"""Claude Code's hooks: session start, each message, end of a reply, each tool call of an installment."""

import json
import os
import re
import sys
import time

from quotient_lib import q_costs, q_learning, q_limits, q_longchats, q_notices, q_quotes, q_rates, q_repairs, q_schedules, q_settings, q_sharing, q_timing, q_weeks

def hook_session():
    """SessionStart: the full protocol, once per session instead of at every message."""
    data = q_settings.read_stdin_json()
    try:
        q_costs.record_claude_link(data)   # hermes branch: before the installment's early return, so an installment is marked too
    except Exception:
        pass
    if os.environ.get("QUOTIENT_JOB"):
        return
    q_settings.sync_plugin_options()
    try:
        q_schedules.refresh_launchers()
    except Exception:  # a launcher that cannot be written must never stop a session
        pass
    cfg = q_settings.config()
    sid = data.get("session_id")
    # The shared average (once a day) and the waiting lines, within a few seconds at most.
    deadline = time.time() + 8
    try:
        q_sharing.fetch_average(cfg, deadline)
        q_sharing.flush_share(cfg, deadline)
    except Exception:  # sharing must never stop a session from starting
        pass
    try:
        q_learning.backfill_chat(time.time() + 5)
    except Exception:  # an old job that cannot be read keeps its whole cost as work
        pass
    try:
        q_timing.backfill_time(time.time() + 5)
    except Exception:  # an old job whose logs cannot be read stays without a time
        pass
    try:
        import telemetry
        telemetry.ensure(q_settings.entry(), cfg)   # 1.1.6: the receiver of Claude Code's telemetry, when it is on
    except Exception:
        pass
    text = q_quotes.protocol(cfg, q_learning.learning(cfg)["factor"])
    if not cfg.get("configured"):
        text += q_longchats.setup_instructions(cfg)
    try:
        moving = chat_jobs_text(cfg, sid)
    except Exception:  # an unreadable file of open jobs must never stop a session
        moving = []
    if moving:
        text += "\n".join(moving) + "\n"
    add_injected(sid, text)
    if q_sharing.share_enabled(cfg) and not cfg["share"].get("notice_shown"):
        # Shown to the user by Claude Code itself, not left to the model: sharing starts only after it.
        q_sharing.store(("share", "notice_shown"), True)
        q_settings.out(json.dumps({"systemMessage": q_sharing.NOTICE,
                        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
        return
    q_settings.out(text)


def hook_prompt():
    data = q_settings.read_stdin_json()
    name = os.environ.get("QUOTIENT_JOB")
    if name:
        q_settings.out("[Quotient %s] This is an installment run of the job '%s': follow the prompt. No quotes, no questions to the user.\n" % (q_settings.VERSION, name))
        return
    q_settings.sync_plugin_options()
    cfg = q_settings.config()
    sid = data.get("session_id") or "unknown"
    path = data.get("transcript_path") or ""
    state = q_settings.load_json(q_settings.session_path(sid), {})
    learned = q_learning.learning(cfg)
    hints = []
    if not state.get("job"):
        # 1.1.8: with no job open too, a reading in the background (at most every limits.every seconds), as in Hermes.
        # Claude Code without the status line (the desktop app, claude -p) read the limits only while a job was open, so
        # a new user's first quote had no shares and the line no tokens left (found in the test of 19/10/2026). Not when
        # the status line has just given them.
        last = q_settings.read_jsonl(q_limits.limits_path(), tail_bytes=4096)
        if not (last and last[-1].get("source") == "statusline" and time.time() - (last[-1].get("epoch") or 0) < 600):
            q_limits.limits_soon(cfg, q_limits.limits_every(cfg))
    ctx = q_costs.context_size(path)
    chat_line = chat_hint(cfg, ctx, state.get("fresh") or q_costs.first_context(path)) if ctx else None
    current = q_limits.limits_line("en")
    hints.append("Plan limits: %s." % current if current else "Plan limits: not read yet (see LIMITS in the protocol).")
    # 1.1.7: the size of 1% without its margin and points (the report has them; quote-table uses them); the threshold
    # and the quote rules are in the protocol, the steps and the time per million in quote-table's numbers
    prefix0 = (cfg["rate"].get("prompt_prefix") or "").strip()
    budget_on = (cfg.get("budget") or {}).get("day_percent") or (cfg.get("budget") or {}).get("week_percent")
    budget_note = ""
    if budget_on and not (prefix0 and (data.get("prompt") or "").lstrip().startswith(prefix0)):   # improvement 10
        import savings
        blocked, budget_note = savings.budget_check(q_settings.entry(), cfg, data.get("prompt") or "")
        if blocked:
            q_settings.out(json.dumps({"decision": "block", "reason": blocked}))
            return
    sizes = []
    for window, label in (("five_hour", "the 5 hours"), ("seven_day", "the week")):
        c = q_limits.week_capacity(cfg) if window == "seven_day" else q_limits.five_capacity(cfg)
        if c:
            sizes.append("%s ~%s wt%s" % (label, q_quotes.fmt(c["per_point"]), q_limits.week_source(c)))
    if sizes:
        hints.append("1%% of %s." % ", of ".join(sizes))
    lines = ["[Quotient %s] %s %s" % (q_settings.VERSION, q_quotes.calibration(cfg, learned), " ".join(hints))]
    if chat_line:
        lines.append(chat_line)
    # A prompt that starts with the installment tag is a scheduled task, not the user: reports wait for the user.
    prefix = (cfg["rate"].get("prompt_prefix") or "").strip()
    scheduled = bool(prefix and (data.get("prompt") or "").lstrip().startswith(prefix))
    if not scheduled:
        lines += q_notices.rate_events(sid, path)
    for alert in (q_weeks.week_alert(cfg), None if scheduled else q_weeks.pace_alert(cfg), None if scheduled else q_weeks.auth_alert(cfg)):
        if alert:
            lines.append(alert)
    if not scheduled:
        try:
            lines += q_repairs.check_alert(cfg)
        except Exception:  # a check that cannot be made must never stop a message
            pass
    if (cfg.get("telemetry") or {}).get("enabled"):
        try:
            import telemetry   # 1.1.6: the receiver if it stopped; a job whose two measures disagree, told once
            telemetry.ensure(q_settings.entry(), cfg)
            found = None if scheduled else telemetry.alert(q_settings.entry(), cfg)
            if found:
                lines.append(found)
        except Exception:
            pass
    try:
        plan = q_limits.plan_alert(cfg, scheduled)   # 1.1.2: the limit looks changed (a change of subscription), told once
        if plan:
            lines.append(plan)
    except Exception:
        pass
    job = state.get("job")
    pending = state.get("pending")
    closed_told = state.get("last_closed") if not scheduled else None
    if closed_told:
        lines.append(closed_told)
    aside_told = None
    if job:
        timing = ""
        if job.get("seconds") is not None:
            timing = "; working time so far %s%s" % (q_timing.fmt_duration(job.get("seconds")), " of about %s expected" % (
                q_timing.fmt_duration(job["predicted_seconds"])) if job.get("predicted_seconds") else "")
        line = ("Open job (level '%s', raw estimate %s wt, spent so far %s wt, of which %s re-reading the older chat%s%s). "
                "Unfinished at the end of this reply: end it with JOB: CONTINUES." % (
                    job.get("choice"), q_quotes.fmt(job.get("raw_estimate")), q_quotes.fmt(job.get("actual")), q_quotes.fmt(job.get("chat") or 0),
                    " and %s messages in between" % q_quotes.fmt(job["aside"]) if job.get("aside") else "", timing))
        if state.get("aside_told") != (job.get("started") or "job"):
            # 1.1.7: at the first message of the job and after a reply counted apart; the protocol explains ASIDE
            line += (" If this message is about something else, answer it and end the reply with the line ASIDE "
                     "instead: the job stays open and that reply is counted apart.") + q_quotes.addition_hint(cfg)
            aside_told = job.get("started") or "job"
        lines.append(line + q_timing.pace_note(job.get("raw_estimate"), job.get("factor_used"),
                                      job.get("actual") - (job.get("aside") or 0), job.get("seconds"), cfg,
                                      job.get("progress"), job.get("packages")))
        if not scheduled:
            q_timing.timer_put(cfg, "run", job.get("seconds") or 0, job.get("predicted_seconds"), job.get("choice"))
        q_limits.limits_soon(cfg)   # 1.1.6: a job open: the limits read every minute, in the background
    elif pending:
        lines.append("A quote waits for the user's choice (raw: %s). If this message chooses, write `CHOICE: <level>` "
                     "(for a choice of their own, `CHOICE: custom=<your raw estimate of it>`) and `PACE: ...` as the "
                     "protocol says, then go on." % (
                         ", ".join("%s=%s" % (k, q_quotes.fmt(v)) for k, v in pending["options"].items())))
    if not scheduled:
        for alert in (q_learning.env_alert, q_repairs.fix_alert):   # 1.1.4: a change of the environment; a measure to repair, told once
            try:
                found = alert()
                if found:
                    lines.append(found)
            except Exception:  # a check that cannot be made must never stop a message
                pass
    requote = None if scheduled else state.get("requote_note")
    if requote:
        lines.insert(1, requote)                       # 1.1.4: the new quote, before anything else, once
    incomplete = None if scheduled else state.get("quote_incomplete")
    if incomplete:
        lines.insert(1, q_quotes.incomplete_line(incomplete))   # 1.1.3: right after the context line, before anything else
    warning = None if scheduled else q_longchats.compact_warning(cfg, state, ctx)
    if warning:
        lines.append(warning)
    tips_line = "" if scheduled else saving_line(
        cfg, sid, ctx, state.get("fresh") or q_costs.first_context(path), bool(job),
        lambda: sys.modules["savings"].claude_usage(q_settings.entry(), q_settings.read_jsonl(path), cfg))
    if tips_line:
        lines.append(tips_line)
    if budget_note:
        lines.append(budget_note)
    told = None
    if state.get("unquoted") and not scheduled:
        told = state["unquoted"]
        lines.append("The last reply cost ~%s wt, above the threshold (%s wt), and had no quote. Tell the user in ONE "
                     "short line, in their language, then go on with what they asked; from now on, quote first when a "
                     "job looks big. (Said once per chat; Quotient counts the others in its report.)" % (
                         q_quotes.fmt(told.get("wt")), q_quotes.fmt(cfg["threshold"])))
    text = "\n".join(lines) + "\n"
    # what Quotient adds to the chat stays there and is re-read: it is counted as Quotient's own weight
    state = q_settings.load_json(q_settings.session_path(sid), {})
    state["q_chars"] = state.get("q_chars", 0) + len(text)
    state["q_new"] = state.get("q_new", 0) + len(text)
    if closed_told:
        state.pop("last_closed", None)
    if aside_told:
        state["aside_told"] = aside_told
    if incomplete:
        state.pop("quote_incomplete", None)
    if requote:
        state.pop("requote_note", None)
    if told:
        state["unquoted"] = None
        state["unquoted_told"] = told.get("ts") or True
    if warning:
        state["compact_warned"] = True
    elif ctx and q_longchats.compact_target(cfg) and ctx < q_longchats.compact_target(cfg) * 0.5:
        state.pop("compact_warned", None)
    q_settings.save_json(q_settings.session_path(sid), state)
    q_settings.out(text)


def work_per_call(cfg):
    """Weighted tokens of work per model call, learned from finished jobs (median of the last 20), or the
    setting until there are 3 of them. Returns (value, how many jobs it is learned from)."""
    values = [q_costs.work_of(j) / j["calls"] for j in q_learning.finished_jobs()[-20:]
              if j.get("calls") and j.get("chat") is not None and q_costs.work_of(j) > 0]
    if len(values) >= 3:
        return q_learning.median(values), len(values)
    return float(cfg["chat"]["work_per_call"]), 0


def chat_share(cfg, ctx, fresh):
    """What re-reading this chat adds to any job done in it, as a percent of the work: all of it (what the
    chat holds now) and the older conversation alone (what a new chat would not carry)."""
    ctx = max(ctx or 0, fresh or 0)
    wpc, n = work_per_call(cfg)
    read = cfg["weights"]["cache_read"]
    older = max(0, ctx - (fresh or 0))
    return {"context": ctx, "fresh": fresh or 0, "older": older, "per_call": ctx * read, "work_per_call": wpc,
            "learned": n, "percent": 100.0 * ctx * read / wpc if wpc else 0.0,
            "older_percent": 100.0 * older * read / wpc if wpc else 0.0}


def new_chat_allowed(cfg, ctx):
    """With the tips on (tips.level), a new chat is proposed only from tips.new_chat_tokens on; off: as always."""
    tips = cfg.get("tips") or {}
    return not tips.get("level") or (ctx or 0) >= (tips.get("new_chat_tokens") or 0)


def saving_line(cfg, sid, ctx, fresh, job_open, usage_of):
    """Improvements 2, 5, 7, 9: the tips due at this message; '' when off. Never stops a message."""
    if not (cfg.get("tips") or {}).get("level"):
        return ""
    try:
        import savings
        return savings.line(q_settings.entry(), cfg, sid, ctx, fresh, job_open, usage_of)
    except Exception as exc:
        sys.stderr.write("quotient: %s\n" % exc)
        return ""


def chat_hint(cfg, ctx, fresh):
    """One line for Claude: how much re-reading this chat adds to a job, and how much a new chat would save."""
    c = chat_share(cfg, ctx, fresh)
    # 1.1.7: short; how to quote it is in the protocol, and quote-table works the chat part out
    line = "CHAT PART: every call re-reads this chat, ~%s tokens (~%s wt): about +%d%% on a job's work." % (
        q_quotes.fmt(c["context"]), q_quotes.fmt(c["per_call"]), round(c["percent"]))
    if c["older_percent"] >= cfg["chat"]["new_chat_percent"] and new_chat_allowed(cfg, c["context"]):
        line += " ~%s of them older conversation (+%d%%): offer the pace 'new chat'." % (
            q_quotes.fmt(c["older"]), round(c["older_percent"]))
    return line


def close_job(job, cfg=None):
    cfg = cfg or q_settings.config()
    job["finished"] = q_settings.now_iso()
    job.pop("waiting", None)
    job["chat"] = round(job.get("chat") or 0)
    job["older"] = round(job.get("older") or 0)
    if job.get("aside"):
        job["aside"] = round(job["aside"])   # 1.1.1: the replies about something else, in the real cost only
    job["work"] = max(0, round(job["actual"] - job["chat"] - (job.get("aside") or 0)))
    job["ratio"] = round(q_costs.work_of(job) / job["raw_estimate"], 4) if job.get("raw_estimate") else None
    if job.get("packages"):
        # 1.1.6: how far each package's PROGRESS line was from the truth; the margin of the next jobs
        job["progress_check"] = q_timing.progress_check(job["packages"], q_costs.work_of(job))
    job["family"] = q_costs.main_family(job.get("families") or {})
    job["check"] = 1                 # 1.1.1: set against the week (measure_checks)
    job["week_end"] = q_repairs.week_used()
    try:
        job["env"] = q_learning.record_env(cfg)     # 1.1.4: the plugins, MCP servers and hooks around it (names only)
    except Exception:
        pass
    try:
        # 1.1.4: what other chats, installments and Hermes spent while it ran (not in this job, but in the limits)
        sid = str(job.get("session") or "")
        job["elsewhere"] = q_learning.elsewhere_wt(job.get("begin") or q_limits.ts_epoch(job.get("started")), q_limits.ts_epoch(job["finished"]),
                                        set(job.get("chats") or []) | set(job.get("claude_sessions") or []) | {sid},
                                        {sid[7:]} if sid.startswith("hermes:") else ())
    except Exception:
        pass
    for key in ("seconds", "predicted_seconds"):
        if job.get(key) is not None:
            job[key] = round(job[key])
    q_settings.append_jsonl(os.path.join(q_settings.home(), "jobs.jsonl"), job)
    q_sharing.queue_share(job, cfg)
    if job.get("seconds") is not None:
        q_timing.timer_put(cfg, "end", job["seconds"], job.get("predicted_seconds"), job.get("choice"))


# ---------------------------------------------------------------- jobs that move from chat to chat

def chat_jobs_path():
    return os.path.join(q_settings.home(), "chat-jobs.json")


def chat_jobs():
    jobs = q_settings.load_json(chat_jobs_path(), {})
    return jobs if isinstance(jobs, dict) else {}


def note_chat_job(sid, job, transcript=None):
    """Keep a job that is still open in a chat (or chosen to be done in a new chat), so that another chat
    can take it over; None removes it."""
    jobs = chat_jobs()
    if job:
        jobs[sid] = {"job": job, "updated": q_settings.now_iso(), "epoch": round(time.time()), "transcript": transcript}
    elif sid in jobs:
        del jobs[sid]
    else:
        return
    q_settings.save_json(chat_jobs_path(), jobs)


def take_chat_job(prefix, sid):
    """Take the open job of another chat (its id starts with prefix) out of that chat."""
    jobs = chat_jobs()
    for other, entry in sorted(jobs.items()):
        if other == sid or not other.lower().startswith(prefix):
            continue
        job = entry.get("job")
        path = q_settings.session_path(other)
        state = q_settings.load_json(path, None)
        if isinstance(state, dict) and state.get("job"):
            job = state["job"]
            state["job"] = None
            q_settings.save_json(path, state)
        del jobs[other]
        q_settings.save_json(chat_jobs_path(), jobs)
        return job
    return None


def chat_jobs_text(cfg, sid):
    """For a new chat: the jobs left open (or chosen for a new chat) in other chats in the last days."""
    jobs, lines, keep = chat_jobs(), [], {}
    limit = time.time() - cfg["chat"]["open_days"] * 86400
    for other, entry in sorted(jobs.items(), key=lambda kv: kv[1].get("epoch") or 0):
        if (entry.get("epoch") or 0) < limit:
            continue  # forgotten after a few days
        keep[other] = entry
        if other == sid:
            continue
        job = entry.get("job") or {}
        where = q_notices.chat_label(entry["transcript"]) if entry.get("transcript") and os.path.exists(entry["transcript"]) else "another chat"
        if job.get("waiting"):
            lines.append("A JOB WAITS TO BE DONE IN A NEW CHAT (chosen in the chat %s): level '%s', raw estimate %s wt. "
                         "When you start it here, write `JOB: RESUME %s` in the last message of that reply (and `JOB: "
                         "CONTINUES` if it is not finished), so Quotient measures it in this chat." % (
                             where, job.get("choice"), q_quotes.fmt(job.get("raw_estimate")), other[:8]))
        else:
            lines.append("AN OPEN JOB IN ANOTHER CHAT (%s, last worked %s): level '%s', raw estimate %s wt, spent %s wt "
                         "so far. If the user goes on with it here, write `JOB: RESUME %s` in the last message of the "
                         "reply (and `JOB: CONTINUES` if it is not finished); if it is already finished, `JOB: CLOSE %s`; "
                         "if it is abandoned, `JOB: DROP %s`. Do not bring it up unless the user talks about that work." % (
                             where, q_limits.when(entry.get("epoch"), "en"), job.get("choice"), q_quotes.fmt(job.get("raw_estimate")),
                             q_quotes.fmt(job.get("actual")), other[:8], other[:8], other[:8]))
    if keep != jobs:
        q_settings.save_json(chat_jobs_path(), keep)
    return lines


# ---------------------------------------------------------------- Quotient's own weight

def add_injected(sid, text):
    """Remember how much text Quotient put into a chat: it stays there and is re-read at every call."""
    if not sid or not text:
        return
    path = q_settings.session_path(sid)
    state = q_settings.load_json(path, {})
    state["q_chars"] = state.get("q_chars", 0) + len(text)
    state["q_new"] = state.get("q_new", 0) + len(text)
    q_settings.save_json(path, state)


def quotient_action(block, text):
    """Is this tool call something Quotient asked for: reading the plan limits for a LIMITS line, its choice
    window, or one of its commands?"""
    name = str(block.get("name") or "")
    given = block.get("input") or {}
    if name.endswith("get_usage"):
        return bool(q_settings.LIMITS_RE.search(text or ""))
    if name == "AskUserQuestion":
        heads = {str(q.get("header") or "").strip().lower() for q in given.get("questions") or [] if isinstance(q, dict)}
        return bool(heads & q_settings.QUOTIENT_HEADERS)
    if name in ("Bash", "PowerShell"):
        return bool(q_settings.QUOTIENT_CMD_RE.search(str(given.get("command") or "")))
    return False


def quotient_weight(cfg, calls, text, chars, new_chars):
    """What Quotient itself added to one turn, in weighted tokens: its texts (counted from characters: an
    estimate), re-read at every call, and its actions. An action that is the only thing a call asked for
    costs one more call (the one that reads its result); together with other tools it costs about nothing."""
    w = cfg["weights"]
    per = float(cfg.get("chars_per_token") or 3.5)
    write = q_costs.write_weight(calls[0]["usage"], w) if calls else w["cache_write_5m"]
    text_wt = chars / per * w["cache_read"] * len(calls) + new_chars / per * max(0.0, write - w["cache_read"])
    actions, actions_wt = 0, 0.0
    for i, call in enumerate(calls):
        mine = [b for b in call["tools"] if quotient_action(b, text)]
        actions += len(mine)
        if mine and len(mine) == len(call["tools"]) and i + 1 < len(calls):
            actions_wt += q_costs.weigh(calls[i + 1]["usage"], w)
    return round(text_wt), actions, round(actions_wt)


def scheduled_prompt(turn, cfg):
    """Does this turn start with the tag of a scheduled task (not the user)?"""
    prefix = (cfg["rate"].get("prompt_prefix") or "").strip()
    if not prefix or not turn:
        return False
    content = (turn[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return str(content or "").lstrip().startswith(prefix)


def hook_stop():
    data = q_settings.read_stdin_json()
    cfg = q_settings.config()
    w = cfg["weights"]
    sid = data.get("session_id") or "unknown"
    path = data.get("transcript_path") or ""
    last = data.get("last_assistant_message") or ""
    turn, start_ts, text = q_costs.turn_of(path)
    # The last message can reach the file a moment after the hook starts.
    for _ in range(6):
        if not last or last.strip()[:200] in text:
            break
        time.sleep(0.3)
        turn, start_ts, text = q_costs.turn_of(path)
    if last and last.strip()[:200] not in text:
        text += "\n" + last
    entries = turn + q_costs.subagent_entries(path, start_ts)
    total, calls = q_costs.cost_of(entries, w)
    families = q_costs.families_of(entries, w)
    main = q_costs.ordered_calls(turn)
    try:
        bind_from_commands(turn, sid, start_ts)
    except Exception:  # binding a chat must never stop the measurement
        pass

    state = q_settings.load_json(q_settings.session_path(sid), {})
    if not state.get("fresh"):
        state["fresh"] = q_costs.first_context(path)
    fresh = state["fresh"]
    # Another Stop hook can send Claude back to work: then this hook runs again
    # for the same turn, and only the part not yet counted is added.
    seen = state.get("turn") or {}
    repeat = seen.get("start") == start_ts
    now_ep = time.time()
    # the turn's working time ends at its last entry (the hook runs a moment after it)
    stamps = [q_limits.ts_epoch(e.get("timestamp")) for e in turn if e.get("timestamp")]
    now_ep = max(stamps) if stamps else now_ep
    start_ep = q_limits.ts_epoch(start_ts) if start_ts else now_ep
    # The working time of this turn not counted yet: a Stop hook run again for the same turn adds only what came
    # after the last one.
    turn_from = seen.get("end") if repeat and seen.get("end") else start_ep

    def turn_seconds(since):
        return q_timing.claude_active_seconds(turn, max(since, turn_from), now_ep)

    base = seen.get("base") if repeat and seen.get("base") else (q_costs.prompt_tokens(main[0]["usage"]) if main else 0)
    new_chars = seen.get("q_new", 0) if repeat else state.get("q_new", 0)
    q_text, q_actions, q_actions_wt = quotient_weight(cfg, main, text, state.get("q_chars", 0), new_chars)
    now = {"cost": total, "chat": q_costs.chat_part(main, 0, base, w), "older": q_costs.chat_part(main, fresh, base, w),
           "q_text": q_text, "q_actions": q_actions, "q_actions_wt": q_actions_wt}
    if cfg.get("note_web_haiku"):
        # 1.1.8: the web searches of the reply, for the line on their small model at the end of the job
        now["searches"] = sum(1 for c in main for b in c["tools"] if b.get("name") == "WebSearch")
    if repeat and "cost" not in seen:
        seen = dict(seen, cost=seen.get("counted", 0))  # a turn counted by 0.9.1
    delta = {k: max(0, v - ((seen.get(k) or 0) if repeat else 0)) for k, v in now.items()}
    cost = delta["cost"]
    state["turn"] = dict(now, start=start_ts, counted=total, base=base, q_new=new_chars, end=now_ep,
                         job_chat=seen.get("job_chat", 0) if repeat else 0, job_older=seen.get("job_older", 0) if repeat else 0)
    state["q_new"] = 0
    compacting = state.pop("compacting", None)
    if compacting and main:
        q_settings.append_jsonl(q_longchats.compactions_path(), dict(compacting, session=sid, after=q_costs.prompt_tokens(main[0]["usage"])))
    row = {"ts": q_settings.now_iso(), "session": sid, "wt": cost, "calls": calls, "repeat": repeat, "chat": delta["chat"],
           "older": delta["older"],
           "q_text": delta["q_text"], "q_actions": delta["q_actions"], "q_actions_wt": delta["q_actions_wt"]}

    readings = q_limits.parse_limits(text)
    if readings:
        q_limits.record_limits(readings, "claude")
    quote = q_costs.parse_quote(text)
    wtype = q_costs.parse_type(text) if quote else None   # 1.1.4: the type of work, in the QUOTE line
    choice = q_costs.parse_choice(text)
    custom = q_costs.parse_custom(text)          # 1.1.3: a choice of the user's own, with the agent's estimate for it
    pace = q_costs.parse_pace(text)
    move = q_costs.parse_move(text)
    progress = q_costs.parse_progress(text)      # 1.1.4: how much of the job is done, after its first million
    continues = bool(q_settings.CONTINUES_RE.search(text))
    job = state.get("job")
    had_job = bool(job)
    if had_job and not os.environ.get("QUOTIENT_JOB"):
        q_limits.limits_soon(cfg)                 # 1.1.6: a job open: the limits read every minute, in the background
    pending = state.get("pending")
    if (cfg.get("small_quote_line") and pending and not (job or quote or choice) and len(pending.get("options") or {}) == 1
            and (continues or q_settings.JOB_DONE_RE.search(text)) and not os.environ.get("QUOTIENT_JOB")):
        # 1.1.8: a one-line quote gets a plain yes, and on 17/10/2026 one job of 22 came back with only `JOB: CLOSE`, no
        # CHOICE: it went unmeasured. The work done (a JOB line) chooses the quote's one level, done today
        choice = next(iter(pending["options"]))
        pace = pace or "today"
    if q_costs.same_quote(quote, choice, job or state.get("closed")):
        quote = choice = custom = None   # the same QUOTE/CHOICE lines again: the same job
    if quote and not os.environ.get("QUOTIENT_JOB"):
        # 1.1.3: a quote the user saw without the time or the shares of a level is given again at the next message
        gaps = q_quotes.quote_gaps(cfg, quote, text, q_quotes.window_options(turn))
        if gaps:
            state["quote_incomplete"] = gaps
        else:
            state.pop("quote_incomplete", None)
    # With the choice window, the quote and the choice arrive in the same turn.
    same_turn = bool(quote and choice and (choice in quote or custom))

    if move and not job:
        moved = take_chat_job(move[1], sid)
        if moved and move[0] == "resume":
            moved.pop("waiting", None)
            moved.setdefault("chats", []).append(sid)
            moved["fresh"], moved["base"] = fresh, base  # this chat's own start and the job's start in it
            moved.setdefault("started", q_settings.now_iso())
            job = state["job"] = moved
            state["turn"]["job_chat"] = state["turn"]["job_older"] = 0
        elif moved and move[0] == "close" and not moved.get("waiting"):
            close_job(moved, cfg)

    def job_chat_now(j):
        """The chat part of this turn for a job: re-reading, at each call, what the chat held when the job
        started in it; and of that, the older conversation a new chat would not carry."""
        whole = q_costs.chat_part(main, 0, j.get("base") or 0, w)
        older = q_costs.chat_part(main, j.get("fresh") or 0, j.get("base") or 0, w)
        part = max(0, whole - (state["turn"].get("job_chat") or 0))
        j["older"] = (j.get("older") or 0) + max(0, older - (state["turn"].get("job_older") or 0))
        state["turn"]["job_chat"], state["turn"]["job_older"] = whole, older
        return part

    aside = bool(q_settings.ASIDE_RE.search(text)) and not quote
    if job:
        job["actual"] += cost
        if aside:
            # a reply about something else: in the real cost (the limits must add up), not in the work the factor
            # learns from, nor in its steps or its time; the job stays open
            older = job.get("older") or 0
            job_chat_now(job)            # keeps this turn's count of re-reading in step, for a repeated hook
            job["older"] = older
            job["aside"] = (job.get("aside") or 0) + cost
            job["aside_calls"] = (job.get("aside_calls") or 0) + (0 if repeat else calls)
            job["aside_turns"] = (job.get("aside_turns") or 0) + (0 if repeat else 1)
            state.pop("aside_told", None)   # 1.1.7: the next message says again how to answer apart
        else:
            job["chat"] = (job.get("chat") or 0) + job_chat_now(job)
            job["calls"] = (job.get("calls") or 0) + (0 if repeat else calls)
            job["turns"] = (job.get("turns") or 0) + (0 if repeat else 1)
            job["seconds"] = (job.get("seconds") or 0) + turn_seconds(turn_from)
            if progress is not None:
                job["progress"] = progress
        if not repeat:
            q_costs.add_families(job, families)
        if delta.get("searches") and not aside:
            job["searches"] = (job.get("searches") or 0) + delta["searches"]
        if quote or not (continues or aside):
            close_job(job, cfg)
            state["closed"] = {"options": job.get("options"), "choice": job.get("choice")}
            state["last_closed"] = q_timing.closed_note(job, cfg)
            state["job"] = None
            note_chat_job(sid, None)
        else:
            # 1.1.4: past its first million, the job's own pace may make a new quote, shown once at the next message
            work_now = job["actual"] - (job.get("chat") or 0) - (job.get("aside") or 0)
            if not aside and not repeat:
                q_timing.add_package(job, work_now, progress, cfg)   # 1.1.6: a package at each million with a PROGRESS line
            rq = None if aside else q_timing.requote_due(cfg, job, work_now, job.get("progress"))
            if rq:
                job["requote"] = rq
                state["requote_note"] = q_timing.requote_text(cfg, rq, "chat", q_costs.prompt_tokens(main[-1]["usage"]) if main else None,
                                                     cfg.get("lang") or "en")
            note_chat_job(sid, job, path)
            q_timing.timer_put(cfg, "pause", job["seconds"], job.get("predicted_seconds"), job.get("choice"))
    elif choice and (same_turn or pending):
        source = ({"options": quote, "factor": q_learning.learning(cfg, "chat", wtype)["factor"], "factor_mid": q_learning.mid_factor(cfg),
                   "factor_own": q_learning.own_chat_factor(cfg), "quote_cost": 0, "type": wtype} if same_turn else pending)
        state["pending"] = None
        raw = custom[1] if custom else source["options"].get(choice)
        installments = (pace not in (None, "today", "new-chat")) or q_settings.INSTALLMENT_RE.match(choice)
        if raw and choice not in q_settings.DECLINE and not installments:
            job = {
                "started": q_settings.now_iso(), "session": sid, "options": source["options"],
                "choice": choice, "raw_estimate": raw, "factor_used": q_learning.factor_for(cfg, raw, source),
                "quote_cost": source.get("quote_cost", 0), "actual": cost, "turns": 1, "calls": calls,
                "families": dict(families), "fresh": fresh, "base": base, "chat": 0,
                "seconds": 0, "predicted_seconds": q_timing.expected_seconds(cfg, raw, factor=q_learning.factor_for(cfg, raw, source)),
                # 1.1.1: where its cost starts (the start of this turn), and the week then
                "begin": round(start_ep, 1), "week_start": q_repairs.week_used(),
            }
            if custom:
                job["custom"] = True     # 1.1.3: measured against the agent's estimate of the user's own choice
            if source.get("type"):
                job["type"] = source["type"]   # 1.1.4: its type learns its own factor
            if delta.get("searches"):
                job["searches"] = delta["searches"]   # 1.1.8 (note_web_haiku)
            if progress is not None:
                job["progress"] = progress
            if pace == "new-chat":
                # chosen here, done in a new chat: this chat only made the quote. What re-reading this chat
                # would have added is kept, to estimate what the move saved.
                avoided = chat_share(cfg, q_costs.prompt_tokens(main[-1]["usage"]) if main else 0, fresh)["older_percent"]
                job.update(waiting=True, actual=0, turns=0, calls=0, families={}, chats=[],
                           chat_avoided_percent=round(avoided, 1))
                note_chat_job(sid, job, path)
            else:
                job["chat"] = job_chat_now(job)
                job["chats"] = [sid]
                # the work starts after the choice: at `timer start` if the agent ran it in this turn
                by_command = q_timing.timer_started_in(start_ep, now_ep)
                job["seconds"] = turn_seconds(by_command or start_ep)
                if continues:
                    state["job"] = job
                    note_chat_job(sid, job, path)
                    q_timing.timer_put(cfg, "pause", job["seconds"], job["predicted_seconds"], choice, start=not by_command)
                else:
                    close_job(job, cfg)
                    state["closed"] = {"options": job.get("options"), "choice": job.get("choice")}
                    state["last_closed"] = q_timing.closed_note(job, cfg)
    elif pending and not repeat:
        pending["age"] = pending.get("age", 0) + 1
        if pending["age"] > cfg["pending_ttl_turns"]:
            state["pending"] = None

    if quote and not same_turn:
        pending = state.get("pending")
        if repeat and pending and pending.get("options") == quote:
            pending["quote_cost"] = pending.get("quote_cost", 0) + cost
        else:
            state["pending"] = {"ts": q_settings.now_iso(), "options": quote, "factor": q_learning.learning(cfg, "chat", wtype)["factor"],
                                "factor_mid": q_learning.mid_factor(cfg), "factor_own": q_learning.own_chat_factor(cfg),
                                "quote_cost": cost, "age": 0, "type": wtype}

    # A reply above the threshold that nobody quoted: said once per chat at the next message, counted always.
    if not (had_job or job or quote or choice or pending or state.get("pending") or repeat
            or os.environ.get("QUOTIENT_JOB") or scheduled_prompt(turn, cfg)) and cost >= cfg["threshold"]:
        row["unquoted"] = True
        if not state.get("unquoted_told"):
            state["unquoted"] = {"wt": cost, "ts": q_settings.now_iso()}
    q_settings.append_jsonl(os.path.join(q_settings.home(), "turns.jsonl"), row)
    q_settings.save_json(q_settings.session_path(sid), state)


BIND_RE = re.compile(r"""\brate\s+(new|here|apart)\s+(?:"([^"]+)"|'([^']+)'|([\w.-]+))""")


def bind_from_commands(turn, sid, start_ts):
    """The chat a job reports to, when Claude Code did not pass it to the command: a `rate new` (a job
    created in this reply that has no chat yet) or a `rate here` run in this reply binds the job here."""
    if os.environ.get("QUOTIENT_JOB") or not sid or sid == "unknown":
        return
    for e in turn:
        if e.get("type") != "assistant":
            continue
        for block in (e.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            command = str((block.get("input") or {}).get("command") or "")
            if "quotient" not in command.lower() and "launcher" not in command.lower():
                continue
            for m in BIND_RE.finditer(command):
                if "--session" in command[m.end():].split("\n")[0]:
                    continue  # bound to the chat it names
                name = m.group(2) or m.group(3) or m.group(4)
                job = q_settings.load_json(os.path.join(q_rates.rate_dir(name), "job.json"), None)
                if not job:
                    continue
                new_here = not job.get("session") and q_limits.ts_epoch(job.get("created")) >= q_limits.ts_epoch(start_ts) - 60
                if m.group(1) == "here" or new_here:
                    q_rates.bind_chat(name, sid)


# 15/10/2026: an installment started 3 helpers (Agent); at the cap this hook refused everything, to the helpers too, and
# their results (about 120 web searches) were lost before anyone wrote them down. So the last part of the cap is kept
# for saving: there, tools that start new work are refused and these still pass. Past the real cap everything stops,
# as before, except the handoff update.
SAVE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite")
# what the hook says when it refuses: the end of an installment finds them in the transcripts (helpers stopped)
CAP_RE = re.compile(r"Quotient: (?:today's|this) installment is (?:nearly )?(?:used up|out of time)")
HEREDOC_RE = re.compile(r"\A\s*(?:cat\s+>>?\s*[^\s;&|<>$`]+\s+|tee\s+(?:-a\s+)?[^\s;&|<>$`]+\s+|cat\s+)<<-?\s*"
                        r"(['\"]?)(\w+)\1(?:\s*>>?\s*[^\s;&|<>$`]+)?\s*$")


def write_only(command):
    """A shell command that only writes a file from a here-document (`cat > notes.md <<'EOF'` ... `EOF`): it starts no
    new work, so it passes in the part of the cap kept for saving. Anything else in the command and it does not."""
    lines = str(command or "").rstrip().splitlines()
    m = HEREDOC_RE.match(lines[0]) if len(lines) >= 2 else None
    if not m or lines[-1].strip() != m.group(2):
        return False
    body = "\n".join(lines[1:-1])
    return bool(m.group(1)) or ("$(" not in body and "`" not in body)  # an unquoted tag would run $(...) in the body


def main_transcript(path):
    """The chat's own transcript: a helper's tool call may come with its own file, under <chat>/subagents/."""
    folder = os.path.dirname(path or "")
    if os.path.basename(folder) == "subagents":
        return os.path.dirname(folder) + ".jsonl"
    return path


def pieces_path(name):
    return os.path.join(q_rates.rate_dir(name), "pieces.json")


def piece_check(name, data, spent, cap, cfg):
    """1.2.1 (the user's request): an installment measured in pieces. Each tool call records the handoff's PROGRESS
    line when it changed (a piece: wt spent in this run, progress); the agent updates it with the handoff after each
    step (RATE_PROMPT). Never refuses a call: in the real test of 19/10/2026 a paused call at each quarter of a 100k
    cap (the first one already passed by the session's start, ~45k) ate the cap and nothing was saved. Returns False."""
    share = float(cfg.get("piece_share") or 0)
    sid = str(data.get("session_id") or "")
    if share <= 0 or not sid or not cap:
        return False
    path = pieces_path(name)
    state = q_settings.load_json(path, {})
    state = state if isinstance(state, dict) else {}
    mine = state.get(sid) or {"pieces": [], "asked": 0}
    handoff = os.path.join(q_rates.rate_dir(name), "HANDOFF.md")
    try:
        progress = q_costs.parse_progress(open(handoff, encoding="utf-8").read())
    except OSError:
        progress = None
    changed = False
    if progress is not None and 0 < progress < 100 and (not mine["pieces"] or mine["pieces"][-1]["progress"] != progress):
        mine["pieces"].append({"wt": round(spent), "progress": progress})
        changed = True
    if changed:
        state[sid] = mine
        q_settings.save_json(path, state)
    return False


def run_pieces(name, sid):
    """1.2.0: the pieces an installment run recorded (piece_check)."""
    return ((q_settings.load_json(pieces_path(name), {}) or {}).get(str(sid or "")) or {}).get("pieces") or []


def step_weight(usage, cfg, first=False):
    """1.2.2: the cost of one step, to size the reserve that closes an installment. The first call of a new session also
    writes the whole start to the cache (about 100k wt), once: no later step pays it again, so with rate.start_fixed it
    counts as if its prompt were read from the cache (19/10/2026: counted whole, it made a 155k installment refuse its
    first read)."""
    if first and (cfg.get("rate") or {}).get("start_fixed"):
        w = cfg["weights"]
        return q_costs.prompt_tokens(usage) * w["cache_read"] + (usage.get("output_tokens") or 0) * w["output"]
    return q_costs.weigh(usage, cfg["weights"])


def hook_pretool():
    """Inside an installment run: in the last part of the day's cap only saving passes (Write, Edit, a here-document);
    when the cap is spent, only the handoff update."""
    name = os.environ.get("QUOTIENT_JOB")
    if not name:
        return
    data = q_settings.read_stdin_json()
    cfg = q_settings.config()
    job = q_settings.load_json(os.path.join(q_rates.rate_dir(name), "job.json"), None)
    if not job:
        return
    path = main_transcript(data.get("transcript_path") or "")
    entries = q_settings.read_jsonl(path)
    spent, _ = q_costs.cost_of(entries + q_costs.subagent_entries(path, None), cfg["weights"])
    cap = int(os.environ.get("QUOTIENT_CAP") or job["daily_cap"])
    if piece_check(name, data, spent, cap, cfg):
        return
    if cfg["rate"].get("loop_stop"):       # improvement 11: the same command or error again and again
        import savings
        reason = savings.loop_check(q_settings.entry(), name, data, entries, cfg)
        if reason:
            q_settings.out(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                   "permissionDecisionReason": reason}}))
            return
    # 06/10/2026: three installments ended 9%, 23% and 9% over the cap, because the check comes before a tool
    # call and the calls after it (updating the handoff, the last answer) still cost. So new work stops
    # when what is spent plus the next steps (the size of the latest calls) would reach the cap.
    recent = [step_weight(c["usage"], cfg, i == 0) for i, c in enumerate(q_costs.ordered_calls(entries))][-3:]
    reserve = min(cfg["rate"]["reserve_calls"] * max(recent or [0]), cap * cfg["rate"]["reserve_max_share"])
    saving = cap * (1 - float(cfg["rate"].get("save_percent") or 0) / 100.0)
    near = spent + reserve >= min(cap, saving)
    # 31/10/2026: an installment stopped by the timeout left no report, so the last minutes before the stop are for saving
    stop_at = float(os.environ.get("QUOTIENT_STOP_AT") or 0)
    close = float(cfg["rate"].get("close_minutes") or 0) * 60
    if not near and not (stop_at and close and time.time() >= stop_at - close):
        return
    handoff = os.path.normcase(os.path.abspath(os.path.join(q_rates.rate_dir(name), "HANDOFF.md")))
    tool = data.get("tool_name") or ""
    given = data.get("tool_input") or {}
    target = given.get("file_path") or given.get("notebook_path") or ""
    if tool in ("Write", "Edit", "MultiEdit", "Read") and target and os.path.normcase(os.path.abspath(target)) == handoff:
        return
    if spent + reserve < cap:
        if tool in SAVE_TOOLS or (tool == "Bash" and write_only(given.get("command"))):
            return
        notes = os.path.join(q_rates.rate_dir(name), "notes")
        why = ("nearly used up (%s of %s wt spent; what is left is kept for saving)" % (q_quotes.fmt(spent), q_quotes.fmt(cap))
               if near else "nearly out of time (Quotient stops it in %d minutes)" % max(0, round((stop_at - time.time()) / 60)))
        reason = ("Quotient: this installment is %s. "
                  "No new work: no helpers, searches, fetches, reads or commands. Save NOW, with Write or Edit, what you "
                  "have found and not written yet: a helper (subagent) into a file of its own in %s, then it stops and "
                  "says where; the installment into %s (what is done, what remains, where to resume, the PROGRESS line), "
                  "then it stops." % (why, notes, handoff))
    else:
        reason = ("Quotient: today's installment is used up (%s of %s wt spent; the steps to close it take about %s). "
                  "Do not start new work. Update %s now (what is done, what remains, where to resume, and the PROGRESS "
                  "line), then stop." % (q_quotes.fmt(spent), q_quotes.fmt(cap), q_quotes.fmt(reserve), handoff))
    q_settings.out(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}))
