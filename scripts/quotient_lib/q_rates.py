"""Installments: their files, finding Claude Code, notifications, the report page, and each installment's start."""

import glob
import html
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

from quotient_lib import q_hooks, q_learning, q_limits, q_notices, q_quotes, q_schedules, q_settings, q_timing

# ---------------------------------------------------------------- installments

RATE_PROMPT = """You are doing ONE installment of a bigger job, inside a spending cap.
1. Read the job: {task}
2. Read the handoff from the previous installments: {handoff}
3. Continue from where the handoff says. Work in small steps. After each finished step, update {handoff}: what is done, what remains, where to resume. Keep it short. Save results as you go (after each part), not only at the end. If you start helpers (subagents), tell each one to write its results into a file of its own in {notes} as it goes, not only at the end, and give it the path. To count, search or compare, do not read many files or large outputs: write a small script that prints only the result.
4. Keep one line `PROGRESS: <n>%` near the top of {handoff}: your honest estimate of how much of the WHOLE job is done (not of this installment). Quotient uses it to tell how many installments remain. Update this line EVERY time you update {handoff}: Quotient reads it as you go and measures the installment in pieces.
Your working folder is {workdir} (the current folder): the job's own files go there, never next to the task and handoff files.
5. Near the end of the cap Quotient refuses tools that start new work but still lets Write and Edit through: then save at once what you have found. If a tool call is refused because this installment is used up, update {handoff} and stop at once. If the handoff lists the work of helpers stopped in an earlier installment, use their files before searching again.
6. When the WHOLE job is finished, write the line JOB DONE at the top of {handoff}.
This installment's cap: {cap} weighted tokens. This is installment {number} of about {days}."""


LOGIN_ERROR = ("Claude Code is not logged in for runs outside the app (the login expired or was never made): log in "
               "again with `claude auth login` (in a chat, ask Claude to start it)")


def rate_dir(name):
    return os.path.join(q_settings.home(), "rate", re.sub(r"[^\w-]", "_", name))


def task_name(name, once=False, at=None):
    """One daily task per job; one task per time for `rate once`, so a second time does not replace the first."""
    base = "quotient-" + re.sub(r"[^\w-]", "_", name)
    if not once:
        return base
    return base + "-once" + (at.strftime("-%Y%m%d-%H%M") if at else "")


def once_task(name, task):
    """Is this Task Scheduler name one of the job's `rate once` tasks (also the old name, without the time)?"""
    return re.fullmatch(re.escape(task_name(name, once=True)) + r"(-\d{8}-\d{4})?", task) is not None


def find_claude(cfg):
    # A saved path is used only while its file is there: the Claude app removes old version
    # folders when it updates, and a stale path made every installment fail.
    if cfg.get("claude_path") and os.path.exists(cfg["claude_path"]):
        return cfg["claude_path"]
    found = shutil.which("claude")
    if found:
        return found
    # The Claude desktop app keeps its own copy of Claude Code. Since October 2026 it lives in
    # %LOCALAPPDATA%\Claude-Data\claude_<id>\claude-code; before, in %APPDATA%\Claude or, for the
    # Microsoft Store app seen from outside it (a scheduled task), under Packages\Claude_*\LocalCache.
    patterns = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Claude-Data", "claude_*", "claude-code", "*", "*",
                     "claude.exe"),
        os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude-code", "*", "*", "claude.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", "Claude_*", "LocalCache", "Roaming",
                     "Claude", "claude-code", "*", "*", "claude.exe"),
    ]

    def version(path):
        parts = os.path.basename(os.path.dirname(os.path.dirname(path))).split(".")
        return tuple(int(p) if p.isdigit() else 0 for p in parts)

    candidates = sorted((c for pattern in patterns for c in glob.glob(pattern)), key=version)
    return candidates[-1] if candidates else None


def find_transcript(session_id, near=None):
    """A chat's transcript, or None if it is gone. `near` is another transcript: chats are kept next to it."""
    safe = re.sub(r"[^\w-]", "", session_id or "")
    if not safe:
        return None
    roots = [os.path.join(os.path.expanduser("~"), ".claude", "projects")]
    if near:
        roots.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(near))))
    for root in roots:
        found = glob.glob(os.path.join(root, "*", safe + ".jsonl"))
        if found:
            return found[0]
    return None


