#!/usr/bin/env python3
"""Makes every picture of the README: the animated demo and the feature cards.

    python docs/make_images.py                  write docs/demo.svg and docs/feature-*.svg
    python docs/make_images.py --preview DIR    also take a PNG of each with Edge (Windows), to look at them
    python docs/make_images.py --preview DIR --at 3 9 15 21 29    which seconds of the demo to take

At a new version: change the numbers in the DATA part, run it, look at the PNGs. Standard library only.
Every number comes from real output of scripts/quotient.py, from the README or from the CHANGELOG: never make one up.
"""
import argparse
import math
import os
import shutil
import subprocess
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- DATA --------------------------------------------------------------------------------------------------------

# python scripts/quotient.py quote-table --raw essential=600000 good=1500000 max=2800000 --kind chat --type code --lang en
# (the shares and what is left depend on the moment and on this PC's factor: copy them all from one run)
QUOTE = [  # level, total, its size for the bar, expected time, share of the 5 hours, of the week
    ("Essential", "216,247", 216247, "about 5 min", "~0.8%", "~0.1%"),
    ("Good", "540,616", 540616, "about 12 min", "~2.1%", "~0.2%"),
    ("Max", "1.01 million", 1010000, "about 23 min", "~3.9%", "~0.3%"),
]
QUOTE_LEFT = {"5 hours": 66, "week": 49}   # what the Max level would leave, same output
PACES = ["All today", "Apart, now", "3 days", "5 days"]   # the pace options of that output
NIGHTS = {"days": 3, "a_day": "~507,465", "each": "about 4 min", "five": "~2.0%", "week": "~0.2%"}   # its 3-day option
APART = {"up_to": "1.31 million", "time": "about 13 min"}   # the same quote with --kind rate: the max level done apart

# One real job of the same size (raw estimate 2,800,000), the release of 1.2.3 on 30/10/2026:
# its line in ~/.quotient/jobs.jsonl and its job.json
JOB = {"cap": 1364792, "estimate": 994293, "actual": 768134, "work": 508450, "chat": 259684,
       "time": "12 min", "expected": "about 13 min"}

# The README
FACTORS = [("code", "x0.70"), ("writing", "x1.0"), ("research", "x0.35"), ("other", "x0.40")]   # measured on 64 clean jobs
LIMITS = [("5-hour", 69, "~22M of ~32M wt", "resets 19:30"), ("week", 94, "~270M of ~287M wt", "resets Mon 12 07:00")]
REREAD = {"total": 4.67, "work": 2.82, "chat": 1.85, "steps": 107, "start": "165,000", "step": "16,500"}

# ~/.quotient/average.json as downloaded on 30/10/2026 (updated 2026-10-21)
SHARED = {"date": "21 October 2026", "jobs": 65, "factor": 1.18, "p25": 0.52, "p75": 1.89}

# ---- LOOK --------------------------------------------------------------------------------------------------------

INK, MUTED, DIM, PANEL, LINE = "#f0f3f6", "#c3ccd6", "#8b96a3", "#1a202a", "#343c48"
GOLD, BLUE, VIOLET, GREEN, CORAL, TEAL, ORANGE, PINK, INDIGO = (
    "#e8b949", "#6cb6ff", "#c297ff", "#57d364", "#ff8e82", "#4dd0d6", "#f5a35c", "#f78cc6", "#9fa8ff")
SANS = '-apple-system,BlinkMacSystemFont,&quot;Segoe UI&quot;,Helvetica,Arial,sans-serif'
MONO = 'ui-monospace,SFMono-Regular,&quot;SF Mono&quot;,Menlo,Consolas,&quot;Liberation Mono&quot;,monospace'


def text(x, y, s, size=20, fill=INK, weight=None, anchor=None, mono=False, attrs=""):
    extra = ""
    if weight:
        extra += ' font-weight="%s"' % weight
    if anchor:
        extra += ' text-anchor="%s"' % anchor
    if mono:
        extra += ' font-family="%s"' % MONO
    return '<text x="%g" y="%g" font-size="%g" fill="%s"%s%s>%s</text>' % (x, y, size, fill, extra, attrs, escape(s))


