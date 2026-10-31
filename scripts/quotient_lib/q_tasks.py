"""A job's task: the check of what it says, and the task-file command."""

import os
import re
import sys

from quotient_lib import q_learning, q_quotes, q_schedules, q_settings

TASK_FILE_RE = re.compile(r"[\w-]+\.[A-Za-z][A-Za-z0-9]{0,4}\b|\w[\\/]\w|\b[A-Za-z]:[\\/]")
TASK_CHECK_RE = re.compile(r"\b(?:test|prov[aeio]|verif|check|controll|compil|build|lint|confront|compar|assert|"
                           r"misur|measur)", re.I)
TASK_GOAL_RE = re.compile(r"\b(?:obiettiv|scopo|goal|aim\b|done\b|finit|finisc|finish|complet|alla fine|job done|"
                          r"risultat|result|criteri|accettazion|acceptance|success|fermati|fermarti|stop|finché|"
                          r"until|deliverable|consegn|tutt[ie]\b|ogni\b|every\b|each\b|all\b)", re.I)
IMPORT_RE = re.compile(r"(?<![\w`])@(~?[\w./\\:-]+)")


def external_imports_approved(folder):
    """1.2.8: True when the user said yes, in an interactive Claude Code session in `folder`, to loading the files
    its CLAUDE.md rules import from outside it (Claude Code asks once per project and keeps the answer in
    .claude.json). Without that yes such files stay out, and a job started with -p shows no dialog to give it."""
    custom = os.environ.get("QUOTIENT_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
    state = q_settings.load_json(os.path.join(q_learning.claude_dir() if custom else os.path.expanduser("~"), ".claude.json"), {})
    projects = state.get("projects") if isinstance(state, dict) else None
    here = os.path.normcase(os.path.abspath(folder))
    for path, project in projects.items() if isinstance(projects, dict) else []:
        if isinstance(project, dict) and os.path.normcase(os.path.abspath(path)) == here:
            return bool(project.get("hasClaudeMdExternalIncludesApproved"))
    return False


def rules_files(folder):
    """The CLAUDE.md files Claude Code loads for a session in `folder`, with the files they import (@path, up to four
    hops as in Claude Code, not inside code): the user's own, those of the folder and of the folders above it (the
    drive root excluded). 1.2.8: a file that a project CLAUDE.md imports from outside `folder` loads only after a yes
    to Claude Code's dialog in an interactive session there, and a job started with -p shows no dialog: such files go
    in a third list, unless that yes is in .claude.json. Three lists of paths: user, project, outside."""
    seen, outside, approved = set(), [], external_imports_approved(folder)
    inside = os.path.normcase(os.path.abspath(folder)).rstrip("\\/")

    def within(path):
        path = os.path.normcase(path)
        return path == inside or path.startswith(inside + os.sep)

    def take(path, found, depth=0, mine=False):
        path = os.path.abspath(path)
        if os.path.normcase(path) in seen or not os.path.isfile(path):
            return
        seen.add(os.path.normcase(path))
        if depth and not mine and not approved and not within(path):
            outside.append(path)      # 1.2.8: Claude Code leaves it out of a job (checked on the author's PC)
            return
        found.append(path)
        if depth >= 4:
            return
        text = re.sub(r"```.*?```|`[^`\n]*`", "", q_schedules.load_text(path) or "", flags=re.S)
        for ref in IMPORT_RE.findall(text):
            ref = os.path.expanduser(ref.rstrip(".:,;"))
            take(ref if os.path.isabs(ref) else os.path.join(os.path.dirname(path), ref), found, depth + 1, mine)

    user, project, chain, here = [], [], [], os.path.abspath(folder)
    take(os.path.join(q_learning.claude_dir(), "CLAUDE.md"), user, mine=True)
    while os.path.dirname(here) != here:
        chain.append(here)
        here = os.path.dirname(here)
    for d in reversed(chain):
        for name in ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"), "CLAUDE.local.md"):
            take(os.path.join(d, name), project)
    return user, project, outside


def task_check(task, folder, cfg):
    """1.2.7 (improvement 12): what may be missing before a job runs, as short lines for the chat; [] when all looks
    fine or the check is off (rate.task_check)."""
    r = cfg["rate"]
    if not r.get("task_check"):
        return []
    notes = []
    words = len(re.findall(r"\w+", task))
    if words < int(r.get("task_min_words") or 0):
        notes.append("it is short (%d words): the job knows only what the task says" % words)
    if not TASK_FILE_RE.search(task):
        notes.append("it names no file or folder: say which files the job reads first")
    if not TASK_CHECK_RE.search(task):
        notes.append("it gives no way to check the work (tests, a command to run, a comparison)")
    if not TASK_GOAL_RE.search(task):
        notes.append("it does not say when the job is finished (the goal, what counts as done)")
    user, project, outside = rules_files(folder)
    if notes and not project:   # only with a thin task: a detailed one does without (19 of 65 of the author's did)
        notes.append("there is no CLAUDE.md in %s or in the folders above it: the job knows only its task, so the "
                     "task must also give the project's commands and rules" % os.path.abspath(folder))
    chars = sum(len(q_schedules.load_text(p) or "") for p in user + project)
    tokens = chars / float(cfg.get("chars_per_token") or 3.5)
    if r.get("rules_warn_tokens") and tokens > r["rules_warn_tokens"]:
        note = ("the rules Claude Code loads for this folder (%s) are about %s tokens, and every step of every "
                "installment re-reads them (about %s wt a step, from the cache; counted from the characters, an "
                "estimate): what the jobs here do not need could move to files read only when needed" % (
                    ", ".join(user + project), q_quotes.fmt(tokens), q_quotes.fmt(tokens * cfg["weights"]["cache_read"])))
        if outside:   # 1.2.8: named apart and never counted (rules_files)
            note += ("; not counted: %s, imported from outside %s: Claude Code loads such files only after a yes in "
                     "an interactive session in that folder, which a job cannot give, so the job does not see them"
                     % (", ".join(outside), os.path.abspath(folder)))
        notes.append(note)
    return notes


# improvement 1 (the PRP method of Rasmus Widing, Francesco's idea of 18/10/2026): one document with all a job that
# cannot ask needs. The headings and the fixed text of the file, in the user's language.
TASK_FILE_TEXT = {
    "it": {
        "intro": "Il lavoro è già approvato: non fermarti a un piano e non fare domande, nessuno può rispondere. "
                 "Qui sotto c'è tutto quello che serve: leggi solo il necessario.",
        "folder": "Cartella di lavoro: %s",
        "what": "Cosa fare", "why": "Perché", "read": "File da leggere",
        "read_note": "Prima questi, nell'ordine; altri file solo se servono.",
        "lines": "%d righe", "range": "righe %s", "folder_entry": "cartella", "missing_entry": "NON TROVATO quando "
        "questo file è stato scritto: cercalo",
        "read_none": "Nessun file indicato: trova i file giusti con una ricerca, senza leggere tutto.",
        "examples": "Esempi del codice che c'è già, da imitare",
        "examples_none": "Nessun esempio indicato: prima di scrivere guarda come è fatto il codice vicino e imitalo.",
        "cut": "(tagliato a %d righe su %d)",
        "check": "Comandi per controllarti",
        "check_note": "Lanciali dopo ogni parte finita; se uno fallisce, sistema prima di andare avanti.",
        "check_none": "Nessun comando indicato: scegli tu una prova che dimostri il risultato e scrivi cosa ha detto.",
        "stops": "Le tre fermate",
        "goal_stop": "Obiettivo raggiunto: %s Fermati e scrivilo.",
        "goal_default": "tutto quello che c'è in «Cosa fare» è fatto e i comandi di controllo passano.",
        "cap_stop": "Tetto: quando la spesa arriva al tetto (Quotient rifiuta gli strumenti che iniziano lavoro nuovo), "
                    "salva subito cosa hai fatto e dove riprendere, e fermati.",
        "stuck_stop": "Bloccato: dopo %d tentativi sullo stesso problema senza progressi, fermati su quel punto: non "
                      "inventare risultati, scrivi cosa hai provato e perché non va, poi passa alla parte dopo.",
    },
    "en": {
        "intro": "This job is already approved: do not stop at a plan and do not ask questions, nobody can answer. "
                 "All it needs is below: read only what is necessary.",
        "folder": "Working folder: %s",
        "what": "What to do", "why": "Why", "read": "Files to read",
        "read_note": "These first, in this order; other files only if needed.",
        "lines": "%d lines", "range": "lines %s", "folder_entry": "folder", "missing_entry": "NOT FOUND when this file "
        "was written: look for it",
        "read_none": "No files given: find the right ones with a search, without reading everything.",
        "examples": "Examples of the existing code, to imitate",
        "examples_none": "No examples given: before writing, look at how the code nearby is made and imitate it.",
        "cut": "(cut at %d lines of %d)",
        "check": "Commands to check yourself",
        "check_note": "Run them after each finished part; if one fails, fix it before going on.",
        "check_none": "No commands given: choose a test that proves the result and write what it said.",
        "stops": "The three stops",
        "goal_stop": "Goal reached: %s Stop and write it down.",
        "goal_default": "all that is in \"What to do\" is done and the commands to check pass.",
        "cap_stop": "Cap: when the spending reaches the cap (Quotient refuses the tools that start new work), save at "
                    "once what you did and where to resume, and stop.",
        "stuck_stop": "Stuck: after %d attempts at the same problem with no progress, stop on that point: do not invent "
                      "results, write what you tried and why it fails, then go on to the next part.",
    },
}
# The few simple questions, when the command runs in a terminal: (answer, the question in each language, a list?)
TASK_FILE_QUESTIONS = (
    ("what", "Cosa deve fare il lavoro?", "What must the job do?", False),
    ("why", "Perché serve?", "Why is it needed?", False),
    ("read", "Quale file deve leggere? (anche file:10-40; invio vuoto per finire)",
     "Which file must it read? (also file:10-40; empty to finish)", True),
    ("example", "Quale pezzo di codice deve imitare? (file:10-40; invio vuoto per finire)",
     "Which piece of code must it imitate? (file:10-40; empty to finish)", True),
    ("check", "Con quale comando si controlla da solo? (invio vuoto per finire)",
     "Which command does it check itself with? (empty to finish)", True),
    ("goal", "Quando è finito?", "When is it finished?", False),
)
TASK_SPOT_RE = re.compile(r"^(.+?):(\d+)(?:-(\d+))?$")


def task_spot(spec, folder):
    """A file named in the answers, `path` or `path:from-to`: (path as given, full path, first line, last line)."""
    m = TASK_SPOT_RE.match(spec.strip())
    path, first, last = (m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))) if m else (spec.strip(), None, None)
    return path, os.path.join(folder, os.path.expanduser(path)), first, last


