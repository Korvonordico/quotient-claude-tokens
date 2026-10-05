# Quotient: token cost quotes and usage limits for Claude Code

*[Leggi in italiano](README.it.md)*

**Know what an AI job will cost before it starts, and never lose a week to the usage limit again.** A plugin for [Claude Code](https://code.claude.com).

Today an AI job works like a mechanic who fixes your car without telling you the price: you find out at the till. With a subscription the till is the usage limit, and a single big job can use up a whole week. Quotient gives you the price first, lets you choose, measures what it really cost, and learns from the difference.

The name holds both halves: it starts like *quote*, the price agreed before a job, and in mathematics the quotient is the result of a division, like a big job divided into installments.

## What it can do

- **A quote before a big job**, in a choice window: *essential*, *good* or *max*, each with what it includes and its estimated cost.
- **The pace is yours**: all today, or in installments, one a day, with the amount per day. Or any pace you write yourself.
- **The real cost after**, read from Claude Code's own records, next to the estimate.
- **It learns from its errors**: each quote is corrected by how far off the earlier ones were.
- **Installments that work while you are away**: the PC wakes up, does the day's piece, and goes back to sleep (see below).
- **The week as a whole**: several jobs together never eat the share of the week you keep for yourself.
- **Your limits at a glance**: how much of the 5-hour and weekly limits you have used, and what is left.
- **Private**: everything stays on your computer. Quotient never connects to the internet.

## Install

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install quotient@quotient
```

Needs Python 3.8 or newer and `sh` (on Windows it comes with Git for Windows, which Claude Code already uses).

The first time, a window asks for four settings: from what size a job gets a quote, how much of the week to keep for yourself, the language, and what the PC does after an installment. You can change them later with `/quotient:setup`.

## How a big job goes

1. You ask for something big, or you say "this is a big job".
2. Claude does not start. A window opens with two questions:
   - **Level**: essential, good or max, with the estimate for each. For a job of about 500,000 tokens: max 500,000, good 250,000, essential 100,000.
   - **Pace**: all today, or for example "2 days, about 250,000 a day" or "5 days, about 100,000 a day". In the free field you can write your own, such as "50,000 a day".
3. If you choose **all today**, Claude does the job, and Quotient measures what it really cost.
4. If you choose **installments**, a second window asks when the first one starts and at what time the next ones run.

Estimates are not guaranteed: at the start they can be quite far off. They get closer with each finished job.

## Installments: the PC works while you are away

You leave the PC **in sleep or hibernation**, as you always do. Every installment then goes like this:

1. **At the time you chose** (for example 03:00), Windows wakes the PC.
2. **Quotient starts Claude Code** in the background, without opening the app. Claude reads the job and a short note of where it stopped last time.
3. **Claude works on the next piece** until it reaches that day's amount. Then it writes down where it stopped, and stops cleanly.
4. **If nobody is using the PC** (no keyboard or mouse for 10 minutes), Quotient **puts it back to sleep**, or into hibernation if you chose that. If you are using it, it stays on.
5. **The next day, at the same time, it starts again**, until the job is finished. Then the schedule removes itself.

Good to know:
- A timer can wake a PC that is **asleep or hibernated, not one that is shut down**. If the PC was off, the installment runs as soon as you turn it on.
- Windows must allow wake timers. `rate check` tells you whether it does, and how to turn them on.
- If you use the Claude desktop app, log in Claude Code once in a terminal (`claude auth login`): installments run outside the app.
- You can start one more installment the same day, if you accept that it uses more of that day's limit.
- Waking and sleeping work on Windows. On macOS and Linux Quotient gives you the line to schedule it yourself.

## The week: all jobs together

Two or three jobs can each fit in the week and still not fit together. Quotient adds up every planned installment until the weekly limit resets and keeps a reserve for your normal use (20% unless you change it). If the plan does not fit, a window asks which jobs to keep, slow down or pause. An installment never eats into the reserve: it gets smaller, or waits.

## Your limits

Quotient records how much of the 5-hour and weekly limits you have used and when they reset, and can show it in Claude Code's status line:

```
Quotient · 5-hour: 31% used, 69% left, resets 19:30 · week: 6% used, 94% left, resets Mon 12 07:00
```

Over time it also estimates how many tokens 1% of each limit holds, so a quote can say "this takes about 8% of your week". Anthropic does not publish the limits in tokens, so this is an estimate, with its margin.

## Commands

In the chat:

| Command | What it does |
|---|---|
| `/quotient:setup` | set Quotient up, or change its settings |
| `/quotient:report` | estimates against real costs, your limits, the weeks |
| `/quotient:rate <job>` | split a big job into installments |
| `/quotient:help` | every command, with what it does |

Claude runs the other commands for you when you choose in the windows. `/quotient:help` lists them all (`rate week`, `rate pause`, `rate check` and the others).

## Limits, said plainly

- The first estimates will be rough. A 2026 study asked AI models to predict their own cost before coding tasks: eight models, correlation with the real cost at most 0.39, and systematically too low ([Bai et al., arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient does not make the model better at guessing: it measures the miss and corrects the next guess.
- It relies on Claude following the rules Quotient gives it. If a quote is skipped, that job is not measured.
- Anthropic could add something similar to Claude Code. That would be fine.

<details>
<summary>Technical details</summary>

**The unit.** Costs are in weighted tokens: input-token equivalents at the ratios of Anthropic's API prices (input 1, cache write 1.25 for 5 minutes or 2 for 1 hour, cache read 0.1, output 5). In a live test, the dollar cost Claude Code reported was exactly the weighted tokens times the model's input price.

**How it hooks in.** At the start of a session Quotient gives Claude its rules once (about 650 tokens); at each message, one short line (about 70 tokens). Claude writes machine lines (`QUOTE:`, `CHOICE:`, `PACE:`, `JOB: CONTINUES`) that Quotient reads at the end of each reply, adding up the cost of that reply with each API call counted once.

**Installments.** Each one is a non-interactive run (`claude -p`) in the job's folder, started by Windows Task Scheduler through a small launcher in `~/.quotient`, so it keeps working after plugin updates. A hook refuses every tool except the handoff update once the day's cap is spent. Two installments of the same job never run at the same time.

**Your data.** Everything is in `~/.quotient/` (or `QUOTIENT_HOME`). `export` prints only numbers (no text, no paths, no session ids), for a future shared estimate built from many people's numbers.

**Tests.** `python -m unittest discover -s tests`

</details>

## Author

Francesco Candela (Korvonordico). The idea, the threshold, the learning from errors, the installments and the weekly budget are his; the code was written with Claude.

## License

MIT
