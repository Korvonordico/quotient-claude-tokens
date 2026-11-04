"""Codex (OpenAI) support, experimental (1.3.6; 1.3.7: its own folder, installments run by `codex exec`).

Codex writes each session to a JSON-lines log (~/.codex/sessions/.../rollout-*.jsonl) in its own shape. Here that log
is turned into the shape of a Claude Code transcript, so the rest of Quotient reads it unchanged: the user's messages,
one assistant entry per model call with its usage (cached input counted as a cache read), and the model's text. The
plan limits (5 hours, week) are taken from the same log. `setup-codex` adds Quotient's hooks to Codex.
OpenAI says the log format is not a stable interface: a change there needs a change here."""
import glob
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

WINDOWS = {300: "five_hour", 10080: "seven_day"}
POLL = 10   # seconds between two measures of a Codex installment against its cap
LOGIN_ERROR = "Codex is not logged in for runs outside the app: log in again with `codex login`"
CLAUDE_MODEL = re.compile(r"(?i)(claude|opus|sonnet|haiku|fable)")


def active(job=None):
    """Is this run for Codex: started with --codex, or a job that Codex works on."""
    return bool(os.environ.get("QUOTIENT_CODEX")) or (job or {}).get("engine") == "codex"


def codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def is_codex_row(row):
    return isinstance(row, dict) and "payload" in row and "timestamp" in row and isinstance(row.get("type"), str)


def usage_of(last):
    """Codex counts cached input and cache writes inside input_tokens; Quotient keeps them apart."""
    cached = last.get("cached_input_tokens") or 0
    write = last.get("cache_write_input_tokens") or 0
    return {"input_tokens": max(0, (last.get("input_tokens") or 0) - cached - write),
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": write,
            "output_tokens": last.get("output_tokens") or 0}


def raw_rows(path, tail_bytes=None):
    rows = []
    try:
        with open(path, "rb") as f:
            if tail_bytes:
                f.seek(0, os.SEEK_END)
                if f.tell() > tail_bytes:
                    f.seek(f.tell() - tail_bytes)
                    f.readline()
                else:
                    f.seek(0)
            for line in f:
                try:
                    rows.append(json.loads(line.decode("utf-8", "replace")))
                except ValueError:
                    pass
    except (OSError, TypeError):
        pass
    return rows


def is_codex_file(path):
    if not path:
        return False
    if os.path.basename(path).startswith("rollout-"):
        return True
    try:
        with open(path, "rb") as f:
            return is_codex_row(json.loads(f.readline().decode("utf-8", "replace")))
    except (OSError, ValueError, TypeError):
        return False


def convert(rows):
    """Codex log rows -> Claude Code-like entries; rows that are not Codex's are kept as they are."""
    out, texts, model, seen, last_ts = [], [], None, set(), None
    prev_total = None
    # Newer Codex writes one token_usage_record per model call; older logs only the running token_count events.
    records = any(isinstance(r, dict) and r.get("type") == "token_usage_record" for r in rows)
    for r in rows:
        if not is_codex_row(r):
            out.append(r)
            continue
        p = r.get("payload") or {}
        ts = r.get("timestamp")
        last_ts = ts or last_ts
        if r.get("type") == "turn_context":
            model = p.get("model") or model
            continue
        if r.get("type") == "token_usage_record":
            key = p.get("response_id") or json.dumps(p.get("usage"), sort_keys=True)
            if key in seen or not isinstance(p.get("usage"), dict):
                continue
            seen.add(key)
            out.append({"type": "assistant", "timestamp": ts, "requestId": "codex-%s" % key,
                        "message": {"model": model, "usage": usage_of(p["usage"]),
                                    "content": [{"type": "text", "text": t} for t in texts]}})
            texts = []
            continue
        if r.get("type") != "event_msg":
            continue
        kind = p.get("type")
        if kind == "user_message":
            out.append({"type": "user", "timestamp": ts, "message": {"role": "user", "content": p.get("message") or ""}})
        elif kind == "agent_message":
            texts.append(p.get("message") or "")
        elif kind == "token_count" and not records:
            info = p.get("info") or {}
            total = info.get("total_token_usage") or {}
            last = info.get("last_token_usage")
            key = json.dumps(total, sort_keys=True)
            if not total or key in seen:
                continue   # no usage, or the same call told again (Codex repeats it with new limits)
            seen.add(key)
            if not last:   # an older log: the call is the difference of the running totals
                last = {k: (total.get(k) or 0) - ((prev_total or {}).get(k) or 0) for k in total}
            prev_total = total
            out.append({"type": "assistant", "timestamp": ts, "requestId": "codex-" + key,
                        "message": {"model": model, "usage": usage_of(last),
                                    "content": [{"type": "text", "text": t} for t in texts]}})
            texts = []
    if texts:   # text written after the last usage: kept, at no cost
        out.append({"type": "assistant", "timestamp": last_ts, "uuid": "codex-text-%d" % len(out),
                    "message": {"model": model, "content": [{"type": "text", "text": t} for t in texts]}})
    return out


