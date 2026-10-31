"""Scheduled installments on Windows, and the PC: awake, idle, asleep."""

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from quotient_lib import q_rates, q_settings

def check_time(value):
    if not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", value or ""):
        sys.exit("quotient: write the time as HH:MM, for example 03:00")
    hh, mm = value.split(":")
    return "%02d:%s" % (int(hh), mm)


def launcher():
    """A small script outside the plugin folder that runs this copy of Quotient, by its exact path.

    Scheduled tasks call it. It never looks for other copies: each session start writes it again with
    the path of the version that is running (refresh_launchers), so tasks keep working after an update.
    """
    path = os.path.join(q_settings.home(), "launcher.py")
    code = (
        "# Runs Token Quotient from this exact file (written by Quotient; scheduled tasks call it).\n"
        "import os, runpy, sys\n"
        "script = %r\n"
        "sys.path.insert(0, os.path.dirname(script))\n"
        "sys.argv = [script] + sys.argv[1:]\n"
        "runpy.run_path(script, run_name='__main__')\n" % q_settings.ENTRY_FILE)
    if load_text(path) != code:
        with open(path, "w", encoding="utf-8") as f:
            f.write(code)
    return path


def statusline_launcher():
    """The status line's small script: it runs this copy of Quotient by its exact path, like launcher()."""
    path = os.path.join(q_settings.home(), "statusline.sh")
    code = ('#!/bin/sh\n# Runs the status line of Token Quotient from this exact folder (written by Quotient).\n'
            'exec sh "%s/run.sh" statusline\n' % os.path.dirname(q_settings.ENTRY_FILE).replace("\\", "/"))
    if load_text(path) != code:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(code)
    return path


def refresh_launchers():
    """At a session start of the installed plugin: the launchers that exist point again at the version
    that is running, so scheduled tasks and the status line follow updates (and the old folders can go)."""
    if not os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return  # a copy run by hand (or by Hermes from a clone) does not move them
    if os.path.exists(os.path.join(q_settings.home(), "launcher.py")):
        launcher()
    if os.path.exists(os.path.join(q_settings.home(), "statusline.sh")):
        statusline_launcher()


def load_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def next_time(at):
    """Today at HH:MM, or tomorrow if that time has already passed."""
    hh, mm = (int(x) for x in check_time(at).split(":"))
    moment = datetime.now().replace(hour=hh, minute=mm, second=0, microsecond=0)
    if moment <= datetime.now():
        moment = moment.fromtimestamp(moment.timestamp() + 86400)
    return moment


def task_xml(name, start, once, arguments, wake=True):
    """A Task Scheduler task that wakes the PC from sleep or hibernation, and runs late if it missed its time."""
    def esc(text):
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))
    stamp = "%Y-%m-%dT%H:%M:%S"
    if once:
        # a once task can still run late for a week; then Windows removes it, so they do not pile up
        end = datetime.fromtimestamp(start.timestamp() + 7 * 86400)
        trigger = ("<TimeTrigger><StartBoundary>%s</StartBoundary><EndBoundary>%s</EndBoundary>"
                   "<Enabled>true</Enabled></TimeTrigger>") % (start.strftime(stamp), end.strftime(stamp))
    else:
        trigger = ("<CalendarTrigger><StartBoundary>%s</StartBoundary><Enabled>true</Enabled>"
                   "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>") % start.strftime(stamp)
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Quotient: installment of %s</Description></RegistrationInfo>
  <Triggers>%s</Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>%s</WakeToRun>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
    <Enabled>true</Enabled>%s
  </Settings>
  <Actions Context="Author"><Exec><Command>%s</Command><Arguments>%s</Arguments><WorkingDirectory>%s</WorkingDirectory></Exec></Actions>
