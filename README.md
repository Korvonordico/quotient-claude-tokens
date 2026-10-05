# Quotient

*[Leggi in italiano](README.it.md)*

**Know what an AI job will cost before it starts.** A plugin for [Claude Code](https://code.claude.com).

Today an AI job works like a mechanic who fixes your car without telling you the price: you find out at the till. With a subscription the till is the usage limit, and a single big job can use up a whole week.

Quotient adds three steps. The name holds both halves: it starts like *quote*, the price you agree before a job, and in mathematics the quotient is the result of a division, like a big job divided into installments.

1. **Before a big job**, Claude stops and offers options with their estimated cost: *essential*, *good*, *max*. The estimates are **not guaranteed**: they get more precise with use.
2. **After the job**, Quotient reads the real cost from Claude Code's own records and puts it next to the estimate.
3. **It learns from its errors**: if past estimates were half the real cost, the next ones are doubled. The report shows how far off it was at the start and how far off it is now.

You choose the threshold: under it, no quote, the work just starts. For very big jobs the options grow (five instead of three) and include **installments**: the same job split into daily pieces, each with a spending cap, so the rest of your day stays free for other work.

## Install

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient
/plugin install quotient@quotient
```

Needs Python 3.8 or newer (standard library only) and `sh` (on Windows it comes with Git for Windows, which Claude Code already uses).

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

## Plan limits: used, left, and how much 1% holds

With a Pro or Max subscription Claude Code passes the status line the share used of the 5-hour and weekly limits, and when they reset. Quotient records these readings and shows them in the status line:

```
Quotient · 5-hour: 31% used, 69% left, resets 19:30 · week: 6% used, 94% left, resets Mon 12 07:00
```

To set it up: `python scripts/quotient.py setup-statusline` shows the setting to add, and `--write` adds it to `~/.claude/settings.json` (only if you have no status line yet). Where there is no status line, Claude can read the limits itself (in the Claude desktop app it has a tool for it) and write a `LIMITS:` line, which Quotient records the same way.

From the readings and the costs it measures, Quotient estimates **how many weighted tokens 1% of each limit holds**, so a quote can say "this level takes about 8% of your week, 86% would be left". Anthropic does not publish the limits in tokens: this is an estimate, with its margin (percentages are whole numbers in some sources, so each window adds up to one point of error), and use outside Quotient's sessions (for example chats on claude.ai) makes the limits look smaller than they are.

The report lists the weeks: the highest share of the weekly limit used in each, and the weighted tokens measured. Whether the weeks are getting lighter it says only after 4 complete weeks: fewer than that would be noise.

## Commands

```
/quotient:report          estimates against real costs, and the trend of the error
/quotient:rate <job>      set up a job in daily installments
```

From a terminal (`scripts/quotient.py`, or `sh scripts/run.sh`):

```
python scripts/quotient.py report
python scripts/quotient.py config                     # show the settings
python scripts/quotient.py config threshold 500000    # change one
python scripts/quotient.py config lang it             # report in Italian
python scripts/quotient.py export                     # only the numbers, to share
```

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
