# Governance

How decisions get made in VW Group Connect, who makes them, and what happens
if the person making them steps back. Short and honest — this is a one-person
project, not a foundation.

---

## The model: single maintainer

VW Group Connect is maintained by one person — **Prash
([@its-me-prash](https://github.com/its-me-prash))**. He has the final say on
scope, on what gets merged, and on what ships. [`.github/CODEOWNERS`](.github/CODEOWNERS)
reflects this literally: until brand captains are recruited, the maintainer
owns every file.

That is a "benevolent dictator" setup, and it's deliberate. A small
integration chasing constant Volkswagen backend changes moves faster with one
clear decision-maker than with a committee. It also means there is no SLA, no
guaranteed review time, and no promise that any given feature will land.
Patches and patience travel further than demands.

---

## How decisions get made

1. **It starts in the open** — a GitHub [issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)
   or [discussion](https://github.com/its-me-prash/vwgroup-connect-ha/discussions).
   Bug reports, feature requests, Vehicle Data Scout findings and real-car test
   results all feed the same queue.
2. **Evidence beats assertion.** Claims about official-app behaviour want
   captured traffic or a diagnostics attachment behind them, not a hunch. The
   maintainer-side rules in [`CONTRIBUTING.md`](CONTRIBUTING.md) (privacy,
   `[Inference]` markers, self-checks before replying) are binding on the
   maintainer too.
3. **The maintainer calls it.** After weighing the report, the code, and the
   house rules, Prash decides. Larger direction lives in
   [`docs/ROADMAP.md`](docs/ROADMAP.md), but the roadmap is a plan, not a
   promise.
4. **Reporters get a real answer.** No issue is closed silently. Contributors
   are answered warmly and specifically — every commenter on a thread, not just
   the author — and credited (see below).

There is no vote and no tie-break procedure, because there is no tie to break.

---

## Earning influence

Influence here is earned by showing up, not by being appointed. The concrete
first rung is documented in [`BRAND_CAPTAINS.md`](BRAND_CAPTAINS.md):

- File at least one **Vehicle Data Scout** report, run the integration on a
  real car for a couple of weeks, and say you'll captain a brand.
- A **Brand Captain** is then added as a co-owner for that brand's API client
  in [`.github/CODEOWNERS`](.github/CODEOWNERS) — so they're auto-requested on
  relevant PRs — and thanked by name in release notes. No coding required;
  live-testing and verifying is the job.

Beyond that, the path toward **co-maintainership** is the same one every small
project runs on: land good, focused pull requests over time. A contributor who
consistently respects the house rules — one PR = one concern, tests for new
behaviour, privacy first, green CI — and shows they understand the codebase
earns review trust, then merge trust. If the project grows enough to need it,
co-maintainer access is extended to someone who has already proven all of that
in practice. It is a matter of demonstrated track record, not a form to fill in.

---

## Release & versioning discipline

The rules that keep releases predictable are not up for negotiation per-PR:

- **SemVer** ([Semantic Versioning 2.0.0](https://semver.org/)), post-1.0.0
  strict: PATCH for fixes, MINOR for new entities/services/brands, MAJOR for
  breaking changes. Betas ship as `X.Y.0bN` on the HACS beta channel.
- **PR-first, not direct-to-main.** Contributions come as pull requests and
  merge only with green CI. The gate runs `ruff`, `mypy` (strict flags), the pytest
  suite with a coverage floor, and JSON validation; a change under
  `custom_components/` that omits a `CHANGELOG.md` entry is rejected by the
  `changelog_check.yml` workflow. Full procedure in
  [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md).
- **No fixed cadence.** A release goes out whenever a coherent, atomic batch is
  on `main` and CI is green — in busy stretches that is roughly a release a
  day, but nothing is owed on a timetable.
- **Every release credits its reporters.** Contributors are listed in
  [`CONTRIBUTORS.md`](CONTRIBUTORS.md) and thanked in the relevant
  [`CHANGELOG.md`](CHANGELOG.md) entry.

**Security** decisions follow their own track: report privately via
[GitHub Security Advisories](https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new),
never a public issue. [`SECURITY.md`](SECURITY.md) states the one place we do
commit to a target (acknowledge within 72 hours, fix high-severity within 14
days).

---

## Continuity — if the maintainer steps back

This is a one-person project, so it is worth being plain: if Prash stops
maintaining it, no one is contractually next. But the project is built so it
can outlive any single person.

- It is licensed **[GNU AGPL-3.0-or-later](LICENSE)**. Anyone may fork it and
  continue, subject to the mandatory-attribution and name/trademark terms in
  [`ATTRIBUTION.md`](ATTRIBUTION.md).
- There are **no external runtime dependencies** — the CARIAD client is
  bundled — so a fork has the whole surface in one repo, nothing to reassemble.
- A successor should start with [`CONTRIBUTING.md`](CONTRIBUTING.md) (especially
  *Adding a new brand* and the privacy rules), [`RELEASE_PROCESS.md`](RELEASE_PROCESS.md),
  and [`docs/ROADMAP.md`](docs/ROADMAP.md). Between them they describe how the
  code is laid out, how it ships, and where it was heading.

If a wind-down ever becomes real, the intent is to hand the project to an
active co-maintainer or clearly point the README at a maintained fork rather
than let it rot silently. That is an intention, not a guarantee.

---

*Governance questions that aren't security-sensitive belong in a
[Discussion](https://github.com/its-me-prash/vwgroup-connect-ha/discussions).
This document describes how the project is run today; it will change as the
project does.*
