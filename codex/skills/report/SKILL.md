---
name: report
description: Token Quotient report - estimates against real costs of the jobs done in Codex, and how the error is changing. Use when the user asks for the Token Quotient or Quotient report, or how accurate the quotes are.
---
How to run Token Quotient: its folder is the plugin's root, three folders above this file (this file is
`<root>/codex/skills/report/SKILL.md`). Run `python3 "<root>/scripts/quotient.py" <command> --codex` (on Windows
`py -3 "<root>\scripts\quotient.py" <command> --codex`, or `python` if `py` is missing). Always add `--codex`: it
keeps Codex's numbers apart from Claude Code's. Token Quotient keeps its data in `~/.quotient/codex`, outside the
project: if the sandbox refuses a command, ask the user to allow it.

1. Run `<command>` = `report`. Show its output to the user as it is, in a code block.
2. Then, in the user's language, add at most two sentences on what it says: is the estimate getting closer to
   the real work or not, how many jobs it is based on, and how much of the cost was re-reading the chat. Do not
   round the numbers.
3. If the user asked for the page or the charts, also run `report --html`: it writes a page in Token Quotient's
   folder and opens it. Say where it is.