def rect(x, y, w, h, fill, r=0, attrs=""):
    return '<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s"%s/>' % (x, y, w, h, r, fill, attrs)


def circle(x, y, r, fill, attrs=""):
    return '<circle cx="%g" cy="%g" r="%g" fill="%s"%s/>' % (x, y, r, fill, attrs)


def panel(x, y, w, h, color=None):
    edge = ' stroke="%s" stroke-opacity="0.75"' % color if color else ' stroke="%s"' % LINE
    return rect(x, y, w, h, PANEL, 14, edge)


def bar(x, y, w, h, share, color, back="#2b323d"):
    """A bar with its background. `share` from 0 to 1."""
    return rect(x, y, w, h, back, h / 2) + rect(x, y, max(h, w * share), h, color, h / 2)


def arrow(x1, y, x2, color):
    return ('<path d="M%g %g H%g M%g %g L%g %g L%g %g" stroke="%s" stroke-width="3" fill="none" stroke-linecap="round" '
            'stroke-linejoin="round"/>' % (x1, y, x2 - 2, x2 - 11, y - 8, x2 - 2, y, x2 - 11, y + 8, color))


def card(name, accent, title, sub, height, body, alt):
    """One card: its own dark background tinted with its colour, so it reads on GitHub's light and dark themes."""
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="900" height="%d" viewBox="0 0 900 %d" role="img" '
           'aria-label="%s" font-family="%s">' % (height, height, escape(alt, {'"': "&quot;"}), SANS))
    svg += ('<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="%s" stop-opacity="0.34"/>'
            '<stop offset="0.6" stop-color="%s" stop-opacity="0.08"/><stop offset="1" stop-color="%s" stop-opacity="0.2"/>'
            '</linearGradient></defs>' % (accent, accent, accent))
    svg += rect(0, 0, 900, height, "#0e1218", 24) + rect(0, 0, 900, height, "url(#bg)", 24)
    svg += rect(1, 1, 898, height - 2, "none", 23, ' stroke="%s" stroke-opacity="0.65" stroke-width="2"' % accent)
    svg += text(48, 68, title, 34, accent, 700) + text(48, 106, sub, 21, INK)
    svg += body + "</svg>\n"
    write("feature-%s.svg" % name, svg)
    return "feature-%s.svg" % name


def write(name, data):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(data)


# ---- THE CARDS ---------------------------------------------------------------------------------------------------

def card_levels():
    b, y, top = "", 136, QUOTE[-1][2]
    for i, (name, total, size, *_rest) in enumerate(QUOTE):
        on = name == "Good"
        b += panel(48, y, 804, 62, GOLD if on else None)
        b += circle(80, y + 31, 11, GOLD if on else "none", ' stroke="%s" stroke-width="2.5"' % (GOLD if on else DIM))
        b += text(106, y + 39, name, 24, GOLD if on else INK, 700 if on else None)
        b += bar(248, y + 23, 370, 16, size / top, GOLD if on else "#8e98a6")
        b += text(830, y + 39, total, 24, INK, 600, "end")
        y += 74
    b += text(48, y + 26, 'Or write your own: "the good one, plus the tests of the max".', 21, MUTED)
    return card("levels", GOLD, "Pick a level", "One to four levels, more for a bigger job. Claude waits for your choice.", y + 56, b,
                "A choice of three levels with their totals: essential 216,247, good 540,616, max 1.01 million weighted tokens.")


