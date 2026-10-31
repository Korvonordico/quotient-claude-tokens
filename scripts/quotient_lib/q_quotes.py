"""The quote worked out: the numbers of each level, the table, and the protocol given to the agent."""

import os
import re
import sys
import time

from quotient_lib import q_costs, q_hooks, q_learning, q_limits, q_rates, q_settings, q_timing, q_weeks

# ---------------------------------------------------------------- formatting

def fmt(n):
    if n is None:
        return "-"
    n = float(n)
    if n >= 1e6:
        return "%.2fM" % (n / 1e6)
    if n >= 1e3:
        return "%.0fk" % (n / 1e3)
    return "%.0f" % n


def fmt_miss(m):
    return "x%.2f" % m if m != float("inf") else "-"


# ---------------------------------------------------------------- hooks

def run_cmd():
    """How Claude should call this script: the same Python that runs the hooks."""
    return '"%s" "%s"' % (sys.executable, q_settings.ENTRY_FILE)


def calibration(cfg, learned):
    """The factor, for the line at each message. 1.1.7: short; the misses before and after the correction are in the
    report, the steps and the working time per million in quote-table's numbers."""
    n = len(learned["jobs"])
    shared = learned.get("shared", 0)
    part = learned.get("shared_weight")
    if part is not None:   # 1.2.3: the shared average stays a part of the factor
        return "Correction factor x%.2f from %d job(s) of yours and the shared average of %d real jobs, which weighs %d%% (installments x%.2f)." % (
            learned["factor"], n, shared, round(part * 100), q_learning.learning(cfg, "rate")["factor"])
    if n == 0 and shared:
        return ("Correction factor x%.2f, from the shared average of %d real jobs (yours take over after %d)." % (
            learned["factor"], shared, cfg["min_jobs"]))
    if n == 0:
        return "No finished jobs yet: correction factor x1, the first estimates will be rough."
    return "Correction factor x%.2f from %d job(s)%s%s (installments x%.2f)." % (
        learned["factor"], n, " plus %d shared" % shared if shared else "",
        " (still uncertain)" if n < cfg["min_jobs"] else "", q_learning.learning(cfg, "rate")["factor"])


# ---------------------------------------------------------------- the quote, worked out by Quotient (1.1.3)
# 15/10/2026, the user: "non sei tu che devi ricordarti, deve essere Quotient". Two quotes had come without the time of
# their levels: now `quote-table` works out every number of a quote, and the end of a reply that quotes checks it.

def level_sizes(cfg):
    return q_settings.merge(q_settings.DEFAULTS["levels"], cfg.get("levels") or {})


def level_count(cfg, corrected):
    """How many levels a quote offers for a job whose biggest level is `corrected` wt of work: 1 to 4."""
    sizes = level_sizes(cfg)
    for n, key in ((1, "one"), (2, "two"), (3, "three")):
        if corrected <= float(sizes[key]):
            return n
    return 4


def level_label(name, lang):
    """A level's name for the user ('Essenziale', 'Good'); a name of the agent's own as it is."""
    words = q_settings.LEVEL_WORDS.get(name)
    label = words["it" if lang == "it" else "en"] if words else name
    return label[:1].upper() + label[1:]


def chat_context():
    """When the command runs inside a Claude Code chat: what each step there re-reads now (tokens) and the chat's own
    start, from its transcript; (None, None) elsewhere (Hermes passes it with --context)."""
    sid = q_rates.chat_id()
    path = q_rates.find_transcript(sid) if sid else None
    if not path:
        return None, None
    state = q_settings.load_json(q_settings.session_path(sid), {})
    return q_costs.context_size(path) or None, state.get("fresh") or q_costs.first_context(path)


def quote_numbers(cfg, options, kind="chat", context=None, wtype=None, factor=None):
    """Every number of a quote, for each level (raw estimates by name, smallest first): the corrected work, the chat part
    (re-reading what the chat holds at each step; for installments, each installment's own start), the total, the
    expected working time, and the share of the 5 hours and of the week the total takes, with what would be left.
    1.1.4: the factor of the type of work when given; factor=1.0 for amounts already corrected (a new quote)."""
    mid = q_learning.mid_factor(cfg) if factor is None and kind == "chat" else None   # hermes branch: the medium band
    own = q_learning.own_chat_factor(cfg) if factor is None and kind == "chat" else None   # improvement 4
    if factor is None:
        factor = q_learning.learning(cfg, kind, wtype)["factor"]
    five, week = q_limits.five_capacity(cfg), q_limits.week_capacity(cfg)
    latest = q_limits.latest_limits()
    steps = q_learning.steps_per_million(cfg, kind)
    overhead = q_rates.installment_overhead(cfg) if kind == "rate" else 0.0
    start = q_rates.installment_start_cost(cfg) if kind == "rate" else 0.0   # 1.2.2: once per installment
    per_step = context * cfg["weights"]["cache_read"] if context and kind != "rate" else None
    wpc = q_hooks.work_per_call(cfg)[0]
    rows = []
    for name, raw in options.items():
        f = q_learning.factor_for(cfg, raw, {"factor": factor, "factor_mid": mid, "factor_own": own}) if mid or own else factor
        work = raw * f
        counted = None
        if kind == "rate":
            chat = work * overhead + start
        elif per_step is not None:
            usual = steps[0] * work / 1e6 if steps else work / max(wpc, 1.0)
            counted = q_learning.chat_steps(cfg, raw, usual)
            chat = (counted[0] if counted else usual) * per_step
        else:
            chat = None
        total = work + (chat or 0)
        row = {"name": name, "raw": raw, "work": work, "chat": chat, "total": total, "factor": f,
               "seconds": q_timing.expected_seconds(cfg, raw, kind, f)}
        if counted:
            row["steps"], row["prudent"] = counted
        for window, c in (("five_hour", five), ("seven_day", week)):
            if c:
                used = (latest.get(window) or {}).get("used")
                row[window] = total / c["per_point"]
                row[window + "_left"] = None if used is None else 100 - used - row[window]
        rows.append(row)
    return {"rows": rows, "factor": factor, "kind": kind, "five": five, "week": week, "steps": steps,
            "overhead": overhead, "start": start, "per_step": per_step}


