"""The measures set against the limits, the guided repair (fix), and the status line."""

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone

from quotient_lib import q_costs, q_learning, q_limits, q_quotes, q_rates, q_reports, q_schedules, q_settings, q_timing

# ---------------------------------------------------------------- the measures set against the week (1.1.1)
# An outside opinion (15/10/2026): "if the measures are wrong, the correction learns the wrong thing". Quotient already
# reads the weekly percentage and estimates how many wt 1% holds: each finished job is set against how much the week
# rose in the same time. A big miss is told, never acted on: the use of other chats, and of what Quotient cannot see
# (claude.ai, the phone), moves the week too.

def checks_path():
    return os.path.join(q_settings.home(), "checks.jsonl")


def week_used():
    """The weekly limit used now, as last read (percent), or None."""
    week = q_limits.latest_limits().get("seven_day")
    return week["used"] if week else None


def check_spans():
    """Every measured job and installment: (key, label, begin, end, wt, to check)."""
    spans = []
    for j in q_settings.read_jsonl(os.path.join(q_settings.home(), "jobs.jsonl")):
        end = q_limits.ts_epoch(j.get("finished"))
        if end and j.get("actual") and not str(j.get("session") or "").startswith("rate:"):
            spans.append((check_key(j), "'%s'" % j.get("choice"),
                          float(j.get("begin") or q_limits.ts_epoch(j.get("started")) or end), end, j["actual"], bool(j.get("check"))))
    base = os.path.join(q_settings.home(), "rate")
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        for i, r in enumerate(q_settings.read_jsonl(os.path.join(base, name, "runs.jsonl")), start=1):
            begin, end = q_limits.ts_epoch(r.get("started")), q_limits.ts_epoch(r.get("finished"))
            if begin and end:
                spans.append(("run:%s:%s" % (name, r.get("started")), "'%s' installment %d" % (name, i), begin, end,
                              r.get("wt") or 0, bool(r.get("check")) and bool(r.get("wt"))))
    return spans


def measure_checks(cfg, now=None):
    """Set the jobs and installments closed since 1.1.1 against the week, once each, when a reading of the week is there
    from before their start and after their end (within check.hours). The result goes to checks.jsonl: agrees, warn (a
    miss beyond x check.factor, nothing else running), overlap (the same miss, but another job or installment ran
    meanwhile), small, or no reading. Returns the new rows."""
    now = now or time.time()
    c = q_settings.merge(q_settings.DEFAULTS["check"], cfg.get("check") or {})
    hours = float(c["hours"]) * 3600
    seen = {r.get("key") for r in q_settings.read_jsonl(checks_path())}
    spans = check_spans()
    todo = [s for s in spans if s[5] and s[0] not in seen]
    if not todo:
        return []
    readings = sorted((r for r in q_settings.read_jsonl(q_limits.limits_path()) if r.get("seven_day") is not None
                       and r.get("seven_day_resets") and r.get("epoch")), key=lambda r: r["epoch"])
    cap, turns, new = None, None, []
    for key, label, begin, end, wt, _ in todo:
        row = {"key": key, "label": label, "begin": round(begin), "end": round(end), "wt": wt, "ts": q_settings.now_iso()}
        after = [r for r in readings if end <= r["epoch"] <= end + hours]
        before = [r for r in readings if begin - hours <= r["epoch"] <= begin + 1
                  and after and abs(r["seven_day_resets"] - after[0]["seven_day_resets"]) < 600]
        if not after or not before:
            if now - end > hours:
                new.append(dict(row, result="no reading"))
            continue
        cap = cap or q_limits.week_capacity(cfg)
        if not cap or cap.get("source") == "plan":
            continue  # how much 1% holds is not known yet here (the plan's shared average judges no measure): wait
        r0, r1 = before[-1], after[0]
        per, points = cap["per_point"], r1["seven_day"] - r0["seven_day"]
        row.update({"from": r0["epoch"], "to": r1["epoch"], "points": points, "per_point": round(per),
                    "expected_points": round(wt / per, 1)})
        if points < 0:
            row["result"] = "no reading"
        elif max(wt / per, points) < float(c["min_points"]):
            row["result"] = "small"
        else:
            # the percentages are whole numbers: each reading can be a point off
            low, high = wt / ((points + 1) * per), wt / (max(points - 1, 0.5) * per)
            row["ratio"] = round(wt / (max(points, 0.5) * per), 2)
            if turns is None:
                turns = q_limits.measured_turns(cfg)
            row["others"] = round(max(0, sum(w for t, w in turns if r0["epoch"] < (t or 0) <= r1["epoch"]) - wt))
            factor = float(c["factor"])
            if low <= factor and high >= 1 / factor:
                row["result"] = "agrees"
            else:
                busy = any(k != key and b < r1["epoch"] and e > r0["epoch"] for k, _, b, e, _, _ in spans)
                row["result"] = "overlap" if busy else "warn"
        new.append(row)
    for row in new:
        q_settings.append_jsonl(checks_path(), row)
    return new


