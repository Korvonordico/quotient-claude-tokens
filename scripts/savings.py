"""Quotient's advice for saving tokens (improvements 2, 5, 7 and 9): off by default, `config tips.level 1` or `2`.

- A long chat: a summary, or from tips.new_chat_tokens a new chat; a job in a long chat: the same job apart.
- Where the spending goes: each tool's share of a chat or an installment, an estimate from the characters of what it
  sent and received, read from the logs (Claude Code's transcript, Hermes' session store), kept as numbers only.
- The cache: how much of what is sent comes from it, with the likely reason when it falls.
- Each tip has an estimate of what it saves, and they come in that order; `tips later` and `tips drop` put one off or
  throw it away, and that choice is saved in ~/.quotient/tips.json.

The tips never ask for shorter replies: that would save tokens by making the work worse. They are about what goes
around the replies: re-reading, tool outputs, cache.
"""

import os
import re
import time

STEPS = 10           # what a tip about re-reading saves is said per this many steps: nobody knows how many are left
KEEP_CHATS = 30      # chats remembered in tips.json
SAFE = re.compile(r"[^\w.-]")

# the groups a tool falls in, the first that matches
GROUPS = (
    ("screenshots", re.compile(r"screenshot|vision|zoom|telecamera")),
    ("browser", re.compile(r"browser|chrome|playwright|navigate")),
    ("helpers", re.compile(r"^(agent|task|delegate)")),
    ("terminal", re.compile(r"^(bash|powershell|terminal|shell|process|execute_code|monitor)")),
    ("files read", re.compile(r"^(read|grep|glob|search_files|list|notebookread)")),
    ("files written", re.compile(r"^(write|edit|patch|multiedit|notebookedit)")),
    ("web", re.compile(r"web|fetch|search")),
)
# (the group as the user reads it, what lowers it): English, Italian
GROUP_TEXT = {
    "screenshots": (("screen photos", "read the text of the window instead of a photo where that is enough"),
                    ("le foto dello schermo", "leggere il testo della finestra invece della foto, dove basta")),
    "browser": (("the browser", "read the page's text instead of whole snapshots"),
                ("il browser", "leggere il testo della pagina invece delle istantanee intere")),
    "helpers": (("helpers", "give each helper a narrow task, and have it write its results to a file"),
                ("gli aiutanti", "dare a ogni aiutante un compito stretto e fargli scrivere i risultati in un file")),
    "terminal": (("the terminal", "have commands print only the result, not long outputs"),
                 ("il terminale", "far stampare ai comandi solo il risultato, non uscite lunghe")),
    "files read": (("reading files", "read only the lines needed, after a search"),
                   ("la lettura dei file", "leggere solo le righe che servono, dopo una ricerca")),
    "files written": (("writing files", "change files with small edits instead of writing them whole"),
                      ("la scrittura dei file", "cambiare i file con piccole modifiche invece di riscriverli interi")),
    "web": (("the web", "open fewer whole pages, after a search"),
            ("il web", "aprire meno pagine intere, dopo una ricerca")),
}
TEXT = {
    "new-chat": ("this chat re-reads about %(tokens)s tokens at every step (%(wt)s wt): a new chat, with where the work "
                 "stands in a file, or a summary, would save about %(saving)s wt every %(steps)d steps (a summary loses "
                 "details).",
                 "questa chat rilegge circa %(tokens)s token a ogni passo (%(wt)s wt): una chat nuova, con in un file il "
                 "punto del lavoro, o un riassunto, farebbe risparmiare circa %(saving)s wt ogni %(steps)d passi (il "
                 "riassunto perde dettagli)."),
    "long-chat": ("this chat re-reads about %(tokens)s tokens at every step (%(wt)s wt): a summary could save about "
                  "%(saving)s wt every %(steps)d steps, if it halves the chat (it loses details).",
                  "questa chat rilegge circa %(tokens)s token a ogni passo (%(wt)s wt): un riassunto, se la dimezza, "
                  "potrebbe far risparmiare circa %(saving)s wt ogni %(steps)d passi (perde dettagli)."),
    "apart": ("the open job re-reads about %(tokens)s tokens of this chat at every step: done apart (rate apart), if it "
              "needs no questions, it would save about %(saving)s wt every %(steps)d steps, start included.",
              "il lavoro aperto rilegge circa %(tokens)s token di questa chat a ogni passo: fatto a parte (rate apart), "
              "se non servono domande, farebbe risparmiare circa %(saving)s wt ogni %(steps)d passi, avvio compreso."),
    "tools": ("%(group)s cost about %(share)d%% of this chat (about %(wt)s wt, an estimate from the characters): "
              "%(advice)s.",
              "%(group)s sono costati circa il %(share)d%% di questa chat (circa %(wt)s wt, stima dai caratteri): "
              "%(advice)s."),
    "cache": ("only %(percent)d%% of what this chat sends comes from the cache, the cheap part (%(calls)d steps); likely "
              "reason: %(reason)s. Back at %(target)d%% it would save about %(saving)s wt.",
              "solo il %(percent)d%% di quello che questa chat manda arriva dalla cache, la parte che costa poco "
              "(%(calls)d passi); motivo probabile: %(reason)s. Tornando al %(target)d%% farebbe risparmiare circa "
              "%(saving)s wt."),
}
REASONS = {
    "pauses": ("%d pauses longer than the cache keeps the chat, after which it is written again at full price",
               "%d pause più lunghe di quanto la cache tiene la chat, dopo le quali la chat si riscrive a prezzo pieno"),
    "changed": ("the start of the chat changed %d times (rules, tools or the model), which writes it again",
                "l'inizio della chat è cambiato %d volte (regole, strumenti o modello), e si riscrive"),
    "new": ("a lot of new text comes in (long outputs, whole files), and new text is always written once",
            "entra molto testo nuovo (uscite lunghe, file interi), e il testo nuovo si scrive sempre una volta"),
}


