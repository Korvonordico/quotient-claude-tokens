"""The anonymous numbers sent to the shared average, and downloading that average."""

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

from quotient_lib import q_costs, q_learning, q_limits, q_quotes, q_settings

# ---------------------------------------------------------------- sharing

SHARE_FIELDS = ("v", "q", "family", "estimate", "actual")
# 1.1.6: sent only when known: the plan the user chose, and how many wt 1% of the week held on this PC (3 digits);
# 1.1.7: and how many wt 1% of the 5 hours held (per_point_5h)
SHARE_OPTIONAL = ("plan", "per_point", "per_point_5h")
# What an older service takes besides the five fields, newest first: the line is sent again without the rest on a 400
SHARE_OLDER = (("plan", "per_point"), ())
PLANS = ("pro", "max5", "max20", "other")
PER_POINT_MIN, PER_POINT_MAX = 10000, 1000000000
# 1.1.7: the 5 hours hold about a tenth of the week (the author's: 409k wt in 1% against 3.58M), so a tenth of the range
PER_POINT_5H_MIN, PER_POINT_5H_MAX = 1000, 100000000
OUTBOX_MAX = 200
NOTICE = ("Quotient shares anonymous numbers of each finished job (raw estimate and real cost, rounded; model "
          "family; Quotient version; the plan, only if you chose it, and the weighted tokens in 1% of your week and "
          "of your 5 hours, rounded: no dates, no text, no ids) to build a shared average that helps everyone "
          "start from real data. Turn it off any time with /token-quotient:share off or in the plugin settings: you "
          "keep using the shared average. Details: "
          "https://github.com/Korvonordico/quotient-claude-tokens/blob/main/PRIVACY.md")


def store(keys, value):
    """Write one setting into config.json without marking Quotient as set up."""
    path = os.path.join(q_settings.home(), "config.json")
    user = q_settings.load_json(path, {})
    node = user
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    q_settings.save_json(path, user)


def round3(n):
    """3 significant digits: enough for a ratio, and an exact count is not a fingerprint."""
    n = int(round(n))
    step = 10 ** max(0, len(str(abs(n))) - 3)
    return int(round(n / step) * step)


def plan_word(text):
    """The plan from the user's words or a setting (1.1.6): 'Max 5x' -> max5, 'Pro' -> pro, 'Max 20x' -> max20,
    'Team' or 'altro' -> other, 'non so' -> unknown; None when it is not a plan."""
    t = re.sub(r"[\s_-]+", "", str(text or "").strip().lower())
    if not t:
        return None
    if t in ("unknown", "nonso", "nonlaso", "idontknow", "dontknow", "?", "boh", "altrononso", "othernotsure"):
        return "unknown"
    if "20" in t:
        return "max20"
    if "5" in t or t in ("max", "max5x"):
        return "max5"
    if t in ("pro", "claudepro"):
        return "pro"
    if t in ("other", "altro", "team", "enterprise", "free", "api", "altri"):
        return "other"
    return None


def learned_per_point(cfg=None):
    """How many wt 1% of the week held on this PC, from the user's own readings (direct, or from the 5-hour ratio),
    rounded to 3 significant digits: what the shared line carries (1.1.6). None when it is not known yet, or when it
    would only be the shared average of the plan given back."""
    try:
        c = q_limits.week_capacity(cfg)
    except Exception:
        return None
    if not c or c.get("source") == "plan":
        return None
    value = round3(c["per_point"])
    return value if PER_POINT_MIN <= value <= PER_POINT_MAX else None


def learned_per_point_5h(cfg=None):
    """How many wt 1% of the 5 hours held on this PC, from the user's own readings only, rounded to 3 significant
    digits (1.1.7, Francesco: the 5-hour limit of each plan confirmed by other people too). None when not known yet;
    never the plan's shared value given back."""
    try:
        c = q_limits.capacity("five_hour")
    except Exception:
        return None
    if not c:
        return None
    value = round3(c["per_point"])
    return value if PER_POINT_5H_MIN <= value <= PER_POINT_5H_MAX else None


