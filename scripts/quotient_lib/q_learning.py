"""The correction factor learned from finished jobs, the shared average, and the environment the jobs ran in."""

import json
import math
import os
import re
import time

from quotient_lib import q_costs, q_limits, q_quotes, q_rates, q_schedules, q_settings, q_sharing

# ---------------------------------------------------------------- learning

def finished_jobs():
    return [j for j in q_settings.read_jsonl(os.path.join(q_settings.home(), "jobs.jsonl"))
            if j.get("raw_estimate") and j.get("actual")]


def backfill_chat(deadline=None):
    """Jobs measured before 0.9.5 have no chat part: work it out once from their chat's transcript, if it
    is still there (the calls from the start of the job's first turn to its end). Each job is looked at
    once (`chat_checked`), so this costs something only the first time. Returns how many were filled."""
    path = os.path.join(q_settings.home(), "jobs.jsonl")
    jobs = q_settings.read_jsonl(path)
    todo = [j for j in jobs if j.get("chat") is None and not j.get("chat_checked")]
    if not todo:
        return 0
    weights = q_settings.config()["weights"]
    filled = 0
    for job in todo:
        if deadline and time.time() > deadline:
            break
        job["chat_checked"] = True
        sid = str(job.get("session") or "")
        transcript = q_rates.find_transcript(sid) if sid and not sid.startswith("rate:") else None
        if not transcript:
            continue
        begin, end = q_limits.ts_epoch(job.get("started")), q_limits.ts_epoch(job.get("finished"))
        entries = [e for e in q_settings.read_jsonl(transcript) if not e.get("isSidechain")]
        starts = [q_limits.ts_epoch(e.get("timestamp")) for e in entries if q_costs.is_turn_start(e)]
        first = max([s for s in starts if s <= begin + 5] or [0])  # times kept to the second
        inside = [e for e in entries if first <= q_limits.ts_epoch(e.get("timestamp")) <= end + 5]
        calls = q_costs.ordered_calls(inside)
        if not first or not calls:
            continue
        fresh = q_costs.first_context(transcript)
        base = q_costs.prompt_tokens(calls[0]["usage"])
        chat = min(q_costs.chat_part(calls, 0, base, weights), job.get("actual") or 0)
        job.update(chat=chat, older=q_costs.chat_part(calls, fresh, base, weights),
                   work=max(0, (job.get("actual") or 0) - chat), fresh=fresh, base=base,
                   calls=job.get("calls") or len(calls), chat_backfilled=True)
        if job.get("raw_estimate"):
            job["ratio"] = round(job["work"] / job["raw_estimate"], 4)
        filled += 1
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for j in jobs:
            f.write(json.dumps(j, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return filled


def plugin_root():
    return os.path.dirname(os.path.dirname(q_settings.ENTRY_FILE))


def shared_path():
    """Numbers only (estimate, real cost) of real jobs, shipped with the plugin in data/shared.jsonl:
    used only when no shared average (downloaded, or data/average.json shipped with the plugin) is available."""
    return os.path.join(plugin_root(), "data", "shared.jsonl")


def average_path():
    """The shared average downloaded once a day."""
    return os.path.join(q_settings.home(), "average.json")


def bundled_average_path():
    """The copy of the shared average shipped with this version of the plugin."""
    return os.path.join(plugin_root(), "data", "average.json")


FACTOR_MIN, FACTOR_MAX = 0.25, 4.0
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def clean_stats(stats):
    """Only the numbers of one summary, or None if they are missing or implausible."""
    if not isinstance(stats, dict):
        return None
    try:
        clean = {"jobs": int(stats.get("jobs") or 0), "factor": float(stats.get("factor") or 0)}
        for k in ("p25", "p75"):
            if stats.get(k) is not None:
                clean[k] = float(stats[k])
    except (TypeError, ValueError, OverflowError):
        return None
    if not 1 <= clean["jobs"] <= 10 ** 9:
        return None
    if not all(math.isfinite(v) and 0.02 <= v <= 50 for k, v in clean.items() if k != "jobs"):
        return None
    return clean


def check_average(data):
    """A clean copy of the average file: the schema, the day it was published, and numbers only.
    Anything else in the file (text, unknown keys, unknown families) is dropped, so nothing but
    numbers from it ever reaches Claude. None if the shape or the numbers are wrong."""
    if not isinstance(data, dict) or data.get("schema") != 1:
        return None
    day = data.get("updated")
    clean = {"schema": 1, "updated": day if isinstance(day, str) and DAY_RE.match(day) else None, "all": None,
             "families": {}}
    if data.get("all") is not None:
        clean["all"] = clean_stats(data["all"])
        if clean["all"] is None:
            return None
    families = data.get("families") or {}
    if not isinstance(families, dict):
        return None
    for name, stats in families.items():
        if name in q_costs.FAMILY_NAMES or name == "other":
            s = clean_stats(stats)
            if s is None:
                return None
            clean["families"][name] = s
    plans = data.get("plans") or {}
    if isinstance(plans, dict):
        # 1.1.6: the size of 1% of the week by plan; a plan whose numbers are wrong is left out, the rest is kept
        for name, stats in plans.items():
            s = clean_plan(stats) if name in q_sharing.PLANS else None
            if s:
                clean.setdefault("plans", {})[name] = s
    return clean


def clean_plan(stats):
    """The numbers of one plan in the shared average (1.1.6): jobs, and the wt in 1% of the week with its middle half;
    1.1.7: the same for the 5 hours (jobs_5h, per_point_5h, p25_5h, p75_5h), which a 1.1.6 copy does not read. Each
    window is kept only when its numbers are plausible; None if neither is."""
    if not isinstance(stats, dict):
        return None
    clean = {}
    for end, low, high in (("", q_sharing.PER_POINT_MIN, q_sharing.PER_POINT_MAX), ("_5h", q_sharing.PER_POINT_5H_MIN, q_sharing.PER_POINT_5H_MAX)):
        try:
            part = {"jobs" + end: int(stats.get("jobs" + end) or 0), "per_point" + end: float(stats.get("per_point" + end) or 0)}
            for k in ("p25" + end, "p75" + end):
                if stats.get(k) is not None:
                    part[k] = float(stats[k])
        except (TypeError, ValueError, OverflowError):
            continue
        if not 1 <= part["jobs" + end] <= 10 ** 9:
            continue
        if all(math.isfinite(v) and low <= v <= high for k, v in part.items() if not k.startswith("jobs")):
            clean.update(part)
    return clean or None


def plan_average(cfg=None):
    """The shared size of 1% of the week (1.1.6) and of the 5 hours (1.1.7) for the user's plan, or None (no plan
    chosen, or not published)."""
    cfg = cfg or q_settings.config()
    plan = cfg.get("subscription")
    if plan not in q_sharing.PLANS:
        return None
    avg = shared_average()
    return ((avg or {}).get("plans") or {}).get(plan)


def shared_average():
    """The downloaded shared average, or else the copy shipped with the plugin."""
    for path in (average_path(), bundled_average_path()):
        avg = check_average(q_settings.load_json(path, None))
        if avg and avg.get("all"):
            return avg
    return None


def shared_factor(jobs):
    """The shared average's factor and how many real jobs are behind it, or None: the one of your model family if it
    has one, else of all jobs, held between x0.25 and x4: anyone can send numbers, so it is not trusted further."""
    avg = shared_average()
    if not avg:
        return None
    family = jobs[-1].get("family") if jobs else None
    stats = (avg.get("families") or {}).get(family) or avg["all"]
    return min(max(float(stats["factor"]), FACTOR_MIN), FACTOR_MAX), int(stats["jobs"])


def shared_prior(cfg, jobs):
    """What stands for other people's jobs until you have enough of your own: rows for the
    factor, and how many real jobs are behind them. The shared average counts as at most
    min_jobs jobs at its factor (with shared_min_weight 0: otherwise see shared_mix)."""
    found = shared_factor(jobs)
    if found:
        factor, n = found
        row = {"raw_estimate": 1000000, "actual": round(1000000 * factor), "finished": "",
               "choice": "shared", "shared": True}
        return [dict(row) for _ in range(min(n, cfg["min_jobs"]))], n
    rows = shared_jobs(jobs)
    return rows, len(rows)


def shared_weight(cfg, n, started=False):
    """1.2.3: how much the shared average weighs next to n of your jobs: nearly all at first, less and less as they
    grow, never under shared_min_weight. With start rows (`started`), just the minimum: 1.1.9 measured those rows on
    clean jobs (x0.58) and they, not the average of all jobs (x1.18 on 21/10/2026), are what a new user starts from."""
    least = float(cfg.get("shared_min_weight") or 0)
    k = max(int(cfg["min_jobs"]), 1)
    return least if started else max(least, k / float(k + n))


def shared_mix(own, shared, weight):
    """1.2.3: your factor and the shared one, weighted on a log scale, so x2 and /2 weigh the same (as in factor_from)."""
    mixed = math.exp(weight * math.log(shared) + (1 - weight) * math.log(own))
    return min(max(mixed, FACTOR_MIN), FACTOR_MAX)


def shared_jobs(own=()):
    seen = {(j.get("raw_estimate"), j.get("actual")) for j in own}
    rows = []
    for r in q_settings.read_jsonl(shared_path()):
        if r.get("raw_estimate") and r.get("actual") and (r["raw_estimate"], r["actual"]) not in seen:
            rows.append({"raw_estimate": r["raw_estimate"], "actual": r["actual"], "finished": r.get("date", ""),
                         "choice": "shared", "shared": True})
    return rows


def teaches(job, cfg):
    """Does this finished job teach the factor? Installments always do. A chat job does not when its quote is under
    learn_min_raw (Francesco, 15/10/2026: small jobs are noise, unless it is an installment he decided) or when its
    work went faster than learn_max_speed wt a second: on 11-12/10 three jobs did 0.5-6 M wt in 2-8 minutes, 4-27
    times the usual pace (about 1,000 wt a second), and pushed the factor from x1.49 to x1.58."""
    if kind_of(job) == "rate":
        return True
    if cfg.get("learn_min_raw") and job.get("raw_estimate", 0) < cfg["learn_min_raw"]:
        return False
    return not too_fast(job, cfg)


def too_fast(job, cfg):
    seconds = job.get("seconds") or 0
    own = q_costs.work_of(job) - (job.get("claude") or 0)   # hermes branch: Claude Code runs work in parallel: the chat's own pace
    return bool(cfg.get("learn_max_speed") and seconds > 0 and own / seconds > cfg["learn_max_speed"])


def mid_band(cfg, raw):
    """Is a quote in the medium band (learn_mid_min up to learn_min_raw)?"""
    return bool(cfg.get("learn_mid_min") and cfg.get("learn_min_raw") and cfg["learn_mid_min"] <= (raw or 0) < cfg["learn_min_raw"])


def mid_factor(cfg):
    """The medium jobs' own factor (hermes branch; Francesco, 15/10/2026): with only the jobs quoted from 1M up teaching the
    factor, the ones quoted between 500k and 1M (about x1.8 on the median of 10) would be corrected by x1.05. None
    until there are min_jobs of them."""
    if not (cfg.get("learn_mid_min") and cfg.get("learn_min_raw")):
        return None
    jobs = [j for j in finished_jobs() if kind_of(j) == "chat" and mid_band(cfg, j.get("raw_estimate"))
            and not too_fast(j, cfg) and (not cfg.get("learn_clean_only") or is_clean(j, cfg))]   # 1.1.9: clean only
    return factor_from(jobs, cfg["history_window"]) if len(jobs) >= cfg["min_jobs"] else None


def claude_runs_text(cfg):
    """For the protocol (hermes branch): the Claude Code runs a job starts are in its measured cost, so in its estimate."""
    return (" The Claude Code runs (claude -p) the job starts, directly or through a script, are counted in its cost "
            "when it closes: put them in the estimate." if cfg.get("claude_runs") else "")


def mid_text(cfg, factor):
    m = mid_factor(cfg)
    if not m:
        return ""
    top = cfg["learn_min_raw"]
    end = blend_end(cfg, m, factor)
    if end <= top:
        return "; for quotes under %s wt x%.2f" % (q_quotes.fmt(top), m)
    return ("; for quotes under %s wt x%.2f; from it up to %s along a straight line to the factor, then the factor "
            "(so a bigger level always comes out bigger)" % (q_quotes.fmt(top), m, q_quotes.fmt(end)))


def blend_end(cfg, mid, big):
    """Where the line from the medium band reaches the factor (learn_blend_raw, 1.1.7). Made longer when it would rise
    less than half as fast as the factor: R x big - top x mid = (R - top) x big / 2 gives R = top x (2 x mid / big - 1)."""
    top = cfg.get("learn_min_raw") or 0
    end = cfg.get("learn_blend_raw", q_settings.DEFAULTS["learn_blend_raw"]) or 0
    if big < mid:
        end = max(end, top * (2.0 * mid / big - 1))
    return end


def chat_origin():
    """Where a chat job is quoted from: Hermes gives its session id to all it starts."""
    return "hermes" if os.environ.get("HERMES_SESSION_ID") else "claude"


def same_origin(job, origin):
    return (job.get("source") == "hermes") == (origin == "hermes")


def chat_jobs_measured(origin=None):
    """The finished chat jobs of one origin, oldest first (`finished_jobs` keeps the order)."""
    origin = origin or chat_origin()
    return [j for j in finished_jobs() if kind_of(j) == "chat" and j.get("raw_estimate") and q_costs.work_of(j) > 0
            and same_origin(j, origin)]


def own_chat_factor(cfg, origin=None):
    """Improvement 4 (chat.own_factor_mix): the median of all the recent chat jobs of this origin; None when off or
    under min_jobs."""
    if not (cfg.get("chat") or {}).get("own_factor_mix"):
        return None
    jobs = chat_jobs_measured(origin)
    return factor_from(jobs, cfg["history_window"]) if len(jobs) >= cfg["min_jobs"] else None


def chat_steps(cfg, raw, usual, origin=None):
    """Improvement 4 (chat.steps_history): the steps of a chat job quoted at raw, from the measured jobs of the same
    origin and size: (steps, prudent). None when off. With too few of them, at least chat.steps_start, said in the quote."""
    opts = cfg.get("chat") or {}
    if not opts.get("steps_history"):
        return None
    bands = sorted(opts.get("steps_bands") or [])

    def band(value):
        return sum(1 for limit in bands if value >= limit)
    rows = [j["calls"] for j in chat_jobs_measured(origin) if j.get("calls") and band(j["raw_estimate"]) == band(raw)]
    rows = rows[-cfg["history_window"]:]
    if len(rows) >= int(opts.get("steps_min_jobs") or 1):
        return median(rows), False
    return max(usual, float(opts.get("steps_start") or 0)), True


def factor_for(cfg, raw, source):
    """The factor a chosen level is corrected with: of its size (band_factor), halfway to the factor of all the chat
    jobs when there is one (improvement 4, chat.own_factor_mix)."""
    factor = band_factor(cfg, raw, source)
    own = source.get("factor_own")
    return math.sqrt(factor * own) if own and factor > 0 else factor


def band_factor(cfg, raw, source):
    """The factor of a level by its size. With the medium band on and its factor known: under learn_min_raw
    the medium factor, smaller quotes too (they teach no factor: the nearest learned one); from learn_min_raw up to
    learn_blend_raw a straight line from learn_min_raw x the medium factor to learn_blend_raw x the factor; from there
    up the factor alone (1.1.7).
    Francesco, 16/10/2026: with plain bands a quote of 999k was corrected to 1.84M and one of 1M to 1.05M; then with
    max(factor, learn_min_raw x mid / raw) every quote from 1M to about 1.7M came out the same (good 1.1M and max 1.6M
    both 1.75M); then in brackets (the first learn_min_raw at the medium factor, the rest at the factor) every job
    above 1M carried 731k more than its factor, and he chose the line: big jobs go back to their factor. The line is
    continuous at both ends and always rises (at least half as fast as the factor), whichever factor is the larger."""
    mid, big = source.get("factor_mid"), source.get("factor", 1.0)
    top = cfg.get("learn_min_raw") or 0
    if not mid or not cfg.get("learn_mid_min") or not top:
        return big
    if (raw or 0) < top:
        return mid
    end = blend_end(cfg, mid, big)
    if raw >= end:
        return big
    return (top * mid + (raw - top) * (end * big - top * mid) / (end - top)) / raw


def chat_factor(cfg, raw, wtype=None, origin=None):
    """The factor a chat job quoted at raw is corrected with: its type of work's factor (1.1.4), the general one
    until the type has its jobs, and the medium band. Under learn_min_raw the band's factor is the same for every type:
    the types learn only from the jobs that teach the factor."""
    return factor_for(cfg, raw, {"factor": learning(cfg, "chat", wtype)["factor"], "factor_mid": mid_factor(cfg),
                                 "factor_own": own_chat_factor(cfg, origin)})


def factor_from(jobs, window, since=None, weight=1, least=3):
    """Median ratio real/estimate of the recent jobs (geometric, so x2 and /2 weigh the same). The real cost
    is the work: re-reading an older chat is not part of what the estimate is about. 1.1.4: `since` is the last change
    of the environment (plugins, MCP servers, hooks): once `least` of the recent jobs finished after it, each of those
    counts `weight` times, so the factor follows what a job costs now without forgetting the jobs before."""
    recent = jobs[-window:]
    newer = [j for j in recent if since and q_limits.ts_epoch(j.get("finished")) > since]
    times = max(1, int(weight)) if len(newer) >= max(1, int(least)) else 1
    logs = []
    for j in recent:
        logs += [math.log(max(q_costs.work_of(j), 1) / j["raw_estimate"])] * (times if j in newer else 1)
    if not logs:
        return 1.0
    logs.sort()
    mid = len(logs) // 2
    med = logs[mid] if len(logs) % 2 else (logs[mid - 1] + logs[mid]) / 2
    return math.exp(med)


def is_clean(job, cfg):
    """1.1.9: a job where the user wrote nothing during the work: at most clean_max_turns replies (the replies counted
    apart with ASIDE are not in them). Only chat jobs: an installment's turns are its runs."""
    return kind_of(job) == "chat" and (job.get("turns") or 1) <= int(cfg.get("clean_max_turns") or 1)


def miss(ratio):
    """How far off, as a factor >= 1: x2 too low and x2 too high both give 2."""
    return max(ratio, 1 / ratio) if ratio > 0 else float("inf")


def median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def kind_of(job):
    """'rate' for an installment job, 'chat' for the others. The two are learned apart (14/10/2026): the chat jobs'
    factor, applied to installments, made their corrected estimates wrong by up to x27 and their daily caps too low,
    while their raw estimates were right on the median."""
    return "rate" if str(job.get("session") or "").startswith("rate:") else "chat"


def job_type(job):
    """The type of work of a job (1.1.4): code, writing, research or other; a job measured before 1.1.4 is 'other'."""
    t = job.get("type")
    return t if t in q_settings.WORK_TYPES else "other"


def steps_per_million(cfg, kind="chat"):
    """How many steps (calls) a job of this kind takes per million wt of work: (median of its recent jobs that
    counted them, how many), or None under 3 of them. 14/10/2026: the chat part of a quote is steps x what each step
    re-reads, and the steps were guessed, far too few (the user's messages in between, the checks)."""
    rows = [j for j in finished_jobs() if kind_of(j) == kind and j.get("calls") and q_costs.work_of(j) > 0]
    rows = rows[-cfg["history_window"]:]
    if len(rows) < 3:
        return None
    return median([j["calls"] / q_costs.work_of(j) * 1e6 for j in rows]), len(rows)


def learning(cfg, kind="chat", wtype=None):
    """The correction factor of one kind of job (chat jobs or installments): from your own jobs of that kind; with
    fewer than min_jobs of them, from all your jobs; until you have min_jobs jobs in all, with the shared ones too
    (1.2.3, with shared_min_weight: the shared average stays a part of the factor for good, see shared_weight).
    1.1.4: with a type of work (code, writing, research, other), from the jobs of that type and kind once there are
    type_min_jobs of them; and the jobs after the last change of the environment weigh more (see factor_from).
    v118: with learn_rate_all on, the installments learn from all the jobs, of both kinds and every type."""
    jobs = finished_jobs()
    window = cfg["history_window"]
    shared, shared_n = shared_prior(cfg, jobs)
    mixing = shared_factor(jobs) if float(cfg.get("shared_min_weight") or 0) > 0 else None
    least = int(cfg.get("type_min_jobs") or 3)
    env = q_settings.merge(q_settings.DEFAULTS["env"], cfg.get("env") or {})
    changes = env_change_epochs()
    rate_all = bool(cfg.get("learn_rate_all"))
    clean_on = bool(cfg.get("learn_clean_only"))
    start = float(cfg.get("start_factor") or 0)

    def tidy(done):
        """1.1.9: the clean chat jobs that teach (learn_clean_only)."""
        return [j for j in done if kind_of(j) == "chat" and teaches(j, cfg) and is_clean(j, cfg)]

    starts = cfg.get("start_factors") or {}

    def prior(k, done, t=None):
        """What stands for jobs not there yet: 1.1.9, with learn_clean_only and start_factor, rows at the start of the
        type (start_factors, else start_factor) up to min_jobs clean chat jobs of that type (of any type without one);
        otherwise the shared average while there are fewer than min_jobs jobs in all."""
        if clean_on and start > 0 and k == "chat":
            base = float(starts.get(t) or start) if t else start
            have = [j for j in tidy(done) if not t or job_type(j) == t]
            row = {"raw_estimate": 1000000, "actual": round(1000000 * base), "finished": "", "choice": "start",
                   "shared": True}
            return [dict(row) for _ in range(max(0, cfg["min_jobs"] - len(have)))]
        return shared if len(done) < cfg["min_jobs"] and not mixing else []   # 1.2.3: mixing, it is not rows

    def since(at):
        before = [c for c in changes if c <= at]
        return before[-1] if before else None

    def own(k, done, t=None):
        if k == "rate" and rate_all:
            return list(done)   # v118: every finished job teaches the installments (learn_rate_all)
        if clean_on and k == "chat":
            done = tidy(done)   # 1.1.9 (learn_clean_only): the chat factor learns from the clean chat jobs only
            if t and start > 0:
                return [j for j in done if job_type(j) == t]   # its own type, the start rows fill the rest (prior)
            if t:
                typed = [j for j in done if job_type(j) == t]
                if len(typed) >= least:
                    return typed
            return done
        done = [j for j in done if teaches(j, cfg)]   # hermes branch: only the jobs that teach
        same = [j for j in done if kind_of(j) == k]
        if t:
            typed = [j for j in same if job_type(j) == t]
            if len(typed) >= least:
                return typed
        return same if len(same) >= cfg["min_jobs"] else done

    def factor(rows, at):
        return factor_from(rows, window, since(at), env["weight"], env["min_jobs"])

    def weight_of(k, done, t=None):
        """1.2.3: how much the shared average weighs for this kind of job, or None when it is not mixed in."""
        return shared_weight(cfg, len(own(k, done, t)), clean_on and start > 0 and k == "chat") if mixing else None

    def estimate(k, done, at, t=None):
        """The factor of one kind of job from what was done so far; 1.2.3: with the shared average mixed in."""
        value = factor(prior(k, done, t) + own(k, done, t), at)
        return shared_mix(value, mixing[0], weight_of(k, done, t)) if mixing else value

    rows = []
    for i, job in enumerate(jobs):
        at = q_limits.ts_epoch(job.get("started")) or q_limits.ts_epoch(job.get("finished"))
        before = estimate(kind_of(job), jobs[:i], at, job.get("type"))
        corrected = job["raw_estimate"] * before
        work = max(q_costs.work_of(job), 1)
        rows.append({
            "job": job,
            "factor_before": before,
            "corrected": corrected,
            "work": work,
            "chat": job.get("chat"),
            "miss_raw": miss(work / job["raw_estimate"]),
            "miss_corrected": miss(work / corrected),
        })
    start_rows = prior(kind, jobs, wtype) if clean_on and start > 0 and kind == "chat" else []
    use_shared = bool(mixing) or (len(jobs) < cfg["min_jobs"] and not (clean_on and start > 0 and kind == "chat"))
    every = kind == "rate" and rate_all
    clean = clean_on and kind == "chat"
    type_jobs = sum(1 for j in (tidy(jobs) if clean else jobs) if kind_of(j) == kind and job_type(j) == wtype
                    and teaches(j, cfg)) if wtype and not every else 0
    return {"jobs": jobs, "rows": rows, "factor": estimate(kind, jobs, time.time(), wtype), "kind": kind,
            "shared_weight": weight_of(kind, jobs, wtype),
            "kind_jobs": len(jobs) if every else (len(tidy(jobs)) if clean else
                                                  sum(1 for j in jobs if kind_of(j) == kind and teaches(j, cfg))),
            "clean": clean, "start_rows": len(start_rows),
            "type": wtype, "type_jobs": type_jobs, "all": every,
            "typed": bool(wtype) and (type_jobs >= least or bool(clean and start > 0 and starts.get(wtype))),
            "shared": shared_n if use_shared and shared else 0}


def type_factors(cfg, kind="chat"):
    """The factor of each type of work of one kind that has jobs: [(type, factor, jobs, its own)], 'its own' False
    while the type has fewer than type_min_jobs and uses the general factor."""
    found = []
    for t in q_settings.WORK_TYPES:
        learned = learning(cfg, kind, t)
        if learned["type_jobs"]:
            found.append((t, learned["factor"], learned["type_jobs"], learned["typed"]))
    return found


# ---------------------------------------------------------------- the environment, and the work done elsewhere (1.1.4)
# 15/10/2026, the user: "Se c'è gente che non lavora in ordine, Quotient deve capire cosa lavora come lavoro di Quotient
# e cosa lavora da un'altra parte, magari mentre installa altre cose che usano comunque token." Each closed job and each
# installment keeps the names of the plugins, MCP servers and hooks around it (names only, never their settings), so a
# change shows in the report; and what other sessions spent while it ran.

SCRIPT_RE = re.compile(r"[\w.-]+\.(?:ps1|py|sh|js|mjs|cjs|ts|cmd|bat|exe)\b", re.I)


def claude_dir():
    """Claude Code's folder of settings (CLAUDE_CONFIG_DIR, else ~/.claude); QUOTIENT_CLAUDE_DIR for the tests."""
    return (os.environ.get("QUOTIENT_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR") or
            os.path.join(os.path.expanduser("~"), ".claude"))


def hook_names(hooks):
    """'Event:script' for each hook command of a settings file: the name of the script it runs, never its arguments."""
    names = set()
    for event, groups in hooks.items() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for h in (group.get("hooks") or []) if isinstance(group, dict) else []:
                if not isinstance(h, dict):
                    continue
                command = " ".join([str(h.get("command") or "")] + [str(a) for a in h.get("args") or []])
                files = SCRIPT_RE.findall(command)
                first = os.path.basename(command.strip().split(" ")[0].strip("\"'")) if command.strip() else ""
                names.add("%s:%s" % (event, files[-1] if files else first or h.get("type") or "?"))
    return sorted(names)


def yaml_block(text, key):
    """The lines of one top-level block of a simple YAML file (Hermes' config), comments left out: no YAML library."""
    lines, inside = [], False
    for line in (text or "").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            inside = line.split(":")[0].strip() == key
            continue
        if inside:
            lines.append(line.split(" #")[0].rstrip())
    return lines


def yaml_keys(lines):
    """The keys at the first level of a block."""
    if not lines:
        return []
    least = min(len(l) - len(l.lstrip()) for l in lines)
    return [l.strip().split(":")[0].strip("\"'") for l in lines
            if len(l) - len(l.lstrip()) == least and ":" in l and not l.strip().startswith("-")]


def yaml_list(lines, key):
    """The items of a list under a key of a block: `enabled: [a, b]` or `enabled:` then `- a` lines."""
    found, inside, depth = [], False, 0
    for l in lines:
        indent, s = len(l) - len(l.lstrip()), l.strip()
        if inside and (s.startswith("- ") or s == "-") and indent >= depth:
            found.append(s[1:].strip().strip("\"'"))
            continue
        inside = False
        if s.split(":")[0].strip() == key:
            rest = s.split(":", 1)[1].strip()
            if rest.startswith("["):
                found += [x.strip().strip("\"'") for x in rest.strip("[]").split(",") if x.strip()]
            else:
                inside, depth = True, indent
    return found


def hermes_env(cfg=None):
    """Hermes' plugins, MCP servers and hooks, from its config (names only), or {} when Hermes is not counted."""
    cfg = cfg or q_settings.config()
    if not cfg.get("hermes", True) or os.environ.get("QUOTIENT_HERMES") == "0":
        return {}
    try:
        import hermes_source as hs
        text = q_schedules.load_text(os.path.join(hs.hermes_home(), "config.yaml"))
    except Exception:
        return {}
    if not text:
        return {}
    hooks = yaml_block(text, "hooks")
    names, event = [], None
    least = min([len(l) - len(l.lstrip()) for l in hooks] or [0])
    for l in hooks:
        if len(l) - len(l.lstrip()) == least and l.strip().endswith(":"):
            event = l.strip()[:-1]
        elif event and "command" in l:
            files = SCRIPT_RE.findall(l)
            names.append("%s:%s" % (event, files[-1] if files else "?"))
    return {"hermes_plugins": sorted(set(yaml_list(yaml_block(text, "plugins"), "enabled"))),
            "hermes_mcp": sorted(set(yaml_keys(yaml_block(text, "mcp_servers")))),
            "hermes_hooks": sorted(set(names))}


def env_snapshot(cfg=None, cwd=None):
    """The names of what is around the jobs now: Claude Code's enabled plugins, MCP servers (the user's, this folder's)
    and hooks, and Hermes' (see hermes_env). Names only: no command line, no setting, no secret."""
    base = claude_dir()
    snap = {"plugins": set(), "mcp": set(), "hooks": set()}
    for name in ("settings.json", "settings.local.json"):
        s = q_settings.load_json(os.path.join(base, name), {})
        if not isinstance(s, dict):
            continue
        plugins = s.get("enabledPlugins")
        if isinstance(plugins, dict):
            snap["plugins"].update(k for k, v in plugins.items() if v)
        snap["hooks"].update(hook_names(s.get("hooks")))
    custom = os.environ.get("QUOTIENT_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
    user = q_settings.load_json(os.path.join(base if custom else os.path.expanduser("~"), ".claude.json"), {})
    here = os.path.normcase(os.path.abspath(cwd or os.getcwd()))
    if isinstance(user, dict):
        snap["mcp"].update((user.get("mcpServers") or {}).keys() if isinstance(user.get("mcpServers"), dict) else ())
        for path, project in (user.get("projects") or {}).items() if isinstance(user.get("projects"), dict) else []:
            if isinstance(project, dict) and os.path.normcase(os.path.abspath(path)) == here:
                servers = project.get("mcpServers")
                snap["mcp"].update(servers.keys() if isinstance(servers, dict) else ())
    local = q_settings.load_json(os.path.join(here, ".mcp.json"), {})
    if isinstance(local, dict) and isinstance(local.get("mcpServers"), dict):
        snap["mcp"].update(local["mcpServers"].keys())
    found = {k: sorted(str(x) for x in v) for k, v in snap.items()}
    found.update(hermes_env(cfg))
    return found


def env_sig(snap):
    import hashlib
    return hashlib.sha1(json.dumps(snap, sort_keys=True).encode("utf-8")).hexdigest()[:8]


def env_path():
    return os.path.join(q_settings.home(), "env.jsonl")


def env_changes_path():
    return os.path.join(q_settings.home(), "env-changes.jsonl")


def env_change_epochs():
    return sorted(r["epoch"] for r in q_settings.read_jsonl(env_changes_path()) if r.get("epoch"))


def record_env(cfg=None, cwd=None):
    """At the end of a job or an installment: the signature of the environment now. A new one goes to env.jsonl with
    its names; one different from the last seen is a change (env-changes.jsonl: what was added and removed), dated
    at the last moment the old one was seen, so the job that shows it counts as after it. Returns the signature."""
    snap = env_snapshot(cfg, cwd)
    sig = env_sig(snap)
    known = {r.get("sig"): r for r in q_settings.read_jsonl(env_path())}
    if sig not in known:
        q_settings.append_jsonl(env_path(), dict(snap, sig=sig, first_seen=q_settings.now_iso()))
    state_path = os.path.join(q_settings.home(), "env-state.json")
    last = q_settings.load_json(state_path, {}) or {}
    if last.get("sig") and last["sig"] != sig:
        old = known.get(last["sig"]) or {}
        added, removed = [], []
        for key, names in snap.items():
            before = set(old.get(key) or [])
            added += ["%s %s" % (key, n) for n in names if n not in before]
            removed += ["%s %s" % (key, n) for n in sorted(before - set(names))]
        q_settings.append_jsonl(env_changes_path(), {"epoch": last.get("epoch") or round(time.time()), "seen": q_settings.now_iso(),
                                          "from": last["sig"], "to": sig, "added": added, "removed": removed})
    q_settings.save_json(state_path, {"sig": sig, "epoch": round(time.time())})
    return sig


def env_alert():
    """A change of the environment, told once, at the user's next message in any chat."""
    path = os.path.join(q_settings.home(), "env-told.json")
    told = q_settings.load_json(path, [])
    told = told if isinstance(told, list) else []
    fresh = [c for c in q_settings.read_jsonl(env_changes_path()) if c.get("to") and "%s>%s" % (c.get("from"), c["to"]) not in told]
    if not fresh:
        return None
    q_settings.save_json(path, told + ["%s>%s" % (c.get("from"), c["to"]) for c in fresh])
    c = fresh[-1]
    what = "; ".join(x for x in ("added " + ", ".join(c["added"]) if c.get("added") else "",
                                 "removed " + ", ".join(c["removed"]) if c.get("removed") else "") if x)
    return ("ENVIRONMENT CHANGED (plugins, MCP servers or hooks: %s). From now on the report shows the jobs before and "
            "after the change apart (factor, and cost per 1M wt of work), so it shows what the change saves or costs; "
            "once there are %d jobs after it, they weigh more in the factor. Tell the user in ONE line, in their "
            "language." % (what or "changed", int(q_settings.merge(q_settings.DEFAULTS["env"], q_settings.config().get("env") or {})["min_jobs"])))


def elsewhere_wt(begin, end, own=(), hermes_own=()):
    """What other sessions spent while a job ran: weighted tokens of the Claude Code turns of other chats and
    installments, and of Hermes chats, between its start and its end. Use Quotient cannot see (claude.ai, the phone)
    is not in it."""
    begin, end = float(begin or 0), float(end or 0)
    if not begin or end <= begin:
        return 0
    total = sum(t.get("wt") or 0 for t in q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl"))
                if t.get("session") not in own and begin < q_limits.ts_epoch(t.get("ts")) <= end)
    try:
        import hermes_source as hs
        total += sum(r.get("wt") or 0 for r in hs.read_log(q_settings.home()) if begin < (r.get("epoch") or 0) <= end
                     and r.get("session") not in hermes_own and r.get("parent") not in hermes_own)
    except Exception:
        pass
    return round(total)


def env_periods(cfg, kind="chat"):
    """The jobs of one kind before and after each change of the environment (the last 3 changes): for each, how many,
    their factor and what 1M wt of their work cost in all (work and re-reading)."""
    jobs = [j for j in finished_jobs() if kind_of(j) == kind]
    found = []
    for c in q_settings.read_jsonl(env_changes_path())[-3:]:
        at = c.get("epoch") or 0
        sides = []
        for side in ([j for j in jobs if q_limits.ts_epoch(j.get("finished")) <= at], [j for j in jobs if q_limits.ts_epoch(j.get("finished")) > at]):
            work = sum(q_costs.work_of(j) for j in side)
            sides.append({"jobs": len(side), "factor": factor_from(side, cfg["history_window"]) if side else None,
                          "per_million": sum(j.get("actual") or 0 for j in side) / work * 1e6 if work else None})
        found.append({"change": c, "before": sides[0], "after": sides[1]})
    return found
