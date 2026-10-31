"""Running installments: new job, apart, one run with its cap, and its status."""

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

from quotient_lib import q_costs, q_hooks, q_learning, q_limits, q_notices, q_quotes, q_rates, q_repairs, q_schedules, q_settings, q_sharing, q_tasks, q_timing, q_weeks

def rate_new(args):
    folder = q_rates.rate_dir(args.name)
    if os.path.exists(os.path.join(folder, "job.json")):
        sys.exit("quotient: a job named '%s' already exists" % args.name)
    if args.task_file:
        with open(args.task_file, encoding="utf-8") as f:
            task = f.read()
    elif args.task:
        task = args.task
    else:
        sys.exit("quotient: give the job with --task or --task-file")
    template = getattr(args, "template", None)
    template = template if isinstance(template, str) and template else None
    if template:
        text = q_schedules.load_text(os.path.join(q_rates.templates_dir(), re.sub(r"[^\w-]", "", template) + ".md"))
        if text is None:
            sys.exit("quotient: no template named '%s' (there are: %s)" % (template, ", ".join(q_rates.templates())))
        task = text.strip() + "\n\n# The job\n\n" + task.strip()
    cfg = q_settings.config()
    wtype = q_costs.work_type(getattr(args, "type", None) if isinstance(getattr(args, "type", None), str) else None)
    factor = q_learning.learning(cfg, "rate", wtype)["factor"]   # 1.1.4: the factor of its type of work, once it has its jobs
    # 1.1.3: a pace in the user's own words ('5 giorni alle 2:00'): the days, the amount a day and the time are read
    # from it; what is given apart (--days, --daily, --at) counts first
    pace = getattr(args, "pace", None)
    plan = q_costs.parse_plan(pace) if isinstance(pace, str) else {}
    want_days = args.days or plan.get("days")
    want_daily = args.daily or plan.get("daily")
    at = getattr(args, "at", None)
    at = q_schedules.check_time(at) if isinstance(at, str) and at else plan.get("at")
    # The daily cap is real spending: the corrected work plus re-reading each installment's start, and (1.2.2) the
    # start itself once per installment.
    reread = q_rates.installment_overhead(cfg)
    start = q_rates.installment_start_cost(cfg)
    total = args.quote * factor * (1 + reread) if args.quote else None
    if want_daily:
        daily = want_daily
    elif total and want_days:
        daily = math.ceil(total / want_days + start)
    else:
        sys.exit("quotient: give --daily (weighted tokens per installment), or --quote with --days (or --pace with "
                 "the user's words, e.g. --pace \"5 giorni alle 2:00\")")
    floor = q_rates.cap_floor(cfg)
    if floor and daily < floor:
        q_settings.out("Cap raised from %s to %s wt: each installment is a new Claude Code session that spends up to about %s wt "
            "just to start (rules and tools), so a smaller cap could end before any work.\n" % (
                q_quotes.fmt(daily), q_quotes.fmt(math.ceil(floor)), q_quotes.fmt(q_rates.installment_start_cost(cfg, highest=True))))
        daily = math.ceil(floor)
    days = want_days or (max(1, math.ceil(total / max(1.0, daily - start))) if total else None)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "TASK.md"), "w", encoding="utf-8") as f:
        f.write(task.strip() + "\n")
    with open(os.path.join(folder, "HANDOFF.md"), "w", encoding="utf-8") as f:
        f.write("Nothing done yet.\n")
    job = {
        "name": args.name, "dir": os.path.abspath(args.dir), "daily_cap": int(daily),
        "days": days, "quote": args.quote, "factor_at_quote": round(factor, 4), "overhead_at_quote": round(reread, 3),
        "start_at_quote": round(start),
        "created": q_settings.now_iso(),
        "status": "open", "model": args.model, "usd_per_wt": None,
        "after": args.after or cfg["rate"]["after"], "template": template,
        # the chat that created the job: each installment's report comes back to it
        "session": (getattr(args, "session", None) if isinstance(getattr(args, "session", None), str) else None) or q_rates.chat_id(),
    }
    apart = getattr(args, "apart", False) is True
    if apart:
        job["apart"] = True      # 1.1.1: done apart, now (rate apart)
    if at:
        job["at"] = at           # 1.1.3: the time the user chose; `rate schedule` and `rate once` use it
    if wtype:
        job["type"] = wtype      # 1.1.4
    whole = q_timing.expected_seconds(cfg, args.quote, "rate", factor) if args.quote else None
    job["predicted_seconds"] = round(whole) if whole else None
    each = q_notices.installment_seconds(cfg, job)
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    notes = q_tasks.task_check(task, job["dir"], cfg)
    if notes:
        q_settings.out("Task check (rate.task_check; simple word checks, they may be wrong):\n" +
            "".join("- %s.\n" % n for n in notes) +
            ("The job starts anyway: these points are for the next task.\n" if apart else
             "The job is created anyway: to improve the task before it runs, edit %s (the job's own copy).\n"
             % os.path.join(folder, "TASK.md")) +
            "Tell the user these points in a line or two.\n")
    if apart:
        return job
    timing = ("Expected time: about %s per installment%s (from the installments timed so far).\n" % (
        q_timing.fmt_duration(each), ", about %s in all" % q_timing.fmt_duration(whole) if whole else "") if each else "")
    when_text = (("Once at %s (today, or tomorrow if past): %s rate once %s\nEvery day at %s: %s rate schedule %s\n" % (
        at, q_quotes.run_cmd(), args.name, at, q_quotes.run_cmd(), args.name)) if at else
        ("Once today at a time: %s rate once %s --time HH:MM\nEvery day: %s rate schedule %s --time HH:MM\n" % (
            q_quotes.run_cmd(), args.name, q_quotes.run_cmd(), args.name)))
    q_settings.out("Job '%s' ready: %s wt per installment%s, working in %s\nJob files: %s\n%s"
        "Run one installment now: %s rate run %s\n%s%s" % (
            args.name, q_quotes.fmt(daily), ", about %d installment(s)" % days if days else "", job["dir"], folder, timing,
            q_quotes.run_cmd(), args.name, when_text,
            "Each installment's report will come back to this chat.\n" if job["session"] else ""))


