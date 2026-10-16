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
    """Counters of a chat plus its subagents, and its API calls. 1.1.4: under "aux", the counters of Hermes' calls in
    the background for them (hs.read_aux), kept apart so that what one call re-reads stays the chat's own."""
    total = {k: 0 for k in hs.COUNTERS}
    aux = {k: 0 for k in hs.COUNTERS}
    calls = 0
    for row in hs.read_sessions():
        if row.get("id") == sid or row.get("parent_session_id") == sid:
            for k in hs.COUNTERS:
                total[k] += int(row.get(k) or 0)
                aux[k] += int((row.get("aux") or {}).get(k) or 0)
            if row.get("id") == sid:
                calls = int(row.get("api_call_count") or 0)
    total["aux"] = aux
    return total, calls


def _grow(totals, start):
    """What a chat's counters grew since a snapshot, the calls in the background included (1.1.4). A snapshot from
    before 1.1.4 has no "aux": the background then counts from now, so what it spent before is not put in a job."""
    grow = {k: max(0, totals[k] - int(start.get(k, totals[k]) or 0)) for k in hs.COUNTERS}
    aux, aux0 = totals.get("aux") or {}, start.get("aux")
    if isinstance(aux0, dict):
        for k in hs.COUNTERS:
            grow[k] += max(0, int(aux.get(k) or 0) - int(aux0.get(k) or 0))
    return grow


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


def _work_now(cfg, job, totals, calls):
    """The work of an open job so far: its growth, without the replies about something else and the chat part."""
    grow = _grow(totals, job["start"])
    actual = hs.weigh_hermes(grow, cfg["weights"])
    aside = min(actual, job.get("aside") or 0)
    d_calls = max(0, calls - job.get("start_calls", calls) - (job.get("aside_calls") or 0))
    return max(0.0, actual - aside - min(actual - aside, d_calls * (job.get("ctx") or 0) * cfg["weights"]["cache_read"]))


def short_line(q, cfg, factor, ctx, rate=None, steps=None, steps_rate=None, timing=""):
    lang = cfg.get("lang")
    limits = q.limits_line(lang) or ("limiti non letti" if lang == "it" else "limits not read")
    chat = q.fmt(ctx * cfg["weights"]["cache_read"]) if ctx else "?"
    rate_part = " (installments x%.2f)" % rate if rate is not None else ""
    mid = q.mid_factor(cfg)
    top = cfg.get("learn_min_raw") or 0
    mid_part = " (quotes under %s x%.2f; from %s at least %s)" % (q.fmt(top), mid, q.fmt(top), q.fmt(top * mid)) if mid else ""
    measured = ""
    if steps:
        measured = "; a job takes about %d steps per 1M wt of work%s" % (
            round(steps[0]), " (installments %d)" % round(steps_rate[0]) if steps_rate else "")
    if timing:
        measured += "; working time %s" % timing
    return ("[Quotient %s] %s · factor x%.2f%s%s · threshold %s wt · CHAT PART: each step re-reads about %s tokens "
            "(%s wt)%s. Big job: quote first (QUOTE / CHOICE / JOB: CLOSE in the last message)." % (
                q.VERSION, limits, factor, mid_part, rate_part, q.fmt(cfg["threshold"]), q.fmt(ctx), chat, measured))


def job_factor(q, cfg, raw, wtype=None):
    """The factor a chosen level is corrected with: its type of work's and the medium band's (16/10/2026: before, the
    jobs quoted in Hermes took the plain factor, and the band was only shown in the line)."""
    return q.chat_factor(cfg, raw, wtype)


def hermes_protocol(q, cfg, factor):
    """Quotient's protocol, adapted: in Hermes the choice window is the clarify tool and there are no slash commands."""
    text = q.protocol(cfg, factor)
    text = text.replace("call the AskUserQuestion tool", "call the clarify tool (one call, both questions)")
    return text + ("In Hermes: run quote-table with `--context <the tokens of the CHAT PART line>`, so it knows what each "
                   "step re-reads. The clarify tool, too, shows 4 choices at most per question and adds 'Other' by "
                   "itself: 1 to 4 options, and say what 'Other' is for. "
                   "When the quoted job is finished (or abandoned), write `JOB: CLOSE` (or `JOB: DROP` if abandoned) "
                   "in the last message, so Quotient measures it. Installments (rate) run with Claude Code, and so does a "
                   "job done apart, now (`rate apart`: Claude Code's `claude -p`, on the same plan): say so in the window. "
                   "Their reports come back to this chat.\n")


