# How accurate are the quotes: 50 measured jobs

Quotient asks the model to estimate a job before it starts, then measures what the job really cost. This page sets the
two side by side for 50 jobs done on purpose, in fresh sessions, by a new user: 9 on 16 October 2026 (Quotient 1.1.7)
and 41 on the evening of 17 October 2026 (Quotient 1.1.8, with its new settings on). Every number is in
[results.json](results.json), with the exact text of each task.

## In short

- **The model's quotes are mostly too high**, not too low: across the 40 jobs of 17 October with a machine-readable
  quote, the measured work was on average 0.58 times the raw quote (geometric mean; from 0.31 to 1.16).
- **It depends on the type of work.** New code: x0.86 (11 jobs, 0.58 to 1.16), close. Fixing bugs in a given module:
  x0.55 (5). Web research: x0.39 (11, plus x0.41 on 16 October): the model quotes research about 2.5 times too high,
  every time. Texts: x0.60 (13), with the rule for texts on.
- **Texts were the big miss, and the rule for texts fixed the direction.** Without it (16 October) texts cost 3.3 to
  5.1 times their quote. With it, the model counted about 47 weighted tokens per final word, and texts cost 23 to 49 per
  word (28 on average): now the quote is about 1.7 times too high. Over all 16 texts the cost per word averaged about 32.
- **The same job done again** cost within ±10% in 13 of 21 pairs and within ±25% in 17; the median change was 5%, the
  largest 49% (a summary of a given topic: 79,057 then 40,325). The model's own quote for the same task changed in 12
  of the 21 pairs (for example 150,000 then 250,000).
- **A quote in a new session costs about 65,000 weighted tokens**, mostly the start of the session: the one-line quote
  for a small job (64,600 on average, 34 jobs) saves only about 8,000 against the full table (72,200, 6 jobs). A quote
  for an addition, in a chat already open, cost 17,000 to 21,500.
- **The correction factor of a new user** (x1.15, from the shared average at that date) moved every type the wrong way
  here, since the quotes were already high: x0.51 instead of x0.58 overall.

## Method

Each job ran in a new Claude Code session (2.1.x, `claude -p`), as a new user:

- the plugin loaded from this repository (`--plugin-dir`), `--setting-sources project` (no user settings, plugins or
  hooks), empty temporary `QUOTIENT_HOME` and `HERMES_HOME`, `QUOTIENT_SHARE=0`, and the environment cleaned of
  `QUOTIENT_*`, `HERMES_*`, `CLAUDE_CODE_*` (except the Git Bash path), `CLAUDECODE`, `CLAUDE_PID`, `CLAUDE_EFFORT`;
- model Claude Opus 5.5, `--output-format json`, `--permission-mode bypassPermissions` (only inside the temporary
  folder of the job), `--max-turns 150`; at most 3 sessions at a time;
- on 17 October the new 1.1.8 settings were on in the test `QUOTIENT_HOME`: `writing_wt_per_word` 50,
  `note_web_haiku` 1, `small_quote_line` 1, `margin_percent` 15, `requote_on_addition` 1.

The user's turns were fixed texts, in Italian, written before any session started and never changed (they are in
results.json):

1. the task, then "Before you start, give me the quote."
2. (resuming the session) "I choose the biggest level, all today. Do the job exactly as I described it, with no
   additions, and at the end write JOB: CLOSE."
3. for the 3 jobs with an addition: "Add also: ..." (one more request, also written beforehand). If that reply had no
   quote and had not done the addition, a fourth turn asked "Quote the addition again." Then: "I choose the biggest
   level, all today. Do the addition exactly as I described it, nothing else, and at the end write JOB: CLOSE."

The 17 October jobs: 4 programs (a library manager with SQLite and 40+ tests, a file converter, a small web server with
tests, a math library with 50+ tests), 3 modules with 6 bugs each planted on purpose (each bug alone fails at least one
test, the correct version passes them all), 5 texts from 600 to 6,000 words (article, short story, guide in chapters,
long formal letter, summary of a given topic), 4 web checks of 8 to 12 true and false claims with links and levels, 3
jobs with an addition halfway (code, text, research), and 3 jobs done twice (code, text, research). Then all 19 tasks
were done a second time, identical (runs marked `r`).

