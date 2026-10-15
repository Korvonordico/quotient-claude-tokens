# Token Quotient: cost quotes and usage limits for Claude Code

Know what a [Claude Code](https://code.claude.com) job will cost before it starts, and fit big jobs into your 5-hour and weekly limits.

[![tests](https://github.com/Korvonordico/quotient-claude-tokens/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Korvonordico/quotient-claude-tokens/actions/workflows/tests.yml)
[![version](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FKorvonordico%2Fquotient-claude-tokens%2Fmain%2F.claude-plugin%2Fplugin.json&query=%24.version&label=version)](CHANGELOG.md)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Leggi in italiano](README.it.md)*

![Token Quotient demo](docs/demo.svg)

## Why

With a Claude subscription you pay for a job in usage limits: a 5-hour window and a weekly cap. Claude Code does not tell you what a job will cost before it starts, so you find out at the till. A big refactor or a long research task can hit the 5-hour limit halfway through, or use up most of your week.

Token Quotient (Quotient for short) gives you the price first, lets you choose, measures what the job really cost, and learns from the difference. Jobs too big for today can run in daily installments, at night if you like.

The name holds both halves: *quotient* starts like *quote*, the price agreed before a job, and in mathematics a quotient is the result of a division, like a big job divided into installments. *Token*, because that price is counted in tokens.

## What it does

- **A quote before a big job.** Above a threshold you set (300,000 weighted tokens by default), Claude does not start. A choice window offers *essential*, *good* or *max*, each with what it includes and its estimated cost.
- **You choose the pace.** All today, a plan in days with the amount per day, or any pace you write yourself.
- **The real cost after**, read from Claude Code's own records and set next to the estimate.
- **How long, too.** Each level also says how long the job should take, learned from your own finished jobs. Quotient reads the time from what Claude Code and Hermes already record (no extra window), counts only the working time, and at the end sets the real time next to the expected one. After the first million weighted tokens of a job, its own pace re-estimates what is left.
- **A correction factor.** Each quote is corrected by how far off the earlier ones were. Until you have 5 jobs of your own, it starts from a shared average of real jobs (numbers only, see [Privacy](#privacy)).
- **Installments that work while you are away.** The PC wakes up, does the day's piece and goes back to sleep. A notification and a report in the job's chat tell you what it did.

It also:

- shows how much of the 5-hour and weekly limits you have used and what is left, and tells you once if this week's pace would reach the limit before it resets;
- plans the week as a whole, so several installment jobs together never eat the share of the week you keep for yourself;
- measures apart what Claude spends re-reading a long chat, and offers a new chat when that saves (see [Work and re-reading](#work-and-re-reading-why-a-long-chat-costs-more));
- measures a job as one job even when it moves from one chat to another;
- measures its own weight, so you can see what it costs next to what it helps;
- opens the report as a page with charts (`/token-quotient:report page`, a local file);
- has ready-made ways of working for long installment jobs: a book, a research, a code review (`rate templates`);
- works inside [Hermes Agent](#quick-start-hermes-agent) too.

## Quick start: Claude Code

In Claude Code:

```
/plugin marketplace add Korvonordico/quotient-claude-tokens
/plugin install token-quotient@token-quotient
```

Installed it as `quotient@quotient`, before version 0.9.8? Remove that one first, then add the marketplace again: `/plugin uninstall quotient@quotient` and `/plugin marketplace remove quotient`. Your data in `~/.quotient` stays.

You need Python 3.8 or newer (standard library only, nothing else to install) and `sh`, which on Windows comes with Git for Windows, already used by Claude Code.

The first time, a window asks for four settings: from what size a job gets a quote, how much of the week to keep for yourself, the language, and whether Quotient may wake the PC for installments and put it back to sleep. A second window asks whether you want to take part in the shared average (yes, no, or anything else you write). Change them later with `/token-quotient:setup`.

Then work as usual. Under the threshold Claude just works; above it, or when you say "this is a big job", you get a quote first.

## Quick start: Hermes Agent

If you also use [Hermes Agent](https://github.com/NousResearch/hermes-agent) with your Claude login, its chats spend the same 5-hour and weekly limits. Quotient can count them and quote jobs inside Hermes too.

1. Clone this repository in a folder where it can stay:

   ```
   git clone https://github.com/Korvonordico/quotient-claude-tokens
   ```

2. Add two shell hooks to Hermes' `config.yaml`, where `<path>` is the folder you cloned:

   ```yaml
   hooks:
     pre_llm_call:
       - command: "<path>/scripts/quotient.py hermes-hook"
     post_llm_call:
       - command: "<path>/scripts/quotient.py hermes-hook"
   ```

   On macOS and Linux Hermes runs the script directly, so make it executable: `chmod +x <path>/scripts/quotient.py`. Hermes asks you to approve each new hook once.

From then on Hermes gives Claude the quote protocol and the real limits at each message, measures quoted jobs from `CHOICE:` to `JOB: CLOSE` (their cost and their working time), and suggests `/compress` when a chat has grown so long that every step mostly re-reads it (at most twice per chat, a day apart). Quotient reads Hermes' token counters from its local session store, read-only: numbers, model and chat title, never the text. Only Claude chats count against the plan. `quotient.py hermes` shows the Hermes numbers; `config hermes false` turns this off. Installments still run with Claude Code.

## How a big job goes

1. You ask for something big, or you say "this is a big job".
2. Claude does not start. A window opens with two questions:
   - **Level**: essential, good or max, with the estimate and the expected time for each. For a job of about 500,000 tokens: max 500,000, good 250,000, essential 100,000.
   - **Pace**: all today, or for example "2 days, about 250,000 a day" or "5 days, about 100,000 a day". In the free field you can write your own, such as "50,000 a day".
3. If you choose **all today**, Claude does the job. Quotient measures what it really cost and how long it took, and Claude tells you at your next message.
4. If you choose **installments**, a second window asks when the first one starts and at what time the next ones run.

Estimates are not guaranteed: at the start they can be quite far off, and they get closer with each finished job. If a reply costs more than the threshold and had no quote, Quotient tells you once, in one line, and counts it in the report.

Costs are in *weighted tokens*: input-token equivalents at the ratios of Anthropic's API prices (input 1, cache write 1.25, or 2 for the 1-hour cache, cache read 0.1, output 5).

## Commands

In the chat:

| Command | What it does |
|---|---|
| `/token-quotient:setup` | set Quotient up, or change its settings |
| `/token-quotient:report` | estimates against real costs, your limits, the weeks; `/token-quotient:report page` opens it as a page with charts |
| `/token-quotient:rate <job>` | split a big job into installments |
| `/token-quotient:share [on\|off]` | the shared average: exactly what is sent, and turning it on or off |
| `/token-quotient:help` | every command, with what it does |

Claude runs the other commands for you when you choose in the windows.

<details>
<summary>Commands from a terminal</summary>

Run them as `python scripts/quotient.py <command>` from the plugin's folder or a clone of this repository.

| Command | What it does |
|---|---|
| `report [--html]` | the report (`--html`: a page with charts, opened in the browser) |
| `setup --threshold N --reserve N --lang it\|en --after sleep\|hibernate\|nothing` | save the settings (also `--wake yes\|no` and `--share yes\|no`) |
| `setup --compact keep\|auto\|<tokens>` | long chats: keep them as they are, or let them compact themselves at a size |
| `config [key [value]]` | show every setting, or change one |
| `share status\|on\|off\|send` | sharing, from a terminal (`send`: send the waiting lines now) |
| `export` | the exact line sharing sends for each finished job |
| `timer start --raw N [--level L]`, `timer show`, `timer stop` | the stopwatch of a quoted job: Claude starts it when the work begins; `stop` hides the window until the next job |
| `backfill-time` | work out the time of jobs measured before 1.1.0 from their logs (Quotient does it by itself once) |
| `setup-statusline [--write]` | show the plan limits in the status line |
| `hermes` | Hermes Agent chats: read its token counters now |
| `tick` | read Hermes' counters and the plan limits now (for a scheduled task) |
| `rate new <job> --dir <folder> --task-file <file> --quote N (--days N \| --daily N) [--template book\|research\|code-review]` | create a job in installments |
| `rate templates` | the ready-made ways of working: book, research, code review |
| `rate run <job> [--force]` | run one installment now (`--force`: even if one already ran today) |
| `rate once <job> --time HH:MM` | one installment at that time (tomorrow if it has passed); wakes the PC |
| `rate schedule <job> --time HH:MM [--force]` | one installment every day at that time; wakes the PC |
| `rate after <job> sleep\|hibernate\|nothing` | what the PC does after each installment, if nobody uses it |
| `rate here <job>` | each installment's report comes to this chat |
| `rate week` | all open jobs against what is left of the week |
| `rate set <job> --daily N --per-day N --days N` | change a job: size of each installment, how many a day, how many in all |
| `rate pause <job>`, `rate resume <job>` | pause a job, or start it again |
| `rate stop <job>` | stop a job and remove its scheduled runs |
| `rate status [job]` | installments done and weighted tokens spent |
| `rate check [--live]` | can a scheduled installment wake this PC, and is Claude Code logged in (`--live`: one real call, a few cents) |

</details>

## How installments work

You leave the PC in sleep or hibernation, as you always do. Every installment then goes like this:

1. **At the time you chose** (for example 03:00), Windows wakes the PC.
2. **Quotient starts Claude Code** in the background, without opening the app. Claude reads the job and a short note of where it stopped last time.
3. **Claude works on the next piece** until it reaches that day's amount. Then it writes down where it stopped, and stops cleanly.
4. **When nobody is using the PC** (no keyboard or mouse for 10 minutes), Quotient puts it back to sleep, or into hibernation if you chose that, whoever turned it on. A notification comes first: move the mouse within 2 minutes and the PC stays on. If you are using the PC, Quotient waits until you stop, for up to 6 hours.
5. **The next day, at the same time, it starts again**, until the job is finished. Then the schedule removes itself.

When you come back, Windows has shown a notification for each installment, which stays in the notification center; a click opens a page with that installment's report (kept in the job's folder, under `reports`). The full report waits in the chat where you created the job and appears at your first message there: which installment, when, what it cost against the day's amount and the week, what it did, what is left and when the next one starts. Other chats tell you once, and a second time no sooner than a day later; then they stop. To get the reports in another chat, ask Claude there (`rate here <job>`).

Good to know:

- If you prefer that Quotient never touches the PC, choose so in the setup: installments then run only when the PC is already on.
- A timer can wake a PC that is asleep or hibernated, not one that is shut down. If the PC was off, the installment runs as soon as you turn it on.
- Windows must allow wake timers. `rate check` tells you whether it does, and how to turn them on.
- If you use the Claude desktop app, log in Claude Code once in a terminal (`claude auth login`): installments run outside the app. That login can expire: while an installment job is open, Quotient checks it every 6 hours on your messages (at no cost) and tells you in the chat, so you can renew it before the night. `rate check --live` makes one real call with the smallest model to be sure (a few cents). An installment that stops for the login spends nothing, and its notification says what to do.
- You can start one more installment the same day, if you accept that it uses more of that day's limit.
- Waking and sleeping work on Windows. On macOS and Linux Quotient gives you the line to schedule it yourself.

## More on how it works

### The week: all jobs together

Two or three jobs can each fit in the week and still not fit together. Quotient adds up every planned installment until the weekly limit resets and keeps a reserve for your normal use (20% unless you change it). If the plan does not fit, a window asks which jobs to keep, slow down or pause. An installment never eats into the reserve: it gets smaller, or waits.

### Your limits

Quotient records how much of the 5-hour and weekly limits you have used and when they reset, and can show it in Claude Code's status line (`setup-statusline --write`):

```
Quotient · 5-hour: 31% used, 69% left, resets 19:30 · week: 6% used, 94% left, resets Mon 12 07:00
```

It takes these numbers from what Claude Code passes to the status line, and also from Claude Code's own `/usage` command, run in the background with no tokens spent (at most every 10 minutes; off with `config limits.live false`). So the limits are there in the Claude desktop app too, where there is no status line. `tick` reads them now, for a scheduled task.

Over time it also estimates how many tokens 1% of each limit holds, so a quote can say "this takes about 8% of your week". Anthropic does not publish the limits in tokens, so this is an estimate, with its margin.

### The time of a job

A quote also says how long each level should take. Quotient measures the **working time** of every quoted job: the time Claude works, without your turns (from the end of a reply to your next message) and without the wait of the choice window. From your last 20 finished jobs it learns how many minutes a million weighted tokens of work take (the median), installments apart, and the expected time of a level is its corrected work times that. Like the correction factor, it gets closer with every job. Jobs measured before 1.1.0 get their time once from their logs: the chat's transcript, Hermes' message times, the installments' start and end.

Claude marks the start of the work right after the choice (`timer start`). After the first million weighted tokens, at each of your messages Quotient also looks at the job's own pace: how long the rest of the estimate takes at that pace, or that the estimate is already passed, so Claude can tell you a new estimate halfway instead of at the end.

The time is in Claude Code's status line. A small always-on-top stopwatch window exists too, off by default (`config timer.window true`; it needs Python's tkinter). At your next message Claude tells you the job's real cost and time against the expected ones. Each installment's report and notification say how long it worked, and `rate new` says how long each installment should take.

### Work and re-reading: why a long chat costs more

At every step (every call to the model) Claude re-reads everything the chat holds: the system, the tools, your rules, the conversation so far. Each re-read token costs little (a tenth of a new one, thanks to the cache), but it adds up. In a chat that starts with 165,000 tokens, every step costs about 16,500 weighted tokens before any work is done; a job of 100 steps, about 1.65 million. A model estimating a job thinks of the work, not of this.

So Quotient splits every job it measures in two:

- **work**: the steps of the job itself. The estimate is about this, and the correction is learned from it.
- **re-reading**: what the chat already held when the job started, read again at every step. Quotient measures it, and in a quote adds it from the size of the chat now and the steps the work will take.

A real case, 6 October 2026: a job cost 4.67 million weighted tokens, of which 2.82 million work and 1.85 million re-reading the 165,000 tokens the chat started with, over 107 steps.

When a chat has grown long, the window also offers to do the job **in a new chat**, and says how much that saves. You open a new chat and ask to continue: Quotient tells the new chat that a job is waiting, and measures it there.

### Long chats: keep them, or let them compact themselves

A plugin cannot run `/compact`, but Claude Code can summarize a chat by itself when it reaches a size. In the setup you choose one of three:

- **Keep the chat as it is** (the default). Quotient does not touch compaction; when a chat has grown long, the window offers a new chat.
- **Let it compact itself at the size Quotient recommends**: where re-reading the chat at every call costs about twice the work of a call, from your own numbers (about 600,000 tokens at the start).
- **At a size you choose**, from 100,000 to 1,000,000 tokens.

For the last two, Quotient writes `autoCompactWindow` in `~/.claude/settings.json`, and takes its own value back if you return to the first (a value you had set yourself is put back). A summary loses some details: when the chat gets close to the size, Quotient tells Claude once to save to files what must not be lost. Each compaction is measured, and the report says what it saved. Change it any time with `/token-quotient:setup` or in the plugin settings.

## Privacy

Everything Quotient records stays on your computer, in `~/.quotient/` (or `QUOTIENT_HOME`). It reads Claude Code's transcripts only for numbers: the token counts of each call, the machine lines Claude writes and the names of the tools Claude called. No text from your chats is ever sent anywhere.

One thing leaves your computer, and you can turn it off: after each finished job, one line of numbers for the shared average, exactly this:

```json
{"v":1,"q":"1.1.0","family":"opus","estimate":225000,"actual":259000}
```

- No dates, no times, no names, no text, no paths, no session or user ids. The service that collects the lines ([code in `server/`](server/)) does not keep IP addresses.
- Turn it off with `/token-quotient:share off`, the plugin setting *Share anonymous numbers*, or `QUOTIENT_SHARE=0`. With sharing off you still get the shared average. `/token-quotient:share` shows exactly what is sent and how many lines are waiting.
- Quotient also downloads the shared average once a day, and reads your plan usage from Anthropic with Claude Code's own login (details below).

Everything in detail: [PRIVACY.md](PRIVACY.md).

<details>
<summary>What is shared, in detail</summary>

Each copy of Quotient learns from its own errors, but a new user has no errors yet. So the copies pool their numbers. The line holds the format, the Quotient version, the model family (opus, sonnet, haiku, fable or other), the raw estimate and the real cost of the work in weighted tokens (from 0.9.5 without the re-reading of the chat, which the estimate is not about), rounded to 3 significant digits. It leaves at the start of your next session, never in the middle of a reply, and nothing is queued before Claude Code has shown you a message about it.

- The service does not keep IP addresses: its code never reads them and request logs are off.
- At most once a week, after at least 20 new jobs and never below 30 jobs in all, it publishes the average in its own repository, [quotient-data](https://github.com/Korvonordico/quotient-data) (the service's key can write only there, never in this code). Every copy of Quotient downloads that file once a day and uses it only between x0.25 and x4: anyone can send numbers, so it is a best-effort average.
- The first-use window asks whether you take part (yes by default), and you can change it any time.

</details>

<details>
<summary>Everything Quotient runs, sends and fetches</summary>

- **On your computer, always**: its Python script, through `sh`, at the start of each session, at each message, at the end of each reply, before a compaction, and before each tool call inside an installment. It reads Claude Code's transcripts of your chats only for numbers: the token counts of each call, the machine lines Claude writes, and which tools Claude called (to measure the cost and Quotient's own weight). No text from them is ever sent anywhere.
- **It writes** only in `~/.quotient/` (or `QUOTIENT_HOME`), plus a report page for each installment in the job's own folder. The two exceptions touch `~/.claude/settings.json`, and only when you choose them: `setup-statusline --write` puts the status line there, and the long-chat choice "compact" writes `autoCompactWindow` there (taken back when you choose "keep" again).
- **For installments, only after you choose them in the window**: Windows Task Scheduler tasks (`schtasks`) that run at the time you chose and, if you allow it, wake the PC; Claude Code itself (`claude -p`) in the job's folder, with the permission mode `acceptEdits`, no permission prompts, and only the tools you allow in `rate.extra_args`; PowerShell for the notification and to read when the next installment runs; sleep or hibernation afterwards, if you chose so and nobody is using the PC. `rate check` reads (never changes) the wake-timer setting with `powercfg`.
- **It runs Claude Code's own `/usage` command** to read your plan usage: Claude Code answers it locally, with its own login, and Quotient keeps only the percentages and the reset times. At most every 10 minutes, with no tokens spent; Quotient never reads your login. Off with `config limits.live false`.
- **With Hermes Agent**, it reads Hermes' local session store, read-only: token counters, model and chat title, and, for the working time of a quoted job, when each message was written and by whom (never its text).
- **The stopwatch window**, only if you turn it on (`config timer.window true`): a small window of its own (Python's tkinter) that only reads `~/.quotient/timer.json`.
- **It sends**, unless sharing is off: one line of numbers per finished job to `https://quotient-share.korvonordico.workers.dev`.
- **It fetches**, once a day: `https://raw.githubusercontent.com/Korvonordico/quotient-data/main/average.json`, or the service's `/v1/average` when GitHub does not answer. Both belong to the author.
- **The page with charts** is a file, `~/.quotient/report.html`, opened in your browser; it loads nothing from the internet.

</details>

## Known limitations

- The first estimates will be rough. A 2026 study asked AI models to predict their own cost before coding tasks: eight models, correlation with the real cost at most 0.39, and systematically too low ([Bai et al., arXiv:2604.22750](https://arxiv.org/abs/2604.22750)). Quotient does not make the model better at guessing: it measures the miss and corrects the next guess.
- It relies on Claude following the rules Quotient gives it. If a quote is skipped, that job is not measured (a big reply without a quote is counted and said once).
- Quotient itself has a weight: its rules at the start of a session (about 1,700 tokens) and a line at each message (about 270 tokens in a long chat), which stay in the chat and are re-read. It measures that weight and shows it in the report, with the number of tokens counted from characters (an estimate).
- The re-reading part of a quote assumes the cache works. After a pause longer than the cache lasts, the chat is written again at a higher price: that is measured afterwards, not foreseen.
- What Quotient saves cannot be measured, because a job not done has no cost. The report gives an estimate (for example, what the choices below the maximum avoided) and says it is one.
- The working time leaves out your turns and the choice window, not other waits inside a reply (a permission prompt, a command waiting for your approval): those count as work. The expected time is as good as the token estimate it comes from, and the first ones are rough.
- Anthropic could add something similar to Claude Code. That would be fine.

<details>
<summary>Technical details</summary>

**The unit.** Costs are in weighted tokens: input-token equivalents at the ratios of Anthropic's API prices (input 1, cache write 1.25 for 5 minutes or 2 for 1 hour, cache read 0.1, output 5). In a live test, the dollar cost Claude Code reported was exactly the weighted tokens times the model's input price.

**How it hooks in.** At the start of a session Quotient gives Claude its rules once (about 5,900 characters, roughly 1,700 tokens); at each message, a short line (about 940 characters in a long chat, roughly 270 tokens, with the CHAT PART: how much re-reading this chat adds). Claude writes machine lines (`QUOTE:`, `CHOICE:`, `PACE:` with `today`, `new chat` or a plan, `JOB: CONTINUES`, `JOB: RESUME|CLOSE|DROP <id>` for a job of another chat, `LIMITS:`) in the last message of a reply; Quotient reads them at the end of the reply, adding up its cost with each API call counted once.

**Work and re-reading, exactly.** A call's prompt is read from the cache first, then written to it, then sent as plain input. For each call, the part of the prompt that the chat held when the job started (position 0 to the size of the job's first prompt) is priced with those weights: that is the re-reading; the rest of the cost is the work. A call after a compaction, whose prompt is shorter, adds no older chat. Jobs measured before 0.9.5 get their split once from their chat's transcript, if it still exists. The steps a quote will take are its corrected work divided by the work per step learned from finished jobs (30,000 weighted tokens until there are 3).

**Installments.** Each one is a non-interactive run (`claude -p`) in the job's folder, started by Windows Task Scheduler through a small launcher in `~/.quotient`, so it keeps working after plugin updates. A hook refuses every tool except the handoff update once what is spent plus the next two steps (the size of the latest calls, at most 40% of the cap) would reach the day's cap, so the steps that close the installment fit inside it. Each installment keeps a `PROGRESS: <n>%` line in its handoff; from it Quotient tells how much and how many installments remain. The day's cap includes re-reading each installment's own start, learned from the installments before. Two installments of the same job never run at the same time. A job remembers the chat that created it (Claude Code passes the chat's id to the commands it runs; when it does not, Quotient takes it at the end of the reply). The notification uses Windows' own notification system through PowerShell (on macOS `osascript`, on Linux `notify-send`) and writes no file; `config rate.notify false` turns it off.

**Time.** The working time of a turn is the sum of the gaps between its consecutive entries (Claude Code's transcript, or the message times in Hermes' session store), except the gap before a prompt of yours and the gap before the answer to the choice window (`AskUserQuestion`, or Hermes' `clarify`). A job adds up its turns; its first turn counts from `timer start` when Claude ran it, else from the turn's start. An installment runs alone, so its time is its whole run. The expected time is the corrected work times the median minutes per million weighted tokens of work of your last 20 timed jobs of the same kind (chat or installments), shown once there are 3 of them. The hooks keep `~/.quotient/timer.json` (run, pause on your turn, end); the window reads it every second and writes a heartbeat, so only one opens.

**Long chats.** A plugin cannot run `/compact` (hooks can only block or watch a compaction), so the choice is written as Claude Code's own `autoCompactWindow`; the environment variable `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, if you set it, wins over it. A `PreCompact` hook notes the chat's size before the summary, and the end of the next reply notes the size after it; the saving is that difference, at the cache price, at every later call of that chat (`compactions.jsonl`).

**Your data.** Everything is in `~/.quotient/` (or `QUOTIENT_HOME`). `export` prints the exact lines sharing sends. The outbox is `share-outbox.jsonl`; the downloaded average is `average.json`; jobs open in a chat are in `chat-jobs.json` (forgotten after 7 days); the page with charts is `report.html`.

**The shared average.** Until you have 5 jobs of your own, the shared average counts as 5 jobs at its factor (the one of your model family when it has at least 5 jobs, else of all jobs), next to your own. From your fifth job on, only your jobs count.

**Tests.** `python -m unittest discover -s tests` (Quotient, offline) and `node --test server/test/stats.test.mjs` (the service's numbers). GitHub Actions runs them at every push and pull request: the Python tests on Windows and Ubuntu with Python 3.9 and 3.13, the service's on Ubuntu.

</details>

## FAQ

**Does it work with other AI tools?**
Quotient is built for Claude Code: it uses Claude Code's hooks and transcripts and Anthropic's plan limits. It also works inside Hermes Agent when Hermes runs Claude with your Claude login; there it counts only Claude chats, since other providers do not use your plan. Other assistants are not supported.

**Is it an official Anthropic tool?**
No. Quotient is an independent open-source project by Francesco Candela. It is not affiliated with or endorsed by Anthropic, or by Nous Research, which makes Hermes Agent.

**What if Anthropic changes the limits?**
The used percentages and reset times come from Anthropic at every reading, so they stay correct, and Quotient never assumes how many tokens a limit holds. Its estimate of the size of 1% is learned from all the readings it has recorded, so after a change it is off for a while and moves toward the new size as new readings come in. If the request behind `/usage` changes, the live reading stops working until Quotient is updated, and the status line readings remain. If the API price ratios change, the weights are settings (for example `config weights.output 5`).

**How accurate are the quotes?**
Rough at first. Each new quote is multiplied by a correction factor: the median ratio of real to estimated cost over your last 20 finished jobs. Installments have their own factor, learned from installments alone once there are 5 of them. Until you have 5 jobs, the shared average counts as 5 jobs next to yours. The part of a quote that comes from re-reading the chat is worked out from the steps your jobs really took (Quotient measures how many steps a job takes per million weighted tokens of work), not guessed. `/token-quotient:report` shows the typical miss before correction and the recent miss with it, so you can see whether it is getting closer. The expected time works the same way: your last 20 jobs' minutes per million weighted tokens of work, times the corrected estimate.

**Does Quotient use tokens itself?**
Yes, a little: about 1,700 tokens of rules at the start of a session and a line of about 270 tokens at each message in a long chat. Both stay in the chat and are re-read, so Quotient measures them and shows them in the report.

**Does it work on macOS and Linux?**
Quotes, measuring, limits and the report work wherever Claude Code, Python 3.8+ and `sh` run. Waking the PC and putting it back to sleep work only on Windows; on macOS and Linux Quotient gives you the line to schedule installments yourself, and notifications use `osascript` or `notify-send`. The automatic tests run on Windows and Ubuntu.

## Roadmap

Ideas under consideration are in [ROADMAP.md](ROADMAP.md). The first one, a quote of how long a job will take with a live stopwatch and a time that learns, came in 1.1.0.

## Contributing

Bug reports, quotes that were far off, and pull requests are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). The tests run with `python -m unittest discover -s tests`, with no packages to install. Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Report security problems privately, as described in [SECURITY.md](SECURITY.md). Changes between versions are in [CHANGELOG.md](CHANGELOG.md).

## Support

Quotient is free and MIT licensed. If it saves you a week of limits:

- star the repository, and tell people who keep hitting the limits;
- open an issue when a quote was far off: real cases are what make it better;
- sponsor the work: GitHub Sponsors <!-- TODO: add link --> · Ko-fi <!-- TODO: add link -->

## Author

Francesco Candela (Korvonordico). The idea, the threshold, the learning from errors, the installments and the weekly budget are his; the code was written with Claude.

## License

[MIT](LICENSE)
