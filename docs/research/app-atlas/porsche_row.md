# App Atlas — Porsche (My Porsche, rest-of-world)

> **Auto-generated** by `.github/workflows/app-atlas-builder.yml` ·
> Last refreshed: 2026-09-26

## Identity

| Field | Value |
|---|---|
| Android package ID | `de.porsche.one` |
| Expected backend | `ppa` |
| OLA enforcement known? | No (not observed yet) |

## Flavors

This is the rest-of-world My Porsche build — the one EU owners install.
North America runs `com.porsche.one`, tracked on [`porsche.md`](porsche.md).

At **20.26.37** (versionCode 188460) the two are the same code: the DEX
string-pool diff is empty apart from the package-name strings and one
Porsche-Card product-availability path, and the Firebase config is identical.
Both are polled anyway, so a future divergence shows up as two different
version rows rather than as nothing at all.

The build string names the flavour: the mirror listing for this package reads
`20.26.36-row+186611`, where the North-American APK reads
`20.26.37-pcna+188460`. The atlas records only the dotted part — a suffixed
string does not compare against a plain one, and that comparison is what stops
a lagging mirror from walking the brand backwards.

Sources: APKMirror has no slug here (the Porsche slug it does have serves the
NA package, and reusing it would report an NA version as this brand's), and
Google Play publishes no version for either Porsche package. APKCombo is the
only source that answers, and it currently lags a release behind.

## Configured sources (fallback chain)

| Source | Configured value |
|---|---|
| APKMirror | `(none)` |
| Uptodown | `(none)` |

## Current version

| | |
|---|---|
| Latest version-name | `20.26.38` |
| Source that responded | `apkcombo` |
| Previously cached version | `20.26.37` |
| Changed since last run? | **YES** |


## Discovered via APK extraction (Phase A.2)

_(Empty — Phase A.2 APK extraction not yet run for this brand, or last attempt failed. See `app_atlas/apk_extractor.py`.)_

## Cross-version diff

The 20.26.31 → 20.26.37 deltas are written up once, on
[`porsche.md`](porsche.md#cross-version-diff), because both flavors carry the
same code at 20.26.37 (verified by DEX string-pool diff — see Flavors above).
Copying the table here would give us two places to keep in sync and one of them
would quietly go stale.

Record ROW-specific findings here as soon as the two builds stop matching.

## Action items

_(Auto-flagged by the pipeline when new endpoints / headers / version-bumps suggest follow-up work.)_

---

_See [`README.md`](README.md) for atlas methodology and
[`LEGAL.md`](LEGAL.md) for reverse-engineering disclosure._