def pace_options(cfg, options, levels, kind="chat", new_chat=False, wtype=None):
    """The pace options of the window, 4 at most (the window adds its free field by itself): for a job done now, all
    today, in a new chat when this one is long, and apart now (not for a big job: one session would meet the 5-hour
    limit); then installment plans in days, more and longer for a bigger job. Each plan with the amount a day of each
    level, the time proposed, how long an installment takes and the share of the 5 hours and of the week a day takes."""
    rate = quote_numbers(cfg, options, "rate", wtype=wtype)
    mpm = q_timing.minutes_per_million(cfg, "rate")
    at = (cfg.get("rate") or {}).get("time") or "03:00"
    if kind == "rate":
        now = ["apart"] if levels < 4 else []
    else:
        now = ["today"] + (["new-chat"] if new_chat else []) + (["apart"] if levels < 4 else [])
    keys = (now + ["days=%d" % d for d in q_settings.PLAN_DAYS[levels]])[:4]
    biggest = max(rate["rows"], key=lambda r: r["total"])
    found = []
    for key in keys:
        option = {"key": key}
        if key == "apart":
            option["cap"] = biggest["total"]
        elif key.startswith("days="):
            days = int(key[5:])
            # 1.2.2: the rows count one start; each day's installment pays its own
            start = rate["start"]
            option.update(days=days, at=at, daily=[(r["name"], (r["total"] - start) / days + start)
                                                   for r in rate["rows"]])
            top = (biggest["total"] - start) / days + start
            if mpm:
                option["seconds"] = (top - start) / (1 + rate["overhead"]) / 1e6 * mpm[0] * 60.0
            for window, c in (("five_hour", rate["five"]), ("seven_day", rate["week"])):
                if c:
                    option[window] = top / c["per_point"]
        found.append(option)
    return found


def writing_notes(cfg, options, wtype, words, lang):
    """1.1.8, the rule for texts in quote-table: a line for the user (the words and what the rule gives) and a note for
    the agent when its biggest level is under the rule's margin, or when a text is quoted without its words."""
    it = lang == "it"
    if not float(cfg.get("writing_wt_per_word") or 0):
        return [], []
    rule = writing_raw(cfg, words)
    if not rule:
        return [], (["Writing: count about %s wt per word of the final text (TEXTS in the protocol) and run quote-table "
                     "again with --words <the words of the biggest level>." % fmt(cfg["writing_wt_per_word"])]
                    if wtype == "writing" else [])
    top = max(options.values())
    user = [("Testo di circa %s parole: con la regola dei testi (%s token pesati a parola finale, fra %s e %s) il lavoro "
             "grezzo è circa %s, fra %s e %s." if it else
             "A text of about %s words: by the rule for texts (%s weighted tokens per final word, between %s and %s) the "
             "raw work is about %s, between %s and %s.") % (
        q_rates.amount(words, lang), q_rates.amount(cfg["writing_wt_per_word"], lang), q_rates.amount(rule[1] / words, lang),
        q_rates.amount(rule[2] / words, lang), q_rates.amount(rule[0], lang), q_rates.amount(rule[1], lang), q_rates.amount(rule[2], lang))]
    agent = []
    if top < rule[1]:
        agent.append("[for the agent] Nothing to copy yet. Writing: your biggest level (%s wt raw) is under the rule for "
                     "%s words (%s to %s, about %s): estimate each level again with the rule and run quote-table again "
                     "(without --words if the text is not written new, for example a light revision)." % (
                         fmt(top), "{:,}".format(int(words)), fmt(rule[1]), fmt(rule[2]), fmt(rule[0])))
    return user, agent


def chat_steps_note(rows, lang):
    """Improvement 4: the quote says when its chat part rests on few measured jobs."""
    if not any(r.get("prudent") for r in rows):
        return ""
    return ("Parte della chat: stima prudente, ci sono ancora pochi lavori misurati di questa grandezza (conta almeno "
            "%d passi)." if lang == "it" else "Chat part: a prudent estimate, there are still few measured jobs of this "
            "size (it counts at least %d steps).") % round(min(r["steps"] for r in rows if r.get("prudent")))