</Task>
""" % (esc(name), trigger, "true" if wake else "false",
       "\n    <DeleteExpiredTaskAfter>PT1H</DeleteExpiredTaskAfter>" if once else "",
       esc(sys.executable), esc(arguments), esc(q_settings.home()))


def schedule(name, at, once, force=False, wake=True):
    start = next_time(at)
    arguments = '"%s" rate run %s%s' % (launcher(), name, " --force" if once or force else "")
    if os.name == "nt":
        xml = os.path.join(q_rates.rate_dir(name), start.strftime("task-once-%Y%m%d-%H%M.xml") if once else "task-daily.xml")
        os.makedirs(os.path.dirname(xml), exist_ok=True)
        with open(xml, "w", encoding="utf-16") as f:
            f.write(task_xml(name, start, once, arguments, wake))
        proc = subprocess.run(["schtasks", "/Create", "/F", "/TN", q_rates.task_name(name, once, start), "/XML", xml],
                              capture_output=True)
        if proc.returncode != 0:
            sys.exit("quotient: the task was not created: %s" % (proc.stderr or proc.stdout).decode("utf-8", "replace").strip())
        q_settings.out("%s '%s' at %s%s. %s Remove it with: rate stop %s\n" % (
            "Scheduled once" if once else "Scheduled every day from", name, start.strftime("%d/%m %H:%M"),
            " (with --force: also after another installment the same day)" if force and not once else "",
            "It wakes the PC from sleep or hibernation." if wake else
            "It does not wake the PC: it runs only if the PC is on (or as soon as it is turned on).", name))
    else:
        run = '"%s" %s' % (sys.executable, arguments)
        hh, mm = start.strftime("%H"), start.strftime("%M")
        if once:
            q_settings.out("Run this once (needs `at`):\necho '%s' | at %s\n" % (run, start.strftime("%H:%M")))
        else:
            q_settings.out("Add this line with `crontab -e`:\n%d %d * * * %s\n" % (int(mm), int(hh), run))
        q_settings.out("To wake the computer first: macOS `sudo pmset repeat wake MTWRFSU %s:00`; Linux `sudo rtcwake -m no -t <time>`.\n" % start.strftime("%H:%M"))


def once_tasks(name):
    """The job's `rate once` tasks that Task Scheduler holds now."""
    proc = subprocess.run(["schtasks", "/Query", "/FO", "CSV", "/NH"], capture_output=True)
    names = set()
    for row in csv.reader(proc.stdout.decode("utf-8", "replace").splitlines()):
        if row and q_rates.once_task(name, row[0].lstrip("\\")):
            names.add(row[0].lstrip("\\"))
    return sorted(names)


def unschedule(name):
    if os.name == "nt":
        for task in [q_rates.task_name(name)] + once_tasks(name):
            subprocess.run(["schtasks", "/Delete", "/F", "/TN", task], capture_output=True)


# ---------------------------------------------------------------- the PC: awake, idle, asleep

def woken_recently(minutes=10):
    """Did the PC resume from sleep or hibernation in the last minutes? Read from Windows' own log (Kernel-Power
    107, Power-Troubleshooter 1). True, False, or None where it cannot be read."""
    if os.name != "nt":
        return None
    script = ("$t=(Get-Date).AddMinutes(-%d); $e=Get-WinEvent -FilterHashtable @{LogName='System';Id=1,107;"
              "StartTime=$t} -ErrorAction SilentlyContinue | Where-Object { $_.ProviderName -match "
              "'Kernel-Power|Power-Troubleshooter' } | Select-Object -First 1; if ($e) {'yes'} else {'no'}" % minutes)
    try:
        proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, timeout=30)
        text = proc.stdout.decode("utf-8", "replace").strip().lower()
    except Exception:
        return None
    return True if text.endswith("yes") else False if text.endswith("no") else None


def found_asleep(cfg):
    """Did this installment find the PC asleep (and so wake it)? 08/10/2026: the PC was on and in use at 03:00,
    nobody had touched mouse or keyboard for 10 minutes, and the installment put it into hibernation. From then
    on the PC goes back to sleep only if it was asleep when the installment started. When Windows' log cannot
    be read: someone who used the PC in the last minutes means it was on."""
    woke = woken_recently()
    if woke is None:
        idle = idle_seconds()
        woke = idle is not None and idle >= cfg["rate"]["idle_minutes"] * 60
    return woke


def keep_awake(on):
    """While an installment works, Windows must not put the PC back to sleep."""
    if os.name != "nt":
        return
    try:
        import ctypes
        flags = 0x80000000 | (0x00000001 if on else 0)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
        ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception:
        pass


def idle_seconds():
    """Seconds since the last keyboard or mouse input, or None where it cannot be read."""
    if os.name != "nt":
        return None
    try:
        import ctypes

        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

        info = LastInput()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


def go_to_sleep(how):
    """Sleep or hibernate; never shut down, because a timer cannot wake a PC that is off."""
    state = "Hibernate" if how == "hibernate" else "Suspend"
    if os.name == "nt":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "Add-Type -AssemblyName System.Windows.Forms; "
                        "[System.Windows.Forms.Application]::SetSuspendState('%s', $false, $false)" % state])
    elif sys.platform == "darwin":
        subprocess.run(["pmset", "sleepnow"])
    else:
        subprocess.run(["systemctl", "hibernate" if how == "hibernate" else "suspend"])


