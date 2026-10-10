"""Quotient inside Hermes Agent: shell hooks for pre_llm_call and post_llm_call.

Hermes runs `python quotient.py hermes-hook` with a JSON payload on stdin (hook_event_name, session_id, extra...).
- pre_llm_call: reads Hermes' token counters and the plan limits, and gives the agent the quote protocol (in full the
  first time in a chat, then one short line), as {"context": ...}.
- post_llm_call: reads the machine lines of the reply (QUOTE / CHOICE / JOB) and opens or closes a measured job.
  A job's real cost is the growth of the chat's counters (its subagents included) between CHOICE and the close;
  the chat part is the re-reading of what the chat held when the job started, as in Claude Code.

Job state per chat: ~/.quotient/hermes-jobs.json. Finished jobs go to jobs.jsonl with "source": "hermes", so the
correction factor learns from Hermes and Claude Code alike.
"""

import json
import os
import sys
import time

import re

import hermes_source as hs

# In Hermes a job needs no id: one open job per chat.
END_RE = re.compile(r"^[\s>*_`#-]*(?:JOB|LAVORO)[*_`]*\s*:[\s*_`]*(CLOSE|CHIUDI|DONE|FINITO|DROP|ABBANDONA)\b",
                    re.M | re.I)


def parse_end(text):
    found = None
    for m in END_RE.finditer(text or ""):
        found = "drop" if m.group(1).lower() in ("drop", "abbandona") else "close"
    return found


def _state_path(q):
    return os.path.join(q.home(), "hermes-jobs.json")


def _load(q):
    return q.load_json(_state_path(q), {})


def _save(q, state):
    q.save_json(_state_path(q), state)


def _counters(sid):
    """Counters of a chat plus its subagents, and its API calls."""
    total = {k: 0 for k in hs.COUNTERS}
    calls = 0
    for row in hs.read_sessions():
        if row.get("id") == sid or row.get("parent_session_id") == sid:
            for k in hs.COUNTERS:
                total[k] += int(row.get(k) or 0)
            if row.get("id") == sid:
                calls = int(row.get("api_call_count") or 0)
    return total, calls


def _context_per_call(state_chat, totals, calls):
    """What one call re-reads now: the cache read of the last calls divided by their number."""
    last = state_chat.get("last") or {}
    d_calls = calls - (last.get("calls") or 0)
    d_read = totals["cache_read_tokens"] - (last.get("cache_read_tokens") or 0)
    if d_calls > 0 and d_read > 0:
        return d_read / d_calls
    if state_chat.get("ctx"):
        return state_chat["ctx"]
    return totals["cache_read_tokens"] / calls if calls else 0    # first look: the chat's average so far


def short_line(q, cfg, factor, ctx):
    lang = cfg.get("lang")
    limits = q.limits_line(lang) or ("limiti non letti" if lang == "it" else "limits not read")
    chat = q.fmt(ctx * cfg["weights"]["cache_read"]) if ctx else "?"
    return ("[Quotient %s] %s · factor x%.2f · threshold %s wt · CHAT PART: each step re-reads about %s tokens "
            "(%s wt). Big job: quote first (QUOTE / CHOICE / JOB: CLOSE in the last message)." % (
                q.VERSION, limits, factor, q.fmt(cfg["threshold"]), q.fmt(ctx), chat))


def hermes_protocol(q, cfg, factor):
    """Quotient's protocol, adapted: in Hermes the choice window is the clarify tool and there are no slash commands."""
    text = q.protocol(cfg, factor)
    text = text.replace("call the AskUserQuestion tool", "call the clarify tool (one call, both questions)")
    return text + ("In Hermes: when the quoted job is finished (or abandoned), write `JOB: CLOSE` (or `JOB: DROP` if abandoned) "
                   "in the last message, so Quotient measures it. Installments (rate) run with Claude Code.\n")


