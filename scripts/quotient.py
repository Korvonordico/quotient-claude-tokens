#!/usr/bin/env python3
"""Quotient: a cost estimate before a big AI job, the real cost after it,
and a correction learned from the difference.

Part of a Claude Code plugin. Standard library only (Python 3.8+).

Commands:
  hook-session         SessionStart hook: the quote protocol, once per session
  hook-prompt          UserPromptSubmit hook (reads the hook JSON on stdin)
  hook-stop            Stop hook
  hook-pretool         PreToolUse hook, used only inside installment runs
  report               estimates, real costs and how the error is changing
  config [KEY [VALUE]] show or change the settings
  export               only the numbers of the finished jobs, to share
  rate ...             the work in installments (see `rate --help`)
"""

import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

VERSION = "0.3.0"

DEFAULTS = {
    # Below this many weighted tokens no quote is asked for.
    "threshold": 300000,
    # When the middle option is above threshold x this, more options and installments.
    "many_options_factor": 5,
    # Weights relative to one input token: the ratios of Anthropic's API prices.
    "weights": {
        "input": 1.0,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
        "cache_read": 0.1,
        "output": 5.0,
    },
    # How many recent jobs the correction factor is learned from.
    "history_window": 20,
    # Below this many measured jobs the factor is shown as uncertain.
    "min_jobs": 5,
    # A quote nobody chose is dropped after this many turns.
    "pending_ttl_turns": 3,
    # Language of the report: "en" or "it".
    "lang": "en",
    # Path to the claude executable; empty means "find it".
    "claude_path": "",
    "rate": {
        # Put in front of every installment prompt (for example a tag your own hooks skip).
        "prompt_prefix": "",
        "permission_mode": "acceptEdits",
        "max_turns": 200,
        # Hard cap in dollars = daily cap x learned dollars per weighted token x this margin.
        "usd_cap_margin": 1.5,
        "timeout_minutes": 240,
        "extra_args": [],
    },
}

QUOTE_KEYS = r"(?:PREVENTIVO|ESTIMATE|QUOTE)"
CHOICE_KEYS = r"(?:SCELTA|CHOICE)"
QUOTE_RE = re.compile(r"^[\s>*_`#-]*" + QUOTE_KEYS + r"[*_`]*\s*:\s*(.+)$", re.M)
CHOICE_RE = re.compile(r"^[\s>*_`#-]*" + CHOICE_KEYS + r"[*_`]*\s*:[\s*_`]*([^\s*_`,.;:]+)", re.M)
CONTINUES_RE = re.compile(r"(?:JOB|LAVORO)[*_`]*\s*:\s*[*_`]*(?:CONTINUES|CONTINUA)", re.I)
PACE_RE = re.compile(r"^[\s>*_`#-]*(?:PACE|RITMO)[*_`]*\s*:[\s*_`]*([^\n]+)", re.M)
TODAY_RE = re.compile(r"\b(?:today|oggi|all|tutto)\b", re.I)
OPTION_RE = re.compile(r"([^\W\d][\w-]*)\s*=\s*~?\s*(\d[\d.,_]*)\s*([kKmM])?(?![\w])")
DECLINE = {"none", "nessuna", "nessuno", "no", "annulla", "cancel"}
INSTALLMENT_RE = re.compile(r"^(?:split|rata|rate|installments?)\d*$", re.I)
DONE_RE = re.compile(r"\b(?:JOB DONE|LAVORO FINITO)\b")


# ---------------------------------------------------------------- storage

def home():
    path = os.environ.get("QUOTIENT_HOME") or os.path.join(os.path.expanduser("~"), ".quotient")
    os.makedirs(path, exist_ok=True)
    return path


def merge(base, over):
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value)
        else:
            out[key] = value
    return out


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def append_jsonl(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path, tail_bytes=None):
    """Rows of a JSON-lines file; with tail_bytes, only the rows in its last part."""
    rows = []
    try:
        with open(path, "rb") as f:
            if tail_bytes:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                if size > tail_bytes:
                    f.seek(size - tail_bytes)
                    f.readline()  # skip the cut line
                else:
                    f.seek(0)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line.decode("utf-8", "replace")))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def config():
    return merge(DEFAULTS, load_json(os.path.join(home(), "config.json"), {}))


def session_path(session_id):
    safe = re.sub(r"[^\w-]", "_", session_id or "unknown")
    return os.path.join(home(), "sessions", safe + ".json")


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def out(text):
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def read_stdin_json():
    raw = sys.stdin.buffer.read().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}


# ---------------------------------------------------------------- cost

