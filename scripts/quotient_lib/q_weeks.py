"""The week: all open installment jobs against the limits, and the list of commands."""

import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from quotient_lib import q_learning, q_limits, q_notices, q_quotes, q_rates, q_schedules, q_settings

# ---------------------------------------------------------------- the week: all installment jobs together

def open_jobs():
    base = os.path.join(q_settings.home(), "rate")
    jobs = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            job = q_settings.load_json(os.path.join(base, name, "job.json"), None)
            if job and job.get("status") == "open":
                job["_runs"] = q_settings.read_jsonl(os.path.join(base, name, "runs.jsonl"))
                jobs.append(job)
    return jobs


def week_plan(cfg):
    """What the open installment jobs will spend before the weekly limit resets, against what is left.

    Each job runs its cap once a day (more if it is set to). The plan is in weighted tokens;
    it becomes a share of the week only when Quotient has estimated how much 1% holds.
    """
    week = q_limits.latest_limits().get("seven_day")
    cap = q_limits.week_capacity(cfg)
    now = time.time()
    resets = (week or {}).get("resets") or now + 7 * 86400
    days_left = max(1, math.ceil((resets - now) / 86400))
    factor = q_learning.learning(cfg, "rate")["factor"]
    rows = []
    for job in open_jobs():
        runs = job["_runs"]
        spent = sum(r.get("wt") or 0 for r in runs)
        left_runs = max(0, (job.get("days") or 0) - len(runs)) if job.get("days") else days_left
        per_day = job.get("per_day") or 1
        planned = min(left_runs, days_left * per_day) * job["daily_cap"]
        left = q_notices.remaining(job, runs)
        if left:
            # the installments' own PROGRESS line knows better than the quote what is left
            planned = min(days_left * per_day * job["daily_cap"], left[1])
            left_runs = left[2]
        elif job.get("quote"):
            planned = min(planned, max(0, job["quote"] * factor - spent))
        rows.append({"name": job["name"], "planned": planned, "cap": job["daily_cap"], "runs_left": left_runs})
    total = sum(r["planned"] for r in rows)
    plan = {"rows": rows, "total": total, "days_left": days_left, "reserve": cfg["week"]["reserve_percent"],
            "used": week["used"] if week else None, "resets": week["resets"] if week else None,
            "per_point": cap["per_point"] if cap else None}
    if week and cap:
        plan["left"] = max(0.0, 100 - week["used"])
        plan["for_jobs"] = max(0.0, plan["left"] - plan["reserve"])
        plan["need"] = total / cap["per_point"]
        plan["fits"] = plan["need"] <= plan["for_jobs"]
    return plan


def week_text(plan, lang):
    it = lang == "it"
    lines = []
    for r in plan["rows"]:
        share = (" (~%.0f%% %s)" % (r["planned"] / plan["per_point"], "della settimana" if it else "of the week")) if plan["per_point"] else ""
        lines.append(("%s: %s token pesati previsti fino all'azzeramento%s, %s rate rimaste" if it else
                      "%s: %s wt planned until the reset%s, %s installments left") % (
            r["name"], q_quotes.fmt(r["planned"]), share, r["runs_left"]))
    if not plan["rows"]:
        lines.append("Nessun lavoro a rate attivo." if it else "No open installment jobs.")
    if "need" in plan:
        lines.append(("Totale: circa %.0f%% della settimana. Resta il %.0f%%; tolta la riserva del %d%% per l'uso normale, "
                      "per le rate c'è il %.0f%%. %s" if it else
                      "Total: about %.0f%% of the week. %.0f%% is left; after the %d%% reserve for normal use, "
                      "%.0f%% is there for installments. %s") % (
            plan["need"], plan["left"], plan["reserve"], plan["for_jobs"],
            ("Ci sta." if plan["fits"] else "NON ci sta: scegli quali lavori tenere, rallentare o mettere in pausa.") if it else
            ("It fits." if plan["fits"] else "It does NOT fit: choose which jobs to keep, slow down or pause.")))
    else:
        lines.append(("Totale: %s token pesati. Quanto vale in percentuale della settimana non è ancora stimato: "
                      "servono alcuni giorni di letture dei limiti." if it else
                      "Total: %s wt. Its share of the week is not estimated yet: it needs a few days of limit readings.") % q_quotes.fmt(plan["total"]))
    return "\n".join(lines)


