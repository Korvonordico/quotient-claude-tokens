---
description: Set Quotient up, or change its settings (threshold, weekly reserve, language, what the PC does after installments)
allowed-tools: Bash(sh:*)
---
!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" config`

Above are Quotient's current settings. Open the choice window (AskUserQuestion) in the user's language with four questions, each also allowing a free answer, and show the current value in each:
1. 'Soglia'/'Threshold': from how many weighted tokens a job gets a quote first (100.000 = often, 300.000 = default, 1.000.000 = only huge jobs).
2. 'Riserva'/'Reserve': share of the weekly limit kept free for normal use (10%, 20%, 30%).
3. 'Lingua'/'Language' of the report (italiano, English).
4. 'Il PC'/'The PC' for scheduled installments: wake it and put it back to sleep / wake it and hibernate it / wake it and leave it on / never touch the PC (installments run only when it is already on). Putting it back to sleep happens only when nobody is using it.

Then save with `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" setup --threshold <n> --reserve <n> --lang it|en --wake yes|no --after sleep|hibernate|nothing` and tell the user, in one line, what is now set.

Then open a second choice window with one question, 'Media condivisa'/'Shared average' (current value: `share.enabled` above, on by default; the environment variable QUOTIENT_SHARE=0 also turns it off): take part in the shared average, which helps the program give everyone better first quotes (it shares only the rounded raw estimate and real cost, the model family and the Quotient version of each finished job; no dates, no text, no ids) / do not take part (the shared average is still used); the free field lets them write anything else. Save with `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" setup --share yes|no` and say in one line what is set, and that `/quotient:share` shows exactly what is sent.