def small_quote(cfg, options, kind, context, wtype, lang):
    """1.1.8 (small_quote_line): a quote for a job under the threshold, in one line: the biggest level's work, chat part,
    total, time and shares, and a note for the agent (no window, no first-use questions now); None for a job over it.
    In a new session the full table, the window and the first-use questions cost about 70,000 wt, more than the job."""
    if not cfg.get("small_quote_line") or kind == "rate":
        return None
    it = lang == "it"
    nums = quote_numbers(cfg, options, kind, context, wtype)
    top = max(nums["rows"], key=lambda r: r["total"])
    if top["total"] >= float(cfg["threshold"]):
        return None
    parts = ["%s %s" % ("lavoro" if it else "work", q_rates.amount(top["work"], lang))]
    if top["chat"] is not None:
        parts.append(("parte della chat %s" if it else "chat part %s") % q_rates.amount(top["chat"], lang))
    shares = []
    for window, label in (("five_hour", "delle 5 ore" if it else "of the 5 hours"),
                          ("seven_day", "della settimana" if it else "of the week")):
        if window in top:
            shares.append("~%s %s" % (q_rates.percent(top[window], lang), label))
    learned = q_learning.learning(cfg, kind, wtype)
    line = (("PREVENTIVO, lavoro piccolo (sotto la soglia di %s token pesati): circa %s token pesati (%s)%s%s. Le stime "
             "non sono garantite e migliorano con l'uso (fattore x%.2f, da %d lavori)." if it else
             "QUOTE, a small job (under the threshold of %s weighted tokens): about %s weighted tokens (%s)%s%s. The "
             "estimates are not guaranteed and get more precise with use (factor x%.2f, from %d jobs).") % (
        q_rates.amount(cfg["threshold"], lang), q_rates.amount(top["total"], lang), " + ".join(parts),
        ((", circa %s" if it else ", about %s") % q_timing.fmt_duration(top["seconds"])) if top["seconds"] else "",
        (", " + (" e " if it else " and ").join(shares)) if shares else "", learned["factor"],
        learned["type_jobs"] if learned["typed"] else learned["kind_jobs"]))
    prudent = chat_steps_note([top], lang)
    if prudent:
        line += " " + prudent
    raw = round(top["raw"])
    q_settings.save_json(os.path.join(q_settings.home(), "quote-table.json"), {"options": {"good": raw}, "kind": kind, "small": True,
                                                          "epoch": round(time.time()), "session": q_rates.chat_id(), "type": wtype})
    return "\n".join([line, "", "[for the agent, not to copy] A small job: copy the line above as it is, in the user's "
                      "language, and ask in one short sentence whether to go on: no table, no choice window, and the "
                      "first-use questions wait for the first job above the threshold. When the user says yes, write "
                      "`CHOICE: good` and `PACE: today` and do the work.",
                      "Machine line, in the LAST message of the reply: QUOTE: good=%d%s" % (
                          raw, " kind=%s" % wtype if wtype else "")]) + "\n"


