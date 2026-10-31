"""The settings and their defaults, the patterns of the machine lines, and reading and writing the files in ~/.quotient. It needs no other module of Quotient, so it loads first."""

import json
import os
import re
import sys
from datetime import datetime, timezone


# The file Quotient is started from (hooks, launchers and detached runs call it again), and the module it loaded: the
# helpers beside this package (hermes_hooks, savings, telemetry) receive that module as `q`.
ENTRY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quotient.py")
ENTRY = {}


def set_entry(module):
    ENTRY["module"] = module


def entry():
    return ENTRY["module"]


VERSION = "1.2.8"

DEFAULTS = {
    # False until the user has set Quotient up (first-use window, /token-quotient:setup, or Claude Code's plugin settings).
    "configured": False,
    # Below this many weighted tokens no quote is asked for.
    "threshold": 300000,
    # 1.1.3: how many levels a quote offers, by the corrected estimate of its biggest level: up to `one` wt one level,
    # up to `two` two, up to `three` three, above that four (the window shows 4 at most, and adds a free field by itself).
    # The installment plans offered grow with them: 2 or 3 days for a small job, 3 or 5, then 3, 5 or 7 days.
    "levels": {
        "one": 300000,
        "two": 1000000,
        "three": 5000000,
    },
    # Weights relative to one input token: the ratios of Anthropic's API prices.
    "weights": {
        "input": 1.0,
        "cache_write_5m": 1.25,
        "cache_write_1h": 2.0,
        "cache_read": 0.1,
        "output": 5.0,
    },
    # Quotes are for the WORK. Re-reading, at every model call, what the chat already held when the job
    # started (system, tools, rules, older conversation: the "chat part") is measured apart and added on top.
    "chat": {
        # Weighted tokens of work per model call, until Quotient has learned it from finished jobs.
        "work_per_call": 30000,
        # Tokens an installment starts with (it runs in a new chat), until Quotient has measured it.
        "installment_start": 50000,
        # From this share of OLDER conversation on (percent of the work), the window offers a new chat.
        "new_chat_percent": 25,
        # An open job in another chat is offered for this many days, then forgotten.
        "open_days": 7,
        # Hermes summarizes a long chat by itself (its own "compression" setting, which Quotient never changes).
        # None = not asked yet; True = each time it does, Quotient first writes the whole chat to a file in
        # ~/.quotient/chats (nothing of it is lost); False = it just summarizes. Set with: setup --hermes-copy yes|no
        "hermes_copy": None,
        # 1.2.6: a pause longer than the cache keeps the chat (Anthropic's documented lifetimes: 5 minutes, 1 hour for
        # the 1-hour cache) makes the next message write the whole chat again at the write price (1.25 or 2) instead of
        # reading it at 0.1. cache_warn 1: Hermes's line tells the user, when each step re-reads at least
        # cache_warn_min tokens. 0 (the default): no line.
        "cache_warn": 0,
        "cache_warn_min": 100000,
        "cache_life_5m": 300,
        "cache_life_1h": 3600,
        # Improvement 4, off by default, measured on the author's jobs (walk-forward; a hint with so few jobs).
        # steps_history 1: the chat part of a quote counts the steps of the measured jobs of the same origin (Hermes or
        # Claude Code) and the same size (steps_bands, in raw wt), their median, instead of a share of the work: a small
        # fix with its release took 24 steps where the quote counted 7. On 21 jobs, work + chat part: typical miss 111%
        # -> 65%, lean x1.54 -> x1.04. Under steps_min_jobs such jobs: at least steps_start steps, and the quote says it
        # is a prudent estimate.
        # own_factor_mix 1: the factor of a job done in a chat is halfway (geometric mean) between the usual one and the
        # median of ALL the recent chat jobs of the same origin, whatever their size and whether the user wrote during
        # them: the usual one learns from clean jobs only, cheaper than most. On 40 jobs, work alone: typical miss 126% ->
        # 74%, lean x1.91 -> x1.28, within 50% 10 -> 15; on the 21 with their chat part about the same (65% -> 62%).
        "steps_history": 0,
        "steps_bands": [500000, 1000000],
        "steps_min_jobs": 3,
        "steps_start": 15,
        "own_factor_mix": 0,
    },
    # Long chats. "keep" (the default): Quotient leaves Claude Code's compaction as it is and, when a chat has
    # grown long, offers a new chat. "auto": the chat compacts itself at the size Quotient recommends from your
    # numbers. "custom": at the size you choose ("at", in tokens). Only for auto or custom does Quotient write
    # autoCompactWindow in ~/.claude/settings.json, and it takes its own value back when you return to keep.
    "compact": {
        "mode": "keep",
        "at": 0,
        # When the chat reaches this share of the size, Claude is told once to save what must not be lost.
        "warn_percent": 85,
    },
    # Characters per token, to turn the text Quotient adds to a chat into tokens (an estimate).
    "chars_per_token": 3.5,
    # How many recent jobs the correction factor is learned from.
    "history_window": 20,
    # Which finished jobs teach the factor (hermes branch). 0 = off. learn_min_raw: chat jobs quoted under this many wt are
    # left out (installments always count). learn_max_speed: a job whose work went faster than this many wt a
    # second is a measuring error (a long chat re-read counted as work), not a real job.
    "learn_min_raw": 0,
    "learn_max_speed": 0,
    # learn_mid_min: chat jobs quoted from this many wt up to learn_min_raw learn a factor of their own (0 = off).
    "learn_mid_min": 0,
    # learn_blend_raw (1.1.7): with the medium band on, a quote from learn_min_raw up to this many wt is corrected along a
    # straight line, from learn_min_raw x the medium factor to this x the factor; from here up, by the factor alone. On
    # the author's numbers (x1.0165, medium x1.7476) 3.4M is twice the quote the factor alone takes to give what the
    # band gives at 1M (1.72M): the line rises 0.71 wt for each raw wt, the extra over the factor shrinks evenly from
    # 731k at 1M to 0 here. If the factors change so that the line would rise less than half as fast as the factor,
    # it is made longer by itself; at or under learn_min_raw, with the factor the larger, there is no line.
    "learn_blend_raw": 3400000,
    # learn_rate_all (v118; 0 = off, 1 = on): the installments' factor is learned from ALL your finished jobs, chat jobs
    # and installments, the last history_window of them, without learn_min_raw / learn_max_speed and without types; the
    # chat jobs' factor does not change. On the author's 51 jobs (16/10/2026, a walk-forward test: each job estimated
    # only with the jobs finished before it) the installments' typical miss went from 48% to 34% and their lean from
    # x1.41 under to x1.06: learned from installments alone, the factor came from a few big book jobs that cost less
    # than quoted, and was applied to smaller jobs that cost more. Only 13 installments: a hint, not a proof.
    "learn_rate_all": 0,
    # 1.1.8: what 9 small jobs measured in new sessions taught (16/10/2026, no additions halfway). Each one 0 = off.
    # writing_wt_per_word: for a text to write, the quote counts this many wt per word of the final text (50 suggested;
    # the protocol says the margin, from half of it to 1.1 times: 25 to 55). The texts were quoted 4 times under: 10 to
    # 19 wt a word in the quotes, 49 to 56 measured, because the text comes out as output (weight 5, about 6.5 tokens a
    # word through the Write tool), then goes back into the context and is re-read at every call after it. On 17/10/2026,
    # with the rule on, 13 more texts cost 23 to 49 wt a word (about 28): 50 quoted them high, 30 to 35 may fit better
    # (docs/evidence/quote-accuracy.md).
    # 1.1.9: on for everyone at 27 (it was off in 1.1.8). Measured since: 16 texts of docs/evidence 23 to 56 wt a word,
    # and 4 new texts done as a new user through the API (19/10/2026) 20 to 39: the median of the 20 is about 27.
    "writing_wt_per_word": 27,
    # note_web_haiku (1 = on): Claude Code's web searches also run a small model (haiku) that is not in the session's
    # log, so its cost is not in the measure; the report at the end of a research job says so in one line (on the one
    # research job measured: about 12% of the session at list prices, some 14,000 haiku input tokens a search).
    "note_web_haiku": 0,
    # small_quote_line (1 = on): a quote the user asks for a job under the threshold is one line (work, total, time,
    # shares) instead of the full table and the choice window, and the first-use questions wait for the first job above
    # the threshold: in a new session the full quote cost about 70,000 wt, more than the small job itself.
    "small_quote_line": 0,
    # margin_percent: the same job done again cost from -9% to +10%, and the quote of the same task changed too; at the
    # end of a job a miss under this many percent is said to be within the margin, noise and not a signal (15 suggested).
    "margin_percent": 0,
    # requote_on_addition (1 = on): the protocol says that a task added to a job (while it is open or right after it)
    # gets a quote of its own before it is done. In the author's jobs, those with signs of additions cost x1.82 their
    # raw quote and the others x1.20; a new quote made halfway came within x0.84 to x1.14 of the real cost.
    # 1.1.9: on for everyone (it was off in 1.1.8): with additions counted in the same job its quote could not be
    # right, and the factor learned the additions as if they were misses (see learn_clean_only).
    "requote_on_addition": 1,
    # learn_clean_only (1.1.9, 1 = on): the chat jobs' factor learns only from CLEAN jobs, those where the user wrote
    # nothing during the work (turns, replies counted apart excluded, at most clean_max_turns). On the author's jobs
    # (19/10/2026) a clean job cost x0.56 its raw quote and a job with messages during the work x1.49 (the user added
    # tasks): one factor for both learned the mix, so it was too low for some jobs and too high for the others. With
    # the clean jobs alone the typical miss of the clean jobs went from 85% to 50%; on the 49 jobs of docs/evidence
    # (all clean) a learned factor gave 33% against 75% raw. Installments keep their own rules (their turns are runs).
    "learn_clean_only": 1,
    "clean_max_turns": 1,
    # start_factor (1.1.9): until there are min_jobs clean chat jobs, rows at this factor fill the gap (instead of the
    # shared average): the 49 clean jobs of docs/evidence cost x0.58 their raw quote. 0 = the shared average as before.
    "start_factor": 0.58,
    # start_factors (1.1.9): the start of each type of work, for a quote with kind=<type>, until there are min_jobs clean
    # jobs of that type: what the clean jobs of that type cost against their raw quotes, the 49 of docs/evidence and 15
    # new ones done as a new user through the API on 19/10/2026 (code 27 jobs x0.70, research 14 x0.34, other 5 x0.38,
    # all 64 x0.59). Texts: 1.0, because their raw quote follows the rule for texts (writing_wt_per_word), already
    # measured. A type not listed starts from start_factor.
    # piece_share, piece_min (1.2.0, the user's request: "the work in small pieces"): a job is measured in pieces of
    # piece_share of its corrected quote (at least piece_min wt), each with a PROGRESS line: before, a piece was 1M wt,
    # so most chat jobs (under 1M) had none, and an installment of 2-3M was one piece. In an installment a piece is
    # piece_share of the day's cap: at each one Quotient asks the agent to update the PROGRESS line once. 0: 1M pieces
    # (requote.after) and one piece per installment, as before.
    "piece_share": 0.25,
    "piece_min": 250000,
    "start_factors": {"code": 0.70, "research": 0.35, "writing": 1.0, "other": 0.40},
    # Claude Code runs (claude -p) a Hermes chat starts, counted in its quoted jobs (hermes branch; 1 = on). A SessionStart
    # hook records which Hermes chat started each Claude Code session (Hermes gives HERMES_SESSION_ID to all it
    # starts); when a job closes, what those sessions spent while it was open is added to its cost.
    # claude_runs_marker: also count the `claude -p` sessions the hook never saw whose first prompt starts with
    # this text (runs from before the hook, or with the user's hooks off); "" = off.
    "claude_runs": 0,
    "claude_runs_marker": "",
    # Below this many measured jobs the factor is shown as uncertain.
    "min_jobs": 5,
    # 1.2.3 (Francesco's rule): the shared average stays a part of the factor for good: it weighs k/(k+n) with n your jobs
    # that teach and k = min_jobs, never under this. With start rows (start_factor) it weighs just this, since those rows
    # are what the first jobs measured. The two are mixed on a log scale. 0 = before 1.2.3: gone after min_jobs jobs.
    # Off (0) by default in 1.2.3: the shared average still holds mostly jobs measured by older versions, and mixing it
    # in made the author's quotes less accurate; turn it on (e.g. 0.1) once it counts only recent versions.
    "shared_min_weight": 0,
    # 1.1.4: a type of work (code, writing, research, other) has its own factor from this many jobs of its own on;
    # before that it uses the factor of all the jobs of its kind (chat or installments).
    "type_min_jobs": 3,
    # 1.1.4: after this many wt of work of a job, its own pace makes a new quote when the corrected estimate of what is
    # left changes by more than `percent`; the user sees it once and chooses whether to go on.
    "requote": {
        "after": 1000000,
        "percent": 30,
    },
    # 1.1.4: the guided repair (`fix`). A job looks split when it ends at most `gap_minutes` before another one of the
    # same chat starts and its work is under `small_share` of that one's.
    "fix": {
        "gap_minutes": 30,
        "small_share": 0.25,
    },
    # 1.1.4: when the plugins, MCP servers or hooks change, the jobs after the change weigh `weight` times the older
    # ones in the factor, once there are `min_jobs` of them.
    "env": {
        "min_jobs": 3,
        "weight": 2,
    },
    # A quote nobody chose is dropped after this many turns.
    "pending_ttl_turns": 3,
    # Language of the report: "en" or "it".
    "lang": "en",
    # Path to the claude executable; empty means "find it".
    "claude_path": "",
    "limits": {
        # Read the plan limits through Claude Code's own /usage command (run in the background, no tokens spent),
        # at most once every this many seconds. live false: only the status line. 1.1.8: 60 (was 600, the user's
        # request): each step of the percentage is caught within a minute, so the size of 1% is measured between two
        # steps instead of across ten minutes of work; a reading costs no tokens, only a ~4 s process in the background.
        "live": True,
        "every": 60,
        # 1.1.8 (the user's request): the line also says how many weighted tokens are left in each window, the share
        # left times how much 1% holds (the user's own estimate, or the plan's shared one until there is one), e.g.
        # "81% left (~26M wt)". It falls as the window is used and follows the same sizes as the quotes. 0: off.
        "show_left": 1,
        # 1.2.0 (the user's request): with show_left, the ceiling of the window too: "81% left (~26M of ~32M wt)".
        # 0: the tokens left alone, as in 1.1.8.
        "show_top": 1,
        # 1.1.6: while a job or an installment is open, at most once every this many seconds (in the background, the
        # message does not wait): more readings, so the size of the limit is learned in fewer uses.
        "job_every": 60,
    },
    # Count the chats of Hermes Agent (same Claude login, same limits) in the weeks and in the report.
    "hermes": True,
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
        # The last minutes before that stop are for saving, as at the end of the cap: new work is refused. 0 = off.
        "close_minutes": 15,
        # After an installment, put the PC back to sleep only if nobody used it for this long.
        "idle_minutes": 10,
        # What the PC does after an installment unless a job says otherwise: nothing, sleep or hibernate.
        "after": "nothing",
        # Whether scheduled installments may wake the PC from sleep or hibernation (the user's choice).
        "wake": True,
        # A desktop notification when an installment ends (on Windows it stays in the notification center).
        "notify": True,
        # The cap is checked before each tool call, and the steps after it still cost: new work stops when
        # what is spent plus this many of the latest calls would reach the cap (at most this share of it).
        "reserve_calls": 2,
        "reserve_max_share": 0.4,
        # The last part of the cap is kept for saving (1.1.1): there, tools that start new work (helpers, web
        # searches, commands) are refused, and Write/Edit still pass, so the installment and its helpers save.
        "save_percent": 8,
        # 1.1.3: the time the quote proposes for the installments, when the user does not write one.
        "time": "03:00",
        # 1.2.2: each installment is a new Claude Code session, and its first call writes the whole start (system,
        # tools, rules: about 50k tokens) to the cache, about 100k wt before any work (19/10/2026: a 99k cap was spent
        # just starting, 139k and nothing done). 1 = quotes and caps count that start once per installment, learned
        # from the measured installments; 0 = the old way (re-reading as a share of the work only).
        "start_fixed": 1,
        # 1.2.2: an installment's cap is at least this many times that start, else it spends its cap just starting
        # (rate new, rate apart, rate set; a week too full for it skips the installment). 0 = no floor.
        "min_cap_starts": 1.5,
        # 1.2.7: before a job starts (rate new, rate apart), a few lines when its task looks vague (short, no file
        # named, no way to check the work, no goal) or when the CLAUDE.md rules Claude Code loads for its folder are
        # missing or big (every step of every installment re-reads them). Simple word checks, so they only advise.
        # 1 = on, 0 = off; the two numbers are where "short" and "big" start.
        "task_check": 0,
        "task_min_words": 60,
        "rules_warn_tokens": 10000,
        # Improvement 1: the command `task-file` writes a job's task file from a few answers. task_file_hint 1: the
        # protocol tells the agent to write the task of a job apart or in installments with it (0 = it just asks for a
        # file). task_file_lines: most lines of one code example in that file (0 = no limit). task_file_stuck: after how
        # many attempts at one problem the file tells the job to stop on it.
        # Improvement 11: an installment that repeats the same command, or meets the same error, this many times in a
        # row stops by itself: Quotient writes it in the handoff and only the handoff can then be written. 0 = off.
        "loop_stop": 0,
        "task_file_hint": 0,
        "task_file_lines": 60,
        "task_file_stuck": 3,
        "extra_args": [],
    },
    # 1.1.1: each finished job (and each installment) is set against how much the weekly limit rose meanwhile. A miss
    # beyond x`factor`, with no other job running, is told once; Quotient changes nothing by itself. Jobs smaller than
    # `min_points` points of the week are not judged (the percentages are whole numbers), and a reading of the week
    # more than `hours` before the start or after the end is too far to tell.
    "check": {
        "factor": 3,
        "min_points": 4,
        "hours": 3,
    },
    # 1.1.2: the two percentages rise with the same use, so the points the 5 hours rise for 1 point of the week give a
    # second estimate of the week (a check). The two estimates are said not to agree beyond x`factor`; the ratio takes
    # the place of the direct estimate when that one has fewer than `min_points` points of the week and the ratio has them.
    "ratio": {
        "factor": 1.5,
        "min_points": 3,
    },
    # 1.1.2: a change of subscription. The last `windows` 5-hour windows (each with `min_points` points or more, in
    # `days` different days at least) all beyond x`factor` from the earlier ones in the same direction, and the week in
    # the same time (`week_points` points or more) beyond it too: the limit has changed, Quotient learns it again.
    "plan": {
        "factor": 1.6,
        "windows": 3,
        "min_points": 5,
        "days": 2,
        "week_points": 3,
    },
    # 1.1.6: the user's subscription, chosen in the setup window or with `plan-changed --plan`: pro, max5, max20, other,
    # or "unknown" ("I don't know"); empty until asked. Only a chosen plan goes in the shared line, and a new user
    # starts from the shared size of 1% of the week of that plan until their own readings are enough.
    "subscription": "",
    # 1.1.6: Claude Code's own telemetry as a second measure (see telemetry.py; `telemetry on` prints the settings).
    # A local receiver on 127.0.0.1:`port` keeps numbers only; it stops after `idle_minutes` without data. A finished
    # job or installment whose two measures differ beyond `percent` (and `min_wt` or more) is told once. The telemetry's
    # cache writes do not say 5 minutes or 1 hour: `cache_write` "1h" (what Claude Code writes in its main work) or "5m".
    "telemetry": {
        "enabled": False,
        "port": 4318,
        "interval_ms": 30000,
        "idle_minutes": 120,
        "percent": 25,
        "min_wt": 100000,
        "cache_write": "1h",
    },
    # The time of a job (1.1.0) is read from the times Claude Code and Hermes already keep. True: also a small
    # always-on-top stopwatch window (needs tkinter); off by default, the user did not want one more window.
    "timer": {
        "window": False,
    },
    # Improvements 2, 5, 7, 9 (savings.py): tips for saving tokens. level 0 = off, 1 = few (the one that saves most, each
    # told once in a chat), 2 = all (at most `most` at a message, told again as they grow). `tips later` and `tips drop`
    # put one off or throw it away.
    # new_chat_tokens: a new chat is proposed only from this size on (Francesco's rule: 500,000), in the tips, in the
    # line and in the quote's pace options while tips are on. long_chat_tokens: a summary, from this size on.
    # apart_tokens: an open job in a chat this long gets the tip of doing it apart. again_tokens: told again after this
    # much growth. tool_share, tool_min_wt: a tool's share of a chat, in percent, from this much spent in the chat.
    # image_tokens: what one screen photo weighs (Anthropic's rule, width x height / 750, about 1,500 for a big one).
    # cache_min_percent, cache_min_calls: the part of what is sent that comes from the cache, below which there is a
    # tip, from this many steps. cold_min_tokens: prompts smaller than this do not count as a cold cache.
    # every_seconds: how often the logs are read for tools and cache. later_days: the default of `tips later`.
    "tips": {
        "level": 0,
        "most": 3,
        "new_chat_tokens": 500000,
        "long_chat_tokens": 500000,
        "apart_tokens": 200000,
        "again_tokens": 100000,
        "tool_share": 25,
        "tool_min_wt": 500000,
        "image_tokens": 1500,
        "cache_min_percent": 70,
        "cache_min_calls": 10,
        "cold_min_tokens": 20000,
        "every_seconds": 600,
        "later_days": 7,
    },
    # Improvement 8 (savings.py): enabled 1: a quote, a closed job and a finished installment job say what the same
    # tokens would cost on a cheaper model (`model`, a family). Only prices, stated as an estimate: a cheaper model may
    # need more steps and may work worse, which nobody can price. A family's price is the input price of `ids` in the
    # table (`prices update`) and otherwise `prices`, dollars per million input tokens from Anthropic's public price
    # page, 31/10/2026 (Haiku 5.5: its price for prompts over 100,000 tokens, the prudent one); they are settings.
    "whatif": {
        "enabled": 0,
        "model": "sonnet",
        "ids": {"fable": "claude-fable-5-1", "opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5",
                "haiku": "claude-haiku-5-5"},
        "prices": {"fable": 10.0, "opus": 4.0, "sonnet": 2.0, "haiku": 0.5},
    },
    # Improvement 10 (savings.py): a budget for the normal chats, in percent of the weekly limit, read from the plan's
    # limits. day_percent: what a day may use (0 = no budget); week_percent: where the week may reach (0 = no budget).
    # A line at each share of `warn`, once. stop 1: past the budget Claude Code refuses the next message, until the user
    # writes BUDGET OK in one (it then passes until the budget's day or week ends); Hermes has no way to refuse a
    # message, so it only asks the agent not to start new work. Installments have their own cap.
    "budget": {
        "day_percent": 0,
        "week_percent": 0,
        "warn": [50, 80, 100],
        "stop": 0,
    },
    "share": {
        # On by default and declared (first-use window, README, PRIVACY.md): after each finished job, one line
        # of numbers (format, version, model family, raw estimate, real cost) goes to the shared average.
        # Off: nothing is sent, and the shared average is still downloaded and used.
        "enabled": True,
        # The service that collects the lines (server/ in the repository). Empty: lines wait in the outbox.
        "endpoint": "https://quotient-share.korvonordico.workers.dev",
        # The published average, read once a day.
        "average_url": "https://raw.githubusercontent.com/Korvonordico/quotient-data/main/average.json",
        "timeout": 3,
        # True once the user has been shown what is shared (a message at session start, the setup
        # window, or /token-quotient:share). Nothing is queued before that.
        "notice_shown": False,
    },
}