def group_of(name, image=False):
    """The group of a tool, by its name; a tool that returned an image is a screen photo, whatever its name."""
    whole = str(name or "").lower()
    low = whole.split("__")[-1]       # an MCP tool: mcp__<server>__<tool>
    if image:
        return "screenshots"
    for group, pattern in GROUPS:
        if pattern.search(low) or (group in ("screenshots", "browser") and pattern.search(whole)):
            return group
    return "other"


def _price(items, seg_end, weights, write):
    """What each group's text costs: its tokens are written to the cache by the call after them and re-read by the
    calls after that, until the chat is compacted; what a call asks of a tool is also output, the dearest part."""
    groups = {}
    for group, tokens, pos, seg, is_output in items:
        later = seg_end.get(seg, pos) - pos
        wt = tokens * weights["output"] if is_output else 0.0
        if later > 0:
            wt += tokens * (write + weights["cache_read"] * (later - 1))
        groups[group] = groups.get(group, 0.0) + wt
    return groups


def _size(content, per, image_tokens):
    """(tokens, has an image) of what a tool sent back: from its characters, an estimate."""
    if isinstance(content, str):
        return len(content) / per, False
    tokens, image = 0.0, False
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "image":
            tokens, image = tokens + image_tokens, True
        elif isinstance(block, dict):
            tokens += len(str(block.get("text") or "")) / per
    return tokens, image


