---
description: Split a big job into installments with a spending cap per installment
argument-hint: [what the job is]
---
The user wants to do this job in installments: $ARGUMENTS

1. If the job is unclear, ask what it is and which folder it works in.
2. Estimate it and open the choice window (AskUserQuestion), in the user's language, with two questions: 'Livello'/'Level' (essential, good, max, each with its corrected estimate) and 'Ritmo'/'Pace' (installment plans that fit, e.g. 2 or 5 days with the amount per day). The free field lets the user write any pace, e.g. '50k a day'.
3. Write the job description to a file, then create the job:
   `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" rate new <short-name> --dir <folder> --task-file <file> --quote <raw estimate> --days <n>` (or `--daily <n>` for a pace per day).
4. Open a second window: 'Prima rata'/'First installment' (now; today at a time they write; tonight at 03:00) and 'Ogni giorno'/'Every day' (the daily time, free field). Then run what they chose: `rate run <name>` in the background, `rate once <name> --time HH:MM`, `rate schedule <name> --time HH:MM`. Scheduling creates a system task: it is the user's choice in the window that allows it.
