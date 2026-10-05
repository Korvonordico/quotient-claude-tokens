#!/usr/bin/env python3
"""Quotient: a cost estimate before a big AI job, the real cost after it,
and a correction learned from the difference.

Part of a Claude Code plugin. Standard library only (Python 3.8+).

Commands:
  hook-session         SessionStart hook: the quote protocol, once per session
  hook-prompt          UserPromptSubmit hook (reads the hook JSON on stdin)
  hook-stop            Stop hook
  hook-pretool         PreToolUse hook, used only inside installment runs
  report               estimates, real costs, plan limits, and how the error is changing
  statusline           status line command: records and shows the plan limits
  setup-statusline     sets that status line up (--write to put it in settings.json)
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

VERSION = "0.7.0"

DEFAULTS = {
    # False until the user has set Quotient up (first-use window, /quotient:setup, or Claude Code's plugin settings).
    "configured": False,
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
    "week": {
        # Share of the weekly limit kept free for normal use; installments never plan into it.
        "reserve_percent": 20,
    },
    "rate": {
        # Put in front of every installment prompt (for example a tag your own hooks skip).
        "prompt_prefix": "",
        "permission_mode": "acceptEdits",
        "max_turns": 200,
        # Hard cap in dollars = daily cap x learned dollars per weighted token x this margin.
        "usd_cap_margin": 1.5,
        "timeout_minutes": 240,
        # After an installment, put the PC back to sleep only if nobody used it for this long.
        "idle_minutes": 10,
        # What the PC does after an installment unless a job says otherwise: nothing, sleep or hibernate.
        "after": "nothing",
        "extra_args": [],
    },
}

QUOTE_KEYS = r"(?:PREVENTIVO|ESTIMATE|QUOTE)"
CHOICE_KEYS = r"(?:SCELTA|CHOICE)"
QUOTE_RE = re.compile(r"^[\s>*_`#-]*" + QUOTE_KEYS + r"[*_`]*\s*:\s*(.+)$", re.M)
CHOICE_RE = re.compile(r"^[\s>*_`#-]*" + CHOICE_KEYS + r"[*_`]*\s*:[\s*_`]*([^\s*_`,.;:]+)", re.M)
CONTINUES_RE = re.compile(r"(?:JOB|LAVORO)[*_`]*\s*:\s*[*_`]*(?:CONTINUES|CONTINUA)", re.I)
PACE_RE = re.compile(r"^[\s>*_`#-]*(?:PACE|RITMO)[*_`]*\s*:[\s*_`]*([^\n]+)", re.M)
LIMITS_RE = re.compile(r"^[\s>*_`#-]*LIMITS[*_`]*\s*:\s*(.+)$", re.M)
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


OPTIONS = {  # plugin setting -> (config key path, type)
    "THRESHOLD": (("threshold",), int),
    "RESERVE_PERCENT": (("week", "reserve_percent"), int),
    "LANG": (("lang",), str),
    "AFTER": (("rate", "after"), str),
}


def config():
    return merge(DEFAULTS, load_json(os.path.join(home(), "config.json"), {}))


def save_settings(values):
    """Write settings (path tuple -> value) into config.json and mark Quotient as set up."""
    path = os.path.join(home(), "config.json")
    user = load_json(path, {})
    for keys, value in values.items():
        node = user
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
    user["configured"] = True
    save_json(path, user)


def sync_plugin_options():
    """Claude Code passes the plugin's settings to hooks as CLAUDE_PLUGIN_OPTION_<KEY>; scheduled runs
    do not get them, so they are copied into config.json, where every part of Quotient reads."""
    values = {}
    for key, (keys, kind) in OPTIONS.items():
        raw = os.environ.get("CLAUDE_PLUGIN_OPTION_" + key)
        if raw not in (None, ""):
            try:
                values[keys] = kind(float(raw)) if kind is int else kind(raw)
            except ValueError:
                pass
    if not values:
        return
    cfg = config()
    current = {}
    for keys in values:
        node = cfg
        for k in keys:
            node = node.get(k) if isinstance(node, dict) else None
        current[keys] = node
    if current != values or not cfg.get("configured"):
        save_settings(values)


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
        "3) Open the choice window: call the AskUserQuestion tool with two questions in the user's language. 'Livello'/'Level': the levels, each with what it includes and its corrected estimate. 'Ritmo'/'Pace': all today, plus two installment plans that fit the job. One installment = ONE DAY of work: always write a plan in days and per-day amount, e.g. '2 giorni: circa 250.000 token al giorno', '5 giorni: circa 100.000 token al giorno'; never write 'N rate'/'N installments' alone. The window always has a free field: the user can write any pace there (e.g. '50.000 al giorno'), so mention it. Say the estimates are not guaranteed and get more precise with use. If the tool is not available, ask the same in text.",
        "Numbers for the user: in words and with the unit ('1,1 milioni di token pesati', not '1.1M'). A range is the margin of the estimate: write it as 'fra 0,7 e 2 milioni' and say so; never bare numbers in parentheses.",
        "4) After the answer write `CHOICE: <level>` and one of `PACE: today`, `PACE: days=<n>`, `PACE: daily=<n>`. If today: do the work; if it will not be finished at the end of a reply, end that reply with `JOB: CONTINUES`. If the user declines: `CHOICE: none`.",
        "5) Installments: do NOT do the whole job now. Write what the whole job is to a file, then run: %s rate new <short-name> --dir <work folder> --task-file <file> --quote <raw estimate of the chosen level> plus --days <n> or --daily <n>. Then open a second window with three questions: 'Prima rata'/'First installment' (now; at a time they write; tonight at 03:00), 'Ogni giorno'/'Every day' (the daily time; free field) and 'Dopo la rata'/'After it' (put the PC back to sleep, hibernate, or leave it as it is: it sleeps only if nobody is using it). Scheduled installments wake the PC from sleep or hibernation by themselves, not from a full shutdown; run `rate check` first and, if wake timers are off, tell the user how to turn them on (you do not change system settings). Set the choice with `rate after <name> sleep|hibernate|nothing`. Then: now = run `%s rate run <name>` in the background; a time = `rate once <name> --time HH:MM` (today, or tomorrow if the time has passed); every day = `rate schedule <name> --time HH:MM` (add --force to run even after another installment the same day). The user may also start an extra installment on the same day (`rate run <name> --force`), at their own risk: it spends more of that day's limit. Let them choose freely." % (cmd, cmd),
        "LIMITS: the Quotient line at each message shows the plan limits (5-hour and weekly) when it knows them, and how many wt 1% holds when it can estimate it. Before a quote, if the limits are missing or older than 30 minutes and you have a tool that reads the plan usage (for example get_usage), call it and write the line: LIMITS: five_hour=<used %> seven_day=<used %> five_hour_resets=<ISO time> seven_day_resets=<ISO time>. Write it again right after a quoted job ends.",
        "In the window, for each level add what share of the 5-hour and weekly limits it would take and what would be left, when Quotient gives the size of 1%; if a level does not fit in what is left of the 5-hour window, say so and suggest a pace in days. At the end of a quoted job, tell the user in one line how much of each limit is used and how much is left.",
        "WEEK: before creating installments, run `%s rate week`: it adds up all open installment jobs until the weekly limit resets, against what is left minus a reserve for normal use (%d%%). If the new job would not fit with the others, say so in the window and offer: keep all, slow some down (`rate set <name> --daily <n>`), pause some (`rate pause <name>`), or pace the new one over more days." % (run_cmd(), cfg["week"]["reserve_percent"]),
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


def setup_instructions(cfg):
    return ("FIRST USE: Quotient is not set up yet. At the user's first message in this session, before anything else, "
            "open the choice window (AskUserQuestion) in the user's language with four questions, each with a free field: "
            "'Soglia'/'Threshold' (from how many weighted tokens a job gets a quote: 100.000 = often, 300.000 = the default, "
            "1.000.000 = only huge jobs); 'Riserva'/'Reserve' (share of the weekly limit kept for normal use: 10%%, 20%%, 30%%); "
            "'Lingua'/'Language' of the report (italiano, English); 'Dopo le rate'/'After installments' (put the PC to sleep, "
            "hibernate, leave it on). Current values: threshold %s, reserve %d%%, language %s, after %s. Then save them with: "
            "%s setup --threshold <n> --reserve <n> --lang it|en --after sleep|hibernate|nothing  and tell the user that "
            "/quotient:setup opens this window again whenever they want to change it.\n" % (
                fmt(cfg["threshold"]), cfg["week"]["reserve_percent"], cfg["lang"], cfg["rate"]["after"], run_cmd()))


def cmd_setup(args):
    values = {}
    if args.threshold is not None:
        values[("threshold",)] = int(args.threshold)
    if args.reserve is not None:
        values[("week", "reserve_percent")] = int(args.reserve)
    if args.lang:
        values[("lang",)] = args.lang
    if args.after:
        values[("rate", "after")] = args.after
    save_settings(values)
    cfg = config()
    out("Quotient is set up: threshold %s wt, reserve %d%% of the week, report in %s, after installments: %s.\n"
        "Change it any time with /quotient:setup.\n" % (
            fmt(cfg["threshold"]), cfg["week"]["reserve_percent"], cfg["lang"], cfg["rate"]["after"]))


def hook_session():
    """SessionStart: the full protocol, once per session instead of at every message."""
    read_stdin_json()
    if os.environ.get("QUOTIENT_JOB"):
        return
    sync_plugin_options()
    cfg = config()
    text = protocol(cfg, learning(cfg)["factor"])
    if not cfg.get("configured"):
        text += setup_instructions(cfg)
    out(text)


def hook_prompt():
    data = read_stdin_json()
    name = os.environ.get("QUOTIENT_JOB")
    if name:
        out("[Quotient %s] This is an installment run of the job '%s': follow the prompt. No quotes, no questions to the user.\n" % (VERSION, name))
        return
    sync_plugin_options()
    cfg = config()
    sid = data.get("session_id") or "unknown"
    state = load_json(session_path(sid), {})
    learned = learning(cfg)
    hints = []
    ctx = context_size(data.get("transcript_path") or "")
    if ctx:
        hints.append("The conversation is ~%s tokens: each model call re-reads it, at least ~%s wt per call." % (
            fmt(ctx), fmt(ctx * cfg["weights"]["cache_read"])))
    current = limits_line("en")
    hints.append("Plan limits: %s." % current if current else "Plan limits: not read yet (see LIMITS in the protocol).")
    sizes = []
    for window, label in (("seven_day", "the week"), ("five_hour", "the 5 hours")):
        c = capacity(window)
        if c:
            sizes.append("1%% of %s ~ %s wt, so 100%% ~ %s wt (between %s and %s; rough, from %d points)" % (
                label, fmt(c["per_point"]), fmt(c["per_point"] * 100), fmt(c["low"]), fmt(c["high"]), c["points"]))
    if sizes:
        hints.append("Estimate: " + "; ".join(sizes) + ".")
    lines = ["[Quotient %s] Threshold %s wt. %s %s Quote rules: see the Quotient protocol at the start of the session." % (
        VERSION, fmt(cfg["threshold"]), calibration(cfg, learned), " ".join(hints))]
    lines += rate_events()
    alert = week_alert(cfg)
    if alert:
        lines.append(alert)
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

    readings = parse_limits(text)
    if readings:
        record_limits(readings, "claude")
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
    cap = int(os.environ.get("QUOTIENT_CAP") or job["daily_cap"])
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


# ---------------------------------------------------------------- plan limits

WINDOWS = ("five_hour", "seven_day")


def to_epoch(value):
    """Unix seconds from a number or an ISO time (with Z or an offset)."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        pass
    try:
        text = str(value).strip().replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None


