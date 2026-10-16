"""Claude Code's own telemetry as a second measure (1.1.6).

Claude Code can send its own counters of tokens and cost (OpenTelemetry, OTLP over HTTP with JSON) to an address of
your choice. Quotient listens for them on this computer only (127.0.0.1) and keeps numbers only: tokens by type, cost in
dollars, model, kind of call (main, subagent, auxiliary), session id and time, in ~/.quotient/otel.jsonl. Never a text,
a prompt, an e-mail or an account id: everything else in the message is dropped as it arrives. Nothing leaves the PC.

The same tokens are counted twice, by Quotient (from the chat files) and by Claude Code (from the answers of the API):
when the two disagree, one of the measures is wrong, and Quotient says so (it never changes the factor by itself).
The calls Claude Code makes on the side (titles, summaries: "auxiliary") are seen only here.

One receiver at a time (the port is the lock); it is started in the background at the start of a session when
telemetry is on, and stops by itself after telemetry.idle_minutes without data.
"""

import gzip
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEEP = {"claude_code.token.usage": "tokens", "claude_code.cost.usage": "cost"}
TYPES = ("input", "output", "cacheRead", "cacheCreation")
SOURCES = ("main", "subagent", "auxiliary")
MAX_BODY = 8 * 1024 * 1024
DEFAULTS = {"enabled": False, "port": 4318, "interval_ms": 30000, "idle_minutes": 120, "percent": 25,
            "min_wt": 100000, "cache_write": "1h"}


def settings(cfg):
    return dict(DEFAULTS, **(cfg.get("telemetry") or {}))


def env_block(port, interval_ms=30000):
    """The exact settings for the "env" block of Claude Code's settings.json: metrics only, as JSON over HTTP, to this
    computer, every interval_ms, as deltas; no events (logs) and no account ids in the metrics."""
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:%d" % int(port),
        "OTEL_METRIC_EXPORT_INTERVAL": str(int(interval_ms)),
        "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "delta",
        "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "false",
    }


def otel_path(home):
    return os.path.join(home, "otel.jsonl")


def life_path(home):
    return os.path.join(home, "otel-receiver.json")


# ---------------------------------------------------------------- reading one OTLP message: numbers only

def _attrs(items):
    """{key: value} of an OTLP attribute list; only plain values (strings, numbers, booleans)."""
    found = {}
    for item in items or []:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        value = item.get("value") or {}
        for kind in ("stringValue", "intValue", "doubleValue", "boolValue"):
            if kind in value:
                found[item["key"]] = value[kind]
                break
    return found


def _number(point):
    for kind in ("asDouble", "asInt"):
        if point.get(kind) is not None:
            try:
                value = float(point[kind])     # int64 values come as strings in JSON
            except (TypeError, ValueError):
                return None
            return value if value == value and abs(value) < 1e15 else None
    return None


def _seconds(nanos):
    try:
        return int(nanos) / 1e9
    except (TypeError, ValueError):
        return None


def rows_from(payload, series=None):
    """One row per data point of the token and cost counters, numbers only. `series` keeps the last value of each
    cumulative series, so a cumulative counter gives what it grew by (a delta counter is taken as it is)."""
    series = {} if series is None else series
    rows = []
    if not isinstance(payload, dict):
        return rows
    for rm in payload.get("resourceMetrics") or []:
        if not isinstance(rm, dict):
            continue
        base = _attrs((rm.get("resource") or {}).get("attributes"))
        for sm in rm.get("scopeMetrics") or []:
            for metric in (sm or {}).get("metrics") or []:
                kind = KEEP.get((metric or {}).get("name"))
                if not kind:
                    continue
                body = metric.get("sum") or metric.get("gauge") or {}
                cumulative = body.get("aggregationTemporality") in (2, "AGGREGATION_TEMPORALITY_CUMULATIVE")
                for point in body.get("dataPoints") or []:
                    if not isinstance(point, dict):
                        continue
                    a = dict(base)
                    a.update(_attrs(point.get("attributes")))
                    value = _number(point)
                    if value is None:
                        continue
                    wtype = a.get("type") if kind == "tokens" else None
                    if kind == "tokens" and wtype not in TYPES:
                        continue
                    source = a.get("query_source")
                    source = source if source in SOURCES else ("other" if source else "")
                    session = str(a.get("session.id") or "")[:64]
                    model = str(a.get("model") or "")[:64]
                    if cumulative:
                        key = (kind, session, model, source, wtype, str(point.get("startTimeUnixNano")))
                        last = series.get(key, 0.0)
                        series[key] = value
                        value = value - last if value >= last else value
                    if value <= 0:
                        continue
                    end = _seconds(point.get("timeUnixNano")) or time.time()
                    row = {"epoch": round(end, 3), "session": session, "model": model, "source": source,
                           "metric": kind, "value": round(value, 6)}
                    start = _seconds(point.get("startTimeUnixNano"))
                    if start and start < end:
                        row["start"] = round(start, 3)
                    if wtype:
                        row["type"] = wtype
                    rows.append(row)
    return rows


