"""The price table of the Claude models, and the share and config commands."""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

from quotient_lib import q_costs, q_learning, q_settings, q_sharing

# ---------------------------------------------------------------- the price table (1.2.3)
# From tokencost (MIT, data/LICENSE-tokencost.txt): only the Claude models, and only when the user asks (`prices update`).
PRICES_URL = "https://raw.githubusercontent.com/AgentOps-AI/tokencost/main/tokencost/model_prices.json"
PRICE_FIELDS = (("input", "input_cost_per_token"), ("output", "output_cost_per_token"),
                ("cache_read", "cache_read_input_token_cost"), ("cache_write", "cache_creation_input_token_cost"))
PRICE_DATE_RE = re.compile(r"-(?:\d{8}|latest)$")


def prices_path():
    return os.path.join(q_learning.plugin_root(), "data", "model-prices.json")


def filter_prices(table):
    """The Claude models of tokencost's table, each with its prices per token: only the numbers are kept."""
    models = {}
    for name, entry in (table.items() if isinstance(table, dict) else ()):
        if not isinstance(entry, dict):
            continue
        low = str(name).lower()
        if "claude" not in low and "anthropic" not in low and str(entry.get("litellm_provider")).lower() != "anthropic":
            continue
        kept = {short: float(entry[field]) for short, field in PRICE_FIELDS
                if isinstance(entry.get(field), (int, float)) and not isinstance(entry.get(field), bool)}
        if kept:
            models[name] = kept
    return models


def model_price(model):
    """The prices per token of a model (input, output, cache_read, cache_write, those the table has), or None. An id
    like claude-opus-4-1[1m] or anthropic/claude-opus-4-1 and one with or without its date find the same line; another
    version of the model never does, because its price can differ."""
    models = q_settings.load_json(prices_path(), {}).get("models") or {}
    name = re.sub(r"\[.*?\]$", "", str(model or "").strip().lower())
    name = name.split("/")[-1]
    if name in models:
        return models[name]
    bare = PRICE_DATE_RE.sub("", name)
    found = [key for key in models if PRICE_DATE_RE.sub("", key) == bare]
    return models[max(found, key=lambda key: (key.endswith("-latest"), key))] if found else None


def prices_update():
    """Download the table again and keep the Claude models. Only when the user runs it; a failure leaves the old table."""
    status, body = q_sharing.http("GET", PRICES_URL, timeout=30, most=20 * 1024 * 1024)
    try:
        models = filter_prices(json.loads(body.decode("utf-8"))) if status == 200 else {}
    except ValueError:
        models = {}
    if not models:
        sys.exit("quotient: the price table could not be downloaded (or has no Claude models): the old one stays.")
    q_settings.save_json(prices_path(), {"source": PRICES_URL, "license": "MIT, see LICENSE-tokencost.txt",
                              "updated": datetime.now().strftime("%Y-%m-%d"), "models": models})
    return len(models)


def cmd_prices(args):
    if args.action == "update":
        q_settings.out("Price table updated: %d Claude models.\n" % prices_update())
    table = q_settings.load_json(prices_path(), {})
    models = table.get("models") or {}
    if not models:
        q_settings.out("No price table yet: prices update downloads it.\n")
        return
    q_settings.out("Dollars per million tokens, from tokencost (MIT), updated %s. Not your plan's cost: plans have limits.\n" % (
        table.get("updated") or "?"))
    width = max(len(name) for name in models)
    q_settings.out("%-*s %9s %9s %10s %11s\n" % (width, "model", "input", "output", "cache read", "cache write"))
    for name in sorted(models):
        q_settings.out("%-*s %s\n" % (width, name, " ".join(
            ("%*.2f" % (size, models[name][key] * 1e6)) if key in models[name] else " " * (size - 1) + "-"
            for (key, _), size in zip(PRICE_FIELDS, (9, 9, 10, 11)))))


def cmd_share(args):
    """status: what is sent and what is waiting; on/off: turn sharing on or off; send: send the waiting
    lines now. --into (for maintainers): add your finished jobs, numbers only, to a JSON-lines file."""
    cfg = q_settings.config()
    if args.into:
        path = args.into
        have = q_settings.read_jsonl(path)
        keys = {(r.get("raw_estimate"), r.get("actual")) for r in have}
        added = 0
        for j in q_learning.finished_jobs():
            row = {"raw_estimate": j["raw_estimate"], "actual": q_costs.work_of(j),
                   "ratio": round(q_costs.work_of(j) / j["raw_estimate"], 4),
                   "family": j.get("family") if j.get("family") in q_costs.FAMILY_NAMES else "other", "version": q_settings.VERSION}
            if (row["raw_estimate"], row["actual"]) not in keys:
                q_settings.append_jsonl(path, row)
                keys.add((row["raw_estimate"], row["actual"]))
                added += 1
        q_settings.out("%d job(s) added to %s (numbers only); %d in all.\n" % (added, path, len(have) + added))
        return
    q_sharing.store(("share", "notice_shown"), True)  # the user is looking at what is shared
    if args.what in ("on", "off"):
        q_settings.save_settings({("share", "enabled"): args.what == "on"})
        cfg = q_settings.config()
        if args.what == "off":
            q_sharing.write_outbox([])  # what was waiting is deleted, never sent
    elif args.what == "send":
        sent = q_sharing.flush_share(cfg, time.time() + 20)
        q_settings.out("%d line(s) sent.\n" % sent)
    q_settings.out(q_sharing.share_status(cfg))


def cmd_config(args):
    path = os.path.join(q_settings.home(), "config.json")
    user = q_settings.load_json(path, {})
    if not args.key:
        q_settings.out(json.dumps(q_settings.merge(q_settings.DEFAULTS, user), indent=1, ensure_ascii=False) + "\n")
        return
    keys = args.key.split(".")
    if args.value is None:
        node = q_settings.merge(q_settings.DEFAULTS, user)
        for k in keys:
            node = node[k]
        q_settings.out(json.dumps(node, ensure_ascii=False) + "\n")
        return
    try:
        value = json.loads(args.value)
    except ValueError:
        value = args.value
    node = user
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value
    q_settings.save_json(path, user)
    q_settings.out("%s = %s\n" % (args.key, json.dumps(value, ensure_ascii=False)))
