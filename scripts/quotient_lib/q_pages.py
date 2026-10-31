"""The report as a page with charts, and the export of the numbers."""

import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone

from quotient_lib import q_learning, q_limits, q_notices, q_quotes, q_rates, q_reports, q_settings, q_sharing

# ---------------------------------------------------------------- report as a page with charts

PAGE_TEXT = {
    "en": {
        "title": "Quotient · report", "made": "Made %s by Quotient %s. Weighted tokens (wt): input + 1.25 x cache "
        "write (2 x for the 1-hour cache) + 0.1 x cache read + 5 x output, the ratios of the API prices.",
        "jobs": "Jobs measured", "factor": "Correction factor", "recent": "Typical miss, last 5",
        "weight": "Quotient's own weight", "chat": "Re-reading the chat", "week": "Week used",
        "of_measured": "of what was measured", "since": "since 0.9.5", "resets": "resets %s",
        "miss_title": "How far each estimate was from the real work",
        "miss_note": "1x = the estimate was right; 2x = the work cost twice the estimate; 0.5x = half. "
                     "Log scale, so x2 and /2 are the same distance from the line.",
        "with": "with the correction", "without": "without the correction", "right": "right",
        "cost_title": "Estimate and real cost, job by job",
        "estimate": "corrected estimate", "work": "work", "chatpart": "re-reading the chat",
        "weeks_title": "The weeks: share of the weekly limit used", "running": "in progress",
        "rate_title": "Jobs in installments", "done_pct": "%s done (the installments' own estimate)",
        "no_progress": "no PROGRESS line yet", "spent": "%s spent of %s", "left": "about %d installment(s) to go",
        "savings_title": "What the choices avoided (estimates)", "table": "All the numbers",
        "no_below": "No job was chosen below its maximum level yet.",
        "cols": ["#", "date", "level", "estimate", "corrected", "work", "+chat", "miss"],
        "none": "No finished jobs yet: a job is measured when a quote (QUOTE) is made and a level is chosen (CHOICE).",
        "no_weeks": "No weekly readings yet.", "note": "Estimates are not guaranteed: they get more precise with use.",
        "status": {"open": "open", "done": "finished", "paused": "paused", "stopped": "stopped"},
    },
    "it": {
        "title": "Quotient · resoconto", "made": "Fatto %s da Quotient %s. Token pesati: ingresso + 1,25 x scrittura "
        "in cache (2 x per la cache di un'ora) + 0,1 x lettura dalla cache + 5 x uscita, i rapporti dei prezzi dell'API.",
        "jobs": "Lavori misurati", "factor": "Fattore di correzione", "recent": "Errore tipico, ultimi 5",
        "weight": "Il peso di Quotient", "chat": "Rilettura della chat", "week": "Settimana usata",
        "of_measured": "di quello misurato", "since": "dalla 0.9.5", "resets": "si azzera %s",
        "miss_title": "Quanto ogni stima era lontana dal lavoro vero",
        "miss_note": "1x = stima giusta; 2x = il lavoro è costato il doppio della stima; 0,5x = la metà. "
                     "Scala logaritmica: x2 e /2 stanno alla stessa distanza dalla linea.",
        "with": "con la correzione", "without": "senza la correzione", "right": "giusta",
        "cost_title": "Stima e costo vero, lavoro per lavoro",
        "estimate": "stima corretta", "work": "lavoro", "chatpart": "rilettura della chat",
        "weeks_title": "Le settimane: parte del limite settimanale usata", "running": "in corso",
        "rate_title": "Lavori a rate", "done_pct": "fatto il %s (stima delle rate stesse)",
        "no_progress": "ancora nessuna riga PROGRESS", "spent": "spesi %s su %s", "left": "ne mancano circa %d",
        "savings_title": "Cosa hanno evitato le scelte (stime)", "table": "Tutti i numeri",
        "no_below": "Finora nessun lavoro è stato scelto sotto il livello massimo.",
        "cols": ["#", "data", "livello", "stima", "corretta", "lavoro", "+chat", "errore"],
        "none": "Ancora nessun lavoro finito: un lavoro si misura quando c'è un preventivo (QUOTE) e si sceglie un livello (CHOICE).",
        "no_weeks": "Ancora nessuna lettura della settimana.", "note": "Le stime non sono garantite: diventano più precise con l'uso.",
        "status": {"open": "aperto", "done": "finito", "paused": "in pausa", "stopped": "fermato"},
    },
}

