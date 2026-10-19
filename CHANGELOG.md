# Changelog

All notable changes to Token Quotient (Quotient for short; called Quotient up to 0.9.7) are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions are those of `.claude-plugin/plugin.json`; dates are those of the commits. Each version links to the commit that released it; from 0.9.7 on, it also has a GitHub release with the same notes.

## [Unreleased]

### Fixed

- **An installment's start is counted** (on for everyone; `rate.start_fixed` 1, `rate.min_cap_starts` 1.5). Each installment is a new Claude Code session, and its first call writes the whole start (system, tools, rules: about 50k tokens) to the one-hour cache: on the author's PC about 94k weighted tokens before any work. Quotient counted only the re-reading of that start, as a share of the work, so small installments were quoted far too low: on 19/10/2026 a job run apart was given a 99k cap, spent 139k just starting and did nothing. Now each installment's start is counted once (the median of the last 10 installments, recorded as `start_wt` in each run from now on, worked out for the older ones), the re-reading share leaves it out, and each day of a plan in days pays its own. Backtest on the 48 measured installments, each predicted from the 10 before it: typical miss of an installment's whole cost 8.9% -> 6.7%, within 30% 40 -> 48; installments under 500k of work 36% -> 12%.
- **A cap too small to start is raised**: `rate new`, `rate apart` and `rate set` raise a cap under 1.5 times the largest recent start (155k on the author's PC) and say so, and an installment whose week has less room than that is skipped instead of spending what is left just starting. The quote table says what the start costs. `config rate.start_fixed 0` and `config rate.min_cap_starts 0` bring back the old way.

## [1.2.1] - 2026-10-19

### Changed

- **The work in pieces** (the user's request; `piece_share` 0.25, `piece_min` 250,000). A chat job's piece, with its `PROGRESS` line, is a quarter of its corrected quote (at least 250k) instead of always 1M, so jobs under 1M get pieces too. An installment records its handoff's `PROGRESS` line each time it changes (`pieces` in its run), so an installment of 2-3M is no longer one piece, and the estimate of the whole job uses every piece. Tested for real with API credits: a 265k installment recorded 6 pieces (2% to 70%, then 82% at the end), and the estimate of the whole job narrowed from 617k to 323k as they came. A first version paused one tool call at each quarter of the cap to ask for the line: in a 100k installment the pauses ate the cap and nothing was saved, so Quotient now only reads the line, never pauses. `config piece_share 0` brings back 1M pieces and one piece per installment.
- **An installment works in the job's folder**: the prompt says the working folder, and that the job's files never go next to the task and handoff files (in the same test, the first chapter was written into Quotient's own folder of the installment).
- The demo's nights show their pieces. README EN/IT.

## [1.2.0] - 2026-10-19

Published for a few minutes as 1.1.10 and renamed: the versions go up to 9 in each place, so after 1.1.9 comes 1.2.0 (and after 1.9.9, 2.0.0). Nothing else changed.

### Added

- **The ceiling of each limit in the line** (`limits.show_top`, on; the user's request): after the share left, the tokens left of the whole window, `81% left (~26M of ~32M wt)`, Italian `resta 81% (~26M su ~32M wt)`, in Hermes' line and in Claude Code's status line. The ceiling is 100 times how much 1% holds, the same estimate the quotes use; the number falls toward zero as the window is used. `config limits.show_top 0` shows the tokens left alone, as in 1.1.8.

### Changed

- **A clearer demo** (`docs/demo.svg`, Italian `docs/demo.it.svg`; the user found the old one not clear enough): one big job in three phases named at the top: 1 the quote, in a choice window with three levels (total, time, share of the 5 hours and of the week) and then the pace, with the second window of installments; 2 the installments, night by night; 3 the bill, real cost and time against the quote and what is left of the 5 hours and of the week, in percent and in tokens of each ceiling.
- The picture of the limits (`docs/limits-left.svg`) writes the share left and the tokens left of the ceiling inside the bars. README EN/IT, site.

## [1.1.9] - 2026-10-19

### Changed

Asked by the user on 19/10/2026 ("the forecast is always wrong"). The author's 58 measured jobs showed where the misses came from: a chat job where the user wrote nothing during the work cost about x0.56 its raw quote (12 jobs), a chat job where the user wrote during the work, mostly adding tasks, about x1.49 (27 jobs). One factor learned from both was wrong both ways.

- **The chat factor learns from clean jobs only** (`learn_clean_only`, on; `clean_max_turns` 1). A clean job is a chat job with at most one turn (replies counted apart with ASIDE are not turns). Installments keep their rules: their turns are runs. Walk-forward on the author's jobs with the real code: the clean jobs' typical miss went from 60% to 43% and their lean from x0.65 to x1.01 (11 jobs: a hint, not a proof); the jobs with additions are missed more (126% to 157%), which is why the next point matters.
- **A task added during a job gets its own quote** (`requote_on_addition`, now on; it was off in 1.1.8).
- **New users start from x0.58** (`start_factor`): what the 49 clean jobs of `docs/evidence` cost against their raw quotes; until there are 5 clean jobs, rows at this factor fill the gap, instead of the shared average (which had too few jobs). With a learned factor those 49 jobs were within 33% on the median, against 75% raw. `config start_factor 0` brings back the shared average.
- The medium band (hermes branch, `learn_mid_min`) also learns from clean jobs only.
- **A start by type of work** (`start_factors`: code x0.70, research x0.35, other x0.58; texts 1.0) and **the rule for texts on at 27 weighted tokens per final word** (`writing_wt_per_word`, was off): a quote with `kind=<type>` starts from its type until there are 5 clean jobs of that type, then learns from them. From 64 clean jobs (docs/evidence and 15 new ones).
- **Checked on new tasks, paid with API credits** (`docs/evidence/results-1.1.9.json`, the new section of `quote-accuracy.md`): on 12 tasks never used to set the starts, the typical miss was 12% (7 of 12 within 30%) against 136% with 1.1.8's start; then 30 more new tasks as a confirmation: 27% (15 of 30 within 30%) against 111%, texts 17%, research 16%, code 58% (quoted too high). Both batches: 22% on 42 jobs. Small jobs in fresh sessions: a good sign, not a proof.
- README EN/IT: what 1.1.9 changes in the learning; under the picture of the limits, that its numbers come from a Max 5x plan and that Anthropic can change the limits at any time. Site: version, and how the factor starts.

Tested and not kept: estimating the number of steps instead of the tokens. The cost follows the steps closely (on the author's jobs, with the true number of steps, the typical miss would be 39%), but asked through the API to foresee its steps for the 49 test tasks, Claude missed them by about 50%, and steps times the cost of a step missed the cost by 40-46%, worse than a learned factor (33%).

## [1.1.8] - 2026-10-19

### Added

Five settings from what nine small jobs taught on 16/10/2026: each was done in a new Claude Code session, as a new user, with nothing added halfway, and its real cost was set against its quote (code: the raw quote held, x0.73; texts: 4 times under; one web research: x0.41; the same job done again: within ±10%; a quote in a new session: about 70,000 weighted tokens). Each setting is off (0) by default.

- **The rule for texts** (`writing_wt_per_word`, 50 suggested). The texts were quoted about 4 times under their cost (10 to 19 weighted tokens per final word in the quotes, 49 to 56 measured): a text comes out as output (weight 5) and then is re-read in the chat at every call after it. With the key on, step 1 of the protocol says to count that many weighted tokens per word of the final text, with its margin (half of it to 1.1 times: 25 to 55), and why; `quote-table --words <n>` adds a line with what the rule gives, and when the biggest level is under the margin it shows nothing but a note to estimate again. With 50, the two texts measured would have been quoted at about 44,000 (881 words, cost 49,571) and 254,000 (5,073 words, cost 257,043).
- **The web searches' second model** (`note_web_haiku`, 1 = on). Claude Code's web searches also run haiku, which is not in the session's log: about 12% of the session at list prices on the one research job measured. With the key on, Quotient counts a job's web searches, and the closing line of a research job (or of a job that searched) and the report of a finished research job in installments say that this cost is not in the measure.
- **One line for a small job** (`small_quote_line`, 1 = on). With the key on, a quote asked for a job under the threshold is one line (work, chat part, total, time, shares) with no table and no choice window, the end of the reply does not send it back as incomplete, and the first-use questions wait for the first job above the threshold. When the reply after a one-level quote does the work and ends with a `JOB:` line but writes no choice, that one level counts as chosen and the job is measured (in the tests of 17/10/2026 one job of 22 came back with only `JOB: CLOSE` and went unmeasured).
- **The margin** (`margin_percent`, 15 suggested). With the key on, the closing line of a job and the report of a finished job in installments say a miss under that many percent is within the margin, since the same job done again varies by about ±10%.
- **A quote for a task added to a job** (`requote_on_addition`, 1 = on). Until now the protocol said only that writing during a job adds to its cost. With the key on, a paragraph (ADDITIONS) says that a task added to a job, while it is open or right after it, gets a quote of its own before it is done: a new QUOTE line closes the job so far and the addition is measured against its own quote (finish what was chosen first when you can; when the new part cannot be told apart, quote what is left with it). The line of the open job reminds it only where it already says how to answer about something else (the job's first message, and after a reply counted apart), so the line of every message does not grow.

- **How accurate are the quotes** (`docs/evidence/`): 50 jobs done on purpose in fresh sessions as a new user, 9 on 16 October and 41 on the evening of 17 October 2026 with the five settings above on (code, bug fixes, texts, web research, additions halfway, every task done twice), with the method, a table of every job, what the numbers do not say, and `results.json`. The quotes were mostly too high (work x0.58 the raw quote): new code x0.86, bug fixes x0.55, web research x0.39, texts x0.60 with the rule at 50 per word (they cost 23 to 49 per word, so 30 to 35 may fit better; without the rule they were 4 times too low). The same job done again: within ±10% in 13 of 21 pairs. A quote in a new session costs about 65,000 weighted tokens, one line or table alike. Linked from the README ("How accurate are the quotes").

Two more, asked by the user on 19/10/2026, both on for everyone:

- **The tokens left in each limit** (`limits.show_left`, on). The line at each message (Hermes) and the status line (Claude Code) say, after the share left, how many weighted tokens are left: `5-hour: 19% used, 81% left (~26M wt)`, `week: 5% used, 95% left (~277M wt)`. It is the share left times how much 1% holds, from the same estimates the quotes use (measured on the PC, or the shared size of the plan until then), so it falls as the limit is used and agrees with the quotes' shares. Rounded (`~26M`, `~4.5M`, `~812k`) because it is an estimate; shown only for a window whose size is known. `config limits.show_left 0` turns it off. A picture in the README shows it (`docs/limits-left.svg`, Italian `docs/limits-left.it.svg`).
- **The limits read every minute** (`limits.every` 60, was 600). Each step of the percentage is caught within a minute, so the size of 1% is measured between two steps instead of across ten minutes of work. A reading spends no tokens: it is Claude Code's own `/usage`, in a process apart (about 4 seconds), and only when a message or a hook asks. `config limits.every 600` brings back the old pace.

And one more, from a test on the author's own jobs:

- **Installments can learn from all your jobs** (`learn_rate_all`, off by default). The user asked to check the estimates against the jobs already measured: a walk-forward test on the author's 51 jobs, each one estimated only with the jobs finished before it (45 of them with at least 5 before), compared the method of 1.1.7 with no correction, one median of all the jobs before, a correction by size and a median that weighs recent jobs more. For chat jobs no method was better in a stable way (the gains changed sign as soon as a few jobs were left out), so nothing changes for them. For installments, learning from all the jobs (chat jobs and installments, the last `history_window`, without `learn_min_raw`, `learn_max_speed` and the types) brought the typical miss from 48% to 34% and the lean from x1.41 under the real cost to x1.06, and it was at least 22% better in each of six checks (later jobs only, without the jobs measured wrong, and so on). Learned from installments alone, the factor came from a few big book jobs that cost less than quoted and was applied to smaller jobs that cost more. Only 13 installments (8 better, 5 worse): a hint, not a proof, so it stays off until the user turns it on (`config learn_rate_all 1`). The report and the quote say when the installments learn from all the jobs.

### Fixed

- **No limits without the status line.** Claude Code without Quotient's status line (the Claude desktop app, `claude -p`, or a user who did not set it up) read the limits only while a job was open: a new user's first quote had no shares of the 5 hours and the week, and the line could not say the tokens left. Found in a test as a new user on 19/10/2026. Now each message with no job open starts a reading in the background too, at most every `limits.every` seconds, as in Hermes; not when the status line gave them in the last 10 minutes. No message waits for it and it spends no tokens.

## [1.1.7] - 2026-10-16

### Added

- **The 5-hour limit of each plan in the shared average** (the user's request: so other people confirm the limit of each plan). The shared line also carries `per_point_5h`, how many weighted tokens 1% of the 5 hours holds on this PC, rounded to 3 significant digits, only when learned from the user's own readings (never the plan's value sent back) and only in the range 1,000 to 100,000,000 (the 5 hours hold about a tenth of the week: 409,000 against 3.58 million on the author's PC). The service takes it, keeps it in a new column (`server/migrate-1.1.7.sql`) and publishes, for each plan with 30 jobs that sent it, the median with its middle half, like the week, in keys of their own (`jobs_5h`, `per_point_5h`, `p25_5h`, `p75_5h`): old lines are still accepted, the averages already published do not change, and a 1.1.6 copy reads the file as before. A new user of that plan starts from it for the 5 hours too (in the quotes, the share of the 5 hours, and the line at each message, which says it is not measured here yet), until their own readings are enough. It is said as an estimate taken from other users, with its margin: Anthropic does not publish the limits and changes them (it doubled Claude Code's 5-hour limits on 6 May 2026). A service not updated yet answers `400` to the new field: the line goes again as a 1.1.6 service takes it (plan and the week), then with the five fields only. `/token-quotient:share`, the README, PRIVACY.md, the site and the service's page say it.

### Fixed

- **A message waited for the limits.** In Hermes, with no job open, the hook before each message read the limits itself (`claude -p /usage`, about 4 seconds) once every 10 minutes, and the message waited. In Hermes' logs of 12-15 October 2026 the hook reached its 20-second limit 14 times and the message went without its line. Now no hook waits for `/usage`: with no job open too, the reading runs in a separate process at the usual pace (`limits.every`, 10 minutes), and at most one is started per interval, even before it writes anything. The line shows the last reading saved; the new one reaches the next message. The check of the measures against the week waits for its reading the same way. Commands run by hand (`report`, `limits`, `tick`, `quote-table`) still read in the foreground when they need fresh numbers.
- **Good and max came out the same.** With the medium band on (`learn_mid_min`), a quote from `learn_min_raw` up was corrected to at least `learn_min_raw` x the medium factor: on the author's numbers every quote from 1 million to about 1.7 million came out 1.75 million (on 16/10/2026 a good level of 1.1 million and a max of 1.6 million both did). Now, from `learn_min_raw` up to a new setting, `learn_blend_raw` (3,400,000 by default), the corrected estimate follows a straight line from `learn_min_raw` x the medium factor to `learn_blend_raw` x the main one, and from there up the main factor alone, as before: no jump at either end, always rising with the raw estimate (so two levels never come out the same), and big jobs go back to their own factor. On the author's numbers 3.4 million is twice the quote the main factor alone takes to give what the band gives at 1 million (1.72 million): the line rises 0.71 wt for each raw wt, and what it adds to the main factor shrinks evenly from 731,000 wt at 1 million to nothing at 3.4 million. If the factors change so much that the line would rise less than half as fast as the main factor, it is made longer by itself; with the main factor larger than the medium one the line rises faster than the factor and there is no jump back. On the author's data (factor x1.0165, medium band x1.7476), raw → corrected, before and after:

  | raw | before | after |
  |---|---|---|
  | 0.9M | 1,572,803 | 1,572,803 |
  | 1M | 1,747,558 | 1,747,558 |
  | 1.1M | 1,747,558 | 1,818,744 |
  | 1.6M | 1,747,558 | 2,174,673 |
  | 2M | 2,032,951 | 2,459,416 |
  | 3M | 3,049,426 | 3,171,274 |
  | 5M | 5,082,377 | 5,082,377 |
  | 10M | 10,164,755 | 10,164,755 |

  The line in `quote-table`, the protocol and the README say the new rule.
- The README showed `@@TESTCOUNT@@` instead of the number of tests (since the 1.1.6 merge). Now 346 tests, 31 of them new in `tests/test_v117.py`, one of which checks the README, the privacy page and the site for the version and for placeholders.

### Changed

- **A shorter line at each message, with the same measures.** The line keeps the version, the limits, the factor, the CHAT PART and the open job; it drops what does not change from message to message or is worked out elsewhere: the threshold, the explanation of the medium band, the steps and the working time per million (quote-table works them out), the typical miss (in the report), the margin and the points of the size of 1% (in the report), and the "Big job: quote first" sentence (in the protocol). The sentence on how to answer about something else (`ASIDE`) comes at the first message of a job and after a reply counted apart, not at every message. Measured on a copy of the author's data, in a long chat (characters, notices shown once left out):

  | | before | after |
  |---|---|---|
  | Claude Code, no job | 1,052 | 394 |
  | Claude Code, job open (first message / after) | 1,467 | 776 / 626 |
  | Hermes, no job | 490 | 215 |
  | Hermes, job open (first message / after) | 741 | 466 / 324 |

  The protocol (Claude Code and Hermes) says where the CHAT PART and the shares of the limits come from now.

### Checked

- **Anthropic's limits, against its own pages** (the user's request). Eight official pages read on 16/10/2026 (support.claude.com, claude.com/pricing, code.claude.com, anthropic.com): usage depends on the model, the length and complexity of the chat, the tools and the effort; claude.ai, Claude Desktop, the phone and Claude Code draw from the same limits; Pro, Max 5x and Max 20x are given only as multiples of the 5-hour session ("no fixed message count"), with no numbers of tokens or messages and no multiple for the week. Nothing in the README is contradicted. One sentence is not confirmed by the pages: Claude Code's documentation lists `/usage` among the commands that "may generate requests" in the background, while the README says it spends no tokens; it is left as it is until it is measured.

## [1.1.6] - 2026-10-16

The user's idea: with more ways to see what a job costs and how big the limit is, Quotient learns much faster, in very few uses. Seven of them.

### Added

- **Claude Code's own telemetry as a second measure** (`telemetry on|off|status`, off by default). Claude Code can send its own counters of tokens and cost (OpenTelemetry). `telemetry on` prints the exact lines for the `env` block of `~/.claude/settings.json` (metrics only, OTLP over HTTP with JSON, to `127.0.0.1:4318`, every 30 seconds, as deltas, no events, no account ids); `--write` puts them there, after a copy of the file; `telemetry off --write` takes them out. A small receiver (`scripts/telemetry.py`, standard library only), started in the background at the start of a session, listens on this PC only and keeps numbers only in `~/.quotient/otel.jsonl`: tokens by type, cost, model, kind of call (main, subagent, auxiliary), session and time; never a text, an e-mail or an id. One receiver at a time (the port is the lock), and it stops by itself after 2 hours without data (`config telemetry.idle_minutes`). Each finished Claude Code job and each installment is set against it once its data has arrived; when the two measures differ by more than 25% on 100,000 weighted tokens or more (`telemetry.percent`, `telemetry.min_wt`), Claude tells the user once. The report shows the comparison and the calls on the side ("auxiliary": titles, summaries) that only the telemetry sees. The factor never changes by itself.
- **The costs others already work out.** Hermes keeps its own estimate of each chat's cost: Quotient now records its growth with the tokens (`usd` in `hermes.jsonl`), and the report sets it against the weighted tokens and against Claude Code's own cost of the installments (`total_cost_usd`, now also with the tokens by type of each installment), with the prices Hermes' costs imply (output and cache read as multiples of input) against Quotient's weights. Far apart beyond x1.25: the report says so; the weights change only by hand (`config weights.<name>`).
- **The cost the status line gets** (`cost.total_cost_usd`, kept when it changes, numbers only): the cost of a job in its session, a third measure in the report.
- **The limits read every minute during a job.** While a job or an installment is open, the limits are read every 60 seconds (`config limits.job_every`) instead of every 10 minutes, in a separate process so no message waits: more points, the size of the limit learned in fewer uses. An installment reads them from a thread while it works.
- **The plan in the setup window**: Pro, Max 5x, Max 20x, other or "I don't know" (`setup --plan`, `plan-changed --plan`). The shared line carries the plan only if the user chose one, and how many weighted tokens 1% of the week holds on this PC (3 digits, when known). The shared service gives back the size of 1% of the week by plan: a new user starts from the one of their plan, said as an estimate with the middle half of its users as margin, until their own readings are enough. The service takes the old five-field lines too, and a client meeting a service not updated yet sends the line again without the new fields.
- **The work in packages** (the user's idea). Past each million of work of a chat job, the agent writes `PROGRESS: n%` and Quotient keeps a package: work, time, progress. The whole job is the cost so far divided by the progress (the time likewise), with a margin from how wrong the PROGRESS lines were on the jobs before (10 points until 3 jobs have it) and at least the spread of the packages; the note to the agent, the new quote halfway and the installments' report and notification show it. Each installment is a package. When a job closes, Quotient keeps how far each PROGRESS line was from the truth (`progress_check`), and the report shows it.

### Checked, not changed

- **Decimals of the percentages: none.** 254 readings of the limits on the author's PC (from `/usage`, the API headers and Claude's own lines) are all whole numbers, so the margin of one point per window stays.
- **The real prices.** On the author's data (55 Hermes chats fitted exactly, and Claude Code's `total_cost_usd` of 37 installments, estimate/real median 1.000): a cache read costs 0.05 x input, not 0.1 x as Quotient weighs it, so jobs with much re-reading weigh more than they cost; output 5 x, cache writes 1.25 x (5 minutes) and 2 x (1 hour) as weighed. The weights are left as they are (they are the plan's own ratios, not certain): the report shows the prices implied, and `config weights.cache_read 0.05` is the user's choice. Installments with web searches cost up to 23% more than their tokens.
- **Hermes' hidden calls** (the user's hint: the size of the limit halved from 10/10, the day Hermes was installed). Hermes keeps its calls on the side only inside a turn; on the author's PC its command approvals (444, Opus), compressions of long chats (21), titles (24), web guard (94, Haiku) and images (about 435) since 10/10 are kept nowhere: about 4 to 6 million weighted tokens on 274 million of Hermes, about 2%. The report says it, and the check against the week names it as a possible part of a gap. It does not explain the halving: the 5-hour windows after 10/10 with mostly Claude Code held 254,000 to 283,000 weighted tokens per 1% (Hermes alone 350,000 to 450,000; before 10/10, 651,000 to 839,000), and the week per 1% went from 3.84 to 3.22 million (-16%) against about -50% for the 5 hours.

## [1.1.5] - 2026-10-16

### Fixed

- **A complete quote in Hermes was called incomplete.** The check of a quote (1.1.3) looked only at the last message of Hermes' reply. In Hermes the table of the quote and the clarify window come in the messages before, and the QUOTE line in the last one, after the work: so a complete quote was reported as incomplete at the next message. The check now also reads the reply's earlier messages and the choices of its clarify windows, from Hermes' session store, read-only, between the start of the reply and its end (`reply_texts`); if the store cannot be read, it checks the last message as before. PRIVACY.md says so.
- **A chat compressed in the middle of a job.** A job's chat part is what re-reading, at each step, what the chat held when the job started cost. When the chat was compressed (Hermes) or compacted (Claude Code) while the job ran, a step re-read less from then on, but Hermes kept counting the size from before: on 16/10/2026 a job measured 0.42 of its estimate instead of about 0.8, and the factor learned it. Hermes now counts reply by reply: a reply whose steps sent less, on average, than the job's starting size counts that, the smallest so far (`ctx_floor`; the whole prompt, so a cache gone cold is not taken for a compression). Claude Code counted nothing after a compaction, and all of it again once the chat had grown back: each call now counts up to the shortest prompt so far.
- **`fix chat <job>`.** `fix list` finds the jobs measured before, whose chat was compressed while they ran, and `fix chat` works their chat part out again: Claude Code exactly, from the transcript; Hermes, which keeps no numbers call by call, as an estimate from Quotient's log of its counters (each row weighed by its time inside the job). A copy first, and `fix undo`.
- The line of the factor in `quote-table` lacked a semicolon before the medium band.

### Docs

- The README (English and Italian), read word by word as a new user would, against the code:
  - the second window of the setup also asks about long chats (keep them, or let them compact themselves), not only about the shared average;
  - the pace options as the code makes them: with one or two levels 2 or 3 days, with three 3 or 5 days, with four 3, 5 or 7 days and no "apart"; "in a new chat" takes the place of the last option when the chat is long;
  - `fix chat <job>` in the table of commands and in the repairs, and `fix list` finding the jobs whose chat was compressed while they ran;
  - privacy: in a reply that gives a quote, Quotient reads Claude's text and the choice window (since 1.1.3), and in Hermes also the reply's earlier messages (1.1.5), only to check the quote; it never reads the user's messages ("never the text" said too little). Also in PRIVACY.md and on the site;
  - Quotient's rules at the start of a session are about 9,900 characters, roughly 2,800 tokens (the README still said 5,900 and 1,700);
  - the number of automatic tests.
- The site's link to the Hermes setup pointed to a section that does not exist (`#hermes-agent-too`); it now opens "Quick start: Hermes Agent". In this changelog, 1.1.3 links to its commit (it has no GitHub release, so the old link led nowhere), and 1.1.4 has its link.

## [1.1.4] - 2026-10-16

The user asked what was left to make the estimates as good as they can be. Four things. Three more came from using Quotient through Hermes (the last three under Added).

### Added

- **A factor for each type of work.** Code, writing and web research go wrong in different ways (15/10/2026: a check of a book's facts with web searches, estimated 1.6M, cost 4.4M). The QUOTE line takes a type, `kind=code|writing|research|other`, chosen by the agent; `quote-table`, `rate new` and `rate apart` take `--type`. Each finished job keeps its type. A type uses its own factor once it has 3 finished jobs of its kind, chat or installments (`config type_min_jobs`); before that, the general factor. The report shows the factor of each type with how many jobs it has. Jobs measured before 1.1.4 count as `other`.
- **A new quote halfway, made by Quotient.** Past the first million weighted tokens of work of a job (`config requote.after`), the agent writes a `PROGRESS: <n>%` line in its replies. When what is left by that line differs from what is left of the corrected quote by more than 30% (`config requote.percent`), Quotient makes a new quote: a table with the rest by the quote and at the job's own pace, its chat part, time, and share of the 5 hours and of the week. At the next message the agent must show it once and ask whether to go on as planned, go on with a smaller level, or stop. It is made once per job and kept in the job (`requote`), and the line at the close says how near it came to the real work; the report lists these new quotes.
- **The same for installments.** At the end of each installment, when the installments' own PROGRESS says the rest will cost more than 30% above what the plan leaves, the notification and the report give the new numbers (what is left, how many more installments, share of the week, time) and ask whether to go on, make the installments bigger (`rate set --daily`) or stop. Each new quote is kept in the job (`requotes`) and becomes the plan the next installments are checked against.
- **The guided repair: `fix`.** `fix list` shows what looks wrong in the measures: a job that looks split in two (a small job, under a quarter of the next one's work, ending at most 30 minutes before another job of the same chat starts: `config fix.gap_minutes`, `fix.small_share`), and the measures that do not match the week (the check of 1.1.1). `fix merge <a> <b>` joins two jobs into one, `fix exclude <job>` takes a job out of the factor (`--why` keeps the reason), `fix undo` takes the last repair back. Jobs are named by their number in the report or by a short key. A copy of `jobs.jsonl` is made first (in `~/.quotient/fix/`), nothing is deleted (jobs taken out or joined go to `jobs-excluded.jsonl`), every repair is written in `fix.jsonl` with the factor before and after. A split job is told once at the next message; the agent proposes the command and runs it only with the user's yes. The check against the week now proposes its `fix exclude` too.
- **The environment of each job.** Each closed job and each installment keeps the names of what was around it: Claude Code's enabled plugins, MCP servers and hooks (the name of the script a hook runs, never its arguments or settings), and Hermes' plugins, MCP servers and hooks from its config. Names only, never secrets. When they change (a plugin installed or removed), Claude tells the user once, and the report shows the jobs before and after the change apart (their factor, and the cost of 1M weighted tokens of work), so you can see what a plugin saves or costs. Once 3 jobs finished after the last change, each of them counts twice in the factor (`config env.min_jobs`, `env.weight`): the factor follows what a job costs now, without forgetting the older ones.
- **Work done elsewhere at the same time.** Each closed job and each installment records what other sessions spent while it ran (other Claude Code chats and installments, Hermes chats). When it is at least 50,000 weighted tokens and 5% of the job, the line at the close and the installment report say it: it is not in the job's cost, but it is in the limits. Use Quotient cannot see (claude.ai, the phone) is not in it.
- Hermes: the type in the QUOTE line, the PROGRESS line and the new quote halfway (shown once), the notices of a split job and of a changed environment.
- **Claude Code runs started from Hermes count in the job** (`claude_runs`, off by default). A SessionStart hook (`claude-link`, and the plugin's own SessionStart) records which Hermes chat started each Claude Code session, from the `HERMES_SESSION_ID` Hermes passes to everything it starts. When a quoted job closes, what those sessions spent while it was open (helpers included) is added to its cost and work, reported apart ("of which ... Claude Code runs"), and the factor learns from the whole; the quote protocol asks to put those runs in the estimate. Installments are left out (their run drops `HERMES_SESSION_ID` and carries `QUOTIENT_JOB`); sessions seen at their start without a Hermes id (scheduled tasks, the user's own chats) never count. `claude_runs_marker` also counts the `claude -p` sessions never seen at their start, by the first words of their prompt. They are not counted again in the work done elsewhere.
- **Which jobs teach the factor** (`learn_min_raw`, `learn_max_speed`, off by default): chat jobs quoted under `learn_min_raw` are left out (installments always teach), and so are jobs whose work ran faster than `learn_max_speed` wt a second, a measuring error rather than a job. The speed is the chat's own: Claude Code runs work in parallel. The number of jobs shown with a factor is of the jobs that teach it.
- **A factor of their own for medium quotes** (`learn_mid_min`, off by default): chat jobs quoted from `learn_mid_min` up to `learn_min_raw` learn their own factor, A chosen level under `learn_min_raw` is corrected with it (smaller quotes too, which teach no factor), and from `learn_min_raw` up the corrected estimate never falls under the one just below it, so a bigger quote is never corrected to less. Jobs quoted in Hermes use it too; the Hermes line shows it. `quote-table` and the stopwatch use it too. Under `learn_min_raw` the medium factor is the same for every type of work: the types learn only from the jobs that teach the factor.

### Fixed

- **Hermes' calls in the background were not counted.** Since 10/10/2026 the size of 1% of the 5 hours learned on the author's PC was about half of before, and Hermes was suspected of counting less than the truth through its cache (1-hour writes weighed as 5-minute ones). Checked on a copy of the data: the cache is not the cause (Hermes writes 5-minute caches unless its config says `cache_ttl: "1h"`, and its own cost estimate prices them at 1.25 x input, as Quotient does). But Hermes keeps its calls in the background (`background_review`) out of its chats' totals, which are what Quotient read: they were 8.8% of all of Hermes' Claude use from 10 to 15 October (0% to 18% per chat), so the cost read from Hermes was about 10% lower than the truth. Quotient now reads them from Hermes' `session_model_usage` (Claude's only, never twice if a chat's totals already hold them), in the measures of the limits and in the jobs measured in Hermes; what they spent before the update stays out, so it does not land at one moment. The report's Hermes section says how much of the week they were.
- **Hermes' cache from its config.** When Hermes' config says `prompt_caching: cache_ttl: "1h"`, its cache writes are weighed as 1-hour ones (2 x input); otherwise as 5-minute ones, as before.
- The halving itself is not explained by Hermes: on the same data, the windows after 10/10 with mostly Claude Code cost as few weighted tokens per 1% as those with Hermes only (about 250,000 to 290,000, against 650,000 to 840,000 before 10/10). Quotient does not change its weights for it; the check of a change of plan (1.1.2) is where such a change shows.

## [1.1.3] - 2026-10-15

### Added

- **The quote worked out by Quotient** (the user: "it is not you who must remember, it must be Quotient"). Two quotes had reached the user without the time of their levels. The new command `quote-table --raw essential=<n> good=<n> max=<n> [--kind rate] [--lang it|en]` works out every number of each level: the corrected work, the re-reading of the chat (in Claude Code from the chat's own transcript, in Hermes from `--context`), the total, the expected time, and the share of the 5 hours and of the week with what would be left; then the pace options, what the free field is for and the week. The protocol tells the agent to run it and copy the table as it is.
- **A quote is checked.** When a reply has a QUOTE line, the end of the reply looks for the time and the shares of each level in its text and in the window's level options. If something is missing, at the next message the agent is told, first of all, to say the quote was incomplete and what it lacked, and to give it again in full. Only what Quotient knows is checked (no time is asked before 3 jobs were timed, no shares before the limits are known). In Claude Code and in Hermes.
- **As many levels as the size calls for.** From 1 to 4 levels, by the corrected size of the biggest: up to 300,000 weighted tokens one (`good`), up to 1 million two (`good max`), up to 5 million three (`essential good max`), above that four (`essential good full max`), always from the smallest. The sizes are settings (`config levels.one|two|three`); `quote-table` tells the agent when it gave a different number or order. The QUOTE line takes 1 to 4 levels with short names, as before.
- **Paces by size, with a time.** The pace question has 4 options at most (the window adds its free field by itself): all today, in a new chat when the chat is long, apart now (not for the biggest jobs), and plans in days, 2 or 3 for a small job, 3, 5 or 7 for a big one, each with the amount a day of each level, the time, how long an installment takes and its share of the limits. The time of the plans is `config rate.time` (03:00).
- **A choice of the user's own.** In the window's free field the user can write their own level, for example a mix of two: the agent estimates it and writes `CHOICE: custom=<n>` (or a short name with its estimate), and the job is measured against that estimate (`custom: true` in its line). For the pace they can write how many days, how much a day and at what time: `rate new --pace "5 giorni alle 2:00"` reads the days, the amount a day and the time (`parse_plan`; also "3 days, 200k a day, at 2am", "a mezzanotte"), and `--at HH:MM` gives the time apart. `rate once` and `rate schedule` without `--time` use the job's time (`rate schedule` falls back to 03:00).
- Hermes: the same rules for the clarify window (4 choices at most, plus Other), `CHOICE: custom=<n>`, and the check of the quote.
- The README (English and Italian) says how many levels and paces a quote offers, what the free field is for, and the new commands.

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

[1.2.1]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.2.1
[1.2.0]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.2.0
[1.1.9]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.9
[1.1.8]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.8
[1.1.7]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.7
[1.1.6]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.6
[1.1.5]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.5
[1.1.4]: https://github.com/Korvonordico/quotient-claude-tokens/releases/tag/v1.1.4
[1.1.3]: https://github.com/Korvonordico/quotient-claude-tokens/commit/6a1dd3d
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
