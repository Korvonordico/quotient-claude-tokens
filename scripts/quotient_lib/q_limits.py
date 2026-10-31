"""The plan's limits: reading them, how much 1% holds, and a change of subscription."""

import math
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone

from quotient_lib import q_learning, q_rates, q_runs, q_settings, q_sharing

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
    for match in q_settings.LIMITS_RE.finditer(text or ""):
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
    return os.path.join(q_settings.home(), "limits.jsonl")


def record_limits(snap, source):
    """Keep a reading of the plan limits; the same reading is not repeated within 5 minutes."""
    now = time.time()
    rows = q_settings.read_jsonl(limits_path(), tail_bytes=4096)
    if rows:
        last = rows[-1]
        same = all(last.get(k) == snap.get(k) for k in ("five_hour", "seven_day"))
        if same and now - (last.get("epoch") or 0) < 300:
            return
    row = {"ts": q_settings.now_iso(), "epoch": round(now), "source": source}
    row.update(snap)
    q_settings.append_jsonl(limits_path(), row)


def latest_limits():
    """The newest reading of each window that has not reset yet."""
    now = time.time()
    latest = {}
    for row in q_settings.read_jsonl(limits_path(), tail_bytes=512 * 1024):
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


def window_sizes(cfg=None):
    """1.1.8 (limits.show_left): how many weighted tokens 1% of each window holds, for the line at each message: the
    same estimates the quotes use (five_capacity, week_capacity). {} when the key is off or nothing is known yet."""
    try:
        cfg = cfg or q_settings.config()
        if not (cfg.get("limits") or {}).get("show_left"):
            return {}
        turns = measured_turns(cfg)
        sizes = {}
        for window, size in (("five_hour", five_capacity), ("seven_day", week_capacity)):
            c = size(cfg, turns=turns)
            if c and c.get("per_point"):
                sizes[window] = float(c["per_point"])
        return sizes
    except Exception:  # the line never fails for its tokens left
        return {}


def left_text(wt, lang, top=None):
    """1.1.8: the weighted tokens left in a window, rounded as an estimate: ~26M from 10 million, ~4.5M from one
    million, ~800k below (Italian: decimal comma)."""
    def short(n):
        n = max(0.0, float(n))
        if n >= 1e7:
            text = "%.0fM" % (n / 1e6)
        elif n >= 1e6:
            text = "%.1fM" % (n / 1e6)
        else:
            text = "%.0fk" % (n / 1e3)
        return text.replace(".", ",") if lang == "it" else text

    wt = max(0.0, float(wt))
    left = "0" if wt < 500 else "~" + short(wt)
    if top:
        # 1.2.0 (the user's request): the ceiling too, "~26M of ~32M wt", so the number falls toward 0 of a known whole
        return "%s %s ~%s wt" % (left, "su" if lang == "it" else "of", short(top))
    return "0 wt" if wt < 500 else "%s wt" % left


def cfg_limits():
    try:
        return q_settings.config().get("limits") or {}
    except Exception:
        return {}


FIVE_HOURS = 5 * 3600


def run_out_at(window, w, now=None, min_used=10):
    """1.3.0 (limits.pace): when the window would be used up at the pace used so far in it, as a Unix time, or None
    when that is after the reset (nothing to say), the reading is too early (under `min_used`%), or the start of the
    window is not known. Only the 5-hour window: its start is its reset minus 5 hours."""
    if window != "five_hour" or not w.get("resets"):
        return None
    used = float(w["used"])
    if used < min_used or used <= 0:
        return None
    at = w.get("epoch") or now or time.time()
    start = w["resets"] - FIVE_HOURS
    elapsed = at - start
    if elapsed <= 0 or at >= w["resets"]:
        return None
    if used >= 100:
        return None
    end = start + elapsed * 100.0 / used
    return end if end < w["resets"] else None


