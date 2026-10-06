# Template: code review — a codebase reviewed in installments

This template comes with Quotient. It tells each installment HOW to work; the job itself (which code, what
to look for, how deep, in which language the report is written) is written by the user below "The job".

## How every installment works
1. Read HANDOFF.md first. Never review again an area it marks as done.
2. Work in small, finished steps and update HANDOFF.md after each one: what is done, what remains, where to
   resume, and the line `PROGRESS: <n>%` computed from the plan (below), not guessed.
3. Keep the context small: read one area at a time; search (grep) before you open whole files.
4. Do not change the code unless "The job" says so. A review reports; it does not fix.

## The order of the work
1. **Map** (first installment): `PLAN.md` lists the areas (folders or modules), their size in lines, and
   the order of review (the riskiest first: input handling, money, security, data that can be lost). Each
   area is worth its share of the lines; the final report, 10%.
2. **One area at a time**: findings in `FINDINGS.md`, each with file and line, what is wrong, a concrete
   case that shows it (input → wrong result), how serious it is (critical / high / medium / low), and how
   sure you are (proven by running it / read in the code / a suspicion).
3. **Check each finding** before it stays: try to prove it wrong. A finding you cannot show with a concrete
   case is marked as a suspicion, never as a bug. If the tests can run, run them and say so.
4. **Report**: `REPORT.md`, in the language of the job: the most serious findings first, then by area;
   what was not reviewed and why; what to fix first.

## Finished
Write `JOB DONE` as the first line of HANDOFF.md only when every area of the plan is reviewed, every finding
is checked, and REPORT.md exists.