def weigh(usage, weights):
    """Weighted tokens of one API call: input-token equivalents at API price ratios."""
    if not usage:
        return 0.0
    inp = usage.get("input_tokens") or 0
    read = usage.get("cache_read_input_tokens") or 0
    write = usage.get("cache_creation_input_tokens") or 0
    split = usage.get("cache_creation") or {}
    w1h = split.get("ephemeral_1h_input_tokens")
    w5m = split.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w5m, w1h = write, 0
    else:
        w1h, w5m = w1h or 0, w5m or 0
        w5m += max(0, write - w1h - w5m)
    output = usage.get("output_tokens") or 0
    return (inp * weights["input"] + w5m * weights["cache_write_5m"]
            + w1h * weights["cache_write_1h"] + read * weights["cache_read"]
            + output * weights["output"])


def is_turn_start(entry):
    """A user entry that is not a tool result starts a new turn."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        return "tool_result" not in kinds and bool(kinds)
    return False


def calls_of(entries):
    """One record per API call: the transcript repeats a call once per content block."""
    calls = {}
    for e in entries:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        key = e.get("requestId") or msg.get("id") or e.get("uuid")
        usage = msg.get("usage") or {}
        old = calls.get(key)
        if old is None or (usage.get("output_tokens") or 0) > (old.get("output_tokens") or 0):
            calls[key] = usage
    return calls


def subagent_entries(transcript_path, since_ts):
    base = transcript_path[:-6] if transcript_path.endswith(".jsonl") else transcript_path
    rows = []
    for path in glob.glob(os.path.join(base, "subagents", "*.jsonl")):
        for e in read_jsonl(path):
            if since_ts is None or (e.get("timestamp") or "") >= since_ts:
                rows.append(e)
    return rows


def turn_of(transcript_path):
    """Entries of the last turn, its start time, and the text Claude wrote in it."""
    entries = read_jsonl(transcript_path, tail_bytes=8 * 1024 * 1024)
    if not any(is_turn_start(e) for e in entries):
        entries = read_jsonl(transcript_path)
    start = 0
    for i, e in enumerate(entries):
        if is_turn_start(e):
            start = i
    turn = [e for e in entries[start:] if not e.get("isSidechain")]
    start_ts = entries[start].get("timestamp") if entries else None
    texts = []
    for e in turn:
        if e.get("type") == "assistant":
            for block in (e.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text") or "")
    return turn, start_ts, "\n".join(texts)


def cost_of(entries, weights):
    calls = calls_of(entries)
    return round(sum(weigh(u, weights) for u in calls.values())), len(calls)


def context_size(transcript_path):
    """Tokens the model re-reads at each call: the size of the last call's prompt."""
    size = 0
    for e in read_jsonl(transcript_path, tail_bytes=2 * 1024 * 1024):
        if e.get("type") == "assistant" and not e.get("isSidechain"):
            u = (e.get("message") or {}).get("usage") or {}
            size = ((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                    + (u.get("cache_creation_input_tokens") or 0))
    return size


# ---------------------------------------------------------------- parsing

def parse_amount(number, suffix):
    s = number.replace("_", "").strip()
    if suffix:
        s = s.replace(",", ".")
        if s.count(".") > 1:
            s = s.replace(".", "", s.count(".") - 1)
        value = float(s) * (1000 if suffix.lower() == "k" else 1000000)
    else:
        value = float(re.sub(r"[.,]", "", s))
    return int(round(value))


def parse_quote(text):
    """Options of the last machine line QUOTE: name=amount ... (PREVENTIVO and ESTIMATE work too)."""
    found = None
    for match in QUOTE_RE.finditer(text or ""):
        options = {}
        for name, number, suffix in OPTION_RE.findall(match.group(1)):
            try:
                options[name.lower()] = parse_amount(number, suffix)
            except ValueError:
                pass
        if options:
            found = options
    return found


def parse_pace(text):
    """'today', the installment plan as written, or None."""
    match = PACE_RE.search(text or "")
    if not match:
        return None
    value = match.group(1).strip()
    return "today" if TODAY_RE.search(value) else value


def parse_choice(text):
    match = CHOICE_RE.search(text or "")
    return match.group(1).lower() if match else None


# ---------------------------------------------------------------- learning

def finished_jobs():
    return [j for j in read_jsonl(os.path.join(home(), "jobs.jsonl"))
            if j.get("raw_estimate") and j.get("actual")]


def factor_from(jobs, window):
    """Median ratio real/estimate of the recent jobs (geometric, so x2 and /2 weigh the same)."""
    ratios = [j["actual"] / j["raw_estimate"] for j in jobs[-window:]]
    if not ratios:
        return 1.0
    logs = sorted(math.log(r) for r in ratios)
    mid = len(logs) // 2
    med = logs[mid] if len(logs) % 2 else (logs[mid - 1] + logs[mid]) / 2
    return math.exp(med)


def miss(ratio):
    """How far off, as a factor >= 1: x2 too low and x2 too high both give 2."""
    return max(ratio, 1 / ratio) if ratio > 0 else float("inf")


def median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def learning(cfg):
    jobs = finished_jobs()
    window = cfg["history_window"]
    rows = []
    for i, job in enumerate(jobs):
        before = factor_from(jobs[:i], window)
        corrected = job["raw_estimate"] * before
        rows.append({
            "job": job,
            "factor_before": before,
            "corrected": corrected,
            "miss_raw": miss(job["actual"] / job["raw_estimate"]),
            "miss_corrected": miss(job["actual"] / corrected),
        })
    return {"jobs": jobs, "rows": rows, "factor": factor_from(jobs, window)}


# ---------------------------------------------------------------- formatting

def fmt(n):
    if n is None:
        return "-"
    n = float(n)
    if n >= 1e6:
        return "%.2fM" % (n / 1e6)
    if n >= 1e3:
        return "%.0fk" % (n / 1e3)
    return "%.0f" % n


def fmt_miss(m):
    return "x%.2f" % m if m != float("inf") else "-"


# ---------------------------------------------------------------- hooks

def run_cmd():
    """How Claude should call this script: the same Python that runs the hooks."""
    return '"%s" "%s"' % (sys.executable, os.path.abspath(__file__))


def calibration(cfg, learned):
    n = len(learned["jobs"])
    if n == 0:
        return "No finished jobs yet, so the correction factor is x1 and the first estimates will be rough."
    rows = learned["rows"]
    return "Correction factor from %d finished job(s): x%.2f%s; typical miss before correction %s, recent miss with it %s." % (
        n, learned["factor"], " (still uncertain)" if n < cfg["min_jobs"] else "",
        fmt_miss(median([r["miss_raw"] for r in rows])), fmt_miss(median([r["miss_corrected"] for r in rows[-5:]])))


def protocol(cfg, factor):
    """The full rules, given once at the start of a session (and after a compaction)."""
    cmd = run_cmd()
    big = cfg["threshold"] * cfg["many_options_factor"]
    return "\n".join([
        "[Quotient %s] Quote protocol for this session. Unit: weighted tokens (wt) = input + 1.25 x cache write (2 x for 1-hour cache) + 0.1 x cache read + 5 x output, the ratios of the API prices." % VERSION,
        "WHEN: before work that will likely cost more than the threshold (%s wt), and whenever the user calls a job big or asks for a quote. Do not start the work: quote first. Under the threshold, if nobody asks, just work." % fmt(cfg["threshold"]),
        "HOW:",
        "1) Estimate the job at three levels sized to it: essential (the minimum that does the job), good, max. Example for a 500k job: max 500k, good 250k, essential 100k. If 'good' is above %s wt, add a fourth level in between. Corrected estimate = raw x the factor (now x%.2f)." % (fmt(big), factor),
        "2) Write one machine line with your RAW estimates, always in English: QUOTE: essential=<n> good=<n> max=<n>",
        "3) Open the choice window: call the AskUserQuestion tool with two questions in the user's language. 'Livello'/'Level': the levels, each with what it includes and its corrected estimate. 'Ritmo'/'Pace': all today, plus two installment plans that fit the job (e.g. '2 days, ~X a day', '5 days, ~Y a day'). The window always has a free field: the user can write any pace there (e.g. '50k a day'), so mention it. Say the estimates are not guaranteed and get more precise with use. If the tool is not available, ask the same in text.",
        "4) After the answer write `CHOICE: <level>` and one of `PACE: today`, `PACE: days=<n>`, `PACE: daily=<n>`. If today: do the work; if it will not be finished at the end of a reply, end that reply with `JOB: CONTINUES`. If the user declines: `CHOICE: none`.",
        "5) Installments: do NOT do the whole job now. Write what the whole job is to a file, then run: %s rate new <short-name> --dir <work folder> --task-file <file> --quote <raw estimate of the chosen level> plus --days <n> or --daily <n>. Then open a second window with two questions: 'Prima rata'/'First installment' (now; today at a time they write; tonight at 03:00) and 'Ogni giorno'/'Every day' (the daily time; free field). Then: now = run `%s rate run <name>` in the background; a time today = `rate once <name> --time HH:MM`; every day = `rate schedule <name> --time HH:MM`. The user may also start an extra installment on the same day (`rate run <name> --force`), at their own risk: it spends more of that day's limit. Let them choose freely." % (cmd, cmd),
        "Every decision Quotient needs from the user goes through the choice window, with a free field.",
    ]) + "\n"


def rate_events():
    """What happened to installment jobs since the user last wrote: each thing is told once."""
    base = os.path.join(home(), "rate")
    lines = []
    if not os.path.isdir(base):
        return lines
    for name in sorted(os.listdir(base)):
        folder = os.path.join(base, name)
        job = load_json(os.path.join(folder, "job.json"), None)
        if not job:
            continue
        runs = read_jsonl(os.path.join(folder, "runs.jsonl"))
        if len(runs) <= job.get("told", 0):
            continue
        last = runs[-1]
        spent = sum(r.get("wt") or 0 for r in runs)
        if job["status"] == "done":
            lines.append("Installment job '%s' is FINISHED after %d installment(s): real cost %s wt%s. Tell the user." % (
                name, len(runs), fmt(spent),
                " against a raw quote of %s wt" % fmt(job["quote"]) if job.get("quote") else ""))
        elif last.get("error"):
            lines.append("Installment %d of job '%s' FAILED (%s). Open the choice window: retry now / retry at a time they choose / stop the job (`rate stop %s`)." % (
                len(runs), name, str(last["error"])[:200], name))
        else:
            lines.append("Installment %d of job '%s' ended at %s: %s wt of a %s daily cap, %s wt so far. Open the choice window: start the next one now (it spends more of today's limit, at their own risk) / today at a time they choose / at the usual daily time." % (
                len(runs), name, (last.get("finished") or "")[11:16], fmt(last.get("wt")),
                fmt(job["daily_cap"]), fmt(spent)))
        job["told"] = len(runs)
        save_json(os.path.join(folder, "job.json"), job)
    if lines:
        lines.append("Commands: %s rate run <name> --force (in the background) | rate once <name> --time HH:MM | rate schedule <name> --time HH:MM | rate stop <name>" % run_cmd())
    return lines


def hook_session():
    """SessionStart: the full protocol, once per session instead of at every message."""
    read_stdin_json()
    if os.environ.get("QUOTIENT_JOB"):
        return
    cfg = config()
    out(protocol(cfg, learning(cfg)["factor"]))


def hook_prompt():
    data = read_stdin_json()
    name = os.environ.get("QUOTIENT_JOB")
    if name:
        out("[Quotient %s] This is an installment run of the job '%s': follow the prompt. No quotes, no questions to the user.\n" % (VERSION, name))
        return
    cfg = config()
    sid = data.get("session_id") or "unknown"
    state = load_json(session_path(sid), {})
    learned = learning(cfg)
    hints = []
    ctx = context_size(data.get("transcript_path") or "")
    if ctx:
        hints.append("The conversation is ~%s tokens: each model call re-reads it, at least ~%s wt per call." % (
            fmt(ctx), fmt(ctx * cfg["weights"]["cache_read"])))
    lines = ["[Quotient %s] Threshold %s wt. %s %s Quote rules: see the Quotient protocol at the start of the session." % (
        VERSION, fmt(cfg["threshold"]), calibration(cfg, learned), " ".join(hints))]
    lines += rate_events()
    job = state.get("job")
    pending = state.get("pending")
    if job:
        lines.append("A job is in progress (level '%s', raw estimate %s wt, spent so far %s wt). If it is not finished at the end of this reply, end it with the line: JOB: CONTINUES" % (
            job.get("choice"), fmt(job.get("raw_estimate")), fmt(job.get("actual"))))
    elif pending:
        lines.append("A quote waits for the user's choice (raw: %s). If this message chooses, write `CHOICE: <level>` and `PACE: ...` as the protocol says, then go on." % (
            ", ".join("%s=%s" % (k, fmt(v)) for k, v in pending["options"].items())))
    out("\n".join(lines) + "\n")


def close_job(job):
    job["finished"] = now_iso()
    job["ratio"] = round(job["actual"] / job["raw_estimate"], 4) if job.get("raw_estimate") else None
    append_jsonl(os.path.join(home(), "jobs.jsonl"), job)


def hook_stop():
    data = read_stdin_json()
    cfg = config()
    sid = data.get("session_id") or "unknown"
    path = data.get("transcript_path") or ""
    last = data.get("last_assistant_message") or ""
    turn, start_ts, text = turn_of(path)
    # The last message can reach the file a moment after the hook starts.
    for _ in range(6):
        if not last or last.strip()[:200] in text:
            break
        time.sleep(0.3)
        turn, start_ts, text = turn_of(path)
    if last and last.strip()[:200] not in text:
        text += "\n" + last
    entries = turn + subagent_entries(path, start_ts)
    total, calls = cost_of(entries, cfg["weights"])

    state = load_json(session_path(sid), {})
    # Another Stop hook can send Claude back to work: then this hook runs again
    # for the same turn, and only the part not yet counted is added.
    seen = state.get("turn") or {}
    repeat = seen.get("start") == start_ts
    cost = max(0, total - seen.get("counted", 0)) if repeat else total
    state["turn"] = {"start": start_ts, "counted": total}
    append_jsonl(os.path.join(home(), "turns.jsonl"),
                 {"ts": now_iso(), "session": sid, "wt": cost, "calls": calls, "repeat": repeat})

    quote = parse_quote(text)
    choice = parse_choice(text)
    pace = parse_pace(text)
    continues = bool(CONTINUES_RE.search(text))
    job = state.get("job")
    pending = state.get("pending")
    # With the choice window, the quote and the choice arrive in the same turn.
    same_turn = bool(quote and choice and choice in quote)

    if job:
        job["actual"] += cost
        job["turns"] += 0 if repeat else 1
        if quote or not continues:
            close_job(job)
            state["job"] = None
    elif choice and (same_turn or pending):
        source = {"options": quote, "factor": learning(cfg)["factor"], "quote_cost": 0} if same_turn else pending
        state["pending"] = None
        raw = source["options"].get(choice)
        installments = (pace not in (None, "today")) or INSTALLMENT_RE.match(choice)
        if raw and choice not in DECLINE and not installments:
            job = {
                "started": now_iso(), "session": sid, "options": source["options"],
                "choice": choice, "raw_estimate": raw, "factor_used": source.get("factor", 1.0),
                "quote_cost": source.get("quote_cost", 0), "actual": cost, "turns": 1,
            }
            if continues:
                state["job"] = job
            else:
                close_job(job)
    elif pending and not repeat:
        pending["age"] = pending.get("age", 0) + 1
        if pending["age"] > cfg["pending_ttl_turns"]:
            state["pending"] = None

    if quote and not same_turn:
        pending = state.get("pending")
        if repeat and pending and pending.get("options") == quote:
            pending["quote_cost"] = pending.get("quote_cost", 0) + cost
        else:
            state["pending"] = {"ts": now_iso(), "options": quote, "factor": learning(cfg)["factor"],
                                "quote_cost": cost, "age": 0}
    save_json(session_path(sid), state)


def hook_pretool():
    """Inside an installment run: when the day's cap is spent, allow only the handoff update."""
    name = os.environ.get("QUOTIENT_JOB")
    if not name:
        return
    data = read_stdin_json()
    cfg = config()
    job = load_json(os.path.join(rate_dir(name), "job.json"), None)
    if not job:
        return
    path = data.get("transcript_path") or ""
    entries = read_jsonl(path)
    spent, _ = cost_of(entries + subagent_entries(path, None), cfg["weights"])
    cap = job["daily_cap"]
    if spent < cap:
        return
    handoff = os.path.normcase(os.path.abspath(os.path.join(rate_dir(name), "HANDOFF.md")))
    target = (data.get("tool_input") or {}).get("file_path") or ""
    if data.get("tool_name") in ("Write", "Edit", "MultiEdit", "Read") and target and \
            os.path.normcase(os.path.abspath(target)) == handoff:
        return
    reason = ("Quotient: today's installment is used up (%s of %s wt). Do not start new work. "
              "Update %s now (what is done, what remains, where to resume), then stop." % (fmt(spent), fmt(cap), handoff))
    out(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}))