def rate_check(args):
    """Read-only: can a scheduled installment wake this PC?"""
    if os.name != "nt":
        q_settings.out("On macOS use `pmset -g sched`, on Linux `rtcwake`: waking by timer needs administrator rights there.\n")
        return
    proc = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "RTCWAKE"], capture_output=True)
    text = proc.stdout.decode("utf-8", "replace") + proc.stdout.decode("cp850", "replace")
    values = re.findall(r":\s*0x0*([0-9a-fA-F]+)\s*$", proc.stdout.decode("cp850", "replace"), re.M)
    names = {"0": "disabled", "1": "enabled", "2": "important timers only"}
    if len(values) >= 2:
        ac, dc = values[-2], values[-1]
        q_settings.out("Wake timers: on mains %s, on battery %s.\n" % (names.get(ac, ac), names.get(dc, dc)))
        if ac != "1":
            q_settings.out("To let Quotient wake the PC: Control Panel > Power Options > Change plan settings > "
                "Change advanced power settings > Sleep > Allow wake timers > Enable.\n")
    else:
        q_settings.out("Could not read the wake-timer setting.\n")
    q_settings.out("Waking works from sleep and from hibernation, not from a full shutdown.\n")
    claude = q_rates.find_claude(q_settings.config())
    if not claude:
        q_settings.out("Claude Code not found: set it with `config claude_path <path to claude.exe>`.\n")
        return
    q_settings.out("Claude Code: %s\n" % claude)
    proc = subprocess.run([claude, "auth", "status"], capture_output=True)
    try:
        logged = json.loads(proc.stdout.decode("utf-8", "replace")).get("loggedIn")
    except ValueError:
        logged = None
    q_settings.out("Logged in for runs outside the app: %s\n" % {True: "yes", False: "NO", None: "unknown"}[logged])
    if getattr(args, "live", False) is True:
        q_settings.out(live_check(q_settings.config(), claude) + "\n")
    if logged is False:
        q_settings.out('Log in once, in a terminal (it opens the browser; paste the code it gives you):\n"%s" auth login\n' % claude)


def live_check(cfg, claude):
    """One real call with the smallest model, the way an installment runs: it shows a login that is there but
    can no longer be renewed (08/10/2026), which the status alone does not. It costs a few cents."""
    prefix = (cfg["rate"].get("prompt_prefix") or "").strip()
    cmd = [claude, "-p", (prefix + " " if prefix else "") + "Reply with the single word OK.", "--model", "haiku",
           "--max-turns", "1", "--output-format", "json"]
    try:
        os.environ["QUOTIENT_CHECK"] = "1"  # for the check's own hooks, only while it runs
        try:
            proc = subprocess.run(cmd, cwd=q_settings.home(), capture_output=True, timeout=180)
        finally:
            os.environ.pop("QUOTIENT_CHECK", None)
        result = {}
        for line in reversed(proc.stdout.decode("utf-8", "replace").strip().splitlines()):
            try:
                result = json.loads(line)
                break
            except ValueError:
                continue
    except Exception as exc:
        return "Live test: it could not run (%s)." % exc
    said = str(result.get("result") or "") + proc.stderr.decode("utf-8", "replace")
    if result and not result.get("is_error") and "ok" in str(result.get("result") or "").lower():
        return "Live test: OK, an installment can run now (cost $%.4f)." % (result.get("total_cost_usd") or 0)
    if "authenticate" in said.lower() or "logged in" in said.lower() or "oauth" in said.lower():
        return "Live test: FAILED, " + q_rates.LOGIN_ERROR + "."
    return "Live test: FAILED: %s" % (said.strip()[-300:] or "no answer")


def wake_allowed(args):
    return q_settings.config()["rate"]["wake"] and not args.no_wake


def job_time(args, fallback=True):
    """The time of a scheduled installment: --time, else the time the user chose for the job (1.1.3, `rate new --at`
    or a pace with a time), else the setting (03:00) when `fallback`."""
    if isinstance(args.time, str) and args.time:
        return args.time
    job = q_settings.load_json(os.path.join(q_rates.rate_dir(args.name), "job.json"), None) or {}
    return job.get("at") or ((q_settings.config()["rate"].get("time") or "03:00") if fallback else None)


def rate_schedule(args):
    schedule(args.name, job_time(args), once=False, force=args.force, wake=wake_allowed(args))


def rate_once(args):
    at = job_time(args, fallback=False)
    if not at:
        sys.exit("quotient: give the time with --time HH:MM (the job has no time of its own)")
    schedule(args.name, at, once=True, wake=wake_allowed(args))


def rate_after(args):
    folder = q_rates.rate_dir(args.name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    job["after"] = args.what
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    q_settings.out("After each installment of '%s': %s%s.\n" % (args.name, args.what,
        " (only if nobody used the PC in the last %d minutes)" % q_settings.config()["rate"]["idle_minutes"] if args.what != "nothing" else ""))


def rate_stop(args):
    folder = q_rates.rate_dir(args.name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    unschedule(args.name)
    if not job:
        sys.exit("quotient: no job named '%s' (its scheduled tasks, if any, are removed)" % args.name)
    if job["status"] == "open":
        job["status"] = "stopped"
        q_settings.save_json(os.path.join(folder, "job.json"), job)
    q_settings.out("Job '%s' stopped; its scheduled runs are removed%s.\n" % (
        args.name, "" if os.name == "nt" else " (remove its crontab line yourself)"))
