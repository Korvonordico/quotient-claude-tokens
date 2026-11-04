"""Codex (OpenAI) support, experimental (1.3.6).

Codex writes each session to a JSON-lines log (~/.codex/sessions/.../rollout-*.jsonl) in its own shape. Here that log
is turned into the shape of a Claude Code transcript, so the rest of Quotient reads it unchanged: the user's messages,
one assistant entry per model call with its usage (cached input counted as a cache read), and the model's text. The
plan limits (5 hours, week) are taken from the same log. `setup-codex` adds Quotient's hooks to Codex.
OpenAI says the log format is not a stable interface: a change there needs a change here."""
import json
import os
import sys

WINDOWS = {300: "five_hour", 10080: "seven_day"}


def is_codex_row(row):
    return isinstance(row, dict) and "payload" in row and "timestamp" in row and isinstance(row.get("type"), str)


def usage_of(last):
    """Codex counts cached input and cache writes inside input_tokens; Quotient keeps them apart."""
    cached = last.get("cached_input_tokens") or 0
    write = last.get("cache_write_input_tokens") or 0
    return {"input_tokens": max(0, (last.get("input_tokens") or 0) - cached - write),
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": write,
            "output_tokens": last.get("output_tokens") or 0}


def raw_rows(path, tail_bytes=None):
    rows = []
    try:
        with open(path, "rb") as f:
            if tail_bytes:
                f.seek(0, os.SEEK_END)
                if f.tell() > tail_bytes:
                    f.seek(f.tell() - tail_bytes)
                    f.readline()
                else:
                    f.seek(0)
            for line in f:
                try:
                    rows.append(json.loads(line.decode("utf-8", "replace")))
                except ValueError:
                    pass
    except (OSError, TypeError):
        pass
    return rows


def is_codex_file(path):
    if not path:
        return False
    if os.path.basename(path).startswith("rollout-"):
        return True
    try:
        with open(path, "rb") as f:
            return is_codex_row(json.loads(f.readline().decode("utf-8", "replace")))
    except (OSError, ValueError, TypeError):
        return False


def convert(rows):
    """Codex log rows -> Claude Code-like entries; rows that are not Codex's are kept as they are."""
    out, texts, model, seen, last_ts = [], [], None, set(), None
    prev_total = None
    # Newer Codex writes one token_usage_record per model call; older logs only the running token_count events.
    records = any(isinstance(r, dict) and r.get("type") == "token_usage_record" for r in rows)
    for r in rows:
        if not is_codex_row(r):
            out.append(r)
            continue
        p = r.get("payload") or {}
        ts = r.get("timestamp")
        last_ts = ts or last_ts
        if r.get("type") == "turn_context":
            model = p.get("model") or model
            continue
        if r.get("type") == "token_usage_record":
            key = p.get("response_id") or json.dumps(p.get("usage"), sort_keys=True)
            if key in seen or not isinstance(p.get("usage"), dict):
                continue
            seen.add(key)
            out.append({"type": "assistant", "timestamp": ts, "requestId": "codex-%s" % key,
                        "message": {"model": model, "usage": usage_of(p["usage"]),
                                    "content": [{"type": "text", "text": t} for t in texts]}})
            texts = []
            continue
        if r.get("type") != "event_msg":
            continue
        kind = p.get("type")
        if kind == "user_message":
            out.append({"type": "user", "timestamp": ts, "message": {"role": "user", "content": p.get("message") or ""}})
        elif kind == "agent_message":
            texts.append(p.get("message") or "")
        elif kind == "token_count" and not records:
            info = p.get("info") or {}
            total = info.get("total_token_usage") or {}
            last = info.get("last_token_usage")
            key = json.dumps(total, sort_keys=True)
            if not total or key in seen:
                continue   # no usage, or the same call told again (Codex repeats it with new limits)
            seen.add(key)
            if not last:   # an older log: the call is the difference of the running totals
                last = {k: (total.get(k) or 0) - ((prev_total or {}).get(k) or 0) for k in total}
            prev_total = total
            out.append({"type": "assistant", "timestamp": ts, "requestId": "codex-" + key,
                        "message": {"model": model, "usage": usage_of(last),
                                    "content": [{"type": "text", "text": t} for t in texts]}})
            texts = []
    if texts:   # text written after the last usage: kept, at no cost
        out.append({"type": "assistant", "timestamp": last_ts, "uuid": "codex-text-%d" % len(out),
                    "message": {"model": model, "content": [{"type": "text", "text": t} for t in texts]}})
    return out