def pre_llm_call(q, payload):
    cfg = q.config()
    sid = payload.get("session_id") or ""
    q.measured_turns(cfg)
    state = _load(q)
    chat = state.setdefault(sid, {})
    if chat.get("job"):
        q.limits_soon(cfg)   # 1.1.6: a job open: the limits read every minute, in the background
    else:
        q.refresh_limits(cfg)
    totals, calls = _counters(sid)
    ctx = _context_per_call(chat, totals, calls)
    chat["ctx"] = ctx
    chat["last"] = dict(totals, calls=calls)
    # where this reply starts: see post_llm_call (the epoch for the working time, 1.1.0)
    chat["turn_start"] = dict(totals, calls=calls, at=q.now_iso(), epoch=time.time())
    if not chat.get("told"):
        try:
            q.backfill_time(time.time() + 4)   # once: the time of the jobs measured before 1.1.0
        except Exception:
            pass
    factor = q.learning(cfg)["factor"]
    rate = q.learning(cfg, "rate")["factor"]
    steps, steps_rate = q.steps_per_million(cfg), q.steps_per_million(cfg, "rate")
    timing = q.time_text(cfg)
    if not chat.get("told"):
        chat["told"] = True
        text = hermes_protocol(q, cfg, factor) + short_line(q, cfg, factor, ctx, rate, steps, steps_rate, timing)
    else:
        text = short_line(q, cfg, factor, ctx, rate, steps, steps_rate, timing)
    incomplete = chat.pop("quote_incomplete", None)
    if incomplete:                       # 1.1.3: the quote of the reply before lacked numbers: give it again first
        text += "\n" + q.incomplete_line(incomplete)
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
        spent = hs.weigh_hermes(_grow(totals, open_job["start"]), cfg["weights"])
        text += " Open job: %s, about %s wt spent of %s (raw)" % (open_job["choice"], q.fmt(spent),
                                                                  q.fmt(open_job["raw_estimate"]))
        if open_job.get("seconds") is not None:
            text += ", working time so far %s%s" % (q.fmt_duration(open_job["seconds"]), " of about %s expected" % (
                q.fmt_duration(open_job["predicted_seconds"])) if open_job.get("predicted_seconds") else "")
        if open_job.get("aside"):
            text += ", of which %s in messages in between" % q.fmt(open_job["aside"])
        text += (". If this message is about something else, answer it and end the reply with the line ASIDE: the job "
                 "stays open and that reply is counted apart." + q.pace_note(
                     open_job["raw_estimate"], open_job.get("factor"), spent - (open_job.get("aside") or 0),
                     open_job.get("seconds"), cfg, open_job.get("progress"), open_job.get("packages")))
        q.timer_put(cfg, "run", open_job.get("seconds") or 0, open_job.get("predicted_seconds"), open_job["choice"])
    requote = chat.pop("requote_note", None)
    if requote:                          # 1.1.4: the new quote from the job's own pace, shown once
        text += "\n" + requote
    note = chat.pop("last_closed", None)
    if note:
        text += " " + note
    for alert in (q.env_alert, q.fix_alert):   # 1.1.4: a change of the environment; a job that looks split
        try:
            found = alert()
            if found:
                text += " " + found
        except Exception:
            pass
    try:
        reports = q.rate_events("hermes:" + sid, own_only=True)   # 1.1.1: jobs started apart from this chat
        if reports:
            text += "\n" + "\n".join(reports)
    except Exception:
        pass
    try:
        for line in q.check_alert(cfg):  # 1.1.1: a measure that does not match the week, told once
            text += " " + line
    except Exception:
        pass
    try:
        plan = q.plan_alert(cfg)  # 1.1.2: the limit looks changed (a change of subscription), told once in any chat
        if plan:
            text += " " + plan
    except Exception:
        pass
    _save(q, state)
    return {"context": text}