def check_line(row):
    """One line for the agent about a measure that does not match the week."""
    more = row["ratio"] >= 1
    job = next((j for j in q_settings.read_jsonl(jobs_path()) if check_key(j) == row.get("key")), None)
    repair = (" If the user knows the measure is wrong (for example a piece of the job counted apart), propose `%s fix "
              "exclude %s`: it takes the job out of the factor (a copy first; `fix undo` takes it back). Run it only after "
              "they say yes." % (q_quotes.run_cmd(), job_key(job))) if job else ""
    if not more and q_reports.hermes_busy(row.get("begin"), row.get("end")):
        # 1.1.6 (7b): a possible part of the explanation, never a change of the weights
        repair = (" Hermes was in use meanwhile: the calls it makes outside a turn (command approvals, compressions, "
                  "titles, images; about %g%% of its use on the author's data) are not counted." % q_reports.HERMES_UNSEEN) + repair
    return ("MEASURE CHECK: the job %s (finished %s) was measured at %s wt, but in the same time the weekly limit rose %s "
            "point(s), about %s wt at the current estimate of 1%% (%s wt): the measure is x%.1f %s than the week shows. "
            "%sUse that Quotient cannot see (claude.ai, the phone, another PC) moves the week too, so this is a hint to "
            "check, not a proof; Quotient changes nothing by itself. Tell the user in ONE line, in their language: the "
            "measure of this job does not match the week, check it (the report shows it)." % (
                row["label"], q_limits.when(row["end"], "en"), q_quotes.fmt(row["wt"]), "%g" % row["points"],
                q_quotes.fmt(row["points"] * row["per_point"]), q_quotes.fmt(row["per_point"]),
                row["ratio"] if more else 1 / max(row["ratio"], 0.01), "higher" if more else "lower",
                "Quotient measured another %s wt in other chats meanwhile. " % q_quotes.fmt(row["others"]) if row.get("others") else "")
            ) + repair


def check_alert(cfg):
    """The measures that do not match the week, told once each, at the user's next message."""
    path = os.path.join(q_settings.home(), "checks-told.json")
    told = q_settings.load_json(path, [])
    told = told if isinstance(told, list) else []
    seen = {r.get("key") for r in q_settings.read_jsonl(checks_path())}
    if any(s[5] and s[0] not in seen for s in check_spans()) and not any(
            (r.get("epoch") or 0) > time.time() - 600 for r in q_settings.read_jsonl(q_limits.limits_path(), tail_bytes=4096)):
        # a job waits for a reading after its end (at most every limits.every seconds); 1.1.7: in the background, so
        # the message does not wait for it: the check is made at a later message
        q_limits.limits_soon(cfg, q_limits.limits_every(cfg))
    measure_checks(cfg)
    lines = [check_line(r) for r in q_settings.read_jsonl(checks_path()) if r.get("result") == "warn" and r.get("key") not in told]
    if lines:
        q_settings.save_json(path, told + [r.get("key") for r in q_settings.read_jsonl(checks_path()) if r.get("result") == "warn"])
    return lines


