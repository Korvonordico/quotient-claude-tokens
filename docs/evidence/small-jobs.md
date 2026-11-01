# Small jobs: what Quotient itself cost, and the 1.3.4 fix

Measured on 1 November 2026 with `claude -p` (Claude Code 2.1.x), model Sonnet 5.5, a new user (`--plugin-dir`,
`--setting-sources project`, empty `QUOTIENT_HOME`), paid with API credits. Each job: step 1 the task and a request for a
quote (without the plugin: "how many tokens will it cost?"), step 2 "the biggest level, all today" via `--resume`.

Note on the measure: the `total_cost_usd` of a resumed `claude -p` run is the cost of the whole session so far (checked
with three one-word turns: 0.0144, 0.0247, 0.0271 USD). The job's cost is the last step's total.

## Where Quotient's cost came from (1.3.3, one transcript read call by call)

1. The session-start protocol (~11,200 characters) was over what Claude Code shows of a hook (~10,000): it was cut and
   saved to a file, and the agent spent one more call reading it (~9,000 wt, about half of what the quote turn added);
   every later call re-read it twice (preview and file).
2. The full quote table, copied into the reply (output weighs 5).
3. The per-message line: 150 to 450 characters, negligible.
4. Texts and "other" quoted about half their cost: the chat part counted a job's steps as work / 30,000 alone, 0.31 times
   the real steps on the 107 jobs of this folder (median); 3 more steps give 1.0 times (typical miss 15%).
5. 4 jobs of 11 unmeasured: 3 ended with only `JOB: CLOSE`, 1 wrote `CHOICE: max` for a quote with only `good`.

## Results (4 small jobs: code, README, web research, sorting 40 files; 3 runs each = 12 per side)

| Side | Mean cost | Quote turn | vs no plugin | Typical estimate miss | Within ±30% | Measured |
|---|---|---|---|---|---|---|
| 1.3.4 | 0.082 USD | 0.031 USD | +9% | 31% | 5/12 | 12/12 |
| 1.3.3 | 0.110 USD | 0.052 USD | +47% | 35% | 5/12 | 5/12 |
| no plugin | 0.075 USD | 0.022 USD | - | 277% | 0/12 | - |

Real cost / estimate, by type (1.3.4 vs 1.3.3): writing 1.05-1.32 vs 1.92-2.44; other 0.55-0.86 vs 1.00-1.18; research
0.64-0.91 vs 0.84-1.55; code 0.45-0.58 vs 0.65-0.75 (code is quoted high by the agent itself; not corrected on 3 jobs).

Two bigger jobs (a 5-module package with 30 tests; a 10,000-word guide), first run per side: 1.3.4 0.52 USD, misses 4%
and 14%, measured 2/2; 1.3.3 0.74 USD, misses 64% and 33%, measured 0/2; no plugin 0.54 USD. With 2 jobs per side the
cost differences are mostly the jobs' own variation.