PAGE_STYLE = """
:root{color-scheme:light;--surface:#fcfcfb;--panel:#f4f3f0;--ink:#0b0b0b;--ink2:#52514e;--grid:#e3e2de;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--ok:#0ca30c}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--surface:#1a1a19;--panel:#242422;--ink:#ffffff;
--ink2:#c3c2b7;--grid:#3a3a37;--s1:#3987e5;--s2:#d95926;--s3:#199e70}}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}main{max-width:960px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}.muted{color:var(--ink2);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}
.tile{background:var(--panel);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:24px;
font-variant-numeric:tabular-nums}.tile span{color:var(--ink2);font-size:13px}
svg{width:100%;height:auto;display:block}svg text{fill:var(--ink2);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--ink2);margin:4px 0}
.key{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.bar{background:var(--panel);border-radius:6px;height:12px;overflow:hidden}.bar i{display:block;height:100%;
background:var(--s1);border-radius:6px}.job{margin:10px 0}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 8px;border-bottom:1px solid var(--grid)}th:nth-child(-n+3),td:nth-child(-n+3){text-align:left}
.scroll{overflow-x:auto}#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);
padding:6px 9px;border-radius:6px;font-size:13px;display:none;max-width:280px;z-index:9}
[data-tip]{cursor:default}
"""

PAGE_SCRIPT = """
const tip=document.getElementById('tip');
document.addEventListener('mouseover',e=>{const t=e.target.closest('[data-tip]');if(!t){tip.style.display='none';return}
tip.textContent=t.getAttribute('data-tip');tip.style.display='block'});
document.addEventListener('mousemove',e=>{tip.style.left=Math.min(e.clientX+14,innerWidth-300)+'px';tip.style.top=(e.clientY+14)+'px'});
"""


def esc(text):
    import html as htmllib
    return htmllib.escape(str(text), quote=True)


def num(n, lang):
    """A number for the page: 1,2 milioni / 548.000 (it), 1.2 million / 548,000 (en)."""
    return q_rates.amount(n, lang).replace(" milioni", " mln").replace(" million", " mln")


def bar_path(x, y, w, base, r=4):
    """A bar whose data end (the top) is rounded and whose foot stays square on the baseline."""
    r = max(0.0, min(r, w / 2, base - y))
    return "M%.1f,%.1f V%.1f Q%.1f,%.1f %.1f,%.1f H%.1f Q%.1f,%.1f %.1f,%.1f V%.1f Z" % (
        x, base, y + r, x, y, x + r, y, x + w - r, x + w, y, x + w, y + r, base)