def claude_usage(q, entries, cfg):
    """Where a Claude Code chat or installment spent, from its transcript: {"groups": wt by group, "total": wt, "calls",
    "read", "written", "plain": prompt tokens by kind, "pauses", "changed": calls that found the cache cold}."""
    opts, w = cfg["tips"], cfg["weights"]
    per = float(cfg.get("chars_per_token") or 3.5)
    calls, order, names, items, seg_end, seen = {}, [], {}, [], {}, set()
    pos, seg = 0, 0
    for e in entries:
        if e.get("subtype") == "compact_boundary" or e.get("isCompactSummary"):
            seg_end[seg] = pos
            seg += 1
            continue
        if e.get("isSidechain"):
            continue
        msg = e.get("message") or {}
        content = msg.get("content")
        if e.get("type") == "assistant":
            key = e.get("requestId") or msg.get("id") or e.get("uuid")
            usage = msg.get("usage") or {}
            if key not in calls:
                calls[key] = {"usage": usage, "at": q.ts_epoch(e.get("timestamp")) if e.get("timestamp") else None}
                order.append(key)
                pos += 1
            elif (usage.get("output_tokens") or 0) > (calls[key]["usage"].get("output_tokens") or 0):
                calls[key]["usage"] = usage
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in seen:
                    seen.add(b.get("id"))
                    names[b.get("id")] = b.get("name")
                    items.append((group_of(b.get("name")), len(str(b.get("input") or "")) / per, pos, seg, True))
        elif e.get("type") == "user":
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tokens, image = _size(b.get("content"), per, float(opts.get("image_tokens") or 0))
                    items.append((group_of(names.get(b.get("tool_use_id")), image), tokens, pos, seg, False))
    seg_end[seg] = pos
    read = written = plain = pauses = changed = 0
    total, before, last_at = 0.0, 0, None
    for key in order:
        call = calls[key]
        u = call["usage"]
        total += q.weigh(u, w)
        r, wr, p = (u.get("cache_read_input_tokens") or 0, u.get("cache_creation_input_tokens") or 0,
                    u.get("input_tokens") or 0)
        read, written, plain = read + r, written + wr, plain + p
        prompt = r + wr + p
        # cold: about the same prompt as the call before (so no compaction), but most of it not read from the cache
        if before >= int(opts.get("cold_min_tokens") or 0) and prompt >= 0.8 * before and r < 0.5 * before:
            hour = ((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0) > 0
            chat = cfg.get("chat") or {}
            life = chat.get("cache_life_1h" if hour else "cache_life_5m") or (3600 if hour else 300)
            if last_at and call["at"] and call["at"] - last_at > life:
                pauses += 1
            else:
                changed += 1
        before, last_at = prompt, call["at"] or last_at
    write = q.write_weight(calls[order[0]]["usage"], w) if order else w["cache_write_5m"]
    return {"groups": _price(items, seg_end, w, write), "total": total, "calls": len(order), "read": read,
            "written": written, "plain": plain, "pauses": pauses, "changed": changed}


def hermes_usage(q, hs, sid, totals, calls, cfg):
    """The same from Hermes' session store (lengths and tool names only, read in memory) and its counters."""
    w = cfg["weights"]
    per = float(cfg.get("chars_per_token") or 3.5)
    rows = hs.tool_rows(sid) or []
    chat = cfg.get("chat") or {}
    hour = hs.cache_ttl() == "1h"
    life = chat.get("cache_life_1h" if hour else "cache_life_5m") or (3600 if hour else 300)
    items, seg_end, pos, seg, pauses, last = [], {}, 0, 0, 0, None
    for when, role, tool, size, asked, compacted in rows:
        if compacted:
            seg_end[seg] = pos
            seg += 1
        if role == "assistant":
            pos += 1
            for name, chars in asked:
                items.append((group_of(name), chars / per, pos, seg, True))
        elif role == "tool":
            items.append((group_of(tool), size / per, pos, seg, False))
        if role == "user" and last and when - last > life:
            pauses += 1
        last = when
    seg_end[seg] = pos
    write = w["cache_write_1h"] if hour else w["cache_write_5m"]
    return {"groups": _price(items, seg_end, w, write), "total": hs.weigh_hermes(totals, w), "calls": calls,
            "read": int(totals.get("cache_read_tokens") or 0), "written": int(totals.get("cache_write_tokens") or 0),
            "plain": int(totals.get("input_tokens") or 0), "pauses": pauses, "changed": 0}


def cache_percent(usage):
    """How much of what is sent comes from the cache, in percent; None before anything is sent."""
    whole = usage["read"] + usage["written"] + usage["plain"]
    return 100.0 * usage["read"] / whole if whole else None


def _tip(tip_id, saving, mark, again, key, values, en=None, it=None):
    return {"id": tip_id, "saving": round(saving), "mark": mark, "again": again,
            "en": TEXT[key][0] % dict(values, **(en or {})), "it": TEXT[key][1] % dict(values, **(it or {}))}


def chat_tips(q, cfg, ctx, fresh, job_open, usage):
    """All the tips that hold now, the one that saves most first. A tip's `mark` and `again`: it is told again when the
    mark has grown by `again` since it was told."""
    opts, w = cfg["tips"], cfg["weights"]
    read = w["cache_read"]
    tips = []
    ctx, fresh = ctx or 0, fresh or 0
    base = {"tokens": q.fmt(ctx), "wt": q.fmt(ctx * read), "steps": STEPS}
    again = int(opts.get("again_tokens") or 0)
    if ctx >= (opts.get("new_chat_tokens") or float("inf")):
        saving = max(0, ctx - fresh) * read * STEPS
        tips.append(_tip("new-chat", saving, ctx, again, "new-chat", dict(base, saving=q.fmt(saving))))
    elif ctx >= (opts.get("long_chat_tokens") or float("inf")):
        saving = ctx * 0.5 * read * STEPS
        tips.append(_tip("long-chat", saving, ctx, again, "long-chat", dict(base, saving=q.fmt(saving))))
    if job_open and ctx >= (opts.get("apart_tokens") or float("inf")):
        saving = max(0, ctx - fresh) * read * STEPS - q.installment_start_cost(cfg)
        if saving > 0:
            tips.append(_tip("apart", saving, ctx, again, "apart", dict(base, saving=q.fmt(saving))))
    if usage and usage["total"] >= (opts.get("tool_min_wt") or float("inf")):
        for group, wt in usage["groups"].items():
            share = min(100.0, 100.0 * wt / usage["total"])
            if group in GROUP_TEXT and share >= (opts.get("tool_share") or float("inf")):
                en, it = GROUP_TEXT[group]
                tips.append(_tip("tools-" + group.replace(" ", "-"), wt / 2, share, 10, "tools",
                                 {"share": round(share), "wt": q.fmt(wt)}, {"group": en[0], "advice": en[1]},
                                 {"group": it[0], "advice": it[1]}))
    percent = cache_percent(usage) if usage else None
    target = opts.get("cache_min_percent") or 0
    if percent is not None and percent < target and usage["calls"] >= int(opts.get("cache_min_calls") or 0):
        whole = usage["read"] + usage["written"] + usage["plain"]
        saving = (target / 100.0 * whole - usage["read"]) * max(0.0, w["cache_write_5m"] - read)
        kind, count = (("pauses", usage["pauses"]) if usage["pauses"] else ("changed", usage["changed"])
                       if usage["changed"] else ("new", 0))
        en, it = (REASONS[kind][0] % count, REASONS[kind][1] % count) if count else REASONS[kind]
        tips.append(_tip("cache", saving, usage["calls"], 100, "cache",
                         {"percent": round(percent), "calls": usage["calls"], "target": target, "saving": q.fmt(saving)},
                         {"reason": en}, {"reason": it}))
    return sorted(tips, key=lambda t: -t["saving"])


def _path(q):
    return os.path.join(q.home(), "tips.json")


def hidden(state, tip_id, now):
    """'dropped', 'later' or None: the user's choice about a tip. A date that has passed brings it back."""
    choice = (state.get("hidden") or {}).get(tip_id)
    if not choice:
        return None
    if choice.get("until") is None:
        return "dropped"
    return "later" if choice["until"] > now else None


def _due(tip, told, level):
    """Is a tip to be told now? Level 1 tells each one once in a chat; level 2 again when it has grown."""
    last = told.get(tip["id"])
    if last is None:
        return True
    return level >= 2 and bool(tip["again"]) and tip["mark"] >= last + tip["again"]


def line(q, cfg, sid, ctx, fresh, job_open, usage_of, now=None):
    """What the agent is told at this message: the tips due, the one that saves most first, at most one at level 1 and
    tips.most at level 2. '' when off or nothing is due. usage_of() reads the logs, at most once in tips.every_seconds
    per chat: a long transcript takes time, and a message must not wait."""
    opts = cfg.get("tips") or {}
    level = int(opts.get("level") or 0)
    if not level:
        return ""
    now = now or time.time()
    state = q.load_json(_path(q), {}) or {}
    chats = state.setdefault("chats", {})
    chat = chats.setdefault(sid, {})
    usage = chat.get("usage")
    if not usage or now - float(chat.get("usage_at") or 0) >= (opts.get("every_seconds") or 0):
        usage = usage_of()
        chat.update(usage=usage, usage_at=now)
    tips = chat_tips(q, cfg, ctx, fresh, job_open, usage)
    told = chat.setdefault("told", {})
    due = [t for t in tips if not hidden(state, t["id"], now) and _due(t, told, level)]
    show = due[:1 if level < 2 else max(1, int(opts.get("most") or 1))]
    for t in show:
        told[t["id"]] = t["mark"]
    state["last"] = {"at": now, "chat": sid, "tips": tips}
    if len(chats) > KEEP_CHATS:
        for old in sorted(chats, key=lambda k: float(chats[k].get("usage_at") or 0))[:len(chats) - KEEP_CHATS]:
            if old != sid:
                chats.pop(old)
    q.save_json(_path(q), state)
    if not show:
        return ""
    return ("SAVING TIPS (estimates; tell the user each in one line, in their language, and then go on with what they "
            "asked; to put one off: `%s tips later <id>`, to throw it away: `tips drop <id>`): " % q.run_cmd() +
            " ".join("[%s] %s" % (t["id"], t["en"]) for t in show))


def recent_family(q):
    """The family of the model the last finished job ran on, for a quote: its model is not known yet."""
    jobs = q.finished_jobs()
    return (jobs[-1].get("family") if jobs else None) or "opus"


def _family_price(q, cfg, family):
    """Dollars per million input tokens: from the table when it has the model, else from the settings."""
    opts = cfg.get("whatif") or {}
    found = q.model_price((opts.get("ids") or {}).get(family))
    if found and found.get("input"):
        return found["input"] * 1e6
    return (opts.get("prices") or {}).get(family)


def what_if(q, cfg, wt, family, lang):
    """Improvement 8: what the same tokens would cost on the cheaper model of whatif.model; '' when off, with no
    numbers, or when that model is not cheaper. The ratio of the input prices: Anthropic's other prices follow them,
    the cache reads of some models excepted."""
    opts = cfg.get("whatif") or {}
    target = opts.get("model")
    if not opts.get("enabled") or not wt or not family or family == target:
        return ""
    now, then = _family_price(q, cfg, family), _family_price(q, cfg, target)
    if not now or not then or then >= now:
        return ""
    ratio = then / now
    if lang == "it":
        return ("Con %s invece di %s gli stessi token costerebbero circa il %d%% del prezzo, circa %s token pesati di "
                "adesso: una stima dai prezzi pubblici, e un modello più economico può fare più passi o lavorare peggio."
                % (target.capitalize(), family.capitalize(), round(100 * ratio), q.fmt(wt * ratio)))
    return ("With %s instead of %s the same tokens would cost about %d%% of the price, about %s of today's weighted "
            "tokens: an estimate from the public prices, and a cheaper model may take more steps or work worse."
            % (target.capitalize(), family.capitalize(), round(100 * ratio), q.fmt(wt * ratio)))


def _week_readings(q):
    return [r for r in q.read_jsonl(q.limits_path(), tail_bytes=4 * 1024 * 1024) if r.get("seven_day") is not None]


def budget_numbers(q, cfg, now=None):
    """The budgets set, as [{"kind", "period", "used", "limit", "share"}]: percent of the weekly limit used against
    each. Today's use is the weekly share now less the last reading before midnight (or the first of today, or 0 when
    the week started again today). As fresh as the latest reading of the limits."""
    opts = cfg.get("budget") or {}
    rows = _week_readings(q)
    if not rows:
        return []
    now = now or time.time()
    last = rows[-1]
    used = float(last["seven_day"])
    found = []
    if opts.get("week_percent"):
        limit = float(opts["week_percent"])
        found.append({"kind": "week", "period": "%d" % round(float(last.get("seven_day_resets") or 0) / 7200),
                      "used": used, "limit": limit, "share": 100.0 * used / limit})
    if opts.get("day_percent"):
        t = time.localtime(now)
        midnight = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, -1))
        before = [r for r in rows if (r.get("epoch") or 0) < midnight]
        today = [r for r in rows if (r.get("epoch") or 0) >= midnight]
        base = before[-1] if before else (today[0] if today else last)
        reset = abs(float(base.get("seven_day_resets") or 0) - float(last.get("seven_day_resets") or 0)) > 3600
        spent = max(0.0, used - (0.0 if reset else float(base["seven_day"])))
        limit = float(opts["day_percent"])
        found.append({"kind": "day", "period": time.strftime("%Y-%m-%d", t), "used": spent, "limit": limit,
                      "share": 100.0 * spent / limit})
    return found