# ---------------------------------------------------------------- the receiver

class Handler(BaseHTTPRequestHandler):
    server_version = "quotient"

    def _answer(self, code, body=b"{}"):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        srv = self.server
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._answer(413 if length > MAX_BODY else 400)
            return
        body = self.rfile.read(length)
        path = self.path.split("?")[0].rstrip("/")
        if path in ("/v1/logs", "/v1/traces"):
            self._answer(200)             # accepted and dropped: only the metrics are kept
            return
        if path != "/v1/metrics":
            self._answer(404)
            return
        if "json" not in (self.headers.get("Content-Type") or "application/json").lower():
            srv.life["protobuf"] = srv.life.get("protobuf", 0) + 1   # the protocol must be http/json
            self._answer(415)
            return
        try:
            if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
                body = gzip.decompress(body)
                if len(body) > 8 * MAX_BODY:
                    raise ValueError("too big")
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            self._answer(400)
            return
        with srv.lock:
            rows = rows_from(payload, srv.series)
            if rows:
                with open(otel_path(srv.home), "a", encoding="utf-8") as f:
                    for row in rows:
                        f.write(json.dumps(row, separators=(",", ":")) + "\n")
                srv.life["last_data"] = round(time.time())
                srv.life["points"] = srv.life.get("points", 0) + len(rows)
        self._answer(200)

    def log_message(self, *args):   # quiet: nothing about the requests is written anywhere
        pass


class Server(ThreadingHTTPServer):
    """The port is the lock of the single receiver: never shared (on Windows SO_REUSEADDR would let a second one bind
    the same port, so the port is taken exclusively there)."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def write_life(home, life):
    path = life_path(home)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(life, f)
    os.replace(tmp, path)


def serve(q, port=None, idle_minutes=None, beat=60):
    """Listen on 127.0.0.1:port until telemetry is turned off or no data came for idle_minutes. Returns False at once if
    another receiver already holds the port."""
    cfg = q.config()
    t = settings(cfg)
    port = int(port or t["port"])
    idle = float(t["idle_minutes"] if idle_minutes is None else idle_minutes) * 60
    try:
        srv = Server(("127.0.0.1", port), Handler)
    except OSError:
        return False      # the port is taken: one receiver is enough
    srv.home, srv.series, srv.lock = q.home(), {}, threading.Lock()
    srv.life = {"pid": os.getpid(), "port": port, "started": round(time.time()), "heartbeat": round(time.time()),
                "last_data": None, "points": 0}
    write_life(srv.home, srv.life)
    stop = threading.Event()

    def watch():
        while not stop.wait(beat):
            srv.life["heartbeat"] = round(time.time())
            try:
                write_life(srv.home, srv.life)
                on = settings(q.config())["enabled"]
            except Exception:
                on = True
            if not on or time.time() - max(srv.life["started"], srv.life.get("last_data") or 0) > idle:
                srv.shutdown()
                return

    threading.Thread(target=watch, daemon=True).start()
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        srv.server_close()
        srv.life["stopped"] = round(time.time())
        try:
            write_life(srv.home, srv.life)
        except OSError:
            pass
    return True


def running(home, now=None):
    """The receiver's life file when its heartbeat is recent, else None."""
    life = q_load(life_path(home))
    now = now or time.time()
    if not life or life.get("stopped") or now - (life.get("heartbeat") or 0) > 150:
        return None
    return life