# ---------------------------------------------------------------- report

TEXT = {
    "en": {
        "title": "Quotient: estimates against real costs (unit: weighted tokens)",
        "none": "No finished jobs yet. A job is measured when a quote is made (QUOTE: ...) and an option is chosen (CHOICE: ...).",
        "head": "#   date        choice        estimate    corrected   real        miss",
        "factor": "Correction factor now: x%.2f (from the last %d jobs)%s",
        "uncertain": ", still uncertain: under %d jobs",
        "miss_raw": "Typical miss without correction: %s",
        "trend": "Typical miss with the learned correction: first half %s, second half %s",
        "turns": "Turns measured: %d, median %s wt per turn",
        "note": "Estimates are not guaranteed: they get more precise with use.",
    },
    "it": {
        "title": "Quotient: stime contro costi veri (unità: token pesati)",
        "none": "Ancora nessun lavoro finito. Un lavoro si misura quando c'è un preventivo (QUOTE: ...) e si sceglie un'opzione (CHOICE: ...).",
        "head": "#   data        scelta        stima       corretta    vero        errore",
        "factor": "Fattore di correzione adesso: x%.2f (dagli ultimi %d lavori)%s",
        "uncertain": ", ancora incerto: meno di %d lavori",
        "miss_raw": "Errore tipico senza correzione: %s",
        "trend": "Errore tipico con la correzione imparata: prima metà %s, seconda metà %s",
        "turns": "Turni misurati: %d, mediana %s token pesati a turno",
        "note": "Le stime non sono garantite: diventano più precise con l'uso.",
    },
}