def chat_id():
    """The Claude Code chat a command runs in (Claude Code passes it to the commands it runs), or None."""
    if os.environ.get("QUOTIENT_JOB"):
        return None  # inside an installment the chat is the installment itself
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def bind_chat(name, sid):
    """The job's installment reports go to this chat from now on."""
    folder = rate_dir(name)
    job = q_settings.load_json(os.path.join(folder, "job.json"), None)
    if not job or job.get("session") == sid:
        return False
    job["session"] = sid
    q_settings.save_json(os.path.join(folder, "job.json"), job)
    state = q_notices.report_state(folder, job)
    state["notices"] = []
    q_settings.save_json(os.path.join(folder, "report.json"), state)
    return True


def next_run(name):
    """When the job's next scheduled installment starts (Windows: read from Task Scheduler): a datetime, None
    when nothing is scheduled, or False when Task Scheduler could not be read (08/10/2026: right after the PC
    resumed, the old query timed out and the report said "no installment is scheduled" although one was)."""
    if os.name != "nt":
        return None
    script = ("$t=@(Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue) + @(Get-ScheduledTask -TaskName "
              "'%s*' -ErrorAction SilentlyContinue); $t | Where-Object { $_ } | Get-ScheduledTaskInfo | Where-Object "
              "{ $_.NextRunTime } | ForEach-Object { $_.NextRunTime.ToString('s') }; 'done'" % (
                  task_name(name), task_name(name, once=True)))
    try:
        proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                              capture_output=True, timeout=30)
        lines = [l.strip() for l in proc.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        if "done" not in lines:
            return False
        times = [datetime.strptime(l, "%Y-%m-%dT%H:%M:%S") for l in lines if l != "done"]
    except Exception:
        return False
    times = [t for t in times if t > datetime.now()]
    return min(times) if times else None


TOAST_APP = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
TOAST_SCRIPT = (
    "$ErrorActionPreference='Stop';"
    "[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
    "[void][Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime];"
    "$t=[Security.SecurityElement]::Escape($env:QUOTIENT_TOAST_TITLE);"
    "$b=[Security.SecurityElement]::Escape($env:QUOTIENT_TOAST_BODY);"
    "$a='';if($env:QUOTIENT_TOAST_LINK){$a=\" activationType='protocol' launch='\"+[Security.SecurityElement]::Escape($env:QUOTIENT_TOAST_LINK)+\"'\"};"
    "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;"
    "$x.LoadXml(\"<toast$a><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>\");"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:QUOTIENT_TOAST_APP)"
    ".Show((New-Object Windows.UI.Notifications.ToastNotification $x))")


def notify(title, body, link=None):
    """A desktop notification, so the user sees that an installment ran without opening anything. On Windows
    it stays in the notification center, and with a link (the report page) a click opens it. The notification
    itself writes no file. Best effort: it never stops an installment."""
    if not q_settings.config()["rate"].get("notify", True):
        return False
    try:
        if os.name == "nt":
            # The text goes to PowerShell in four variables, never inside the command; only while it runs.
            os.environ["QUOTIENT_TOAST_TITLE"] = title
            os.environ["QUOTIENT_TOAST_BODY"] = body
            os.environ["QUOTIENT_TOAST_APP"] = TOAST_APP
            os.environ["QUOTIENT_TOAST_LINK"] = link or ""
            cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", TOAST_SCRIPT]
        elif sys.platform == "darwin":
            def quoted(s):
                return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')
            cmd = ["osascript", "-e", "display notification %s with title %s" % (quoted(body), quoted(title))]
        else:
            cmd = ["notify-send", title, body]
        return subprocess.run(cmd, capture_output=True, timeout=30).returncode == 0
    except Exception:
        return False
    finally:
        os.environ.pop("QUOTIENT_TOAST_TITLE", None)
        os.environ.pop("QUOTIENT_TOAST_BODY", None)
        os.environ.pop("QUOTIENT_TOAST_APP", None)
        os.environ.pop("QUOTIENT_TOAST_LINK", None)


def amount(n, lang):
    """A number of weighted tokens for the user: 548.000, 1,15 milioni / 548,000, 1.15 million."""
    n = float(n or 0)
    if n >= 1e6:
        return ("%.2f milioni" % (n / 1e6)).replace(".", ",") if lang == "it" else "%.2f million" % (n / 1e6)
    text = "{:,}".format(int(round(n)))
    return text.replace(",", ".") if lang == "it" else text