def pre_llm_call(q, payload):
    cfg = q.config()
    sid = payload.get("session_id") or ""
    q.measured_turns(cfg)
    q.refresh_limits(cfg)
    state = _load(q)
    chat = state.setdefault(sid, {})
    totals, calls = _counters(sid)
    ctx = _context_per_call(chat, totals, calls)
    chat["ctx"] = ctx
    chat["last"] = dict(totals, calls=calls)
    factor = q.learning(cfg)["factor"]
    if not chat.get("told"):
        chat["told"] = True
        text = hermes_protocol(q, cfg, factor) + short_line(q, cfg, factor, ctx)
    else:
        text = short_line(q, cfg, factor, ctx)
    open_job = chat.get("job")
    # Long chats (the lesson of M33: re-reading the chat is most of the cost). Two notices at most, a day apart.
    big = (cfg.get("chat") or {}).get("hermes_compress_at", 250000)
    told = chat.setdefault("compress_told", [])
    if ctx > big and len(told) < 2 and (not told or time.time() - told[-1] > 24 * 3600):
        told.append(time.time())
        text += (" LONG CHAT: each step re-reads about %s tokens (%s wt). Tell the user once, in one line, that "
                 "/compress (or a new chat with a summary) would make every next step cheaper." % (
                     q.fmt(ctx), q.fmt(ctx * cfg["weights"]["cache_read"])))
    if open_job:
        spent = hs.weigh_hermes({k: totals[k] - open_job["start"][k] for k in hs.COUNTERS}, cfg["weights"])
        text += " Open job: %s, about %s wt spent of %s (raw)." % (open_job["choice"], q.fmt(spent),
                                                                   q.fmt(open_job["raw_estimate"]))
    _save(q, state)
    return {"context": text}


def _close(q, cfg, chat, totals, calls, how):
    job = chat.pop("job")
    grow = {k: max(0, totals[k] - job["start"][k]) for k in hs.COUNTERS}
    actual = hs.weigh_hermes(grow, cfg["weights"])
    d_calls = max(0, calls - job.get("start_calls", calls))
    chat_part = min(actual, d_calls * (job.get("ctx") or 0) * cfg["weights"]["cache_read"])
    row = {"started": job["started"], "session": "hermes:" + job["session"], "source": "hermes",
           "options": job["options"], "choice": job["choice"], "raw_estimate": job["raw_estimate"],
           "factor_used": job["factor"], "quote_cost": 0, "actual": round(actual), "chat": chat_part,
           "turns": job.get("turns", 1), "families": {q.family_of(job.get("model") or ""): round(actual)},
           "closed_by": how}
    if how == "drop":
        return None
    q.close_job(row, cfg)
    return row


def post_llm_call(q, payload):
    cfg = q.config()
    sid = payload.get("session_id") or ""
    extra = payload.get("extra") or {}
    text = extra.get("assistant_response") or ""
    if not isinstance(text, str):
        text = str(text)
    state = _load(q)
    chat = state.setdefault(sid, {})
    totals, calls = _counters(sid)
    quote = q.parse_quote(text)
    choice = q.parse_choice(text)
    move = parse_end(text)
    closed = None
    if chat.get("job"):
        chat["job"]["turns"] = chat["job"].get("turns", 1) + 1
        if move:
            closed = _close(q, cfg, chat, totals, calls, move)
        elif quote:                      # a new quote ends the job before it
            closed = _close(q, cfg, chat, totals, calls, "new-quote")
    if quote:
        chat["quote"] = {"options": quote, "ts": time.time()}
    if choice:
        pending = (chat.get("quote") or {}).get("options") or {}
        if choice in q.DECLINE or choice not in pending:
            chat.pop("quote", None)
        else:
            chat["job"] = {"session": sid, "started": q.now_iso(), "options": pending, "choice": choice,
                           "raw_estimate": pending[choice], "factor": q.learning(cfg)["factor"],
                           "start": totals, "start_calls": calls, "ctx": chat.get("ctx") or 0,
                           "model": extra.get("model") or ""}
            chat.pop("quote", None)
    _save(q, state)
    return {"closed": closed} if closed else {}


def main(q):
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    event = payload.get("hook_event_name")
    try:
        if event == "pre_llm_call":
            result = pre_llm_call(q, payload)
        elif event == "post_llm_call":
            post_llm_call(q, payload)
            result = {}
        else:
            result = {}
    except Exception as e:          # never break a Hermes turn
        result = {}
        q.append_jsonl(os.path.join(q.home(), "hermes-errors.jsonl"), {"ts": q.now_iso(), "event": event, "error": repr(e)})
    sys.stdout.write(json.dumps(result) + "\n")