def ts_epoch(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def parse_limits(text):
    """The last machine line LIMITS: five_hour=<%> seven_day=<%> [five_hour_resets=<time>] [seven_day_resets=<time>]."""
    found = None
    for match in LIMITS_RE.finditer(text or ""):
        found = match
    if not found:
        return None
    values = dict(re.findall(r"(five_hour_resets|seven_day_resets|five_hour|seven_day)\s*=\s*([^\s,;|]+)", found.group(1)))
    snap = {}
    for window in WINDOWS:
        if window in values:
            try:
                snap[window] = float(values[window].rstrip("%").replace(",", "."))
            except ValueError:
                pass
        if values.get(window + "_resets"):
            snap[window + "_resets"] = to_epoch(values[window + "_resets"])
    return snap or None


def limits_path():
    return os.path.join(home(), "limits.jsonl")


def record_limits(snap, source):
    """Keep a reading of the plan limits; the same reading is not repeated within 5 minutes."""
    now = time.time()
    rows = read_jsonl(limits_path(), tail_bytes=4096)
    if rows:
        last = rows[-1]
        same = all(last.get(k) == snap.get(k) for k in ("five_hour", "seven_day"))
        if same and now - (last.get("epoch") or 0) < 300:
            return
    row = {"ts": now_iso(), "epoch": round(now), "source": source}
    row.update(snap)
    append_jsonl(limits_path(), row)


def latest_limits():
    """The newest reading of each window that has not reset yet."""
    now = time.time()
    latest = {}
    for row in read_jsonl(limits_path(), tail_bytes=512 * 1024):
        for window in WINDOWS:
            if row.get(window) is None:
                continue
            resets = row.get(window + "_resets")
            if resets and resets < now:
                continue
            if window not in latest or row["epoch"] >= latest[window]["epoch"]:
                latest[window] = {"used": row[window], "resets": resets, "epoch": row["epoch"]}
    return latest


def when(epoch, lang):
    if not epoch:
        return "?"
    moment = datetime.fromtimestamp(epoch)
    if moment.date() == datetime.now().date():
        return moment.strftime("%H:%M")
    days = {"it": ["lun", "mar", "mer", "gio", "ven", "sab", "dom"],
            "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}[lang if lang == "it" else "en"]
    return "%s %d %s" % (days[moment.weekday()], moment.day, moment.strftime("%H:%M"))


def limits_line(lang):
    latest = latest_limits()
    if not latest:
        return None
    names = {"it": {"five_hour": "5 ore", "seven_day": "settimana"},
             "en": {"five_hour": "5-hour", "seven_day": "week"}}["it" if lang == "it" else "en"]
    words = ("usato %s%%, resta %s%%, si azzera %s" if lang == "it" else "%s%% used, %s%% left, resets %s")
    parts = []
    for window in WINDOWS:
        if window in latest:
            w = latest[window]
            parts.append("%s: %s" % (names[window], words % (
                round(w["used"]), max(0, 100 - round(w["used"])), when(w["resets"], lang))))
    newest = max(w["epoch"] for w in latest.values())
    age = (time.time() - newest) / 60
    stale = (" (letto alle %s)" if lang == "it" else " (read at %s)") % datetime.fromtimestamp(newest).strftime("%H:%M") \
        if age > 30 else ""
    return " · ".join(parts) + stale


def capacity(window):
    """How many weighted tokens 1% of a window holds, from readings and measured turns.

    Within one window (same reset time) the rise of the percentage is set against the
    weighted tokens Quotient measured in between. Percentages are whole numbers in some
    sources, so each window carries an error of up to one point: that is the margin.
    """
    groups = {}
    for row in read_jsonl(limits_path()):
        if row.get(window) is None or not row.get(window + "_resets"):
            continue
        groups.setdefault(round(row[window + "_resets"] / 300), []).append(row)
    turns = [(ts_epoch(t.get("ts")), t["wt"]) for t in read_jsonl(os.path.join(home(), "turns.jsonl")) if t.get("wt")]
    total_wt, total_points, count = 0.0, 0.0, 0
    for rows in groups.values():
        rows.sort(key=lambda r: r["epoch"])
        first, last = rows[0], rows[-1]
        points = last[window] - first[window]
        if points <= 0:
            continue
        total_wt += sum(w for t, w in turns if first["epoch"] < t <= last["epoch"])
        total_points += points
        count += 1
    if total_points < 3 or total_wt <= 0:
        return None
    return {"per_point": total_wt / total_points, "points": total_points, "windows": count,
            "low": total_wt / (total_points + count) * 100,
            "high": total_wt / max(total_points - count, 0.5) * 100}


def weeks():
    """One row per weekly window: the highest percentage seen and the weighted tokens measured in it."""
    groups = {}
    for row in read_jsonl(limits_path()):
        if row.get("seven_day") is not None and row.get("seven_day_resets"):
            key = round(row["seven_day_resets"] / 300)
            g = groups.setdefault(key, {"resets": row["seven_day_resets"], "used": 0})
            g["used"] = max(g["used"], row["seven_day"])
    turns = [(ts_epoch(t.get("ts")), t["wt"]) for t in read_jsonl(os.path.join(home(), "turns.jsonl")) if t.get("wt")]
    rows = []
    for g in sorted(groups.values(), key=lambda g: g["resets"]):
        start = g["resets"] - 7 * 86400
        rows.append({"resets": g["resets"], "used": g["used"], "complete": g["resets"] < time.time(),
                     "wt": sum(w for t, w in turns if start < t <= g["resets"])})
    return rows


def statusline():
    """Status line command: records the plan limits Claude Code passes in, and shows them."""
    data = read_stdin_json()
    limits = data.get("rate_limits") or {}
    snap = {}
    for window in WINDOWS:
        w = limits.get(window) or {}
        if w.get("used_percentage") is not None:
            snap[window] = float(w["used_percentage"])
            snap[window + "_resets"] = to_epoch(w.get("resets_at"))
    if snap:
        record_limits(snap, "statusline")
    line = limits_line(config().get("lang"))
    out("Quotient · " + (line or ("limiti non ancora letti" if config().get("lang") == "it" else "limits not read yet")) + "\n")


def setup_statusline(args):
    """Writes a small launcher that always finds the installed version, and shows (or writes) the setting."""
    launcher = os.path.join(home(), "statusline.sh")
    with open(launcher, "w", encoding="utf-8", newline="\n") as f:
        f.write('#!/bin/sh\n# Runs the status line of the newest installed Quotient.\n'
                'dir=$(ls -d "$HOME"/.claude/plugins/cache/*/quotient/*/scripts 2>/dev/null | sort -V | tail -n 1)\n'
                '[ -n "$dir" ] || dir="%s"\nexec sh "$dir/run.sh" statusline\n' % os.path.dirname(os.path.abspath(__file__)).replace("\\", "/"))
    setting = {"type": "command", "command": 'sh "%s"' % launcher.replace("\\", "/")}
    path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    if args.write:
        settings = load_json(path, None)
        if settings is None:
            sys.exit("quotient: cannot read %s" % path)
        if settings.get("statusLine") and not args.force:
            sys.exit("quotient: a status line is already set; it was left as it is (use --force to replace it)")
        settings["statusLine"] = setting
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.write("\n")
        out("Status line set in %s. It starts with the next session.\n" % path)
    else:
        out('Add this to %s:\n"statusLine": %s\n' % (path, json.dumps(setting)))


# ---------------------------------------------------------------- the week: all installment jobs together

def open_jobs():
    base = os.path.join(home(), "rate")
    jobs = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            job = load_json(os.path.join(base, name, "job.json"), None)
            if job and job.get("status") == "open":
                job["_runs"] = read_jsonl(os.path.join(base, name, "runs.jsonl"))
                jobs.append(job)
    return jobs


def week_plan(cfg):
    """What the open installment jobs will spend before the weekly limit resets, against what is left.

    Each job runs its cap once a day (more if it is set to). The plan is in weighted tokens;
    it becomes a share of the week only when Quotient has estimated how much 1% holds.
    """
    week = latest_limits().get("seven_day")
    cap = capacity("seven_day")
    now = time.time()
    resets = (week or {}).get("resets") or now + 7 * 86400
    days_left = max(1, math.ceil((resets - now) / 86400))
    factor = learning(cfg)["factor"]
    rows = []
    for job in open_jobs():
        runs = job["_runs"]
        spent = sum(r.get("wt") or 0 for r in runs)
        left_runs = max(0, (job.get("days") or 0) - len(runs)) if job.get("days") else days_left
        per_day = job.get("per_day") or 1
        planned = min(left_runs, days_left * per_day) * job["daily_cap"]
        if job.get("quote"):
            planned = min(planned, max(0, job["quote"] * factor - spent))
        rows.append({"name": job["name"], "planned": planned, "cap": job["daily_cap"], "runs_left": left_runs})
    total = sum(r["planned"] for r in rows)
    plan = {"rows": rows, "total": total, "days_left": days_left, "reserve": cfg["week"]["reserve_percent"],
            "used": week["used"] if week else None, "resets": week["resets"] if week else None,
            "per_point": cap["per_point"] if cap else None}
    if week and cap:
        plan["left"] = max(0.0, 100 - week["used"])
        plan["for_jobs"] = max(0.0, plan["left"] - plan["reserve"])
        plan["need"] = total / cap["per_point"]
        plan["fits"] = plan["need"] <= plan["for_jobs"]
    return plan


def week_text(plan, lang):
    it = lang == "it"
    lines = []
    for r in plan["rows"]:
        share = (" (~%.0f%% %s)" % (r["planned"] / plan["per_point"], "della settimana" if it else "of the week")) if plan["per_point"] else ""
        lines.append(("%s: %s token pesati previsti fino all'azzeramento%s, %s rate rimaste" if it else
                      "%s: %s wt planned until the reset%s, %s installments left") % (
            r["name"], fmt(r["planned"]), share, r["runs_left"]))
    if not plan["rows"]:
        lines.append("Nessun lavoro a rate attivo." if it else "No open installment jobs.")
    if "need" in plan:
        lines.append(("Totale: circa %.0f%% della settimana. Resta il %.0f%%; tolta la riserva del %d%% per l'uso normale, "
                      "per le rate c'è il %.0f%%. %s" if it else
                      "Total: about %.0f%% of the week. %.0f%% is left; after the %d%% reserve for normal use, "
                      "%.0f%% is there for installments. %s") % (
            plan["need"], plan["left"], plan["reserve"], plan["for_jobs"],
            ("Ci sta." if plan["fits"] else "NON ci sta: scegli quali lavori tenere, rallentare o mettere in pausa.") if it else
            ("It fits." if plan["fits"] else "It does NOT fit: choose which jobs to keep, slow down or pause.")))
    else:
        lines.append(("Totale: %s token pesati. Quanto vale in percentuale della settimana non è ancora stimato: "
                      "servono alcuni giorni di letture dei limiti." if it else
                      "Total: %s wt. Its share of the week is not estimated yet: it needs a few days of limit readings.") % fmt(plan["total"]))
    return "\n".join(lines)


def rate_week(args):
    cfg = config()
    out(week_text(week_plan(cfg), cfg.get("lang")) + "\n")


def week_alert(cfg):
    """One line for Claude when the open jobs do not fit in the week; said once for each new situation."""
    plan = week_plan(cfg)
    if "fits" not in plan or plan["fits"]:
        return None
    key = "%s:%d:%d" % (",".join(r["name"] for r in plan["rows"]), round(plan["need"]), round(plan["for_jobs"]))
    path = os.path.join(home(), "week-told.txt")
    if load_text(path) == key:
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return ("WEEK: the open installment jobs need ~%.0f%% of the week before it resets, but only %.0f%% is there for them "
            "(%.0f%% left minus the %d%% reserve for normal use). Jobs: %s. Open the choice window: which jobs to keep, "
            "which to slow down (`rate set <name> --daily <n>`), which to pause (`rate pause <name>`); free field." % (
                plan["need"], plan["for_jobs"], plan["left"], plan["reserve"],
                ", ".join("%s ~%.0f%%" % (r["name"], r["planned"] / plan["per_point"]) for r in plan["rows"])))


def week_room(cfg, job):
    """Weighted tokens this installment may spend without eating into the reserve (None if unknown)."""
    plan = week_plan(cfg)
    if "for_jobs" not in plan:
        return None
    return plan["for_jobs"] * plan["per_point"]


def rate_pause(args):
    set_status(args.name, "paused", from_status="open")


def rate_resume(args):
    set_status(args.name, "open", from_status="paused")


def set_status(name, status, from_status):
    folder = rate_dir(name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % name)
    if job["status"] != from_status:
        sys.exit("quotient: '%s' is %s" % (name, job["status"]))
    job["status"] = status
    save_json(os.path.join(folder, "job.json"), job)
    out("Job '%s' is now %s.%s\n" % (name, status, " Its scheduled runs stay, and skip it until `rate resume`." if status == "paused" else ""))


def rate_set(args):
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    if args.daily:
        job["daily_cap"] = int(args.daily)
    if args.per_day:
        job["per_day"] = int(args.per_day)
    if args.days:
        job["days"] = int(args.days)
    save_json(os.path.join(folder, "job.json"), job)
    out("Job '%s': %s wt per installment, %s per day, %s installments in all.\n" % (
        args.name, fmt(job["daily_cap"]), job.get("per_day") or 1, job.get("days") or "?"))


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
        "limits": "Plan limits now: %s",
        "no_limits": "not read yet (they come from the status line, or from Claude in the desktop app)",
        "capacity_seven_day": "The whole week holds about %s wt (between %s and %s; rough estimate from %d percentage points). Usage outside Quotient's sessions makes it look smaller.",
        "capacity_five_hour": "The 5 hours hold about %s wt (between %s and %s; rough estimate from %d percentage points).",
        "no_capacity_seven_day": "The size of the week is not estimated yet: it needs a few percentage points measured.",
        "no_capacity_five_hour": "The size of the 5 hours is not estimated yet.",
        "weeks_head": "Week (resets)          used    measured",
        "running": "(in progress)",
        "too_early": "Too early to say whether the weeks are getting lighter: %d complete week(s), at least 4 are needed.",
        "trend_weeks": "Last 2 weeks: %.0f%% of the limit on average; the 2 before: %.0f%%.",
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
        "limits": "Limiti del piano adesso: %s",
        "no_limits": "non ancora letti (arrivano dalla riga di stato, o da Claude nell'app desktop)",
        "capacity_seven_day": "La settimana intera vale circa %s token pesati (fra %s e %s: stima grezza da %d punti percentuali). L'uso fuori dalle sessioni di Quotient la fa sembrare più piccola.",
        "capacity_five_hour": "Le 5 ore valgono circa %s token pesati (fra %s e %s: stima grezza da %d punti percentuali).",
        "no_capacity_seven_day": "Quanto vale la settimana non è ancora stimato: servono alcuni punti percentuali misurati.",
        "no_capacity_five_hour": "Quanto valgono le 5 ore non è ancora stimato.",
        "weeks_head": "Settimana (si azzera)   usato   misurato",
        "running": "(in corso)",
        "too_early": "Troppo presto per dire se le settimane si alleggeriscono: %d settimane complete, ne servono almeno 4.",
        "trend_weeks": "Ultime 2 settimane: in media %.0f%% del limite; le 2 prima: %.0f%%.",
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
    lang = cfg.get("lang")
    current = limits_line(lang)
    lines += ["", t["limits"] % (current or t["no_limits"])]
    for window in ("seven_day", "five_hour"):
        c = capacity(window)
        lines.append(t["capacity_" + window] % (fmt(c["per_point"] * 100), fmt(c["low"]), fmt(c["high"]), c["points"])
                     if c else t["no_capacity_" + window])
    rows = weeks()
    if rows:
        lines += ["", t["weeks_head"]]
        for r in rows[-8:]:
            lines.append("%-22s %5s%%   %s" % (when(r["resets"], lang), round(r["used"]), fmt(r["wt"])) + ("" if r["complete"] else "   " + t["running"]))
        done = [r for r in rows if r["complete"]]
        if len(done) < 4:
            lines.append(t["too_early"] % len(done))
        else:
            recent, before = [r["used"] for r in done[-2:]], [r["used"] for r in done[-4:-2]]
            lines.append(t["trend_weeks"] % (sum(recent) / 2, sum(before) / 2))
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
    # The Claude desktop app keeps its own copy of Claude Code. Installed from the Microsoft
    # Store, the app's AppData is private: outside the app (a scheduled task) it lives under
    # Packages\Claude_*\LocalCache, so both places are searched.
    patterns = [
        os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "*", "*", "claude.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_*", "LocalCache", "Roaming",
                     "Claude", "claude-code", "*", "*", "claude.exe"),
    ]

    def version(path):
        parts = os.path.basename(os.path.dirname(os.path.dirname(path))).split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts)

    candidates = sorted((c for pattern in patterns for c in glob.glob(pattern)), key=version)
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
        "after": args.after or config()["rate"]["after"],
    }
    save_json(os.path.join(folder, "job.json"), job)
    out("Job '%s' ready: %s wt per installment%s, working in %s\nJob files: %s\n"
        "Run one installment now: %s rate run %s\nOnce today at a time: %s rate once %s --time HH:MM\n"
        "Every day: %s rate schedule %s --time HH:MM\n" % (
            args.name, fmt(daily), ", about %d installment(s)" % days if days else "", job["dir"], folder,
            run_cmd(), args.name, run_cmd(), args.name, run_cmd(), args.name))