def report():
    cfg = config()
    t = TEXT.get(cfg.get("lang"), TEXT["en"])
    learned = learning(cfg)
    rows = learned["rows"]
    lines = [t["title"], ""]
    if not rows:
        lines.append(t["none"])
    else:
        lines.append(t["head"])
        for i, r in enumerate(rows[-30:], start=max(1, len(rows) - 29)):
            j = r["job"]
            lines.append("%-3d %-11s %-13s %-11s %-11s %-11s %s" % (
                i, (j.get("finished") or "")[:10], (j.get("choice") or "")[:13], fmt(j["raw_estimate"]),
                fmt(r["corrected"]), fmt(j["actual"]), fmt_miss(r["miss_corrected"])))
        lines.append("")
        n = len(rows)
        lines.append(t["factor"] % (learned["factor"], min(n, cfg["history_window"]),
                                    t["uncertain"] % cfg["min_jobs"] if n < cfg["min_jobs"] else ""))
        lines.append(t["miss_raw"] % fmt_miss(median([r["miss_raw"] for r in rows])))
        if n >= 2:
            half = n // 2
            lines.append(t["trend"] % (fmt_miss(median([r["miss_corrected"] for r in rows[:half]])),
                                       fmt_miss(median([r["miss_corrected"] for r in rows[half:]]))))
    turns = [x["wt"] for x in read_jsonl(os.path.join(home(), "turns.jsonl")) if x.get("wt")]
    if turns:
        lines.append(t["turns"] % (len(turns), fmt(median(turns))))
    lines += ["", t["note"]]
    out("\n".join(lines) + "\n")


