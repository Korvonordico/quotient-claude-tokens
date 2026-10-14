"""Hermes Agent as a second source for Quotient.

Hermes (https://github.com/NousResearch/hermes-agent) can run Claude with the same Claude Code login, so its chats
use the same 5-hour and weekly limits. Hermes keeps, per chat, running totals of the tokens in its session store
(SQLite, read here read-only). It does not keep one line per API call, so Quotient takes a snapshot of the totals
and records what grew since the last snapshot: each growth is one row of hermes.jsonl, with the time it was seen.

Nothing is sent anywhere and no chat text is read: only the token counters, the model and the chat title.
"""

import json
import os
import sqlite3
import time

COUNTERS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")


def hermes_home():
    """Where Hermes keeps its data: $HERMES_HOME, else %LOCALAPPDATA%\\hermes on Windows, else ~/.hermes."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return env
    local = os.environ.get("LOCALAPPDATA")
    if local and os.path.isdir(os.path.join(local, "hermes")):
        return os.path.join(local, "hermes")
    return os.path.join(os.path.expanduser("~"), ".hermes")


def db_path(home=None):
    return os.path.join(home or hermes_home(), "state.db")


def available(home=None):
    return os.path.isfile(db_path(home))


def weigh_hermes(row, weights):
    """Weighted tokens from Hermes' counters. Hermes does not split 5-minute and 1-hour cache writes:
    they count as 5-minute writes (the cheaper one), so this is a floor, not an overestimate."""
    return ((row.get("input_tokens") or 0) * weights["input"]
            + (row.get("cache_write_tokens") or 0) * weights["cache_write_5m"]
            + (row.get("cache_read_tokens") or 0) * weights["cache_read"]
            + (row.get("output_tokens") or 0) * weights["output"])


def read_sessions(home=None):
    """One dict per Hermes chat (subagents included, with their parent). Empty list if Hermes is not there."""
    path = db_path(home)
    if not os.path.isfile(path):
        return []
    uri = "file:" + path.replace("\\", "/") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        return []
    try:
        con.row_factory = sqlite3.Row
        cols = {r[1] for r in con.execute("pragma table_info(sessions)")}
        want = ["id", "source", "model", "started_at", "ended_at", "parent_session_id", "title",
                "last_activity_at", "estimated_cost_usd", "billing_provider", "api_call_count"] + list(COUNTERS)
        got = [c for c in want if c in cols]
        if "id" not in got or not set(COUNTERS) <= set(got):
            return []
        rows = [dict(r) for r in con.execute("select %s from sessions" % ", ".join(got))]
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return rows


def is_anthropic(row):
    """Only Claude chats count against the plan; other providers (OpenRouter, local models) do not."""
    provider = (row.get("billing_provider") or "").lower()
    model = (row.get("model") or "").lower()
    return "anthropic" in provider or "claude" in model or (not provider and model.startswith(("opus", "sonnet", "haiku")))


def sync(quotient_home, weights, home=None, now=None):
    """Compare Hermes' totals with the last snapshot and append the growth to hermes.jsonl.
    The first time, each chat's whole total is dated at its last activity (or its end, or its start).
    Returns the rows appended."""
    now = now if now is not None else time.time()
    state_path = os.path.join(quotient_home, "hermes-state.json")
    log_path = os.path.join(quotient_home, "hermes.jsonl")
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    first = not state
    seen = state.get("sessions", {})
    added = []
    for row in read_sessions(home):
        if not is_anthropic(row):
            continue
        sid = row["id"]
        totals = {k: int(row.get(k) or 0) for k in COUNTERS}
        before = seen.get(sid, {k: 0 for k in COUNTERS})
        grow = {k: max(0, totals[k] - int(before.get(k) or 0)) for k in COUNTERS}
        # a chat whose counters went down (rewound or repaired): start again from the new totals
        if any(totals[k] < int(before.get(k) or 0) for k in COUNTERS):
            grow = dict(totals) if first else {k: 0 for k in COUNTERS}
        seen[sid] = totals
        wt = weigh_hermes(grow, weights)
        if wt <= 0:
            continue
        when = now
        if first or sid not in state.get("sessions", {}):
            when = row.get("last_activity_at") or row.get("ended_at") or row.get("started_at") or now
            when = min(float(when), now)
        added.append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(when)),
                      "epoch": round(float(when), 1), "session": sid, "parent": row.get("parent_session_id"),
                      "kind": "subagent" if row.get("source") == "subagent" else "chat",
                      "title": (row.get("title") or "")[:80], "model": row.get("model") or "",
                      "wt": round(wt), **grow})
    if added:
        os.makedirs(quotient_home, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for r in added:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    state = {"sessions": seen, "synced": now}
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, state_path)
    return added


def messages(sid, since, until, home=None):
    """(time, role, tool name) of a chat's messages between two moments, oldest first: only when they were written
    and by whom, never their text. None if the session store cannot be read."""
    path = db_path(home)
    if not sid or not os.path.isfile(path):
        return None
    uri = "file:" + path.replace("\\", "/") + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        cols = {r[1] for r in con.execute("pragma table_info(messages)")}
        if not {"session_id", "role", "timestamp"} <= cols:
            return None
        tool = "tool_name" if "tool_name" in cols else "NULL"
        rows = con.execute("select timestamp, role, %s from messages where session_id = ? and timestamp >= ? "
                           "and timestamp <= ? order by timestamp, id" % tool, (sid, since, until)).fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()
    return [(float(t), r, n) for t, r, n in rows if t is not None]


def last_user_message(sid, before, home=None):
    """When the user last wrote in a chat, at or before a moment (the start of that turn), or None."""
    rows = messages(sid, before - 7 * 86400, before, home) or []
    users = [t for t, role, _ in rows if role == "user"]
    return users[-1] if users else None


def active_seconds(sid, since, until, home=None):
    """The agent's working time in a chat between two moments: the time between its consecutive messages, without
    the user's turns (a user message starts a new turn: the wait before it was the user's) and without the waits of
    the choice window (a clarify result arrives when the user has chosen). The stretch after the last message up to
    `until` counts (the last answer is written as the turn ends). None if the messages cannot be read."""
    rows = messages(sid, since - 1, until + 1, home)
    if rows is None:
        return None
    total, prev = 0.0, since
    for ts, role, tool in rows:
        ts = min(max(ts, since), until)
        if role == "user" or (role == "tool" and tool == "clarify"):
            prev = ts
            continue
        total += max(0.0, ts - prev)
        prev = ts
    return total + max(0.0, until - prev)


def read_log(quotient_home):
    rows = []
    try:
        with open(os.path.join(quotient_home, "hermes.jsonl"), encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def summary(quotient_home, now=None, since=None):
    """Totals for the report: last 5 hours, last 7 days (or since a reset), the heaviest chats, the subagents' share."""
    now = now if now is not None else time.time()
    rows = read_log(quotient_home)
    def in_window(r, lo):
        return (r.get("epoch") or 0) >= lo
    week_lo = since if since else now - 7 * 86400
    week = [r for r in rows if in_window(r, week_lo)]
    five = [r for r in rows if in_window(r, now - 5 * 3600)]
    chats = {}
    for r in week:
        key = r.get("parent") or r["session"]
        c = chats.setdefault(key, {"wt": 0, "title": "", "sub": 0})
        c["wt"] += r["wt"]
        if r.get("kind") == "subagent":
            c["sub"] += r["wt"]
        elif r.get("title"):
            c["title"] = r["title"]
    top = sorted(chats.items(), key=lambda kv: -kv[1]["wt"])[:5]
    return {"rows": len(rows), "five_hour": sum(r["wt"] for r in five), "week": sum(r["wt"] for r in week),
            "subagents": sum(r["wt"] for r in week if r.get("kind") == "subagent"), "top": top,
            "read_share": (sum(r.get("cache_read_tokens", 0) * 0.1 for r in week) / max(1, sum(r["wt"] for r in week)))}
