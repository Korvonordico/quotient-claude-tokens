# Quotient: token cost quotes and usage limits for Claude Code

*[Leggi in italiano](README.it.md)*

**Know what an AI job will cost before it starts, and never lose a week to the usage limit again.** A plugin for [Claude Code](https://code.claude.com).

Today an AI job works like a mechanic who fixes your car without telling you the price: you find out at the till. With a subscription the till is the usage limit, and a single big job can use up a whole week. Quotient gives you the price first, lets you choose, measures what it really cost, and learns from the difference.

The name holds both halves: it starts like *quote*, the price you agree before a job, and in mathematics the quotient is the result of a division, like a big job divided into installments.

## What it can do

- **A quote before a big job.** When a job will likely cost more than your threshold, or whenever you say it is a big job, Claude stops and opens a choice window: *essential*, *good* or *max*, each with what it includes and its estimated cost, sized to the job. Estimates are not guaranteed: they get more precise with use.
- **The pace, chosen by you.** In the same window: all today, or in installments, written in days and amount per day ("5 days, about 100,000 a day"). The free field takes any pace you like.
- **The real cost after.** Quotient reads Claude Code's own records and adds up what the job really cost, each API call counted once, in weighted tokens (input-token equivalents at the API price ratios).
- **It learns from its errors.** The ratio between real cost and estimate becomes a correction factor for the next quotes; the report shows how far off it was at the start and how far off it is now.
- **Installments that run while you are away.** A big job is split into pieces: one installment a day (or more, if you choose), each with a spending cap and a handoff file that says what is done and where to resume. On Windows an installment wakes the PC from sleep or hibernation, works, and puts it back to sleep if nobody is using it. When the cap is reached it stops cleanly instead of being cut off, and two installments of the same job never run together. You can start an extra one the same day, at your own risk.
- **The week as a whole.** Two or three jobs can each fit in the week and still not fit together. Quotient adds up every planned installment until the weekly limit resets, keeps a reserve for your normal use, and when the plan does not fit it asks which jobs to keep, slow down or pause. An installment never eats into the reserve: it gets smaller, or waits.
- **Your limits at a glance.** It records the share used of the 5-hour and weekly limits and when they reset, shows what is left in the status line, and estimates how many tokens 1% of each limit holds, so a quote can say "this takes about 8% of your week".
- **Set up once.** The first use opens a window for four settings: threshold, weekly reserve, language, what the PC does after installments. `/quotient:setup` changes them, `/quotient:help` lists every command.
- **Private.** Everything stays on your computer. Quotient never connects to the internet; `export` gives only numbers, to share if you want.

## Install

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install quotient@quotient
```

Needs Python 3.8 or newer (standard library only) and `sh` (on Windows it comes with Git for Windows, which Claude Code already uses).

## First use

The first time, Quotient asks for four settings in a choice window: the threshold (from how many weighted tokens a job gets a quote), the share of the week kept free for normal use, the language of the report, and what the PC does after scheduled installments. Claude Code's own plugin settings show the same four. To change them later: `/quotient:setup`.

## How it works

- **At the start of a session** (`SessionStart` hook), Quotient gives Claude the quote rules once: about 650 tokens. **At each message** (`UserPromptSubmit` hook) only one short line: the threshold, the correction factor, the size of the conversation, and news about your installments. About 70 tokens.
- **When it steps in:** when a job will likely cost more than the threshold, and whenever you say it's a big job or ask for a quote.
- **A choice window opens** (Claude Code's own question window) with two questions:
  - **Level**: *essential*, *good*, *max*, sized to the job. For a 500k job: max 500k, good 250k, essential 100k.
  - **Pace**: all today, or installments that fit the job, for example 250k a day for 2 days, or 100k a day for 5 days.
  - The window always has a free field: write your own pace there, for example "50k a day".
- Claude writes a machine line with its raw estimates, `QUOTE: essential=100k good=250k max=500k`, and after your answer `CHOICE: good` and `PACE: today` (or `PACE: daily=100k`). If a job takes more than one reply, each unfinished reply ends with `JOB: CONTINUES`, and the cost of the following replies is added.
- **At the end of each reply** (`Stop` hook), Quotient reads the conversation file and adds up the cost of that reply. Each API call is counted **once**: the file repeats a call once per content block, and counting every line would double the result.

### The unit: weighted tokens

The cost is in **weighted tokens (wt)**: input-token equivalents at the ratios of Anthropic's API prices.

| Part of the call | Weight |
|---|---|
| input | 1 |
| cache write, 5 minutes | 1.25 |
| cache write, 1 hour | 2 |
| cache read | 0.1 |
| output | 5 |

The share of your subscription limit is not in Claude Code's files, so Quotient does not claim to know it. Weighted tokens move together with it, and you can compare one job with another.

One thing the numbers show quickly: every model call re-reads the whole conversation. In a 400,000-token conversation that is about 40,000 wt per call before Claude writes a word. Long conversations cost more than they look.

## The week: all installment jobs together

Each job on its own can fit in the week while two or three together do not. Quotient adds up the installments of all open jobs until the weekly limit resets and compares them with what is left, minus a **reserve for normal use** (20% by default, `config week.reserve_percent 25` to change it).

```
python scripts/quotient.py rate week              # every open job, the total, and whether it fits
python scripts/quotient.py rate pause book        # the job's scheduled runs skip it
python scripts/quotient.py rate resume book
python scripts/quotient.py rate set book --daily 150000   # slow it down: smaller installments
```

- When the jobs no longer fit, the next time you write a choice window asks which jobs to keep, slow down or pause. It asks once for each new situation.
- Before a new job is created, Claude checks the week, and if it would not fit it says so in the window.
- An installment never plans into the reserve: if the week is short it runs smaller, and if almost nothing is left it waits.

The share of the week needs the estimate of how much 1% holds (see below): until Quotient has a few days of readings, the plan is shown in weighted tokens only.

## The PC works while you are away

On Windows, a scheduled installment **wakes the PC from sleep or hibernation**, works, and if you chose so **puts it back to sleep**, but only if nobody has used the keyboard or mouse in the last 10 minutes: if you are using the PC, it stays on. While an installment works, Windows is kept from going back to sleep halfway. If the PC was off at the scheduled time, the installment runs as soon as it is back on.

```
python scripts/quotient.py rate check                  # can this PC be woken by a timer?
python scripts/quotient.py rate after book sleep       # after each installment: sleep | hibernate | nothing
```

Limits: a timer can wake a PC from sleep or hibernation, not from a full shutdown. Windows must allow wake timers (Power Options > Sleep > Allow wake timers); `rate check` reads the setting and says how to turn it on, but Quotient never changes it for you. Scheduled tasks call a small launcher in `~/.quotient`, so they keep working after the plugin updates. Two installments of the same job never run at the same time.

## Plan limits: used, left, and how much 1% holds

With a Pro or Max subscription Claude Code passes the status line the share used of the 5-hour and weekly limits, and when they reset. Quotient records these readings and shows them in the status line:

```
Quotient · 5-hour: 31% used, 69% left, resets 19:30 · week: 6% used, 94% left, resets Mon 12 07:00
```

To set it up: `python scripts/quotient.py setup-statusline` shows the setting to add, and `--write` adds it to `~/.claude/settings.json` (only if you have no status line yet). Where there is no status line, Claude can read the limits itself (in the Claude desktop app it has a tool for it) and write a `LIMITS:` line, which Quotient records the same way.

From the readings and the costs it measures, Quotient estimates **how many weighted tokens 1% of each limit holds**, so a quote can say "this level takes about 8% of your week, 86% would be left". Anthropic does not publish the limits in tokens: this is an estimate, with its margin (percentages are whole numbers in some sources, so each window adds up to one point of error), and use outside Quotient's sessions (for example chats on claude.ai) makes the limits look smaller than they are.

The report lists the weeks: the highest share of the weekly limit used in each, and the weighted tokens measured. Whether the weeks are getting lighter it says only after 4 complete weeks: fewer than that would be noise.

## Commands

In the chat:

| Command | What it does |
|---|---|
| `/quotient:setup` | set Quotient up, or change its four settings |
| `/quotient:report` | estimates against real costs, plan limits, the weeks |
| `/quotient:rate <job>` | split a big job into installments, with the choice window |
| `/quotient:help` | this list |

From a terminal, with `python scripts/quotient.py <command>` (or `sh scripts/run.sh <command>`):

| Command | What it does |
|---|---|
| `report` | the report, from a terminal |
| `setup --threshold N --reserve N --lang it\|en --after sleep\|hibernate\|nothing` | save the four settings |
| `config [key [value]]` | show every setting, or change one |
| `export` | only the numbers of finished jobs, to share |
| `setup-statusline [--write]` | show the plan limits in the status line |
| `rate new <job> --dir <folder> --task-file <file> --quote N (--days N \| --daily N)` | create a job in installments |
| `rate run <job> [--force]` | run one installment now (--force: even if one already ran today) |
| `rate once <job> --time HH:MM` | one installment at that time (tomorrow if it has passed); wakes the PC |
| `rate schedule <job> --time HH:MM [--force]` | one installment every day at that time; wakes the PC |
| `rate after <job> sleep\|hibernate\|nothing` | what the PC does after each installment, if nobody uses it |
| `rate week` | all open jobs against what is left of the week |
| `rate set <job> --daily N --per-day N --days N` | change a job: size of each installment, how many a day, how many in all |
| `rate pause <job> / rate resume <job>` | pause a job, or start it again |
| `rate stop <job>` | stop a job and remove its scheduled runs |
| `rate status [job]` | installments done and weighted tokens spent |
| `rate check` | can a scheduled installment wake this PC, and is Claude Code logged in |

## Installments

A job too big for one day can run in pieces:

```
python scripts/quotient.py rate new book --dir ~/book --task-file job.md --quote 500000 --daily 100000   # 5 installments
python scripts/quotient.py rate run book                     # one installment now
python scripts/quotient.py rate schedule book --time 03:00   # one every day
python scripts/quotient.py rate status
```

After you choose installments, a second window asks when the first one starts (now, today at a time you write, or tonight) and at what time the next ones run every day. When an installment ends, the next time you write a window asks what to do: start the next one now (it spends more of today's limit, at your own risk), at a time you choose today, or at the usual time. Every choice has a free field: the plan is yours.

```
python scripts/quotient.py rate once book --time 15:30       # one more installment today
python scripts/quotient.py rate run book --force              # one more installment now
python scripts/quotient.py rate stop book                     # stop the job and its schedule
```

Each installment is a fresh, non-interactive Claude Code run (`claude -p`) in the job's folder. It reads the job description and a handoff file (what is done, what remains, where to resume), works, and updates the handoff after each step. When the day's cap is spent, a hook refuses every tool except the handoff update, so the run stops cleanly instead of being cut off. After the first run Quotient also learns the dollar value Claude Code reports per weighted token and adds `--max-budget-usd` as a hard stop.

A fresh run with a short handoff re-reads much less than a long conversation, so installments may cost **less in total**, not only less per day. That is a guess: the report will show it.

Limits: the job has to be divisible (a novel by chapters, yes; a review that must see the whole text at once, less). Installments run with `--permission-mode acceptEdits` by default and cannot answer permission prompts: commands they need must be allowed in your settings. On Windows `rate schedule` creates a Task Scheduler task; on macOS and Linux it prints the `crontab` line to add.

## Your data

Everything stays in `~/.quotient/` (or `QUOTIENT_HOME`): your settings, the quotes, the measured costs. Quotient never sends anything anywhere. `export` prints only numbers (date, number of options, chosen level, estimate, real cost, turns): no text, no paths, no session ids.

## Shared learning (not active yet)

With one person's data the correction factor needs a few jobs before it means much (about five, a guess to check with use). Pooled numbers from many people would help newcomers start from everyone's average. The plan: people who want to send the output of `export` to this repository, and the plugin offers the pooled factor as a starting point. Until people send numbers, there is nothing to pool.

## Limits, said plainly

- The first estimates will be rough. A 2026 study asked AI models to predict their own cost before coding tasks: eight models, correlation with the real cost at most 0.39, and systematically too low ([Bai et al., arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient does not make the model better at guessing; it measures the miss and corrects the next guess.
- The correction is a single factor: the median ratio between real cost and estimate over the last 20 jobs. If your jobs are very different from each other, the miss stays large.
- It relies on Claude writing the `QUOTE:` and `CHOICE:` lines. If it forgets, that job is not measured.
- Anthropic could add something similar to Claude Code. That would be fine.

## Tests

```
python -m unittest discover -s tests
```

## Author

Francesco Candela (Korvonordico). The idea, the threshold, the learning from errors and the installments are his; the code was written with Claude.

## License

MIT