def q_load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def ensure(q, cfg=None):
    """Start the receiver in the background when telemetry is on and none is running (at most one try every 5
    minutes). Fast: a look at a file, and at most one process started. True if one was started."""
    cfg = cfg or q.config()
    t = settings(cfg)
    if not t["enabled"] or os.environ.get("QUOTIENT_TELEMETRY") == "0":
        return False
    home = q.home()
    if running(home):
        return False
    tried_path = os.path.join(home, "otel-start.json")
    tried = (q_load(tried_path) or {}).get("tried") or 0
    if time.time() - tried < 300:
        return False
    q.save_json(tried_path, {"tried": round(time.time())})
    return bool(q.start_detached(["telemetry", "serve"], os.path.join(home, "otel-receiver.log")))


# ---------------------------------------------------------------- the second measure of a job

def weigh(tokens, weights, cache_write="1h"):
    """Weighted tokens from the telemetry's four types. Its cache writes do not say 5 minutes or 1 hour: Claude Code
    writes 1-hour cache in its main work, so they are weighed as that unless telemetry.cache_write says "5m"."""
    write = weights["cache_write_5m"] if cache_write == "5m" else weights["cache_write_1h"]
    return (tokens.get("input", 0) * weights["input"] + tokens.get("output", 0) * weights["output"] +
            tokens.get("cacheRead", 0) * weights["cache_read"] + tokens.get("cacheCreation", 0) * write)


def measure(rows, session, begin, end, weights, cache_write="1h"):
    """What the telemetry saw of one session between begin and end (epochs): weighted tokens, tokens by type, dollars,
    and the part of the calls on the side (auxiliary). None when it saw nothing."""
    tokens, aux, usd, points = {}, {}, 0.0, 0
    for r in rows:
        if r.get("session") != session or not (begin <= (r.get("epoch") or 0) <= end):
            continue
        points += 1
        if r.get("metric") == "cost":
            usd += r.get("value") or 0
        elif r.get("type") in TYPES:
            tokens[r["type"]] = tokens.get(r["type"], 0) + (r.get("value") or 0)
            if r.get("source") == "auxiliary":
                aux[r["type"]] = aux.get(r["type"], 0) + (r.get("value") or 0)
    if not points:
        return None
    return {"wt": round(weigh(tokens, weights, cache_write)), "tokens": {k: round(v) for k, v in tokens.items()},
            "usd": round(usd, 4), "aux_wt": round(weigh(aux, weights, cache_write)), "points": points}


def measured_items(q, cfg):
    """The finished Claude Code jobs and installment runs to set against the telemetry: (key, label, session, begin,
    end, Quotient's wt). Hermes jobs are not Claude Code: left out."""
    items = []
    for job in q.finished_jobs()[-50:]:
        sid = str(job.get("session") or "")
        if not sid or ":" in sid or job.get("source") == "hermes":
            continue
        begin, end = q.ts_epoch(job.get("started")), q.ts_epoch(job.get("finished"))
        if begin and end and job.get("actual"):
            items.append(("job:%s:%s" % (sid, job.get("started")), "job '%s'" % (job.get("choice") or "?"), sid, begin,
                          end, float(job["actual"])))
    base = os.path.join(q.home(), "rate")
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            for n, run in enumerate(q.read_jsonl(os.path.join(base, name, "runs.jsonl")), 1):
                sid = run.get("session")
                begin, end = q.ts_epoch(run.get("started")), q.ts_epoch(run.get("finished"))
                if sid and begin and end and run.get("wt"):
                    items.append(("run:%s:%d" % (name, n), "installment %d of '%s'" % (n, name), sid, begin, end,
                                  float(run["wt"])))
    return items


def checks_path(home):
    return os.path.join(home, "otel-checks.jsonl")


