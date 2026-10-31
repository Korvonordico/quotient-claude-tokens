"""Long chats: compaction at a size, and the setup command."""

import json
import os
import sys
import time

from quotient_lib import q_costs, q_hooks, q_learning, q_limits, q_quotes, q_settings, q_sharing

# ---------------------------------------------------------------- long chats: keep, or compact at a size

COMPACT_MIN, COMPACT_MAX = 100000, 1000000
COMPACT_MODES = ("keep", "auto", "custom")


def claude_settings_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def recommended_compact(cfg):
    """The chat size from which compacting pays, from your numbers: where re-reading the chat at every call
    (0.1 x its size) costs about twice the work of a call. Rounded to 50,000 and kept between 200,000 and
    900,000 tokens. Returns (tokens, how many jobs the work per call is learned from)."""
    wpc, n = q_hooks.work_per_call(cfg)
    size = 2 * wpc / cfg["weights"]["cache_read"]
    return max(200000, min(900000, int(round(size / 50000.0)) * 50000)), n


def compact_target(cfg):
    """The size at which the chat compacts itself, or None when the user keeps the chat as it is."""
    mode = cfg["compact"].get("mode") or "keep"
    if mode == "auto":
        return recommended_compact(cfg)[0]
    if mode == "custom":
        try:
            at = int(cfg["compact"].get("at") or 0)
        except (TypeError, ValueError):
            return None
        return max(COMPACT_MIN, min(COMPACT_MAX, at)) if at else None
    return None


def apply_compact(cfg):
    """Make Claude Code's own setting match the user's choice: autoCompactWindow = the size, so the chat
    summarizes itself there (a plugin cannot run /compact itself). With "keep", Quotient takes back only a
    value it wrote and puts back what was there before. A settings file that cannot be read is never
    overwritten. Returns one sentence for the user."""
    target = compact_target(cfg)
    path = claude_settings_path()
    if os.path.exists(path):
        settings = q_settings.load_json(path, None)
        if not isinstance(settings, dict):
            return "Claude Code's settings file could not be read, so it was left as it is: %s" % path
    else:
        settings = {}
    applied = cfg["compact"].get("applied")
    current = settings.get("autoCompactWindow")
    note = ""
    if os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW"):
        note = " The variable CLAUDE_CODE_AUTO_COMPACT_WINDOW is set, and it wins over this setting."
    if target:
        if current == target:
            sentence = "The chat already compacts itself at about %s tokens." % "{:,}".format(target)
        else:
            if current is not None and current != applied:
                q_sharing.store(("compact", "previous"), current)  # the user's own value, put back with "keep"
            settings["autoCompactWindow"] = int(target)
            save_json_pretty(path, settings)
            sentence = ("From the next chat, a chat compacts itself when it reaches about %s tokens "
                        "(autoCompactWindow in %s)." % ("{:,}".format(target), path))
        q_sharing.store(("compact", "applied"), int(target))
        return sentence + note
    if applied is not None and current == applied:
        previous = cfg["compact"].get("previous")
        if previous is not None:
            settings["autoCompactWindow"] = previous
        else:
            settings.pop("autoCompactWindow", None)
        save_json_pretty(path, settings)
        q_sharing.store(("compact", "applied"), None)
        q_sharing.store(("compact", "previous"), None)
        return "Chats are kept as they are again: Quotient took back its compaction setting." + note
    q_sharing.store(("compact", "applied"), None)
    return "Chats are kept as they are: Quotient does not touch Claude Code's compaction." + note