def budget_check(q, cfg, prompt, now=None):
    """Improvement 10, at each message of a normal chat: (the reason to refuse it or None, a line for the agent or '').
    Each step of budget.warn is told once a period. With budget.stop, past 100%, a message is refused until one says
    BUDGET OK, which lifts the stop until that budget's period ends."""
    opts = cfg.get("budget") or {}
    numbers = budget_numbers(q, cfg, now)
    if not numbers:
        return None, ""
    state = q.load_json(_path(q), {}) or {}
    memory = state.setdefault("budget", {})
    notes, blocked = [], None
    passed = "BUDGET OK" in (prompt or "")
    for b in numbers:
        mine = memory.get(b["kind"])
        if not mine or mine.get("period") != b["period"]:
            mine = memory[b["kind"]] = {"period": b["period"], "told": 0}
        if passed and b["share"] >= 100:
            mine["passed"] = True
        steps = [w for w in opts.get("warn") or [] if b["share"] >= w and w > mine["told"]]
        if steps:
            mine["told"] = max(steps)
            notes.append("BUDGET: %s used %.1f%% of the weekly limit against a budget of %g%% (%d%% of it). Tell the user "
                         "in one line, in their language, and go on." % (
                             "today" if b["kind"] == "day" else "the week", b["used"], b["limit"], round(b["share"])))
        if opts.get("stop") and b["share"] >= 100 and not mine.get("passed"):
            blocked = ("Quotient: the budget of %s is used up (%.1f%% of the weekly limit, budget %g%%). To go on anyway, "
                       "send a message with BUDGET OK in it, or change it with: config budget.stop 0" % (
                           "the day" if b["kind"] == "day" else "the week", b["used"], b["limit"]))
    q.save_json(_path(q), state)
    return blocked, " ".join(notes)