def card_time():
    level = QUOTE[-1]
    b = panel(48, 136, 256, 190, BLUE)
    b += text(176, 186, "Expected time", 20, MUTED, None, "middle")
    b += text(176, 248, level[3].replace("about ", "~"), 46, BLUE, 700, "middle")
    b += text(176, 288, "learned from your own jobs", 18, MUTED, None, "middle")
    for x, name, share, key in ((322, "5 hours", level[4], "5 hours"), (596, "Week", level[5], "week")):
        left = QUOTE_LEFT[key]
        b += panel(x, 136, 256, 190)
        b += text(x + 128, 186, name, 20, MUTED, None, "middle")
        b += text(x + 128, 248, share, 46, INK, 700, "middle")
        b += bar(x + 28, 268, 200, 12, left / 100.0, BLUE)
        b += text(x + 128, 310, "%d%% left after it" % left, 18, MUTED, None, "middle")
    b += text(48, 368, "This is the max level of a real quote. Every level shows the same three numbers.", 21, MUTED)
    return card("time", BLUE, "How long, and how much of your limits", "You see it before the work starts.", 400, b,
                "The max level of a quote: about 23 minutes, about 3.9 percent of the 5 hours with 66 percent left, about 0.3 percent of the week with 49 percent left.")


def card_installments():
    b, n = "", NIGHTS
    for i in range(n["days"]):
        x = 48 + i * 275
        b += panel(x, 136, 254, 112, VIOLET)
        b += circle(x + 42, 192, 19, GOLD) + circle(x + 51, 186, 16, PANEL)
        b += text(x + 80, 183, "Day %d" % (i + 1), 20, MUTED)
        b += text(x + 80, 218, "03:00", 32, INK, 700)
    x, steps = 48, (("PC wakes", 158), ("works to its cap", 214), ("saves", 112), ("PC sleeps", 158))
    for i, (word, w) in enumerate(steps):
        b += rect(x, 272, w, 52, VIOLET, 26, ' fill-opacity="0.2" stroke="%s"' % VIOLET)
        b += text(x + w / 2, 305, word, 21, INK, None, "middle")
        if i < 3:
            b += arrow(x + w + 8, 298, x + w + 44, VIOLET)
        x += w + 52
    b += text(48, 366, "%s a day, %s each: a %s plan from a real quote." % (n["a_day"], n["each"], "%d-day" % n["days"]), 21, MUTED)
    b += text(48, 398, "The last 8% of each cap is kept for saving what it found.", 21, MUTED)
    return card("installments", VIOLET, "Big jobs, a piece a night", "Each piece has its own cap, and the week's reserve stays yours.", 430, b,
                "Three days at 03:00. Each time the PC wakes, Claude works up to the cap, saves, and the PC goes back to sleep.")


def card_report():
    j = JOB
    x, w, top = 230, 600, float(j["cap"])
    b = ""
    b += text(48, 164, "Cap", 22, MUTED) + rect(x, 144, w, 28, "none", 8, ' stroke="%s" stroke-width="2" stroke-dasharray="7 6"' % DIM)
    b += text(x + w - 14, 165, "%.2fM" % (j["cap"] / 1e6), 20, MUTED, None, "end")
    b += text(48, 216, "Estimate", 22, MUTED) + rect(x, 196, w * j["estimate"] / top, 28, "#8e98a6", 8)
    b += text(x + w * j["estimate"] / top - 14, 217, "%dk of work" % round(j["estimate"] / 1e3), 20, "#0e1218", 600, "end")
    work, chat = w * j["work"] / top, w * j["chat"] / top
    b += text(48, 268, "Real cost", 22, INK, 700)
    b += rect(x, 248, work, 28, GREEN, 8) + rect(x + work - 8, 248, chat + 8, 28, TEAL, 8)
    b += text(x + work + chat + 14, 269, "%dk" % round(j["actual"] / 1e3), 22, INK, 700)
    b += circle(x + 8, 306, 8, GREEN) + text(x + 24, 313, "work %dk" % round(j["work"] / 1e3), 20, MUTED)
    b += circle(x + 188, 306, 8, TEAL) + text(x + 204, 313, "re-reading the chat %dk" % round(j["chat"] / 1e3), 20, MUTED)
    b += panel(48, 340, 804, 62, GREEN)
    b += text(76, 379, "Working time", 22, MUTED) + text(250, 379, j["time"], 26, GREEN, 700)
    b += text(824, 379, "%s expected" % j["expected"], 22, MUTED, None, "end")
    return card("report", GREEN, "The real cost after", "Measured from Claude Code's own records. One real job, 30 October 2026.", 434, b,
                "A real job: cap 1.36 million, estimate 994 thousand of work, real cost 768 thousand (work 508, re-reading 260), 12 minutes against about 13 expected.")


