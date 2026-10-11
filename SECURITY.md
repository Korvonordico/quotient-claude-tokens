# Security policy

## Supported versions

Fixes go into the latest release only. Update the plugin before reporting, if you can.

| Version | Supported |
|---|---|
| 0.9.x, the latest | yes |
| older | no |

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**, or go straight to [the private report form](https://github.com/Korvonordico/quotient-claude-tokens/security/advisories/new).

Include:

- what the problem is and what an attacker could do with it;
- how to reproduce it;
- the Quotient version (`python scripts/quotient.py --version`) and your operating system.

The report stays private between you and the maintainer until a fix is out. Quotient is maintained by one person, so there is no fixed response time; you will get an answer in the report itself. When the fix is released, the advisory is published, with credit to you unless you prefer otherwise.

If the private form is not available, open an issue that only asks for a private contact, without any details of the problem.

## What matters most

Quotient runs on your computer with your permissions, so these parts are the most sensitive:

- the hooks and scripts that run at every session, message and reply (`hooks/`, `scripts/`);
- installments: Windows Task Scheduler tasks that wake the PC and run Claude Code (`claude -p`) with the `acceptEdits` permission mode in the job's folder;
- reading Claude Code's login to ask Anthropic for the plan limits (`scripts/limits_live.py`);
- writing to `~/.claude/settings.json` (the status line and `autoCompactWindow`);
- anything that could send more than the one line of numbers described in [PRIVACY.md](PRIVACY.md);
- the shared-average service in `server/` and what it accepts.

Problems in Claude Code, Hermes Agent, Cloudflare or GitHub themselves should go to those projects.