def rate_week(args):
    cfg = q_settings.config()
    q_settings.out(week_text(week_plan(cfg), cfg.get("lang")) + "\n")


def week_alert(cfg):
    """One line for Claude when the open jobs do not fit in the week; said once for each new situation."""
    plan = week_plan(cfg)
    if "fits" not in plan or plan["fits"]:
        return None
    key = "%s:%d:%d" % (",".join(r["name"] for r in plan["rows"]), round(plan["need"]), round(plan["for_jobs"]))
    path = os.path.join(q_settings.home(), "week-told.txt")
    if q_schedules.load_text(path) == key:
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return ("WEEK: the open installment jobs need ~%.0f%% of the week before it resets, but only %.0f%% is there for them "
            "(%.0f%% left minus the %d%% reserve for normal use). Jobs: %s. Open the choice window: which jobs to keep, "
            "which to slow down (`rate set <name> --daily <n>`), which to pause (`rate pause <name>`); free field." % (
                plan["need"], plan["for_jobs"], plan["left"], plan["reserve"],
                ", ".join("%s ~%.0f%%" % (r["name"], r["planned"] / plan["per_point"]) for r in plan["rows"])))


def week_pace():
    """Where this week's pace leads, from the newest reading of the weekly limit: used, per day, where it
    would be at the reset, and when it would reach 100%. None before half a day of the week has passed."""
    week = q_limits.latest_limits().get("seven_day")
    if not week or not week.get("resets") or not week.get("used"):
        return None
    start = week["resets"] - 7 * 86400
    elapsed = (week["epoch"] - start) / 86400.0
    if elapsed < 0.5:
        return None
    per_day = week["used"] / elapsed
    days_left = max(0.0, (week["resets"] - week["epoch"]) / 86400.0)
    pace = {"used": week["used"], "per_day": per_day, "elapsed": elapsed, "days_left": days_left,
            "projected": week["used"] + per_day * days_left, "resets": week["resets"], "hit": None,
            "fits_per_day": max(0.0, 100 - week["used"]) / days_left if days_left > 0 else None}
    if pace["projected"] >= 100 and per_day > 0:
        pace["hit"] = week["epoch"] + (100 - week["used"]) / per_day * 86400
    return pace


def pace_alert(cfg):
    """One line for Claude when, at this week's pace, the weekly limit runs out before it resets (the
    problem of 01/10/2026: three days of work stopped). Said once for each new situation."""
    p = week_pace()
    if not p or not p["hit"]:
        return None
    key = "%d:%s" % (round(p["resets"] / 3600), datetime.fromtimestamp(p["hit"]).strftime("%Y%m%d"))
    path = os.path.join(q_settings.home(), "pace-told.txt")
    if q_schedules.load_text(path) == key:
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return ("WEEK PACE: %.0f%% of the weekly limit used in %.1f days (~%.0f%% a day). At this pace it runs out around "
            "%s, before it resets (%s). Tell the user once, in ONE line, in their language: to last until the reset, "
            "about %.0f%% a day. Then go on with what they asked." % (
                p["used"], p["elapsed"], p["per_day"], q_limits.when(p["hit"], "en"), q_limits.when(p["resets"], "en"),
                p["fits_per_day"] or 0))


AUTH_EVERY = 6 * 3600  # how often the login for installments is checked, on the user's messages