def miss_chart(rows, t, lang, offset=0):
    """Dots: the real work over the estimate, job by job, on a log scale with the 'right' line at 1x."""
    W, H, L, R, T, B = 720, 260, 44, 16, 14, 30
    pts = [(i, r["work"] / r["corrected"], r["work"] / r["job"]["raw_estimate"], r) for i, r in enumerate(rows)]
    lo = min([0.5] + [min(a, b) for _, a, b, _ in pts])
    hi = max([2.0] + [max(a, b) for _, a, b, _ in pts])
    lo, hi = 2 ** math.floor(math.log2(lo)), 2 ** math.ceil(math.log2(hi))

    def y(v):
        return T + (math.log2(hi) - math.log2(v)) / (math.log2(hi) - math.log2(lo)) * (H - T - B)

    def x(i):
        return L + (i + 0.5) * (W - L - R) / max(1, len(pts))
    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, esc(t["miss_title"]))]
    v = lo
    while v <= hi * 1.001:
        parts.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--grid)" stroke-width="%s"/>' % (
            L, W - R, y(v), y(v), "2" if abs(v - 1) < 1e-9 else "1"))
        label = ("%gx" % v).replace(".", "," if lang == "it" else ".")
        parts.append('<text x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (L - 6, y(v), label))
        v *= 2
    parts.append('<text x="%d" y="%.1f" dy="-5" text-anchor="end">%s</text>' % (W - R, y(1), esc(t["right"])))
    for i, corrected, raw, r in pts:
        j = r["job"]
        date = (j.get("finished") or "")[:10]
        for value, color, label in ((raw, "var(--s2)", t["without"]), (corrected, "var(--s1)", t["with"])):
            tipt = "%s · %s · %s: x%s" % (date, j.get("choice") or "", label, ("%.2f" % value).replace(".", "," if lang == "it" else "."))
            parts.append('<circle cx="%.1f" cy="%.1f" r="5" fill="%s" stroke="var(--surface)" stroke-width="2" '
                         'data-tip="%s"/>' % (x(i), y(value), color, esc(tipt)))
        if len(pts) <= 16 or i % max(1, len(pts) // 12) == 0:
            parts.append('<text x="%.1f" y="%d" text-anchor="middle">%d</text>' % (x(i), H - 10, offset + i + 1))
    parts.append("</svg>")
    return "".join(parts)


def cost_chart(rows, t, lang):
    """Pairs of bars, job by job: the corrected estimate, and the real cost (work, with the chat part on top)."""
    offset = max(0, len(rows) - 12)
    rows = rows[-12:]
    W, H, L, R, T, B = 720, 260, 64, 16, 14, 30
    top = max([1.0] + [max(r["corrected"], r["work"] + (r["chat"] or 0)) for r in rows])
    step = 10 ** math.floor(math.log10(top))
    top = math.ceil(top / step) * step

    def y(v):
        return T + (1 - v / top) * (H - T - B)
    slot = (W - L - R) / max(1, len(rows))
    bw = min(28.0, slot / 2 - 4)
    base = y(0)
    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, esc(t["cost_title"]))]
    for k in range(0, 5):
        v = top * k / 4
        parts.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--grid)"/>' % (L, W - R, y(v), y(v)))
        parts.append('<text x="%d" y="%.1f" text-anchor="end" dy="4">%s</text>' % (L - 6, y(v), esc(num(v, lang))))
    for i, r in enumerate(rows):
        j = r["job"]
        cx = L + slot * (i + 0.5)
        date = (j.get("finished") or "")[:10]
        x1 = cx - bw - 1
        parts.append('<path d="%s" fill="var(--s1)" data-tip="%s"/>' % (
            bar_path(x1, y(r["corrected"]), bw, base), esc("%s · %s: %s" % (date, t["estimate"], num(r["corrected"], lang)))))
        x2 = cx + 1
        chat = r["chat"] or 0
        work_top = y(r["work"])
        if chat:
            parts.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="var(--s2)" data-tip="%s"/>' % (
                x2, work_top, bw, max(0.0, base - work_top), esc("%s · %s: %s" % (date, t["work"], num(r["work"], lang)))))
            parts.append('<path d="%s" fill="var(--s3)" stroke="var(--surface)" stroke-width="2" data-tip="%s"/>' % (
                bar_path(x2, y(r["work"] + chat), bw, work_top), esc("%s · %s: %s" % (date, t["chatpart"], num(chat, lang)))))
        else:
            parts.append('<path d="%s" fill="var(--s2)" data-tip="%s"/>' % (
                bar_path(x2, work_top, bw, base), esc("%s · %s: %s" % (date, t["work"], num(r["work"], lang)))))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%d</text>' % (cx, H - 10, offset + i + 1))
    parts.append("</svg>")
    return "".join(parts)