QUOTE_KEYS = r"(?:PREVENTIVO|ESTIMATE|QUOTE)"
CHOICE_KEYS = r"(?:SCELTA|CHOICE)"
QUOTE_RE = re.compile(r"^[\s>*_`#-]*" + QUOTE_KEYS + r"[*_`]*\s*:\s*(.+)$", re.M)
CHOICE_RE = re.compile(r"^[\s>*_`#-]*" + CHOICE_KEYS + r"[*_`]*\s*:[\s*_`]*([^\s*_`,.;:=]+)", re.M)
# 1.1.3: a choice of the user's own (the window's free field: a mix of levels, a level of their own) comes with the
# agent's raw estimate for it: `CHOICE: custom=<n>` (or another name with its estimate)
CHOICE_AMOUNT_RE = re.compile(r"^[\s>*_`#-]*" + CHOICE_KEYS + r"[*_`]*\s*:[\s*_`]*([^\W\d][\w-]*)\s*=\s*~?\s*"
                              r"(\d[\d.,_]*)\s*([kKmM])?(?![\w])", re.M)
CONTINUES_RE = re.compile(r"(?:JOB|LAVORO)[*_`]*\s*:\s*[*_`]*(?:CONTINUES|CONTINUA)", re.I)
# 1.1.8: the end of a job written as a line of its own (`JOB: CLOSE` with no chat id after it)
JOB_DONE_RE = re.compile(r"^[\s>*_`#-]*(?:JOB|LAVORO)[*_`]*\s*:[\s*_`]*(?:CLOSE|CHIUDI|DONE|FINITO)[*_`.]*[ \t]*$",
                         re.M | re.I)