def start_detached(argv, log):
    """Start this script with argv in the background, apart from the chat (it goes on when the reply ends), writing
    to log. True if it started."""
    exe, kw = sys.executable, {}
    if os.name == "nt":
        quiet = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = quiet if os.path.isfile(quiet) else exe
        flags = [0x00000008 | 0x00000200 | 0x01000000, 0x00000008 | 0x00000200]  # detached, own group, out of the job
    else:
        flags, kw["start_new_session"] = [0], True
    with open(log, "ab") as f:
        for flag in flags:
            try:
                subprocess.Popen([exe, q_settings.ENTRY_FILE] + list(argv), stdin=subprocess.DEVNULL, stdout=f,
                                 stderr=f, close_fds=True, cwd=q_settings.home(), **(dict(kw, creationflags=flag) if flag else kw))
                return True
            except OSError:  # breaking away from the chat's job object may not be allowed: try without
                continue
    return False


def rate_apart(args):
    """'Apart, now' (1.1.1, the user's idea): the job starts at once as ONE installment in a separate session (claude -p)
    whose cap is the whole corrected quote, so its measure is clean and the chat does not re-read it. No waking and no
    sleep afterwards. Its report comes back to the chat that started it."""
    args.apart, args.days, args.daily, args.after = True, 1, None, "nothing"
    job = rate_new(args)
    folder = q_rates.rate_dir(args.name)
    log = os.path.join(folder, "apart.log")
    started = start_detached(["rate", "run", args.name], log)
    each = q_notices.installment_seconds(q_settings.config(), job)
    if not started:
        q_settings.out("Job '%s' is ready, but it could not be started in the background: run `%s rate run %s` in the background.\n"
            % (args.name, q_quotes.run_cmd(), args.name))
        return
    q_settings.out("Job '%s' started apart, now: one installment of up to %s wt (the whole corrected quote) in a separate Claude "
        "Code session (claude -p), working in %s.%s It cannot be talked to while it works and asks no questions; a "
        "command that needs a permission may stop it. Its report comes back to %s when it ends, and a notification "
        "shows it. Log: %s\n" % (
            args.name, q_quotes.fmt(job["daily_cap"]), job["dir"],
            " Expected time: about %s." % q_timing.fmt_duration(each) if each else "",
            "this chat" if job.get("session") else "the first chat you write in", log))


def bind_new_apart(sid, since):
    """A job started apart from a chat that could not pass its id (Hermes): the newest one with no chat, created after
    `since`, reports to sid from now on. True if one was bound."""
    base = os.path.join(q_settings.home(), "rate")
    found = []
    for folder_name in os.listdir(base) if os.path.isdir(base) else []:
        job = q_settings.load_json(os.path.join(base, folder_name, "job.json"), None)
        if job and job.get("apart") and not job.get("session") and q_limits.ts_epoch(job.get("created")) >= since:
            found.append((q_limits.ts_epoch(job["created"]), job["name"]))
    return q_rates.bind_chat(max(found)[1], sid) if found else False