def cmd_budget(q):
    cfg = q.config()
    it = cfg.get("lang") == "it"
    numbers = budget_numbers(q, cfg)
    if not numbers:
        q.out("Nessun budget (o nessuna lettura dei limiti): config budget.day_percent e budget.week_percent.\n" if it else
              "No budget (or no reading of the limits): config budget.day_percent and budget.week_percent.\n")
    for b in numbers:
        name = (("oggi" if b["kind"] == "day" else "la settimana") if it else ("today" if b["kind"] == "day" else "the week"))
        q.out(("%s: %.1f%% del limite settimanale su %g%% di budget (%d%%).\n" if it else
               "%s: %.1f%% of the weekly limit, budget %g%% (%d%%).\n") % (name, b["used"], b["limit"], round(b["share"])))
    if numbers and (cfg.get("budget") or {}).get("stop"):
        q.out("Stop vero acceso.\n" if it else "A real stop is on.\n")


def _tool_uses(q, entries):
    """The tool calls of a transcript, oldest first: (id, name, input)."""
    found = []
    for call in q.ordered_calls(entries):
        found += [(b.get("id"), b.get("name"), b.get("input")) for b in call["tools"]]
    return found


def _error_text(block):
    content = block.get("content")
    if isinstance(content, list):
        content = " ".join(str(b.get("text") or "") for b in content if isinstance(b, dict))
    return re.sub(r"\s+", " ", str(content or "")).strip()[:200]