**Units.** Weighted tokens: input 1, cache write 1.25 (5 minutes) or 2 (1 hour), cache read 0.1, output 5, the ratios
of the API prices. **Measured work** is the real cost minus the chat part (re-reading, at each call, what the chat
held before the job started): it is what Quotient sets against the raw quote and learns its factor from. The real cost
plus the quote is the whole session, and it matches, to the token, the sum worked out again from the session's log.

**Checking the results.** Every job was checked: the tests run and pass (and the given test file is untouched in the
bug fixes), the words of each text are counted, each research report has its links (22 to 34 different links) and a
level per claim. All 50 passed these checks.

## All the jobs

`+` rows are the additions, measured as jobs of their own (with their own quote). F1 is worked out from the turns
Quotient recorded (the model wrote no choice line, so Quotient did not open the job; fixed since, see below). F3 has no
machine-readable quote (the model quoted by hand, "40-60k", without the quote command): it is left out of the ratios.

| Job | Date | Type | What | Raw quote | Measured work | Real cost | Chat part | Quote cost | Work / raw | Result |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 | 2026-10-16 | code | small program (to-do list, 8+ tests) | 40,000 | 30,133 | 51,798 | 21,665 | 70,500 | x0.75 | 10 tests, all pass |
| L2 | 2026-10-16 | code | medium program (expenses, SQLite, 20+ tests) | 80,000 | 74,312 | 104,980 | 30,668 | 71,775 | x0.93 | 34 tests, all pass |
| L2b | 2026-10-16 | code | medium program (expenses, SQLite, 20+ tests) | 70,000 | 81,981 | 111,264 | 29,283 | 70,212 | x1.17 | 32 tests, all pass |
| L3 | 2026-10-16 | code | fix a module (6 bugs, 32 tests) | 60,000 | 32,190 | 48,710 | 16,520 | 73,689 | x0.54 | 32 tests, all pass, tests untouched |
| L3b | 2026-10-16 | code | fix a module (6 bugs, 32 tests) | 60,000 | 29,263 | 45,244 | 15,981 | 72,402 | x0.49 | 32 tests, all pass, tests untouched |
| L4 | 2026-10-16 | writing | article, ~800 words | 15,000 | 49,571 | 86,722 | 37,151 | 66,862 | x3.30 | 881 words |
| L5 | 2026-10-16 | writing | guide, ~5,000 words, 6 chapters | 50,000 | 257,043 | 304,341 | 47,298 | 70,522 | x5.14 | 5073 words |
| L5b | 2026-10-16 | writing | guide, ~5,000 words, 6 chapters | 60,000 | 242,325 | 271,570 | 29,245 | 69,588 | x4.04 | 4944 words |
| L6 | 2026-10-16 | research | research: check 8 claims on the web | 200,000 | 81,921 | 115,933 | 34,012 | 70,460 | x0.41 | 22 links |
| C1 | 2026-10-17 | code | library manager, SQLite, 40+ tests | 150,000 | 168,718 | 203,480 | 34,762 | 65,247 | x1.12 | 67 tests, all pass |
| T3 | 2026-10-17 | writing | guide, ~6,000 words, 8 chapters | 300,000 | 190,141 | 230,849 | 40,708 | 74,028 | x0.63 | 6323 words |
| R1 | 2026-10-17 | research | research: 10 claims (science, health) | 200,000 | 98,352 | 124,691 | 26,339 | 64,550 | x0.49 | 26 links |
| F1 | 2026-10-17 | code | fix a module (6 bugs, 35 tests), from the turns | 60,000 | 28,270 | 42,809 | 14,539 | 63,956 | x0.47 | 35 tests, all pass, tests untouched |
| A1 | 2026-10-17 | code | contacts CLI (15 tests), then add vCard (8 tests) | 120,000 | 69,509 | 88,769 | 19,260 | 65,092 | x0.58 | 37 tests, all pass |
| A1+ | 2026-10-17 | code | the addition | 70,000 | 56,384 | 87,881 | 31,497 | 21,041 | x0.81 | |
| T1 | 2026-10-17 | writing | article, ~600 words | 30,000 | 18,309 | 32,812 | 14,503 | 64,280 | x0.61 | 694 words |
| C2 | 2026-10-17 | code | file converter CLI, 25+ tests | 120,000 | 102,763 | 134,825 | 32,062 | 66,000 | x0.86 | 38 tests, all pass |
| R2 | 2026-10-17 | research | research: 8 claims (history) | 200,000 | 64,238 | 82,984 | 18,746 | 64,853 | x0.32 | 24 links |
| F2 | 2026-10-17 | code | fix a module (6 bugs, 29 tests) | 40,000 | 25,615 | 44,359 | 18,744 | 64,035 | x0.64 | 29 tests, all pass, tests untouched |
| A2 | 2026-10-17 | writing | article ~1,000 words, then add FAQ and summary | 50,000 | 49,512 | 72,295 | 22,783 | 63,328 | x0.99 | 1402 words + summary 200 words |
| A2+ | 2026-10-17 | writing | the addition | 30,000 | 26,945 | 55,530 | 28,585 | 17,250 | x0.90 | |
| T2 | 2026-10-17 | writing | short story, ~2,000 words | 100,000 | 49,778 | 68,416 | 18,638 | 63,591 | x0.50 | 1875 words |
| C3 | 2026-10-17 | code | small web server (notes API), 20+ tests | 120,000 | 137,188 | 203,344 | 66,156 | 65,400 | x1.14 | 31 tests, all pass |
| R3 | 2026-10-17 | research | research: 12 claims (geography, nature) | 240,000 | 75,243 | 104,958 | 29,715 | 70,456 | x0.31 | 29 links |
| F3 | 2026-10-17 | code | fix a module (6 bugs, 25 tests), quoted by hand | - | 8,833 | 21,561 | 12,728 | 59,062 | - | 25 tests, all pass, tests untouched |
| A3 | 2026-10-17 | research | research: 6 claims, then add 4 | 180,000 | 57,641 | 84,896 | 27,255 | 64,424 | x0.32 | 26 links |
| A3+ | 2026-10-17 | research | the addition | 65,000 | 31,794 | 52,989 | 21,195 | 21,467 | x0.49 | |
| T4 | 2026-10-17 | writing | formal letter, ~1,200 words | 60,000 | 34,847 | 53,775 | 18,928 | 64,402 | x0.58 | 1230 words |
| C4 | 2026-10-17 | code | math library (stats, matrices), 50+ tests | 150,000 | 135,887 | 163,337 | 27,450 | 65,017 | x0.91 | 84 tests, all pass |
| R4 | 2026-10-17 | research | research: 10 claims (technology) | 150,000 | 93,262 | 120,653 | 27,391 | 65,599 | x0.62 | 25 links |
| T5 | 2026-10-17 | writing | summary of a given topic, ~1,500 words | 75,000 | 79,057 | 114,686 | 35,629 | 63,864 | x1.05 | 1632 words |
| C2b | 2026-10-17 | code | file converter CLI, 25+ tests | 150,000 | 112,764 | 140,291 | 27,527 | 65,216 | x0.75 | 46 tests, all pass |
| T4b | 2026-10-17 | writing | formal letter, ~1,200 words | 60,000 | 33,682 | 52,379 | 18,697 | 64,266 | x0.56 | 1275 words |
| R2b | 2026-10-17 | research | research: 8 claims (history) | 200,000 | 63,909 | 82,804 | 18,895 | 65,058 | x0.32 | 23 links |
| C1r | 2026-10-17 | code | library manager, SQLite, 40+ tests | 250,000 | 196,807 | 248,569 | 51,762 | 70,397 | x0.79 | 71 tests, all pass |
| T3r | 2026-10-17 | writing | guide, ~6,000 words, 8 chapters | 330,000 | 143,207 | 174,557 | 31,350 | 74,032 | x0.43 | 6122 words |
| R1r | 2026-10-17 | research | research: 10 claims (science, health) | 250,000 | 93,611 | 124,687 | 31,076 | 72,746 | x0.37 | 28 links |
| F1r | 2026-10-17 | code | fix a module (6 bugs, 35 tests) | 60,000 | 28,034 | 42,614 | 14,580 | 64,411 | x0.47 | 35 tests, all pass, tests untouched |
| A1r | 2026-10-17 | code | contacts CLI (15 tests), then add vCard (8 tests) | 80,000 | 68,936 | 92,035 | 23,099 | 64,259 | x0.86 | 39 tests, all pass |
| A1r+ | 2026-10-17 | code | the addition | 50,000 | 46,439 | 65,833 | 19,394 | 20,027 | x0.93 | |
| T1r | 2026-10-17 | writing | article, ~600 words | 30,000 | 18,342 | 37,000 | 18,658 | 63,606 | x0.61 | 683 words |
| C2r | 2026-10-17 | code | file converter CLI, 25+ tests | 130,000 | 100,927 | 124,201 | 23,274 | 65,029 | x0.78 | 43 tests, all pass |
| R2r | 2026-10-17 | research | research: 8 claims (history) | 200,000 | 68,328 | 87,178 | 18,850 | 64,984 | x0.34 | 23 links |
| F2r | 2026-10-17 | code | fix a module (6 bugs, 29 tests) | 50,000 | 26,476 | 45,228 | 18,752 | 63,897 | x0.53 | 29 tests, all pass, tests untouched |
| A2r | 2026-10-17 | writing | article ~1,000 words, then add FAQ and summary | 50,000 | 28,587 | 47,126 | 18,539 | 63,247 | x0.57 | 1580 words + summary 180 words |
| A2r+ | 2026-10-17 | writing | the addition | 30,000 | 15,801 | 32,882 | 17,081 | 16,862 | x0.53 | |
| T2r | 2026-10-17 | writing | short story, ~2,000 words | 100,000 | 44,643 | 63,344 | 18,701 | 63,742 | x0.45 | 1982 words |
| C3r | 2026-10-17 | code | small web server (notes API), 20+ tests | 120,000 | 88,782 | 120,563 | 31,781 | 65,317 | x0.74 | 33 tests, all pass |
| R3r | 2026-10-17 | research | research: 12 claims (geography, nature) | 200,000 | 99,684 | 131,171 | 31,487 | 64,549 | x0.50 | 34 links |
| F3r | 2026-10-17 | code | fix a module (6 bugs, 25 tests) | 40,000 | 26,393 | 40,931 | 14,538 | 68,261 | x0.66 | 25 tests, all pass, tests untouched |
| A3r | 2026-10-17 | research | research: 6 claims, then add 4 | 110,000 | 58,367 | 81,370 | 23,003 | 64,320 | x0.53 | 24 links |
| A3r+ | 2026-10-17 | research | the addition | 70,000 | 31,958 | 53,247 | 21,289 | 20,755 | x0.46 | |
| T4r | 2026-10-17 | writing | formal letter, ~1,200 words | 60,000 | 34,911 | 58,181 | 23,270 | 64,507 | x0.58 | 1201 words |
| C4r | 2026-10-17 | code | math library (stats, matrices), 50+ tests | 120,000 | 139,362 | 166,681 | 27,319 | 64,648 | x1.16 | 85 tests, all pass |
| R4r | 2026-10-17 | research | research: 10 claims (technology) | 250,000 | 82,196 | 107,918 | 25,722 | 71,540 | x0.33 | 30 links |
| T5r | 2026-10-17 | writing | summary of a given topic, ~1,500 words | 80,000 | 40,325 | 59,025 | 18,700 | 63,691 | x0.50 | 1770 words |