def quote_table(cfg, options, kind="chat", context=None, fresh=None, new_chat=None, lang="en", wtype=None, words=None):
    """The quote, ready: a table of the levels with every number, the pace options and what the free field is for, in
    the user's language; then a few lines for the agent (in English). The agent copies the first part as it is.
    1.1.4: `wtype` is the type of work (code, writing, research, other), with its own factor once it has its jobs.
    1.1.8: `words`, the final words of a text (the rule for texts); one line for a small job (small_quote_line)."""
    it = lang == "it"
    told_words, check_words = writing_notes(cfg, options, wtype, words, lang)
    if check_words and words:
        return "\n".join(check_words) + "\n"     # under the rule for texts: estimated again before anything is shown
    small = small_quote(cfg, options, kind, context, wtype, lang)
    if small:
        return small + "".join(n + "\n" for n in check_words)
    nums = quote_numbers(cfg, options, kind, context, wtype)
    rows = nums["rows"]
    biggest = max(rows, key=lambda r: r["work"])
    levels = level_count(cfg, biggest["work"])
    if new_chat is None:
        new_chat = bool(context and fresh and kind != "rate" and q_hooks.new_chat_allowed(cfg, context) and
                        q_hooks.chat_share(cfg, context, fresh)["older_percent"] >= cfg["chat"]["new_chat_percent"])

    def time_of(seconds):
        return ("circa %s" if it else "about %s") % q_timing.fmt_duration(seconds) if seconds else "?"

    def share_of(row, window):
        if window not in row:
            return "?"
        left = row.get(window + "_left")
        text = "~" + q_rates.percent(row[window], lang)
        if left is None:
            return text
        if left < 0:
            return text + ((" (non ci sta: ne resta %s)" if it else " (does not fit: %s left)") %
                           q_rates.percent(max(0.0, left + row[window]), lang))
        return text + ((" (resta %s)" if it else " (%s left)") % q_rates.percent(left, lang))

    lines = [("PREVENTIVO (unità: token pesati)" if it else "QUOTE (unit: weighted tokens)"), ""]
    head = ["Livello" if it else "Level", "Lavoro" if it else "Work",
            ((("Partenza e rilettura delle rate" if it else "Installments' start and re-reading") if nums.get("start")
              else ("Rilettura delle rate" if it else "Installments' re-reading"))) if kind == "rate" else
            ("Parte della chat" if it else "Chat part"), "Totale" if it else "Total",
            "Tempo previsto" if it else "Expected time"]
    head += (["5 ore" if it else "5 hours"] if kind != "rate" else []) + ["Settimana" if it else "Week"]
    lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        cells = [level_label(r["name"], lang), q_rates.amount(r["work"], lang),
                 "+" + q_rates.amount(r["chat"], lang) if r["chat"] is not None else "?", q_rates.amount(r["total"], lang),
                 time_of(r["seconds"])]
        cells += ([share_of(r, "five_hour")] if kind != "rate" else []) + [share_of(r, "seven_day")]
        lines.append("| " + " | ".join(cells) + " |")
    if told_words:
        lines += [""] + told_words
    prudent = chat_steps_note(rows, lang)
    if prudent:
        lines += ["", prudent]
    if (cfg.get("whatif") or {}).get("enabled"):      # improvement 8
        import savings
        cheaper = savings.what_if(q_settings.entry(), cfg, biggest["total"], savings.recent_family(q_settings.entry()), lang)
        if cheaper:
            lines += ["", cheaper]
    unknown = []
    if not any(r["seconds"] for r in rows):
        unknown.append("il tempo previsto arriva dopo 3 lavori misurati col tempo" if it else
                       "the expected time comes after 3 jobs measured with their time")
    if not nums["five"] or not nums["week"]:
        unknown.append("le parti dei limiti arrivano dopo qualche giorno di letture dei limiti" if it else
                       "the shares of the limits come after a few days of limit readings")
    if any(r["chat"] is None for r in rows):
        unknown.append("la parte della chat non è nota qui" if it else "the chat part is not known here")
    if unknown:
        lines.append("")
        lines.append(("Ancora senza numero (?): " if it else "No number yet (?): ") + "; ".join(unknown) + ".")
    if kind == "rate":
        lines.append("")
        if nums.get("start"):
            # 1.2.2: the start is the larger part of a small installment: said, with its number
            lines.append(("Ogni rata è una sessione nuova di Claude Code: paga circa %s token pesati solo per partire "
                          "(regole e strumenti), una volta per rata, poi rilegge il suo inizio a ogni passo. Il tetto di "
                          "ogni giorno paga già tutto questo." if it else
                          "Each installment is a new Claude Code session: it pays about %s weighted tokens just to "
                          "start (rules and tools), once per installment, then re-reads its start at each step. Each "
                          "day's cap already pays for all of it.") % q_rates.amount(nums["start"], lang))
        else:
            lines.append("Ogni rata rilegge solo il suo inizio, e il tetto di ogni giorno lo paga già." if it else
                         "Each installment re-reads only its own start, and each day's cap already pays for it.")

    lines += ["", ("RITMO (al massimo 4 scelte):" if it else "PACE (4 options at most):")]
    for i, o in enumerate(pace_options(cfg, options, levels, kind, new_chat, wtype), 1):
        key = o["key"]
        if key == "today":
            label = "Tutto oggi" if it else "All today"
            desc = "in questa chat, adesso" if it else "in this chat, now"
            short = [r for r in rows if r.get("five_hour_left") is not None and r["five_hour_left"] < 0]
            if short:
                desc += ((": %s non ci sta nelle 5 ore che restano (si fermerebbe al limite)" if it else
                          ": %s does not fit in what is left of the 5 hours (it would stop at the limit)") %
                         ", ".join(level_label(r["name"], lang) for r in short))
        elif key == "new-chat":
            label = "In una nuova chat" if it else "In a new chat"
            desc = ("questa chat è lunga e ogni passo la rilegge: in una chat nuova costa meno" if it else
                    "this chat is long and every step re-reads it: a new chat costs less")
        elif key == "apart":
            label = "A parte, adesso" if it else "Apart, now"
            desc = (("parte subito come una rata sola in una sessione separata (fino a %s per il livello più grande): "
                     "misura pulita e questa chat non la rilegge; ma non le puoi parlare mentre lavora, non fa domande "
                     "a metà, e un comando che chiede un permesso può fermarla") if it else
                    ("it starts at once as one installment in a separate session (up to %s for the biggest level): a "
                     "clean measure, and this chat does not re-read it; but you cannot talk to it while it works, it "
                     "asks no questions halfway, and a command that needs a permission may stop it")) % q_rates.amount(o["cap"], lang)
        else:
            label = ("%d giorni" if it else "%d days") % o["days"]
            per = " · ".join("%s ~%s" % (level_label(n, lang).lower() if len(o["daily"]) > 1 else "", q_rates.amount(v, lang))
                             for n, v in o["daily"]).strip()
            desc = (("al giorno %s; una rata al giorno alle %s" if it else "a day %s; one installment a day at %s") %
                    (per, o["at"]))
            extra = []
            if o.get("seconds"):
                extra.append(("circa %s a rata" if it else "about %s each") % q_timing.fmt_duration(o["seconds"]))
            if "five_hour" in o:
                extra.append(("~%s delle 5 ore" if it else "~%s of the 5 hours") % q_rates.percent(o["five_hour"], lang))
            if "seven_day" in o:
                extra.append(("~%s della settimana al giorno" if it else "~%s of the week a day") %
                             q_rates.percent(o["seven_day"], lang))
            if extra:
                desc += " (%s%s)" % (", ".join(extra), (", livello più grande" if it else ", biggest level")
                                     if len(o["daily"]) > 1 else "")
        lines.append("%d. %s: %s" % (i, label, desc))
    lines += ["", ("ALTRO (il campo libero che la finestra aggiunge da sola): scrivi lì una scelta tua. Per il livello, "
                   "per esempio un mix (una parte della buona e una della massima): Claude la stima e la misura contro "
                   "quella stima. Per il ritmo: quanti giorni, quanto al giorno e a che ora, per esempio «5 giorni alle "
                   "2:00»." if it else
                   "OTHER (the free field the window adds by itself): write a choice of your own there. For the level, "
                   "for example a mix (part of good and part of max): Claude estimates it and it is measured against that "
                   "estimate. For the pace: how many days, how much a day and at what time, for example '5 days at 2:00'.")]
    plan = q_weeks.week_plan(cfg)
    if "for_jobs" in plan and nums["week"]:
        rate_top = max(r["total"] for r in quote_numbers(cfg, options, "rate", wtype=wtype)["rows"])
        room = plan["for_jobs"] - plan["need"]
        need = rate_top / nums["week"]["per_point"]
        lines.append(("Settimana: resta il %s; tolta la riserva del %d%% per l'uso normale e le rate già aperte, per un "
                      "lavoro a rate c'è il %s. Il livello più grande ne chiede circa il %s: %s." if it else
                      "Week: %s is left; after the %d%% reserve for normal use and the open installment jobs, %s is "
                      "there for a job in installments. The biggest level needs about %s: %s.") % (
            q_rates.percent(plan["left"], lang), plan["reserve"], q_rates.percent(max(0.0, room), lang), q_rates.percent(need, lang),
            ("ci sta" if it else "it fits") if need <= room else
            ("non ci sta: più giorni, o meno lavoro" if it else "it does not fit: more days, or less work")))
    learned = q_learning.learning(cfg, kind, wtype)
    typed = ((" di tipo «%s»" if it else " of type '%s'") % wtype) if learned["typed"] else ""
    lines.append(("Le stime non sono garantite e migliorano con l'uso (fattore di correzione x%.2f, da %d lavori%s%s)." if it
                  else "The estimates are not guaranteed and get more precise with use (correction factor x%.2f, from "
                  "%d jobs%s%s).") % (learned["factor"], learned["type_jobs"] if learned["typed"] else learned["kind_jobs"],
                                      ((", chat e rate" if it else ", chat jobs and installments") if learned.get("all") else
                                       (" a rate" if it else " in installments")) if kind == "rate" else "", typed))
    own = q_learning.own_chat_factor(cfg) if kind == "chat" else None
    if own:       # improvement 4: the factor in the table is halfway to this one
        lines[-1] = lines[-1][:-2] + (("; a metà strada con x%.2f, tutti i lavori fatti in chat)." if it else
                                       "; halfway to x%.2f, all the jobs done in a chat).") % own)
    mid = q_learning.mid_factor(cfg) if kind == "chat" else None
    if mid:
        top = cfg["learn_min_raw"]
        end = q_learning.blend_end(cfg, mid, learned["factor"])
        lines[-1] = lines[-1][:-2] + ((("; per i preventivi sotto %s x%.2f; da lì a %s in linea dritta fino a x%.2f, "
                                        "poi x%.2f)." if it else
                                        "; for quotes under %s x%.2f; from it up to %s along a straight line to x%.2f, "
                                        "then x%.2f).") % (q_rates.amount(top, lang), mid, q_rates.amount(end, lang), learned["factor"],
                                                           learned["factor"])) if end > top else
                                      (("; per i preventivi sotto %s x%.2f)." if it else
                                        "; for quotes under %s x%.2f).") % (q_rates.amount(top, lang), mid)))

    names = list(options)
    notes = ["", "[for the agent, not to copy] Copy everything above into your message as it is, in the user's "
             "language. In the window: 'Livello'/'Level' with one option per level (label: its name and total; "
             "description: what it includes, then its time and shares as in the table)%s; 'Ritmo'/'Pace' with the "
             "pace options above. The window adds the free field by itself: a choice written there is estimated by "
             "you and written as `CHOICE: custom=<raw estimate>`; a pace written there goes to `rate new --pace "
             "\"<the user's words>\"`." % ("; with one level, ask only the pace" if len(names) == 1 else ""),
             "Machine line, in the LAST message of the reply: QUOTE: " +
             " ".join("%s=%d" % (n, v) for n, v in options.items()) + (" kind=%s" % wtype if wtype else "")]
    if not wtype:
        notes.append("Add the type of work to the QUOTE line: kind=code, kind=writing, kind=research or kind=other "
                     "(and run quote-table with --type <it>): each type learns its own factor.")
    notes += check_words   # 1.1.8: a text quoted without its words
    if len(names) != levels:
        notes.append("For this size (biggest level ~%s wt of corrected work) Quotient gives %d level%s (%s); you gave "
                     "%d. Unless the user asked otherwise, give %d." % (
                         fmt(biggest["work"]), levels, "" if levels == 1 else "s", ", ".join(q_settings.LEVEL_NAMES[levels]),
                         len(names), levels))
    if len(names) > 4:
        notes.append("The window shows 4 options at most: keep 4 levels.")
    if [options[n] for n in names] != sorted(options.values()):
        notes.append("Write the levels from the smallest to the biggest.")
    q_settings.save_json(os.path.join(q_settings.home(), "quote-table.json"), {"options": options, "kind": kind, "epoch": round(time.time()),
                                                          "session": q_rates.chat_id(), "type": wtype})
    return "\n".join(lines + notes) + "\n"