def limits_line(lang, sizes=None):
    """The plan limits for the line at each message. 1.1.8: with limits.show_left on (and how much 1% holds known),
    after the share left the weighted tokens left, e.g. "resta 81% (~26M wt)"; `sizes` (window -> wt per 1%) skips
    working them out again."""
    latest = latest_limits()
    if not latest:
        return None
    sizes = window_sizes() if sizes is None else sizes
    names = {"it": {"five_hour": "5 ore", "seven_day": "settimana"},
             "en": {"five_hour": "5-hour", "seven_day": "week"}}["it" if lang == "it" else "en"]
    words = ("usato %s%%, resta %s%%%s, si azzera %s" if lang == "it" else "%s%% used, %s%% left%s, resets %s")
    parts = []
    for window in WINDOWS:
        if window in latest:
            w = latest[window]
            left = " (%s)" % left_text(sizes[window] * max(0.0, 100 - float(w["used"])), lang,
                                       sizes[window] * 100 if (cfg_limits().get("show_top", 1)) else None) \
                if sizes.get(window) else ""
            parts.append("%s: %s" % (names[window], words % (
                round(w["used"]), max(0, 100 - round(w["used"])), left, when(w["resets"], lang))))
            lim = cfg_limits()
            end = run_out_at(window, w, min_used=float(lim.get("pace_min_used", 10))) if lim.get("pace", 1) else None
            if end:
                parts[-1] += (", a questo ritmo finisce verso %s" if lang == "it" else ", at this pace it runs out ~%s") \
                    % when(end, lang)
    newest = max(w["epoch"] for w in latest.values())
    age = (time.time() - newest) / 60
    stale = (" (letto alle %s)" if lang == "it" else " (read at %s)") % datetime.fromtimestamp(newest).strftime("%H:%M") \
        if age > 30 else ""
    return " · ".join(parts) + stale


