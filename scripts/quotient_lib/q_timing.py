"""The time of a job, its pieces of work with their new quotes, the note when a job closes, and the stopwatch."""

import json
import os
import subprocess
import sys
import time

from quotient_lib import q_costs, q_learning, q_limits, q_notices, q_quotes, q_rates, q_settings

# ---------------------------------------------------------------- time
# 15/10/2026 (1.1.0): a quote says how long a job will take, a stopwatch shows the time while it runs, and the real
# time is compared with the expected one at the end. The time is the agent's WORKING time: the user's turns and the
# waits of the choice window do not count. How long work takes is learned from the finished jobs, like the factor.

def fmt_duration(seconds):
    """A duration for people: '40 s', '12 min', '1 h 05 min' (the same in Italian)."""
    if seconds is None:
        return "?"
    s = max(0, int(round(seconds)))
    if s < 60:
        return "%d s" % s
    m = int(round(s / 60.0))
    if m < 60:
        return "%d min" % m
    h, m = divmod(m, 60)
    return "%d h %02d min" % (h, m)


def minutes_per_million(cfg, kind="chat"):
    """How long a job of this kind takes per million wt of work: (median minutes of its recent jobs that measured
    their time, how many), or None under 3 of them. Each finished job adds its own time, so it learns by itself."""
    rows = [j for j in q_learning.finished_jobs() if q_learning.kind_of(j) == kind and (j.get("seconds") or 0) > 0 and q_costs.work_of(j) > 0]
    rows = rows[-cfg["history_window"]:]
    if len(rows) < 3:
        return None
    return q_learning.median([j["seconds"] / 60.0 / q_costs.work_of(j) * 1e6 for j in rows]), len(rows)


def expected_seconds(cfg, raw, kind="chat", factor=None):
    """Expected working time of a job: its corrected work (raw x factor) x the minutes per 1M wt of its kind, or
    None until Quotient has measured the time of 3 jobs of that kind."""
    mpm = minutes_per_million(cfg, kind)
    if not mpm or not raw:
        return None
    if factor is None:
        factor = q_learning.learning(cfg, kind)["factor"]
    return raw * factor / 1e6 * mpm[0] * 60.0


def time_misses(kind=None):
    """How far the expected times were from the real ones, for the jobs that had both (x2 too long or too short
    both give 2)."""
    return [q_learning.miss(j["seconds"] / j["predicted_seconds"]) for j in q_learning.finished_jobs()
            if (kind is None or q_learning.kind_of(j) == kind) and j.get("seconds") and j.get("predicted_seconds")]


def time_text(cfg):
    """'about 14 min per 1M wt of work (installments 6 min)', or '' while it is not known."""
    chat, rate = minutes_per_million(cfg), minutes_per_million(cfg, "rate")
    if not chat and not rate:
        return ""
    text = "about %s per 1M wt of work" % fmt_duration(chat[0] * 60) if chat else "installments about %s per 1M wt of work" % fmt_duration(rate[0] * 60)
    if chat and rate:
        text += " (installments %s)" % fmt_duration(rate[0] * 60)
    return text


ASK_TOOLS = ("AskUserQuestion",)


def claude_active_seconds(entries, since, until):
    """The agent's working time in a Claude Code transcript between two moments: the time between consecutive
    entries, without the user's turns (a prompt starts a turn: the wait before it was the user's) and without the
    waits of the choice window (the answer to AskUserQuestion comes when the user has chosen)."""
    asks = set()
    for e in entries:
        if e.get("type") == "assistant":
            for b in (e.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in ASK_TOOLS:
                    asks.add(b.get("id"))
    total, prev = 0.0, since
    for e in entries:
        if e.get("isSidechain"):
            continue
        ts = q_limits.ts_epoch(e.get("timestamp")) if e.get("timestamp") else 0
        if not ts or ts < since - 1 or ts > until + 1:
            continue
        ts = min(max(ts, since), until)
        content = (e.get("message") or {}).get("content") if e.get("type") == "user" else None
        answer = isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in asks for b in content)
        if q_costs.is_turn_start(e) or answer:
            prev = ts
            continue
        total += max(0.0, ts - prev)
        prev = ts
    return total + max(0.0, until - prev)


