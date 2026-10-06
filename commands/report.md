---
description: Estimates against real costs, Quotient's own weight, and how the error is changing (add "page" for charts)
argument-hint: [page]
allowed-tools: Bash(sh:*)
---
!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" report`

Show the report above to the user as it is, in a code block. Then, in the user's language, add at most two sentences on what it says: is the estimate getting closer to the real work or not, how many jobs it is based on, and how much of the cost was re-reading the chat. Do not round the numbers.

If the user asked for the page or the charts ($ARGUMENTS says page, pagina, html, charts or grafici), also run `sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" report --html`: it writes the page in Quotient's own folder and opens it in the browser. Say where it is.
