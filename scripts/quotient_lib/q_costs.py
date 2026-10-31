"""What a chat cost: weighted tokens from Claude Code's transcripts, the Claude Code runs a Hermes chat starts, and the machine lines read from a reply."""

import glob
import json
import os
import re

from quotient_lib import q_limits, q_rates, q_settings

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
    """A user entry that is not a tool result starts a new turn. Claude Code's own notices about background
    tasks (<task-notification>) arrive as user entries but are not something the user wrote: not a turn."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return not content.lstrip().startswith("<task-notification>")
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        if kinds == {"text"} and all(str(b.get("text") or "").lstrip().startswith("<task-notification>")
                                     for b in content if isinstance(b, dict)):
            return False
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
        for e in q_settings.read_jsonl(path):
            if since_ts is None or (e.get("timestamp") or "") >= since_ts:
                rows.append(e)
    return rows


def turn_of(transcript_path):
    """Entries of the last turn, its start time, and the text Claude wrote in it."""
    entries = q_settings.read_jsonl(transcript_path, tail_bytes=8 * 1024 * 1024)
    if not any(is_turn_start(e) for e in entries):
        entries = q_settings.read_jsonl(transcript_path)
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


FAMILY_NAMES = ("opus", "sonnet", "haiku", "fable")


def family_of(model):
    """opus, sonnet, haiku, fable or other, from a model id such as claude-opus-5-5."""
    model = (model or "").lower()
    for name in FAMILY_NAMES:
        if name in model:
            return name
    return "other"


def families_of(entries, weights):
    """Weighted tokens per model family, each API call counted once."""
    calls = {}
    for e in entries:
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        key = e.get("requestId") or msg.get("id") or e.get("uuid")
        usage = msg.get("usage") or {}
        old = calls.get(key)
        if old is None or (usage.get("output_tokens") or 0) > (old[1].get("output_tokens") or 0):
            calls[key] = (msg.get("model"), usage)
    totals = {}
    for model, usage in calls.values():
        family = family_of(model)
        totals[family] = round(totals.get(family, 0) + weigh(usage, weights))
    return {k: v for k, v in totals.items() if v}


def add_families(job, families):
    totals = job.setdefault("families", {})
    for k, v in families.items():
        totals[k] = totals.get(k, 0) + v


def main_family(families):
    """The family that did most of the work."""
    return max(families, key=families.get) if families else "other"


def prompt_tokens(usage):
    """How long one call's prompt was: everything the model read for it."""
    usage = usage or {}
    return ((usage.get("input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0))


def context_size(transcript_path):
    """Tokens the model re-reads at each call: the size of the last call's prompt."""
    size = 0
    for e in q_settings.read_jsonl(transcript_path, tail_bytes=2 * 1024 * 1024):
        if e.get("type") == "assistant" and not e.get("isSidechain"):
            size = prompt_tokens((e.get("message") or {}).get("usage"))
    return size


def first_context(transcript_path):
    """The prompt of a chat's first call: what any new chat costs to read (system, tools, rules, first
    message). Above it, a long chat carries its older conversation."""
    try:
        with open(transcript_path, "rb") as f:
            for n, line in enumerate(f):
                if n > 20000:
                    break
                try:
                    e = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if isinstance(e, dict) and e.get("type") == "assistant" and not e.get("isSidechain"):
                    size = prompt_tokens((e.get("message") or {}).get("usage"))
                    if size:
                        return size
    except OSError:
        pass
    return 0


def ordered_calls(entries):
    """The calls of the main chat (subagents apart), in order, each once: its usage and its tool calls."""
    calls, order = {}, []
    for e in entries:
        if e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        key = e.get("requestId") or msg.get("id") or e.get("uuid")
        usage = msg.get("usage") or {}
        if key not in calls:
            calls[key] = {"usage": usage, "tools": []}
            order.append(key)
        elif (usage.get("output_tokens") or 0) > (calls[key]["usage"].get("output_tokens") or 0):
            calls[key]["usage"] = usage
        for block in msg.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls[key]["tools"].append(block)
    return [calls[k] for k in order]


def write_weight(usage, weights):
    """The weight of one call's cache writes: 2 for the one-hour cache, 1.25 for the five-minute one."""
    total = usage.get("cache_creation_input_tokens") or 0
    split = usage.get("cache_creation") or {}
    w1h = split.get("ephemeral_1h_input_tokens") or 0
    w5m = split.get("ephemeral_5m_input_tokens") or 0
    w5m += max(0, total - w1h - w5m)
    if w1h + w5m <= 0:
        return weights["cache_write_5m"]
    return (w1h * weights["cache_write_1h"] + w5m * weights["cache_write_5m"]) / (w1h + w5m)


def span_cost(usage, lo, hi, weights):
    """Weighted cost of the prompt tokens from position lo to hi of one call. A prompt is read from the
    cache first, then written to it, then sent as plain input: an older part of the chat is mostly read
    from the cache (0.1), unless the cache had expired (then it is written again, 1.25 or 2)."""
    read = usage.get("cache_read_input_tokens") or 0
    write = usage.get("cache_creation_input_tokens") or 0
    size = prompt_tokens(usage)
    hi = min(hi, size)
    if hi <= lo:
        return 0.0

    def overlap(a, b):
        return max(0, min(b, hi) - max(a, lo))
    return (overlap(0, read) * weights["cache_read"] + overlap(read, read + write) * write_weight(usage, weights)
            + overlap(read + write, size) * weights["input"])


def chat_part(calls, lo, hi, weights):
    """What re-reading the older chat (prompt positions lo..hi) cost in these calls. After a compaction a prompt is
    shorter than hi: the older chat is then what the compacted prompt holds, so from that call on each call counts up
    to the shortest prompt so far (16/10/2026: before, the calls after a compaction counted nothing, and all of hi
    again once the chat had grown back past it)."""
    if hi <= lo:
        return 0
    total, top = 0.0, hi
    for c in calls:
        top = min(top, prompt_tokens(c["usage"]))
        total += span_cost(c["usage"], lo, top, weights)
    return round(total)


def work_of(job):
    """The cost comparable with the estimate: the work, without re-reading at each call what the chat held
    before the job started (before 0.9.5, when that is not known, the whole cost)."""
    if job.get("work") is not None:
        return job["work"]
    return max(0, (job.get("actual") or 0) - (job.get("chat") or 0))


# ---------------------------------------------------------------- Claude Code runs a Hermes chat starts (hermes branch)

RATE_SIGN = "You are doing ONE installment of a bigger job"   # the first words of RATE_PROMPT


def claude_links_path():
    return os.path.join(q_settings.home(), "claude-links.jsonl")


def record_claude_link(data, cfg=None):
    """At the start of any Claude Code session: which Hermes chat started it, if any. Hermes passes
    HERMES_SESSION_ID to everything it starts (scripts, `claude -p`); an installment has QUOTIENT_JOB. Sessions with
    neither get a line too: a session seen here and not started by Hermes (a scheduled task, the user's own chat) is
    then never counted, not even by the marker."""
    cfg = cfg or q_settings.config()
    sid = (data or {}).get("session_id")
    if not cfg.get("claude_runs") or not sid:
        return
    q_settings.append_jsonl(claude_links_path(), {
        "ts": q_settings.now_iso(), "session": sid, "transcript": data.get("transcript_path"), "source": data.get("source"),
        "hermes": os.environ.get("HERMES_SESSION_ID") or None, "rate": os.environ.get("QUOTIENT_JOB") or None})


def claude_links():
    """Claude Code session -> what its start records say (a field once set stays: a later resume does not erase it)."""
    links = {}
    for r in q_settings.read_jsonl(claude_links_path()):
        sid = r.get("session")
        if not sid:
            continue
        link = links.setdefault(sid, {"session": sid})
        for key in ("hermes", "rate", "transcript"):
            if r.get(key) and not link.get(key):
                link[key] = r[key]
    return links


def first_prompt(path):
    """The first prompt of a `claude -p` session (its entries say entrypoint sdk-cli), or None for any other."""
    try:
        with open(path, "rb") as f:
            for n, line in enumerate(f):
                if n > 200:
                    break
                try:
                    e = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(e, dict) or e.get("type") != "user" or e.get("isSidechain"):
                    continue
                if e.get("entrypoint") != "sdk-cli":
                    return None
                content = (e.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
                return str(content or "")
    except OSError:
        pass
    return None


def first_time(path):
    """When a transcript starts (epoch seconds), or 0."""
    try:
        with open(path, "rb") as f:
            for n, line in enumerate(f):
                if n > 50:
                    break
                try:
                    e = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                when = q_limits.ts_epoch(e.get("timestamp")) if isinstance(e, dict) else 0
                if when:
                    return when
    except OSError:
        pass
    return 0


def find_run_transcript(folder, started, finished, known=(), root=None):
    """The transcript of an installment that left no session id (31/10/2026: sor-tappa4, stopped by the timeout after 4
    hours, recorded 0 wt: only the answer printed at the end of a run gives the id, and a stopped run prints nothing).
    It is the `claude -p` session whose first prompt names this job's TASK.md and that started during the run. `known`:
    sessions already given to other runs of the job. None when nothing matches."""
    lo, hi = q_limits.ts_epoch(started), q_limits.ts_epoch(finished)
    if not lo or not hi:
        return None
    task = os.path.join(folder, "TASK.md")
    root = root or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    found = []
    for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
        try:
            if os.path.getmtime(path) < lo - 60:
                continue
        except OSError:
            continue
        if os.path.basename(path)[:-6] in known or task not in (first_prompt(path) or ""):
            continue
        begin = first_time(path)
        if lo - 60 <= begin <= hi + 60:
            found.append((begin, path))
    return min(found)[1] if found else None


def tokens_of(entries):
    """Tokens by type over the calls of a transcript, for a run Claude Code's own answer does not cover."""
    totals = {}
    for usage in calls_of(entries).values():
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            if isinstance(usage.get(k), (int, float)):
                totals[k] = totals.get(k, 0) + int(usage[k])
    return totals


def claude_run_cost(path, lo, hi, weights):
    """What one Claude Code session spent from lo to hi (epoch seconds), its helpers (subagents) included."""
    entries = [e for e in q_settings.read_jsonl(path) + subagent_entries(path, None)
               if e.get("type") == "assistant" and lo <= q_limits.ts_epoch(e.get("timestamp")) <= hi]
    return cost_of(entries, weights)[0], families_of(entries, weights)


def claude_runs_of(hermes_sid, lo, hi, cfg, root=None):
    """The Claude Code sessions a Hermes chat started and what they spent from lo to hi (epoch seconds): the ones
    linked at their start to this chat, installments left out (they measure themselves); with claude_runs_marker,
    also the `claude -p` sessions never seen at their start whose first prompt begins with it."""
    root = root or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    links = claude_links()
    found = {}
    for sid, link in links.items():
        if link.get("hermes") == hermes_sid and not link.get("rate"):
            path = link.get("transcript")
            path = path if path and os.path.exists(path) else q_rates.find_transcript(sid)
            if path:
                found[path] = "link"
    marker = cfg.get("claude_runs_marker") or ""
    if marker:
        for path in glob.glob(os.path.join(root, "*", "*.jsonl")):
            if path in found or os.path.basename(path)[:-6] in links:
                continue
            try:
                if os.path.getmtime(path) < lo:
                    continue
            except OSError:
                continue
            prompt = first_prompt(path)
            if prompt is not None and prompt.lstrip().startswith(marker) and RATE_SIGN not in prompt:
                found[path] = "marker"
    total, families, runs = 0, {}, []
    for path, how in sorted(found.items()):
        wt, fam = claude_run_cost(path, lo, hi, cfg["weights"])
        if wt:
            total += wt
            for k, v in fam.items():
                families[k] = families.get(k, 0) + v
            runs.append({"session": os.path.basename(path)[:-6], "wt": wt, "by": how})
    return {"wt": total, "families": families, "runs": runs}


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
    for match in q_settings.QUOTE_RE.finditer(text or ""):
        options = {}
        for name, number, suffix in q_settings.OPTION_RE.findall(match.group(1)):
            try:
                options[name.lower()] = parse_amount(number, suffix)
            except ValueError:
                pass
        if options:
            found = options
    return found


def work_type(word):
    """A type of work from a word of the agent or the user ('code', 'ricerca', 'libro'): one of WORK_TYPES, else
    'other'; None for no word."""
    if not word:
        return None
    return q_settings.TYPE_WORDS.get(str(word).strip().lower(), "other")


def parse_type(text):
    """The type of work of the last QUOTE line (the one parse_quote reads): `QUOTE: good=200k max=400k kind=code` ->
    'code'; None when the line gives none."""
    found = None
    for match in q_settings.QUOTE_RE.finditer(text or ""):
        if q_settings.OPTION_RE.search(match.group(1)):
            m = q_settings.TYPE_RE.search(match.group(1))
            found = work_type(m.group(1)) if m else None
    return found


def parse_pace(text):
    """'today', 'new-chat' (the job is done in a new chat), 'apart' (done apart, now), the installment plan as written,
    or None."""
    match = q_settings.PACE_RE.search(text or "")
    if not match:
        return None
    value = match.group(1).strip()
    if q_settings.NEW_CHAT_RE.search(value):
        return "new-chat"
    if q_settings.APART_RE.search(value):
        return "apart"
    plan = parse_plan(value)
    if plan.get("days") or plan.get("daily"):
        return value                  # an installment plan, also with 'all' or 'today' in its words
    return "today" if q_settings.TODAY_RE.search(value) else value


def plan_amount(number, word):
    """An amount of a plan: '250.000', '250k', '1,5 milioni', '50 mila'."""
    word = (word or "").lower()
    suffix = "k" if word in ("k", "mila") else "m" if word and word[0] == "m" else None
    return parse_amount(number, suffix)


def parse_plan(text):
    """An installment plan in the user's words or in a PACE line (1.1.3): {'days': n, 'daily': wt, 'at': 'HH:MM'},
    with only what the text says. '5 giorni alle 2:00' -> {'days': 5, 'at': '02:00'}."""
    text = text or ""
    plan = {}
    m = q_settings.PLAN_DAYS_RE.search(text)
    if m:
        days = int(m.group(1) or m.group(2))
        if 1 <= days <= 365:
            plan["days"] = days
    m = q_settings.PLAN_DAILY_RE.search(text)
    if m:
        try:
            daily = parse_amount(m.group(1), m.group(2)) if m.group(1) else plan_amount(m.group(3), m.group(4))
        except ValueError:
            daily = 0
        if daily >= 1000:            # '2 a day' is not an amount of tokens
            plan["daily"] = daily
    for m in q_settings.PLAN_AT_RE.finditer(text):
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
        half = (m.group(3) or "").lower()
        if half == "pm" and hh < 12:
            hh += 12
        elif half == "am" and hh == 12:
            hh = 0
        if hh <= 23 and mm <= 59:
            plan["at"] = "%02d:%02d" % (hh, mm)
            break
    if "at" not in plan and q_settings.MIDNIGHT_RE.search(text):
        plan["at"] = "00:00"
    return plan


def parse_move(text):
    """The last `JOB: RESUME|CLOSE|DROP <id>` line: (what, id) or None."""
    found = None
    for match in q_settings.MOVE_RE.finditer(text or ""):
        found = (q_settings.MOVES[match.group(1).lower()], match.group(2).lower())
    return found


def parse_progress(text):
    """The installment's PROGRESS line: how much of the whole job is done, 0-100, or None."""
    found = None
    for match in q_settings.PROGRESS_RE.finditer(text or ""):
        found = match
    if not found:
        return None
    value = float(found.group(1).replace(",", "."))
    return value if 0 <= value <= 100 else None


def parse_choice(text):
    match = q_settings.CHOICE_RE.search(text or "")
    return match.group(1).lower() if match else None


def parse_custom(text):
    """A choice with its own estimate (1.1.3: the user wrote their own in the window's free field, the agent estimated
    it): `CHOICE: custom=700k` -> ('custom', 700000), or None. Only the CHOICE line parse_choice reads."""
    first = q_settings.CHOICE_RE.search(text or "")
    match = q_settings.CHOICE_AMOUNT_RE.match(text, first.start()) if first else None
    if not match:
        return None
    try:
        value = parse_amount(match.group(2), match.group(3))
    except ValueError:
        return None
    return (match.group(1).lower(), value) if value > 0 else None


def same_quote(quote, choice, job):
    """True when a QUOTE line is the open (or just closed) job's quote written again: same numbers, and the same
    level if a CHOICE comes with it. Then it is the same job, not a new one. 14/10/2026: an agent that wrote its
    QUOTE and CHOICE lines again at every message cut 4 jobs into 57 pieces, each with the whole estimate and a
    sliver of the work, and the correction factor fell to x0.14."""
    return bool(quote) and bool(job) and quote == job.get("options") and (not choice or choice == job.get("choice"))
