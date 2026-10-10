"""The plan limits read straight from Anthropic, without the status line and without spending tokens.

Claude Code's /usage asks https://api.anthropic.com/api/oauth/usage with the user's own login; this does the same,
with the token Claude Code keeps in ~/.claude/.credentials.json. Only that request is made, only to Anthropic;
the token is never written anywhere by Quotient. Off with: config limits.live false.
"""

import json
import os
import time
import urllib.request
from datetime import datetime

URL = "https://api.anthropic.com/api/oauth/usage"


def credentials_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, ".credentials.json")


def token():
    try:
        with open(credentials_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    oauth = data.get("claudeAiOauth") or {}
    tok = oauth.get("accessToken")
    expires = oauth.get("expiresAt")
    if not tok:
        return None
    if isinstance(expires, (int, float)) and expires / 1000 < time.time():
        return None          # expired: Claude Code renews it the next time it runs
    return tok


def to_epoch(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fetch(timeout=10):
    """{'five_hour': %, 'five_hour_resets': epoch, 'seven_day': %, 'seven_day_resets': epoch} or None."""
    tok = token()
    if not tok:
        return None
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20",
                                               "Accept": "application/json", "User-Agent": "quotient"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    snap = {}
    for window in ("five_hour", "seven_day"):
        w = data.get(window) or {}
        if w.get("utilization") is not None:
            snap[window] = float(w["utilization"])
            snap[window + "_resets"] = to_epoch(w.get("resets_at"))
    return snap or None