def card_factor():
    b = panel(48, 136, 804, 86, CORAL)
    b += text(82, 190, "1.50M", 34, INK, 700) + text(190, 190, "the model's estimate", 20, MUTED)
    b += text(430, 190, "x0.70", 34, CORAL, 700)
    b += arrow(538, 180, 590, CORAL)
    b += text(610, 190, "1.05M", 34, INK, 700) + text(716, 190, "corrected", 20, MUTED)
    for i, (kind, value) in enumerate(FACTORS):
        x = 48 + i * 204
        b += panel(x, 242, 192, 118)
        b += text(x + 96, 284, kind, 21, MUTED, None, "middle")
        b += text(x + 96, 334, value, 38, CORAL, 700, "middle")
    b += text(48, 400, "Where each type starts, measured on 64 clean jobs. Then it learns from yours.", 21, MUTED)
    return card("factor", CORAL, "It learns from your jobs", "Each quote is corrected by how far off the earlier ones were.", 432, b,
                "An estimate of 1.50 million times 0.70 gives 1.05 million. Starting factors by type of work: code 0.70, writing 1.0, research 0.35, other 0.40.")


def card_shared():
    s = SHARED
    b = panel(48, 136, 804, 136, TEAL)
    b += text(76, 186, "opus", 28, TEAL, 700) + text(76, 224, "%d jobs" % s["jobs"], 20, MUTED)
    x, w = 230, 590

    def at(v):   # a log scale from x0.25 to x4, the range Quotient accepts
        return x + w * (math.log(v) - math.log(0.25)) / (math.log(4) - math.log(0.25))
    b += rect(x, 196, w, 10, "#2b323d", 5)
    b += rect(at(s["p25"]), 196, at(s["p75"]) - at(s["p25"]), 10, TEAL, 5)
    b += circle(at(s["factor"]), 201, 12, INK)
    b += text(at(s["factor"]), 178, "x%.2f" % s["factor"], 26, INK, 700, "middle")
    b += text(at(s["p25"]), 240, "x%.2f" % s["p25"], 20, MUTED, None, "middle")
    b += text(at(s["p75"]), 240, "x%.2f" % s["p75"], 20, MUTED, None, "middle")
    for i, family in enumerate(("sonnet", "haiku", "fable", "other")):
        px = 48 + i * 204
        b += rect(px, 288, 192, 54, "none", 14, ' stroke="%s" stroke-dasharray="6 5"' % DIM)
        b += text(px + 96, 322, family, 21, MUTED, None, "middle")
    b += text(48, 382, "The other models have no average yet. Numbers as of %s." % s["date"], 21, MUTED)
    b += text(48, 414, "The band is the middle half of the jobs. Sharing is optional.", 21, MUTED)
    return card("shared", TEAL, "A start from other people's numbers", "Until your own numbers are enough, an average fills in, by model.", 446, b,
                "The shared average for Opus: 65 jobs, factor 1.18, middle half from 0.52 to 1.89. Sonnet, Haiku, Fable and other have no average yet.")


def card_limits():
    b, y = "", 136
    for name, left, tokens, resets in LIMITS:
        b += panel(48, y, 804, 104)
        b += text(76, y + 42, name, 26, INK, 700)
        b += text(226, y + 42, tokens, 22, MUTED)
        b += text(824, y + 42, "%d%% left" % left, 26, ORANGE, 700, "end")
        b += bar(76, y + 60, 748, 16, left / 100.0, ORANGE)
        y += 118
    b += text(48, y + 22, "Example numbers: yours depend on your plan, and they reset on their own.", 21, MUTED)
    b += text(48, y + 54, "If this week's pace would reach the limit before it resets, it tells you once.", 21, MUTED)
    return card("limits", ORANGE, "Your limits, always in view", "What is left of the 5 hours and of the week, at each message.", y + 84, b,
                "Two bars: the 5-hour limit with 69 percent left, about 22 million of 32 million weighted tokens; the week with 94 percent left, about 270 million of 287 million.")