def quote_gaps(cfg, quote, text, window=()):
    """What a quote shown to the user lacks (1.1.3): for each level, the expected time (when Quotient knows the time of
    work) and its share of the 5 hours and of the week (when it knows their size). `text` is what the reply wrote,
    `window` the options of the window's level question (in Hermes, 1.1.5: also the lines of the reply's messages
    before the last one). [(level, ['time', 'shares']), ...], [] when complete."""
    last = q_settings.load_json(os.path.join(q_settings.home(), "quote-table.json"), {}) or {}
    if last.get("small") and last.get("options") == quote:
        return []     # 1.1.8: a small job's quote is one line (small_quote_line), with no levels to check
    kind = last.get("kind") if last.get("options") == quote else "chat"
    need_time = bool(q_timing.minutes_per_million(cfg, kind))
    windows = (1 if kind != "rate" and q_limits.five_capacity(cfg) else 0) + (1 if q_limits.week_capacity(cfg) else 0)
    if not need_time and not windows:
        return []
    segments = [line for line in (text or "").splitlines() + [str(w) for w in window]
                if not (q_settings.QUOTE_RE.match(line) or q_settings.CHOICE_RE.match(line) or q_settings.PACE_RE.match(line))]
    gaps = []
    for name in quote:
        words = (name,) + tuple((q_settings.LEVEL_WORDS.get(name) or {}).get("also", ()))
        pattern = re.compile(r"(?<![\w])(?:%s)(?![\w])" % "|".join(re.escape(w) for w in words), re.I)
        mine = " ".join(s for s in segments if pattern.search(s))
        lacks = []
        if need_time and not q_settings.TIME_TOKEN_RE.search(mine):
            lacks.append("time")
        if len(q_settings.PERCENT_TOKEN_RE.findall(mine)) < windows:
            lacks.append("shares")
        if lacks:
            gaps.append([name, lacks])
    return gaps