def weeks_chart(rows, t, lang):
    W, H, L, R, T, B = 720, 220, 44, 16, 14, 30
    rows = rows[-8:]

    def y(v):
        return T + (1 - min(v, 100) / 100.0) * (H - T - B)
    slot = (W - L - R) / max(1, len(rows))
    bw = min(48.0, slot - 12)
    parts = ['<svg viewBox="0 0 %d %d" role="img" aria-label="%s">' % (W, H, esc(t["weeks_title"]))]
    for v in (0, 25, 50, 75, 100):
        parts.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="var(--grid)" stroke-width="%s"/>' % (
            L, W - R, y(v), y(v), "2" if v == 100 else "1"))
        parts.append('<text x="%d" y="%.1f" text-anchor="end" dy="4">%d%%</text>' % (L - 6, y(v), v))
    for i, r in enumerate(rows):
        cx = L + slot * (i + 0.5)
        label = q_limits.when(r["resets"], lang)
        short = " ".join(label.split(" ")[:2])
        tipt = "%s: %d%%%s · %s wt" % (label, round(r["used"]), "" if r["complete"] else " (%s)" % t["running"], num(r["wt"], lang))
        parts.append('<path d="%s" fill="var(--s1)" opacity="%s" data-tip="%s"/>' % (
            bar_path(cx - bw / 2, y(r["used"]), bw, y(0)), "1" if r["complete"] else "0.55", esc(tipt)))
        parts.append('<text x="%.1f" y="%d" text-anchor="middle">%s</text>' % (cx, H - 10, esc(short)))
    parts.append("</svg>")
    return "".join(parts)


def installment_jobs():
    base = os.path.join(q_settings.home(), "rate")
    jobs = []
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            job = q_settings.load_json(os.path.join(base, name, "job.json"), None)
            if job:
                jobs.append((job, q_settings.read_jsonl(os.path.join(base, name, "runs.jsonl"))))
    return jobs