def save_json_pretty(path, data):
    """Write a settings file the way people read it: 2 spaces, a final newline, through a temporary file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".quotient.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def compact_warning(cfg, state, ctx):
    """One line for Claude when the chat is close to compacting itself: a summary loses details, so what must
    not be lost goes to files first. Said once each time the chat grows towards the size."""
    target = compact_target(cfg)
    if not target or not ctx:
        return None
    if ctx < target * 0.5:
        state.pop("compact_warned", None)  # the chat compacted (or is new): the next approach is told again
        return None
    if ctx < target * cfg["compact"].get("warn_percent", 85) / 100.0 or state.get("compact_warned"):
        return None
    state["compact_warned"] = True
    return ("COMPACTION SOON: this chat (~%s tokens) will summarize itself at about %s tokens (the user's choice "
            "in Quotient). A summary loses details: before it, write to files what must not be lost (the handoff, "
            "notes, decisions, an open job), then go on with what the user asked. Tell the user in one line." % (
                q_quotes.fmt(ctx), q_quotes.fmt(target)))


def hook_precompact():
    """PreCompact: remember the chat's size before the summary; the size after it is read at the end of the
    next reply, and the two together say what the compaction saves at every call. It never blocks."""
    data = q_settings.read_stdin_json()
    if os.environ.get("QUOTIENT_JOB"):
        return
    sid = data.get("session_id") or "unknown"
    state = q_settings.load_json(q_settings.session_path(sid), {})
    state["compacting"] = {"ts": q_settings.now_iso(), "trigger": data.get("trigger") or "",
                           "before": q_costs.context_size(data.get("transcript_path") or "")}
    q_settings.save_json(q_settings.session_path(sid), state)


def compactions_path():
    return os.path.join(q_settings.home(), "compactions.jsonl")


def compaction_summary():
    """How many compactions, and what they saved: at every call after one, the chat re-reads (before - after)
    tokens less, at the cache price (0.1). The summary itself is not counted (it is one big call): an estimate."""
    rows = [r for r in q_settings.read_jsonl(compactions_path()) if r.get("before") and r.get("after") is not None]
    turns = q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl"))
    saved = 0.0
    for r in rows:
        later = sum(t.get("calls") or 0 for t in turns if t.get("session") == r.get("session")
                    and q_limits.ts_epoch(t.get("ts")) > q_limits.ts_epoch(r.get("ts")) and not t.get("repeat"))
        saved += max(0, r["before"] - r["after"]) * 0.1 * later
    return {"count": len(rows), "auto": sum(1 for r in rows if r.get("trigger") == "auto"), "saved": saved,
            "before": q_learning.median([r["before"] for r in rows]) if rows else None}


def setup_instructions(cfg):
    # 1.1.8 (small_quote_line): the first-use questions wait for the first job above the threshold
    when = ("Before the first quote of a job above the threshold (%s wt; a small job does not need these questions), or "
            "when the user asks to set it up, " % q_quotes.fmt(cfg["threshold"]) if cfg.get("small_quote_line") else
            "At the user's first message in this session, before anything else, ")
    return ("FIRST USE: Quotient is not set up yet. " + when +
            "open the choice window (AskUserQuestion) in the user's language with four questions, each with a free field: "
            "'Soglia'/'Threshold' (from how many weighted tokens a job gets a quote: 100.000 = often, 300.000 = the default, "
            "1.000.000 = only huge jobs); 'Riserva'/'Reserve' (share of the weekly limit kept for normal use: 10%%, 20%%, 30%%); "
            "'Lingua'/'Language' of the report (italiano, English); 'Piano'/'Plan', the user's Claude subscription: Pro / Max "
            "5x / Max 20x / another one or I don't know (the free field takes another plan's name); say that a chosen plan "
            "lets Quotient start from the size of that plan's limits measured by its other users, and goes in the shared "
            "line only if they share. "
            "Current values: threshold %s, reserve %d%%, language %s, plan %s.\n"
            "Then open a second choice window. First question, 'Il PC'/'The PC' for scheduled installments: wake it and put it "
            "back to sleep / wake it and hibernate it / wake it and leave it on / never touch the PC (installments run only if it "
            "is already on); current: wake %s, after %s. Save the five answers with: "
            "%s setup --threshold <n> --reserve <n> --lang it|en --plan pro|max5|max20|other|unknown --wake yes|no "
            "--after sleep|hibernate|nothing  and tell the user that /token-quotient:setup opens these windows again whenever "
            "they want to change them.\n"
            "In that second window add a question, 'Media condivisa'/'Shared average': does the user "
            "take part in the shared average, which helps the program give everyone better first quotes? Say what it "
            "shares: only the raw estimate and the real cost (rounded), the model family and the Quotient version of "
            "each finished job, and when known the plan they chose and how many weighted tokens 1%% of the week holds "
            "on this PC; no dates, no text, no ids; and that people who do not take part still get the average. "
            "Options: take part (recommended, the default) / do not take part; the free field lets them write anything "
            "else (do what it asks if Quotient can, else explain the two options). Save with: %s setup --share yes|no "
            "and say that /token-quotient:share on|off changes it any time.\n"
            "In that same second window add a question 'Chat lunghe'/'Long chats': every call re-reads the whole chat, "
            "so a long chat costs more at every step. Options: keep the chat as it is (the default: Quotient offers a new "
            "chat when it pays) / let it compact itself at the size Quotient recommends from the user's numbers (now about "
            "%s tokens) / at a size the user writes in the free field (100.000 to 1.000.000 tokens). Say that a summary "
            "loses some details and that Quotient warns before it. Save with: %s setup --compact keep|auto|<tokens>\n" % (
                q_quotes.fmt(cfg["threshold"]), cfg["week"]["reserve_percent"], cfg["lang"], cfg.get("subscription") or "not said",
                "yes" if cfg["rate"]["wake"] else "no", cfg["rate"]["after"], q_quotes.run_cmd(), q_quotes.run_cmd(),
                "{:,}".format(recommended_compact(cfg)[0]).replace(",", "."), q_quotes.run_cmd()))


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
    if getattr(args, "wake", None) in ("yes", "no"):
        values[("rate", "wake")] = q_settings.to_bool(args.wake)
        if not values[("rate", "wake")]:
            values[("rate", "after")] = "nothing"  # a PC that is never woken is never put to sleep either
    if getattr(args, "share", None) in ("yes", "no"):
        values[("share", "enabled")] = q_settings.to_bool(args.share)
    plan = getattr(args, "plan", None)
    if isinstance(plan, str) and plan.strip():
        word = q_sharing.plan_word(plan)
        if not word:
            sys.exit("quotient: --plan takes pro, max5, max20, other or unknown")
        values[("subscription",)] = word   # 1.1.6
    values[("share", "notice_shown")] = True  # the setup window declares sharing
    compact = getattr(args, "compact", None)
    compact = compact if isinstance(compact, str) else None
    if compact:
        choice = compact.strip().lower().replace(".", "").replace(",", "").replace("_", "")
        if choice in ("keep", "auto"):
            values[("compact", "mode")] = choice
        elif choice.isdigit():
            values[("compact", "mode")] = "custom"
            values[("compact", "at")] = max(COMPACT_MIN, min(COMPACT_MAX, int(choice)))
        else:
            sys.exit("quotient: --compact takes keep, auto, or a size in tokens (100000 to 1000000)")
    copy = getattr(args, "hermes_copy", None)
    if copy in ("yes", "no"):
        values[("chat", "hermes_copy")] = q_settings.to_bool(copy)
        values[("chat", "hermes_copy_since")] = int(time.time())
    q_settings.save_settings(values)
    cfg = q_settings.config()
    if copy == "yes":
        q_settings.out("Hermes chats: each time Hermes summarizes a long chat, Quotient first saves the whole chat in %s.\n"
            % os.path.join(q_settings.home(), "chats"))
    elif copy == "no":
        q_settings.out("Hermes chats: Hermes summarizes long chats and Quotient saves no copy.\n")
    if compact:
        q_settings.out(apply_compact(cfg) + "\n")
    q_settings.out("Quotient is set up: threshold %s wt, reserve %d%% of the week, report in %s, wake the PC for installments: %s, "
        "after installments: %s, sharing anonymous numbers: %s, plan: %s.\nChange it any time with /token-quotient:setup "
        "(sharing: /token-quotient:share).\n" % (
            q_quotes.fmt(cfg["threshold"]), cfg["week"]["reserve_percent"], cfg["lang"],
            "yes" if cfg["rate"]["wake"] else "no", cfg["rate"]["after"], "on" if q_sharing.share_enabled(cfg) else "off",
            cfg.get("subscription") or "not said"))


def hook_claude_link():
    """SessionStart as a user hook (hermes branch): the link of hook_session, for a Claude Code whose Quotient plugin is
    older or missing."""
    q_costs.record_claude_link(q_settings.read_stdin_json())