def auth_alert(cfg):
    """While an installment job is open, check at most every 6 hours (on the user's messages, so there is time
    to fix it before the night) that Claude Code is logged in for runs outside the app. It only reads the
    status, at no token cost; a login that is there but cannot be renewed shows only in a real call
    (`rate check --live`). One line for Claude when it is not logged in."""
    if not any(j.get("status") == "open" for j in open_jobs()):
        return None
    path = os.path.join(q_settings.home(), "auth-check.json")
    state = q_settings.load_json(path, {})
    if time.time() - (state.get("epoch") or 0) < AUTH_EVERY:
        return None
    claude = q_rates.find_claude(cfg)
    if not claude:
        return None
    logged = None
    try:
        proc = subprocess.run([claude, "auth", "status"], capture_output=True, timeout=8)
        logged = json.loads(proc.stdout.decode("utf-8", "replace")).get("loggedIn")
    except Exception:
        pass
    q_settings.save_json(path, {"epoch": round(time.time()), "logged": logged})
    if logged is not False:
        return None
    return ("INSTALLMENTS WILL FAIL: Claude Code is not logged in for runs outside the app (auth status). Tell the "
            "user in ONE line, and offer to start the login now: run `\"%s\" auth login` in the background; the "
            "browser opens and the user clicks Authorize. If the page shows a code, the user pastes it into a "
            "terminal themselves: never handle that code. Then check with `\"%s\" auth status`." % (claude, claude))


def week_room(cfg, job):
    """Weighted tokens this installment may spend without eating into the reserve (None if unknown)."""
    plan = week_plan(cfg)
    if "for_jobs" not in plan:
        return None
    return plan["for_jobs"] * plan["per_point"]


def rate_pause(args):
    set_status(args.name, "paused", from_status="open")


def rate_resume(args):
    set_status(args.name, "open", from_status="paused")


def set_status(name, status, from_status):
    folder = q_rates.rate_dir(name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % name)
    if job["status"] != from_status:
        sys.exit("quotient: '%s' is %s" % (name, job["status"]))
    job["status"] = status
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    q_settings.out("Job '%s' is now %s.%s\n" % (name, status, " Its scheduled runs stay, and skip it until `rate resume`." if status == "paused" else ""))