def rate_here(args):
    """The reports of a job come to this chat, or to the chat given with --session."""
    if not q_settings.load_json(os.path.join(q_rates.rate_dir(args.name), "job.json"), None):
        sys.exit("quotient: no job named '%s'" % args.name)
    sid = args.session or q_rates.chat_id()
    if not sid:
        q_settings.out("Run this inside the Claude Code chat where the reports should come: it is set when the reply ends. "
            "From a terminal, give the chat with --session <id>.\n")
        return
    q_rates.bind_chat(args.name, sid)
    q_settings.out("The installment reports of '%s' now come to %s.\n" % (
        args.name, "this chat" if not args.session else "the chat %s" % args.session))


def rate_run(args):
    """One installment, kept awake while it works; afterwards the PC sleeps if the job says so."""
    folder = q_rates.rate_dir(args.name)
    lock = os.path.join(folder, "run.lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < q_settings.config()["rate"]["timeout_minutes"] * 60:
        q_settings.out("An installment of '%s' is already running.\n" % args.name)
        return
    os.makedirs(folder, exist_ok=True)
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    woke = q_schedules.found_asleep(q_settings.config())
    args.woke = woke
    q_schedules.keep_awake(True)
    try:
        close_lost_run(args.name, q_settings.config())
        run_installment(args)
    finally:
        q_schedules.keep_awake(False)
        try:
            os.remove(lock)
        except OSError:
            pass
    job = q_settings.load_json(os.path.join(folder, "job.json"), {}) or {}
    after = job.get("after") or "nothing"
    if after != "nothing":
        after_installment(after, q_settings.config())


def after_installment(how, cfg, sleep=None):
    """Sleep or hibernate after an installment, whoever turned the PC on (14/10/2026, the user: waking it and putting
    it to sleep must be independent). Never under someone who is using it (08/10/2026: it hibernated at 03:00 a PC in
    use): it waits until nobody has touched mouse and keyboard for idle_minutes (up to after_wait_hours), then warns
    and waits 2 more minutes; a touch in those 2 minutes keeps the PC on. True if it put the PC to sleep."""
    sleep = sleep or time.sleep
    rc = cfg["rate"]
    need = rc["idle_minutes"] * 60
    limit = rc.get("after_wait_hours", 6) * 3600
    waited = 0
    while True:
        idle = q_schedules.idle_seconds()
        if idle is None:
            q_settings.out("Cannot tell whether someone is using the PC: it stays on.\n")
            return False
        if idle >= need:
            break
        if waited >= limit:
            q_settings.out("The PC was in use until the end of the wait: it stays on.\n")
            return False
        step = min(300, need - idle + 5)
        sleep(step)
        waited += step
    it = cfg.get("lang") == "it"
    what = ("ibernazione" if how == "hibernate" else "sospensione") if it else ("hibernation" if how == "hibernate" else "sleep")
    q_rates.notify("Quotient", ("Tra 2 minuti il PC va in %s: muovi il mouse per lasciarlo acceso." if it else
                        "In 2 minutes the PC goes to %s: move the mouse to keep it on.") % what)
    sleep(120)
    idle = q_schedules.idle_seconds()
    if idle is None or idle < 110:
        q_settings.out("Someone touched the PC after the warning: it stays on.\n")
        return False
    q_settings.out("Nobody is using the PC: %s.\n" % how)
    q_schedules.go_to_sleep(how)
    return True


def refused_by_cap(entries):
    """Did Quotient's cap refuse a tool call in these transcript entries?"""
    for e in entries:
        content = (e.get("message") or {}).get("content") if e.get("type") == "user" else None
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                said = b.get("content")
                if isinstance(said, list):
                    said = " ".join(str(x.get("text") or "") for x in said if isinstance(x, dict))
                if q_hooks.CAP_RE.search(str(said or "")):
                    return True
    return False


def capped(transcript):
    return refused_by_cap(q_settings.read_jsonl(transcript))


def helper_work(transcript):
    """The helpers (subagents) of an installment: their files, what they did (web searches, pages fetched, files read)
    and whether the cap stopped them. 15/10/2026: three helpers stopped at the cap had done about 120 web searches,
    and nobody had written them down."""
    base = transcript[:-6] if transcript.endswith(".jsonl") else transcript
    helpers = []
    for path in sorted(glob.glob(os.path.join(base, "subagents", "agent-*.jsonl"))):
        entries = q_settings.read_jsonl(path)
        used = {}
        for e in entries:
            for b in (e.get("message") or {}).get("content") or [] if e.get("type") == "assistant" else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    used[b.get("id") or len(used)] = b.get("name")
        names = list(used.values())
        meta = q_settings.load_json(path[:-6] + ".meta.json", {})
        helpers.append({"file": path, "what": str((meta if isinstance(meta, dict) else {}).get("description") or "")[:80],
                        "searches": names.count("WebSearch"), "pages": names.count("WebFetch"),
                        "reads": sum(names.count(n) for n in ("Read", "Grep", "Glob")),
                        "stopped": refused_by_cap(entries)})
    return helpers


def save_helpers_note(folder, helpers, number, lang):
    """At the end of an installment stopped before it saved everything: where its helpers left their work, added to
    the handoff, so the next installment takes it up instead of doing it again."""
    it = lang == "it"
    notes = sorted(glob.glob(os.path.join(folder, "notes", "*")))
    lines = ["", "## " + (("Lavoro degli aiutanti fermati (rata %d, scritto da Quotient)" if it else
                           "Work of the stopped helpers (installment %d, written by Quotient)") % number),
             ("La rata %d si è fermata prima di salvare tutto. Prima di rifare le ricerche di questi aiutanti, leggi i "
              "loro file (righe JSON: i risultati degli strumenti tengono quello che hanno trovato)." if it else
              "Installment %d stopped before it saved everything. Before doing these helpers' searches again, read "
              "their files (JSON lines: the tool results hold what they found).") % number]
    for h in helpers:
        lines.append(("- %s: %d ricerche, %d pagine, %d letture%s. File: %s" if it else
                      "- %s: %d searches, %d pages, %d reads%s. File: %s") % (
            h["what"] or ("aiutante" if it else "helper"), h["searches"], h["pages"], h["reads"],
            (", fermato dal tetto" if it else ", stopped by the cap") if h["stopped"] else "", h["file"]))
    if notes:
        lines.append(("File salvati in notes: %s" if it else "Files saved in notes: %s") % ", ".join(notes))
    with open(os.path.join(folder, "HANDOFF.md"), "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


TIME_LINE = (" Time limit: Quotient stops this installment at %s (this PC's clock), whatever it is doing, and what is not "
             "saved is lost. Keep the handoff up to date, and have your final report in it before then.")


def open_run_path(folder):
    return os.path.join(folder, "run-open.json")


def drop_open_run(folder):
    try:
        os.remove(open_run_path(folder))
    except OSError:
        pass


def measure_transcript(transcript, cfg):
    """What an installment spent, from its transcript and its helpers'."""
    entries = q_settings.read_jsonl(transcript) + q_costs.subagent_entries(transcript, None)
    wt, calls = q_costs.cost_of(entries, cfg["weights"])
    # an installment starts in a new chat: its chat part is re-reading that start at every call
    fresh = q_costs.first_context(transcript)
    main_calls = q_costs.ordered_calls(entries)
    return {"wt": wt, "calls": calls, "families": q_costs.families_of(entries, cfg["weights"]), "fresh": fresh,
            "chat": q_costs.chat_part(main_calls, 0, fresh, cfg["weights"]),
            # 1.2.2: what its first call paid for that start (written to the cache), learned for the next quotes
            "start_wt": round(q_costs.span_cost(main_calls[0]["usage"], 0, fresh, cfg["weights"])) if main_calls else None,
            "tokens": q_costs.tokens_of(entries)}


def measure_into(run, name, transcript, cfg):
    """A recorded run with no measure gets the one of its transcript. Returns what it spent per model family."""
    m = measure_transcript(transcript, cfg)
    sid = os.path.basename(transcript)[:-6]
    helpers = helper_work(transcript)
    run.update(session=sid, wt=m["wt"], calls=m["calls"], chat=m["chat"], fresh=m["fresh"], start_wt=m["start_wt"],
               tokens=m["tokens"] or None, pieces=q_hooks.run_pieces(name, sid), helpers=len(helpers),
               helpers_stopped=sum(1 for h in helpers if h["stopped"]),
               elsewhere=q_learning.elsewhere_wt(q_limits.ts_epoch(run.get("started")), q_limits.ts_epoch(run.get("finished")), {sid}))
    return m["families"]


def close_lost_run(name, cfg):
    """An installment Quotient itself did not see the end of (the PC turned off, the process killed) has no line in
    runs.jsonl: at the job's next run its marker is still there, and the line is written from the transcript."""
    folder = q_rates.rate_dir(name)
    marker = q_settings.load_json(open_run_path(folder), None)
    if not marker:
        return None
    runs = q_settings.read_jsonl(os.path.join(folder, "runs.jsonl"))
    started = marker.get("started")
    drop_open_run(folder)
    if not started or any(r.get("started") == started for r in runs):
        return None
    transcript = q_costs.find_run_transcript(folder, started, q_settings.now_iso(), {r.get("session") for r in runs})
    if not transcript:
        return None
    finished = datetime.fromtimestamp(os.path.getmtime(transcript), timezone.utc).astimezone().isoformat(timespec="seconds")
    handoff = q_schedules.load_text(os.path.join(folder, "HANDOFF.md")) or ""
    run = {"started": started, "finished": finished, "found_asleep": None, "usd": None, "done": False,
           "error": "stopped: Quotient did not see the end of this installment (PC turned off or process killed)",
           "cap": marker.get("cap"), "progress": q_costs.parse_progress(handoff),
           "seconds": round(max(0.0, q_limits.ts_epoch(finished) - q_limits.ts_epoch(started))), "predicted_seconds": None,
           "check": 1}
    families = measure_into(run, name, transcript, cfg)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None) or {}
    q_costs.add_families(job, families)
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    q_settings.append_jsonl(os.path.join(folder, "runs.jsonl"), run)
    return run


def repair_job(name, cfg, dry=False):
    """Lines of runs.jsonl written before 31/10/2026 by a stopped installment (0 wt, no session): measured again from the
    transcript. A copy of the file first. [(line, wt before)] of what changed or would change."""
    folder = q_rates.rate_dir(name)
    path = os.path.join(folder, "runs.jsonl")
    runs = q_settings.read_jsonl(path)
    changed, families = [], {}
    known = {r.get("session") for r in runs}
    for r in runs:
        if r.get("session") or r.get("wt") or not r.get("error"):
            continue
        transcript = q_costs.find_run_transcript(folder, r.get("started"), r.get("finished"), known)
        if not transcript:
            continue
        known.add(os.path.basename(transcript)[:-6])
        was = r.get("wt")
        if dry:
            r["wt"] = measure_transcript(transcript, cfg)["wt"]
        else:
            for k, v in measure_into(r, name, transcript, cfg).items():
                families[k] = families.get(k, 0) + v
            r["repaired"] = {"at": q_settings.now_iso(), "wt": was}
        changed.append((r, was))
    if dry or not changed:
        return changed
    shutil.copyfile(path, path + datetime.now().strftime(".%Y%m%d-%H%M%S.bak"))
    q_repairs.write_rows(path, runs)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None) or {}
    q_costs.add_families(job, families)
    if job.get("status") == "done":
        repair_finished(name, job, runs)
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    if any(r is runs[-1] for r, _ in changed) and runs[-1].get("report_page"):
        q_rates.write_report_page(name, job, runs, cfg, folder)   # the page of that installment said 0 wt
    return changed