def export():
    """Only numbers: no text, no paths, no session ids."""
    for j in finished_jobs():
        names = list(j.get("options", {}))
        out(json.dumps({
            "date": (j.get("finished") or "")[:10],
            "options": len(names),
            "level": names.index(j["choice"]) if j.get("choice") in names else None,
            "raw_estimate": j["raw_estimate"],
            "actual": j["actual"],
            "turns": j.get("turns"),
            "version": VERSION,
        }) + "\n")


def cmd_config(args):
    path = os.path.join(home(), "config.json")
    user = load_json(path, {})
    if not args.key:
        out(json.dumps(merge(DEFAULTS, user), indent=1, ensure_ascii=False) + "\n")
        return
    keys = args.key.split(".")
    if args.value is None:
        node = merge(DEFAULTS, user)
        for k in keys:
            node = node[k]
        out(json.dumps(node, ensure_ascii=False) + "\n")
        return
    try:
        value = json.loads(args.value)
    except ValueError:
        value = args.value
    node = user
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    save_json(path, user)
    out("%s = %s\n" % (args.key, json.dumps(value, ensure_ascii=False)))


# ---------------------------------------------------------------- installments

RATE_PROMPT = """You are doing ONE installment of a bigger job, inside a spending cap.
1. Read the job: {task}
2. Read the handoff from the previous installments: {handoff}
3. Continue from where the handoff says. Work in small steps. After each finished step, update {handoff}: what is done, what remains, where to resume. Keep it short.
4. If a tool call is refused because this installment is used up, update {handoff} and stop at once.
5. When the WHOLE job is finished, write the line JOB DONE at the top of {handoff}.
This installment's cap: {cap} weighted tokens. This is installment {number} of about {days}."""


