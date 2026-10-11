## What this changes

<!-- One or two sentences: what changes for the user, and why. Link the issue, e.g. "Fixes #12". -->

## How it was tested

<!-- What you ran, and what you checked by hand (a quote in Claude Code, an installment, Hermes Agent...). -->

- [ ] `python -m unittest discover -s tests` passes
- [ ] `node --test server/test/stats.test.mjs` passes (only if `server/` changed)

## Checklist

- [ ] A bug fix comes with a test that fails without it
- [ ] Python standard library only, still working on Python 3.8
- [ ] README.md and README.it.md updated, if behavior or commands changed
- [ ] PRIVACY.md updated, if this changes what Quotient reads, keeps, sends or fetches
- [ ] Any text added to every chat (the rules or the per-message line) is as short as it can be
- [ ] A line under "Unreleased" in CHANGELOG.md
