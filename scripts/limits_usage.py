"""The plan limits, read through Claude Code's own /usage command: no tokens spent, no login read by Quotient.

`claude -p /usage` prints the same lines as /usage in the app ("Current session: 22% used · resets Oct 12,
3:49am (Europe/Rome)"). Claude Code answers it locally, with its own login: Quotient only runs the command
(without hooks and without saving a session) and keeps the percentages and the reset times. Nothing is sent
by Quotient. Off with: config limits.live false.
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta

MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                          "nov", "dec"))}
LINES = (("five_hour", re.compile(r"^\W*current session\b[^:\n]*:\s*(\d{1,3}(?:\.\d+)?)\s*%\s*used(.*)$", re.I | re.M)),
         ("seven_day", re.compile(r"^\W*current week\s*\(all models\)[^:\n]*:\s*(\d{1,3}(?:\.\d+)?)\s*%\s*used(.*)$",
                                  re.I | re.M)))
RESET_RE = re.compile(r"resets\s+(?:(?:on|at)\s+)?(?:([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(?:at\s+)?)?"
                      r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.I)


def reset_epoch(rest, now=None):
    """'resets Oct 12, 3:49am (Europe/Rome)' -> Unix seconds, read as the computer's local time (Claude Code
    writes the reset in the computer's own time zone). Without a date: the next time that hour comes."""
    m = RESET_RE.search(rest or "")
    if not m:
        return None
    now = now or datetime.now()
    month, day, hour, minute, half = m.groups()
    hour = int(hour) % 12 + (12 if half.lower() == "p" else 0)
    minute = int(minute or 0)
    try:
        if month:
            if month.lower() not in MONTHS:
                return None
            moment = datetime(now.year, MONTHS[month.lower()], int(day), hour, minute)
            if moment < now - timedelta(days=180):     # a reset in January, read in December
                moment = moment.replace(year=now.year + 1)
        else:
            moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if moment < now:
                moment += timedelta(days=1)
    except ValueError:
        return None
    return moment.timestamp()


def parse(text, now=None):
    """{'five_hour': %, 'five_hour_resets': epoch, 'seven_day': %, 'seven_day_resets': epoch}, or None."""
    snap = {}
    for window, rx in LINES:
        m = rx.search(text or "")
        if m:
            snap[window] = float(m.group(1))
            snap[window + "_resets"] = reset_epoch(m.group(2), now)
    return snap or None


def fetch(claude, cwd=None, timeout=25):
    """Run Claude Code's /usage and read it; None when Claude Code is missing, too old, or not on a plan."""
    if not claude:
        return None
    cmd = [claude, "-p", "/usage", "--output-format", "json", "--no-session-persistence",
           "--settings", json.dumps({"disableAllHooks": True})]
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}  # not seen as a session inside a session
    flags = 0x08000000 if os.name == "nt" else 0                        # CREATE_NO_WINDOW: no console flashes
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout, creationflags=flags)
        out = proc.stdout.decode("utf-8", "replace").strip()
    except Exception:
        return None
    text = out
    for line in reversed(out.splitlines()):
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if isinstance(data, dict):
            if data.get("is_error"):
                return None
            text = str(data.get("result") or "")
        break
    return parse(text)