# 1.1.1 (the user's idea): a reply about something else while a job is open ends with this line. It is a real cost
# (it is in the limits) but not work: it is counted apart, and the job stays open.
ASIDE_RE = re.compile(r"^[\s>*_`#-]*ASIDE[*_`]*[ \t]*(?::[^\n]*)?$", re.M)
# A job of another chat: resumed here, finished (closed with what it cost), or dropped (not measured).
MOVE_RE = re.compile(r"^[\s>*_`#-]*(?:JOB|LAVORO)[*_`]*\s*:[\s*_`]*(RESUME|RIPRENDI|CLOSE|CHIUDI|DROP|ABBANDONA)"
                     r"[*_`]*\s+[*_`]*([0-9a-fA-F-]{4,40})", re.M | re.I)
MOVES = {"resume": "resume", "riprendi": "resume", "close": "close", "chiudi": "close", "drop": "drop",
         "abbandona": "drop"}
PACE_RE = re.compile(r"^[\s>*_`#-]*(?:PACE|RITMO)[*_`]*\s*:[\s*_`]*([^\n]+)", re.M)
LIMITS_RE = re.compile(r"^[\s>*_`#-]*LIMITS[*_`]*\s*:\s*(.+)$", re.M)
TODAY_RE = re.compile(r"\b(?:today|oggi|all|tutto)\b", re.I)
NEW_CHAT_RE = re.compile(r"new[\s_-]*chat|nuova[\s_-]*chat|chat[\s_-]*nuova", re.I)
# 1.1.1: 'apart, now' / 'a parte, adesso': one installment in a separate session, started at once (rate apart)
APART_RE = re.compile(r"\bapart\b|\ba[\s_-]*parte\b|\bseparat", re.I)
# the installment keeps this line in its handoff: how much of the whole job is done
PROGRESS_RE = re.compile(r"^[\s>*_`#-]*(?:PROGRESS|AVANZAMENTO)[*_`]*\s*:[\s*_`~]*(\d{1,3}(?:[.,]\d+)?)\s*%", re.M | re.I)
# the window's questions that belong to Quotient (its own actions are counted as its weight)
QUOTIENT_HEADERS = {"livello", "level", "ritmo", "pace", "prima rata", "first installment", "ogni giorno",
                    "every day", "dopo la rata", "after it", "soglia", "threshold", "riserva", "reserve",
                    "lingua", "language", "il pc", "the pc", "media condivisa", "shared average", "piano", "plan"}