def window_options(turn):
    """The options of the choice window's level question in a turn: label and description, one string each."""
    found = []
    for e in turn or []:
        if e.get("type") != "assistant":
            continue
        for b in (e.get("message") or {}).get("content") or []:
            if not (isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in q_timing.ASK_TOOLS):
                continue
            for q in (b.get("input") or {}).get("questions") or []:
                if isinstance(q, dict) and re.search(r"livell|level", "%s %s" % (q.get("header") or "",
                                                                                  q.get("question") or ""), re.I):
                    found += ["%s %s" % (o.get("label") or "", o.get("description") or "")
                              for o in q.get("options") or [] if isinstance(o, dict)]
    return found


def incomplete_line(gaps, cmd=None):
    """For the agent, at the message after a quote that lacked numbers: give it again in full, first of all."""
    what = {"time": "its expected time", "shares": "its share of the limits (5 hours and week)"}
    told = "; ".join("'%s': %s" % (name, " and ".join(what[k] for k in lacks)) for name, lacks in gaps)
    return ("THE QUOTE BEFORE WAS INCOMPLETE (%s). Before anything else: tell the user in one line, in their language, "
            "that the quote before was incomplete and what it lacked, then give it again in full: run `%s quote-table "
            "--raw <the same raw estimates>` and copy its table as it is. If the user already chose and the missing "
            "numbers do not change the choice, then go on with the job (the same QUOTE line keeps the same job)." % (
                told, cmd or run_cmd()))


def cmd_quote_table(args):
    cfg = q_settings.config()
    options = {}
    for name, number, suffix in q_settings.OPTION_RE.findall(" ".join(args.raw or [])):
        try:
            options[name.lower()] = q_costs.parse_amount(number, suffix)
        except ValueError:
            pass
    if not options or not all(v > 0 for v in options.values()):
        sys.exit("quotient: give the raw estimates as --raw essential=<n> good=<n> max=<n> (1 to 4 levels)")
    context, fresh = (args.context, None) if args.context else chat_context()
    q_settings.out(quote_table(cfg, options, args.kind, context, fresh, True if args.new_chat else None,
                    args.lang or cfg.get("lang") or "en", q_costs.work_type(getattr(args, "type", None)),
                    getattr(args, "words", None)))


WRITING_MARGIN = (0.5, 1.1)   # 1.1.8: the margin of writing_wt_per_word, as shares of it (25 to 55 wt a word for 50)


def writing_raw(cfg, words):
    """1.1.8: the raw estimate of a text of `words` final words by the rule for texts (writing_wt_per_word): (estimate,
    low, high) in wt, or None when the rule is off. With 50: the article of 881 words about 44,000 wt (it cost 49,571),
    the guide of 5,073 words about 254,000 (it cost 257,043)."""
    per = float(cfg.get("writing_wt_per_word") or 0)
    if per <= 0 or not words or words <= 0:
        return None
    return words * per, words * per * WRITING_MARGIN[0], words * per * WRITING_MARGIN[1]


def writing_rule(cfg):
    """1.1.8: the rule for texts, in step 1 of the protocol; '' when writing_wt_per_word is off."""
    per = float(cfg.get("writing_wt_per_word") or 0)
    if per <= 0:
        return ""
    return (" TEXTS (kind=writing): count about %s wt per word of the final text (between %s and %s), its checks and "
            "edits included, whatever the words alone suggest: the text comes out as output (weight 5, about 6.5 tokens a "
            "word through the Write tool), then goes back into the context and is re-read at every call after it. For "
            "example 900 words about %s wt, 5,000 words about %s wt. Give quote-table the words of the biggest level with "
            "--words <n>." % ("{:,}".format(int(per)) if per == int(per) else per, fmt(per * WRITING_MARGIN[0]),
                              fmt(per * WRITING_MARGIN[1]), fmt(900 * per), fmt(5000 * per)))


