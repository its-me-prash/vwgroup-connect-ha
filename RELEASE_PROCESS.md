# Release process

> Single canonical release procedure. Follow this for every tag.

Last updated: 2026-04-26 — current version: v1.8.0

---

## When to release

Release whenever a coherent, atomic batch of changes is on `main` and CI is
green. There is no fixed cadence. The session-based roadmap
([`docs/ROADMAP.md`](docs/ROADMAP.md)) maps each upcoming session to a
target version.

---

## Daily: `[Unreleased]` block

Every commit that touches `custom_components/` needs an entry in the
`[Unreleased]` block of `CHANGELOG.md`. The `changelog_check.yml`
workflow enforces this.

```markdown
## [Unreleased]

### Added | Changed | Fixed | Removed
- short description of the change
```

Commit-message prefix conventions are listed in
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## Semver

We are now on **post-1.0.0 strict semver**:

| Change | Bump | Example |
|---|---|---|
| Bug fix only | PATCH | 1.8.0 → 1.8.1 |
| New feature, new entity, new brand, new endpoint | MINOR | 1.8.0 → 1.9.0 |
| Breaking change (removed entity, renamed config key, dropped HA version) | MAJOR | 1.x → 2.0.0 |

Pre-1.0.0 historical correction is documented at the top of
`CHANGELOG.md`. **Do not refer to it for new releases.**

---

## Step by step

### 1. Bump `manifest.json`

```jsonc
// custom_components/vag_connect/manifest.json
{
  "version": "1.9.0"   // bump per semver
}
```

### 2. Finalise `CHANGELOG.md`

Replace the `[Unreleased]` heading with the version + ISO date and add a
new empty `[Unreleased]` block above it.

```markdown
## [Unreleased]

## [1.9.0] - 2026-MM-DD

### Added
- Capability-aware entity creation (#56)
```

### 3. Mirror release notes into all 8 READMEs

If the release adds visible features, update the roadmap table in
`README.md` and the seven translations to mark the version as `✅ Done`.

### 4. Commit + push

```bash
git add custom_components/vag_connect/manifest.json CHANGELOG.md README*.md
git commit -m "chore: release 1.9.0"
git push origin main
```

### 5. Tag

```bash
git tag -a v1.9.0 -m "VW Group Connect v1.9.0"
git push origin v1.9.0
```

The `release.yml` workflow then automatically:

- builds `vag_connect.zip`
- generates release notes from the matching `CHANGELOG.md` section
- creates the GitHub Release attached to that tag
- HACS picks it up within ~6 hours

### 6. Notify users

If the release fixes user-reported bugs (issues with comments from
non-maintainer accounts), add a short comment on each affected issue
linking to the release page. **Address every commenter, not just the
issue author.**

---

## Pre-release checklist

```bash
python -m pytest tests/                                   # all green
python -m ruff check custom_components/                   # 0 errors
python -m mypy custom_components/vag_connect/ \
  --ignore-missing-imports \
  --disallow-untyped-defs \
  --disallow-incomplete-defs \
  --warn-return-any                                       # 0 errors
python -m pytest tests/ \
  --cov=custom_components/vag_connect \
  --cov-fail-under=65                                     # ≥65 % coverage
```

These match the CI gates exactly.

---

## Hotfix procedure

If a release breaks setup for users:

1. Open a `bug` issue describing the regression.
2. Fix on a short-lived branch.
3. Bump PATCH (e.g. 1.9.0 → 1.9.1).
4. Squash-merge to `main`.
5. Tag immediately.

Avoid amending or force-pushing to existing tags. Tags are immutable.

---

## Version history

Full history: [`CHANGELOG.md`](CHANGELOG.md)

| Version | Date | Type | Notes |
|---|---|---|---|
| 1.8.0 | 2026-04-26 | MINOR | Foundation Fix — 7 P0 audit findings + CUPRA flash |
| 1.7.0 | 2026-04-26 | MINOR | Škoda complete rewrite + car-friendly translations |
| 1.6.x | 2026-04-25 | MINOR | SEAT/CUPRA 9-endpoint expansion, Lock platform |
| 1.5.x | 2026-04-23/24 | PATCH chain | Multiple auth fixes (Škoda, CUPRA) |
| 1.0.0 | 2026-04-12 | MAJOR | First stable, 7 brands, HACS-ready |