def checks_summary():
    rows = q_settings.read_jsonl(checks_path())
    judged = [r for r in rows if r.get("result") in ("agrees", "warn", "overlap")]
    return {"judged": len(judged), "agrees": sum(1 for r in judged if r["result"] == "agrees"),
            "warn": [r for r in judged if r["result"] == "warn"],
            "overlap": sum(1 for r in judged if r["result"] == "overlap"),
            "skipped": len(rows) - len(judged)}


# ---------------------------------------------------------------- the guided repair (1.1.4)
# 15/10/2026: a piece of a job had been counted apart, and jobs.jsonl was put right by hand (a copy first). Now Quotient
# finds such cases itself (a measure that does not match the week; a small job right before another of the same chat),
# proposes the command, and the agent runs it only with the user's yes. Nothing is ever deleted: a copy of jobs.jsonl
# comes first, the jobs taken out go to jobs-excluded.jsonl, and `fix undo` puts the last change back.

def job_key(job):
    """A short id of a measured job that does not change: from its chat and its start."""
    import hashlib
    return hashlib.sha1(("%s|%s" % (job.get("session"), job.get("started"))).encode("utf-8")).hexdigest()[:8]


def check_key(job):
    """The key of a job in checks.jsonl (see check_spans); a job joined by `fix merge` is checked again."""
    return "job:%s:%s%s" % (job.get("session"), job.get("started"), ":merged" if job.get("merged_from") else "")


def jobs_path():
    return os.path.join(q_settings.home(), "jobs.jsonl")


def excluded_path():
    return os.path.join(q_settings.home(), "jobs-excluded.jsonl")


