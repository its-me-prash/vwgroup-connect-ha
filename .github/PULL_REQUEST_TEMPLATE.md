<!--
Thanks for sending a patch — this integration is one person's spare-time
project, and a focused PR with the boxes ticked is the fastest path to merge.
Fill in the three short sections, then run through the checklist. The commands
match CI exactly, so if they pass locally the PR usually goes green.
-->

## Summary

<!-- One line: what does this PR do? -->

## What & why

<!--
What changed, and why. What was broken or missing before?
If you changed how a payload is parsed or how a command is sent, say what you
grounded it against — captured app traffic, a diagnostics dump, an issue. If a
path works but isn't semantically verified against the official app, mark it
`[Inference]` in the code (see CONTRIBUTING.md).
-->

## Linked issue

<!-- "Closes #123" ties this to a report. Small self-explanatory fixes can say "no issue". -->

Closes #

## Checklist

These run in CI on every PR to `main` — running them locally first keeps the round-trip short (see CONTRIBUTING.md → *Pull requests*):

- [ ] `python -m pytest tests/` passes (CI also enforces a coverage floor —
      the gate is `--cov-fail-under` in `.github/workflows/ci.yml`)
- [ ] `python -m ruff check custom_components/` is clean
- [ ] `mypy` strict is clean on `custom_components/vag_connect/` (full flags in CONTRIBUTING.md; CI runs the same checks)
- [ ] Added a `## [Unreleased]` entry in `CHANGELOG.md` — CI rejects a code change without one — and credited the work (yourself, plus the reporter if this fixes their issue)
- [ ] All `*.json` under `custom_components/` still parse (translations and `manifest.json` load at HA startup)

Review rules from CONTRIBUTING.md:

- [ ] New feature has tests — a new sensor needs a parser test **plus** an entity test; a new command needs a coordinator dispatch test
- [ ] Changed a user-facing string? Updated `strings.json` (the English source of truth) and mirrored it into **every** `translations/*.json`, in everyday driver vocabulary
- [ ] No new runtime dependencies — `manifest.json` `requirements` stays empty (we bundle our own CARIAD client)
- [ ] **No secrets in the diff** — no tokens, S-PIN, full 17-char VINs, user-IDs, e-mail, or exact GPS (round to 1 decimal), even from your own car (see CONTRIBUTING.md → *Privacy & data handling*)
- [ ] **Used an AI assistant on this?** Please say so — a `Co-Authored-By:` trailer, or one line in the description above. It is welcome here and it counts against nothing: it tells a reviewer which parts to read twice. A pull request has already arrived with tests its own checklist called passing that failed on the first run here, so knowing saves us both a round trip.
- [ ] One PR = one concern; commit messages use a `feat|fix|refactor|docs|test|chore|ci|i18n:` prefix

<!--
hassfest and HACS validation also run automatically. PRs merge against main with
green CI — no direct pushes to main. Thanks again.
-->