def card_reread():
    r = REREAD
    x, w = 48, 804
    work = w * r["work"] / r["total"]
    b = rect(x, 142, work, 66, GREEN, 14) + rect(x + work - 14, 142, w - work + 14, 66, PINK, 14)
    b += text(x + 22, 186, "work %.2fM" % r["work"], 28, "#0e1218", 700)
    b += text(x + work + 22, 186, "re-reading %.2fM" % r["chat"], 28, "#0e1218", 700)
    b += panel(48, 230, 394, 110) + panel(458, 230, 394, 110)
    b += text(245, 276, "%s tokens" % r["start"], 30, INK, 700, "middle") + text(245, 314, "in the chat when the job started", 20, MUTED, None, "middle")
    b += text(655, 276, "%d steps" % r["steps"], 30, INK, 700, "middle") + text(655, 314, "and each one reads it all again", 20, MUTED, None, "middle")
    b += text(48, 380, "When a chat has grown long, the window offers a new chat and says what that saves.", 21, MUTED)
    return card("reread", PINK, "Why a long chat costs more", "A real job: %.2f million, and %.2f of it was only re-reading." % (r["total"], r["chat"]), 412, b,
                "A real job of 4.67 million weighted tokens: 2.82 million of work and 1.85 million re-reading the 165,000 tokens the chat started with, over 107 steps.")


def card_hermes():
    b = ""
    for y, name, note in ((142, "Claude Code", "the plugin"), (242, "Hermes Agent", "two hooks in its config")):
        b += panel(48, y, 340, 84, INDIGO)
        b += text(76, y + 38, name, 26, INK, 700) + text(76, y + 66, note, 19, MUTED)
        b += arrow(396, y + 42, 470, INDIGO)
    b += rect(482, 142, 370, 184, INDIGO, 18, ' fill-opacity="0.2" stroke="%s" stroke-width="2"' % INDIGO)
    b += text(667, 210, "The same limits", 30, INK, 700, "middle")
    b += text(667, 250, "5 hours and week", 22, MUTED, None, "middle")
    b += text(667, 286, "Quotient counts both", 22, INDIGO, 600, "middle")
    b += text(48, 368, "Quotes and job measures work inside Hermes too. Installments still run with", 21, MUTED)
    b += text(48, 398, "Claude Code. Quotient reads Hermes' counters only, never your messages.", 21, MUTED)
    return card("hermes", INDIGO, "Hermes Agent too", "With your Claude login, its chats spend the same limits.", 430, b,
                "Claude Code and Hermes Agent both spend the same 5-hour and weekly limits, and Quotient counts both.")


# ---- THE DEMO ----------------------------------------------------------------------------------------------------

DEMO_W, DEMO_H, TOTAL = 900, 600, 36.0   # keep 900x600: docs/index.html shows it at that size
SCENES = [("You ask", 0.0, 5.0), ("The quote", 5.0, 13.5), ("You choose", 13.5, 19.5), ("Inside its cap", 19.5, 26.0),
          ("The report", 26.0, 36.0)]
FADE = 0.4


class Demo:
    """One duration for everything and one @keyframes per element, so --at can freeze the film at any second."""

    def __init__(self):
        self.css, self.count = [], 0

    def keyframes(self, stops):
        self.count += 1
        name = "k%d" % self.count
        body = "".join("%.3f%%{%s}" % (100.0 * t / TOTAL, rule) for t, rule in stops)
        self.css.append("@keyframes %s{%s}#a%d{animation-name:%s}" % (name, body, self.count, name))
        return ' id="a%d" class="an"' % self.count

    def window(self, start, end):
        """Visible from start to end."""
        stops = [(0, "opacity:0"), (start, "opacity:0"), (start + FADE, "opacity:1"), (end - FADE, "opacity:1"),
                 (end, "opacity:0"), (TOTAL, "opacity:0")]
        if start == 0:
            stops = [(0, "opacity:1"), (end - FADE, "opacity:1"), (end, "opacity:0"), (TOTAL, "opacity:0")]
        return self.keyframes(stops)

    def appear(self, start, end):
        """Part of a scene: comes in at start and leaves with it at end."""
        return self.window(start, end)

    def grow(self, start, stop, end):
        """A bar that fills from the left."""
        return self.keyframes([(0, "transform:scaleX(0)"), (start, "transform:scaleX(0)"), (stop, "transform:scaleX(1)"),
                               (end, "transform:scaleX(1)"), (TOTAL, "transform:scaleX(1)")])