## What the numbers say

**Measured work / raw quote** (geometric mean, range, and the geometric spread):

| Group | 16 October (1.1.7) | 17 October (1.1.8 settings on) |
|---|---|---|
| all | x1.22 (9 jobs) | x0.58 (40 jobs, 0.31 to 1.16, spread x1.45) |
| new code | x0.93 (L1, L2, L2b) | x0.86 (11, 0.58 to 1.16) |
| bug fixes | x0.51 (L3, L3b) | x0.55 (5, 0.47 to 0.66) |
| texts | x4.09 (3, no rule) | x0.60 (13, 0.43 to 1.05, rule on) |
| research | x0.41 (1) | x0.39 (11, 0.31 to 0.62) |
| additions (as jobs of their own) | none | x0.66 (6, 0.46 to 0.93) |

1. **Code: the raw quote holds for new programs** (x0.86, within ±30% in 10 of 11), and is about twice too high for
   fixing a given module (x0.55): the model expects to search more than it needs to.
2. **Research: quoted 2.5 times too high, steadily** (12 jobs over the two days, x0.31 to x0.62). The work came to
   about 6,300 to 9,800 weighted tokens per claim checked (with two links each), about 8,500 on average. On top of it,
   Claude Code's web searches also run a small model (haiku) that is not in the session's log, so it is not in these
   numbers (about 12% of one session at list prices, measured on 16 October).