def rate_run(args):
    """One installment, kept awake while it works; afterwards the PC sleeps if the job says so."""
    folder = rate_dir(args.name)
    lock = os.path.join(folder, "run.lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < config()["rate"]["timeout_minutes"] * 60:
        out("An installment of '%s' is already running.\n" % args.name)
        return
    os.makedirs(folder, exist_ok=True)
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    keep_awake(True)
    try:
        run_installment(args)
    finally:
        keep_awake(False)
        try:
            os.remove(lock)
        except OSError:
            pass
    job = load_json(os.path.join(folder, "job.json"), {}) or {}
    after = job.get("after") or "nothing"
    if after != "nothing":
        idle = idle_seconds()
        if idle is not None and idle >= config()["rate"]["idle_minutes"] * 60:
            out("Nobody is using the PC: %s.\n" % after)
            go_to_sleep(after)
        else:
            out("The PC is in use: it stays on.\n")


def run_installment(args):
    cfg = config()
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    if job["status"] in ("done", "stopped", "paused"):
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
    # The week comes first: an installment never plans into the reserve for normal use.
    cap = job["daily_cap"]
    room = week_room(cfg, job)
    if room is not None and room < cap:
        if room < cap * 0.1:
            job["last_skip"] = {"at": now_iso(), "why": "week", "room": round(room)}
            save_json(os.path.join(folder, "job.json"), job)
            out("Installment of '%s' skipped: the week has only %s wt left before the reserve.\n" % (args.name, fmt(room)))
            return
        cap = int(room)
        out("Installment of '%s' shortened to %s wt to stay out of the reserve.\n" % (args.name, fmt(cap)))
    prompt = (rc["prompt_prefix"] + " " if rc["prompt_prefix"] else "") + RATE_PROMPT.format(
        task=os.path.join(folder, "TASK.md"), handoff=os.path.join(folder, "HANDOFF.md"),
        cap=fmt(cap), number=len(runs) + 1, days=job.get("days") or "?")
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
        cmd += ["--max-budget-usd", "%.2f" % (cap * job["usd_per_wt"] * rc["usd_cap_margin"])]
    cmd += list(rc["extra_args"])
    env = dict(os.environ, QUOTIENT_JOB=args.name, QUOTIENT_CAP=str(cap))
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
    error = None
    if result.get("is_error") or not result:
        said = str(result.get("result") or "") + stderr
        error = ("Claude Code is not logged in for runs outside the app: run `claude auth login` once in a terminal"
                 if "logged in" in said.lower() or "/login" in said else (said.strip()[-300:] or "error"))
    run = {"started": started, "finished": now_iso(), "session": sid, "wt": wt, "calls": calls,
           "usd": usd, "error": error, "done": done}
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


def launcher():
    """A small script outside the plugin folder that runs the newest installed Quotient.

    Scheduled tasks call it, so they keep working after the plugin updates and old
    version folders are removed.
    """
    path = os.path.join(home(), "launcher.py")
    fallback = os.path.abspath(__file__)
    code = (
        "# Runs the newest installed Quotient (written by Quotient; scheduled tasks call it).\n"
        "import glob, os, re, runpy, sys\n"
        "def version(p):\n"
        "    v = os.path.basename(os.path.dirname(os.path.dirname(p)))\n"
        "    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r'[.-]', v))\n"
        "found = sorted(glob.glob(os.path.join(os.path.expanduser('~'), '.claude', 'plugins', 'cache', '*', 'quotient', '*', 'scripts', 'quotient.py')), key=version)\n"
        "script = found[-1] if found else %r\n"
        "sys.argv = [script] + sys.argv[1:]\n"
        "runpy.run_path(script, run_name='__main__')\n" % fallback)
    if load_text(path) != code:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
    return path


def load_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def next_time(at):
    """Today at HH:MM, or tomorrow if that time has already passed."""
    hh, mm = (int(x) for x in check_time(at).split(":"))
    moment = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if moment <= datetime.now():
        moment = moment.fromtimestamp(moment.timestamp() + 86400)
    return moment


def task_xml(name, start, once, arguments, wake=True):
    """A Task Scheduler task that wakes the PC from sleep or hibernation, and runs late if it missed its time."""
    def esc(text):
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    trigger = ("<TimeTrigger><StartBoundary>%s</StartBoundary><Enabled>true</Enabled></TimeTrigger>" if once else
               "<CalendarTrigger><StartBoundary>%s</StartBoundary><Enabled>true</Enabled>"
               "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>") % start.strftime("%Y-%m-%dT%H:%M:%S")
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Quotient: installment of %s</Description></RegistrationInfo>
  <Triggers>%s</Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>%s</WakeToRun>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author"><Exec><Command>%s</Command><Arguments>%s</Arguments><WorkingDirectory>%s</WorkingDirectory></Exec></Actions>
</Task>
""" % (esc(name), trigger, "true" if wake else "false", esc(sys.executable), esc(arguments), esc(home()))


def schedule(name, at, once, force=False, wake=True):
    start = next_time(at)
    arguments = '"%s" rate run %s%s' % (launcher(), name, " --force" if once or force else "")
    if os.name == "nt":
        xml = os.path.join(rate_dir(name), "task-once.xml" if once else "task-daily.xml")
        os.makedirs(os.path.dirname(xml), exist_ok=True)
        with open(xml, "w", encoding="utf-16") as f:
            f.write(task_xml(name, start, once, arguments, wake))
        proc = subprocess.run(["schtasks", "/Create", "/F", "/TN", task_name(name, once), "/XML", xml], capture_output=True)
        if proc.returncode != 0:
            sys.exit("quotient: the task was not created: %s" % (proc.stderr or proc.stdout).decode("utf-8", "replace").strip())
        out("%s '%s' at %s%s. It runs even if the PC is asleep or hibernated%s. Remove it with: rate stop %s\n" % (
            "Scheduled once" if once else "Scheduled every day from", name, start.strftime("%d/%m %H:%M"),
            " (with --force: also after another installment the same day)" if force and not once else "",
            "" if wake else " (no: --no-wake)", name))
    else:
        run = '"%s" %s' % (sys.executable, arguments)
        hh, mm = start.strftime("%H"), start.strftime("%M")
        if once:
            out("Run this once (needs `at`):\necho '%s' | at %s\n" % (run, start.strftime("%H:%M")))
        else:
            out("Add this line with `crontab -e`:\n%d %d * * * %s\n" % (int(mm), int(hh), run))
        out("To wake the computer first: macOS `sudo pmset repeat wake MTWRFSU %s:00`; Linux `sudo rtcwake -m no -t <time>`.\n" % start.strftime("%H:%M"))


def unschedule(name):
    if os.name == "nt":
        for once in (False, True):
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", task_name(name, once)], capture_output=True)


# ---------------------------------------------------------------- the PC: awake, idle, asleep

def keep_awake(on):
    """While an installment works, Windows must not put the PC back to sleep."""
    if os.name != "nt":
        return
    try:
        import ctypes
        flags = 0x80000000 | (0x00000001 if on else 0)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def idle_seconds():
    """Seconds since the last keyboard or mouse input, or None where it cannot be read."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LastInput()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


def go_to_sleep(how):
    """Sleep or hibernate; never shut down, because a timer cannot wake a PC that is off."""
    state = "Hibernate" if how == "hibernate" else "Suspend"
    if os.name == "nt":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "[System.Windows.Forms.Application]::SetSuspendState('%s', $false, $false)" % state])
    elif sys.platform == "darwin":
        subprocess.run(["pmset", "sleepnow"])
    else:
        subprocess.run(["systemctl", "hibernate" if how == "hibernate" else "suspend"])