def demo_svg(freeze=None):
    d = Demo()
    size, cw = 22, 22 * 0.6
    body = ""

    def scene(index, inner, static_visible=False):
        title, start, end = SCENES[index]
        head = circle(58, 94, 18, GOLD) + text(58, 103, str(index + 1), 24, "#0e1218", 700, "middle", True)
        head += text(90, 104, title, 30, GOLD, 700, None, False)
        opacity = "" if static_visible else ' opacity="0"'
        return "<g%s%s>%s%s</g>" % (d.window(start, end), opacity, head, inner)

    # 1. You ask: the prompt is typed in, then the answer comes
    prompt = "> This is a big job: the next version."
    s1 = text(40, 190, prompt, size, INK, None, None, True, ' textLength="%g" lengthAdjust="spacing"' % (len(prompt) * cw))
    n = len(prompt)
    # the cover slides right in steps and uncovers the letters; a cursor rides on its edge
    slide = d.keyframes([(0, "transform:translateX(0);animation-timing-function:steps(%d,end)" % n),
                         (0.4, "transform:translateX(0);animation-timing-function:steps(%d,end)" % n),
                         (2.4, "transform:translateX(%gpx)" % (n * cw)), (TOTAL, "transform:translateX(%gpx)" % (n * cw))])
    fade = d.window(0, 2.8)
    s1 += '<g%s opacity="0"><g%s>%s%s</g></g>' % (fade, slide, rect(38, 168, n * cw + 40, 32, "#10151c"), rect(36, 170, 3, 26, GOLD))
    s1 += "<g%s>%s</g>" % (d.appear(2.8, 5.0), text(40, 256, "Claude does not start.", 26, INK, 600))
    s1 += "<g%s>%s</g>" % (d.appear(3.3, 5.0), text(40, 298, "First, the price.", 26, GOLD, 600))
    body += scene(0, s1, True)

    # 2. The quote
    cols = (("Level", 40, None), ("Total", 352, "end"), ("Time", 386, None), ("5 hours", 692, "end"), ("Week", 860, "end"))
    s2 = "".join(text(x, 168, word, 20, DIM, None, a, True) for word, x, a in cols)
    s2 += rect(40, 182, 820, 2, LINE)
    start, end = SCENES[1][1], SCENES[1][2]
    for i, (level, total, _size, when, five, week) in enumerate(QUOTE):
        y, on = 226 + i * 58, level == "Max"
        row = rect(30, y - 34, 840, 50, GOLD, 10, ' fill-opacity="0.16"') if on else ""
        row += text(40, y, level, size, GOLD if on else INK, 700 if on else None, None, True)
        row += text(352, y, total, size, INK, None, "end", True) + text(386, y, when, size, INK, None, None, True)
        row += text(692, y, five, size, INK, None, "end", True) + text(860, y, week, size, INK, None, "end", True)
        s2 += "<g%s>%s</g>" % (d.appear(start + 0.7 + i * 0.7, end), row)
    s2 += "<g%s>%s</g>" % (d.appear(start + 3.2, end), text(40, 430, "With max, you would still have:", 24, MUTED))
    for i, (key, left) in enumerate((("5 hours", QUOTE_LEFT["5 hours"]), ("week", QUOTE_LEFT["week"]))):
        y = 464 + i * 46
        fill = ('<g%s style="transform-box:fill-box;transform-origin:left">%s</g>' % (d.grow(start + 3.6, start + 4.6, end), rect(170, y, 560 * left / 100.0, 22, GOLD, 11)))
        row = text(40, y + 19, key, size, INK, None, None, True) + rect(170, y, 560, 22, "#2b323d", 11) + fill
        row += text(860, y + 19, "%d%%" % left, size, INK, 700, "end", True)
        s2 += "<g%s>%s</g>" % (d.appear(start + 3.4, end), row)
    body += scene(1, s2)

    # 3. You choose
    start, end = SCENES[2][1], SCENES[2][2]
    s3 = text(40, 168, "Level", 22, DIM)
    for i, level in enumerate(q[0] for q in QUOTE):
        x, on = 40 + i * 200, level == "Max"
        s3 += rect(x, 182, 184, 54, "#1a202a", 12, ' stroke="%s"' % LINE)
        s3 += text(x + 92, 217, level, size, DIM, None, "middle")
        if on:
            s3 += "<g%s>%s%s</g>" % (d.appear(start + 1.2, end), rect(x, 182, 184, 54, GOLD, 12), text(x + 92, 217, level, size, "#0e1218", 700, "middle"))
    s3 += text(40, 280, "Pace", 22, DIM)
    for i, pace in enumerate(PACES):
        x, on = 40 + i * 205, pace == "Apart, now"
        s3 += rect(x, 294, 190, 54, "#1a202a", 12, ' stroke="%s"' % LINE)
        s3 += text(x + 95, 329, pace, size, DIM, None, "middle")
        if on:
            s3 += "<g%s>%s%s</g>" % (d.appear(start + 2.4, end), rect(x, 294, 190, 54, GOLD, 12), text(x + 95, 329, pace, size, "#0e1218", 700, "middle"))
    s3 += "<g%s>%s%s</g>" % (d.appear(start + 3.2, end), text(40, 412, "It starts at once, in a separate session.", 24, INK),
                             text(40, 452, "Up to %s, %s." % (APART["up_to"], APART["time"]), 24, GOLD, 600))
    body += scene(2, s3)

    # 4. Inside its cap
    start, end = SCENES[3][1], SCENES[3][2]
    x, y, w = 40, 214, 820
    share = float(JOB["actual"]) / JOB["cap"]
    grow = d.grow(start + 0.8, start + 3.4, end)
    s4 = text(40, 180, "A real job of this size: its cap", 22, MUTED) + text(860, 180, "{:,}".format(JOB["cap"]), size, INK, None, "end", True)
    s4 += rect(x, y, w, 44, "#2b323d", 12, ' stroke="%s"' % DIM)
    s4 += '<g%s style="transform-box:fill-box;transform-origin:left">%s</g>' % (grow, rect(x, y, w * share, 44, GOLD, 12))
    s4 += "<g%s>%s</g>" % (d.appear(start + 3.4, end), text(x + w * share + 16, y + 31, "{:,} spent".format(JOB["actual"]), size, INK, 700, None, True))
    s4 += "<g%s>%s</g>" % (d.appear(start + 3.9, end), text(40, 330, "It works up to its cap and no further.", 26, INK, 600))
    s4 += "<g%s>%s</g>" % (d.appear(start + 4.3, end), text(40, 374, "The last 8% is kept for saving what it found.", 24, MUTED))
    body += scene(3, s4)

    # 5. The report
    start, end = SCENES[4][1], SCENES[4][2]
    rows = (("Estimate", "%dk of work" % round(JOB["estimate"] / 1e3), MUTED),
            ("Real cost", "{:,}".format(JOB["actual"]), GOLD),
            ("  work", "{:,}".format(JOB["work"]), INK),
            ("  chat part", "{:,}".format(JOB["chat"]), INK),
            ("Working time", "%s, %s expected" % (JOB["time"], JOB["expected"]), INK))
    s5 = ""
    for i, (label, value, color) in enumerate(rows):
        y = 176 + i * 52
        s5 += "<g%s>%s%s</g>" % (d.appear(start + 0.6 + i * 0.6, end), text(40, y, label, size, MUTED, None, None, True),
                                 text(320, y, value, size, color, 700 if color == GOLD else None, None, True))
    s5 += "<g%s>%s</g>" % (d.appear(start + 4.0, end), text(40, 470, "The next quote learns from the difference.", 26, GOLD, 600))
    s5 += "<g%s>%s</g>" % (d.appear(start + 4.4, end), text(40, 512, "A real job: the release of version 1.2.3.", 22, MUTED))
    body += scene(4, s5)

    # the five dots along the bottom say where the film is
    dots = ""
    for i, (_t, start, end) in enumerate(SCENES):
        cx = DEMO_W / 2 - 60 + i * 30
        dots += circle(cx, 570, 6, "#2b323d")
        dots += "<g%s%s>%s</g>" % (d.window(start, end), "" if i == 0 else ' opacity="0"', circle(cx, 570, 6, GOLD))

    css = ["text{white-space:pre}", ".an{animation-duration:%gs;animation-timing-function:linear;animation-iteration-count:infinite}" % TOTAL]
    css += d.css
    css.append("@media (prefers-reduced-motion:reduce){.an{animation:none!important}}")
    if freeze is not None:
        css.append(".an{animation-play-state:paused!important;animation-delay:-%gs!important}" % freeze)
    chrome = rect(0, 0, DEMO_W, DEMO_H, "#10151c", 18) + rect(0.5, 0.5, DEMO_W - 1, DEMO_H - 1, "none", 18, ' stroke="%s"' % LINE)
    chrome += '<path d="M0 44V18a18 18 0 0 1 18-18H%g a18 18 0 0 1 18 18V44Z" fill="#1a202a"/>' % (DEMO_W - 18)
    chrome += circle(26, 22, 7, "#ff5f57") + circle(50, 22, 7, "#febc2e") + circle(74, 22, 7, "#28c840")
    chrome += text(DEMO_W / 2, 30, "Token Quotient", 20, MUTED, None, "middle")
    desc = ("A film in five scenes. You ask for a big job. Quotient's quote shows three levels with total, time and share of "
            "the 5 hours and of the week. You choose max, apart now. A real job of that size stays inside its cap of 1.36 million. "
            "The report: real cost 768,134 against an estimate of 994k of work, 12 minutes against about 13 expected.")
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-labelledby="t d" '
            'font-family="%s" font-size="%d"><title id="t">Token Quotient: the quote, your choice, the cap, the report</title>'
            '<desc id="d">%s</desc><style>%s</style>%s%s%s</svg>\n' % (
                DEMO_W, DEMO_H, DEMO_W, DEMO_H, SANS, size, escape(desc), "\n".join(css), chrome, body, dots))