def additions_rule(cfg):
    """1.1.8: what to do when a task is added to a job (requote_on_addition); '' when it is off. Before 1.1.8 the
    protocol said only that writing during a job adds to its cost: nothing told the agent to quote the new part."""
    if not cfg.get("requote_on_addition"):
        return ""
    return ("ADDITIONS: a message that adds a task to the job (more to do than what was chosen, while the job is open or "
            "right after it ended; not a fix, an answer or a detail of the same task) gets a quote of its own BEFORE you "
            "do it: estimate only the new part, as in steps 1-4, and wait for the choice. A new QUOTE line closes the "
            "open job with what it cost so far, so first finish what was chosen when you can; when the new part cannot "
            "be told apart from what is left, quote what is left of the whole job with it. Quotient then measures the "
            "addition against its own quote.")


def task_file_hint(cfg):
    """Improvement 1: what the protocol says about `task-file`; '' when rate.task_file_hint is off."""
    if not cfg["rate"].get("task_file_hint"):
        return ""
    return ("TASK FILES: the file of a job apart or in installments is written by `%s task-file --out <file> --dir "
            "<work folder> --what \"...\" --why \"...\" --goal \"...\"`, plus `--read <file or file:from-to>`, `--example "
            "<file:from-to>` and `--check \"<command>\"` as many times as needed. It adds the code examples and the three "
            "stops: goal reached, cap, stuck. Name only what the job must read." % run_cmd())


def addition_hint(cfg):
    """1.1.8: the reminder in the open job's line, only where the ASIDE reminder is (the first message of the job and
    after a reply counted apart), so the line of every message does not grow; '' when requote_on_addition is off."""
    return (" If it adds a task to the job, quote the new part before doing it (ADDITIONS)."
            if cfg.get("requote_on_addition") else "")