def share_row(job, cfg=None, per_point=None, per_point_5h=None):
    """The exact line sent for a finished job: format, Quotient version, model family, raw estimate and
    real cost (rounded to 3 significant digits). Nothing else: no date, no text, no path, no session or
    user id. None if implausible. From 0.9.5 the real cost is the work (what the estimate is about),
    without re-reading an older chat; the version in the line tells the two apart. 1.1.6: with cfg, also the plan
    (only if the user chose one) and the size of 1% of the week learned here (per_point, when known); 1.1.7: and of
    the 5 hours (per_point_5h, when known)."""
    try:
        estimate, actual = round3(float(job["raw_estimate"])), round3(float(q_costs.work_of(job)))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (1000 <= estimate <= 100000000 and 1000 <= actual <= 100000000 and 0.1 <= actual / estimate <= 10):
        return None
    family = job.get("family") if job.get("family") in q_costs.FAMILY_NAMES else "other"
    row = {"v": 1, "q": q_settings.VERSION, "family": family, "estimate": estimate, "actual": actual}
    if cfg is not None and cfg.get("subscription") in PLANS:
        row["plan"] = cfg["subscription"]
    if per_point and PER_POINT_MIN <= int(per_point) <= PER_POINT_MAX:
        row["per_point"] = int(per_point)
    if per_point_5h and PER_POINT_5H_MIN <= int(per_point_5h) <= PER_POINT_5H_MAX:
        row["per_point_5h"] = int(per_point_5h)
    return row