def report_html(cfg):
    """The report as a page with charts, written in Quotient's own folder (never on the Desktop) and opened."""
    lang = "it" if cfg.get("lang") == "it" else "en"
    t = PAGE_TEXT[lang]
    learned = q_learning.learning(cfg)
    rows = learned["rows"]
    s = q_reports.weight_summary()
    saved = q_reports.savings(learned["jobs"])
    week = q_limits.latest_limits().get("seven_day")
    tiles = [
        (str(len(rows)), t["jobs"]),
        (("x%.2f" % learned["factor"]).replace(".", "," if lang == "it" else "."), t["factor"]),
        (q_quotes.fmt_miss(q_learning.median([r["miss_corrected"] for r in rows[-5:]])).replace(".", "," if lang == "it" else ".")
         if rows else "-", t["recent"]),
        (q_reports.share_of(s["weight"], s["total"], lang), "%s, %s %s" % (t["weight"], t["of_measured"], t["since"])),
        (q_reports.share_of(s["chat"], s["total"], lang), "%s, %s" % (t["chat"], t["since"])),
    ]
    if week:
        tiles.append(("%d%%" % round(week["used"]), "%s, %s" % (t["week"], t["resets"] % q_limits.when(week["resets"], lang))))
    body = ['<main><h1>%s</h1><p class="muted">%s</p><div class="tiles">' % (
        esc(t["title"]), esc(t["made"] % (datetime.now().strftime("%d/%m/%Y %H:%M"), q_settings.VERSION)))]
    body += ['<div class="tile"><b>%s</b><span>%s</span></div>' % (esc(a), esc(b)) for a, b in tiles]
    body.append("</div>")
    if rows:
        body.append('<h2>%s</h2><div class="legend"><span><i class="key" style="background:var(--s1)"></i>%s</span>'
                    '<span><i class="key" style="background:var(--s2)"></i>%s</span></div>%s<p class="muted">%s</p>' % (
                        esc(t["miss_title"]), esc(t["with"]), esc(t["without"]), miss_chart(rows[-30:], t, lang, max(0, len(rows) - 30)), esc(t["miss_note"])))
        body.append('<h2>%s</h2><div class="legend"><span><i class="key" style="background:var(--s1)"></i>%s</span>'
                    '<span><i class="key" style="background:var(--s2)"></i>%s</span><span><i class="key" '
                    'style="background:var(--s3)"></i>%s</span></div>%s' % (
                        esc(t["cost_title"]), esc(t["estimate"]), esc(t["work"]), esc(t["chatpart"]), cost_chart(rows, t, lang)))
    else:
        body.append("<p>%s</p>" % esc(t["none"]))
    wk = q_limits.weeks()
    body.append("<h2>%s</h2>%s" % (esc(t["weeks_title"]), weeks_chart(wk, t, lang) if wk else "<p>%s</p>" % esc(t["no_weeks"])))
    jobs = installment_jobs()
    if jobs:
        body.append("<h2>%s</h2>" % esc(t["rate_title"]))
        for job, runs in jobs:
            spent = sum(r.get("wt") or 0 for r in runs)
            expected = (job.get("quote") or 0) * (job.get("factor_at_quote") or 1.0)
            left = q_notices.remaining(job, runs)
            done = 100.0 if job.get("status") == "done" else (left[0] if left else None)
            what = [t["status"].get(job.get("status"), job.get("status") or ""),
                    t["spent"] % (num(spent, lang), num(expected, lang)) if expected else num(spent, lang)]
            what.append(t["done_pct"] % q_rates.percent(done, lang) if done is not None else t["no_progress"])
            if left and left[0] < 100 and job.get("status") == "open":
                what.append(t["left"] % left[2])
            body.append('<div class="job"><b>%s</b> <span class="muted">%s</span><div class="bar" data-tip="%s">'
                        '<i style="width:%.0f%%"></i></div></div>' % (
                            esc(job.get("name")), esc(" · ".join(what)), esc(" · ".join(what)), done or 0))
    body.append("<h2>%s</h2><ul>" % esc(t["savings_title"]))
    texts = q_reports.TEXT[lang]
    if saved["below"]:
        body.append("<li>%s</li>" % esc(texts["below"] % (saved["below"], q_rates.amount(saved["below_wt"], lang))))
    else:
        body.append("<li>%s</li>" % esc(t["no_below"]))
    if saved["moved"]:
        body.append("<li>%s</li>" % esc(texts["moved"] % (saved["moved"], q_rates.amount(saved["moved_wt"], lang))))
    if s["turns"]:
        body.append("<li>%s</li>" % esc(texts["weight"] % (q_rates.amount(s["text"], lang), s["actions"], q_rates.amount(s["actions_wt"], lang),
                                                            q_rates.amount(s["weight"], lang), q_reports.share_of(s["weight"], s["total"], lang),
                                                            q_rates.amount(s["total"], lang))))
        body.append("<li>%s</li>" % esc(texts["unquoted"] % (s["unquoted"], q_rates.amount(s["unquoted_wt"], lang))))
    body.append("</ul>")
    if rows:
        body.append('<h2>%s</h2><div class="scroll"><table><tr>%s</tr>' % (
            esc(t["table"]), "".join("<th>%s</th>" % esc(c) for c in t["cols"])))
        for i, r in enumerate(rows, start=1):
            j = r["job"]
            cells = [str(i), (j.get("finished") or "")[:10], j.get("choice") or "", q_rates.amount(j["raw_estimate"], lang),
                     q_rates.amount(r["corrected"], lang), q_rates.amount(r["work"], lang), q_rates.amount(j["chat"], lang) if j.get("chat") else "-",
                     q_quotes.fmt_miss(r["miss_corrected"]).replace(".", "," if lang == "it" else ".")]
            body.append("<tr>%s</tr>" % "".join("<td>%s</td>" % esc(c) for c in cells))
        body.append("</table></div>")
    body.append('<p class="muted">%s</p></main><div id="tip"></div>' % esc(t["note"]))
    page = ('<!doctype html><html lang="%s"><head><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>%s</title><style>%s</style></head><body>%s'
            '<script>%s</script></body></html>' % (lang, esc(t["title"]), PAGE_STYLE, "".join(body), PAGE_SCRIPT))
    path = os.path.join(q_settings.home(), "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    return path


def open_file(path):
    """Open a page in the default browser; never an error if it cannot."""
    try:
        if os.name == "nt":
            os.startfile(path)  # noqa: the default browser for .html
        elif sys.platform == "darwin":
            subprocess.run(["open", path], capture_output=True)
        else:
            subprocess.run(["xdg-open", path], capture_output=True)
    except Exception:
        pass


def export():
    """The exact line sharing sends for each finished job: numbers only, no date, no text, no ids."""
    cfg = q_settings.config()
    per_point = q_sharing.learned_per_point(cfg)
    for j in q_learning.finished_jobs():
        row = q_sharing.share_row(j, cfg, per_point)
        if row:
            q_settings.out(json.dumps(row, separators=(",", ":")) + "\n")