def compare(q, cfg, now=None):
    """Set each finished job and installment against the telemetry, once, when its data has surely arrived (two export
    intervals after its end). Returns the new comparisons."""
    t = settings(cfg)
    now = now or time.time()
    home = q.home()
    done = {r.get("key") for r in q.read_jsonl(checks_path(home))}
    late = 2 * t["interval_ms"] / 1000.0 + 30
    rows = None
    found = []
    for key, label, sid, begin, end, wt in measured_items(q, cfg):
        if key in done or now < end + late:
            continue
        if rows is None:
            rows = q.read_jsonl(otel_path(home))
            if not rows:
                return []
            first = min(r.get("epoch") or now for r in rows)
        if begin < first:
            # older than the telemetry: nothing to set it against, and not looked at again
            q.append_jsonl(checks_path(home), {"key": key, "label": label, "ts": q.now_iso(), "before": True})
            continue
        seen = measure(rows, sid, begin - 5, end + late, cfg["weights"], t["cache_write"])
        row = {"key": key, "label": label, "ts": q.now_iso(), "quotient": round(wt), "telemetry": seen["wt"] if seen
               else None, "usd": seen["usd"] if seen else None, "aux_wt": seen["aux_wt"] if seen else None}
        if seen:
            row["percent"] = round(100.0 * (seen["wt"] - wt) / wt, 1) if wt else None
        q.append_jsonl(checks_path(home), row)
        found.append(row)
    return found


def far(row, cfg):
    t = settings(cfg)
    return (row.get("telemetry") is not None and row.get("percent") is not None and
            abs(row["percent"]) > t["percent"] and max(row["quotient"], row["telemetry"]) >= t["min_wt"])


def alert(q, cfg):
    """One line for the agent when a new comparison is far apart (beyond telemetry.percent, on jobs of telemetry.min_wt
    or more); None otherwise. Quotient changes nothing by itself."""
    if not settings(cfg)["enabled"]:
        return None
    lines = []
    for row in compare(q, cfg):
        if far(row, cfg):
            lines.append("%s: Quotient %s wt, Claude Code's telemetry %s wt (%+.0f%%)" % (
                row["label"], q.fmt(row["quotient"]), q.fmt(row["telemetry"]), row["percent"]))
    if not lines:
        return None
    return ("TELEMETRY CHECK: " + "; ".join(lines) + ". The two measures of the same tokens do not agree: tell the user "
            "in ONE short line, in their language, that one of the two measures may be wrong and that the report "
            "(/token-quotient:report) shows the comparison; Quotient changed nothing.")


WORDS = {
    "en": {"head": "Claude Code's telemetry: %s%s.", "on": "on", "off": "off (telemetry on prints the settings)",
           "listening": ", receiver listening on 127.0.0.1:%s", "stopped": ", receiver not running",
           "both": "  %d job(s) and installment(s) measured by both: Quotient %s wt, telemetry %s wt (%+.0f%%)%s; "
                   "%d beyond %d%%.",
           "aux": ", of which %s wt in calls on the side (auxiliary), seen only by the telemetry",
           "row": "  %s: Quotient %s wt, telemetry %s wt (%+.0f%%), $%.2f.", "none": "  No job measured by both yet."},
    "it": {"head": "Telemetria di Claude Code: %s%s.", "on": "accesa", "off": "spenta (telemetry on stampa le impostazioni)",
           "listening": ", ricevitore in ascolto su 127.0.0.1:%s", "stopped": ", ricevitore fermo",
           "both": "  %d lavori e rate misurati da tutte e due: Quotient %s wt, telemetria %s wt (%+.0f%%)%s; "
                   "%d oltre il %d%%.",
           "aux": ", di cui %s wt in chiamate di contorno (auxiliary), viste solo dalla telemetria",
           "row": "  %s: Quotient %s wt, telemetria %s wt (%+.0f%%), $%.2f.", "none": "  Ancora nessun lavoro misurato da "
                                                                                   "tutte e due."},
}


def report_lines(q, cfg, lang="en"):
    """The comparisons for the report and for `telemetry status`."""
    w = WORDS["it" if lang == "it" else "en"]
    t = settings(cfg)
    life = running(q.home())
    rows = q.read_jsonl(checks_path(q.home()))
    lines = [w["head"] % (w["on"] if t["enabled"] else w["off"],
                          w["listening"] % life.get("port") if life else (w["stopped"] if t["enabled"] else ""))]
    seen = [r for r in rows if r.get("telemetry")]
    if seen:
        total_q = sum(r["quotient"] for r in seen)
        total_t = sum(r["telemetry"] for r in seen)
        aux = sum(r.get("aux_wt") or 0 for r in seen)
        lines.append(w["both"] % (len(seen), q.fmt(total_q), q.fmt(total_t),
                                  100.0 * (total_t - total_q) / total_q if total_q else 0,
                                  w["aux"] % q.fmt(aux) if aux else "", sum(1 for r in seen if far(r, cfg)),
                                  t["percent"]))
        for r in seen[-5:]:
            lines.append(w["row"] % (r["label"], q.fmt(r["quotient"]), q.fmt(r["telemetry"]), r.get("percent") or 0,
                                     r.get("usd") or 0))
    elif t["enabled"]:
        lines.append(w["none"])
    return lines