# Quotient run by Claude: the installed plugin's script (folder token-quotient, or quotient before 0.9.8) or the launcher
QUOTIENT_CMD_RE = re.compile(r"[\\/](?:token-)?quotient[\\/]+[\w.-]+[\\/]+scripts[\\/]+(?:quotient\.py|run\.sh)|"
                             r"\.quotient[\\/]+launcher\.py", re.I)
OPTION_RE = re.compile(r"([^\W\d][\w-]*)\s*=\s*~?\s*(\d[\d.,_]*)\s*([kKmM])?(?![\w])")
DECLINE = {"none", "nessuna", "nessuno", "no", "annulla", "cancel"}
INSTALLMENT_RE = re.compile(r"^(?:split|rata|rate|installments?)\d*$", re.I)
# the installment writes JOB DONE as the first line of the handoff; a sentence that only names it
# ("after line 3: write JOB DONE") is not the end of the job (05/10/2026: that closed a job at 1 line of 3)
DONE_RE = re.compile(r"\A[﻿#*_>\s-]*(?:JOB DONE|LAVORO FINITO)\b")
# 1.1.3: an installment plan in the user's words or in the machine line: how many days, how much a day, at what time
# ("5 giorni alle 2:00", "days=5 at=02:00", "50.000 al giorno", "3 days, 200k a day, at 2am")
PLAN_DAYS_RE = re.compile(r"\bdays?\s*=\s*(\d{1,3})\b|\b(\d{1,3})\s*(?:giorni|giorno|gg|days?)\b", re.I)
PLAN_DAILY_RE = re.compile(
    r"\bdaily\s*=\s*~?\s*(\d[\d.,_]*)\s*([kKmM])?(?![\w])|"
    r"(\d[\d.,_]*)\s*(k|m|mila|milion[ei]|millions?)?\s*(?:di\s+)?(?:token\w*\s*)?(?:pesati\s*)?(?:wt\s*)?"
    r"(?:al\s+giorno|a\s+day|per\s+day|/\s*day|ogni\s+giorno|every\s+day)", re.I)