def rate_set(args):
    folder = q_rates.rate_dir(args.name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    if not job:
        sys.exit("quotient: no job named '%s'" % args.name)
    if args.daily:
        cfg = q_settings.config()
        floor = q_rates.cap_floor(cfg)
        if floor and args.daily < floor:
            q_settings.out("Cap raised from %s to %s wt: an installment spends up to about %s wt just to start, so a smaller cap "
                "could end before any work.\n" % (q_quotes.fmt(args.daily), q_quotes.fmt(math.ceil(floor)),
                                                  q_quotes.fmt(q_rates.installment_start_cost(cfg, highest=True))))
        job["daily_cap"] = int(max(args.daily, math.ceil(floor)))
    if args.per_day:
        job["per_day"] = int(args.per_day)
    if args.days:
        job["days"] = int(args.days)
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    q_settings.out("Job '%s': %s wt per installment, %s per day, %s installments in all.\n" % (
        args.name, q_quotes.fmt(job["daily_cap"]), job.get("per_day") or 1, job.get("days") or "?"))


COMMANDS = [
    # (command, English, Italian)
    ("/token-quotient:setup", "set Quotient up, or change its four settings", "configura Quotient, o cambia le sue quattro impostazioni"),
    ("/token-quotient:report", "estimates against real costs, plan limits, the weeks", "stime contro costi veri, limiti del piano, le settimane"),
    ("/token-quotient:rate <job>", "split a big job into installments, with the choice window", "dividi un lavoro grande in rate, con la finestra di scelta"),
    ("/token-quotient:help", "this list", "questa lista"),
    ("report [--html]", "the report, from a terminal (--html: a page with charts, opened in the browser)",
     "il resoconto, dal terminale (--html: una pagina con i grafici, aperta nel browser)"),
    ("setup --threshold N --reserve N --lang it|en --after sleep|hibernate|nothing", "save the four settings", "salva le quattro impostazioni"),
    ("setup --compact keep|auto|<tokens>", "long chats: keep them as they are, or let them compact themselves at a size",
     "chat lunghe: lasciarle come sono, o farle compattare da sole a una grandezza"),
    ("config [key [value]]", "show every setting, or change one", "mostra tutte le impostazioni, o ne cambia una"),
    ("/token-quotient:share [on|off]", "the shared average: exactly what is sent, and turning it on or off", "la media condivisa: cosa parte esattamente, e accenderla o spegnerla"),
    ("share status|on|off|send", "the same, from a terminal (send: send the waiting lines now)", "lo stesso, dal terminale (send: manda adesso le righe in attesa)"),
    ("tick", "read Hermes' counters and the plan limits now (a scheduled task can run it every few minutes)",
     "legge adesso i contatori di Hermes e i limiti del piano (un'attività pianificata può farlo ogni pochi minuti)"),
    ("hermes", "Hermes Agent chats (same Claude login, same limits): read its token counters now",
     "le chat di Hermes Agent (stesso login di Claude, stessi limiti): legge adesso i suoi contatori dei token"),
    ("export", "the exact line sharing sends for each finished job", "la riga esatta che la condivisione manda per ogni lavoro finito"),
    ("quote-table --raw essential=N good=N max=N [--kind rate] [--type code|writing|research|other] [--words N] [--lang it|en]",
     "the quote worked out by Quotient: every number of each level (time, share of the 5 hours and of the week) and the pace options; the agent copies it",
     "il preventivo calcolato da Quotient: ogni numero di ogni livello (tempo, parte delle 5 ore e della settimana) e le scelte del ritmo; l'agente lo copia"),
    ("fix [list] / fix merge <a> <b> / fix exclude <job> [--why ...] / fix undo",
     "the guided repair: what looks wrong in the measures, joining a job counted in two pieces, taking a wrong measure out of the factor (a copy first, never deleted), and taking the last repair back",
     "la riparazione guidata: cosa non torna nelle misure, riunire un lavoro contato in due pezzi, togliere dal fattore una misura sbagliata (prima una copia, mai cancellato), e annullare l'ultima riparazione"),
    ("timer start --raw N [--level L] / timer show / timer stop",
     "the stopwatch of a quoted job: start it when the work begins (the agent does it), see it, or hide it",
     "il cronometro di un lavoro col preventivo: farlo partire quando comincia il lavoro (lo fa l'agente), vederlo, o nasconderlo"),
    ("backfill-time", "work out the time of the jobs measured before 1.1.0, from the logs (done by itself once)",
     "ricava dai registri il tempo dei lavori misurati prima della 1.1.0 (lo fa da sola una volta)"),
    ("setup-statusline [--write]", "show the plan limits in the status line", "mostra i limiti del piano nella riga di stato"),
    ("plan-changed [--undo] [--plan pro|max5|max20|other|unknown]", "you changed subscription: Quotient learns the size of your limit again from now (--undo: take the last change back; --plan: the new plan)",
     "hai cambiato abbonamento: Quotient reimpara da adesso quanto vale il tuo limite (--undo: annulla l'ultimo cambio; --plan: il piano nuovo)"),
    ("telemetry [status|on|off] [--write]", "Claude Code's own telemetry as a second measure, kept on this PC (numbers only): on prints the settings, --write puts them in settings.json (a copy first)",
     "la telemetria di Claude Code come seconda misura, tenuta su questo PC (solo numeri): on stampa le impostazioni, --write le scrive in settings.json (prima una copia)"),
    ("rate new <job> --dir <folder> --task-file <file> --quote N (--days N | --daily N | --pace \"5 giorni alle 2:00\") [--at HH:MM] [--template book|research|code-review] [--type code|writing|research|other]",
     "create a job in installments (--pace: the user's own words, with days, amount a day and time; a template gives it a tested way of working)",
     "crea un lavoro a rate (--pace: le parole dell'utente, con giorni, quantita' al giorno e ora; un modello gli da' un modo di lavorare gia' provato)"),
    ("rate templates", "the ready-made ways of working: book, research, code review", "i modi di lavorare pronti: libro, ricerca, revisione di codice"),
    ("budget", "the budget of the normal chats, in percent of the weekly limit: how much is used (set it with config budget.day_percent and budget.week_percent; budget.stop 1: a real stop)",
     "il budget delle chat normali, in percentuale del limite settimanale: quanto e' usato (si imposta con config budget.day_percent e budget.week_percent; budget.stop 1: uno stop vero)"),
    ("tips [list|later <id> [--days N]|drop <id>|back <id>]",
     "the tips for saving tokens, most useful first, with an estimate of each; put one off, or drop it (on with config tips.level 1 or 2)",
     "i consigli per risparmiare token, dal piu' utile, ognuno con la sua stima; rimandarne uno o scartarlo (si accendono con config tips.level 1 o 2)"),
    ("task-file --out <file> --dir <folder> --what ... --why ... --read <file[:from-to]> --example <file:from-to> --check <command> --goal ... [--no-ask] [--lang it|en] [--force]",
     "write the task file of a job apart or in installments: what and why, the exact files, code examples, the commands to check, the three stops (goal, cap, stuck); in a terminal it asks what you leave out",
     "scrive il file-compito di un lavoro a parte o a rate: cosa e perche', i file esatti, esempi di codice, i comandi per controllarsi, le tre fermate (obiettivo, tetto, bloccato); nel terminale chiede quello che manca"),
    ("rate apart <job> --dir <folder> --task-file <file> --quote N [--type code|writing|research|other]",
     "do a job apart, now: it starts at once as one installment in a separate session, and its report comes back here",
     "fa un lavoro a parte, adesso: parte subito come una rata sola in una sessione separata, e il resoconto torna qui"),
    ("rate run <job> [--force]", "run one installment now (--force: even if one already ran today)", "fa una rata adesso (--force: anche se oggi ne ha gia' fatta una)"),
    ("rate once <job> [--time HH:MM]", "one installment at that time (tomorrow if it has passed; without --time, the job's own time); wakes the PC",
     "una rata a quell'ora (domani se e' passata; senza --time, l'ora del lavoro); sveglia il PC"),
    ("rate schedule <job> [--time HH:MM] [--force]", "one installment every day at that time (without --time: the job's time, else 03:00); wakes the PC",
     "una rata ogni giorno a quell'ora (senza --time: l'ora del lavoro, se no le 03:00); sveglia il PC"),
    ("rate after <job> sleep|hibernate|nothing", "what the PC does after each installment, if nobody uses it", "cosa fa il PC dopo ogni rata, se nessuno lo usa"),
    ("rate here <job>", "each installment's report comes to this chat (by default: the chat that created the job)", "il resoconto di ogni rata arriva in questa chat (di serie: la chat che ha creato il lavoro)"),
    ("rate week", "all open jobs against what is left of the week", "tutti i lavori attivi contro quello che resta della settimana"),
    ("rate set <job> --daily N --per-day N --days N", "change a job: size of each installment, how many a day, how many in all", "cambia un lavoro: quanto vale ogni rata, quante al giorno, quante in tutto"),
    ("rate pause <job> / rate resume <job>", "pause a job, or start it again", "mette in pausa un lavoro, o lo fa ripartire"),
    ("rate stop <job>", "stop a job and remove its scheduled runs", "ferma un lavoro e toglie i suoi orari"),
    ("rate status [job]", "installments done and weighted tokens spent", "rate fatte e token pesati spesi"),
    ("rate check [--live]", "can a scheduled installment wake this PC, and is Claude Code logged in (--live: one real call, a few cents)",
     "una rata programmata puo' svegliare il PC, e Claude Code e' collegato (--live: una chiamata vera, pochi centesimi)"),
]


def cmd_commands(args=None):
    it = q_settings.config().get("lang") == "it"
    lines = ["Quotient " + q_settings.VERSION + ": " + (
        "il preventivo prima di un lavoro grande dell'IA, il costo vero dopo, la correzione imparata dagli errori, "
        "le rate giornaliere e i limiti del piano." if it else
        "a quote before a big AI job, the real cost after, a correction learned from its errors, "
        "daily installments and the plan limits."), ""]
    lines.append("Comandi nella chat:" if it else "Commands in the chat:")
    for command, en, ita in COMMANDS:
        if command.startswith("/"):
            lines.append("  %-24s %s" % (command, ita if it else en))
    lines += ["", ("Comandi dal terminale (python scripts/quotient.py ...):" if it else
                   "Commands from a terminal (python scripts/quotient.py ...):")]
    for command, en, ita in COMMANDS:
        if not command.startswith("/"):
            lines.append("  " + command)
            lines.append("      " + (ita if it else en))
    q_settings.out("\n".join(lines) + "\n")