def percent(points, lang):
    """A share for the user: one decimal below 10% (an installment is often well under 1% of the week)."""
    text = "%.1f%%" % points if points < 10 else "%.0f%%" % points
    return text.replace(".", ",") if lang == "it" else text


def page_uri(path):
    """A file path as a link a notification can open (file:///E:/Libri/...)."""
    if not path:
        return ""
    return "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"), safe="/:")


def md_to_html(text):
    """Enough Markdown for a handoff: headings, bullets, bold, code. Everything else is escaped text."""
    lines, in_list = [], False

    def inline(t):
        t = html.escape(t, quote=False)
        t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
        return re.sub(r"`([^`]+)`", r"<code>\1</code>", t)

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        item = re.match(r"^\s*[-*] (.*)", line)
        if item:
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append("<li>%s</li>" % inline(item.group(1)))
            continue
        if in_list:
            lines.append("</ul>")
            in_list = False
        head = re.match(r"^(#{1,3}) (.*)", line)
        if head:
            level = len(head.group(1)) + 1
            lines.append("<h%d>%s</h%d>" % (level, inline(head.group(2)), level))
        elif line.strip():
            lines.append("<p>%s</p>" % inline(line))
    if in_list:
        lines.append("</ul>")
    return "\n".join(lines)


RUN_PAGE_STYLE = ("body{font-family:Segoe UI,system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;"
              "line-height:1.6;color:#1d1d1f;background:#fafaf7}h1{font-size:1.6rem}h2{font-size:1.25rem;margin-top:2rem}"
              "h3{font-size:1.1rem}code{background:#ecebe6;padding:1px 4px;border-radius:4px}.box{background:#fff;"
              "border:1px solid #ddd;border-radius:10px;padding:12px 16px}.err{color:#b3261e}"
              "@media (prefers-color-scheme:dark){body{background:#17171a;color:#e8e6e1}.box{background:#202024;"
              "border-color:#3a3a40}code{background:#2c2c31}}")


def write_report_page(name, job, runs, cfg, folder=None):
    """The installment's report as a page the user opens without writing in any chat (Francesco, 07/10/2026:
    the report shown only at his next message in one chat looked like no report at all). One page per
    installment, in the job's work folder under 'resoconti' ('reports' in English); the notification opens
    it. Best effort: it never stops an installment. Returns the page's path, or None."""
    try:
        it = cfg.get("lang") == "it"
        folder = folder or rate_dir(name)
        base = job.get("dir") if job.get("dir") and os.path.isdir(job["dir"]) else folder
        target = os.path.join(base, "resoconti" if it else "reports")
        os.makedirs(target, exist_ok=True)
        n, run = len(runs), runs[-1]
        title, summary = installment_toast(name, job, runs, cfg, page=True)
        summary = summary.replace("Clicca per aprire il resoconto.", "").replace("Click to open the report.", "")
        parts = ["<h1>%s</h1>" % html.escape(title.replace("Quotient · ", ""), quote=False),
                 "<div class='box'><p>%s</p>" % html.escape(summary.strip(), quote=False)]
        if run.get("error"):
            parts.append("<p class='err'>%s %s</p>" % ("Errore:" if it else "Error:", html.escape(str(run["error"]), quote=False)))
        if job.get("status") == "open":
            nxt = next_run(name)
            parts.append("<p><b>%s</b> %s</p>" % ("Prossima rata:" if it else "Next installment:",
                         q_limits.when(nxt.timestamp(), cfg.get("lang")) if nxt else (("non letta da Windows" if it else "not read from Windows") if nxt is False
                                     else ("nessuna in programma" if it else "none scheduled"))))
        parts.append("<p>%s <code>%s</code></p></div>" % ("Cartella del lavoro:" if it else "Work folder:",
                     html.escape(job.get("dir") or folder, quote=False)))
        text = (q_schedules.load_text(os.path.join(folder, "HANDOFF.md")) or "").strip()
        if text:
            parts.append("<h2>%s</h2>" % ("Cosa ha fatto e cosa manca (scritto dalla rata)" if it else
                                           "What it did and what remains (written by the installment)"))
            parts.append(md_to_html(text))
        page = ("<!doctype html><html lang='%s'><head><meta charset='utf-8'><meta name='viewport' "
                "content='width=device-width,initial-scale=1'><title>%s</title><style>%s</style></head><body>%s"
                "<p><small>Quotient %s</small></p></body></html>") % (
            "it" if it else "en", html.escape(title, quote=False), RUN_PAGE_STYLE, "\n".join(parts), q_settings.VERSION)
        path = os.path.join(target, ("%s-rata-%d.html" if it else "%s-installment-%d.html") % (re.sub(r"[^\w-]", "_", name), n))
        with open(path, "w", encoding="utf-8") as f:
            f.write(page)
        return path
    except Exception:
        return None