def loop_found(q, entries, data, limit):
    """What repeats at the end of a transcript, as a sentence, or None: the same call `limit` times in a row (the one
    about to run included), or the same error `limit` times in a row. Whatever else happens in between breaks it, so a
    test run again after an edit is no loop."""
    uses = _tool_uses(q, entries)
    now = (data.get("tool_use_id"), data.get("tool_name"), data.get("tool_input"))
    if not uses or not now[0] or uses[-1][0] != now[0]:
        uses.append(now)
    count = 0
    for use in reversed(uses):
        if use[1] != now[1] or use[2] != now[2]:
            break
        count += 1
    if count >= limit:
        shown = re.sub(r"\s+", " ", str(now[2]))[:120]
        return "the same call of %s %d times in a row (%s)" % (now[1], count, shown)
    results = []
    for e in entries:
        content = (e.get("message") or {}).get("content") if e.get("type") == "user" and not e.get("isSidechain") else None
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                results.append(_error_text(b) if b.get("is_error") else None)
    if results and results[-1]:
        count = 0
        for r in reversed(results):
            if r != results[-1]:
                break
            count += 1
        if count >= limit:
            return "the same error %d times in a row (%s)" % (count, results[-1][:120])
    return None


def loop_check(q, name, data, entries, cfg):
    """Improvement 11, before each tool call of an installment: None to let it pass, or why it is refused. When
    something repeats, Quotient itself writes it in the handoff, and from then on only the handoff passes."""
    limit = int(cfg["rate"].get("loop_stop") or 0)
    sid = str(data.get("session_id") or "")
    if limit <= 0 or not sid:
        return None
    folder = q.rate_dir(name)
    path = os.path.join(folder, "stuck.json")
    handoff = os.path.join(folder, "HANDOFF.md")
    stuck = q.load_json(path, {}) or {}
    what = stuck.get(sid)
    if not what:
        what = loop_found(q, entries, data, limit)
        if not what:
            return None
        stuck[sid] = what
        q.save_json(path, stuck)
        with open(handoff, "a", encoding="utf-8") as f:
            f.write("\nSTUCK (written by Quotient, %s): the installment stopped by itself: %s.\n" % (q.now_iso(), what))
    target = (data.get("tool_input") or {}).get("file_path") or ""
    if data.get("tool_name") in ("Write", "Edit", "MultiEdit", "Read") and target and \
            os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(handoff)):
        return None
    return ("Quotient: this installment is going round in circles: %s. Quotient stopped it and noted it in %s. Do not "
            "try again: add there what you tried, why it fails and where to resume, then stop." % (what, handoff))