PLAN_AT_RE = re.compile(
    r"(?:\b(?:at|time)\s*=\s*|\balle(?:\s+ore)?\s*|\ball'\s*|\bore\s+|\bat\s+|@\s*)(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?"
    r"(?![\d:])(?!\s*(?:giorni|giorno|gg|days?|%|k\b|mila))", re.I)
MIDNIGHT_RE = re.compile(r"\b(?:a\s+)?mezzanotte\b|\bat\s+midnight\b", re.I)
# 1.1.3: how many levels a quote offers, by its size (see `levels` in DEFAULTS), and their names in the QUOTE line,
# always from the smallest to the biggest; the window shows 4 options at most and adds a free field by itself
LEVEL_NAMES = {1: ("good",), 2: ("good", "max"), 3: ("essential", "good", "max"), 4: ("essential", "good", "full", "max")}
LEVEL_WORDS = {   # the names in the user's language, also to find each level in the text of a quote
    "essential": {"it": "essenziale", "en": "essential", "also": ("essenziale", "minimo", "minimal", "base", "basic")},
    "good": {"it": "buono", "en": "good", "also": ("buono", "buona", "buon")},
    "full": {"it": "completo", "en": "full", "also": ("completo", "completa", "complete", "pieno")},
    "max": {"it": "massimo", "en": "max", "also": ("massimo", "massima", "maximum", "massime")},
}
# installment plans offered in the window, in days, by the number of levels the size of the job gives
PLAN_DAYS = {1: (2, 3), 2: (2, 3), 3: (3, 5), 4: (3, 5, 7)}
# what a complete quote shows for each level (1.1.3, checked at the end of the reply that quotes)
TIME_TOKEN_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:min|minut[oi]|minutes?|h|ore|ora|hours?|hrs?|sec|secondi|"
                           r"seconds?|s)\b|\b(?:un'ora|mezz'ora|an hour|half an hour)\b", re.I)