def rate_dir(name):
    return os.path.join(home(), "rate", re.sub(r"[^\w-]", "_", name))


def task_name(name, once=False):
    return "quotient-" + re.sub(r"[^\w-]", "_", name) + ("-once" if once else "")


def find_claude(cfg):
    if cfg.get("claude_path"):
        return cfg["claude_path"]
    found = shutil.which("claude")
    if found:
        return found
    # The Claude desktop app keeps its own copy of Claude Code.
    pattern = os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "*", "*", "claude.exe")

    def version(path):
        parts = os.path.basename(os.path.dirname(os.path.dirname(path))).split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts)

    candidates = sorted(glob.glob(pattern), key=version)
    return candidates[-1] if candidates else None


def find_transcript(session_id):
    pattern = os.path.join(os.path.expanduser("~"), ".claude", "projects", "*", session_id + ".jsonl")
    found = glob.glob(pattern)
    return found[0] if found else None


def rate_new(args):
    folder = rate_dir(args.name)
    if os.path.exists(os.path.join(folder, "job.json")):
        sys.exit("quotient: a job named '%s' already exists" % args.name)
    if args.task_file:
        with open(args.task_file, encoding="utf-8") as f:
            task = f.read()
    elif args.task:
        task = args.task
    else:
        sys.exit("quotient: give the job with --task or --task-file")
    factor = learning(config())["factor"]
    # The daily cap is real spending, so it uses the corrected total.
    total = args.quote * factor if args.quote else None
    if args.daily:
        daily = args.daily
        days = args.days or (max(1, math.ceil(total / daily)) if total else None)
    elif total and args.days:
        daily = math.ceil(total / args.days)
        days = args.days
    else:
        sys.exit("quotient: give --daily (weighted tokens per installment), or --quote with --days")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "TASK.md"), "w", encoding="utf-8") as f:
        f.write(task.strip() + "\n")
    with open(os.path.join(folder, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("Nothing done yet.\n")
    job = {
        "name": args.name, "dir": os.path.abspath(args.dir), "daily_cap": int(daily),
        "days": days, "quote": args.quote, "factor_at_quote": round(factor, 4), "created": now_iso(),
        "status": "open", "model": args.model, "usd_per_wt": None, "told": 0,
    }
    save_json(os.path.join(folder, "job.json"), job)
    out("Job '%s' ready: %s wt per installment%s, working in %s\nJob files: %s\n"
        "Run one installment now: %s rate run %s\nOnce today at a time: %s rate once %s --time HH:MM\n"
        "Every day: %s rate schedule %s --time HH:MM\n" % (
            args.name, fmt(daily), ", about %d installment(s)" % days if days else "", job["dir"], folder,
            run_cmd(), args.name, run_cmd(), args.name, run_cmd(), args.name))


def rate_run(args):
    cfg = config()
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    if job["status"] in ("done", "stopped"):
        out("Job '%s' is %s.\n" % (args.name, job["status"]))
        return
    runs = read_jsonl(os.path.join(folder, "runs.jsonl"))
    today = datetime.now().strftime("%Y-%m-%d")
    if not args.force and any((r.get("started") or "").startswith(today) for r in runs):
        out("Today's installment of '%s' has already run. To run another one today (it spends more of "
            "today's limit): rate run %s --force\n" % (args.name, args.name))
        return
    claude = find_claude(cfg)
    if not claude:
        sys.exit("quotient: claude not found; set it with: config claude_path <path>")
    rc = cfg["rate"]
    prompt = (rc["prompt_prefix"] + " " if rc["prompt_prefix"] else "") + RATE_PROMPT.format(
        task=os.path.join(folder, "TASK.md"), handoff=os.path.join(folder, "HANDOFF.md"),
        cap=fmt(job["daily_cap"]), number=len(runs) + 1, days=job.get("days") or "?")
    hook = {"hooks": {"PreToolUse": [{"hooks": [{
        "type": "command", "command": sys.executable,
        "args": [os.path.abspath(__file__), "hook-pretool"], "timeout": 30}]}]}}
    cmd = [claude, "-p", prompt, "--output-format", "json",
           "--permission-mode", rc["permission_mode"], "--permission-prompts", "none",
           "--max-turns", str(rc["max_turns"]), "--add-dir", folder,
           "--settings", json.dumps(hook)]
    if job.get("model"):
        cmd += ["--model", job["model"]]
    if job.get("usd_per_wt"):
        cmd += ["--max-budget-usd", "%.2f" % (job["daily_cap"] * job["usd_per_wt"] * rc["usd_cap_margin"])]
    cmd += list(rc["extra_args"])
    env = dict(os.environ, QUOTIENT_JOB=args.name)
    started = now_iso()
    try:
        proc = subprocess.run(cmd, cwd=job["dir"], env=env, capture_output=True,
                              timeout=rc["timeout_minutes"] * 60)
        stdout = proc.stdout.decode("utf-8", "replace")
        stderr = proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        stdout, stderr = "", "timeout"
    result = {}
    for line in reversed(stdout.strip().splitlines()):
        try:
            result = json.loads(line)
            break
        except ValueError:
            continue
    sid = result.get("session_id")
    transcript = find_transcript(sid) if sid else None
    if transcript:
        entries = read_jsonl(transcript) + subagent_entries(transcript, None)
        wt, calls = cost_of(entries, cfg["weights"])
    else:
        wt, calls = round(weigh(result.get("usage"), cfg["weights"])), result.get("num_turns")
    usd = result.get("total_cost_usd")
    if usd and wt:
        job["usd_per_wt"] = usd / wt
    with open(os.path.join(folder, "HANDOFF.md"), encoding="utf-8") as f:
        done = bool(DONE_RE.search(f.read()))
    run = {"started": started, "finished": now_iso(), "session": sid, "wt": wt, "calls": calls,
           "usd": usd, "error": result.get("is_error") or (not result and stderr[-300:]) or None,
           "done": done}
    append_jsonl(os.path.join(folder, "runs.jsonl"), run)
    if done:
        job["status"] = "done"
        job["finished"] = run["finished"]
        total = sum(r.get("wt") or 0 for r in runs) + wt
        job["actual"] = total
        if job.get("quote"):
            append_jsonl(os.path.join(home(), "jobs.jsonl"), {
                "started": job["created"], "finished": job["finished"], "session": "rate:" + job["name"],
                "options": {"rate": job["quote"]}, "choice": "rate", "raw_estimate": job["quote"],
                "factor_used": job.get("factor_at_quote", 1.0), "quote_cost": 0, "actual": total,
                "turns": len(runs) + 1, "ratio": round(total / job["quote"], 4)})
        unschedule(args.name)
    save_json(os.path.join(folder, "job.json"), job)
    out("Installment %d of '%s': %s wt (cap %s)%s%s\n" % (
        len(runs) + 1, args.name, fmt(wt), fmt(job["daily_cap"]),
        ". Job finished." if done else "", " Error: %s" % run["error"] if run["error"] else ""))


def rate_status(args):
    base = os.path.join(home(), "rate")
    names = [args.name] if args.name else (sorted(os.listdir(base)) if os.path.isdir(base) else [])
    if not names:
        out("No installment jobs.\n")
    for name in names:
        folder = rate_dir(name)
        job = load_json(os.path.join(folder, "job.json"), None)
        if not job:
            continue
        runs = read_jsonl(os.path.join(folder, "runs.jsonl"))
        spent = sum(r.get("wt") or 0 for r in runs)
        out("%s: %s, %d installment(s), %s wt spent, cap %s per installment%s\n" % (
            name, job["status"], len(runs), fmt(spent), fmt(job["daily_cap"]),
            ", raw quote %s" % fmt(job["quote"]) if job.get("quote") else ""))
        for r in runs[-5:]:
            out("  %s  %s wt%s\n" % (r["started"][:16], fmt(r.get("wt")), "  error" if r.get("error") else ""))


def check_time(value):
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", value or ""):
        sys.exit("quotient: write the time as HH:MM, for example 03:00")
    hh, mm = value.split(":")
    return "%02d:%s" % (int(hh), mm)


def schedule(name, at, once):
    at = check_time(at)
    run = '"%s" "%s" rate run %s%s' % (sys.executable, os.path.abspath(__file__), name, " --force" if once else "")
    if os.name == "nt":
        cmd = ["schtasks", "/Create", "/F", "/SC", "ONCE" if once else "DAILY",
               "/TN", task_name(name, once), "/TR", run, "/ST", at]
        proc = subprocess.run(cmd, capture_output=True)
        out((proc.stdout or proc.stderr).decode("utf-8", "replace") or "")
        out("%s '%s' at %s. Remove it with: rate stop %s\n" % (
            "Scheduled once, today," if once else "Scheduled every day", name, at, name))
    else:
        hh, mm = at.split(":")
        if once:
            out("Run this once (needs `at`):\necho '%s' | at %s\n" % (run, at))
        else:
            out("Add this line with `crontab -e`:\n%d %d * * * %s\n" % (int(mm), int(hh), run))


def unschedule(name):
    if os.name == "nt":
        for once in (False, True):
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", task_name(name, once)], capture_output=True)


def rate_schedule(args):
    schedule(args.name, args.time, once=False)


def rate_once(args):
    schedule(args.name, args.time, once=True)


def rate_stop(args):
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    unschedule(args.name)
    if job["status"] == "open":
        job["status"] = "stopped"
        save_json(os.path.join(folder, "job.json"), job)
    out("Job '%s' stopped; its scheduled runs are removed%s.\n" % (
        args.name, "" if os.name == "nt" else " (remove its crontab line yourself)"))


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(prog="quotient", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd")
    for name in ("hook-session", "hook-prompt", "hook-stop", "hook-pretool", "report", "export"):
        sub.add_parser(name)
    p = sub.add_parser("config")
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")

    rate = sub.add_parser("rate", help="the work in installments")
    rsub = rate.add_subparsers(dest="rate_cmd")
    p = rsub.add_parser("new", help="split a big job into installments")
    p.add_argument("name")
    p.add_argument("--dir", default=".", help="folder the work happens in")
    p.add_argument("--task", help="what the whole job is")
    p.add_argument("--task-file", help="file holding what the whole job is")
    p.add_argument("--days", type=int, help="how many installments")
    p.add_argument("--daily", type=int, help="cap per installment, in weighted tokens")
    p.add_argument("--quote", type=int, help="raw estimate of the whole job, in weighted tokens")
    p.add_argument("--model")
    p = rsub.add_parser("run", help="run one installment now")
    p.add_argument("name")
    p.add_argument("--force", action="store_true", help="run even if one already ran today")
    p = rsub.add_parser("status")
    p.add_argument("name", nargs="?")
    p = rsub.add_parser("schedule", help="run an installment every day at a time")
    p.add_argument("name")
    p.add_argument("--time", default="03:00")
    p = rsub.add_parser("once", help="run one more installment today at a time")
    p.add_argument("name")
    p.add_argument("--time", required=True)
    p = rsub.add_parser("stop", help="stop a job and remove its scheduled runs")
    p.add_argument("name")

    args = parser.parse_args(argv)
    hooks = {"hook-session": hook_session, "hook-prompt": hook_prompt,
             "hook-stop": hook_stop, "hook-pretool": hook_pretool}
    if args.cmd in hooks:
        try:
            hooks[args.cmd]()
        except Exception as exc:  # a broken hook must never block the user's work
            sys.stderr.write("quotient: %s\n" % exc)
        return
    if args.cmd == "report":
        report()
    elif args.cmd == "export":
        export()
    elif args.cmd == "config":
        cmd_config(args)
    elif args.cmd == "rate":
        actions = {"new": rate_new, "run": rate_run, "status": rate_status, "schedule": rate_schedule,
                   "once": rate_once, "stop": rate_stop}
        if args.rate_cmd not in actions:
            rate.print_help()
            return
        actions[args.rate_cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