def limits_of(rows):
    """The last plan limits in the log, in Quotient's shape: five_hour / seven_day used % and when they reset."""
    from quotient_lib import q_limits
    for r in reversed(rows):
        if not isinstance(r, dict):
            continue
        p = r.get("payload") or {}
        if r.get("type") != "event_msg" or p.get("type") != "token_count" or not isinstance(p.get("rate_limits"), dict):
            continue
        snap = {}
        for w in p["rate_limits"].values():
            if not isinstance(w, dict) or w.get("used_percent") is None:
                continue
            name = WINDOWS.get(w.get("window_minutes"))
            if not name:
                continue
            snap[name] = float(w["used_percent"])
            if w.get("resets_at"):
                snap[name + "_resets"] = q_limits.to_epoch(w["resets_at"])
            elif w.get("resets_in_seconds") is not None:
                snap[name + "_resets"] = q_limits.ts_epoch(r.get("timestamp")) + float(w["resets_in_seconds"])
        if snap:
            return snap
    return None


def run_hook(fn, name):
    """Runs a hook; inside Codex the limits come from its log, not from `claude -p /usage`, and the Stop hook only
    prints JSON (Codex refuses plain text there)."""
    from quotient_lib import q_limits, q_settings
    data = q_settings.read_stdin_json()
    q_settings.read_stdin_json = lambda: data
    path = data.get("transcript_path") or ""
    if os.environ.get("QUOTIENT_CODEX") or is_codex_file(path):
        os.environ["QUOTIENT_LIMITS_LIVE"] = "0"
        if not first_to_run(name, data):
            return   # the other copy of the hooks (the plugin's or `setup-codex`'s) already did this one
        try:
            snap = limits_of(raw_rows(path, tail_bytes=2 * 1024 * 1024))
            if snap:
                q_limits.record_limits(snap, "codex")
        except Exception as exc:   # limits that cannot be read must never stop a message
            sys.stderr.write("quotient: codex limits: %s\n" % exc)
        if name == "hook-stop":
            plain = q_settings.out
            q_settings.out = lambda text: plain(text) if text.lstrip().startswith("{") else None
    fn()