PERCENT_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%|\bper\s?cento\b|\bpercent\b", re.I)
# 1.1.4: the type of work, in the QUOTE line (`kind=code`): code, writing and research go wrong in different ways
# (15/10/2026: the book's curiosities, checked against history with web searches, quoted 1.6M, cost 4.4M)
WORK_TYPES = ("code", "writing", "research", "other")
TYPE_WORDS = {"code": "code", "codice": "code", "coding": "code", "programming": "code", "programmazione": "code",
              "writing": "writing", "scrittura": "writing", "testo": "writing", "testi": "writing", "text": "writing",
              "libro": "writing", "book": "writing", "research": "research", "ricerca": "research", "web": "research",
              "other": "other", "altro": "other", "mix": "other"}
TYPE_RE = re.compile(r"(?<![\w])(?:kind|type|tipo)\s*=\s*([^\W\d][\w-]*)", re.I)


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
    "WAKE": (("rate", "wake"), "bool"),
    "SHARE": (("share", "enabled"), "bool"),
    "COMPACT": (("compact", "mode"), str),
    "COMPACT_AT": (("compact", "at"), int),
}


def to_bool(value):
    return str(value).strip().lower() in ("1", "true", "yes", "si", "sì", "on")


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


def plugin_options():
    """The plugin's settings, as Claude Code passes them to hooks. Each variable is written out in full, so it
    is plain which ones Quotient reads: these eight, all of them settings, none of them a credential."""
    return {
        "THRESHOLD": os.environ.get("CLAUDE_PLUGIN_OPTION_THRESHOLD"),
        "RESERVE_PERCENT": os.environ.get("CLAUDE_PLUGIN_OPTION_RESERVE_PERCENT"),
        "LANG": os.environ.get("CLAUDE_PLUGIN_OPTION_LANG"),
        "AFTER": os.environ.get("CLAUDE_PLUGIN_OPTION_AFTER"),
        "WAKE": os.environ.get("CLAUDE_PLUGIN_OPTION_WAKE"),
        "SHARE": os.environ.get("CLAUDE_PLUGIN_OPTION_SHARE"),
        "COMPACT": os.environ.get("CLAUDE_PLUGIN_OPTION_COMPACT"),
        "COMPACT_AT": os.environ.get("CLAUDE_PLUGIN_OPTION_COMPACT_AT"),
    }


