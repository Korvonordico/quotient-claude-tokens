---
description: Split a big job into daily installments with a spending cap per day
argument-hint: [what the job is]
---
The user wants to do this job in daily installments: $ARGUMENTS

1. If the job or its size is unclear, ask the user one question at a time: what the job is, the folder it works in, how many days, and the cap per day in weighted tokens (or the total estimate, which gets divided by the days).
2. Write the job description to a temporary file, then create the job with:
   `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" rate new <short-name> --dir <folder> --task-file <file> --days <n> --daily <cap>` (add `--quote <total>` when there is a total estimate, so the final cost can be compared with it).
3. Tell the user how to run one installment now, and how to run one every day (`rate schedule <short-name> --time HH:MM`). Scheduling creates a system task: do it only if the user says yes.