def installment_toast(name, job, runs, cfg, page=None):
    """Title and text of the notification at the end of an installment, in the user's language. With a
    report page, the text says a click opens it (and the page itself uses the text as its summary)."""
    it = cfg.get("lang") == "it"
    run = runs[-1]
    n = len(runs)
    chat = find_transcript(job.get("session")) if job.get("session") and not page else None
    if page:
        where = "Clicca per aprire il resoconto." if it else "Click to open the report."
    elif chat:
        where = ("Il resoconto è nella chat %s." if it else "The report is in the chat %s.") % q_notices.chat_label(chat, cfg.get("lang"))
    else:
        where = "Il resoconto arriva nella prossima chat in cui scrivi." if it else "The report comes in the next chat you write in."
    if job.get("status") == "done":
        spent = sum(r.get("wt") or 0 for r in runs)
        title = ("Quotient · «%s» è finito" if it else "Quotient · '%s' is finished") % name
        body = (("%d rata, " if n == 1 else "%d rate, ") + "%s token pesati in tutto%s, %s di lavoro. " if it else
                "%d installment(s), %s weighted tokens in all%s, %s of work. ") % (
            n, amount(spent, cfg.get("lang")),
            ((" (preventivo %s)" if it else " (quote %s)") % amount(job["quote"], cfg.get("lang"))) if job.get("quote") else "",
            q_timing.fmt_duration(sum(q_notices.run_seconds(r) for r in runs)))
    elif run.get("error"):
        title = ("Quotient · rata %d di «%s» non riuscita" if it else "Quotient · installment %d of '%s' failed") % (n, name)
        if str(run["error"]).startswith(LOGIN_ERROR[:40]):
            title = ("Quotient · rata %d di «%s» non partita: login scaduto" if it else
                     "Quotient · installment %d of '%s' did not start: login expired") % (n, name)
            body = ("Claude Code per le rate non è collegato. In una chat chiedi di rifare il login, poi di "
                    "riprovare la rata. Non si è speso niente. " if it else
                    "Claude Code is not logged in for installments. In a chat, ask to log in again, then to retry "
                    "the installment. Nothing was spent. ")
        else:
            body = str(run["error"])[:150].strip().rstrip(".") + ". "
    else:
        per_point = (q_limits.week_capacity(cfg) or {}).get("per_point")
        title = ("Quotient · rata %d di «%s» finita" if it else "Quotient · installment %d of '%s' done") % (n, name)
        body = ("%s–%s · %s token pesati su %s" if it else "%s–%s · %s weighted tokens of %s") % (
            (run.get("started") or "")[11:16], (run.get("finished") or "")[11:16],
            amount(run.get("wt"), cfg.get("lang")), amount(run.get("cap") or job.get("daily_cap"), cfg.get("lang")))
        if q_notices.run_seconds(run):
            body += (" · %s di lavoro%s" if it else " · %s of work%s") % (
                q_timing.fmt_duration(q_notices.run_seconds(run)), ((" (previsti circa %s)" if it else " (about %s expected)") % q_timing.fmt_duration(
                    run["predicted_seconds"])) if run.get("predicted_seconds") else "")
        if per_point and run.get("wt"):
            body += (" · %s della settimana (stima)" if it else " · %s of the week (estimate)") % percent(
                run["wt"] / per_point, cfg.get("lang"))
        left = q_notices.remaining(job, runs)
        if left and left[0] < 100:
            body += ((" · fatto circa il %.0f%%, ne mancano circa %d" if it else " · about %.0f%% done, about %d to go")
                     % (left[0], left[2]))
            est = q_timing.package_estimate(q_timing.run_packages(runs), cfg, "rate")
            if est:   # 1.1.6: the whole job from the packages done, with its margin
                body += ((" · tutto circa %s (fra %s e %s)" if it else " · in all about %s (between %s and %s)") %
                         (q_quotes.fmt(est["total"]), q_quotes.fmt(est["low"]), q_quotes.fmt(est["high"])))
        rq = run.get("requote")
        if rq:   # 1.1.4: the rest will cost much more than the plan
            body += ((" · il resto costerà di più: circa %s (il piano diceva %s)" if it else
                      " · what is left costs more: about %s (the plan said %s)") %
                     (amount(rq["rest"], cfg.get("lang")), amount(rq["plan_rest"], cfg.get("lang"))))
        body += ". "
    return title, body + where