# ---- PREVIEW -----------------------------------------------------------------------------------------------------

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def shot(svg_path, png_path, width, height, profile):
    subprocess.run([EDGE, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--user-data-dir=" + profile,
                    "--screenshot=" + png_path, "--window-size=%d,%d" % (width, height), "file:///" + svg_path.replace(os.sep, "/")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)


def main():
    ap = argparse.ArgumentParser(description="Make the README's pictures.")
    ap.add_argument("--preview", help="a folder for PNGs of each picture, taken with Edge")
    ap.add_argument("--at", type=float, nargs="*", default=[2.0, 4.5, 11.0, 18.0, 25.0, 34.0], help="seconds of the demo to take")
    args = ap.parse_args()
    write("demo.svg", demo_svg())
    cards = [f() for f in (card_levels, card_time, card_installments, card_report, card_factor, card_shared, card_limits,
                           card_reread, card_hermes)]
    print("written: demo.svg, " + ", ".join(cards))
    if args.preview:
        out = os.path.abspath(args.preview)
        os.makedirs(out, exist_ok=True)
        profile = os.path.join(out, "edge-profile")
        for name in cards:
            with open(os.path.join(HERE, name), encoding="utf-8") as f:
                height = int(f.read().split('height="')[1].split('"')[0])
            shot(os.path.join(HERE, name), os.path.join(out, name[:-4] + ".png"), 900, height, profile)
        for t in args.at:
            frame = os.path.join(out, "demo-at-%g.svg" % t)
            with open(frame, "w", encoding="utf-8") as f:
                f.write(demo_svg(freeze=t))
            shot(frame, frame[:-4] + ".png", DEMO_W, DEMO_H, profile)
        shutil.rmtree(profile, ignore_errors=True)
        print("previews in " + out)


if __name__ == "__main__":
    main()