def rate_check(args):
    """Read-only: can a scheduled installment wake this PC?"""
    if os.name != "nt":
        out("On macOS use `pmset -g sched`, on Linux `rtcwake`: waking by timer needs administrator rights there.\n")
        return
    proc = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE"], capture_output=True)
    text = proc.stdout.decode("utf-8", "replace") + proc.stdout.decode("cp850", "replace")
    values = re.findall(r":\s*0x0*([0-9a-fA-F]+)\s*$", proc.stdout.decode("cp850", "replace"), re.M)
    names = {"0": "disabled", "1": "enabled", "2": "important timers only"}
    if len(values) >= 2:
        ac, dc = values[-2], values[-1]
        out("Wake timers: on mains %s, on battery %s.\n" % (names.get(ac, ac), names.get(dc, dc)))
        if ac != "1":
            out("To let Quotient wake the PC: Control Panel > Power Options > Change plan settings > "
                "Change advanced power settings > Sleep > Allow wake timers > Enable.\n")
    else:
        out("Could not read the wake-timer setting.\n")
    out("Waking works from sleep and from hibernation, not from a full shutdown.\n")
    claude = find_claude(config())
    if not claude:
        out("Claude Code not found: set it with `config claude_path <path to claude.exe>`.\n")
        return
    out("Claude Code: %s\n" % claude)
    proc = subprocess.run([claude, "auth", "status"], capture_output=True)
    try:
        logged = json.loads(proc.stdout.decode("utf-8", "replace")).get("loggedIn")
    except ValueError:
        logged = None
    out("Logged in for runs outside the app: %s\n" % {True: "yes", False: "NO", None: "unknown"}[logged])
    if logged is False:
        out('Log in once, in a terminal (it opens the browser; paste the code it gives you):\n"%s" auth login\n' % claude)