def installment_runs(last=10):
    """The last installments of every job that measured their re-reading, oldest first."""
    runs = []
    base = os.path.join(q_settings.home(), "rate")
    if os.path.isdir(base):
        for name in os.listdir(base):
            runs += q_settings.read_jsonl(os.path.join(base, name, "runs.jsonl"))
    runs = [r for r in runs if r.get("chat") and r.get("wt") and r["wt"] > r["chat"]]
    runs.sort(key=lambda r: r.get("started") or "")
    return runs[-last:]


def run_start_cost(cfg, run):
    """1.2.2: what an installment paid at its first call for its start (system, tools, rules), which a new Claude Code
    session writes to the cache: recorded since 1.2.2; for older runs, the re-reading of the start minus reading it
    from the cache at each later call. None when the run did not measure it."""
    if run.get("start_wt") is not None:
        return float(run["start_wt"])
    if run.get("chat") and run.get("fresh") and run.get("calls"):
        return max(0.0, run["chat"] - cfg["weights"]["cache_read"] * run["fresh"] * (run["calls"] - 1))
    return None


def installment_start_cost(cfg, highest=False):
    """1.2.2: the fixed cost of starting one installment, in wt: the median of the last 10 installments that measured
    it (highest: the largest of them, a start that found nothing in the cache), or the start in tokens written to the
    one-hour cache until there are 2. 0 with rate.start_fixed off."""
    if not (cfg.get("rate") or {}).get("start_fixed"):
        return 0.0
    starts = [s for s in (run_start_cost(cfg, r) for r in installment_runs()) if s is not None]
    if len(starts) >= 2:
        return float((max(starts) if highest else q_learning.median(starts)) or 0.0)
    return cfg["chat"]["installment_start"] * cfg["weights"]["cache_write_1h"]


def cap_floor(cfg):
    """1.2.2: the smallest cap an installment can do something with: rate.min_cap_starts times the largest recent start
    (0: no floor), since a cap must get past a start that finds nothing in the cache."""
    return installment_start_cost(cfg, highest=True) * float((cfg.get("rate") or {}).get("min_cap_starts") or 0)


def installment_overhead(cfg):
    """Re-reading an installment's own start, as a share of its work: learned from the installments that
    measured it (median of the last 10), or worked out from the settings until there are 2. 1.2.2: with
    rate.start_fixed the first call's start is counted apart (installment_start_cost) and left out of the share
    (backtest on 48 measured installments, each from the 10 before it: typical miss of the whole cost 8.9% -> 6.7%,
    within 30% 40 -> 48; installments under 500k of work 36% -> 12%)."""
    fixed = (cfg.get("rate") or {}).get("start_fixed")
    shares = []
    for r in installment_runs():
        start = run_start_cost(cfg, r) if fixed else 0.0
        if start is not None:
            shares.append(max(0.0, r["chat"] - start) / (r["wt"] - r["chat"]))
    if len(shares) >= 2:
        return q_learning.median(shares)
    wpc, _ = q_hooks.work_per_call(cfg)
    return cfg["chat"]["installment_start"] * cfg["weights"]["cache_read"] / wpc


def templates_dir():
    return os.path.join(q_learning.plugin_root(), "templates")


def templates():
    """The ready-made ways of working for long jobs (book, research, code review): name -> first line."""
    found = {}
    for path in sorted(glob.glob(os.path.join(templates_dir(), "*.md"))):
        first = (q_schedules.load_text(path) or "").strip().splitlines()[:1]
        found[os.path.basename(path)[:-3]] = first[0].lstrip("# ").strip() if first else ""
    return found


def rate_templates(args):
    it = q_settings.config().get("lang") == "it"
    q_settings.out(("Modelli per i lavori lunghi a rate (rate new <lavoro> --template <nome> ...):\n" if it else
         "Templates for long installment jobs (rate new <job> --template <name> ...):\n") +
        "".join("  %-12s %s\n" % (k, v) for k, v in templates().items()))


# 1.2.7 (improvement 12): signs that a task says what the job needs. Plain word checks in English and Italian:
# they can miss a vague task written with the right words, or flag a clear one, so they only advise.
