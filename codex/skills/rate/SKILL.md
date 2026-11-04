---
name: rate
description: Split a big job into daily installments with Token Quotient, each done by `codex exec` and stopped at its spending cap. Use when the user asks for installments, a job "apart", or a job to run at night.
---
How to run Token Quotient: its folder is the plugin's root, three folders above this file (this file is
`<root>/codex/skills/rate/SKILL.md`). Run `python3 "<root>/scripts/quotient.py" <command> --codex` (on Windows
`py -3 "<root>\scripts\quotient.py" <command> --codex`, or `python` if `py` is missing). Always add `--codex`: it
keeps Codex's numbers apart from Claude Code's. Token Quotient keeps its data in `~/.quotient/codex`, outside the
project: if the sandbox refuses a command, ask the user to allow it.

1. If the job is unclear, ask what it is and which folder it works in.
2. Estimate the WORK of each level, then let Token Quotient work the numbers out:
   `<command>` = `quote-table --kind rate --raw essential=<n> good=<n> max=<n> --lang <it|en>`. Copy its table into
   your message as it is, and ask the user to choose a level and a pace (days, or how much per day, and a time).
3. Write the job description to a file, then create the job:
   `<command>` = `rate new <short-name> --dir <folder> --task-file <file> --quote <raw estimate> --days <n>`
   (or `--daily <n>` for a pace per day, `--at HH:MM` for the time).
4. Ask when the first installment runs: now (`rate run <name>` in the background), today at a time
   (`rate once <name> --time HH:MM`), or only every day at the planned time (`rate schedule <name>`). For the job in
   one go, now and apart from this chat: `rate apart <short-name> --dir <folder> --task-file <file> --quote <n>`.
5. Tell the user in one line: each installment runs `codex exec` in its folder (it can edit files there), Token
   Quotient measures it from Codex's log and stops it at its cap, and the report comes back at their next message.
   `rate status` shows the jobs; `rate stop <name>` stops one.