def rate_schedule(args):
    schedule(args.name, args.time, once=False, force=args.force, wake=not args.no_wake)


def rate_once(args):
    schedule(args.name, args.time, once=True, wake=not args.no_wake)


def rate_after(args):
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    job["after"] = args.what
    save_json(os.path.join(folder, "job.json"), job)
    out("After each installment of '%s': %s%s.\n" % (args.name, args.what,
        " (only if nobody used the PC in the last %d minutes)" % config()["rate"]["idle_minutes"] if args.what != "nothing" else ""))


def rate_stop(args):
    folder = rate_dir(args.name)
    job = load_json(os.path.join(folder, "job.json"), None)
    unschedule(args.name)
    if not job:
        sys.exit("quotient: no job named '%s' (its scheduled tasks, if any, are removed)" % args.name)
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
    for name in ("hook-session", "hook-prompt", "hook-stop", "hook-pretool", "report", "export", "statusline"):
        sub.add_parser(name)
    p = sub.add_parser("setup", help="set Quotient up: threshold, weekly reserve, language, what the PC does after installments")
    p.add_argument("--threshold", type=int)
    p.add_argument("--reserve", type=int)
    p.add_argument("--lang", choices=("it", "en"))
    p.add_argument("--after", choices=("nothing", "sleep", "hibernate"))
    p = sub.add_parser("setup-statusline", help="show the plan limits in the status line and record them")
    p.add_argument("--write", action="store_true", help="write the setting in ~/.claude/settings.json")
    p.add_argument("--force", action="store_true", help="replace a status line that is already set")
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
    p.add_argument("--after", choices=("nothing", "sleep", "hibernate"),
                   help="what the PC does after each installment, if nobody is using it (default: the setting)")
    p = rsub.add_parser("run", help="run one installment now")
    p.add_argument("name")
    p.add_argument("--force", action="store_true", help="run even if one already ran today")
    p = rsub.add_parser("status")
    p.add_argument("name", nargs="?")
    p = rsub.add_parser("schedule", help="run an installment every day at a time (wakes the PC)")
    p.add_argument("name")
    p.add_argument("--time", default="03:00")
    p.add_argument("--force", action="store_true", help="run even if another installment ran the same day")
    p.add_argument("--no-wake", action="store_true", help="do not wake the PC")
    p = rsub.add_parser("once", help="run one installment at a time (today, or tomorrow if past)")
    p.add_argument("name")
    p.add_argument("--time", required=True)
    p.add_argument("--no-wake", action="store_true", help="do not wake the PC")
    p = rsub.add_parser("after", help="what the PC does after each installment")
    p.add_argument("name")
    p.add_argument("what", choices=("nothing", "sleep", "hibernate"))
    rsub.add_parser("check", help="can a scheduled installment wake this PC?")
    rsub.add_parser("week", help="all open installment jobs against what is left of the week")
    p = rsub.add_parser("pause", help="pause a job: its scheduled runs skip it")
    p.add_argument("name")
    p = rsub.add_parser("resume", help="resume a paused job")
    p.add_argument("name")
    p = rsub.add_parser("set", help="change a job: cap per installment, installments per day, how many in all")
    p.add_argument("name")
    p.add_argument("--daily", type=int)
    p.add_argument("--per-day", type=int)
    p.add_argument("--days", type=int)
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
    if args.cmd == "statusline":
        try:
            statusline()
        except Exception as exc:  # the status line must never break
            out("Quotient\n")
            sys.stderr.write("quotient: %s\n" % exc)
    elif args.cmd == "setup-statusline":
        setup_statusline(args)
    elif args.cmd == "setup":
        cmd_setup(args)
    elif args.cmd == "report":
        report()
    elif args.cmd == "export":
        export()
    elif args.cmd == "config":
        cmd_config(args)
    elif args.cmd == "rate":
        actions = {"new": rate_new, "run": rate_run, "status": rate_status, "schedule": rate_schedule,
                   "once": rate_once, "stop": rate_stop, "after": rate_after, "check": rate_check,
                   "week": rate_week, "pause": rate_pause, "resume": rate_resume, "set": rate_set}
        if args.rate_cmd not in actions:
            rate.print_help()
            return
        actions[args.rate_cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