def write_rows(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def split_jobs(cfg, jobs=None):
    """Pairs of measured jobs that look like one job cut in two: the same chat, the first ends at most fix.gap_minutes
    before the second starts, and its work is under fix.small_share of the second's. [(first, second, gap seconds)]"""
    c = q_settings.merge(q_settings.DEFAULTS["fix"], cfg.get("fix") or {})
    jobs = [j for j in (q_settings.read_jsonl(jobs_path()) if jobs is None else jobs)
            if j.get("raw_estimate") and j.get("actual") and q_learning.kind_of(j) == "chat"]
    chats = {}
    for j in jobs:
        chats.setdefault(str(j.get("session")), []).append(j)
    pairs = []
    for rows in chats.values():
        rows.sort(key=lambda j: q_limits.ts_epoch(j.get("started")))
        for a, b in zip(rows, rows[1:]):
            gap = float(b.get("begin") or q_limits.ts_epoch(b.get("started"))) - q_limits.ts_epoch(a.get("finished"))
            if -60 <= gap <= float(c["gap_minutes"]) * 60 and q_costs.work_of(a) < float(c["small_share"]) * max(q_costs.work_of(b), 1):
                pairs.append((a, b, max(0.0, gap)))
    return pairs


def fix_problems(cfg):
    """What `fix` proposes: jobs that look split (join them) and measures that do not match the week (take the job out
    of the factor, if the user knows the measure is wrong). Only jobs still in jobs.jsonl."""
    jobs = q_settings.read_jsonl(jobs_path())
    found = []
    for a, b, gap in split_jobs(cfg, jobs):
        found.append({"what": "split", "id": "split:%s>%s" % (job_key(a), job_key(b)), "jobs": [a, b], "gap": gap,
                      "command": "fix merge %s %s" % (job_key(a), job_key(b))})
    by_check = {check_key(j): j for j in jobs}
    rates = {str(j.get("session"))[5:]: j for j in jobs if q_learning.kind_of(j) == "rate"}
    for r in q_settings.read_jsonl(checks_path()):
        if r.get("result") != "warn":
            continue
        key = str(r.get("key") or "")
        job = by_check.get(key) or (rates.get(key.split(":")[1]) if key.startswith("run:") and key.count(":") >= 2 else None)
        if job:
            found.append({"what": "check", "id": "check:%s" % key, "jobs": [job], "row": r,
                          "command": "fix exclude %s" % job_key(job)})
    return found


def fix_alert():
    """A job that looks split, told once: the agent proposes `fix merge` and runs it only with the user's yes. (A measure
    that does not match the week is told by check_alert, with its `fix exclude`.)"""
    cfg = q_settings.config()
    path = os.path.join(q_settings.home(), "fix-told.json")
    told = q_settings.load_json(path, [])
    told = told if isinstance(told, list) else []
    new = [p for p in fix_problems(cfg) if p["what"] == "split" and p["id"] not in told]
    if not new:
        return None
    q_settings.save_json(path, told + [p["id"] for p in new])
    p = new[-1]
    a, b = p["jobs"]
    return ("A JOB LOOKS SPLIT: the job '%s' (work %s wt) ended %s before the job '%s' of the same chat started (work %s "
            "wt): probably one job counted in two pieces, which teaches the factor the wrong thing. Propose to the user, "
            "in ONE line in their language, to join them with `%s %s` (Quotient copies jobs.jsonl first, and `fix undo` "
            "takes it back); run it only after they say yes.%s" % (
                a.get("choice"), q_quotes.fmt(q_costs.work_of(a)), q_timing.fmt_duration(p["gap"]), b.get("choice"), q_quotes.fmt(q_costs.work_of(b)), q_quotes.run_cmd(),
                p["command"], " (%d more: `fix list`.)" % (len(new) - 1) if len(new) > 1 else ""))


def fix_backup():
    """Copies of jobs.jsonl and jobs-excluded.jsonl before a change, in ~/.quotient/fix/."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder = os.path.join(q_settings.home(), "fix")
    os.makedirs(folder, exist_ok=True)
    copies = {}
    for name, path in (("jobs", jobs_path()), ("excluded", excluded_path())):
        copy = os.path.join(folder, "%s-%s.jsonl" % (name, stamp))
        if os.path.exists(path):
            shutil.copyfile(path, copy)
            copies[name] = copy
        else:
            copies[name] = None
    return copies


def factors_now(cfg):
    return {"chat": round(q_learning.learning(cfg)["factor"], 4), "rate": round(q_learning.learning(cfg, "rate")["factor"], 4)}


def fix_find(ref, jobs):
    """The index in jobs.jsonl of a job given by its number in the report (1, 2, ...) or by its key (a prefix is
    enough when it is unique), or None."""
    ref = str(ref or "").strip().lower()
    if ref.isdigit():
        measured = [i for i, j in enumerate(jobs) if j.get("raw_estimate") and j.get("actual")]
        n = int(ref)
        return measured[n - 1] if 1 <= n <= len(measured) else None
    found = [i for i, j in enumerate(jobs) if ref and job_key(j).startswith(ref)]
    return found[0] if len(found) == 1 else None


def joined(a, b):
    """Two pieces of one job made one: the costs, steps and times added; the estimate and the start of the first, the
    end of the second."""
    job = dict(a)
    for k in ("actual", "chat", "older", "aside", "calls", "turns", "seconds", "quote_cost", "aside_turns",
              "aside_calls", "elsewhere"):
        if a.get(k) is not None or b.get(k) is not None:
            job[k] = (a.get(k) or 0) + (b.get(k) or 0)
    job["work"] = q_costs.work_of(a) + q_costs.work_of(b)
    families = dict(a.get("families") or {})
    for k, v in (b.get("families") or {}).items():
        families[k] = families.get(k, 0) + v
    job.update(families=families, finished=b.get("finished"), week_end=b.get("week_end"),
               merged_from=[job_key(a), job_key(b)], fixed=q_settings.now_iso())
    if b.get("env"):
        job["env"] = b["env"]
    job["ratio"] = round(q_costs.work_of(job) / job["raw_estimate"], 4) if job.get("raw_estimate") else None
    if job.get("family") or families:
        job["family"] = q_costs.main_family(families)
    return job


def fix_log(row):
    q_settings.append_jsonl(os.path.join(q_settings.home(), "fix.jsonl"), dict(row, ts=q_settings.now_iso()))


# 16/10/2026: a job's chat part is what re-reading, at each step, what the chat held when the job started cost. When
# the chat is compressed (Hermes) or compacted (Claude Code) while the job runs, a step re-reads less from then on; the
# jobs measured before that was counted (see _chat_part in hermes_hooks and chat_part) are found by `fix list` and
# worked out again by `fix chat <job>`.

def compressions_in(job):
    """When the chat of a job was compressed or compacted while it ran: [(its time, the first answer after it)] in
    epoch seconds, [] when nothing says so or the data are gone. Installments are left out."""
    begin = float(job.get("begin") or 0) or q_limits.ts_epoch(job.get("started"))
    end = q_limits.ts_epoch(job.get("finished"))
    sid = str(job.get("session") or "")
    if not begin or not end or end <= begin or sid.startswith("rate:"):
        return []
    if sid.startswith("hermes:"):
        try:
            import hermes_source as hs
            return hs.compressions(sid[7:], begin, end)
        except Exception:
            return []
    path = q_rates.find_transcript(sid) if sid else None
    if not path:
        return []
    return [(q_limits.ts_epoch(e.get("timestamp")),) * 2 for e in q_settings.read_jsonl(path)
            if (e.get("subtype") == "compact_boundary" or e.get("isCompactSummary"))
            and begin < q_limits.ts_epoch(e.get("timestamp")) <= end]


def chat_again(cfg, job, when):
    """The chat part of a job whose chat was compressed (`when`: from compressions_in), worked out again: (chat part,
    'transcript' or 'hermes-log'), or None without data. Claude Code: call by call from the transcript (chat_part).
    Hermes keeps no numbers call by call: from Quotient's log of its counters, the steps before the compression count
    the size the job started with (`ctx`, their number from what they read) and the steps after count what they sent on
    average, if less; an estimate."""
    sid, w = str(job.get("session") or ""), cfg["weights"]
    if sid.startswith("hermes:"):
        import hermes_source as hs
        begin = float(job.get("begin") or 0) or q_limits.ts_epoch(job.get("started"))
        end = q_limits.ts_epoch(job.get("finished"))
        ctx, calls = float(job.get("ctx") or 0), int(job.get("calls") or 0)
        # each row of the log is what the counters grew since the row before: the part inside the job, by its time
        log = sorted((r for r in hs.read_log(q_settings.home()) if r.get("session") == sid[7:]), key=lambda r: r.get("epoch") or 0)
        rows, prev = [], None
        for r in log:
            at = r.get("epoch") or 0
            start, prev = (prev if prev is not None else at - 1), at
            inside = max(0.0, min(at, end) - max(start, begin))
            if inside > 0 and at > start:
                rows.append((at, inside / (at - start), r))
        if not ctx or not calls or not rows:
            return None

        def total(part, keys):
            return sum(f * sum(r.get(k) or 0 for k in keys) for _, f, r in part)
        pre = [x for x in rows if x[0] <= when[1]]
        post = [x for x in rows if x[0] > when[1]]
        pre_calls = min(calls, int(round(total(pre, ("cache_read_tokens",)) / ctx)))
        post_calls = calls - pre_calls
        sent = total(post, ("cache_read_tokens", "cache_write_tokens", "input_tokens"))
        size = min(ctx, sent / post_calls) if post_calls and sent else ctx
        return min((pre_calls * ctx + post_calls * size) * w["cache_read"], job.get("actual") or 0), "hermes-log"
    path = q_rates.find_transcript(sid) if sid else None
    if not path:
        return None
    begin, end = q_limits.ts_epoch(job.get("started")), q_limits.ts_epoch(job.get("finished"))
    entries = [e for e in q_settings.read_jsonl(path) if not e.get("isSidechain")]
    starts = [q_limits.ts_epoch(e.get("timestamp")) for e in entries if q_costs.is_turn_start(e)]
    first = max([s for s in starts if s <= begin + 5] or [0])
    calls = q_costs.ordered_calls([e for e in entries if first <= q_limits.ts_epoch(e.get("timestamp")) <= end + 5])
    if not first or not calls:
        return None
    return min(q_costs.chat_part(calls, 0, q_costs.prompt_tokens(calls[0]["usage"]), w), job.get("actual") or 0), "transcript"


def rechat(job, chat, how):
    """A job with its chat part worked out again (the old values kept under `chat_fixed`)."""
    new = dict(job, chat=round(chat), chat_fixed={"at": q_settings.now_iso(), "how": how, "chat": job.get("chat"),
                                                   "work": job.get("work")})
    new["work"] = max(0, round((job.get("actual") or 0) - chat - (job.get("aside") or 0)))
    if new.get("raw_estimate"):
        new["ratio"] = round(q_costs.work_of(new) / new["raw_estimate"], 4)
    return new


def compression_problems(cfg):
    """The jobs whose chat was compressed while they ran and whose chat part comes out different worked out again
    (not the ones measured after the fix, nor the ones already worked out). Only for `fix list`: it reads transcripts."""
    found = []
    for job in q_settings.read_jsonl(jobs_path()):
        if not (job.get("raw_estimate") and job.get("actual")) or job.get("chat_fixed") or job.get("ctx_floor"):
            continue
        when = compressions_in(job)
        again = chat_again(cfg, job, when[0]) if when else None
        if again and abs(again[0] - (job.get("chat") or 0)) >= 1000:
            found.append({"what": "chat", "id": "chat:%s" % job_key(job), "jobs": [job], "chat": again[0],
                          "how": again[1], "command": "fix chat %s" % job_key(job)})
    return found


def how_text(how):
    return "from its transcript" if how == "transcript" else "an estimate from Quotient's log of Hermes"


def cmd_fix(args):
    cfg = q_settings.config()
    what = args.what or "list"
    jobs = q_settings.read_jsonl(jobs_path())
    cmd = q_quotes.run_cmd()
    if what == "list":
        problems = fix_problems(cfg) + compression_problems(cfg)
        if not problems:
            q_settings.out("Nothing to repair: no job looks split, no measure is far from the week, and no chat part needs "
                "working out again after a compression.\n")
            return
        lines = ["What Quotient proposes to repair (nothing changes without the command; each makes a copy first, and "
                 "`fix undo` takes the last one back):"]
        for p in problems:
            if p["what"] == "split":
                a, b = p["jobs"]
                lines.append("- split: '%s' %s (work %s) ended %s before '%s' %s (work %s) of the same chat. Join them: "
                             "%s %s" % (a.get("choice"), job_key(a), q_quotes.fmt(q_costs.work_of(a)), q_timing.fmt_duration(p["gap"]),
                                        b.get("choice"), job_key(b), q_quotes.fmt(q_costs.work_of(b)), cmd, p["command"]))
            elif p["what"] == "chat":
                j = p["jobs"][0]
                new = rechat(j, p["chat"], p["how"])
                lines.append("- compressed: '%s' %s: its chat was compressed while it ran; chat part %s -> %s wt, work %s -> "
                             "%s, ratio x%.2f -> x%.2f (%s). Work it out again: %s %s" % (
                                 j.get("choice"), job_key(j), q_quotes.fmt(j.get("chat") or 0), q_quotes.fmt(p["chat"]), q_quotes.fmt(q_costs.work_of(j)),
                                 q_quotes.fmt(q_costs.work_of(new)), q_costs.work_of(j) / j["raw_estimate"], q_costs.work_of(new) / j["raw_estimate"],
                                 how_text(p["how"]), cmd, p["command"]))
            else:
                r, j = p["row"], p["jobs"][0]
                lines.append("- measure: '%s' %s was measured at %s wt, the week rose %s point(s) (~%s wt), x%.2f. If you "
                             "know this measure is wrong, take it out of the factor: %s %s" % (
                                 j.get("choice"), job_key(j), q_quotes.fmt(r.get("wt")), "%g" % (r.get("points") or 0),
                                 q_quotes.fmt((r.get("points") or 0) * (r.get("per_point") or 0)), r.get("ratio") or 0, cmd,
                                 p["command"]))
        q_settings.out("\n".join(lines) + "\n")
        return
    if what == "undo":
        log = q_settings.read_jsonl(os.path.join(q_settings.home(), "fix.jsonl"))
        undone = {r.get("undid") for r in log if r.get("action") == "undo"}
        last = next((r for r in reversed(log) if r.get("action") in ("merge", "exclude", "chat") and r.get("ts") not in undone), None)
        if not last:
            q_settings.out("Nothing to undo.\n")
            return
        before = factors_now(cfg)
        copies = fix_backup()           # the state now is kept too
        for name, path in (("jobs", jobs_path()), ("excluded", excluded_path())):
            source = (last.get("backup") or {}).get(name)
            if source and os.path.exists(source):
                shutil.copyfile(source, path)
            elif name == "excluded" and os.path.exists(path):
                write_rows(path, [])    # there was none before: its rows are back in jobs.jsonl (and in the copy)
        after = factors_now(cfg)
        fix_log({"action": "undo", "undid": last["ts"], "backup": copies, "factor_before": before, "factor_after": after})
        q_settings.out("Undone: the %s of %s (from %s). Factor now x%.2f (installments x%.2f), before the undo x%.2f (x%.2f). "
            "Copy of the state before the undo: %s\n" % (last["action"], ", ".join(last.get("keys") or []), last["ts"],
                                                         after["chat"], after["rate"], before["chat"], before["rate"],
                                                         copies["jobs"]))
        return
    refs = args.jobs or []
    if what == "merge":
        if len(refs) != 2:
            sys.exit("quotient: fix merge <job> <job> (their number in the report or their key, see fix list)")
        i, k = fix_find(refs[0], jobs), fix_find(refs[1], jobs)
        if i is None or k is None or i == k:
            sys.exit("quotient: no such pair of jobs (see fix list)")
        if q_limits.ts_epoch(jobs[k].get("started")) < q_limits.ts_epoch(jobs[i].get("started")):
            i, k = k, i                 # the earlier one first
        a, b = jobs[i], jobs[k]
        before = factors_now(cfg)
        copies = fix_backup()
        merged = joined(a, b)
        rows = [merged if n == i else j for n, j in enumerate(jobs) if n != k]
        for j in (a, b):
            q_settings.append_jsonl(excluded_path(), dict(j, fix={"action": "merge", "at": q_settings.now_iso(), "into": job_key(merged)}))
        write_rows(jobs_path(), rows)
        after = factors_now(cfg)
        fix_log({"action": "merge", "keys": [job_key(a), job_key(b)], "backup": copies, "factor_before": before,
                 "factor_after": after})
        q_settings.out("Joined '%s' %s (work %s) and '%s' %s (work %s) into one job: work %s wt against the raw estimate %s of the "
            "first, ratio x%.2f. Factor x%.2f -> x%.2f (installments x%.2f -> x%.2f). The two pieces are kept in %s; "
            "copy of jobs.jsonl before: %s. To take it back: %s fix undo\n" % (
                a.get("choice"), job_key(a), q_quotes.fmt(q_costs.work_of(a)), b.get("choice"), job_key(b), q_quotes.fmt(q_costs.work_of(b)),
                q_quotes.fmt(q_costs.work_of(merged)), q_quotes.fmt(merged.get("raw_estimate")), merged.get("ratio") or 0, before["chat"],
                after["chat"], before["rate"], after["rate"], excluded_path(), copies["jobs"], cmd))
        return
    if what == "chat":
        if len(refs) != 1:
            sys.exit("quotient: fix chat <job> (its number in the report or its key, see fix list)")
        i = fix_find(refs[0], jobs)
        if i is None:
            sys.exit("quotient: no such job (see fix list)")
        job = jobs[i]
        when = compressions_in(job)
        again = chat_again(cfg, job, when[0]) if when else None
        if not again:
            sys.exit("quotient: no compression found while this job ran, or its data are gone")
        before = factors_now(cfg)
        copies = fix_backup()
        new = rechat(job, again[0], again[1])
        write_rows(jobs_path(), [new if n == i else j for n, j in enumerate(jobs)])
        after = factors_now(cfg)
        fix_log({"action": "chat", "keys": [job_key(job)], "backup": copies, "factor_before": before,
                 "factor_after": after})
        q_settings.out("Chat part of '%s' %s worked out again (%s): %s -> %s wt; work %s -> %s, ratio x%.2f -> x%.2f. Factor x%.2f "
            "-> x%.2f (installments x%.2f -> x%.2f). Copy of jobs.jsonl before: %s. To take it back: %s fix undo\n" % (
                job.get("choice"), job_key(job), how_text(again[1]), q_quotes.fmt(job.get("chat") or 0), q_quotes.fmt(again[0]),
                q_quotes.fmt(q_costs.work_of(job)), q_quotes.fmt(q_costs.work_of(new)), q_costs.work_of(job) / job["raw_estimate"],
                q_costs.work_of(new) / job["raw_estimate"], before["chat"], after["chat"], before["rate"], after["rate"],
                copies["jobs"], cmd))
        return
    if what == "exclude":
        if len(refs) != 1:
            sys.exit("quotient: fix exclude <job> (its number in the report or its key, see fix list)")
        i = fix_find(refs[0], jobs)
        if i is None:
            sys.exit("quotient: no such job (see fix list)")
        job = jobs[i]
        before = factors_now(cfg)
        copies = fix_backup()
        q_settings.append_jsonl(excluded_path(), dict(job, fix={"action": "exclude", "at": q_settings.now_iso(), "why": args.why or ""}))
        write_rows(jobs_path(), [j for n, j in enumerate(jobs) if n != i])
        after = factors_now(cfg)
        fix_log({"action": "exclude", "keys": [job_key(job)], "why": args.why or "", "backup": copies,
                 "factor_before": before, "factor_after": after})
        q_settings.out("Took '%s' %s (work %s wt, raw estimate %s) out of the factor: it is kept in %s. Factor x%.2f -> x%.2f "
            "(installments x%.2f -> x%.2f). Copy of jobs.jsonl before: %s. To take it back: %s fix undo\n" % (
                job.get("choice"), job_key(job), q_quotes.fmt(q_costs.work_of(job)), q_quotes.fmt(job.get("raw_estimate")), excluded_path(),
                before["chat"], after["chat"], before["rate"], after["rate"], copies["jobs"], cmd))
        return
    sys.exit("quotient: fix list | merge <a> <b> | exclude <job> | undo")


def statusline():
    """Status line command: records the plan limits Claude Code passes in, and shows them."""
    data = q_settings.read_stdin_json()
    limits = data.get("rate_limits") or {}
    snap = {}
    for window in q_limits.WINDOWS:
        w = limits.get(window) or {}
        if w.get("used_percentage") is not None:
            snap[window] = float(w["used_percentage"])
            snap[window + "_resets"] = q_limits.to_epoch(w.get("resets_at"))
    if snap:
        q_limits.record_limits(snap, "statusline")
    usd = (data.get("cost") or {}).get("total_cost_usd")
    if data.get("session_id") and isinstance(usd, (int, float)) and not isinstance(usd, bool) and usd >= 0:
        q_reports.record_statusline_cost(str(data["session_id"])[:64], round(float(usd), 6))   # 1.1.6: the third measure
    line = q_limits.limits_line(q_settings.config().get("lang"))
    text = "Quotient · " + (line or ("limiti non ancora letti" if q_settings.config().get("lang") == "it" else "limits not read yet"))
    st = q_timing.timer_state()
    if st.get("state") in ("run", "pause") and time.time() - float(st.get("ts") or 0) < 12 * 3600:
        # the stopwatch of the open job (1.1.0)
        text += " · ⏱ %s%s" % (q_timing.fmt_duration(q_timing.timer_seconds(st)), " / ~%s" % q_timing.fmt_duration(st["predicted"])
                               if st.get("predicted") else "")
    q_settings.out(text + "\n")


def setup_statusline(args):
    """Writes a small launcher that runs this installed version (session starts keep it current), and shows
    (or writes) the setting."""
    launcher = q_schedules.statusline_launcher()
    setting = {"type": "command", "command": 'sh "%s"' % launcher.replace("\\", "/")}
    path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    if args.write:
        settings = q_settings.load_json(path, None)
        if settings is None:
            sys.exit("quotient: cannot read %s" % path)
        if settings.get("statusLine") and not args.force:
            sys.exit("quotient: a status line is already set; it was left as it is (use --force to replace it)")
        settings["statusLine"] = setting
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.write("\n")
        q_settings.out("Status line set in %s. It starts with the next session.\n" % path)
    else:
        q_settings.out('Add this to %s:\n"statusLine": %s\n' % (path, json.dumps(setting)))