def sync_plugin_options():
    """Claude Code passes the plugin's settings to hooks as CLAUDE_PLUGIN_OPTION_<KEY>; scheduled runs
    do not get them, so they are copied into config.json, where every part of Quotient reads.
    A plugin setting is copied only when it changes, so a choice made elsewhere (for example
    `share off`) is not undone by a plugin setting the user never touched."""
    path = os.path.join(home(), "config.json")
    seen = load_json(path, {}).get("plugin_seen") or {}
    values, now_seen = {}, dict(seen)
    given = plugin_options()
    for key, (keys, kind) in OPTIONS.items():
        raw = given.get(key)
        if raw in (None, "") or seen.get(key) == raw:
            continue
        try:
            values[keys] = to_bool(raw) if kind == "bool" else kind(float(raw)) if kind is int else kind(raw)
            now_seen[key] = raw
        except ValueError:
            pass
    if values:
        save_settings(values)
        if any(keys[0] == "compact" for keys in values):
            try:
                from quotient_lib import q_longchats   # used only here: q_settings loads before all the others
                q_longchats.apply_compact(config())  # the user changed it in the plugin's settings: that is their choice
            except Exception:
                pass
    if now_seen != seen:
        user = load_json(path, {})
        user["plugin_seen"] = now_seen
        save_json(path, user)


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