def measured_turns(cfg=None):
    """(epoch, weighted tokens) of everything measured on this login: Claude Code turns and Hermes chats."""
    rows = [(ts_epoch(t.get("ts")), t["wt"]) for t in q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl")) if t.get("wt")]
    cfg = cfg or q_settings.config()
    if cfg.get("hermes", True) and os.environ.get("QUOTIENT_HERMES") != "0":
        try:
            import hermes_source as hs
            if hs.available():
                hs.sync(q_settings.home(), cfg["weights"])
            rows += [(r.get("epoch"), r["wt"]) for r in hs.read_log(q_settings.home()) if r.get("wt") and r.get("epoch")]
        except Exception:
            pass
    return rows


def limits_live(cfg):
    lim = cfg.get("limits") or {}
    return bool(lim.get("live", True)) and os.environ.get("QUOTIENT_LIMITS_LIVE") != "0"


def limits_every(cfg, busy=False):
    """1.1.6: how often the limits are read. While a job or an installment is open, every limits.job_every seconds (60):
    more points, so the size of the limit is learned in fewer uses; otherwise every limits.every seconds."""
    lim = cfg.get("limits") or {}
    return float(lim.get("job_every", 60) if busy else lim.get("every", 60))


def limits_due(every):
    """True when neither a reading nor a try is younger than `every` seconds."""
    last = q_settings.read_jsonl(limits_path(), tail_bytes=4096)
    tried = q_settings.load_json(os.path.join(q_settings.home(), "limits-state.json"), {}).get("tried") or 0
    now = time.time()
    return not ((last and now - (last[-1].get("epoch") or 0) < every) or now - tried < every)


def limits_soon(cfg, every=None):
    """1.1.6: during an open job, a reading of the limits in a separate process, so the message never waits for it; at
    most every limits.job_every seconds. 1.1.7: with `every` (limits.every when no job is open), the same at that pace:
    no hook waits for `claude -p /usage` any more (in Hermes the message waited about 4 s every 10 minutes, and 14
    times in 4 days the hook reached its 20 s limit and the message went without its line). The message shows the
    last reading saved; the new one reaches the message after. At most one start per interval, even before the process
    writes anything. True if one was started."""
    try:
        wait = limits_every(cfg, busy=True) if every is None else float(every)
        if not limits_live(cfg) or not limits_due(wait):
            return False
        path = os.path.join(q_settings.home(), "limits-state.json")
        state = q_settings.load_json(path, {})
        state = state if isinstance(state, dict) else {}
        if time.time() - float(state.get("started") or 0) < wait:
            return False   # started a moment ago: it has not read yet
        state["started"] = round(time.time(), 1)
        q_settings.save_json(path, state)
        return q_runs.start_detached(["limits-read"] + ([] if every is None else ["--every", "%g" % wait]),
                              os.path.join(q_settings.home(), "limits-read.log"))
    except Exception:  # a reading that cannot start must never stop a message
        pass
    return False


def limits_reader(cfg):
    """1.1.6: while an installment works (nobody writes, so no hook asks), a thread reads the limits every
    limits.job_every seconds. Returns the event that stops it, or None when live readings are off."""
    if not limits_live(cfg):
        return None
    every = limits_every(cfg, busy=True)
    stop = threading.Event()

    def loop():
        while not stop.wait(every):
            try:
                refresh_limits(cfg, every=every)
            except Exception:  # a reading that fails waits for the next one
                pass

    threading.Thread(target=loop, daemon=True).start()
    return stop


def refresh_limits(cfg=None, force=False, every=None):
    """A fresh reading of the plan limits from Claude Code's own /usage, when the last one is older than
    limits.every (or `every` seconds). No tokens are spent and Quotient never reads the login (see limits_usage.py)."""
    cfg = cfg or q_settings.config()
    if not limits_live(cfg):
        return None
    every = (cfg.get("limits") or {}).get("every", 60) if every is None else every
    if not force and not limits_due(every):
        return None      # read recently, or tried recently without an answer: Claude Code is not asked again yet
    state_path = os.path.join(q_settings.home(), "limits-state.json")
    state = q_settings.load_json(state_path, {})
    state = state if isinstance(state, dict) else {}
    state["tried"] = round(time.time())   # 1.1.7: the other keys stay (limits_soon's "started")
    q_settings.save_json(state_path, state)
    try:
        import limits_usage
        snap = limits_usage.fetch(q_rates.find_claude(cfg), cwd=q_settings.home())
    except Exception:
        snap = None
    if snap:
        record_limits(snap, "usage")
    return snap


def window_rows(window, since=0, until=None, turns=None):
    """One row per window (same reset time) from the readings in [since, until): its first and last reading, the points
    the percentage rose between them and the weighted tokens Quotient measured in between. Windows whose percentage did
    not rise are left out."""
    groups = {}
    for row in q_settings.read_jsonl(limits_path()):
        if row.get(window) is None or not row.get(window + "_resets") or not row.get("epoch"):
            continue
        if row["epoch"] < since or (until is not None and row["epoch"] >= until):
            continue
        groups.setdefault(round(row[window + "_resets"] / 300), []).append(row)
    turns = measured_turns() if turns is None else turns
    rows = []
    for group in groups.values():
        group.sort(key=lambda r: r["epoch"])
        first, last = group[0], group[-1]
        points = last[window] - first[window]
        if points <= 0:
            continue
        rows.append({"begin": first["epoch"], "end": last["epoch"], "resets": last[window + "_resets"], "points": points,
                     "wt": sum(w for t, w in turns if first["epoch"] < (t or 0) <= last["epoch"])})
    rows.sort(key=lambda r: r["begin"])
    return rows


def capacity(window, since=None, turns=None):
    """How many weighted tokens 1% of a window holds, from readings and measured turns.

    Within one window (same reset time) the rise of the percentage is set against the
    weighted tokens Quotient measured in between. Percentages are whole numbers in some
    sources, so each window carries an error of up to one point: that is the margin.
    Only the readings after the last change of plan count (1.1.2).
    """
    rows = window_rows(window, plan_since() if since is None else since, turns=turns)
    total_wt = sum(r["wt"] for r in rows)
    total_points = sum(r["points"] for r in rows)
    count = len(rows)
    if total_points < 3 or total_wt <= 0:
        return None
    return {"per_point": total_wt / total_points, "points": total_points, "windows": count,
            "low": total_wt / (total_points + count) * 100,
            "high": total_wt / max(total_points - count, 0.5) * 100}


def window_ratio(since=None):
    """How many points the 5 hours rise for 1 point of the week (1.1.2, the user's idea). The two percentages rise with
    the same use: within one 5-hour window and one week (same reset times) the two rises are set side by side, and they
    are summed over all such windows. The week rises slowly, so its own estimate has few points; this ratio times the
    size of 1% of the 5 hours, which has many, is a second estimate of the week. It needs no measured turns.

    The percentages are whole numbers: each window's two rises can be up to a point off. Over n windows those errors
    partly cancel (the variance of each rise is about 1/6 of a point squared), so the margin takes two standard
    deviations, 2 x sqrt(n/6) points, on each sum."""
    since = plan_since() if since is None else since
    groups = {}
    for row in q_settings.read_jsonl(limits_path()):
        if not row.get("epoch") or row["epoch"] < since or not row.get("five_hour_resets") or not row.get("seven_day_resets"):
            continue
        if row.get("five_hour") is None or row.get("seven_day") is None:
            continue
        groups.setdefault((round(row["five_hour_resets"] / 300), round(row["seven_day_resets"] / 300)), []).append(row)
    five, week, count = 0.0, 0.0, 0
    for group in groups.values():
        group.sort(key=lambda r: r["epoch"])
        d5 = group[-1]["five_hour"] - group[0]["five_hour"]
        dw = group[-1]["seven_day"] - group[0]["seven_day"]
        if d5 < 0 or dw < 0 or d5 == dw == 0:
            continue
        five, week, count = five + d5, week + dw, count + 1
    if five <= 0 or week <= 0:
        return None
    margin = 2 * math.sqrt(count / 6.0)
    return {"ratio": five / week, "low": max(five - margin, 0.0) / (week + margin),
            "high": (five + margin) / max(week - margin, 0.5), "five_points": five, "week_points": week,
            "windows": count, "since": since}


def week_capacity(cfg=None, turns=None):
    """How much 1% of the week holds: the direct estimate (capacity) when it has its points; otherwise, when the
    5-hour/week ratio has them, the ratio times 1% of the 5 hours, said so (source "ratio"). After a change of plan told
    by hand the ratio may still come from the readings of before ("ratio-before"), on the guess that the new plan keeps
    the same proportion between the two windows; the report says it, and the direct estimate replaces it in a few days."""
    cfg = cfg or q_settings.config()
    turns = measured_turns(cfg) if turns is None else turns
    direct = capacity("seven_day", turns=turns)
    if direct:
        return dict(direct, source="direct")
    five = capacity("five_hour", turns=turns)
    if not five:
        return plan_capacity(cfg)
    least = float(q_settings.merge(q_settings.DEFAULTS["ratio"], cfg.get("ratio") or {})["min_points"])
    since = plan_since()
    ratio, source = window_ratio(since), "ratio"
    if since and (not ratio or ratio["week_points"] < least):
        ratio, source = window_ratio(0), "ratio-before"
    if not ratio or ratio["week_points"] < least:
        return plan_capacity(cfg)
    return {"per_point": ratio["ratio"] * five["per_point"], "points": ratio["week_points"], "windows": ratio["windows"],
            "low": ratio["low"] * five["low"], "high": ratio["high"] * five["high"], "source": source, "ratio": ratio}


def plan_capacity(cfg, window="seven_day"):
    """1.1.6: until the user's own readings are enough, the shared size of 1% of the week of the plan they chose, as an
    estimate: its margin is the middle half of the users of that plan (source "plan"). 1.1.7: the same for the 5 hours
    (window "five_hour")."""
    p = q_learning.plan_average(cfg)
    end = "_5h" if window == "five_hour" else ""
    if not p or not p.get("per_point" + end):
        return None
    per = p["per_point" + end]
    return {"per_point": per, "points": 0, "windows": 0, "low": p.get("p25" + end) or per * 0.7,
            "high": p.get("p75" + end) or per * 1.4, "source": "plan", "plan": cfg.get("subscription"),
            "jobs": p["jobs" + end]}


def five_capacity(cfg=None, turns=None):
    """How much 1% of the 5 hours holds (1.1.7): the user's own estimate when it has its points; until then the shared
    one of their plan, as an estimate with its margin (source "plan"), like the week."""
    direct = capacity("five_hour", turns=turns)
    if direct:
        return dict(direct, source="direct")
    return plan_capacity(cfg or q_settings.config(), "five_hour")


def week_source(c):
    """A few words for the agent on where the estimate of the week comes from, when it is not the direct one."""
    if not c or c.get("source") in (None, "direct"):
        return ""
    if c["source"] == "plan":   # 1.1.6
        return ("; NOT measured here yet: the shared average of the users of the %s plan (%d jobs), an estimate until "
                "this PC has its own readings: say so" % (c.get("plan"), c.get("jobs") or 0))
    return ("; from the 5-hour/week ratio, the week's own estimate has too few points" if c["source"] == "ratio" else
            "; from the 5-hour/week ratio of before the change of plan, the week's own estimate has too few points")


# ---------------------------------------------------------------- a change of subscription (1.1.2)
# Each user learns the size of their own limit on their own PC (Pro, Max and the others differ). When the subscription
# changes, the windows of the old plan would stay mixed in for a long time: Quotient looks for the last windows all far
# from the earlier ones in the same direction, and from there on uses only the windows after the change. A day of much
# use outside Quotient (claude.ai, the phone) makes the limit look smaller for a while: one far window is not enough.

def plan_changes_path():
    return os.path.join(q_settings.home(), "plan-changes.jsonl")


def plan_state():
    """(since, quiet, row): the epoch of the last change of plan still standing (0: none), the epoch of the last one
    taken back (0: none; the windows that began before it are not judged again), and the row of that change."""
    changes, quiet = [], 0
    for row in q_settings.read_jsonl(plan_changes_path()):
        if row.get("undo"):
            if changes:
                changes.pop()
            quiet = max(quiet, row.get("epoch") or 0)
        elif row.get("epoch"):
            changes.append(row)
    last = changes[-1] if changes else None
    return (last["epoch"] if last else 0), quiet, last


def plan_since():
    """From when the size of the limit is learned: the last change of plan still standing, or 0."""
    return plan_state()[0]


def plan_detect(cfg=None, now=None):
    """Whether the limit has changed since the last change of plan (see DEFAULTS["plan"]). The last 5-hour windows must
    all be far from the earlier ones in the same direction and fall in more than one day, and the week, from the start
    of the first of them, must be as far in the same direction. Writes the change to plan-changes.jsonl and returns it,
    or None. From the start of the first far window on, only the readings after it count."""
    cfg = cfg or q_settings.config()
    p = q_settings.merge(q_settings.DEFAULTS["plan"], cfg.get("plan") or {})
    since, quiet, _ = plan_state()
    turns = measured_turns(cfg)
    n, factor = int(p["windows"]), float(p["factor"])
    five = [w for w in window_rows("five_hour", since, turns=turns) if w["points"] >= float(p["min_points"]) and w["wt"] > 0]
    if n < 1 or len(five) < 2 * n:
        return None
    recent, older = five[-n:], five[:-n]
    if recent[0]["begin"] < quiet:
        return None  # the user took the last change back: only windows after that are judged
    base = sum(w["wt"] for w in older) / sum(w["points"] for w in older)
    ratios = [w["wt"] / w["points"] / base for w in recent]
    if all(r >= factor for r in ratios):
        direction = "bigger"
    elif all(r <= 1 / factor for r in ratios):
        direction = "smaller"
    else:
        return None
    if len({datetime.fromtimestamp(w["begin"]).date() for w in recent}) < int(p["days"]):
        return None  # a day of much use outside Quotient is not a change of plan
    start = recent[0]["begin"]
    before = window_rows("seven_day", since, until=start, turns=turns)
    after = window_rows("seven_day", start, turns=turns)
    pb, pa = sum(w["points"] for w in before), sum(w["points"] for w in after)
    wb, wa = sum(w["wt"] for w in before), sum(w["wt"] for w in after)
    least = float(p["week_points"])
    if pb < least or pa < least or wb <= 0:
        return None  # the week cannot tell yet
    week = (wa / pa) / (wb / pb)
    if not (week >= factor if direction == "bigger" else week <= 1 / factor):
        return None
    row = {"ts": q_settings.now_iso(), "epoch": round(start), "source": "detected", "direction": direction,
           "five_hour": [round(r, 2) for r in ratios], "week": round(week, 2), "found": round(now or time.time())}
    q_settings.append_jsonl(plan_changes_path(), row)
    return row


def plan_alert(cfg, scheduled=False):
    """One line for the agent, once, when the limit looks changed (a change of subscription). The check runs only when a
    new reading of the limits came in since the last check; a scheduled prompt checks but leaves the telling to the user's
    next message."""
    path = os.path.join(q_settings.home(), "plan-state.json")
    st = q_settings.load_json(path, {})
    last = q_settings.read_jsonl(limits_path(), tail_bytes=4096)
    newest = last[-1].get("epoch") if last else None
    if newest and newest != st.get("checked"):
        st["checked"] = newest
        q_settings.save_json(path, st)
        plan_detect(cfg)
    if scheduled:
        return None
    _, _, row = plan_state()
    told = st.get("told") if isinstance(st.get("told"), list) else []
    if not row or row.get("source") != "detected" or row.get("found") in told:
        return None
    st["told"] = told + [row.get("found")]
    q_settings.save_json(path, st)
    bigger = row.get("direction") == "bigger"
    return ("PLAN: the plan limit looks %s than before: the last %d five-hour windows held x%s the weighted tokens per 1%% "
            "of the earlier ones, and the week in the same time x%s. Maybe the user changed subscription%s. From %s on, "
            "Quotient learns the size of the limit again, from the readings after it only. Tell the user once, in ONE "
            "line, in their language: their limit seems to have changed, maybe they changed subscription: Quotient "
            "starts learning it again (if they did not, `plan-changed --undo` takes it back)." % (
                "bigger" if bigger else "smaller", len(row.get("five_hour") or []),
                "/".join("%.1f" % r for r in row.get("five_hour") or []), "%.1f" % (row.get("week") or 0),
                "" if bigger else ", or used Claude a lot where Quotient cannot see (claude.ai, the phone)",
                when(row["epoch"], "en")))


def cmd_plan_changed(args):
    """The user says the subscription changed: from now on the size of the limit is learned from the readings after now
    only. --undo takes the last change back (found by Quotient or told by hand). 1.1.6: --plan also keeps the new plan
    (pro, max5, max20, other, unknown), as the setup window does."""
    it = q_settings.config().get("lang") == "it"
    now = round(time.time())
    plan = getattr(args, "plan", None)
    if isinstance(plan, str) and plan.strip():
        word = q_sharing.plan_word(plan)
        if not word:
            sys.exit("quotient: --plan takes pro, max5, max20, other or unknown")
        q_sharing.store(("subscription",), word)
        q_settings.out(("Piano salvato: %s.\n" if it else "Plan saved: %s.\n") % word)
    if getattr(args, "undo", False):
        since, _, _ = plan_state()
        if not since:
            q_settings.out("Nessun cambio di piano da annullare.\n" if it else "No change of plan to take back.\n")
            return
        q_settings.append_jsonl(plan_changes_path(), {"ts": q_settings.now_iso(), "epoch": now, "undo": True, "took_back": since})
        q_settings.out(("Annullato il cambio di piano del %s: le finestre di prima tornano a contare.\n" if it else
             "The change of plan of %s is taken back: the windows of before count again.\n") % when(since, "it" if it else "en"))
        return
    q_settings.append_jsonl(plan_changes_path(), {"ts": q_settings.now_iso(), "epoch": now, "source": "user"})
    q_settings.out("Fatto: da adesso Quotient reimpara quanto vale il tuo limite, solo dalle letture da qui in poi. Nel frattempo la "
        "settimana si stima, se si può, dal rapporto con le 5 ore (il resoconto lo dice).\n" if it else
        "Done: from now on Quotient learns the size of your limit again, from the readings after now only. Meanwhile the "
        "week is estimated, when it can be, from its ratio with the 5 hours (the report says so).\n")


def weeks():
    """One row per weekly window: the highest percentage seen and the weighted tokens measured in it."""
    groups = {}
    for row in q_settings.read_jsonl(limits_path()):
        if row.get("seven_day") is not None and row.get("seven_day_resets"):
            key = round(row["seven_day_resets"] / 300)
            g = groups.setdefault(key, {"resets": row["seven_day_resets"], "used": 0})
            g["used"] = max(g["used"], row["seven_day"])
    turns = measured_turns()
    rows = []
    for g in sorted(groups.values(), key=lambda g: g["resets"]):
        start = g["resets"] - 7 * 86400
        rows.append({"resets": g["resets"], "used": g["used"], "complete": g["resets"] < time.time(),
                     "wt": sum(w for t, w in turns if start < t <= g["resets"])})
    return rows
