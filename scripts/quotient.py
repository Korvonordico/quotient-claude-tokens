#!/usr/bin/env python3
"""Quotient: a cost estimate before a big AI job, the real cost after it,
and a correction learned from the difference.

Part of a Claude Code plugin. Standard library only (Python 3.8+).

Commands:
  hook-session         SessionStart hook: the quote protocol, once per session
  hook-prompt          UserPromptSubmit hook (reads the hook JSON on stdin)
  hook-stop            Stop hook
  hook-pretool         PreToolUse hook, used only inside installment runs
  commands             the list of commands, with what each one does
  report               estimates, real costs, plan limits, and how the error is changing
  statusline           status line command: records and shows the plan limits
  setup-statusline     sets that status line up (--write to put it in settings.json)
  config [KEY [VALUE]] show or change the settings
  export               the exact lines that sharing sends (numbers only)
  share [status|on|off] the shared average: what is sent, and turning it on or off
  prices [update]    the price table of the Claude models; update downloads it again
  plan-changed [--undo] [--plan P] you changed subscription: learn the size of the limit again from now
  telemetry [status|on|off] [--write] Claude Code's own telemetry as a second measure
  rate ...           the work in installments (see `rate --help`)
"""

import argparse
import csv
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import html
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# The modules first, in the order that loads each one whole, then each name again: `q.<name>` keeps working.
from quotient_lib import (  # noqa: F401
    q_settings, q_costs, q_learning, q_timing, q_sharing, q_quotes, q_notices, q_longchats, q_hooks, q_limits, q_repairs, q_weeks, q_reports, q_pages, q_prices, q_rates, q_tasks, q_runs, q_schedules,
)
from quotient_lib.q_settings import (  # noqa: F401
    APART_RE, ASIDE_RE, CHOICE_AMOUNT_RE, CHOICE_KEYS, CHOICE_RE, CONTINUES_RE, DECLINE, DEFAULTS, DONE_RE,
    INSTALLMENT_RE, JOB_DONE_RE, LEVEL_NAMES, LEVEL_WORDS, LIMITS_RE, MIDNIGHT_RE, MOVES, MOVE_RE, NEW_CHAT_RE,
    OPTIONS, OPTION_RE, PACE_RE, PERCENT_TOKEN_RE, PLAN_AT_RE, PLAN_DAILY_RE, PLAN_DAYS, PLAN_DAYS_RE, PROGRESS_RE,
    QUOTE_KEYS, QUOTE_RE, QUOTIENT_CMD_RE, QUOTIENT_HEADERS, TIME_TOKEN_RE, TODAY_RE, TYPE_RE, TYPE_WORDS, VERSION,
    WORK_TYPES, append_jsonl, config, home, load_json, merge, now_iso, out, plugin_options, read_jsonl,
    read_stdin_json, save_json, save_settings, session_path, sync_plugin_options, to_bool, ENTRY, ENTRY_FILE, entry,
    set_entry,
)
from quotient_lib.q_costs import (  # noqa: F401
    FAMILY_NAMES, RATE_SIGN, add_families, calls_of, chat_part, claude_links, claude_links_path, claude_run_cost,
    claude_runs_of, context_size, cost_of, families_of, family_of, first_context, first_prompt, is_turn_start,
    main_family, ordered_calls, parse_amount, parse_choice, parse_custom, parse_move, parse_pace, parse_plan,
    parse_progress, parse_quote, parse_type, plan_amount, prompt_tokens, record_claude_link, same_quote, span_cost,
    subagent_entries, turn_of, weigh, work_of, work_type, write_weight,
)
from quotient_lib.q_learning import (  # noqa: F401
    DAY_RE, FACTOR_MAX, FACTOR_MIN, SCRIPT_RE, average_path, backfill_chat, band_factor, blend_end,
    bundled_average_path, chat_factor, chat_jobs_measured, chat_origin, chat_steps, check_average, claude_dir,
    claude_runs_text, clean_plan, clean_stats, elsewhere_wt, env_alert, env_change_epochs, env_changes_path,
    env_path, env_periods, env_sig, env_snapshot, factor_for, factor_from, finished_jobs, hermes_env, hook_names,
    is_clean, job_type, kind_of, learning, median, mid_band, mid_factor, mid_text, miss, own_chat_factor,
    plan_average, plugin_root, record_env, same_origin, shared_average, shared_factor, shared_jobs, shared_mix,
    shared_path, shared_prior, shared_weight, steps_per_million, teaches, too_fast, type_factors, yaml_block,
    yaml_keys, yaml_list,
)
from quotient_lib.q_timing import (  # noqa: F401
    ASK_TOOLS, add_package, backfill_time, claude_active_seconds, closed_note, cmd_timer, estimate_words,
    expected_seconds, fmt_duration, job_time_from_logs, margin_words, minutes_per_million, pace_note,
    package_estimate, package_lines, piece_size, progress_check, progress_error, requote_due, requote_text,
    run_packages, time_misses, time_text, timer_path, timer_put, timer_seconds, timer_started_in, timer_state,
    timer_window, timer_window_on, timer_window_open, web_note,
)
from quotient_lib.q_sharing import (  # noqa: F401
    NOTICE, OUTBOX_MAX, PER_POINT_5H_MAX, PER_POINT_5H_MIN, PER_POINT_MAX, PER_POINT_MIN, PLANS, SHARE_FIELDS,
    SHARE_OLDER, SHARE_OPTIONAL, allowed_url, fetch_average, flush_share, http, learned_per_point,
    learned_per_point_5h, outbox_path, plan_status, plan_word, queue_share, round3, share_active, share_enabled,
    share_row, share_status, store, write_outbox,
)
from quotient_lib.q_quotes import (  # noqa: F401
    WRITING_MARGIN, addition_hint, additions_rule, calibration, chat_context, chat_steps_note, cmd_quote_table, fmt,
    fmt_miss, incomplete_line, level_count, level_label, level_sizes, pace_options, protocol, quote_gaps,
    quote_numbers, quote_table, run_cmd, small_quote, task_file_hint, window_options, writing_notes, writing_raw,
    writing_rule,
)
from quotient_lib.q_notices import (  # noqa: F401
    NOTICES_MAX, NOTICE_GAP, chat_label, handoff_text, installment_seconds, notice_line, rate_events, rate_requote,
    remaining, report_lines, report_state, run_seconds,
)
from quotient_lib.q_longchats import (  # noqa: F401
    COMPACT_MAX, COMPACT_MIN, COMPACT_MODES, apply_compact, claude_settings_path, cmd_setup, compact_target,
    compact_warning, compaction_summary, compactions_path, hook_claude_link, hook_precompact, recommended_compact,
    save_json_pretty, setup_instructions,
)
from quotient_lib.q_hooks import (  # noqa: F401
    BIND_RE, CAP_RE, HEREDOC_RE, SAVE_TOOLS, add_injected, bind_from_commands, chat_hint, chat_jobs, chat_jobs_path,
    chat_jobs_text, chat_share, close_job, hook_pretool, hook_prompt, hook_session, hook_stop, main_transcript,
    new_chat_allowed, note_chat_job, piece_check, pieces_path, quotient_action, quotient_weight, run_pieces,
    saving_line, scheduled_prompt, step_weight, take_chat_job, work_per_call, write_only,
)
from quotient_lib.q_limits import (  # noqa: F401
    WINDOWS, capacity, cfg_limits, cmd_plan_changed, five_capacity, latest_limits, left_text, limits_due,
    limits_every, limits_line, limits_live, limits_path, limits_reader, limits_soon, measured_turns, parse_limits,
    plan_alert, plan_capacity, plan_changes_path, plan_detect, plan_since, plan_state, record_limits, refresh_limits,
    to_epoch, ts_epoch, week_capacity, week_source, weeks, when, window_ratio, window_rows, window_sizes,
)
from quotient_lib.q_repairs import (  # noqa: F401
    chat_again, check_alert, check_key, check_line, check_spans, checks_path, checks_summary, cmd_fix,
    compression_problems, compressions_in, excluded_path, factors_now, fix_alert, fix_backup, fix_find, fix_log,
    fix_problems, how_text, job_key, jobs_path, joined, measure_checks, rechat, setup_statusline, split_jobs,
    statusline, week_used, write_rows,
)
from quotient_lib.q_weeks import (  # noqa: F401
    AUTH_EVERY, COMMANDS, auth_alert, cmd_commands, open_jobs, pace_alert, rate_pause, rate_resume, rate_set,
    rate_week, set_status, week_alert, week_pace, week_plan, week_room, week_text,
)
from quotient_lib.q_reports import (  # noqa: F401
    HERMES_UNSEEN, TEXT, cost_lines, hermes_busy, hermes_cost, hermes_lines, implied_prices, ratio_lines,
    record_statusline_cost, report, report_v114, report_v115, run_rows, savings, session_usd, share_of, solve3,
    statusline_cost_path, statusline_jobs, usd_per_wt, weight_summary,
)
from quotient_lib.q_pages import (  # noqa: F401
    PAGE_SCRIPT, PAGE_STYLE, PAGE_TEXT, bar_path, cost_chart, esc, export, installment_jobs, miss_chart, num,
    open_file, report_html, weeks_chart,
)
from quotient_lib.q_prices import (  # noqa: F401
    PRICES_URL, PRICE_DATE_RE, PRICE_FIELDS, cmd_config, cmd_prices, cmd_share, filter_prices, model_price,
    prices_path, prices_update,
)
from quotient_lib.q_rates import (  # noqa: F401
    LOGIN_ERROR, RATE_PROMPT, RUN_PAGE_STYLE, TOAST_APP, TOAST_SCRIPT, amount, bind_chat, cap_floor, chat_id,
    find_claude, find_transcript, installment_overhead, installment_runs, installment_start_cost, installment_toast,
    md_to_html, next_run, notify, once_task, page_uri, percent, rate_dir, rate_templates, run_start_cost, task_name,
    templates, templates_dir, write_report_page,
)
from quotient_lib.q_tasks import (  # noqa: F401
    IMPORT_RE, TASK_CHECK_RE, TASK_FILE_QUESTIONS, TASK_FILE_RE, TASK_FILE_TEXT, TASK_GOAL_RE, TASK_SPOT_RE,
    cmd_task_file, external_imports_approved, rules_files, task_check, task_example, task_file_ask, task_file_text,
    task_read_line, task_spot,
)
from quotient_lib.q_runs import (  # noqa: F401
    after_installment, bind_new_apart, capped, helper_work, rate_apart, rate_here, rate_new, rate_run, rate_status,
    refused_by_cap, run_installment, save_helpers_note, start_detached,
)
from quotient_lib.q_schedules import (  # noqa: F401
    check_time, found_asleep, go_to_sleep, idle_seconds, job_time, keep_awake, launcher, live_check, load_text,
    next_time, once_tasks, rate_after, rate_check, rate_once, rate_schedule, rate_stop, refresh_launchers, schedule,
    statusline_launcher, task_xml, unschedule, wake_allowed, woken_recently,
)