def limits_of(rows):
    """The last plan limits in the log, in Quotient's shape: five_hour / seven_day used % and when they reset."""
    from quotient_lib import q_limits
    for r in reversed(rows):
        if not isinstance(r, dict):
            continue
        p = r.get("payload") or {}
        if r.get("type") != "event_msg" or p.get("type") != "token_count" or not isinstance(p.get("rate_limits"), dict):
            continue
        snap = {}
        for w in p["rate_limits"].values():
            if not isinstance(w, dict) or w.get("used_percent") is None:
                continue
            name = WINDOWS.get(w.get("window_minutes"))
            if not name:
                continue
            snap[name] = float(w["used_percent"])
            if w.get("resets_at"):
                snap[name + "_resets"] = q_limits.to_epoch(w["resets_at"])
            elif w.get("resets_in_seconds") is not None:
                snap[name + "_resets"] = q_limits.ts_epoch(r.get("timestamp")) + float(w["resets_in_seconds"])
        if snap:
            return snap
    return None


def run_hook(fn, name):
    """Runs a hook; inside Codex the limits come from its log, not from `claude -p /usage`, and the Stop hook only
    prints JSON (Codex refuses plain text there)."""
    from quotient_lib import q_limits, q_settings
    data = q_settings.read_stdin_json()
    q_settings.read_stdin_json = lambda: data
    path = data.get("transcript_path") or ""
    if os.environ.get("QUOTIENT_CODEX") or is_codex_file(path):
        os.environ["QUOTIENT_LIMITS_LIVE"] = "0"
        try:
            snap = limits_of(raw_rows(path, tail_bytes=2 * 1024 * 1024))
            if snap:
                q_limits.record_limits(snap, "codex")
        except Exception as exc:   # limits that cannot be read must never stop a message
            sys.stderr.write("quotient: codex limits: %s\n" % exc)
        if name == "hook-stop":
            plain = q_settings.out
            q_settings.out = lambda text: plain(text) if text.lstrip().startswith("{") else None
    fn()


def setup(args=None):
    """Adds Quotient's hooks to Codex (~/.codex/hooks.json, or $CODEX_HOME), replacing older Quotient entries."""
    from quotient_lib import q_settings, q_sharing
    home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, "hooks.json")
    try:
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    except (OSError, ValueError):
        conf = {}
    entry = q_settings.ENTRY_FILE
    py = sys.executable
    posix = '"%s" "%s"' % (py.replace("\\", "/"), entry.replace("\\", "/"))
    windows = ('%s "%s"' % (py, entry)) if " " not in py else 'py -3 "%s"' % entry
    hooks = conf.setdefault("hooks", {})
    for event, cmd, timeout in (("SessionStart", "hook-session", 20), ("UserPromptSubmit", "hook-prompt", 20),
                                ("Stop", "hook-stop", 30)):
        groups = [g for g in hooks.get(event) or []
                  if not any("quotient.py" in (h.get("command") or "") for h in g.get("hooks") or [])]
        handler = {"type": "command", "command": "%s %s --codex" % (posix, cmd),
                   "commandWindows": "%s %s --codex" % (windows, cmd),
                   "timeout": timeout, "statusMessage": "Quotient"}
        if event != "Stop":
            handler["additionalContextLimit"] = 0   # the whole protocol and quote lines, not a preview
        groups.append({"hooks": [handler]})
        hooks[event] = groups
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    # Codex jobs are not sent to the shared averages: those are per Claude plan.
    q_sharing.store(("share", "enabled"), False)
    q_settings.out("Quotient hooks added to %s.\nNext: open Codex, type /hooks and trust the three Quotient hooks "
                   "(Codex skips new hooks until you trust them). Sharing of anonymous job data is now off.\n" % path)
