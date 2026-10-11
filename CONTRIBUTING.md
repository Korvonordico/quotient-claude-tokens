# Contributing to Quotient

Bug reports, quotes that were far off, documentation fixes and pull requests are all welcome. This page says how to run the tests, what the code expects, and how a change gets in.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md). Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Issues first

- **A bug**: open an issue with the bug form. Say what happened, what you expected, and how to reproduce it. Paste numbers and error messages, never chat text or anything private.
- **A quote that was far off**: that is useful data. Open a bug with the level you chose, the estimate and the real cost from `/quotient:report`.
- **A feature**: open an issue with the feature form before writing code, so we can agree on the shape first. Check [ROADMAP.md](ROADMAP.md) too.

## Project layout

| Path | What it is |
|---|---|
| `scripts/quotient.py` | the plugin itself: hooks, quotes, measuring, the report, installments (Python, standard library only) |
| `scripts/run.sh` | finds Python 3.8 or newer and runs `quotient.py`; the hooks and slash commands go through it |
| `scripts/hermes_source.py`, `scripts/hermes_hooks.py` | Hermes Agent: reading its token counters, and the shell hooks |
| `scripts/limits_live.py` | reads the plan limits from Anthropic |
| `hooks/hooks.json` | the Claude Code hooks: `SessionStart`, `UserPromptSubmit`, `Stop`, `PreCompact` |
| `commands/` | the slash commands: `/quotient:setup`, `report`, `rate`, `share`, `help` |
| `templates/` | ready-made ways of working for installment jobs: book, research, code review |
| `server/` | the shared-average service (Cloudflare Worker, JavaScript), see [server/README.md](server/README.md) |
| `data/` | the average shipped with the plugin |
| `tests/` | the Python tests |
| `.claude-plugin/` | the plugin and marketplace manifests |

## Run the tests

From the repository folder:

```sh
python -m unittest discover -s tests
```

You need Python 3.8 or newer and nothing else. The tests run offline, in temporary folders, so they do not touch your own `~/.quotient`.

If you change `server/`, also run the service's tests (Node.js; CI uses Node 22):

```sh
node --test server/test/stats.test.mjs
```

GitHub Actions runs both at every push and pull request: the Python tests on Ubuntu and Windows with Python 3.9 and 3.13, the service's tests on Ubuntu with Node 22. A pull request needs them green.

## Code style

- **Standard library only.** Quotient runs inside other people's Claude Code with whatever Python they have: no third-party packages, and keep the code working on Python 3.8.
- **Follow the code around you.** Functions have a docstring that says what they do; comments say why, often with the real case that led to the change.
- **A fix comes with a test** that fails without it. Tests describe the case they protect in their docstring.
- **Every token Quotient adds to a chat is paid by every user**, at every step: its rules at the start of a session and its line at each message are re-read all the time. Keep any text added there as short as you can, and check its weight in the report.
- **Two languages.** User-facing text exists in English and Italian (the report strings in `quotient.py`, README.md and README.it.md). Change both.
- **Plain words for users.** Short sentences, numbers with their unit, no jargon where a common word works.
- **Privacy is part of the change.** If a change touches what Quotient reads, keeps, sends or fetches, update [PRIVACY.md](PRIVACY.md) (both languages) and the "Everything Quotient runs, sends and fetches" list in both READMEs in the same pull request. The shared line (`v`, `q`, `family`, `estimate`, `actual`) is fixed: the service refuses anything else, so changing it needs an issue first.

## Pull requests

1. Fork the repository and branch from `main`.
2. Keep one change per pull request, as small as it can be.
3. Run the tests.
4. Update README.md and README.it.md if behavior or commands change, and add a line under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).
5. Open the pull request and fill in the template.

Commit messages are one line that says what changes for the user, like the history: `Quotient 0.9.7: the PC goes back to sleep only if the installment woke it`.

Leave the version number as it is: the maintainer sets it when releasing. It lives in two places that must match, `.claude-plugin/plugin.json` and `VERSION` in `scripts/quotient.py`.

## License

By contributing, you agree that your contribution is released under the [MIT License](LICENSE), like the rest of Quotient.