def first_to_run(name, data):
    """1.3.7: with the plugin and the hooks of `setup-codex` both in Codex, each event reaches Token Quotient twice;
    only the first copy works (a mark file made atomically), so nothing is counted twice."""
    from quotient_lib import q_settings
    if not data.get("session_id"):
        return True
    key = "|".join([name] + [str(data.get(k) or "") for k in ("session_id", "turn_id", "source")])
    window = 120 if data.get("turn_id") else 30
    try:
        folder = os.path.join(q_settings.home(), "hook-marks")
        os.makedirs(folder, exist_ok=True)
        mark = os.path.join(folder, hashlib.sha1(key.encode("utf-8")).hexdigest()[:24])
        for _ in range(2):
            try:
                os.close(os.open(mark, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                if time.time() - os.path.getmtime(mark) < window:
                    return False
                os.remove(mark)
        old = time.time() - 86400
        for other in os.listdir(folder)[:500]:
            full = os.path.join(folder, other)
            if os.path.getmtime(full) < old:
                os.remove(full)
    except OSError:
        pass
    return True


def setup(args=None):
    """Adds Quotient's hooks to Codex (~/.codex/hooks.json, or $CODEX_HOME), replacing older Quotient entries;
    with --remove (1.3.7) it only takes them away, for who moves to the plugin."""
    from quotient_lib import q_settings
    os.environ["QUOTIENT_CODEX"] = "1"   # 1.3.7: Codex's own settings, never Claude Code's
    home = codex_home()
    os.makedirs(home, exist_ok=True)
    path = os.path.join(home, "hooks.json")
    try:
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    except (OSError, ValueError):
        conf = {}
    entry = q_settings.ENTRY_FILE
    py = sys.executable
    posix = '"%s" "%s"' % (py.replace("\\", "/"), entry.replace("\\", "/"))
    windows = ('%s "%s"' % (py, entry)) if " " not in py else 'py -3 "%s"' % entry
    hooks = conf.setdefault("hooks", {})
    remove = bool(getattr(args, "remove", False))
    for event, cmd, timeout in (("SessionStart", "hook-session", 20), ("UserPromptSubmit", "hook-prompt", 20),
                                ("Stop", "hook-stop", 30)):
        groups = [g for g in hooks.get(event) or []
                  if not any("quotient.py" in (h.get("command") or "") for h in g.get("hooks") or [])]
        handler = {"type": "command", "command": "%s %s --codex" % (posix, cmd),
                   "commandWindows": "%s %s --codex" % (windows, cmd),
                   "timeout": timeout, "statusMessage": "Quotient"}
        if event != "Stop":
            handler["additionalContextLimit"] = 0   # the whole protocol and quote lines, not a preview
        if not remove:
            groups.append({"hooks": [handler]})
        hooks[event] = groups
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    if remove:
        q_settings.out("Quotient hooks removed from %s. Token Quotient's data stay where they are.\n" % path)
        return
    q_settings.home()   # Codex's own folder of Quotient, with the settings of Claude Code's as a start
    q_settings.out("Quotient hooks added to %s.\nNext: open Codex, type /hooks and trust the three Quotient hooks "
                   "(Codex skips new hooks until you trust them). Codex jobs are never shared.\n"
                   "If you installed the Token Quotient plugin in Codex, do not use this too: each message would be "
                   "counted twice.\n" % path)


def record_limits_from(path):
    from quotient_lib import q_limits
    snap = limits_of(raw_rows(path, tail_bytes=2 * 1024 * 1024)) if path else None
    if snap:
        q_limits.record_limits(snap, "codex")
    return snap


# ---- 1.3.7: installments done by Codex (`codex exec`), stopped from outside when they reach their cap ----

def find_codex(job=None):
    """The command that starts Codex, as a list, or None. The path found when the job was made comes first: a
    scheduled task may not have the PATH of a terminal."""
    for path in (os.environ.get("QUOTIENT_CODEX_BIN"), (job or {}).get("codex_path")):
        if path and os.path.isfile(path):
            return [path]
    found = shutil.which("codex")
    if found:
        return [found]
    for path in (os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"),
                 os.path.join(os.path.expanduser("~"), ".local", "bin", "codex"),
                 "/opt/homebrew/bin/codex", "/usr/local/bin/codex"):
        if os.path.isfile(path):
            return [path]
    return None


def exec_cmd(codex, job, folder, rc):
    """`codex exec` for one installment: JSON events on stdout, the prompt on stdin (a .cmd on Windows cuts an
    argument at its first new line), edits allowed in the job's folder and in its handoff folder."""
    cmd = list(codex) + ["exec", "--json", "--skip-git-repo-check",
                         "--sandbox", rc.get("codex_sandbox") or "workspace-write",
                         "--cd", job.get("dir") or os.getcwd(), "--add-dir", folder]
    model = job.get("model") or ""
    if model and not CLAUDE_MODEL.match(model):
        cmd += ["--model", model]
    return cmd + list(rc.get("codex_args") or []) + ["-"]


def installment_prompt(prompt):
    """The installment prompt, with what Quotient does at the cap in Codex: it stops the run, it refuses no tool."""
    return re.sub(r"5\. Near the end of the cap.*?\n(?=6\. )",
                  "5. Quotient stops this installment from outside when its cap is used up: what is not saved then is "
                  "lost, so save results and update the handoff after each step. If the handoff lists the work of "
                  "helpers stopped in an earlier installment, use their files before searching again.\n",
                  prompt, flags=re.S)


def find_rollout(thread_id):
    safe = re.sub(r"[^\w-]", "", thread_id or "")
    if not safe:
        return None
    found = glob.glob(os.path.join(codex_home(), "sessions", "*", "*", "*", "rollout-*%s.jsonl" % safe))
    return found[0] if found else None


def first_user_message(path):
    try:
        with open(path, "rb") as f:
            for n, line in enumerate(f):
                if n > 400:
                    break
                try:
                    r = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                p = r.get("payload") if isinstance(r, dict) else None
                if isinstance(p, dict) and r.get("type") == "event_msg" and p.get("type") == "user_message":
                    return p.get("message") or ""
    except OSError:
        pass
    return None


def find_run_rollout(task, lo, hi, known=()):
    """The log of the `codex exec` run of an installment that printed nothing (stopped, killed): the newest session
    changed since it started whose first message names the job's TASK.md."""
    found = []
    for path in glob.glob(os.path.join(codex_home(), "sessions", "*", "*", "*", "rollout-*.jsonl")):
        try:
            changed = os.path.getmtime(path)
        except OSError:
            continue
        if changed < lo - 60 or os.path.basename(path)[-42:-6] in known:
            continue
        if task in (first_user_message(path) or ""):
            found.append((changed, path))
    return max(found)[1] if found else None


def spent(path, weights):
    from quotient_lib import q_costs, q_settings
    return sum(q_costs.weigh(u, weights) for u in q_costs.calls_of(q_settings.read_jsonl(path)).values())


def kill_tree(proc):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except Exception:
        pass
    try:
        proc.wait(15)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def read_events(lines):
    """What `codex exec --json` said: its session, the usage of its turns, its last message, an error."""
    out = {"session_id": None, "usage": {}, "num_turns": 0, "text": "", "error": None}
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        kind = e.get("type")
        if kind == "thread.started":
            out["session_id"] = e.get("thread_id") or out["session_id"]
        elif kind == "turn.completed":
            out["num_turns"] += 1
            for k, v in usage_of(e.get("usage") or {}).items():
                out["usage"][k] = out["usage"].get(k, 0) + v
        elif kind in ("turn.failed", "error"):
            err = e.get("error") if isinstance(e.get("error"), dict) else e
            out["error"] = str(err.get("message") or err)[-300:]
        elif kind == "item.completed" and isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message":
            out["text"] = e["item"].get("text") or out["text"]
    return out


def run_exec(cmd, prompt, cwd, timeout, cap, weights):
    """Runs one installment with `codex exec` and measures its log every POLL seconds: at its cap (or at the time
    limit) Quotient stops it, from outside, whatever it is doing. Returns (result in the shape of `claude -p`'s
    answer, its log or None, stderr)."""
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000200 | 0x08000000}
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    lines, errs = [], []

    def pump(stream, into):
        for raw in iter(stream.readline, b""):
            into.append(raw.decode("utf-8", "replace"))

    readers = [threading.Thread(target=pump, args=(proc.stdout, lines), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, errs), daemon=True)]
    for t in readers:
        t.start()
    try:
        proc.stdin.write(prompt.encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass
    deadline, stopped, path, used = time.time() + timeout, None, None, 0
    while True:
        try:
            proc.wait(POLL)
            break
        except subprocess.TimeoutExpired:
            pass
        if not path:
            path = find_rollout(read_events(list(lines))["session_id"])
        if path:
            try:
                used = spent(path, weights)
            except Exception:
                pass
        if cap and used >= cap:
            stopped = "cap"
        elif time.time() > deadline:
            stopped = "timeout"
        if stopped:
            kill_tree(proc)
            break
    for t in readers:
        t.join(10)
    for stream in (proc.stdout, proc.stderr):
        try:
            stream.close()
        except OSError:
            pass
    said = read_events(lines)
    path = path or find_rollout(said["session_id"])
    stderr = "".join(errs)
    error = said["error"]
    if stopped == "timeout":
        error = "timeout"
    elif not error and proc.returncode not in (0, None) and not stopped:
        error = stderr.strip()[-300:] or "codex exec ended with code %s" % proc.returncode
    if error and error != "timeout" and re.search(r"(?i)\blog ?in\b|logged in|unauthori[sz]ed|\b401\b|not signed in", error):
        error = LOGIN_ERROR
    result = {"session_id": said["session_id"], "usage": said["usage"], "num_turns": said["num_turns"],
              "is_error": bool(error), "result": error or said["text"], "stopped": stopped}
    return result, path, stderr
