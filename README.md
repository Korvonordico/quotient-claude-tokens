# Quotient: token cost quotes and usage limits for Claude Code

*[Leggi in italiano](README.it.md)*

**Know what an AI job will cost before it starts, and never lose a week to the usage limit again.** A plugin for [Claude Code](https://code.claude.com).

Today an AI job works like a mechanic who fixes your car without telling you the price: you find out at the till. With a subscription the till is the usage limit, and a single big job can use up a whole week. Quotient gives you the price first, lets you choose, measures what it really cost, and learns from the difference.

The name holds both halves: it starts like *quote*, the price agreed before a job, and in mathematics the quotient is the result of a division, like a big job divided into installments.

## What it can do

- **A quote before a big job**, in a choice window: *essential*, *good* or *max*, each with what it includes and its estimated cost.
- **The pace is yours**: all today, or in installments, one a day, with the amount per day. Or any pace you write yourself.
- **The real cost after**, read from Claude Code's own records, next to the estimate.
- **The work apart from re-reading the chat**: at every step Claude re-reads everything the chat holds. Quotient measures that apart, so the estimate is about the work and the window shows work + re-reading = total. In a long chat it says how much a new chat would save, and the job can be done there (see [Work and re-reading](#work-and-re-reading-why-a-long-chat-costs-more)).
- **A job can move between chats**: chosen in one chat and done in a new one, or left open in one and finished in another, it is still measured as one job.
- **It learns from its errors**: each quote is corrected by how far off the earlier ones were. You do not start from zero: until you have 5 jobs of your own, it starts from the shared average of everyone's real jobs (numbers only, see below).
- **Installments that work while you are away**: the PC wakes up, does the day's piece, and goes back to sleep. When you come back, a notification and the report in the job's chat tell you what it did (see below).
- **The week as a whole**: several jobs together never eat the share of the week you keep for yourself.
- **Your limits at a glance**: how much of the 5-hour and weekly limits you have used, and what is left. If this week's pace would reach the limit before it resets, Quotient says so once, with how much a day would last.
- **Its own weight, measured**: the text Quotient adds to a chat and the actions it asks for are counted, so you can see what it costs next to what it helps.
- **A page with charts**: `/quotient:report page` opens the report in your browser (a local file, nothing loaded from the internet).
- **Ready-made ways of working** for long installment jobs: a book, a research, a code review (`rate templates`).
- **Private**: everything stays on your computer, except one line of numbers per finished job for the shared average, which you can turn off (see [What is shared](#what-is-shared)).

## Install

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install quotient@quotient
```

Needs Python 3.8 or newer and `sh` (on Windows it comes with Git for Windows, which Claude Code already uses).

The first time, a window asks for four settings: from what size a job gets a quote, how much of the week to keep for yourself, the language, and whether Quotient may wake the PC for installments and put it back to sleep. You can change them later with `/quotient:setup`. Then a second window asks whether you want to take part in the shared average, which helps the program (yes, no, or anything else you write).

## How a big job goes

1. You ask for something big, or you say "this is a big job".
2. Claude does not start. A window opens with two questions:
   - **Level**: essential, good or max, with the estimate for each. For a job of about 500,000 tokens: max 500,000, good 250,000, essential 100,000.
   - **Pace**: all today, or for example "2 days, about 250,000 a day" or "5 days, about 100,000 a day". In the free field you can write your own, such as "50,000 a day".
3. If you choose **all today**, Claude does the job, and Quotient measures what it really cost.
4. If you choose **installments**, a second window asks when the first one starts and at what time the next ones run.

Estimates are not guaranteed: at the start they can be quite far off. They get closer with each finished job.

If a reply costs more than the threshold and had no quote, Quotient tells you once, in one line, and counts it in the report.

## Work and re-reading: why a long chat costs more

At every step (every call to the model) Claude re-reads everything the chat holds: the system, the tools, your rules, the conversation so far. Each re-read token costs little (a tenth of a new one, thanks to the cache), but it adds up. In a chat that starts with 165,000 tokens, every step costs about 16,500 weighted tokens before any work is done; a job of 100 steps, about 1.65 million. A model estimating a job thinks of the work, not of this.

So Quotient splits every job it measures in two:

- **work**: the steps of the job itself. The estimate is about this, and the correction is learned from it.
- **re-reading**: what the chat already held when the job started, read again at every step. Quotient measures it, and in a quote adds it from the size of the chat now and the steps the work will take.

A real case, 6 October 2026: a job cost 4.67 million weighted tokens, of which 2.82 million work and 1.85 million re-reading the 165,000 tokens the chat started with, over 107 steps.

When a chat has grown long, the window also offers to do the job **in a new chat**, and says how much that saves. You open a new chat and ask to continue: Quotient tells the new chat that a job is waiting, and measures it there.

## Installments: the PC works while you are away

You leave the PC **in sleep or hibernation**, as you always do. Every installment then goes like this:

1. **At the time you chose** (for example 03:00), Windows wakes the PC.
2. **Quotient starts Claude Code** in the background, without opening the app. Claude reads the job and a short note of where it stopped last time.
3. **Claude works on the next piece** until it reaches that day's amount. Then it writes down where it stopped, and stops cleanly.
4. **If nobody is using the PC** (no keyboard or mouse for 10 minutes), Quotient **puts it back to sleep**, or into hibernation if you chose that. If you are using it, it stays on.
5. **The next day, at the same time, it starts again**, until the job is finished. Then the schedule removes itself.

**When you come back, you see it at once.** For each installment Windows shows a notification, which stays in the notification center. The full report waits in the chat where you created the job and appears at your first message there: which installment, when, what it cost against the day's amount and the week, what it did, what is left and when the next one starts. Other chats tell you only once, and a second time no sooner than a day later; then they stop. To get the reports in another chat, ask Claude there (`rate here <job>`).

Good to know:
- If you prefer that Quotient never touches the PC, choose so in the setup: installments then run only when the PC is already on.
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

## What is shared

Each copy of Quotient learns from its own errors, but a new user has no errors yet. So the copies pool their numbers: after each finished job, Quotient sends **one line of numbers, exactly this and nothing else**:

```json
{"v":1,"q":"0.9.5","family":"opus","estimate":225000,"actual":259000}
```

The format, the Quotient version, the model family (opus, sonnet, haiku, fable or other), the raw estimate and the real cost of the work in weighted tokens (from 0.9.5 without the re-reading of the chat, which the estimate is not about), rounded to 3 significant digits. **No dates, no names, no text, no paths, no session or user ids.** The line leaves at the start of your next session, never in the middle of a reply, and nothing is queued before Claude Code has shown you a message about it.

- A small service ([code in `server/`](server/)) collects the lines. It does not keep IP addresses: its code never reads them and request logs are off.
- At most once a week, after at least 20 new jobs and never below 30 jobs in all, it publishes the average in its own repository, [quotient-data](https://github.com/Korvonordico/quotient-data) (the service's key can write only there, never in this code). Every copy of Quotient downloads that file once a day and uses it only between x0.25 and x4: anyone can send numbers, so it is a best-effort average.
- **You choose**: the first-use window asks whether you take part (yes by default). You can change it any time: `/quotient:share off`, the plugin setting *Share anonymous numbers*, or `QUOTIENT_SHARE=0`. **With sharing off you still get the shared average.**
- `/quotient:share` shows exactly what is sent and how many lines are waiting.

Everything in detail: [PRIVACY.md](PRIVACY.md).

## What Quotient runs, sends and fetches

Everything, so nothing is a surprise:

- **On your computer, always**: its Python script, through `sh`, at the start of each session, at each message, at the end of each reply, and before each tool call inside an installment. It reads Claude Code's transcripts of your chats only for numbers: the token counts of each call, the machine lines Claude writes, and which tools Claude called (to measure the cost and Quotient's own weight). No text from them is ever sent anywhere.
- **It writes** only in `~/.quotient/` (or `QUOTIENT_HOME`). The one exception is `setup-statusline --write`, which puts the status line in `~/.claude/settings.json`, and only when you run it.
- **For installments, only after you choose them in the window**: Windows Task Scheduler tasks (`schtasks`) that run at the time you chose and, if you allow it, wake the PC; Claude Code itself (`claude -p`) in the job's folder, with the permission mode `acceptEdits`, no permission prompts, and only the tools you allow in `rate.extra_args`; PowerShell for the notification and to read when the next installment runs; sleep or hibernation afterwards, if you chose so and nobody is using the PC. `rate check` reads (never changes) the wake-timer setting with `powercfg`.
- **It sends**, unless sharing is off: one line of numbers per finished job to `https://quotient-share.korvonordico.workers.dev` (see [What is shared](#what-is-shared)).
- **It fetches**, once a day: `https://raw.githubusercontent.com/Korvonordico/quotient-data/main/average.json`, or the service's `/v1/average` when GitHub does not answer. Both belong to the author.
- **The page with charts** is a file in `~/.quotient/report.html`, opened in your browser; it loads nothing from the internet.

## Commands

In the chat:

| Command | What it does |
|---|---|
| `/quotient:setup` | set Quotient up, or change its settings |
| `/quotient:report` | estimates against real costs, your limits, the weeks; `/quotient:report page` opens it as a page with charts |
| `/quotient:rate <job>` | split a big job into installments |
| `/quotient:share [on\|off]` | the shared average: exactly what is sent, and turning it on or off |
| `/quotient:help` | every command, with what it does |

Claude runs the other commands for you when you choose in the windows. `/quotient:help` lists them all (`rate week`, `rate pause`, `rate check` and the others).

## Limits, said plainly

- The first estimates will be rough. A 2026 study asked AI models to predict their own cost before coding tasks: eight models, correlation with the real cost at most 0.39, and systematically too low ([Bai et al., arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient does not make the model better at guessing: it measures the miss and corrects the next guess.
- It relies on Claude following the rules Quotient gives it. If a quote is skipped, that job is not measured (a big reply without a quote is counted and said once).
- Quotient itself has a weight: its rules at the start of a session (about 1,700 tokens) and a line at each message (about 270 tokens in a long chat), which stay in the chat and are re-read. It measures that weight and shows it in the report, with the number of tokens counted from characters (an estimate).
- The re-reading part of a quote assumes the cache works. After a pause longer than the cache lasts, the chat is written again at a higher price: that is measured afterwards, not foreseen.
- What Quotient saves cannot be measured, because a job not done has no cost. The report gives an estimate (for example, what the choices below the maximum avoided) and says it is one.
- Anthropic could add something similar to Claude Code. That would be fine.

<details>
<summary>Technical details</summary>

**The unit.** Costs are in weighted tokens: input-token equivalents at the ratios of Anthropic's API prices (input 1, cache write 1.25 for 5 minutes or 2 for 1 hour, cache read 0.1, output 5). In a live test, the dollar cost Claude Code reported was exactly the weighted tokens times the model's input price.

**How it hooks in.** At the start of a session Quotient gives Claude its rules once (about 5,900 characters, roughly 1,700 tokens); at each message, a short line (about 940 characters in a long chat, roughly 270 tokens, with the CHAT PART: how much re-reading this chat adds). Claude writes machine lines (`QUOTE:`, `CHOICE:`, `PACE:` with `today`, `new chat` or a plan, `JOB: CONTINUES`, `JOB: RESUME|CLOSE|DROP <id>` for a job of another chat, `LIMITS:`) in the last message of a reply; Quotient reads them at the end of the reply, adding up its cost with each API call counted once.

**Work and re-reading, exactly.** A call's prompt is read from the cache first, then written to it, then sent as plain input. For each call, the part of the prompt that the chat held when the job started (position 0 to the size of the job's first prompt) is priced with those weights: that is the re-reading; the rest of the cost is the work. A call after a compaction, whose prompt is shorter, adds no older chat. Jobs measured before 0.9.5 get their split once from their chat's transcript, if it still exists. The steps a quote will take are its corrected work divided by the work per step learned from finished jobs (30,000 weighted tokens until there are 3).

**Installments.** Each one is a non-interactive run (`claude -p`) in the job's folder, started by Windows Task Scheduler through a small launcher in `~/.quotient`, so it keeps working after plugin updates. A hook refuses every tool except the handoff update once what is spent plus the next two steps (the size of the latest calls, at most 40% of the cap) would reach the day's cap, so the steps that close the installment fit inside it. Each installment keeps a `PROGRESS: <n>%` line in its handoff; from it Quotient tells how much and how many installments remain. The day's cap includes re-reading each installment's own start, learned from the installments before. Two installments of the same job never run at the same time. A job remembers the chat that created it (Claude Code passes the chat's id to the commands it runs; when it does not, Quotient takes it at the end of the reply). The notification uses Windows' own notification system through PowerShell (on macOS `osascript`, on Linux `notify-send`) and writes no file; `config rate.notify false` turns it off.

**Your data.** Everything is in `~/.quotient/` (or `QUOTIENT_HOME`). `export` prints the exact lines sharing sends. The outbox is `share-outbox.jsonl`; the downloaded average is `average.json`; jobs open in a chat are in `chat-jobs.json` (forgotten after 7 days); the page with charts is `report.html`.

**The shared average.** Until you have 5 jobs of your own, the shared average counts as 5 jobs at its factor (the one of your model family when it has at least 5 jobs, else of all jobs), next to your own. From your fifth job on, only your jobs count.

**Tests.** `python -m unittest discover -s tests` (Quotient, offline) and `node --test server/test/stats.test.mjs` (the service's numbers). GitHub runs both at every push, on Windows and Ubuntu.

</details>

## Author

Francesco Candela (Korvonordico). The idea, the threshold, the learning from errors, the installments and the weekly budget are his; the code was written with Claude.

## License

MIT
