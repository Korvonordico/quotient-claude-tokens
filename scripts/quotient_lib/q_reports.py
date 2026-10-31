"""The report in the chat: costs, weight, other sessions."""

import os
import sys
import time

from quotient_lib import q_costs, q_learning, q_limits, q_longchats, q_pages, q_quotes, q_rates, q_repairs, q_settings, q_timing

# ---------------------------------------------------------------- report

TEXT = {
    "en": {
        "title": "Quotient: estimates against real costs (unit: weighted tokens)",
        "none": "No finished jobs yet. A job is measured when a quote is made (QUOTE: ...) and an option is chosen (CHOICE: ...).",
        "head": "#   date        choice        estimate    corrected   work        +chat       miss",
        "columns": "work = the real cost of the work; +chat = re-reading, at every call, what the chat already held when the job started (system, tools, rules, older conversation): measured apart, not in the estimate.",
        "weight": "Quotient's own weight since 0.9.5: its texts ~%s wt (estimated from characters), %d action(s) ~%s wt (limit readings, choice windows, its commands): %s wt in all, %s of the %s wt measured.",
        "chat_total": "Re-reading what each chat already held: %s wt, %s of the %s wt measured since 0.9.5; of it, older conversation a new chat would not carry: %s wt.",
        "below": "Choices below the maximum: %d job(s). At the maximum they would have cost about %s wt more. This is an estimate (the difference of the quotes x the factor of the time): what a job that was not done would have cost cannot be measured.",
        "moved": "Jobs moved to a new chat on Quotient's advice: %d. Re-reading the old chat would have added about %s wt (an estimate, from the chat part at the time of the quote).",
        "unquoted": "Replies above the threshold without a quote: %d (%s wt).",
        "compact_mode": "Long chats: %s.",
        "compact_keep": "kept as they are (a new chat is offered when it pays)",
        "compact_at": "they compact themselves at about",
        "compactions": "Compactions: %d (%d automatic). Each call after them re-reads less: about %s wt saved (an estimate, without the cost of the summaries themselves).",
        "html": "Page with charts: %s",
        "factor": "Correction factor now: x%.2f (from the last %d jobs)%s",
        "factor_rate": "Installments have their own: x%.2f (from their last %d jobs)",
        "factor_rate_few": "Installments: %d job(s) measured, fewer than %d, so they use the factor of all jobs",
        "factor_rate_all": "Installments learn from all your jobs (learn_rate_all): x%.2f (from the last %d)",
        "uncertain": ", still uncertain: under %d jobs",
        "miss_raw": "Typical miss without correction: %s",
        "trend": "Typical miss with the learned correction: first half %s, second half %s",
        "turns": "Turns measured: %d, median %s wt per turn",
        "note": "Estimates are not guaranteed: they get more precise with use.",
        "limits": "Plan limits now: %s",
        "no_limits": "not read yet (they come from the status line, or from Claude in the desktop app)",
        "capacity_seven_day": "The whole week holds about %s wt (between %s and %s; rough estimate from %d percentage points). Usage outside Quotient's sessions makes it look smaller.",
        "capacity_five_hour": "The 5 hours hold about %s wt (between %s and %s; rough estimate from %d percentage points).",
        "no_capacity_seven_day": "The size of the week is not estimated yet: it needs a few percentage points measured.",
        "no_capacity_five_hour": "The size of the 5 hours is not estimated yet.",
        "ratio": "From the 5 hours: %s points of the 5 hours for 1 point of the week (between %s and %s; %s points of the week in %d windows), so the week holds about %s wt (between %s and %s).",
        "ratio_agree": "The two estimates of the week agree (x%.2f apart).",
        "ratio_disagree": "The two estimates of the week do NOT agree: x%.2f apart, more than x%s. Use Quotient cannot see, or readings far apart, move one more than the other: the direct one is used; worth checking the readings.",
        "ratio_used": "The week's own estimate has fewer than %s points: the one from the 5 hours is used in its place.",
        "ratio_used_before": "The week's own estimate has fewer than %s points: the one from the 5 hours is used in its place, with the ratio of before the change of plan (on the guess that the new plan keeps the same proportion between the 5 hours and the week).",
        "no_ratio": "The ratio between the 5 hours and the week is not measured yet: it needs readings of both within the same windows.",
        "plan_since": "The size of the limit is learned from %s on (%s): the windows of before do not count.",
        "plan_detected": "a change of plan Quotient found; plan-changed --undo takes it back",
        "plan_user": "a change of plan you told",
        "weeks_head": "Week (resets)          used    measured",
        "running": "(in progress)",
        "too_early": "Too early to say whether the weeks are getting lighter: %d complete week(s), at least 4 are needed.",
        "trend_weeks": "Last 2 weeks: %.0f%% of the limit on average; the 2 before: %.0f%%.",
        "hermes_head": "Hermes (same login, same limits): last 5 hours %s wt, last 7 days %s wt, of it subagents %s; re-reading the chat (cache reads) %s of it.",
        "hermes_top": "  heaviest chat: %s wt  %s",
        "hermes_background": "  of it Hermes' calls in the background (such as background_review: Hermes keeps them out of its chats' totals, Quotient adds them since 1.1.4): %s wt (%s); cache writes weighed as %s ones, as Hermes' config says.",
        "hermes_none": "Hermes: not found on this PC.",
        "checks": "Measures set against the week (since 1.1.1): %d judged, %d agree within x%s, %d do not (told in the chat), %d did not while other jobs ran (not told); %d too small or without a reading of the week. The week also moves with use Quotient cannot see: a hint, not a proof.",
        "check_row": "  ! %s job %s: measured %s wt, the week rose %s point(s) (~%s wt): x%.2f",
        "types": "Factor by type of work (%s): %s. A type with fewer than %d jobs of its own uses the general factor.",
        "type_item": "%s x%.2f (%d job(s)%s)",
        "type_general": ", general factor",
        "chat_jobs": "chat jobs",
        "rate_jobs": "installments",
        "requotes": "New quotes made halfway, from the job's own pace: %d; the new total of the work was x%s from the real one (median), the first quote x%s.",
        "env_head": "Change of environment (plugins, MCP servers, hooks), %s: %s",
        "env_side": "  %s %s: %d job(s), factor %s, 1M wt of work cost %s in all (work and re-reading)",
        "env_before": "before",
        "env_after": "after",
        "elsewhere": "Jobs during which other sessions spent tokens too: %d (%s wt elsewhere): they are in the limits, not in the jobs.",
        "fix": "To repair: %d (see `fix list`: join a job counted in two pieces, or take a wrong measure out of the factor; a copy comes first and `fix undo` takes it back).",
        "excluded": "Jobs taken out of the factor or joined by `fix`: %d, kept in jobs-excluded.jsonl.",
    },
    "it": {
        "title": "Quotient: stime contro costi veri (unità: token pesati)",
        "none": "Ancora nessun lavoro finito. Un lavoro si misura quando c'è un preventivo (QUOTE: ...) e si sceglie un'opzione (CHOICE: ...).",
        "head": "#   data        scelta        stima       corretta    lavoro      +chat       errore",
        "columns": "lavoro = il costo vero del lavoro; +chat = la rilettura, a ogni passo, di quello che la chat conteneva già quando il lavoro è cominciato (sistema, strumenti, regole, conversazione di prima): misurata a parte, non è nella stima.",
        "weight": "Il peso di Quotient stesso dalla 0.9.5: i suoi testi circa %s token pesati (stimati dai caratteri), %d azione/i circa %s (letture dei limiti, finestre di scelta, i suoi comandi): %s in tutto, il %s dei %s misurati.",
        "chat_total": "Rilettura di quello che ogni chat conteneva già: %s token pesati, il %s dei %s misurati dalla 0.9.5; di questi, conversazione di prima che una chat nuova non avrebbe: %s.",
        "below": "Scelte sotto il massimo: %d lavoro/i. Al massimo sarebbero costati circa %s token pesati in più. È una stima (la differenza dei preventivi per il fattore di quel momento): quanto sarebbe costato un lavoro non fatto non si può misurare.",
        "moved": "Lavori spostati in una chat nuova su consiglio di Quotient: %d. Rileggere la chat vecchia avrebbe aggiunto circa %s token pesati (stima, dalla parte chat al momento del preventivo).",
        "unquoted": "Risposte sopra la soglia senza preventivo: %d (%s token pesati).",
        "compact_mode": "Chat lunghe: %s.",
        "compact_keep": "restano come sono (quando conviene, Quotient propone una chat nuova)",
        "compact_at": "si compattano da sole a circa",
        "compactions": "Compattazioni: %d (%d automatiche). Ogni chiamata dopo rilegge meno: circa %s token pesati risparmiati (stima, senza il costo dei riassunti stessi).",
        "html": "Pagina con i grafici: %s",
        "factor": "Fattore di correzione adesso: x%.2f (dagli ultimi %d lavori)%s",
        "factor_rate": "Le rate hanno il loro: x%.2f (dalle ultime %d)",
        "factor_rate_few": "Rate: %d misurate, meno di %d, quindi usano il fattore di tutti i lavori",
        "factor_rate_all": "Le rate imparano da tutti i lavori (learn_rate_all): x%.2f (dagli ultimi %d)",
        "uncertain": ", ancora incerto: meno di %d lavori",
        "miss_raw": "Errore tipico senza correzione: %s",
        "trend": "Errore tipico con la correzione imparata: prima metà %s, seconda metà %s",
        "turns": "Turni misurati: %d, mediana %s token pesati a turno",
        "note": "Le stime non sono garantite: diventano più precise con l'uso.",
        "limits": "Limiti del piano adesso: %s",
        "no_limits": "non ancora letti (arrivano dalla riga di stato, o da Claude nell'app desktop)",
        "capacity_seven_day": "La settimana intera vale circa %s token pesati (fra %s e %s: stima grezza da %d punti percentuali). L'uso fuori dalle sessioni di Quotient la fa sembrare più piccola.",
        "capacity_five_hour": "Le 5 ore valgono circa %s token pesati (fra %s e %s: stima grezza da %d punti percentuali).",
        "no_capacity_seven_day": "Quanto vale la settimana non è ancora stimato: servono alcuni punti percentuali misurati.",
        "no_capacity_five_hour": "Quanto valgono le 5 ore non è ancora stimato.",
        "ratio": "Dalle 5 ore: %s punti delle 5 ore per 1 punto della settimana (fra %s e %s; %s punti della settimana in %d finestre), quindi la settimana vale circa %s token pesati (fra %s e %s).",
        "ratio_agree": "Le due stime della settimana vanno d'accordo (distanti x%.2f).",
        "ratio_disagree": "Le due stime della settimana NON vanno d'accordo: distanti x%.2f, oltre x%s. L'uso che Quotient non vede, o letture lontane fra loro, spostano una più dell'altra: si usa quella diretta; conviene controllare le letture.",
        "ratio_used": "La stima propria della settimana ha meno di %s punti: al suo posto si usa quella dalle 5 ore.",
        "ratio_used_before": "La stima propria della settimana ha meno di %s punti: al suo posto si usa quella dalle 5 ore, col rapporto di prima del cambio di piano (supponendo che il piano nuovo tenga la stessa proporzione fra 5 ore e settimana).",
        "no_ratio": "Il rapporto fra le 5 ore e la settimana non è ancora misurato: servono letture di tutte e due dentro le stesse finestre.",
        "plan_since": "Quanto vale il limite si impara dal %s (%s): le finestre di prima non contano.",
        "plan_detected": "un cambio di piano trovato da Quotient; plan-changed --undo lo annulla",
        "plan_user": "un cambio di piano detto da te",
        "weeks_head": "Settimana (si azzera)   usato   misurato",
        "running": "(in corso)",
        "too_early": "Troppo presto per dire se le settimane si alleggeriscono: %d settimane complete, ne servono almeno 4.",
        "trend_weeks": "Ultime 2 settimane: in media %.0f%% del limite; le 2 prima: %.0f%%.",
        "hermes_head": "Hermes (stesso login, stessi limiti): ultime 5 ore %s token pesati, ultimi 7 giorni %s, di cui aiutanti %s; rilettura della chat (letture dalla cache) il %s.",
        "hermes_top": "  chat più pesante: %s token pesati  %s",
        "hermes_background": "  di cui chiamate di Hermes in sottofondo (come background_review: Hermes le tiene fuori dai totali delle sue chat, Quotient le aggiunge dalla 1.1.4): %s token pesati (%s); scritture in cache pesate da %s, come dice la config di Hermes.",
        "hermes_none": "Hermes: non trovato su questo PC.",
        "checks": "Misure confrontate con la settimana (dalla 1.1.1): %d giudicate, %d tornano entro x%s, %d no (dette in chat), %d no mentre giravano altri lavori (non dette); %d troppo piccole o senza una lettura della settimana. La settimana si muove anche con l'uso che Quotient non vede: un indizio, non una prova.",
        "check_row": "  ! %s lavoro %s: misurati %s token pesati, la settimana è salita di %s punti (~%s): x%.2f",
        "types": "Fattore per tipo di lavoro (%s): %s. Un tipo con meno di %d lavori suoi usa il fattore generale.",
        "type_item": "%s x%.2f (%d lavoro/i%s)",
        "type_general": ", fattore generale",
        "chat_jobs": "lavori in chat",
        "rate_jobs": "rate",
        "requotes": "Nuovi preventivi fatti a metà, dal ritmo del lavoro: %d; il nuovo totale del lavoro era a x%s dal vero (mediana), il primo preventivo a x%s.",
        "env_head": "Cambio di ambiente (plugin, server MCP, hook), %s: %s",
        "env_side": "  %s %s: %d lavoro/i, fattore %s, 1 milione di lavoro è costato %s in tutto (lavoro e rilettura)",
        "env_before": "prima",
        "env_after": "dopo",
        "elsewhere": "Lavori durante i quali anche altre sessioni hanno speso token: %d (%s token pesati altrove): sono nei limiti, non nei lavori.",
        "fix": "Da riparare: %d (vedi `fix list`: riunire un lavoro contato in due pezzi, o togliere dal fattore una misura sbagliata; prima una copia, e `fix undo` la annulla).",
        "excluded": "Lavori tolti dal fattore o riuniti da `fix`: %d, tenuti in jobs-excluded.jsonl.",
    },
}