q_settings.set_entry(sys.modules[__name__])


# ---------------------------------------------------------------- main

def main(argv=None):
    parser = argparse.ArgumentParser(prog="quotient", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=q_settings.VERSION)
    sub = parser.add_subparsers(dest="cmd")
    for name in ("hook-session", "hook-prompt", "hook-stop", "hook-pretool", "hook-precompact", "export", "statusline",
                 "commands", "claude-link"):
        sub.add_parser(name)
    p = sub.add_parser("report", help="estimates against real costs, Quotient's own weight, the plan limits")
    p.add_argument("--html", action="store_true", help="a page with charts, opened in the browser")
    p.add_argument("--no-open", action="store_true", help="with --html: write the page, do not open it")
    p = sub.add_parser("share", help="the shared average: what is sent, and turning sharing on or off")
    p.add_argument("what", nargs="?", choices=("", "status", "on", "off", "send"), default="status")
    p.add_argument("--into", help="(maintainers) add your finished jobs, numbers only, to a JSON-lines file")
    p = sub.add_parser("setup", help="set Quotient up: threshold, weekly reserve, language, what the PC does after installments")
    p.add_argument("--threshold", type=int)
    p.add_argument("--reserve", type=int)
    p.add_argument("--lang", choices=("it", "en"))
    p.add_argument("--after", choices=("nothing", "sleep", "hibernate"))
    p.add_argument("--wake", choices=("yes", "no"), help="may scheduled installments wake the PC")
    p.add_argument("--share", choices=("yes", "no"), help="share anonymous numbers of finished jobs")
    p.add_argument("--compact", help="long chats: keep, auto (the size Quotient recommends), or a size in tokens")
    p.add_argument("--plan", help="your subscription: pro, max5, max20, other, or unknown (I don't know)")
    p.add_argument("--hermes-copy", dest="hermes_copy", choices=("yes", "no"),
                   help="Hermes: save the whole chat to a file before each automatic summary")
    p = sub.add_parser("setup-statusline", help="show the plan limits in the status line and record them")
    p.add_argument("--write", action="store_true", help="write the setting in ~/.claude/settings.json")
    p.add_argument("--force", action="store_true", help="replace a status line that is already set")
    sub.add_parser("hermes", help="Hermes Agent chats: same Claude login, same limits")
    sub.add_parser("hermes-hook", help="(Hermes shell hook) pre_llm_call / post_llm_call, JSON on stdin")
    sub.add_parser("tick", help="read Hermes' counters and the plan limits now (for a scheduled task, every few minutes)")
    p = sub.add_parser("timer", help="the stopwatch of a quoted job: start it when the work begins, show it, or hide it")
    p.add_argument("what", nargs="?", choices=("start", "show", "stop"), default="show")
    p.add_argument("--raw", type=int, help="raw estimate of the chosen level, for the expected time")
    p.add_argument("--level", help="the chosen level, shown in the window")
    p.add_argument("--kind", choices=("chat", "rate"), default="chat")
    p = sub.add_parser("quote-table", help="the quote, worked out: every number of each level and the pace options")
    p.add_argument("--raw", nargs="+", required=True, help="raw estimates by level: essential=<n> good=<n> max=<n>")
    p.add_argument("--kind", choices=("chat", "rate"), default="chat", help="rate: the job is surely in installments")
    p.add_argument("--lang", choices=("it", "en"), help="the user's language (default: the setting)")
    p.add_argument("--context", type=int, help="tokens each step re-reads now (Hermes: the CHAT PART line)")
    p.add_argument("--new-chat", action="store_true", help="offer 'in a new chat' among the pace options")
    p.add_argument("--type", help="the type of work: code, writing, research or other (each learns its own factor)")
    p.add_argument("--words", type=int, help="1.1.8: the final words of a text (biggest level), for the rule for texts")
    p = sub.add_parser("fix", help="the guided repair of the measures: list, merge <a> <b>, exclude <job>, chat <job>, undo")
    p.add_argument("what", nargs="?", choices=("list", "merge", "exclude", "chat", "undo"), default="list")
    p.add_argument("jobs", nargs="*", help="jobs: their number in the report or their key (see fix list)")
    p.add_argument("--why", help="with exclude: why the measure is wrong (kept with the job)")
    sub.add_parser("timer-window", help="(internal) the stopwatch window")
    sub.add_parser("backfill-time", help="work out the time of jobs measured before 1.1.0 from the logs")
    p = sub.add_parser("plan-changed", help="you changed subscription: learn the size of the limit again from now")
    p.add_argument("--undo", action="store_true", help="take the last change of plan back")
    p.add_argument("--plan", help="the new subscription: pro, max5, max20, other, or unknown")
    p = sub.add_parser("telemetry", help="Claude Code's own telemetry as a second measure: status, on, off")
    p.add_argument("what", nargs="?", choices=("status", "on", "off", "serve"), default="status")
    p.add_argument("--write", action="store_true", help="with on/off: change ~/.claude/settings.json (a copy first)")
    p.add_argument("--port", type=int, help="the local port of the receiver (default: the setting, 4318)")
    p = sub.add_parser("limits-read", help="(internal) one reading of the plan limits, run in the background")
    p.add_argument("--every", type=float, help="not if read or tried within these seconds (default: limits.job_every)")
    p = sub.add_parser("prices", help="the price table of the Claude models; `prices update` downloads it again")
    p.add_argument("action", nargs="?", choices=["update"])
    p = sub.add_parser("budget", help="the budget of the normal chats against the plan's limits")
    p = sub.add_parser("tips", help="the tips for saving tokens, most useful first: put one off (later) or drop it")
    p.add_argument("what", nargs="?", choices=("list", "later", "drop", "back"), default="list")
    p.add_argument("id", nargs="?", help="the tip, as the list names it")
    p.add_argument("--days", type=float, help="with later: for how many days (default: tips.later_days)")
    p = sub.add_parser("task-file", help="write the task file of a job apart or in installments, from a few answers")
    p.add_argument("--out", help="the file to write (default: print it)")
    p.add_argument("--dir", default=".", help="the job's working folder; the files named are relative to it")
    p.add_argument("--what", help="what the job must do")
    p.add_argument("--why", help="why it is needed")
    p.add_argument("--read", action="append", help="a file it must read, or file:from-to (repeat it)")
    p.add_argument("--example", action="append", help="code to imitate, file:from-to, copied into the file (repeat it)")
    p.add_argument("--check", action="append", help="a command it checks itself with (repeat it)")
    p.add_argument("--goal", help="when it is finished")
    p.add_argument("--lang", choices=("it", "en"), help="the language of the file (default: the setting)")
    p.add_argument("--no-ask", action="store_true", help="never ask, even in a terminal")
    p.add_argument("--force", action="store_true", help="overwrite the file if it exists")
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
    p.add_argument("--pace", help="the pace in the user's words: days, amount a day, time ('5 giorni alle 2:00')")
    p.add_argument("--at", help="the time of the installments, HH:MM (rate once and rate schedule use it)")
    p.add_argument("--model")
    p.add_argument("--after", choices=("nothing", "sleep", "hibernate"),
                   help="what the PC does after each installment, if nobody is using it (default: the setting)")
    p.add_argument("--template", help="a ready-made way of working: book, research, code-review (see rate templates)")
    p.add_argument("--type", help="the type of work: code, writing, research or other (each learns its own factor)")
    rsub.add_parser("templates", help="the ready-made ways of working for long jobs")
    p = rsub.add_parser("run", help="run one installment now")
    p.add_argument("name")
    p.add_argument("--force", action="store_true", help="run even if one already ran today")
    p = rsub.add_parser("status")
    p.add_argument("name", nargs="?")
    p = rsub.add_parser("schedule", help="run an installment every day at a time (wakes the PC)")
    p.add_argument("name")
    p.add_argument("--time", help="HH:MM (default: the job's time, else 03:00)")
    p.add_argument("--force", action="store_true", help="run even if another installment ran the same day")
    p.add_argument("--no-wake", action="store_true", help="do not wake the PC")
    p = rsub.add_parser("once", help="run one installment at a time (today, or tomorrow if past)")
    p.add_argument("name")
    p.add_argument("--time", help="HH:MM (default: the job's time)")
    p.add_argument("--no-wake", action="store_true", help="do not wake the PC")
    p = rsub.add_parser("after", help="what the PC does after each installment")
    p.add_argument("name")
    p.add_argument("what", choices=("nothing", "sleep", "hibernate"))
    p = rsub.add_parser("here", help="each installment's report comes to this chat")
    p.add_argument("name")
    p.add_argument("--session", help="the chat (Claude Code session id), when run from a terminal")
    p = rsub.add_parser("apart", help="do a job apart, now: one installment in a separate session, started at once")
    p.add_argument("name")
    p.add_argument("--dir", default=".", help="folder the work happens in")
    p.add_argument("--task", help="what the whole job is")
    p.add_argument("--task-file", help="file holding what the whole job is")
    p.add_argument("--quote", type=int, required=True, help="raw estimate of the chosen level, in weighted tokens")
    p.add_argument("--model")
    p.add_argument("--template", help="a ready-made way of working: book, research, code-review (see rate templates)")
    p.add_argument("--session", help="the chat its report comes back to, when run from a terminal")
    p.add_argument("--type", help="the type of work: code, writing, research or other (each learns its own factor)")
    p = rsub.add_parser("check", help="can a scheduled installment wake this PC, and is Claude Code logged in?")
    p.add_argument("--live", action="store_true", help="also one real call with the smallest model (a few cents)")
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
    hooks = {"hook-session": q_hooks.hook_session, "hook-prompt": q_hooks.hook_prompt,
             "hook-stop": q_hooks.hook_stop, "hook-pretool": q_hooks.hook_pretool, "hook-precompact": q_longchats.hook_precompact,
             "claude-link": q_longchats.hook_claude_link}
    if args.cmd in hooks and os.environ.get("QUOTIENT_CHECK"):
        return  # the live test of `rate check` is not a chat: nothing to measure or to tell
    if args.cmd in hooks:
        try:
            hooks[args.cmd]()
        except Exception as exc:  # a broken hook must never block the user's work
            sys.stderr.write("quotient: %s\n" % exc)
        return
    if args.cmd == "statusline":
        try:
            q_repairs.statusline()
        except Exception as exc:  # the status line must never break
            q_settings.out("Quotient\n")
            sys.stderr.write("quotient: %s\n" % exc)
    elif args.cmd == "setup-statusline":
        q_repairs.setup_statusline(args)
    elif args.cmd == "setup":
        q_longchats.cmd_setup(args)
    elif args.cmd == "share":
        q_prices.cmd_share(args)
    elif args.cmd == "prices":
        q_prices.cmd_prices(args)
    elif args.cmd == "commands":
        q_weeks.cmd_commands()
    elif args.cmd == "hermes-hook":
        import hermes_hooks
        hermes_hooks.main(sys.modules[__name__])
    elif args.cmd == "tick":
        cfg = q_settings.config()
        q_limits.measured_turns(cfg)
        snap = q_limits.refresh_limits(cfg, force=True)
        q_settings.out(json.dumps({"limits": snap, "hermes": cfg.get("hermes", True)}) + "\n")
    elif args.cmd == "timer":
        q_timing.cmd_timer(args)
    elif args.cmd == "quote-table":
        q_quotes.cmd_quote_table(args)
    elif args.cmd == "fix":
        q_repairs.cmd_fix(args)
    elif args.cmd == "timer-window":
        q_timing.timer_window()
    elif args.cmd == "backfill-time":
        q_settings.out("Jobs given a time from the logs: %d\n" % q_timing.backfill_time())
    elif args.cmd == "plan-changed":
        q_limits.cmd_plan_changed(args)
    elif args.cmd == "telemetry":
        import telemetry
        telemetry.cmd(sys.modules[__name__], args)
    elif args.cmd == "limits-read":
        try:
            cfg = q_settings.config()
            q_limits.refresh_limits(cfg, every=q_limits.limits_every(cfg, busy=True) if args.every is None else args.every)
        except Exception as exc:  # a reading in the background must never show an error
            sys.stderr.write("quotient: %s\n" % exc)
    elif args.cmd == "hermes":
        cfg = q_settings.config()
        t = q_reports.TEXT.get(cfg.get("lang"), q_reports.TEXT["en"])
        q_settings.out("\n".join(q_reports.hermes_lines(cfg, t, cfg.get("lang")) or [t["hermes_none"]]).strip() + "\n")
    elif args.cmd == "report":
        q_reports.report(args)
    elif args.cmd == "export":
        q_pages.export()
    elif args.cmd == "config":
        q_prices.cmd_config(args)
    elif args.cmd == "task-file":
        q_tasks.cmd_task_file(args)
    elif args.cmd == "budget":
        import savings
        savings.cmd_budget(sys.modules[__name__])
    elif args.cmd == "tips":
        import savings
        savings.cmd(sys.modules[__name__], args)
    elif args.cmd == "rate":
        actions = {"new": q_runs.rate_new, "apart": q_runs.rate_apart, "run": q_runs.rate_run, "status": q_runs.rate_status, "schedule": q_schedules.rate_schedule,
                   "once": q_schedules.rate_once, "stop": q_schedules.rate_stop, "after": q_schedules.rate_after, "here": q_runs.rate_here, "check": q_schedules.rate_check,
                   "week": q_weeks.rate_week, "pause": q_weeks.rate_pause, "resume": q_weeks.rate_resume, "set": q_weeks.rate_set,
                   "templates": q_rates.rate_templates}
        if args.rate_cmd not in actions:
            rate.print_help()
            return
        actions[args.rate_cmd](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
