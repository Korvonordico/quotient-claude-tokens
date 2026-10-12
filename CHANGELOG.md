# Changelog

All notable changes to Token Quotient (Quotient for short; called Quotient up to 0.9.7) are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are those of `.claude-plugin/plugin.json`; dates are those of the commits. Each version links to the commit that released it; from 0.9.7 on, it also has a GitHub release with the same notes.

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