def task_read_line(spec, folder, t):
    """One line of the list of files, with its size or range, so a job plans its reading without opening them."""
    path, full, first, last = task_spot(spec, folder)
    if os.path.isdir(full):
        return "- `%s` (%s)" % (path, t["folder_entry"])
    text = q_schedules.load_text(full)
    if text is None:
        return "- `%s` (%s)" % (path, t["missing_entry"])
    size = t["range"] % ("%d-%d" % (first, last)) if first else t["lines"] % len(text.splitlines())
    return "- `%s` (%s)" % (path, size)


def task_example(spec, folder, t, most):
    """An example as the lines themselves: the job imitates them without opening the file. None if there is no file."""
    path, full, first, last = task_spot(spec, folder)
    text = q_schedules.load_text(full) if os.path.isfile(full) else None
    if text is None:
        return None
    lines = text.splitlines()
    chosen = lines[first - 1:last] if first else lines
    head = "### `%s`" % path + (" (%s)" % (t["range"] % ("%d-%d" % (first, last))) if first else "")
    note = ""
    if most and len(chosen) > most:
        note, chosen = "\n" + t["cut"] % (most, len(chosen)), chosen[:most]
    fence = "`" * max([3] + [len(run) + 1 for run in re.findall(r"`{3,}", "\n".join(chosen))])
    return "%s\n%s\n%s\n%s%s" % (head, fence, "\n".join(chosen), fence, note)


