---
description: The shared average - exactly what Quotient sends, and turning sharing on or off (on, off)
allowed-tools: Bash(sh:*)
---
!`sh "${CLAUDE_PLUGIN_ROOT}/scripts/run.sh" share "$ARGUMENTS"`

Above is the state of sharing in Quotient. Tell the user, in their language and in a few plain lines: whether sharing is on or off, the exact line that is sent after each finished job (show it as it is), how many lines are waiting, that nothing else is sent (no dates, no text, no paths, no ids), and that the shared average is used either way. If it is on, say that `/quotient:share off` turns it off; if it is off, that `/quotient:share on` turns it back on. Link: https://github.com/Korvonordico/quotient-claude-tokens/blob/main/PRIVACY.md
