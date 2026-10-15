# Changelog

All notable changes to Token Quotient (Quotient for short; called Quotient up to 0.9.7) are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are those of `.claude-plugin/plugin.json`; dates are those of the commits. Each version links to the commit that released it; from 0.9.7 on, it also has a GitHub release with the same notes.

## [1.1.2] - 2026-10-15

### Added

- **The week checked against the 5 hours** (the user's idea). Both percentages rise with the same use: within one 5-hour window and one week, the points the 5 hours rose are set against the points the week rose (`window_ratio`). The ratio, times the size of 1% of the 5 hours, is a second estimate of the week, with its margin (the percentages are whole numbers: two standard deviations of the rounding, which partly cancels over the windows). The report shows the two estimates side by side and says when they are more than 1.5 times apart (`config ratio.factor`). When the week's own estimate has fewer than 3 points and the ratio has them, the ratio is used in its place (in the quotes' line, the week's plan, the checks and the installments' reports), and that is said. On the author's readings of 5 to 15 October 2026 the two came out x1.00 apart. Nothing new is sent to the server.
- **A change of subscription.** Each user learns the size of their own limits on their own PC, but the size was learned from every window ever recorded, so after a change of plan the old size stayed mixed in for a long time. Now, when the last three 5-hour windows (5 points or more each, on more than one day) are all more than 1.6 times away from the earlier ones in the same direction (`config plan.factor`), and the week in the same time is too, Quotient takes it as a change of plan: from the start of those windows on it learns only from the new readings, writes the change in `plan-changes.jsonl`, and Claude tells the user once, in Claude Code or Hermes: the limit seems to have changed, maybe they changed subscription, Quotient starts learning it again. A day of heavy use outside Quotient makes the limit look smaller, which is why one window or one day is not enough.
- **`plan-changed`**: the user says the subscription changed, and the size is learned again from now (until the week has points of its own, from the ratio with the 5 hours of before, said so). `plan-changed --undo` takes the last change back; the windows already judged are not judged again.
- The README (English and Italian) says that the size of the limits is learned by each user for their plan, how the 5-hour/week check works, and what happens when you change plan.

## [1.1.1] - 2026-10-15

### Fixed

- **The end of an installment's cap is kept for saving.** On 15/10/2026 an installment started three helpers (the Agent tool); at the cap the hook refused every tool, the helpers' too, and their results (about 120 web searches) were lost before being written. Now, in the last 8% of the cap (`config rate.save_percent`), the hook refuses only the tools that start new work (helpers, web searches and fetches, commands) and lets Write, Edit, MultiEdit, NotebookEdit, TodoWrite and a here-document into a file through; its message says to save at once what was found in the handoff. Past the real cap everything stops, as before. A helper's tool call counts the whole installment.
- **Save as you go.** The installment protocol asks to save results after each part, and to tell helpers to write their results to files as they go, not only at the end.
- **The helpers' work is not lost.** At the end of an installment that stopped with helpers, Quotient writes in the handoff a section with the helpers' transcripts, their short description and how many searches, pages and reads each made, so the next installment takes them up instead of doing them again.
- The tests no longer read `QUOTIENT_CAP` from the environment, so they pass inside an installment too.

### Added

- **The measures against the week.** If the measures are wrong, the correction learns the wrong thing (an outside review said so). Each finished job and each installment is now set against how much the weekly limit rose in the same time, through the learned size of 1%. When the two are more than 3 times apart (`config check.factor`) and no other job or installment was running, Claude tells the user once at the next message that the measure does not match the week, and the report lists it (`checks.jsonl`). Jobs under 4 points of the week are not judged (`config check.min_points`). It changes nothing by itself, and says that other chats and use Quotient cannot see move the week too.
- **Messages in between.** While a job is open, a reply about something else ends with an `ASIDE` line: its cost goes in the job's `aside`, in the real cost (so the limits add up) but not in the work the correction learns from. At the close: work · messages in between · total. After the choice Claude says in one line that writing during the job adds to its cost. In Hermes too (the user's idea).
- **Apart, now.** A new pace in the choice window: the job starts at once as one installment in a separate session (`rate apart`: `rate new` with one installment and the whole corrected quote as its cap, started in the background), so its measure is clean and the chat does not re-read it. The window says the cons: no talking to it while it works, the task must be written well, no questions halfway, a command that needs a permission may stop it. From Hermes too, where it runs with Claude Code (the user's idea).
- **How we check the measures**, a short section of the README (English and Italian): the automatic tests, the errors found and fixed, the new check against the week, and what is not shown yet.

## [1.1.0] - 2026-10-15

### Added

- **How long a job takes.** A quote now also says how long each level should take: its corrected work times the minutes a million weighted tokens of work took in your last 20 jobs (median; installments apart; shown once 3 jobs have a time). Like the correction factor, it learns from every finished job.
- **The time is read, not shown in one more window.** It comes from what Claude Code and Hermes already record; Claude marks the start of the work with `timer start`. It is in Claude Code's status line; an always-on-top stopwatch window exists but is off by default (`config timer.window true`).
- **The job's own pace.** After the first million weighted tokens, at each message Quotient tells Claude how long the rest of the estimate takes at the job's own pace, or that the estimate is already passed, so a new estimate comes halfway (the user's idea).
- **The real time after.** Every quoted job records its working time (`seconds`) and the expected one (`predicted_seconds`): the time the agent works, without the user's turns and without the wait of the choice window (`AskUserQuestion` in Claude Code, `clarify` in Hermes, read from the message times, never the text). At the next message Claude gets the job's real cost and time against the expected ones, to tell the user in one line.
- **Installments with a time.** `rate new` says how long each installment should take; each installment records how long it ran, and its report and notification say it.
- **Old jobs get their time once** from what is still on disk (Claude Code transcripts, Hermes message times, the installments' runs): `backfill-time`, run by itself at the start of a session.

### Fixed

- The demo's texts were all drawn at 16 px: a CSS rule overrode their sizes, and the smaller ones only had their letters squeezed together. The demo now has the time in the quote, the stopwatch, and the time of each night.

## [1.0.1] - 2026-10-14

### Fixed

- **Hermes: a level chosen for installments, or for a new chat, no longer opens a job in the chat that quoted it.** That chat only made the quote: measuring it as the job counted the wrong thing (Claude Code already skipped it). The installments measure themselves.

## [1.0.0] - 2026-10-14

Quotes that learn from the right numbers. On 14/10/2026 the correction factor had fallen to x0.14 and the typical miss had grown to x5: the jobs were measured wrong, not quoted wrong.

### Fixed

- **A QUOTE written again no longer cuts a job into pieces.** An agent that wrote its `QUOTE` and `CHOICE` lines again at every message made Quotient close the job and open a new one each time: in Hermes 4 jobs became 57, each with the whole estimate and a sliver of the work, and the factor fell to x0.14; in Claude Code the job closed before its end. The same numbers (and the same level) are now the same job, open or just closed; a quote with other numbers is still a new job. The protocol says to write `QUOTE` and `CHOICE` once.
- **Hermes: the job starts where the reply with the choice started**, as in Claude Code. The `CHOICE` line comes at the end of a reply, after its work, so a job chosen and done in the same reply counted almost nothing.
- **Hermes: `CHOICE` and `JOB: CLOSE` in the same reply** close the job at once; before, it stayed open.
- **Hermes: a job in the first reply of a chat has its chat part.** Nothing had been measured before it, so the re-reading counted as work.

### Added

- **Installments have their own correction factor**, learned from installments alone once there are 5 of them: they behave differently from chat jobs (their raw estimates were right on the median, and the chat jobs' factor made them wrong by up to x27). It sets the daily cap of `rate new` and the week plan, and is shown next to the other factor in the report, in the prompt line and in the protocol.
- **Measured steps.** Quotient counts the steps (calls) of each job, Hermes too, and gives the median steps per million weighted tokens of work; the protocol tells the agent to work out the chat part of a quote from them, plus one step per message expected from the user, instead of guessing.

### Changed

- **After an installment, the PC goes back to sleep whoever turned it on** (the user: waking it and putting it to sleep are independent). It still never sleeps under someone using it: it waits until nobody has touched keyboard and mouse for 10 minutes, up to 6 hours (`rate.after_wait_hours`), then shows a notification and waits 2 more minutes; a touch keeps the PC on. Before, a PC that was already on stayed on.
- Jobs already cut into pieces are not repaired automatically.

## [0.9.9] - 2026-10-12

For the second check of Anthropic's plugin directory. Nothing changes in what Quotient does.

### Changed

- The plugin's settings are read by their full names (`CLAUDE_PLUGIN_OPTION_THRESHOLD` and the other seven, written out one by one in `plugin_options()`), so it is plain that Quotient reads eight settings and no credential. Before, each name was put together at run time.
- The programs Quotient starts get their few extra variables written out by name, only while they run, and inherit the rest as any program does: `QUOTIENT_JOB` and `QUOTIENT_CAP` for an installment, `QUOTIENT_CHECK` for the login check, the four `QUOTIENT_TOAST_` ones for a Windows notification; for `/usage`, `CLAUDECODE` is taken away while it runs. Before, Quotient handed them a copy of the whole environment. They receive the same environment as before.
- `plugin.json` no longer names the icon, and no test opens it: the directory still finds the icon in its usual place, next to `plugin.json`. The directory's check holds for review an image that code points to, because a program pointed at it could run its bytes.
- `.gitignore` no longer lists `.wrangler/` (the deploy state of the shared-average service, kept out of git on the deploying machine only): listed there, the directory's check read it as the plugin reading Wrangler's login folder.
- Tests use `http://localhost` instead of `example.com` as an address Quotient must refuse, and set their variables with `mock.patch.dict` instead of copying the environment.

## [0.9.8] - 2026-10-12

### Changed

- **New name: Token Quotient.** The plugin is now `token-quotient`, for Anthropic's plugin directory, where the name "quotient" was already taken. The commands are `/token-quotient:setup`, `report`, `rate`, `share` and `help`; install with `/plugin install token-quotient@token-quotient`. Your data in `~/.quotient` stays where it is. If you installed `quotient@quotient`, uninstall it and install `token-quotient@token-quotient`: with both, every turn would be counted twice.
- The plan limits are read through Claude Code's own `/usage` command (`claude -p /usage`, without hooks and without saving a session), at most every 10 minutes and with no tokens spent. Quotient no longer reads Claude Code's login. The limits are there in the Claude desktop app too, where there is no status line.
- The launchers in `~/.quotient`, for scheduled installments and for the status line, run one exact file of the installed plugin, and each session start rewrites them after an update. Before, they looked for the newest copy in any plugin folder.
- The slash commands may run only their own script, with the arguments they need (`allowed-tools`), instead of any `sh` command.
- GitHub Actions moved off Node 20 (`actions/checkout`, `actions/setup-python` and `actions/setup-node` v7).

### Added

- The plugin's icon, and its documentation, support and privacy links, for the directory listing.
- Hermes Agent as a second source: Quotient reads Hermes' local session store (read-only: token counters, model and chat title, never the text) and counts its Claude chats in the weeks and in the report. `quotient.py hermes` shows them; `config hermes false` turns it off.
- Quotient inside Hermes Agent: the `hermes-hook` command, for Hermes' `pre_llm_call` and `post_llm_call` shell hooks, gives Claude the quote protocol and the real limits at each message, and measures quoted jobs from `CHOICE:` to `JOB: CLOSE` (or `JOB: DROP`), subagents included.
- In a long Hermes chat, Claude is told to suggest `/compress` (at most twice per chat, a day apart).
- `tick` command: reads Hermes' counters and the plan limits now, for a scheduled task.
- ROADMAP.md, with the first idea: time estimates with a live timer and a correction factor for time.

### Fixed

- Claude Code's notices about background tasks (`<task-notification>`) are no longer counted as turns written by the user.
- A scheduled installment finds Quotient's other files: before, the launcher ran without them, so the week's room left out Hermes' chats.
- Commands that run Quotient through `run.sh` are counted in Quotient's own weight too.

## [0.9.7] - 2026-10-08

### Changed

- After an installment, the PC goes back to sleep only if the installment woke it. A PC that was already on stays on, even if nobody is touching the keyboard or mouse (Quotient reads this from Windows' own log).

### Added

- An expired Claude Code login is found before the night: while an installment job is open, Quotient checks the login every 6 hours on your messages, at no cost, and says so in the chat. `rate check --live` makes one real call with the smallest model. An installment stopped by the login spends nothing, and its notification says what to do.

## [0.9.6] - 2026-10-07

### Added

- Long chats: keep them as they are (the default), let Claude Code compact them at the size Quotient recommends, or at a size you choose from 100,000 to 1,000,000 tokens (`setup --compact`). Quotient writes `autoCompactWindow` in `~/.claude/settings.json` only for the last two, and puts back what was there before when you return to the first.
- A `PreCompact` hook measures each compaction; the report says what it saved.
- Each installment's report as a page in the job's folder (`reports`), opened from the notification.

## [0.9.5] - 2026-10-06

### Added

- The work apart from re-reading the chat: quotes are about the work, and the window shows work + re-reading = total (the CHAT PART). In a long chat the window offers to do the job in a new chat and says how much that saves.
- Jobs that move between chats: chosen in one chat and done in another, or left open in one and finished in another, they are measured as one job (`PACE: new chat`, `JOB: RESUME`).
- Quotient's own weight (its rules and its line at each message) is measured and shown in the report.
- A warning, once, when this week's pace would reach the weekly limit before it resets.
- A one-line notice, once, when a reply cost more than the threshold without a quote; it is counted in the report.
- `/quotient:report page` (`report --html`): the report as a local page with charts.
- Templates for long installment jobs: book, research, code review (`rate templates`, `rate new --template`).
- A GitHub Actions workflow that runs the tests at every push, on Windows and Ubuntu.

### Changed

- The real cost in the shared line is the work only, without re-reading the chat. Jobs measured before 0.9.5 get their split once from their chat's transcript, if it still exists.

## [0.9.1] - 2026-10-06

### Added

- Each installment's report comes back to the chat that created the job, at your next message there; other chats tell you once, and a second time no sooner than a day later. `rate here <job>` moves the reports to another chat.
- A system notification at the end of each installment.

## [0.9.0] - 2026-10-06

### Added

- The shared average, anonymous and by choice: after each finished job, one line of numbers (format, Quotient version, model family, raw estimate and real cost, rounded) goes to a small service, which publishes the average at most once a week in [quotient-data](https://github.com/Korvonordico/quotient-data). Every copy downloads it once a day.
- The first-use window asks whether you take part (yes by default). `/quotient:share`, the plugin setting *Share anonymous numbers* and `QUOTIENT_SHARE=0` turn it off; the shared average is used either way.
- PRIVACY.md, and the service's code in `server/` (a Cloudflare Worker), with its tests.

## [0.8.0] - 2026-10-05

### Added

- New users start from real numbers, not from zero: until you have 5 jobs of your own, quotes are corrected with an average of real jobs shipped with Quotient.

## [0.7.5] - 2026-10-05

### Added

- You choose whether Quotient may wake the PC for installments (`setup --wake yes|no`). With waking off, installments run only when the PC is already on.

### Changed

- The repository moved to `Korvonordico/quotient-claude-tokens`: install with `/plugin marketplace add Korvonordico/quotient-claude-tokens`.
- A shorter README, with the night installment cycle step by step and the technical details folded away.

## [0.7.4] - 2026-10-05

### Changed

- The plugin's name, description and keywords say "token", where people search for it.
- The README lists everything Quotient can do, in English and Italian.

## [0.7.3] - 2026-10-05

### Fixed

- Only a `JOB DONE` on the first line of the handoff ends a job. Before, a sentence that only mentioned it could close a job too early.

## [0.7.2] - 2026-10-05

### Fixed

- Each `rate once` time is its own scheduled task, so a second time no longer replaces the first. Windows removes these tasks a week after they are due, so they do not pile up.

## [0.7.1] - 2026-10-05

### Added

- `/quotient:help` and the `commands` command: the list of commands, with what each one does.

## [0.7.0] - 2026-10-05

### Added

- Setup at first use: a window asks for the threshold, the weekly reserve, the language and what the PC does after installments. `/quotient:setup` changes them later.

## [0.6.0] - 2026-10-05

### Added

- The week, all installment jobs together: `rate week` adds up the open jobs until the weekly limit resets and compares them with what is left, minus a reserve for normal use (20% by default). When they do not fit, a window asks which jobs to keep, slow down (`rate set`) or pause (`rate pause`, `rate resume`). An installment never plans into the reserve.

## [0.5.1] - 2026-10-05

### Fixed

- Scheduled tasks find Claude Code, also when it comes with the Claude desktop app, and Quotient says clearly when Claude Code is not logged in for runs outside the app (`claude auth login`).

## [0.5.0] - 2026-10-05

### Added

- On Windows, scheduled installments wake the PC from sleep or hibernation and, if you choose so, put it back to sleep when nobody has used it for 10 minutes (`rate after`). `rate check` says whether wake timers are allowed.

## [0.4.0] - 2026-10-05

### Added

- Plan limits: used, left and reset times of the 5-hour and weekly limits, recorded from Claude Code's status line (`setup-statusline`), and an estimate of how many weighted tokens 1% of each limit holds.
- The report lists the weeks.

## [0.3.1] - 2026-10-05

### Changed

- Installment plans are shown as days with the amount per day, and the margin of an estimate is written in words.

## [0.3.0] - 2026-10-05

### Added

- The choice window: two questions, level and pace, with a free field for any pace.
- After choosing installments, a second window for when the first one starts and when the next ones run; `rate once`, `rate run --force` and `rate stop`.

## [0.2.0] - 2026-10-05

### Added

- First version: a quote before big jobs (*essential*, *good*, *max*) above a threshold you choose; the real cost after, read from Claude Code's transcripts, in weighted tokens; a correction factor learned from the difference; big jobs in daily installments with a spending cap (`rate new`, `rate run`, `rate schedule`, `rate status`); `/quotient:report` and `/quotient:rate`.

[1.1.2]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.2
[1.1.1]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.1
[1.1.0]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.0
[1.0.1]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.0.1
[1.0.0]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.0.0
[0.9.9]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v0.9.9
[0.9.8]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v0.9.8
[0.9.7]: https://github.com/Korvonordico/quotient-claude-tokens/commit/6fc9013
[0.9.6]: https://github.com/Korvonordico/quotient-claude-tokens/commit/3091a62
[0.9.5]: https://github.com/Korvonordico/quotient-claude-tokens/commit/12da94a
[0.9.1]: https://github.com/Korvonordico/quotient-claude-tokens/commit/b06b414
[0.9.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/ef52063
[0.8.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/57089a1
[0.7.5]: https://github.com/Korvonordico/quotient-claude-tokens/commit/037443a
[0.7.4]: https://github.com/Korvonordico/quotient-claude-tokens/commit/11af62d
[0.7.3]: https://github.com/Korvonordico/quotient-claude-tokens/commit/90f803d
[0.7.2]: https://github.com/Korvonordico/quotient-claude-tokens/commit/a6f4794
[0.7.1]: https://github.com/Korvonordico/quotient-claude-tokens/commit/2d06e50
[0.7.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/91e1177
[0.6.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/76c4c26
[0.5.1]: https://github.com/Korvonordico/quotient-claude-tokens/commit/28ee122
[0.5.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/22949ca
[0.4.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/e9516a1
[0.3.1]: https://github.com/Korvonordico/quotient-claude-tokens/commit/d42643c
[0.3.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/50378fc
[0.2.0]: https://github.com/Korvonordico/quotient-claude-tokens/commit/c96ac40