def task_file_text(answers, folder, lang, most, stuck):
    """The file of the task: what and why, the exact files, examples, the commands to check, the three stops. Sections
    with no answer say what to do instead, since the job cannot ask."""
    t = TASK_FILE_TEXT[lang if lang in TASK_FILE_TEXT else "en"]
    what = answers["what"].strip()
    parts = ["# " + re.split(r"[\r\n]", what)[0][:100], "", t["intro"], t["folder"] % os.path.abspath(folder), "",
             "## " + t["what"], "", what, ""]
    if answers.get("why"):
        parts += ["## " + t["why"], "", answers["why"].strip(), ""]
    parts += ["## " + t["read"], ""]
    reads = answers.get("read") or []
    parts += ([t["read_note"], ""] + [task_read_line(r, folder, t) for r in reads]) if reads else [t["read_none"]]
    parts += ["", "## " + t["examples"], ""]
    examples = [e for e in (task_example(s, folder, t, most) for s in answers.get("example") or []) if e]
    parts += ["\n\n".join(examples)] if examples else [t["examples_none"]]
    parts += ["", "## " + t["check"], ""]
    checks = answers.get("check") or []
    parts += ([t["check_note"], ""] + ["- `%s`" % c.strip() for c in checks]) if checks else [t["check_none"]]
    goal = (answers.get("goal") or "").strip() or t["goal_default"]
    goal = goal if goal[-1] in ".!?" else goal + "."
    parts += ["", "## " + t["stops"], "", "1. " + t["goal_stop"] % goal, "2. " + t["cap_stop"],
              "3. " + t["stuck_stop"] % stuck, ""]
    return "\n".join(parts)