def repair_finished(name, job, runs):
    """A finished job's total, and its row in jobs.jsonl (a copy first), with the installments measured again."""
    total = sum(r.get("wt") or 0 for r in runs)
    job["actual"] = total
    jobs = q_settings.read_jsonl(q_repairs.jobs_path())
    at = [i for i, j in enumerate(jobs) if j.get("session") == "rate:" + name]
    if not at:
        return
    chat = sum(r.get("chat") or 0 for r in runs)
    row = dict(jobs[at[-1]], actual=total, chat=chat, work=max(0, total - chat), calls=sum(r.get("calls") or 0 for r in runs))
    if row.get("raw_estimate"):
        row["ratio"] = round(row["work"] / row["raw_estimate"], 4)
    copies = q_repairs.fix_backup()
    jobs[at[-1]] = row
    q_repairs.write_rows(q_repairs.jobs_path(), jobs)
    q_repairs.fix_log({"action": "repair-run", "keys": [q_repairs.job_key(row)], "backup": copies})


def rate_repair(args):
    """`rate repair [name] [--dry]`: installments stopped before 31/10/2026 get their real cost from their transcript."""
    base = os.path.join(q_settings.home(), "rate")
    names = [args.name] if args.name else (sorted(os.listdir(base)) if os.path.isdir(base) else [])
    cfg = q_settings.config()
    seen = 0
    for name in names:
        folder = q_rates.rate_dir(name)
        if not os.path.exists(os.path.join(folder, "job.json")):
            continue
        if os.path.exists(os.path.join(folder, "run.lock")):
            q_settings.out("%s: an installment is running, left as it is.\n" % name)
            continue
        for r, was in repair_job(name, cfg, bool(args.dry)):
            seen += 1
            q_settings.out("%s: installment of %s, stopped (%s): %s -> %s wt%s\n" % (
                name, str(r.get("started"))[:16], str(r.get("error"))[:40], q_quotes.fmt(was or 0), q_quotes.fmt(r.get("wt")),
                " (nothing changed: --dry)" if args.dry else ""))
    if not seen:
        q_settings.out("No stopped installment with its cost missing and its transcript still there.\n")