3. **Texts: the cost per final word is the right unit, and it varies.** 23 to 56 weighted tokens per word over 16
   texts (about 32 on average). On 16 October the texts cost 49 to 56 per word; on 17 October mostly 23 to 30, with
   two at 48 and 49. With 50 per word, 9 of the 13 texts of 17 October fell within the rule's margin of 25 to 55 and
   4 just under it (23). So 50 now quotes texts about 1.7 times too high; something nearer 30 to 35 per word would
   have matched both days better. The same summary of a given topic cost 79,057 and then 40,325: for texts, the same
   job can vary by twice.
4. **The same job done again** (21 pairs): within ±10% in 13, within ±15% in 15, within ±25% in 17; median change 5%.
   The four changes beyond 25% are two texts (x0.51 and x0.58), a web server (x0.65) and a research (x1.33). Saying a miss under
   15% is "within the margin" (`margin_percent`) fits most jobs, not all.
5. **Additions.** All 6 additions got a quote of their own without being asked (`requote_on_addition` on), in an open
   chat, for 17,000 to 21,500 weighted tokens. Each addition cost 54% to 81% of the first job's work. Their quotes were
   also high (x0.66 raw), but nearer once corrected with the factor learned from the first job of the same session
   (x0.58 to x0.99).
6. **The quote itself** cost about 65,000 weighted tokens in every new session, 38.6% of all the spending of these
   tests (2.81 million of 7.28 million). Most of it is the start of the session, so a one-line quote saves little
   there; in a chat already open (the additions) a quote cost a third as much.
