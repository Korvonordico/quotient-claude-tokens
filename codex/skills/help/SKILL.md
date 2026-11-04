---
name: help
description: The list of Token Quotient's commands, with what each one does. Use when the user asks what Token Quotient or Quotient can do in Codex.
---
How to run Token Quotient: its folder is the plugin's root, three folders above this file (this file is
`<root>/codex/skills/help/SKILL.md`). Run `python3 "<root>/scripts/quotient.py" <command> --codex` (on Windows
`py -3 "<root>\scripts\quotient.py" <command> --codex`, or `python` if `py` is missing). Always add `--codex`: it
keeps Codex's numbers apart from Claude Code's. Token Quotient keeps its data in `~/.quotient/codex`, outside the
project: if the sandbox refuses a command, ask the user to allow it.

Run `<command>` = `commands` and show the list to the user as it is, in a code block, in the user's language
(translate it if it is not). Then add one line: in Codex the status line and the slash commands of Claude Code are
not there; these skills (report, setup, rate, help) take their place.