def _close(q, cfg, chat, totals, calls, how):
    job = chat.pop("job")
    chat["closed"] = {"options": job["options"], "choice": job["choice"]}   # see quotient.same_quote
    grow = _grow(totals, job["start"])
    actual = hs.weigh_hermes(grow, cfg["weights"])
    # 1.1.1: the replies about something else (ASIDE) are in the real cost, not in the work nor its steps
    aside = min(actual, job.get("aside") or 0)
    d_calls = max(0, calls - job.get("start_calls", calls) - (job.get("aside_calls") or 0))
    chat_part = min(actual - aside, d_calls * (job.get("ctx") or 0) * cfg["weights"]["cache_read"])
    row = {"started": job["started"], "session": "hermes:" + job["session"], "source": "hermes",
           "options": job["options"], "choice": job["choice"], "raw_estimate": job["raw_estimate"],
           "factor_used": job["factor"], "quote_cost": 0, "actual": round(actual), "chat": chat_part,
           "turns": job.get("turns", 1), "families": {q.family_of(job.get("model") or ""): round(actual)},
           "calls": d_calls, "ctx": round(job.get("ctx") or 0), "closed_by": how,
           "begin": job.get("begin"), "week_start": job.get("week_start")}
    if aside:
        row.update(aside=round(aside), aside_turns=job.get("aside_turns") or 1)
    if job.get("custom"):
        row["custom"] = True
    for key in ("type", "requote", "progress", "packages"):   # 1.1.4; the packages 1.1.6
        if job.get(key) is not None:
            row[key] = job[key]
    if job.get("seconds") is not None:
        row["seconds"] = job["seconds"]
        row["predicted_seconds"] = job.get("predicted_seconds")
    if how == "drop":
        st = q.timer_state()
        if st:                           # an abandoned job: the stopwatch goes away
            st["hidden"] = True
            q.save_json(q.timer_path(), st)
        return None
    if cfg.get("claude_runs"):
        # hermes branch: the Claude Code runs this chat started while the job was open are part of its cost
        try:
            runs = q.claude_runs_of(job["session"], float(job.get("begin") or 0), time.time(), cfg)
        except Exception as e:
            runs = None
            q.append_jsonl(os.path.join(q.home(), "hermes-errors.jsonl"),
                           {"ts": q.now_iso(), "event": "claude_runs", "error": repr(e)})
        if runs and runs["wt"]:
            row["actual"] += runs["wt"]
            row["claude"] = runs["wt"]
            row["claude_runs"] = len(runs["runs"])
            row["claude_sessions"] = [r.get("session") for r in runs["runs"] if r.get("session")]   # not counted again as work elsewhere
            q.add_families(row, runs["families"])
    q.close_job(row, cfg)
    chat["last_closed"] = q.closed_note(row)
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
    custom = q.parse_custom(text)        # 1.1.3: a choice of the user's own, with the agent's estimate for it
    pace = q.parse_pace(text)
    move = parse_end(text)
    closed = None
    now = time.time()
    t0 = float((chat.get("turn_start") or {}).get("epoch") or now)
    created, by_command = False, None

    def worked(since):
        """The agent's working time in this reply from a moment on: the waits of the clarify window left out."""
        secs = hs.active_seconds(sid, since, now)
        return max(0.0, now - since) if secs is None else secs

    if q.same_quote(quote, choice, chat.get("job") or chat.get("closed")):
        quote = choice = custom = None
    if quote:
        # 1.1.3: a quote the user saw without the time or the shares of a level is given again at the next message
        gaps = q.quote_gaps(cfg, quote, text)
        if gaps:
            chat["quote_incomplete"] = gaps
        else:
            chat.pop("quote_incomplete", None)
    aside = bool(q.ASIDE_RE.search(text)) and not quote and not move
    if chat.get("job"):
        job = chat["job"]
        if aside:
            # 1.1.1: a reply about something else while the job is open: counted apart, the job stays open
            start = chat.get("turn_start") or {}
            grow = _grow(totals, start)
            job["aside"] = (job.get("aside") or 0) + hs.weigh_hermes(grow, cfg["weights"])
            job["aside_calls"] = (job.get("aside_calls") or 0) + max(0, calls - int(start.get("calls", calls) or 0))
            job["aside_turns"] = (job.get("aside_turns") or 0) + 1
        else:
            job["turns"] = job.get("turns", 1) + 1
            job["seconds"] = (job.get("seconds") or 0) + worked(t0)
            progress = q.parse_progress(text)
            if progress is not None:
                job["progress"] = progress
        if move:
            closed = _close(q, cfg, chat, totals, calls, move)
        elif quote:                      # a new quote ends the job before it
            closed = _close(q, cfg, chat, totals, calls, "new-quote")
        elif not aside:
            # 1.1.4: past its first million, the job's own pace may make a new quote, shown once at the next message
            work_now = _work_now(cfg, job, totals, calls)
            q.add_package(job, work_now, q.parse_progress(text), cfg)   # 1.1.6: a package at each million
            rq = q.requote_due(cfg, job, work_now, job.get("progress"))
            if rq:
                job["requote"] = rq
                chat["requote_note"] = q.requote_text(cfg, rq, "chat", chat.get("ctx"), cfg.get("lang") or "en")
    if quote:
        chat["quote"] = {"options": quote, "ts": time.time(), "type": q.parse_type(text)}
    if choice:
        pending = (chat.get("quote") or {}).get("options") or {}
        # 14/10/2026: a job chosen for installments (or for a new chat) is not done in this chat: measuring the chat
        # as that job counted the wrong thing. The installments measure themselves.
        elsewhere = pace not in (None, "today") or bool(q.INSTALLMENT_RE.match(choice))
        raw = custom[1] if custom and pending else pending.get(choice)
        if choice in q.DECLINE or not raw or elsewhere:
            chat.pop("quote", None)
        else:
            # 14/10/2026: the CHOICE line comes in the last message of a reply, after that reply's work, so the job
            # starts where the reply started (as in Claude Code); measured from the end, it lost that work.
            start = chat.get("turn_start") or dict(totals, calls=calls)
            begin = {k: min(int(start.get(k) or 0), totals[k]) for k in hs.COUNTERS}
            if isinstance(start.get("aux"), dict):   # 1.1.4: the calls in the background, from the same moment
                begin["aux"] = {k: min(int(start["aux"].get(k) or 0), totals["aux"][k]) for k in hs.COUNTERS}
            start_calls = min(int(start.get("calls") or 0), calls)
            ctx = chat.get("ctx") or 0
            if not ctx and calls > start_calls:
                # the first reply of a chat: nothing was measured before it, so what one call re-reads is taken
                # from this reply (before, the chat part of such a job stayed at zero)
                ctx = max(0, totals["cache_read_tokens"] - begin["cache_read_tokens"]) / (calls - start_calls)
            wtype = (chat.get("quote") or {}).get("type")      # 1.1.4: the type of work learns its own factor
            factor = job_factor(q, cfg, raw, wtype)
            # its time: from `timer start` if the agent started the stopwatch in this reply, else from the reply's start
            by_command = q.timer_started_in(t0, now)
            chat["job"] = {"session": sid, "started": start.get("at") or q.now_iso(), "options": pending,
                           "choice": choice, "raw_estimate": raw, "factor": factor,
                           "start": begin, "start_calls": start_calls, "ctx": ctx,
                           "model": extra.get("model") or "", "seconds": worked(by_command or t0),
                           "predicted_seconds": q.expected_seconds(cfg, raw, factor=factor),
                           "begin": round(t0, 1), "week_start": q.week_used()}   # 1.1.1: for the check
            if custom:
                chat["job"]["custom"] = True   # 1.1.3: measured against the agent's estimate of the user's own choice
            if wtype:
                chat["job"]["type"] = wtype
            created = True
            chat.pop("quote", None)
            if move and not closed:      # chosen, done and closed in the same reply
                closed = _close(q, cfg, chat, totals, calls, move)
    if pace == "apart" and choice:
        chat["apart_since"] = now      # 1.1.1: the job started apart (rate apart) reports to this chat
    if chat.get("apart_since"):
        if q.bind_new_apart("hermes:" + sid, chat["apart_since"] - 600) or now - chat["apart_since"] > 1800:
            chat.pop("apart_since", None)
    job = chat.get("job")
    if job or closed:
        q.limits_soon(cfg)   # 1.1.6: a reading near the end of each step of a job, in the background
    if job and job.get("seconds") is not None:
        # the job goes on after this reply: the stopwatch waits for the user
        q.timer_put(cfg, "pause", job["seconds"], job.get("predicted_seconds"), job["choice"],
                    start=created and not by_command)
    chat.pop("turn_start", None)
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