# ---------------------------------------------------------------- the command

def _settings_file(q):
    return os.path.join(q.claude_dir(), "settings.json")


def cmd(q, args):
    cfg = q.config()
    t = settings(cfg)
    port = int(getattr(args, "port", None) or t["port"])
    what = getattr(args, "what", None) or "status"
    if what == "serve":
        serve(q, port)
        return
    if what == "status":
        compare(q, cfg)
        q.out("\n".join(report_lines(q, cfg, cfg.get("lang"))) + "\n")
        life = q_load(life_path(q.home())) or {}
        if life.get("protobuf"):
            q.out("The receiver got %d message(s) in protobuf: set OTEL_EXPORTER_OTLP_PROTOCOL=http/json.\n"
                  % life["protobuf"])
        q.out("Data points kept: %d (numbers only, in %s).\n" % (len(q.read_jsonl(otel_path(q.home()))),
                                                                otel_path(q.home())))
        return
    block = env_block(port, t["interval_ms"])
    path = _settings_file(q)
    if what == "on":
        if getattr(args, "port", None):
            q.store(("telemetry", "port"), port)
        if not getattr(args, "write", False):
            q.out("Claude Code's own telemetry, as a second measure. Add these lines to the \"env\" block of %s (or run "
                  "telemetry on --write, which makes a copy of the file first):\n%s\nThey send numbers only to this "
                  "computer (127.0.0.1:%d): no prompts (Claude Code leaves them out unless OTEL_LOG_USER_PROMPTS is "
                  "set), no events, no account ids. Quotient keeps tokens, cost, model, session and time. They take "
                  "effect in the next session.\n" % (path, json.dumps(block, indent=2), port))
            q.store(("telemetry", "enabled"), True)
            ensure(q, q.config())
            return
        current = q.load_json(path, {}) if os.path.exists(path) else {}
        if current is None:
            sys.exit("quotient: cannot read %s" % path)
        copy = backup(path)
        current.setdefault("env", {}).update(block)
        save_settings_file(path, current)
        q.store(("telemetry", "enabled"), True)
        ensure(q, q.config())
        q.out("Telemetry set in %s%s. It starts with the next session.\n" % (
            path, " (copy of the file before: %s)" % copy if copy else ""))
        return
    if what == "off":
        q.store(("telemetry", "enabled"), False)
        if getattr(args, "write", False) and os.path.exists(path):
            current = q.load_json(path, None)
            if current is None:
                sys.exit("quotient: cannot read %s" % path)
            env = current.get("env") or {}
            ours = [k for k, v in block.items() if k != "OTEL_EXPORTER_OTLP_ENDPOINT" and env.get(k) == v]
            if env.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").startswith("http://127.0.0.1:"):
                ours.append("OTEL_EXPORTER_OTLP_ENDPOINT")
            copy = backup(path)
            for k in ours:
                env.pop(k, None)
            save_settings_file(path, current)
            q.out("Telemetry taken out of %s (%d line(s); copy of the file before: %s). The receiver stops by itself "
                  "within a minute.\n" % (path, len(ours), copy))
        else:
            q.out("Telemetry is off for Quotient: the receiver stops by itself within a minute. To stop Claude Code "
                  "sending it, take these lines out of the \"env\" block of %s (or run telemetry off --write): %s\n"
                  % (path, ", ".join(block)))
        return


def backup(path):
    if not os.path.exists(path):
        return None
    copy = "%s.quotient-%s.bak" % (path, time.strftime("%Y%m%d-%H%M%S"))
    with open(path, "rb") as src, open(copy, "wb") as dst:
        dst.write(src.read())
    return copy


def save_settings_file(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
