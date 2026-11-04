---
name: setup
description: Set Token Quotient up in Codex, or change its settings (threshold, weekly reserve, language). Use after installing the plugin, or when the user asks to change Token Quotient's or Quotient's settings.
---
How to run Token Quotient: its folder is the plugin's root, three folders above this file (this file is
`<root>/codex/skills/setup/SKILL.md`). Run `python3 "<root>/scripts/quotient.py" <command> --codex` (on Windows
`py -3 "<root>\scripts\quotient.py" <command> --codex`, or `python` if `py` is missing). Always add `--codex`: it
keeps Codex's numbers apart from Claude Code's. Token Quotient keeps its data in `~/.quotient/codex`, outside the
project: if the sandbox refuses a command, ask the user to allow it.

1. Run `<command>` = `config` and show the current settings in one short list.
2. Ask the user, in their language, three questions in one message, each with the current value:
   - Threshold: from how many weighted tokens a job gets a quote first (100,000 = often, 300,000 = default,
     1,000,000 = only huge jobs).
   - Reserve: share of the weekly limit kept free for normal use (10%, 20%, 30%).
   - Language of the report and of the quotes (Italian or English).
3. Save the answers with `<command>` = `setup --threshold <n> --reserve <n> --lang it|en` and tell the user in one
   line what is now set.
4. Tell them, in one line each: the Token Quotient hooks run only after they trust them (`/hooks` in Codex); in Codex
   the numbers are estimates made with the price ratios of Claude's API; Codex jobs are never shared.