def run_numbers(q, entries, cfg):
    """What an installment keeps of this, in numbers: wt by group, and how much came from the cache."""
    usage = claude_usage(q, entries, cfg)
    percent = cache_percent(usage)
    return {"tools": {k: round(v) for k, v in usage["groups"].items()},
            "cache_percent": round(percent, 1) if percent is not None else None}


def run_line(q, cfg, run, lang):
    """One line for an installment's report: where it spent, and its cache when low. '' when off or not measured."""
    opts = cfg.get("tips") or {}
    if not opts.get("level") or not run.get("tools") or not run.get("wt"):
        return ""
    it = lang == "it"
    parts = []
    for group, wt in sorted(run["tools"].items(), key=lambda kv: -kv[1]):
        share = 100.0 * wt / run["wt"]
        if group in GROUP_TEXT and share >= 10:
            parts.append("%s %d%%" % (GROUP_TEXT[group][1 if it else 0][0], min(100, round(share))))
    text = ("Dove è andata la spesa (stima): %s." if it else "Where the spending went (an estimate): %s.") % (
        ", ".join(parts)) if parts else ""
    percent, target = run.get("cache_percent"), opts.get("cache_min_percent") or 0
    if percent is not None and percent < target:
        text += (" Dalla cache solo il %d%% di quello che ha mandato." if it else
                 " Only %d%% of what it sent came from the cache.") % percent
    return text.strip()


def cmd(q, args):
    """`tips`: the list, most useful first; `tips later <id> [--days N]`, `tips drop <id>`, `tips back <id>`."""
    cfg = q.config()
    opts = cfg.get("tips") or {}
    it = cfg.get("lang") == "it"
    state = q.load_json(_path(q), {}) or {}
    now = time.time()
    if args.what in ("later", "drop", "back"):
        if not args.id:
            raise SystemExit("quotient: %s" % ("quale consiglio? Vedi: tips" if it else "which tip? See: tips"))
        tip_id = SAFE.sub("", args.id)
        choices = state.setdefault("hidden", {})
        if args.what == "back":
            choices.pop(tip_id, None)
            done = "Consiglio %s di nuovo attivo." if it else "Tip %s is back."
        elif args.what == "drop":
            choices[tip_id] = {"until": None}
            done = "Consiglio %s scartato (tips back per riaverlo)." if it else "Tip %s dropped (tips back brings it back)."
        else:
            days = args.days if args.days is not None else (opts.get("later_days") or 7)
            choices[tip_id] = {"until": now + days * 86400}
            done = ("Consiglio %%s rimandato di %g giorni." if it else "Tip %%s put off for %g days.") % days
        q.save_json(_path(q), state)
        q.out(done % tip_id + "\n")
        return
    if not opts.get("level"):
        q.out("Consigli spenti: config tips.level 1 (uno solo, una volta) o 2 (tutti).\n" if it else
              "Tips are off: config tips.level 1 (one, once) or 2 (all).\n")
    tips = (state.get("last") or {}).get("tips") or []
    if not tips:
        q.out("Nessun consiglio per ora.\n" if it else "No tips for now.\n")
    for n, t in enumerate(tips, 1):
        why = hidden(state, t["id"], now)
        mark = {"dropped": " (scartato)" if it else " (dropped)", "later": " (rimandato)" if it else " (put off)"}.get(why, "")
        q.out("%d. [%s]%s %s\n" % (n, t["id"], mark, t["it" if it else "en"]))
    rest = [k for k in state.get("hidden") or {} if hidden(state, k, now) and k not in [t["id"] for t in tips]]
    if rest:
        q.out(("Messi da parte: %s\n" if it else "Set aside: %s\n") % ", ".join(sorted(rest)))