7. **Two times in 41 Quotient did not record the job as quoted.** Once the model answered the one-line quote with the
   work and `JOB: CLOSE` but no `CHOICE` line; since 1.1.8 the work done chooses the quote's one level (it then
   worked twice in the second round). Once the model quoted by hand, without the quote command or the `QUOTE` line: the
   protocol was not followed, and no code can fix that afterwards.

## What the numbers do not say

- **These are small, fresh jobs.** The measured work goes from about 16,000 to 257,043 weighted tokens, done in one go, with
  no questions halfway. Real jobs are often 10 to 100 times bigger, in long chats, with helpers and installments; there
  the chat part and the quote weigh differently.
- **Additions written in advance are not real additions.** Real ones change the job as it goes; here each was a clean
  extra request. The test of the author's own 51 jobs found that jobs with signs of additions cost x1.82 their raw quote
  against x1.20 for the others: that effect is not measured here.
- **One model, one machine, one user's account, two evenings.** Claude Opus 5.5 in Claude Code only; Hermes was not
  tested. The plan limits rose with these tests and with other use at the same time.
- **Non-interactive sessions.** With `claude -p` there is no choice window: the model asked in text and the turns were
  scripted. The first-use questions of a new user were left for later (`small_quote_line`) or asked in text.
- **The tasks were written by the person who measured them**, in Italian, and some of their answers (the research
  claims) are well known: models may know them without searching.
- **The rule for texts was on while the texts were quoted on 17 October**, so those quotes test the rule, not the model
  alone; the 16 October texts show the model without it.
- **The geometric means hide the spread**: a single job can be 2 times off in either direction even when the mean is
  close.

## Files

- [results.json](results.json): every job of both days, with the task text (Italian), the user's turns, the quote's
  options, the factor used, the measured work, the real cost, the chat part, the cost of the quote, the time, the calls
  and the checks of the result; and the summaries above.
- The settings these tests led to are in the [README](../../README.md) (`writing_wt_per_word`, `note_web_haiku`,
  `small_quote_line`, `margin_percent`, `requote_on_addition`) and in the [CHANGELOG](../../CHANGELOG.md).