def share_enabled(cfg):
    if os.environ.get("QUOTIENT_SHARE", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return bool(cfg["share"].get("enabled"))


def share_active(cfg):
    """Lines are queued only when sharing is on AND the user has been told (the notice was shown)."""
    return share_enabled(cfg) and bool(cfg["share"].get("notice_shown"))


def outbox_path():
    return os.path.join(q_settings.home(), "share-outbox.jsonl")


def write_outbox(rows):
    path = outbox_path()
    if not rows:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for row in rows[-OUTBOX_MAX:]:
            f.write(json.dumps(row) + "\n")
    os.replace(tmp, path)


def queue_share(job, cfg):
    """Put the finished job's line in the outbox. It leaves at the next session start, never in the
    middle of a reply. With sharing off, or before the notice was shown, nothing is queued."""
    if not share_active(cfg):
        return share_row(job, cfg)
    row = share_row(job, cfg, learned_per_point(cfg), learned_per_point_5h(cfg))
    if row:
        q_settings.append_jsonl(outbox_path(), row)
    return row


def allowed_url(url):
    """Only HTTPS (plain HTTP only to this computer, for tests)."""
    url = (url or "").lower()
    return url.startswith("https://") or url.startswith("http://127.0.0.1")


def http(method, url, body=None, timeout=3, most=262144):
    """A plain HTTPS request: no cookies, no identifying headers, at most 256 KB read (or `most` bytes) within a time
    limit. Returns (status, body) or (None, b"")."""
    if not allowed_url(url):
        return None, b""
    data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    headers = {"User-Agent": "quotient"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    end = time.time() + 3 * timeout
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            chunks, size = [], 0
            while size < most and time.time() < end:
                chunk = resp.read(16384)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            return resp.status, b"".join(chunks)
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, b""
    except Exception:  # no network, a slow or broken answer: never an error for the user
        return None, b""


def flush_share(cfg, deadline):
    """Send the waiting lines; returns how many were accepted. With sharing off the waiting lines are
    deleted, never sent. Without an endpoint, or when the service does not answer, they wait."""
    rows = q_settings.read_jsonl(outbox_path())
    if not rows:
        return 0
    if not share_enabled(cfg):
        write_outbox([])
        return 0
    endpoint = (cfg["share"].get("endpoint") or "").rstrip("/")
    if not endpoint or not allowed_url(endpoint):
        return 0
    sent, left = 0, []
    for i, row in enumerate(rows):
        if time.time() > deadline:
            left = rows[i:]
            break
        line = {k: row.get(k) for k in SHARE_FIELDS}
        line.update({k: row[k] for k in SHARE_OPTIONAL if row.get(k) is not None})
        status, _ = http("POST", endpoint + "/v1/jobs", line, cfg["share"].get("timeout", 3))
        for older in SHARE_OLDER:
            # a service not updated yet refuses the fields it does not know (400): the line goes again without them,
            # first as a 1.1.6 service takes it (plan, per_point), then with the five fields only
            fewer = {k: v for k, v in line.items() if k in SHARE_FIELDS or k in older}
            if status != 400 or len(fewer) == len(line):
                continue
            line = fewer
            status, _ = http("POST", endpoint + "/v1/jobs", line, cfg["share"].get("timeout", 3))
        if status is None or status == 429 or status >= 500:
            left = rows[i:]
            break
        if status < 300:
            sent += 1
        # any other answer (400: not acceptable) drops the line: sending it again would not change it
    write_outbox(left)
    state = q_settings.load_json(os.path.join(q_settings.home(), "share-state.json"), {})
    state["sent"] = state.get("sent", 0) + sent
    q_settings.save_json(os.path.join(q_settings.home(), "share-state.json"), state)
    return sent


def fetch_average(cfg, deadline):
    """Once a day, download the shared average: from GitHub, or from the service if GitHub does not
    answer. Done whether sharing is on or off: people who do not share still get everyone's average.
    Only a clean copy (numbers only) is kept."""
    state_path = os.path.join(q_settings.home(), "share-state.json")
    state = q_settings.load_json(state_path, {})
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("checked") == today:
        return False
    state["checked"] = today
    q_settings.save_json(state_path, state)
    endpoint = (cfg["share"].get("endpoint") or "").rstrip("/")
    for url in (cfg["share"].get("average_url"), endpoint + "/v1/average" if endpoint else None):
        if not url or time.time() > deadline:
            continue
        status, body = http("GET", url, timeout=cfg["share"].get("timeout", 3))
        if status != 200:
            continue
        try:
            avg = q_learning.check_average(json.loads(body.decode("utf-8")))
        except Exception:  # broken or hostile file: ignored
            avg = None
        if avg and avg.get("all"):
            q_settings.save_json(q_learning.average_path(), avg)
            return True
    return False


def plan_status(cfg):
    """The line of share_status on the plan's shared sizes (1.1.6 the week, 1.1.7 the 5 hours too)."""
    p = q_learning.plan_average(cfg)
    if not p:
        return "By plan: %s." % ("choose your plan in /token-quotient:setup" if cfg.get("subscription") not in PLANS
                                 else "no shared size for your plan yet")
    parts = ["1%% of %s holds about %s wt for its users (%d jobs)" % (label, q_quotes.fmt(p["per_point" + end]), p["jobs" + end])
             for end, label in (("", "the week"), ("_5h", "the 5 hours")) if p.get("per_point" + end)]
    return ("Your plan (%s): %s; an estimate from other users, with its margin, used until this PC has its own "
            "readings." % (cfg.get("subscription"), ", ".join(parts)))


def share_status(cfg):
    on = share_enabled(cfg)
    active = share_active(cfg)
    state = q_settings.load_json(os.path.join(q_settings.home(), "share-state.json"), {})
    waiting = len(q_settings.read_jsonl(outbox_path()))
    avg = q_learning.shared_average()
    example = share_row({"raw_estimate": 225000, "actual": 259311, "family": "opus"}, cfg, learned_per_point(cfg),
                        learned_per_point_5h(cfg))
    lines = [
        "Sharing: %s." % ("ON (the default)" if active else "ON, it starts after the notice is shown" if on else "OFF"),
        "What is sent after each finished job, and nothing else (no date, no text, no path, no id):",
        "  " + json.dumps(example, separators=(",", ":")),
        "  (plan: only if you chose it, now %s; per_point and per_point_5h: the weighted tokens in 1%% of your week and "
        "of your 5 hours, when known)" % (cfg.get("subscription") or "not said"),
        "Lines sent so far: %d. Lines waiting to be sent: %d." % (state.get("sent", 0), waiting),
        ("Shared average: x%.2f from %d real jobs%s; %s, and held between x0.25 and x4." % (
            avg["all"]["factor"], avg["all"]["jobs"], " (published %s)" % avg["updated"] if avg.get("updated") else "",
            "a part of the factor that weighs less as your own jobs grow, never under %d%%" % round(
                float(cfg["shared_min_weight"]) * 100) if float(cfg.get("shared_min_weight") or 0) > 0 else
            "used until you have %d jobs of your own" % cfg["min_jobs"])
         if avg else "Shared average: not available yet."),
        plan_status(cfg),
        "Turn sharing %s with: share %s (or /token-quotient:share %s). Either way the shared average is downloaded "
        "once a day; to stop that too: config share.average_url \"\" and config share.endpoint \"\"." % (
            ("off", "off", "off") if on else ("on", "on", "on")),
        "Details: https://github.com/Korvonordico/quotient-claude-tokens/blob/main/PRIVACY.md",
    ]
    return "\n".join(lines) + "\n"