def protocol(cfg, factor):
    """The full rules, given once at the start of a session (and after a compaction)."""
    cmd = run_cmd()
    sizes = level_sizes(cfg)
    small = (" If the user asks for a quote anyway, run quote-table as below: for a job under the threshold it gives "
             "ONE line, without the table and the window." if cfg.get("small_quote_line") else "")
    added = (", that a task added to it gets a quote of its own" if cfg.get("requote_on_addition") else "")
    return "\n".join([x for x in [
        "[Quotient %s] Quote protocol for this session. Unit: weighted tokens (wt) = input + 1.25 x cache write (2 x for 1-hour cache) + 0.1 x cache read + 5 x output, the ratios of the API prices." % q_settings.VERSION,
        "WHEN: before work that will likely cost more than the threshold (%s wt), and whenever the user calls a job big or asks for a quote. Do not start the work: quote first. Under the threshold, if nobody asks, just work.%s" % (fmt(cfg["threshold"]), small),
        "HOW:",
        "1) Estimate the WORK: the steps of the job itself (reading, writing, checking). Re-reading, at every call, what the chat already holds (system, tools, rules, the conversation so far) is measured apart and added by Quotient (the CHAT PART line at each message gives it): never put it in the estimate.%s" % writing_rule(cfg) + "%s First the biggest level (the whole job done well), then the smaller ones. HOW MANY LEVELS goes with the size of the biggest, as a corrected estimate (raw x the factor, now x%.2f%s; for installments x%.2f): up to %s wt one level, up to %s two, up to %s three, above that four. Their names, from the smallest: one level `good`; two `good max`; three `essential good max`; four `essential good full max` (or short names of your own, in English). Example for a job of 2 million: essential 400k, good 1M, max 2M." % (q_learning.claude_runs_text(cfg), factor, q_learning.mid_text(cfg, factor), q_learning.learning(cfg, "rate")["factor"], fmt(sizes["one"]), fmt(sizes["two"]), fmt(sizes["three"])),
        "2) Let Quotient work the numbers out: run `%s quote-table --raw essential=<n> good=<n> max=<n>` with your raw estimates (add `--kind rate` when the job is surely in installments, `--lang it|en` for the user's language). It gives, for each level, the corrected work, the chat part, the total, the expected TIME and the share of the 5 hours and of the week with what is left, then the pace options that fit the job's size, what the free field is for, and the week. Copy its table into your message AS IT IS: do not work these numbers out yourself and leave none out. The end of the reply checks it: a quote that lacks the time or the shares of a level is sent back at the next message." % cmd,
        "3) Write one machine line with your RAW estimates, always in English, 1 to 4 levels from the smallest, and the TYPE of the work: QUOTE: essential=<n> good=<n> max=<n> kind=<type>. The type is one of code (programs, scripts, with their tests), writing (texts, a book), research (web searches, checking sources) or other (a mix, for example data made and analysed with a report, a web page with its guide, rules or a plan with a small script; or anything else): pass the same with `--type <type>` to quote-table (and to rate new / rate apart). Each type learns its own correction factor, because each goes wrong in its own way.",
        "4) Open the choice window: call the AskUserQuestion tool with two questions in the user's language. 'Livello'/'Level': one option per level, its name and total in the label, what it includes and the table's time and shares in the description; with one level, ask only the pace (a question needs two options). 'Ritmo'/'Pace': the pace options of the table, as they are: all today; 'in a new chat' when this chat is long; 'a parte, adesso'/'apart, now' (the job starts at once as one installment in a separate session: its measure is clean and this chat does not re-read it; it costs the user this: they cannot talk to it while it works, the task must be written well, it asks no questions halfway, a command that needs a permission may stop it); installment plans in days, 2 or 3 for a small job and up to 7 for a big one. One installment = ONE DAY of work: always write a plan in days and per-day amount, e.g. '2 giorni: circa 250.000 token al giorno', '5 giorni: circa 100.000 token al giorno'; never write 'N rate'/'N installments' alone. The window shows 4 options at most per question and adds by itself a free field ('Other'/'Altro'): say what it is for. For the level, a choice of the user's own, e.g. a mix (part of good and part of max); for the pace, how many days, how much a day and AT WHAT TIME (e.g. '5 giorni alle 2:00', '50.000 al giorno'). Say the estimates are not guaranteed and get more precise with use. If the tool is not available, ask the same in text.",
        "Numbers for the user: in words and with the unit ('1,1 milioni di token pesati', not '1.1M'). A range is the margin of the estimate: write it as 'fra 0,7 e 2 milioni' and say so; never bare numbers in parentheses.",
        "5) After the answer write `CHOICE: <level>`. A choice written in the free field: estimate it (raw, as the levels) and write `CHOICE: custom=<n>` (or a short name of your own with its estimate): Quotient measures the job against that estimate. Then one of `PACE: today`, `PACE: apart`, `PACE: new chat`, `PACE: days=<n>`, `PACE: daily=<n>` (add `at=HH:MM` when the user gave a time; the user's own words work too). Apart: write what the whole job is to a file, with everything a session that cannot ask needs, then run `%s rate apart <short-name> --dir <work folder> --task-file <file> --quote <raw estimate of the chosen level>`: it starts at once in the background, and its report comes back to this chat when it ends." % cmd + " If today: start the stopwatch with `%s timer start --raw <raw estimate of the chosen level> --level <level>` (the job's time counts from there), then do the work; if it will not be finished at the end of a reply, end that reply with `JOB: CONTINUES`. Right after the choice, tell the user in one line that writing to you while the job runs adds to its cost%s, and that messages about something else are counted apart: while the job is open, a reply that is not about it ends with the line `ASIDE` (the job stays open; Quotient counts that reply apart from the work). New chat: write what the job is to a file and tell the user to open a new chat and ask to continue it; Quotient tells the new chat, which writes `JOB: RESUME <id>` when it starts. If the user declines: `CHOICE: none`." % (cmd, added),
        "Machine lines (QUOTE, CHOICE, PACE, JOB, ASIDE, LIMITS) go in the LAST message of your reply, the one after your last tool call: a progress note written in the middle of a reply may be kept only as a summary, and then Quotient never sees them. Write QUOTE and CHOICE once: later replies of the same job carry only the JOB line.",
        additions_rule(cfg),
        task_file_hint(cfg),
        "6) Installments: do NOT do the whole job now. Write what the whole job is to a file, then run: %s rate new <short-name> --dir <work folder> --task-file <file> --quote <raw estimate of the chosen level> plus --days <n> or --daily <n> (and --at HH:MM for the time); a pace the user wrote in the free field goes as it is with --pace \"<their words>\": Quotient reads the days, the amount a day and the time from it. Then open a second window with three questions: 'Prima rata'/'First installment' (now; at a time they write; tonight at the time of the plan, 03:00 unless they gave another), 'Ogni giorno'/'Every day' (the daily time; free field; leave it out when the pace already gave the time: `rate schedule <name>` uses it) and 'Dopo la rata'/'After it' (put the PC back to sleep, hibernate, or leave it as it is: whoever turned the PC on, it sleeps only when nobody is using it, after a 2-minute warning). Scheduled installments wake the PC from sleep or hibernation by themselves, not from a full shutdown; run `rate check` first and, if wake timers are off, tell the user how to turn them on (you do not change system settings). Set the choice with `rate after <name> sleep|hibernate|nothing`. Then: now = run `%s rate run <name>` in the background; a time = `rate once <name> --time HH:MM` (today, or tomorrow if the time has passed); every day = `rate schedule <name> --time HH:MM` (without --time: the time of the plan; add --force to run even after another installment the same day). The user may also start an extra installment on the same day (`rate run <name> --force`), at their own risk: it spends more of that day's limit. Let them choose freely. Each installment's report comes back to the chat that ran `rate new`, at the user's next message there (other chats get a one-line notice, twice at most); `rate here <name>` run in another chat moves the reports there." % (cmd, cmd),
        "LIMITS: the Quotient line at each message shows the plan limits (5-hour and weekly) when it knows them (in Claude Code also how many wt 1% holds); quote-table works out each level's share. Before a quote, if the limits are missing or older than 30 minutes and you have a tool that reads the plan usage (for example get_usage), call it and write the line: LIMITS: five_hour=<used %> seven_day=<used %> five_hour_resets=<ISO time> seven_day_resets=<ISO time>. Write it again right after a quoted job ends.",
        "Read the limits before running quote-table, so its shares are fresh. When the table says a level does not fit in what is left of the 5 hours, say so in the window and suggest a pace in days. At the end of a quoted job, tell the user in one line how much of each limit is used and how much is left; at the next message Quotient gives the job's real cost and working time against the expected ones: tell them in one line.",
        "WEEK: before creating installments, run `%s rate week`: it adds up all open installment jobs until the weekly limit resets, against what is left minus a reserve for normal use (%d%%). If the new job would not fit with the others, say so in the window and offer: keep all, slow some down (`rate set <name> --daily <n>`), pause some (`rate pause <name>`), or pace the new one over more days." % (run_cmd(), cfg["week"]["reserve_percent"]),
        "Every decision Quotient needs from the user goes through the choice window, with a free field.",
    ] if x]) + "\n"