def savings(jobs):
    """What the choices helped by Quotient avoided, estimated (never measured: a job not done has no cost).
    Below the maximum: the highest option minus the chosen one, times the factor of the time. Moved to a
    new chat: the work times the chat part there was when the quote was made."""
    below, below_wt, moved, moved_wt = 0, 0.0, 0, 0.0
    for j in jobs:
        options = {k: v for k, v in (j.get("options") or {}).items() if isinstance(v, (int, float))}
        if j.get("choice") not in ("rate", "shared") and options and j.get("raw_estimate"):
            top = max(options.values())
            if top > j["raw_estimate"]:
                below += 1
                below_wt += (top - j["raw_estimate"]) * (j.get("factor_used") or 1.0)
        if j.get("chat_avoided_percent"):
            moved += 1
            moved_wt += q_costs.work_of(j) * j["chat_avoided_percent"] / 100.0
    return {"below": below, "below_wt": below_wt, "moved": moved, "moved_wt": moved_wt}


def weight_summary():
    """Quotient's own weight and the re-reading of older chats, over the turns measured since 0.9.5."""
    rows = [r for r in q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl")) if "q_text" in r]
    total = sum(r.get("wt") or 0 for r in rows)
    text = sum(r.get("q_text") or 0 for r in rows)
    acts = sum(r.get("q_actions") or 0 for r in rows)
    acts_wt = sum(r.get("q_actions_wt") or 0 for r in rows)
    unquoted = [r for r in q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl")) if r.get("unquoted")]
    return {"turns": len(rows), "total": total, "text": text, "actions": acts, "actions_wt": acts_wt,
            "weight": text + acts_wt, "chat": sum(r.get("chat") or 0 for r in rows),
            "older": sum(r.get("older") or 0 for r in rows),
            "unquoted": len(unquoted), "unquoted_wt": sum(r.get("wt") or 0 for r in unquoted)}


def share_of(part, whole, lang):
    return q_rates.percent(100.0 * part / whole, lang) if whole else "-"


def hermes_lines(cfg, t, lang):
    """The Hermes section of the report: its chats use the same login, so the same limits."""
    try:
        import hermes_source as hs
    except ImportError:
        return []
    if not cfg.get("hermes", True) or os.environ.get("QUOTIENT_HERMES") == "0" or not hs.available():
        return []
    try:
        hs.sync(q_settings.home(), cfg["weights"])
    except Exception:
        pass
    s = hs.summary(q_settings.home())
    if not s["rows"]:
        return []
    lines = ["", t["hermes_head"] % (q_quotes.fmt(s["five_hour"]), q_quotes.fmt(s["week"]), q_quotes.fmt(s["subagents"]),
                                      share_of(s["read_share"] * s["week"], s["week"], lang))]
    for _sid, c in s["top"][:3]:
        lines.append(t["hermes_top"] % (q_quotes.fmt(c["wt"]), c["title"] or _sid))
    if s["week"]:                        # 1.1.4 (3c): what Hermes' own totals leave out, and its cache
        it = lang == "it"
        lines.append(t["hermes_background"] % (
            q_quotes.fmt(s.get("background") or 0), share_of(s.get("background") or 0, s["week"], lang),
            ("1 ora" if it else "1-hour") if hs.cache_ttl() == "1h" else ("5 minuti" if it else "5-minute")))
        # 1.1.6 (7b): the calls Hermes makes outside a turn are kept nowhere: an estimate, not counted
        lines.append(("Hermes: circa %g%% non visto dai suoi contatori (approvazioni dei comandi, compressioni delle chat "
                      "lunghe, titoli, immagini), stima sui dati dell'autore; non contato." if it else
                      "Hermes: about %g%% not seen by its counters (command approvals, compressions of long chats, "
                      "titles, images), an estimate on the author's data; not counted.") % HERMES_UNSEEN)
    return lines


# ---------------------------------------------------------------- 1.1.6: the costs others already work out
# Hermes keeps its own estimate of each chat's cost, Claude Code gives the cost of each installment (total_cost_usd) and
# of the session to the status line. They are set against Quotient's weighted tokens: a check of the weights, never a
# change of them.

HERMES_UNSEEN = 2.0   # percent of Hermes' use its counters do not keep (approvals, compressions, titles, images): the
#                       author's data, 10-16/10/2026, an estimate (see CHANGELOG 1.1.6)


def hermes_busy(begin, end):
    """True when Hermes' counters grew between two moments (7b: its unseen calls may explain part of a gap)."""
    if not begin or not end:
        return False
    try:
        import hermes_source as hs
        return any(begin <= (r.get("epoch") or 0) <= end for r in hs.read_log(q_settings.home()))
    except Exception:
        return False


def run_rows():
    """Every installment run of every job, oldest first."""
    base = os.path.join(q_settings.home(), "rate")
    rows = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            rows += [dict(r, job=name) for r in q_settings.read_jsonl(os.path.join(base, name, "runs.jsonl"))]
    rows.sort(key=lambda r: r.get("started") or "")
    return rows


def usd_per_wt(cfg=None):
    """Dollars per weighted token from Claude Code's own cost of the last 20 installments (the median), or None under 3."""
    values = [r["usd"] / r["wt"] for r in run_rows() if r.get("usd") and r.get("wt")][-20:]
    return q_learning.median(values) if len(values) >= 3 else None


def solve3(m, v):
    """x with m x = v for a 3 x 3 system (Gauss with pivoting), or None when it has no single answer."""
    a = [list(map(float, m[i])) + [float(v[i])] for i in range(3)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-12:
            return None
        a[c], a[p] = a[p], a[c]
        for r in range(3):
            if r != c:
                f = a[r][c] / a[c][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][3] / a[i][i] for i in range(3)]


def implied_prices(rows):
    """The prices Hermes' costs imply, as multiples of the input price: output and cache read, by least squares on
    usd = a (input + 1.25 cache write) + b output + c cache read over the rows of one model (its cache write at 1.25 x
    input, as Hermes prices it). None with fewer than 10 rows or no single answer."""
    rows = [r for r in rows if r.get("usd") and r.get("usd") > 0]
    if len(rows) < 10:
        return None
    xs = [((r.get("input_tokens") or 0) + 1.25 * (r.get("cache_write_tokens") or 0), r.get("output_tokens") or 0,
           r.get("cache_read_tokens") or 0) for r in rows]
    m = [[sum(x[i] * x[j] for x in xs) for j in range(3)] for i in range(3)]
    v = [sum(x[i] * r["usd"] for x, r in zip(xs, rows)) for i in range(3)]
    found = solve3(m, v)
    if not found or found[0] <= 0:
        return None
    a, b, c = found
    return {"output": b / a, "cache_read": c / a, "rows": len(rows), "input_per_million": a * 1e6}


def hermes_cost(cfg, days=30):
    """Hermes' own cost estimate against Quotient's weighted tokens of the same chats (their own counters, the calls in
    the background left out, since Hermes does not price them in the chat), over the last `days` days."""
    try:
        import hermes_source as hs
    except ImportError:
        return None
    since = time.time() - days * 86400
    rows = [r for r in hs.read_log(q_settings.home()) if r.get("usd") is not None and (r.get("epoch") or 0) >= since]
    usd = sum(r["usd"] for r in rows)
    wt = sum(max(0, r.get("wt", 0) - (r.get("background") or 0)) for r in rows)
    if not rows or usd <= 0 or wt <= 0:
        return None
    models = {}
    for r in rows:
        models.setdefault(r.get("model") or "?", []).append(r)
    model, its = max(models.items(), key=lambda kv: len(kv[1]))
    return {"usd": usd, "wt": wt, "per_wt": usd / wt, "rows": len(rows), "model": model,
            "prices": implied_prices(its)}


def statusline_cost_path():
    return os.path.join(q_settings.home(), "statusline-cost.jsonl")


def record_statusline_cost(sid, usd):
    """The session's cost the status line gets from Claude Code (cost.total_cost_usd), kept when it changes: numbers
    only (1.1.6, the third measure)."""
    path = os.path.join(q_settings.home(), "statusline-cost.json")
    seen = q_settings.load_json(path, {})
    if seen.get(sid) == usd:
        return False
    seen[sid] = usd
    if len(seen) > 50:
        seen = dict(list(seen.items())[-50:])
    q_settings.save_json(path, seen)
    q_settings.append_jsonl(statusline_cost_path(), {"epoch": round(time.time(), 1), "session": sid, "usd": usd})
    return True


def session_usd(rows, sid, begin, end):
    """What a session cost between two moments from the status line's readings: the last reading up to 10 seconds after
    the end (it must come from the last minute of the job) less the last one before the start. None when the readings
    do not cover it."""
    its = sorted((r for r in rows if r.get("session") == sid and r.get("usd") is not None),
                 key=lambda r: r.get("epoch") or 0)
    before = [r for r in its if r["epoch"] <= begin]
    after = [r for r in its if r["epoch"] <= end + 10]
    if not before or not after or after[-1]["epoch"] < end - 60:
        return None
    return max(0.0, after[-1]["usd"] - before[-1]["usd"])


def statusline_jobs(cfg, per_wt):
    """The finished Claude Code jobs the status line's readings cover: (count, their dollars, Quotient's wt of them)."""
    rows = q_settings.read_jsonl(statusline_cost_path())
    if not rows:
        return None
    n, usd, wt = 0, 0.0, 0.0
    for job in q_learning.finished_jobs()[-50:]:
        sid = str(job.get("session") or "")
        if not sid or ":" in sid:
            continue
        cost = session_usd(rows, sid, q_limits.ts_epoch(job.get("started")), q_limits.ts_epoch(job.get("finished")))
        if cost is None or not job.get("actual"):
            continue
        n, usd, wt = n + 1, usd + cost, wt + float(job["actual"])
    return {"jobs": n, "usd": usd, "wt": wt} if n else None


def cost_lines(cfg, lang):
    """1.1.6 in the report: the dollars Hermes, the installments and the status line give, against the weighted tokens."""
    it = lang == "it"
    lines = []
    per = usd_per_wt(cfg)
    if per:
        lines.append(("Costo vero di Claude Code (ultime rate): $%.2f per milione di token pesati." if it else
                      "Claude Code's own cost (last installments): $%.2f per million weighted tokens.") % (per * 1e6))
    h = hermes_cost(cfg)
    if h:
        line = ("Hermes, la sua stima dei costi (30 giorni): $%.2f per %s wt delle sue chat, $%.2f per milione" if it else
                "Hermes' own cost estimate (30 days): $%.2f for %s wt of its chats, $%.2f per million") % (
                    h["usd"], q_quotes.fmt(h["wt"]), h["per_wt"] * 1e6)
        if per:
            apart = h["per_wt"] / per
            line += ((", x%.2f rispetto a Claude Code%s" if it else ", x%.2f against Claude Code%s") % (
                apart, (" (lontani: uno dei pesi o una delle due stime non torna)" if it else
                        " (far apart: a weight or one of the two estimates is off)") if not 0.8 <= apart <= 1.25 else ""))
        lines.append(line + ".")
        p = h["prices"]
        if p:
            w = cfg["weights"]
            far = [k for k, mine in (("output", w["output"]), ("cache_read", w["cache_read"]))
                   if not 0.8 <= p[k] / mine <= 1.25]
            lines.append(("  Prezzi che ne risultano (%s, %d letture): uscita x%.2f l'ingresso, lettura della cache x%.3f; "
                          "Quotient pesa x%g e x%g%s." if it else
                          "  Prices they imply (%s, %d readings): output x%.2f input, cache read x%.3f; Quotient weighs "
                          "x%g and x%g%s.") % (
                h["model"], p["rows"], p["output"], p["cache_read"], w["output"], w["cache_read"],
                ((": diversi oltre x1.25 per %s; i pesi non cambiano da soli (config weights.<nome> <valore>)" if it else
                  ": apart beyond x1.25 for %s; the weights never change by themselves (config weights.<name> <value>)")
                 % ", ".join(far)) if far else ""))
    s = statusline_jobs(cfg, per)
    if s:
        line = ("Riga di stato: %d lavori, $%.2f secondo Claude Code" if it else
                "Status line: %d job(s), $%.2f by Claude Code's count") % (s["jobs"], s["usd"])
        if per:
            mine = s["wt"] * per
            line += ((", contro $%.2f dai token pesati di Quotient (%+.0f%%)" if it else
                      ", against $%.2f from Quotient's weighted tokens (%+.0f%%)") % (mine, 100.0 * (mine - s["usd"]) /
                                                                                     s["usd"] if s["usd"] else 0))
        lines.append(line + ".")
    return lines


def ratio_lines(cfg, t, direct, five, turns=None):
    """The second estimate of the week, from the 5 hours and the ratio between the two windows (1.1.2), beside the
    direct one: whether they agree, or which one is used."""
    least = q_settings.merge(q_settings.DEFAULTS["ratio"], cfg.get("ratio") or {})
    week = None if direct else q_limits.week_capacity(cfg, turns)
    ratio = week["ratio"] if week else q_limits.window_ratio()
    if not ratio or not five:
        return [t["no_ratio"]]
    est = ratio["ratio"] * five["per_point"] * 100
    lines = [t["ratio"] % ("%.1f" % ratio["ratio"], "%.1f" % ratio["low"], "%.1f" % ratio["high"], "%g" % ratio["week_points"],
                           ratio["windows"], q_quotes.fmt(est), q_quotes.fmt(ratio["low"] * five["low"]), q_quotes.fmt(ratio["high"] * five["high"]))]
    if direct:
        mine = direct["per_point"] * 100
        apart = max(est, mine) / max(min(est, mine), 1.0)
        lines.append(t["ratio_agree"] % apart if apart <= float(least["factor"]) else
                     t["ratio_disagree"] % (apart, "%g" % float(least["factor"])))
    elif week:
        lines.append(t["ratio_used" if week["source"] == "ratio" else "ratio_used_before"] % ("%g" % float(least["min_points"])))
    return lines


def report_v114(cfg, t, lang, learned):
    """1.1.4 in the report: the factor of each type of work, how near the new quotes came, the jobs before and after a
    change of the environment, the work done elsewhere meanwhile, and what `fix` would repair."""
    lines = []
    least = int(cfg.get("type_min_jobs") or 3)
    for kind, label in (("chat", t["chat_jobs"]), ("rate", t["rate_jobs"])):
        found = q_learning.type_factors(cfg, kind)
        if found and (len(found) > 1 or found[0][0] != "other"):
            items = [t["type_item"] % (name, f, n, "" if own else t["type_general"]) for name, f, n, own in found]
            lines.append(t["types"] % (label, "; ".join(items), least))
    done = [j for j in learned["jobs"] if (j.get("requote") or {}).get("total")]
    if done:
        lines.append(t["requotes"] % (len(done), q_quotes.fmt_miss(q_learning.median([q_learning.miss(max(q_costs.work_of(j), 1) / j["requote"]["total"]) for j in done]))[1:],
                                      q_quotes.fmt_miss(q_learning.median([q_learning.miss(max(q_costs.work_of(j), 1) / (j["raw_estimate"] * (j.get("factor_used") or 1.0)))
                                                       for j in done]))[1:]))
    for pc, pr in zip(q_learning.env_periods(cfg, "chat"), q_learning.env_periods(cfg, "rate")):
        c = pc["change"]
        sides = [(t["chat_jobs"], pc), (t["rate_jobs"], pr)]
        if not any(p[s]["jobs"] for _, p in sides for s in ("before", "after")):
            continue
        what = "; ".join(x for x in (", ".join("+" + a for a in c.get("added") or []),
                                     ", ".join("-" + r for r in c.get("removed") or [])) if x)
        lines.append(t["env_head"] % (q_limits.when(c["epoch"], lang), what or "?"))
        for label, p in sides:
            for side in ("before", "after"):
                s = p[side]
                if s["jobs"]:
                    lines.append(t["env_side"] % (label, t["env_" + side], s["jobs"],
                                                  "x%.2f" % s["factor"] if s["factor"] else "-",
                                                  q_quotes.fmt(s["per_million"]) if s["per_million"] else "-"))
    busy = [j for j in learned["jobs"] if (j.get("elsewhere") or 0) >= max(50000, 0.05 * (j.get("actual") or 0))]
    if busy:
        lines.append(t["elsewhere"] % (len(busy), q_quotes.fmt(sum(j["elsewhere"] for j in busy))))
    problems = q_repairs.fix_problems(cfg)
    if problems:
        lines.append(t["fix"] % len(problems))
    out_rows = q_settings.read_jsonl(q_repairs.excluded_path())
    if out_rows:
        lines.append(t["excluded"] % len(out_rows))
    return ([""] + lines) if lines else []


def report_v115(cfg, lang):
    """1.1.6 in the report: Claude Code's telemetry, the costs others work out, the packages of work."""
    lines = []
    q = q_settings.entry()
    try:
        import telemetry
        if telemetry.settings(cfg)["enabled"] or os.path.exists(telemetry.checks_path(q_settings.home())):
            telemetry.compare(q, cfg)
            lines += telemetry.report_lines(q, cfg, lang)
    except Exception:  # a section that cannot be worked out must never stop the report
        pass
    for part in (cost_lines, q_timing.package_lines):
        try:
            lines += part(cfg, lang)
        except Exception:
            pass
    return ([""] + lines) if lines else []


def report(args=None):
    cfg = q_settings.config()
    try:
        q_learning.backfill_chat(time.time() + 15)
    except Exception:
        pass
    t = TEXT.get(cfg.get("lang"), TEXT["en"])
    lang = cfg.get("lang")
    if args is not None and getattr(args, "html", False):
        path = q_pages.report_html(cfg)
        q_settings.out(t["html"] % path + "\n")
        if not getattr(args, "no_open", False):
            q_pages.open_file(path)
        return
    learned = q_learning.learning(cfg)
    rows = learned["rows"]
    lines = [t["title"], ""]
    if not rows:
        lines.append(t["none"])
    else:
        lines.append(t["head"])
        for i, r in enumerate(rows[-30:], start=max(1, len(rows) - 29)):
            j = r["job"]
            lines.append("%-3d %-11s %-13s %-11s %-11s %-11s %-11s %s" % (
                i, (j.get("finished") or "")[:10], (j.get("choice") or "")[:13], q_quotes.fmt(j["raw_estimate"]),
                q_quotes.fmt(r["corrected"]), q_quotes.fmt(r["work"]), "+" + q_quotes.fmt(j["chat"]) if j.get("chat") else "-",
                q_quotes.fmt_miss(r["miss_corrected"])))
        lines.append(t["columns"])
        lines.append("")
        n = len(rows)
        own_n = learned["kind_jobs"] if learned["kind_jobs"] >= cfg["min_jobs"] else n
        lines.append(t["factor"] % (learned["factor"], min(own_n, cfg["history_window"]),
                                    t["uncertain"] % cfg["min_jobs"] if n < cfg["min_jobs"] else ""))
        rate = q_learning.learning(cfg, "rate")
        if rate.get("all"):
            lines.append(t["factor_rate_all"] % (rate["factor"], min(rate["kind_jobs"], cfg["history_window"])))
        else:
            lines.append(t["factor_rate"] % (rate["factor"], min(rate["kind_jobs"], cfg["history_window"]))
                         if rate["kind_jobs"] >= cfg["min_jobs"] else
                         t["factor_rate_few"] % (rate["kind_jobs"], cfg["min_jobs"]))
        lines.append(t["miss_raw"] % q_quotes.fmt_miss(q_learning.median([r["miss_raw"] for r in rows])))
        if n >= 2:
            half = n // 2
            lines.append(t["trend"] % (q_quotes.fmt_miss(q_learning.median([r["miss_corrected"] for r in rows[:half]])),
                                       q_quotes.fmt_miss(q_learning.median([r["miss_corrected"] for r in rows[half:]]))))
        try:
            lines += report_v114(cfg, t, lang, learned)
        except Exception:  # a section that cannot be worked out must never stop the report
            pass
    turns = [x["wt"] for x in q_settings.read_jsonl(os.path.join(q_settings.home(), "turns.jsonl")) if x.get("wt")]
    if turns:
        lines.append(t["turns"] % (len(turns), q_quotes.fmt(q_learning.median(turns))))
    s = weight_summary()
    if s["turns"]:
        lines += ["", t["weight"] % (q_quotes.fmt(s["text"]), s["actions"], q_quotes.fmt(s["actions_wt"]), q_quotes.fmt(s["weight"]),
                                     share_of(s["weight"], s["total"], lang), q_quotes.fmt(s["total"])),
                  t["chat_total"] % (q_quotes.fmt(s["chat"]), share_of(s["chat"], s["total"], lang), q_quotes.fmt(s["total"]), q_quotes.fmt(s["older"]))]
    saved = savings(learned["jobs"])
    if saved["below"]:
        lines.append(t["below"] % (saved["below"], q_quotes.fmt(saved["below_wt"])))
    if saved["moved"]:
        lines.append(t["moved"] % (saved["moved"], q_quotes.fmt(saved["moved_wt"])))
    if s["unquoted"]:
        lines.append(t["unquoted"] % (s["unquoted"], q_quotes.fmt(s["unquoted_wt"])))
    c = q_longchats.compaction_summary()
    target = q_longchats.compact_target(cfg)
    lines.append(t["compact_mode"] % (("%s %s" % (t["compact_at"], q_quotes.fmt(target))) if target else t["compact_keep"]))
    if c["count"]:
        lines.append(t["compactions"] % (c["count"], c["auto"], q_quotes.fmt(c["saved"])))
    lines += hermes_lines(cfg, t, lang)
    q_limits.refresh_limits(cfg)
    try:
        q_repairs.measure_checks(cfg)
    except Exception:
        pass
    k = q_repairs.checks_summary()
    if k["judged"] or k["skipped"]:
        lines += ["", t["checks"] % (k["judged"], k["agrees"], q_settings.merge(q_settings.DEFAULTS["check"], cfg.get("check") or {})["factor"],
                                     len(k["warn"]), k["overlap"], k["skipped"])]
        for r in k["warn"][-5:]:
            lines.append(t["check_row"] % (q_limits.when(r["end"], lang), r["label"], q_quotes.fmt(r["wt"]), "%g" % r["points"],
                                           q_quotes.fmt(r["points"] * r["per_point"]), r["ratio"]))
    lines += report_v115(cfg, lang)
    current = q_limits.limits_line(lang)
    lines += ["", t["limits"] % (current or t["no_limits"])]
    since, _, change = q_limits.plan_state()
    if since:
        lines.append(t["plan_since"] % (q_limits.when(since, lang), t["plan_detected" if change.get("source") == "detected"
                                                              else "plan_user"]))
    turns = q_limits.measured_turns(cfg)
    sizes = {}
    for window in ("seven_day", "five_hour"):
        c = sizes[window] = q_limits.capacity(window, turns=turns)
        lines.append(t["capacity_" + window] % (q_quotes.fmt(c["per_point"] * 100), q_quotes.fmt(c["low"]), q_quotes.fmt(c["high"]), c["points"])
                     if c else t["no_capacity_" + window])
    lines += ratio_lines(cfg, t, sizes["seven_day"], sizes["five_hour"], turns)
    rows = q_limits.weeks()
    if rows:
        lines += ["", t["weeks_head"]]
        for r in rows[-8:]:
            lines.append("%-22s %5s%%   %s" % (q_limits.when(r["resets"], lang), round(r["used"]), q_quotes.fmt(r["wt"])) + ("" if r["complete"] else "   " + t["running"]))
        done = [r for r in rows if r["complete"]]
        if len(done) < 4:
            lines.append(t["too_early"] % len(done))
        else:
            recent, before = [r["used"] for r in done[-2:]], [r["used"] for r in done[-4:-2]]
            lines.append(t["trend_weeks"] % (sum(recent) / 2, sum(before) / 2))
    lines += ["", t["note"]]
    q_settings.out("\n".join(lines) + "\n")