def piece_size(raw, factor, cfg=None):
    """1.2.0: the size of a piece of a job: piece_share of its corrected quote, at least piece_min; with piece_share 0,
    requote.after (1M) as before."""
    cfg = cfg or {}
    share = float(cfg.get("piece_share") or 0)
    if share > 0 and raw:
        return max(float(cfg.get("piece_min") or 0), float(raw) * float(factor or 1.0) * share)
    return float(q_settings.merge(q_settings.DEFAULTS["requote"], cfg.get("requote") or {})["after"])


def pace_note(raw, factor, spent, seconds, cfg=None, progress=None, packages=None):
    """After the first million wt of a job, its own pace says more than the quote: how long the rest of the estimate
    takes at that pace, or that the estimate is already passed (idea of the user, 15/10/2026). 1.1.4: from then on the
    agent writes how much of the job is done (PROGRESS), and Quotient makes a new quote from it (requote_due). 1.1.6:
    with packages, the whole job from the cost so far divided by the progress, with its margin. 1.2.0: a piece is
    piece_size (a quarter of the corrected quote), no longer always 1M."""
    after = piece_size(raw, factor, cfg)
    if not spent or spent < after or not raw:
        return ""
    ask = ""
    if progress is None:
        ask = (" Past %s wt of work: in the last message of each reply of this job write the line PROGRESS: <n>%% (how "
               "much of the whole job is done, your honest estimate); Quotient makes a new quote from it when what is "
               "left changed a lot." % q_quotes.fmt(after))
    elif packages and int(spent // after) > int(packages[-1]["work"] // after):
        ask = " Another %s wt of work: write PROGRESS: <n>%% again in this reply." % q_quotes.fmt(after)   # 1.1.6: a new package
    est = package_estimate(packages, cfg)
    if est:
        ask = " By cost so far / progress: %s." % estimate_words(est) + ask
    if not seconds:
        return ask
    per_m = seconds / (spent / 1e6)
    corrected = raw * (factor or 1.0)
    if spent < corrected:
        return (" At this job's own pace (%s per 1M wt) the rest of the corrected estimate takes about %s more." % (
            fmt_duration(per_m), fmt_duration((corrected - spent) / 1e6 * per_m))) + ask
    return (" Already x%.1f the corrected estimate (%s wt) after %s: tell the user in one line, with your new estimate of "
            "what is left and how long it takes at this pace (%s per 1M wt)." % (
                spent / corrected, q_quotes.fmt(corrected), fmt_duration(seconds), fmt_duration(per_m))) + ask


def requote_due(cfg, job, work, progress):
    """1.1.4, the new quote from the job's own pace: past requote.after wt of work, when the PROGRESS the agent wrote
    says the rest (work x (100 - p) / p) differs from the rest of the corrected estimate by more than requote.percent,
    the numbers of a new quote; once per job, else None."""
    rq = q_settings.merge(q_settings.DEFAULTS["requote"], cfg.get("requote") or {})
    if job.get("requote") or progress is None or not 0 < progress < 100 or work < float(rq["after"]):
        return None
    corrected = (job.get("raw_estimate") or 0) * (job.get("factor_used") or job.get("factor") or 1.0)
    old = max(0.0, corrected - work)
    new = work * (100.0 - progress) / progress
    if abs(new - old) <= float(rq["percent"]) / 100.0 * max(old, 1.0):
        return None
    rq = {"at": round(work), "progress": progress, "rest_old": round(old), "rest": round(new),
          "total": round(work + new), "corrected": round(corrected), "ts": q_settings.now_iso(),
          "seconds": round(new * job["seconds"] / work) if job.get("seconds") else None}
    est = package_estimate(job.get("packages"), cfg)
    if est:
        rq.update(low=est["low"], high=est["high"], packages=est["packages"])   # 1.1.6: the margin of the packages
    return rq


# ---------------------------------------------------------------- 1.1.6: the work in packages (the user's idea)
# "Quotient measures the work in packages of a million: each package says what it cost and how long it took; even
# half-way through a package it works the right estimate out again from all the packages done." A package closes at
# each requote.after wt of work with a PROGRESS line; an installment is one package. The whole job = the cost so far
# divided by the progress (the time likewise), with a margin that narrows at each package; when the job closes,
# Quotient keeps how far each PROGRESS line was from the truth, and that error is the margin of the next jobs.

def add_package(job, work, progress, cfg):
    """A package of a chat job: the first PROGRESS line written after each piece of work (piece_size; 1M before 1.2.0)
    (work, working time, progress). Returns the package, or None."""
    after = piece_size(job.get("raw_estimate"), job.get("factor_used") or job.get("factor"), cfg)
    if progress is None or not 0 < progress < 100 or work < after:
        return None
    packs = job.setdefault("packages", [])
    if packs and int(work // after) <= int(packs[-1]["work"] // after):
        return None
    pack = {"work": round(work), "seconds": round(job.get("seconds") or 0), "progress": progress, "ts": q_settings.now_iso()}
    packs.append(pack)
    return pack


def run_packages(runs):
    """The packages of an installment job: one per installment with a PROGRESS line, its cost and time so far."""
    packs, work, seconds = [], 0.0, 0.0
    for r in runs:
        took = q_notices.run_seconds(r)
        for piece in r.get("pieces") or []:   # 1.2.0: the pieces inside the installment, before its end
            p = piece.get("progress")
            if p is not None and 0 < p < 100 and 0 < piece.get("wt", 0) < (r.get("wt") or 0):
                share = piece["wt"] / float(r["wt"])
                packs.append({"work": round(work + piece["wt"]), "seconds": round(seconds + took * share), "progress": p})
        work += r.get("wt") or 0
        seconds += took
        p = r.get("progress")
        if p is not None and 0 < p < 100:
            packs.append({"work": round(work), "seconds": round(seconds), "progress": p})
    return packs


def progress_error(cfg=None, kind=None):
    """How many points the agents' PROGRESS lines were off, from the jobs that closed with packages: the median of the
    last 20 jobs' own medians; 10 points until 3 jobs have it. Returns (points, jobs)."""
    found = [j["progress_check"]["median"] for j in q_learning.finished_jobs()
             if (j.get("progress_check") or {}).get("median") is not None and (kind is None or q_learning.kind_of(j) == kind)]
    found = found[-20:]
    return (q_learning.median(found), len(found)) if len(found) >= 3 else (10.0, len(found))


def package_estimate(packs, cfg=None, kind=None):
    """The whole job from its packages: cost so far x 100 / progress (time likewise), from the last package; the margin
    is the PROGRESS error learned (progress_error) and at least the spread of the packages' own estimates. None
    without packages."""
    packs = [p for p in packs or [] if p.get("progress") and 0 < p["progress"] < 100 and p.get("work")]
    if not packs:
        return None
    last = packs[-1]
    error, learned = progress_error(cfg, kind)
    p = last["progress"]
    total = last["work"] * 100.0 / p
    low, high = last["work"] * 100.0 / min(99.9, p + error), last["work"] * 100.0 / max(p - error, p / 2.0, 1.0)
    totals = [x["work"] * 100.0 / x["progress"] for x in packs[-3:]]
    if len(totals) >= 2:
        spread = (max(totals) - min(totals)) / 2.0
        low, high = min(low, total - spread), max(high, total + spread)
    est = {"total": round(total), "low": round(max(low, last["work"])), "high": round(high), "progress": p,
           "work": last["work"], "packages": len(packs), "error": error, "learned": learned}
    if last.get("seconds"):
        est["seconds"] = round(last["seconds"] * 100.0 / p)
        est["seconds_low"] = round(last["seconds"] * est["low"] / last["work"])
        est["seconds_high"] = round(last["seconds"] * est["high"] / last["work"])
    return est


def estimate_words(est, lang="en"):
    """'the whole job about 3.2M wt (between 2.8M and 3.9M), about 2h 10m in all, from 2 package(s)'."""
    it = lang == "it"
    text = ("tutto il lavoro circa %s wt (fra %s e %s)" if it else "the whole job about %s wt (between %s and %s)") % (
        q_quotes.fmt(est["total"]), q_quotes.fmt(est["low"]), q_quotes.fmt(est["high"]))
    if est.get("seconds"):
        text += (", circa %s in tutto" if it else ", about %s in all") % fmt_duration(est["seconds"])
    return text + ((", da %d pacchetti" if it else ", from %d package(s)") % est["packages"])


def progress_check(packs, final):
    """When a job closes: how far each package's PROGRESS was from the truth (its work over the final work), in points."""
    if not packs or not final:
        return None
    errors = [round(abs(p["progress"] - 100.0 * p["work"] / final), 1) for p in packs if p.get("work")]
    if not errors:
        return None
    return {"packages": len(errors), "errors": errors, "median": round(q_learning.median(errors), 1)}


def package_lines(cfg, lang):
    """1.1.6 in the report: how near the PROGRESS lines came to the truth."""
    it = lang == "it"
    jobs = [j for j in q_learning.finished_jobs() if (j.get("progress_check") or {}).get("median") is not None]
    if not jobs:
        return []
    error, learned = progress_error(cfg)
    packs = sum(j["progress_check"]["packages"] for j in jobs)
    return [("Avanzamento (PROGRESS): %d lavori chiusi a pacchetti (%d pacchetti); la riga sbagliava di %.0f punti "
             "(mediana)%s." if it else
             "Progress (PROGRESS): %d job(s) closed in packages (%d packages); the line was off by %.0f points "
             "(median)%s.") % (len(jobs), packs, q_learning.median([j["progress_check"]["median"] for j in jobs]),
                               "" if learned >= 3 else (", il margine usa ancora 10 punti" if it else
                                                        ", the margin still uses 10 points"))]


def requote_text(cfg, rq, kind="chat", context=None, lang="en"):
    """The new quote for the user (a table: the rest by the quote and at the job's pace, with its chat part, time and
    shares of the 5 hours and of the week), then the line that makes the agent show it once and ask."""
    it = lang == "it"
    nums = q_quotes.quote_numbers(cfg, {"quote": rq["rest_old"], "pace": rq["rest"]}, kind, context, factor=1.0)
    head = ["Il resto" if it else "What is left", "Lavoro" if it else "Work",
            "Parte della chat" if it else "Chat part", "Totale" if it else "Total", "Tempo" if it else "Time"]
    head += (["5 ore" if it else "5 hours"] if kind != "rate" else []) + ["Settimana" if it else "Week"]
    lines = [("NUOVO PREVENTIVO, dal ritmo del lavoro (unità: token pesati)" if it else
              "NEW QUOTE, from the job's own pace (unit: weighted tokens)"), "",
             ("Dopo %s di lavoro la riga PROGRESS dice fatto circa il %s: il resto costerà %s di quanto diceva il "
              "preventivo." if it else "After %s of work the PROGRESS line says about %s done: what is left will cost "
              "%s than the quote said.") % (q_rates.amount(rq["at"], lang), q_rates.percent(rq["progress"], lang),
                                            ("più" if it else "more") if rq["rest"] > rq["rest_old"] else
                                            ("meno" if it else "less")), "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in nums["rows"]:
        label = (("Secondo il preventivo" if it else "By the quote") if r["name"] == "quote" else
                 ("Al ritmo di adesso" if it else "At the pace so far"))
        secs = rq.get("seconds") if r["name"] == "pace" and rq.get("seconds") else r["seconds"]
        cells = [label, q_rates.amount(r["work"], lang), "+" + q_rates.amount(r["chat"], lang) if r["chat"] is not None else "?",
                 q_rates.amount(r["total"], lang), (("circa %s" if it else "about %s") % fmt_duration(secs)) if secs else "?"]
        for window in (("five_hour",) if kind != "rate" else ()) + ("seven_day",):
            left = r.get(window + "_left")
            cells.append("?" if window not in r else "~" + q_rates.percent(r[window], lang) + (
                "" if left is None else ((" (resta %s)" if it else " (%s left)") % q_rates.percent(left, lang) if left >= 0 else
                                         (" (non ci sta)" if it else " (does not fit)"))))
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", ("Tutto il lavoro: preventivo corretto %s, adesso circa %s (x%.2f)%s. È una stima, buona quanto la riga "
                   "PROGRESS." if it else "The whole job: corrected quote %s, now about %s (x%.2f)%s. An estimate, as good "
                   "as the PROGRESS line.") % (q_rates.amount(rq["corrected"], lang), q_rates.amount(rq["total"], lang),
                                              rq["total"] / max(rq["corrected"], 1.0),
                                              ((", fra %s e %s" if it else ", between %s and %s") % (
                                                  q_rates.amount(rq["low"], lang), q_rates.amount(rq["high"], lang))
                                               if rq.get("low") and rq.get("high") else "")),
              "", "[for the agent, not to copy] NEW QUOTE: before anything else, show the table above ONCE to the user "
              "as it is, in their language, then ask with the choice window whether to go on like this: go on as "
              "planned / a smaller level for the rest (say which, with your raw estimate of it) / stop here (then close "
              "the job). Do not show it again: Quotient keeps it to see how near it came to the real cost."]
    return "\n".join(lines)


def margin_words(cfg, real, expected):
    """1.1.8 (margin_percent): ', within the ±15% margin (...)' when the real cost is that near the expected one, else
    ''. The same job done again cost from -9% to +10% (16/10/2026): a miss that small is noise, not a signal."""
    margin = float((cfg or {}).get("margin_percent") or 0)
    if margin <= 0 or not expected or real is None:
        return ""
    if abs(real / float(expected) - 1) * 100 >= margin:
        return ""
    return (" (x%.2f: within the ±%g%% margin, since the same job done again varies by about ±10%%: say it is within "
            "the margin)" % (real / float(expected), margin))


def web_note(cfg, row, tail="say so in the same line"):
    """1.1.8 (note_web_haiku): for a research job, or one that searched the web, the line that says the searches' small
    model is not in the measure; '' otherwise."""
    if not (cfg or {}).get("note_web_haiku") or not (row.get("type") == "research" or row.get("searches")):
        return ""
    n = row.get("searches")
    return ("; Claude Code's web searches%s also ran a small model (haiku) that is not in the session's log, so its cost "
            "is not in this measure (on one research job measured, about 12%% of the session at list prices): %s" % (
                " (%d in this job)" % n if n else "", tail))


def closed_note(row, cfg=None):
    """For the agent, at the user's next message after a quoted job closed: what it cost and how long it took."""
    corrected = (row.get("raw_estimate") or 0) * (row.get("factor_used") or 1.0)
    text = ("The last quoted job (level '%s') is closed: real cost %s wt (work %s + chat part %s) against a corrected "
            "estimate of %s wt of work%s" % (row.get("choice"), q_quotes.fmt(row.get("actual") or 0), q_quotes.fmt(q_costs.work_of(row)),
                                             q_quotes.fmt(row.get("chat") or 0), q_quotes.fmt(corrected),
                                             margin_words(cfg, q_costs.work_of(row), corrected)))
    if row.get("claude"):
        n = row.get("claude_runs") or 1   # hermes branch: the Claude Code runs it started, inside the work
        text += "; of which %s wt in %d Claude Code run%s it started (claude -p)" % (
            q_quotes.fmt(row["claude"]), n, "" if n == 1 else "s")
    if row.get("aside"):
        # 1.1.1: the replies about something else are counted apart: say the three numbers
        text += ("; the messages in between (%d repl%s about something else) are counted apart: say 'work %s wt · "
                 "messages in between %s wt · total %s wt'" % (
                     row.get("aside_turns") or 1, "y" if (row.get("aside_turns") or 1) == 1 else "ies",
                     q_quotes.fmt(q_costs.work_of(row) + (row.get("chat") or 0)), q_quotes.fmt(row["aside"]), q_quotes.fmt(row.get("actual") or 0)))
    if row.get("seconds"):
        text += "; working time %s" % fmt_duration(row["seconds"])
        if row.get("predicted_seconds"):
            text += " against about %s expected" % fmt_duration(row["predicted_seconds"])
    rq = row.get("requote")
    if rq and rq.get("total"):
        # 1.1.4: how near the new quote made halfway came to the truth
        text += "; the new quote made after %s wt of work said %s wt of work in all, the real work was %s (x%.2f)" % (
            q_quotes.fmt(rq.get("at")), q_quotes.fmt(rq["total"]), q_quotes.fmt(q_costs.work_of(row)), max(q_costs.work_of(row), 1) / rq["total"])
    if (row.get("elsewhere") or 0) >= max(50000, 0.05 * (row.get("actual") or 0)):
        # 1.1.4: work done elsewhere meanwhile
        text += ("; while it ran, other sessions (other chats, installments, Hermes) spent %s wt: not in this job, "
                 "but in the limits" % q_quotes.fmt(row["elsewhere"]))
    text += web_note(cfg, row) + ". Tell the user in one line, in their language."
    if ((cfg or q_settings.config()).get("whatif") or {}).get("enabled"):      # improvement 8
        import savings
        cheaper = savings.what_if(q_settings.entry(), cfg or q_settings.config(), row.get("actual") or 0, row.get("family"), "en")
        text += (" " + cheaper) if cheaper else ""
    return text


# The stopwatch: a small file the hooks keep (run while the agent works, pause on the user's turn, end when the job
# closes) and, unless it is off, a small always-on-top window that reads it every second.

def timer_path():
    return os.path.join(q_settings.home(), "timer.json")


def timer_state():
    return q_settings.load_json(timer_path(), {})


def timer_seconds(st, now=None):
    """What the stopwatch shows: the finished stretches plus the running one."""
    secs = float(st.get("done") or 0)
    if st.get("state") == "run" and st.get("since"):
        secs += max(0.0, (now if now is not None else time.time()) - float(st["since"]))
    return secs


def timer_put(cfg, state, done, predicted=None, label=None, start=False):
    """Set the stopwatch: 'run' (the agent works), 'pause' (the user's turn) or 'end' (the job is closed). `done` is
    the working time measured so far; a new stopwatch (start) forgets the old one."""
    now = time.time()
    st = {"started": now} if start else timer_state()
    st.update(state=state, done=round(float(done or 0), 1), since=now if state == "run" else None, ts=now)
    if start or predicted is not None:
        st["predicted"] = round(predicted) if predicted else None
    if label is not None:
        st["label"] = label
    q_settings.save_json(timer_path(), st)
    if state != "end":
        timer_window_open(cfg)
    return st


def timer_started_in(begin, end):
    """When the agent started the stopwatch with `timer start` (the work begins after the choice), if that happened
    between two moments; else None."""
    st = timer_state()
    at = st.get("started") or 0
    return at if st.get("by") == "command" and begin - 2 <= at <= end + 2 else None


def timer_window_on(cfg):
    if os.environ.get("QUOTIENT_TIMER_WINDOW", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool((cfg.get("timer") or {}).get("window", True))


def timer_window_open(cfg):
    """Start the stopwatch window unless it is off, already open, closed by the user for this job, or impossible
    here (without tkinter the window writes timer-window.unavailable once and is not tried again)."""
    if not timer_window_on(cfg):
        return False
    if timer_state().get("hidden") or os.path.exists(os.path.join(q_settings.home(), "timer-window.unavailable")):
        return False
    alive = os.path.join(q_settings.home(), "timer-window.alive")
    try:
        if time.time() - float(q_settings.load_json(alive, {}).get("ts") or 0) < 4:
            return False
    except (TypeError, ValueError):
        pass
    q_settings.save_json(alive, {"ts": time.time(), "starting": True})
    exe, kw = sys.executable, {}
    if os.name == "nt":
        quiet = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = quiet if os.path.isfile(quiet) else exe
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    try:
        # never the hook's own pipes: Hermes and Claude Code wait for them to close
        subprocess.Popen([exe, q_settings.ENTRY_FILE, "timer-window"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)
        return True
    except OSError:
        return False


def timer_window():
    """The small always-on-top stopwatch (command `timer-window`, started by Quotient). It shows the working time of
    the open job against the expected one, stops on the user's turn, and closes itself 30 s after the job ends.
    Closing it by hand hides it until the next job."""
    alive = os.path.join(q_settings.home(), "timer-window.alive")
    try:
        import tkinter as tk
    except Exception:
        q_settings.save_json(os.path.join(q_settings.home(), "timer-window.unavailable"), {"ts": q_settings.now_iso(), "python": sys.executable})
        return
    other = q_settings.load_json(alive, {})
    if not other.get("starting") and time.time() - float(other.get("ts") or 0) < 3:
        return  # another window is open
    q_settings.save_json(alive, {"ts": time.time(), "pid": os.getpid()})
    it = q_settings.config().get("lang") == "it"
    c = {"bg": "#0d1117", "fg": "#e6edf3", "muted": "#a2abb6", "green": "#56d364", "amber": "#e3b341",
         "track": "#30363d"}
    root = tk.Tk()
    root.title("Quotient")
    root.configure(bg=c["bg"])
    root.resizable(False, False)
    for attribute in ("-topmost", "-toolwindow"):
        try:
            root.attributes(attribute, True)
        except tk.TclError:
            pass
    width, height = 260, 108
    root.geometry("%dx%d+%d+%d" % (width, height, root.winfo_screenwidth() - width - 24,
                                   root.winfo_screenheight() - height - 96))
    top = tk.Label(root, bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9), anchor="w")
    top.pack(fill="x", padx=12, pady=(8, 0))
    clock = tk.Label(root, bg=c["bg"], fg=c["fg"], font=("Consolas", 24, "bold"), anchor="w")
    clock.pack(fill="x", padx=12)
    bar = tk.Canvas(root, width=width - 24, height=6, bg=c["track"], highlightthickness=0, bd=0)
    bar.pack(padx=12, pady=(2, 4))
    fill = bar.create_rectangle(0, 0, 0, 6, fill=c["green"], width=0)
    low = tk.Label(root, bg=c["bg"], fg=c["muted"], font=("Segoe UI", 9), anchor="w")
    low.pack(fill="x", padx=12)

    def close():
        st = timer_state()
        if st:
            st["hidden"] = True
            q_settings.save_json(timer_path(), st)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)

    def tick():
        now = time.time()
        q_settings.save_json(alive, {"ts": now, "pid": os.getpid()})
        st = timer_state()
        state, age = st.get("state"), now - float(st.get("ts") or 0)
        if not st or st.get("hidden") or (state == "end" and age > 30) or age > 12 * 3600:
            root.destroy()
            return
        secs = timer_seconds(st, now)
        s = int(secs)
        clock["text"] = "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60) if s >= 3600 else "%02d:%02d" % (s // 60, s % 60)
        pred = st.get("predicted")
        top["text"] = (("Quotient · lavoro «%s»" if it else "Quotient · job '%s'") % st["label"]) if st.get("label") else "Quotient"
        over = bool(pred) and secs > pred
        bar.coords(fill, 0, 0, (width - 24) * (min(1.0, secs / pred) if pred else 0), 6)
        bar.itemconfigure(fill, fill=c["amber"] if over else c["green"])
        expected = (("previsti circa %s" if it else "about %s expected") % fmt_duration(pred) if pred else
                    ("tempo previsto dopo 3 lavori misurati" if it else "expected time after 3 measured jobs"))
        if state == "end":
            low["text"] = ("finito · " if it else "done · ") + expected
            clock["fg"] = c["amber"] if pred and secs > pred * 1.1 else c["green"]
        elif state == "pause":
            low["text"] = ("in pausa, tocca a te · " if it else "paused, your turn · ") + expected
            clock["fg"] = c["muted"]
        else:
            low["text"] = expected
            clock["fg"] = c["amber"] if over else c["fg"]
        root.after(1000, tick)

    tick()
    root.mainloop()
    try:
        os.remove(alive)
    except OSError:
        pass


def cmd_timer(args):
    """`timer start --raw N`: the agent starts the stopwatch when the work begins (after the choice); `timer show`;
    `timer stop` (hides it)."""
    cfg = q_settings.config()
    if args.what == "start":
        kind = "rate" if args.kind == "rate" else "chat"
        factor = q_learning.chat_factor(cfg, args.raw) if args.raw and kind == "chat" else None
        predicted = expected_seconds(cfg, args.raw, kind, factor) if args.raw else None
        st = timer_put(cfg, "run", 0, predicted, args.level or None, start=True)
        st["by"] = "command"
        q_settings.save_json(timer_path(), st)
        q_settings.out("Stopwatch started%s.\n" % (": about %s expected" % fmt_duration(predicted) if predicted else
                                       " (no expected time yet: Quotient learns it after 3 measured jobs)"))
    elif args.what == "stop":
        st = timer_state()
        if st:
            st["hidden"] = True
            q_settings.save_json(timer_path(), st)
        q_settings.out("Stopwatch hidden until the next job.\n")
    else:
        st = timer_state()
        q_settings.out(("%s · %s of about %s\n" % (st.get("state"), fmt_duration(timer_seconds(st)), fmt_duration(st.get("predicted"))))
            if st else "No stopwatch.\n")


def job_time_from_logs(job, home_hermes=None):
    """The working time of a job measured before 1.1.0, from what is still on disk: an installment job from its runs
    (each runs alone, start to end); a Hermes job from its chat's messages; a Claude Code job from its transcript.
    The job's first turn counts from its start (the CHOICE line comes at its end). None when nothing is left."""
    sid = str(job.get("session") or "")
    begin, end = q_limits.ts_epoch(job.get("started")), q_limits.ts_epoch(job.get("finished"))
    if not begin or not end or end < begin:
        return None
    if sid.startswith("rate:"):
        runs = q_settings.read_jsonl(os.path.join(q_rates.rate_dir(sid[5:]), "runs.jsonl"))
        spans = [q_limits.ts_epoch(r.get("finished")) - q_limits.ts_epoch(r.get("started")) for r in runs
                 if r.get("started") and r.get("finished") and begin - 60 <= q_limits.ts_epoch(r.get("started")) <= end + 60]
        return float(sum(s for s in spans if s > 0)) or None
    if sid.startswith("hermes:"):
        import hermes_source as hs
        chat = sid[7:]
        first = hs.last_user_message(chat, begin + 5, home_hermes) or begin
        return hs.active_seconds(chat, min(first, begin), end, home_hermes)
    transcript = q_rates.find_transcript(sid) if sid else None
    if not transcript:
        return None
    entries = [e for e in q_settings.read_jsonl(transcript) if not e.get("isSidechain")]
    starts = [q_limits.ts_epoch(e.get("timestamp")) for e in entries if q_costs.is_turn_start(e)]
    first = max([s for s in starts if s <= begin + 5] or [0])
    if not first:
        return None
    return claude_active_seconds(entries, first, end)


def backfill_time(deadline=None, home_hermes=None):
    """Jobs measured before 1.1.0 have no time: work it out once from the logs (`job_time_from_logs`), so the
    expected times start from real data. Each job is looked at once (`time_checked`). Returns how many got a time."""
    path = os.path.join(q_settings.home(), "jobs.jsonl")
    jobs = q_settings.read_jsonl(path)
    todo = [j for j in jobs if j.get("seconds") is None and not j.get("time_checked")]
    if not todo:
        return 0
    filled = 0
    for job in todo:
        if deadline and time.time() > deadline:
            break
        job["time_checked"] = True
        try:
            secs = job_time_from_logs(job, home_hermes)
        except Exception:  # a log that cannot be read leaves the job without a time
            secs = None
        if secs and secs > 0:
            job["seconds"], job["seconds_from"] = round(secs), "logs"
            filled += 1
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return filled