def task_file_ask(answers, it):
    """The questions a terminal answers, only for what the arguments left out."""
    for key, ita, en, many in TASK_FILE_QUESTIONS:
        if answers.get(key):
            continue
        try:
            if many:
                answers[key] = list(iter(lambda: input((ita if it else en) + " ").strip(), ""))
            else:
                answers[key] = input((ita if it else en) + " ").strip()
        except EOFError:
            return


def cmd_task_file(args):
    """Improvement 1: write the task file of a job apart or in installments. With a terminal it asks what the arguments
    left out; with --no-ask, or with no terminal (claude -p cannot answer), it never asks."""
    cfg = q_settings.config()
    lang = args.lang or cfg.get("lang")
    it = lang == "it"
    answers = {"what": args.what, "why": args.why, "read": args.read, "example": args.example, "check": args.check,
               "goal": args.goal}
    if not args.no_ask and sys.stdin is not None and sys.stdin.isatty():
        task_file_ask(answers, it)
    if not (answers.get("what") or "").strip():
        sys.exit("quotient: serve almeno --what: cosa deve fare il lavoro" if it else
                 "quotient: --what is needed at least: what the job must do")
    if args.out and os.path.exists(args.out) and not args.force:
        sys.exit("quotient: %s c'e' gia': usa --force per sovrascriverlo" % args.out if it else
                 "quotient: %s exists already: use --force to overwrite it" % args.out)
    folder = os.path.abspath(args.dir)
    r = cfg["rate"]
    text = task_file_text(answers, folder, lang, int(r.get("task_file_lines") or 0), max(1, int(r.get("task_file_stuck") or 3)))
    if not args.out:
        q_settings.out(text)
        return
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(text)
    names = {"why": ("perche'", "why"), "read": ("file da leggere", "files to read"),
             "example": ("esempi di codice", "code examples"), "check": ("comandi di controllo", "commands to check"),
             "goal": ("quando e' finito", "when it is finished")}
    empty = [names[k][0 if it else 1] for k in ("why", "read", "example", "check", "goal") if not answers.get(k)]
    # what was named but is not on disk: the job would look for it, and a typo here costs it steps
    lost = [s for s in (answers.get("read") or []) + (answers.get("example") or [])
            if not os.path.exists(task_spot(s, folder)[1])]
    q_settings.out(("Compito scritto: %s (%d righe). Usalo con rate new o rate apart, --task-file.\n" if it else
         "Task written: %s (%d lines). Use it with rate new or rate apart, --task-file.\n") % (
             args.out, len(text.splitlines())))
    if empty:
        q_settings.out(("Senza risposta: %s. Il file dice al lavoro di arrangiarsi, e questo gli costa passi.\n" if it else
             "Not answered: %s. The file tells the job to manage without, which costs it steps.\n") % ", ".join(empty))
    if lost:
        q_settings.out(("Non trovati in %s: %s.\n" if it else "Not found in %s: %s.\n") % (folder, ", ".join(lost)))