def run_installment(args):
    cfg = q_settings.config()
    folder = q_rates.rate_dir(args.name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    if job["status"] in ("done", "stopped", "paused"):
        q_settings.out("Job '%s' is %s.\n" % (args.name, job["status"]))
        return
    runs = q_settings.read_jsonl(os.path.join(folder, "runs.jsonl"))
    today = datetime.now().strftime("%Y-%m-%d")
    if not args.force and any((r.get("started") or "").startswith(today) for r in runs):
        q_settings.out("Today's installment of '%s' has already run. To run another one today (it spends more of "
            "today's limit): rate run %s --force\n" % (args.name, args.name))
        return
    it = cfg.get("lang") == "it"
    claude = q_rates.find_claude(cfg)
    if not claude:
        q_rates.notify(("Quotient · la rata di «%s» non è partita" if it else "Quotient · the installment of '%s' did not start") % args.name,
               "Claude Code non trovato: config claude_path <percorso>." if it else "Claude Code not found: config claude_path <path>.")
        sys.exit("quotient: claude not found; set it with: config claude_path <path>")
    rc = cfg["rate"]
    # The week comes first: an installment never plans into the reserve for normal use.
    cap = job["daily_cap"]
    room = q_weeks.week_room(cfg, job)
    if room is not None and room < cap:
        # 1.2.2: nor when the room left is under the smallest cap an installment can work with
        if room < cap * 0.1 or room < q_rates.cap_floor(cfg):
            job["last_skip"] = {"at": q_settings.now_iso(), "why": "week", "room": round(room)}
            q_settings.save_json(os.path.join(folder, "job.json"), job)
            q_rates.notify(("Quotient · rata di «%s» saltata" if it else "Quotient · installment of '%s' skipped") % args.name,
                   ("Della settimana restano solo %s token pesati prima della riserva per il tuo uso: riprova al prossimo orario."
                    if it else "The week has only %s weighted tokens left before your reserve: it tries again at the next time.")
                   % q_rates.amount(room, cfg.get("lang")))
            q_settings.out("Installment of '%s' skipped: the week has only %s wt left before the reserve.\n" % (args.name, q_quotes.fmt(room)))
            return
        cap = int(room)
        q_settings.out("Installment of '%s' shortened to %s wt to stay out of the reserve.\n" % (args.name, q_quotes.fmt(cap)))
    prompt = (rc["prompt_prefix"] + " " if rc["prompt_prefix"] else "") + q_rates.RATE_PROMPT.format(
        task=os.path.join(folder, "TASK.md"), handoff=os.path.join(folder, "HANDOFF.md"),
        notes=os.path.join(folder, "notes"), cap=q_quotes.fmt(cap), number=len(runs) + 1, days=job.get("days") or "?",
        workdir=job.get("dir") or os.getcwd())
    hook = {"hooks": {"PreToolUse": [{"hooks": [{
        "type": "command", "command": sys.executable,
        "args": [q_settings.ENTRY_FILE, "hook-pretool"], "timeout": 30}]}]}}
    cmd = [claude, "-p", prompt, "--output-format", "json",
           "--permission-mode", rc["permission_mode"], "--permission-prompts", "none",
           "--max-turns", str(rc["max_turns"]), "--add-dir", folder,
           "--settings", json.dumps(hook)]
    if job.get("model"):
        cmd += ["--model", job["model"]]
    if job.get("usd_per_wt"):
        cmd += ["--max-budget-usd", "%.2f" % (cap * job["usd_per_wt"] * rc["usd_cap_margin"])]
    cmd += list(rc["extra_args"])
    os.makedirs(os.path.join(folder, "notes"), exist_ok=True)   # where helpers save as they go (1.1.1)
    started = q_settings.now_iso()
    os.environ.pop("HERMES_SESSION_ID", None)   # hermes branch: an installment measures itself, not in the chat that started it
    os.environ["QUOTIENT_JOB"] = args.name  # for the installment's hooks: its job and its cap, only while it runs
    os.environ["QUOTIENT_CAP"] = str(cap)
    # 31/10/2026: a run stopped by the timeout left no report. It is told when the stop comes, and hook_pretool stops new
    # work in the last rate.close_minutes.
    stop_at = time.time() + rc["timeout_minutes"] * 60
    os.environ["QUOTIENT_STOP_AT"] = str(stop_at)
    cmd[2] = prompt + TIME_LINE % datetime.fromtimestamp(stop_at).strftime("%H:%M")
    q_settings.save_json(open_run_path(folder), {"started": started, "cap": cap})
    reader = q_limits.limits_reader(cfg)   # 1.1.6: the limits read every minute while the installment works
    try:
        proc = subprocess.run(cmd, cwd=job["dir"], capture_output=True, timeout=rc["timeout_minutes"] * 60)
        stdout = proc.stdout.decode("utf-8", "replace")
        stderr = proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        stdout, stderr = "", "timeout"
    finally:
        if reader:
            reader.set()
        os.environ.pop("QUOTIENT_JOB", None)
        os.environ.pop("QUOTIENT_CAP", None)
        os.environ.pop("QUOTIENT_STOP_AT", None)
    result = {}
    for line in reversed(stdout.strip().splitlines()):
        try:
            result = json.loads(line)
            break
        except ValueError:
            continue
    sid = result.get("session_id")
    transcript = q_rates.find_transcript(sid) if sid else None
    if not transcript:
        # 31/10/2026: stopped by the timeout or killed, it printed nothing: its transcript still holds what it spent
        transcript = q_costs.find_run_transcript(folder, started, q_settings.now_iso(), {r.get("session") for r in runs})
        sid = os.path.basename(transcript)[:-6] if transcript else sid
    families = {}
    chat, fresh, start_wt, read_tokens = None, None, None, {}
    if transcript:
        m = measure_transcript(transcript, cfg)
        wt, calls, families, chat, fresh, start_wt, read_tokens = (
            m["wt"], m["calls"], m["families"], m["chat"], m["fresh"], m["start_wt"], m["tokens"])
    else:
        wt, calls = round(q_costs.weigh(result.get("usage"), cfg["weights"])), result.get("num_turns")
        if job.get("model"):
            families = {q_costs.family_of(job["model"]): wt}
    usd = result.get("total_cost_usd")
    # 1.1.6: the tokens by type Claude Code gives for the whole run, numbers only (the prices they imply)
    tokens = {k: int(v) for k, v in (result.get("usage") or {}).items()
              if k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
              and isinstance(v, (int, float))} or read_tokens
    handoff = q_schedules.load_text(os.path.join(folder, "HANDOFF.md")) or ""
    done = bool(q_settings.DONE_RE.search(handoff))
    error = None
    if result.get("is_error") or not result:
        said = str(result.get("result") or "") + stderr
        low = said.lower()
        error = (q_rates.LOGIN_ERROR if "logged in" in low or "/login" in said or "authenticate" in low or "oauth" in low
                 else (said.strip()[-300:] or "error"))
    helpers = helper_work(transcript) if transcript else []
    if helpers and not done and (error or any(h["stopped"] for h in helpers) or capped(transcript)):
        save_helpers_note(folder, helpers, len(runs) + 1, cfg.get("lang"))
    finished_at = q_settings.now_iso()
    expected_run = q_notices.installment_seconds(cfg, job, cap)
    run = {"started": started, "finished": finished_at, "session": sid, "wt": wt, "calls": calls,
           "found_asleep": getattr(args, "woke", None) if isinstance(getattr(args, "woke", None), bool) else None,
           "chat": chat, "fresh": fresh, "start_wt": start_wt, "usd": usd, "tokens": tokens or None, "error": error,
           "done": done, "cap": cap,
           "progress": 100.0 if done else q_costs.parse_progress(handoff),
           "pieces": q_hooks.run_pieces(args.name, sid),   # 1.2.0: the PROGRESS lines inside the run
           # 1.1.0: an installment works alone, so its time is its whole run
           "seconds": round(max(0.0, q_limits.ts_epoch(finished_at) - q_limits.ts_epoch(started))),
           "predicted_seconds": round(expected_run) if expected_run else None,
           "helpers": len(helpers), "helpers_stopped": sum(1 for h in helpers if h["stopped"]),
           "check": 1}   # 1.1.1: set against the week (measure_checks)
    stuck = (q_settings.load_json(os.path.join(folder, "stuck.json"), {}) or {}).get(str(sid or ""))
    if stuck:
        run["stuck"] = stuck      # improvement 11
    try:
        if transcript and (cfg.get("tips") or {}).get("level"):   # improvements 5, 7: where it spent, its cache
            import savings
            run.update(savings.run_numbers(q_settings.entry(), q_settings.read_jsonl(transcript), cfg))
        run["env"] = q_learning.record_env(cfg, job.get("dir"))   # 1.1.4: the plugins, MCP servers and hooks it ran with
        run["elsewhere"] = q_learning.elsewhere_wt(q_limits.ts_epoch(started), q_limits.ts_epoch(finished_at), {sid} if sid else ())
    except Exception:
        pass
    # Read the job again: a chat may have changed it while the installment worked (`rate here`, `rate set`).
    job = q_settings.load_json(os.path.join(folder, "job.json"), None) or job
    if not done:
        # 1.1.4: what is left by the installments' own pace, against the plan; told with the new numbers when it is
        # much more, and kept to see how near it came to the real cost
        rq = q_notices.rate_requote(cfg, job, runs + [run])
        if rq:
            run["requote"] = rq
            job.setdefault("requotes", []).append(rq)
    q_costs.add_families(job, families)
    if usd and wt:
        job["usd_per_wt"] = usd / wt
    if done:
        job["status"] = "done"
        job["finished"] = run["finished"]
        total = sum(r.get("wt") or 0 for r in runs) + wt
        job["actual"] = total
        if job.get("quote"):
            # every installment starts in a new chat: its chat part is only re-reading that start
            chat_total = sum(r.get("chat") or 0 for r in runs) + (chat or 0)
            finished = {
                "started": job["created"], "finished": job["finished"], "session": "rate:" + job["name"],
                "options": {"rate": job["quote"]}, "choice": "rate", "raw_estimate": job["quote"],
                "factor_used": job.get("factor_at_quote", 1.0), "quote_cost": 0, "actual": total,
                "chat": chat_total, "older": 0, "work": max(0, total - chat_total),
                "calls": sum(r.get("calls") or 0 for r in runs) + (calls or 0),
                "turns": len(runs) + 1, "ratio": round(max(0, total - chat_total) / job["quote"], 4),
                "family": q_costs.main_family(job.get("families") or {}),
                "seconds": sum(q_notices.run_seconds(r) for r in runs) + run["seconds"],
                "predicted_seconds": job.get("predicted_seconds"),
                # 1.1.4: its type, the environment of its last installment, what other sessions spent meanwhile
                "env": run.get("env"), "elsewhere": sum(r.get("elsewhere") or 0 for r in runs + [run])}
            if job.get("type"):
                finished["type"] = job["type"]
            if job.get("requotes"):
                # the first new quote made from the installments' pace, in work, to see how near it came
                first = job["requotes"][0]
                finished["requote"] = {"at": first.get("work_at"), "total": first.get("work_total"),
                                       "progress": first.get("progress"), "ts": first.get("ts")}
            check = q_timing.progress_check(q_timing.run_packages(runs + [run]), total)   # 1.1.6: each installment is a package
            if check:
                finished["progress_check"] = check
            q_settings.append_jsonl(os.path.join(q_settings.home(), "jobs.jsonl"), finished)
            now_cfg = q_settings.config()  # read again: sharing may have been turned off during the installment
            q_sharing.queue_share(finished, now_cfg)
            try:
                q_sharing.flush_share(now_cfg, time.time() + 10)  # an installment runs in the background: no one waits
            except Exception:
                pass
        q_schedules.unschedule(args.name)
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    # A sign the user sees without opening anything, and a page with the full report that a click on it opens
    # (the report also waits in the chat that created the job).
    page = q_rates.write_report_page(args.name, job, runs + [run], cfg, folder)
    if page:
        run["report_page"] = page
    run["notified"] = q_rates.notify(*q_rates.installment_toast(args.name, job, runs + [run], cfg, page), link=q_rates.page_uri(page))
    q_settings.append_jsonl(os.path.join(folder, "runs.jsonl"), run)
    drop_open_run(folder)
    q_settings.out("Installment %d of '%s': %s wt (cap %s)%s%s\n" % (
        len(runs) + 1, args.name, q_quotes.fmt(wt), q_quotes.fmt(cap),
        ". Job finished." if done else "", " Error: %s" % run["error"] if run["error"] else ""))


def rate_status(args):
    base = os.path.join(q_settings.home(), "rate")
    names = [args.name] if args.name else (sorted(os.listdir(base)) if os.path.isdir(base) else [])
    if not names:
        q_settings.out("No installment jobs.\n")
    for name in names:
        folder = q_rates.rate_dir(name)
        job = q_settings.load_json(os.path.join(folder, "job.json"), None)
        if not job:
            continue
        runs = q_settings.read_jsonl(os.path.join(folder, "runs.jsonl"))
        spent = sum(r.get("wt") or 0 for r in runs)
        chat = q_rates.find_transcript(job.get("session")) if job.get("session") else None
        q_settings.out("%s: %s, %d installment(s), %s wt spent, cap %s per installment%s; reports go to %s\n" % (
            name, job["status"], len(runs), q_quotes.fmt(spent), q_quotes.fmt(job["daily_cap"]),
            ", raw quote %s" % q_quotes.fmt(job["quote"]) if job.get("quote") else "",
            "the chat %s" % q_notices.chat_label(chat) if chat else "the first chat the user writes in"))
        for r in runs[-5:]:
            q_settings.out("  %s  %s wt%s\n" % (r["started"][:16], q_quotes.fmt(r.get("wt")), "  error" if r.get("error") else ""))
