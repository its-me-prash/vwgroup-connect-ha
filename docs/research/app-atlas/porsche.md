# App Atlas — Porsche (My Porsche, North America)

> **Auto-generated** by `.github/workflows/app-atlas-builder.yml` ·
> Last refreshed: 2026-09-26

## Identity

| Field | Value |
|---|---|
| Android package ID | `com.porsche.one` |
| Expected backend | `ppa` |
| OLA enforcement known? | No (not observed yet) |

## Flavors

My Porsche ships as two packages, and the atlas tracks both:

| Flavor | Package | Atlas page |
|---|---|---|
| North America (PCNA) | `com.porsche.one` | this page |
| Rest of world (EU included) | `de.porsche.one` | [`porsche_row.md`](porsche_row.md) |

At **20.26.37** (versionCode 188460) the two builds are the same code: a DEX
string-pool diff of both APKs comes back identical apart from the package-name
strings themselves and one Porsche-Card product-availability path, and the
Firebase config matches. So a finding verified on one flavor holds for the
other **at this version** — which is exactly why both are polled: the day the
builds diverge, the version pages diverge with them instead of the split
passing unnoticed behind a single row.

## Configured sources (fallback chain)

| Source | Configured value |
|---|---|
| APKMirror | `dr-ing-h-c-f-porsche-ag/my-porsche` |
| Uptodown | `(none)` |

## Current version

| | |
|---|---|
| Latest version-name | `20.26.38` |
| Source that responded | `apkmirror` |
| Previously cached version | `20.26.37` |
| Changed since last run? | **YES** |


## Discovered via APK extraction (Phase A.2)

_(Empty — Phase A.2 APK extraction not yet run for this brand, or last attempt failed. See `app_atlas/apk_extractor.py`.)_

## Cross-version diff

**20.26.31 (versionCode 183270) → 20.26.37 (versionCode 188460)**, verified by
walking the DEX with androguard (not a string grep) on both APKs. Holds for
`de.porsche.one` too — see Flavors above.

| Area | 20.26.31 | 20.26.37 | Note |
|---|---|---|---|
| `MeasurementType` enum | 86 members | 87 members | `+CHARGING_SESSION_HISTORY` |
| `CommandType` enum | 61 members | 62 members | `+DASHCAM`, `+SPIDERMAP`, `−CS_VOICE_MIMIC` |
| Manifest permissions | — | `+ACCESS_LOCAL_NETWORK` | the only permission change; it is what the dashcam talks over |
| Certificate pins | 10 | 11 | one added, none removed; the 10 existing pins are byte-identical |
| VICI BFF host | present | removed | signup/profile traffic no longer routes through it |
| `TRUNK_UNLOCK` | present, not surfaced | present, user-facing | the command itself is unchanged in both builds |
| Auth stack | — | unchanged | Auth0, `identity.porsche.com`, `my.porsche.com`, PPA route shapes and `X-*` headers all identical |

**`CHARGING_SESSION_HISTORY` payload** — one `HistoryItem` per session:

| Field | Shape |
|---|---|
| `id` | int |
| `startChargingDateTimeWithOffset` / `endChargingDateTimeWithOffset` | ISO-8601 with offset |
| `plugInDateTimeWithOffset` / `plugOutDateTimeWithOffset` | ISO-8601 with offset |
| `netDurationS` | seconds |
| `chargeType` | `AC` \| `DC` \| `AWC` \| `UNKNOWN` |
| `averageChargingPowerkW` / `peakChargingPowerkW` | float, kW |
| `totalChargedEnergykWh` | float, kWh |
| `startSoC` / `endSoC` | int, percent |

The app tells users that history older than 28 days is unavailable, so do not
expect the backend to answer for a longer window.

**`SPIDERMAP`** is an isochrone command (reachable-range polygon) and carries a
SPIN in its payload, which puts it in the same authorisation class as the other
SPIN-gated commands rather than with the plain reads.

**Attribution caveat.** The North-American line jumped 20.26.31 → 20.26.37 while the rest-of-world line was already at 20.26.36. Cross-checked against `de.porsche.one` 20.26.36: the dashcam capability, `ACCESS_LOCAL_NETWORK`, push-category subscriptions, the user-facing tailgate unlock, pickup & delivery and the contract renames were all in 20.26.36 already, i.e. 20.26.32–20.26.36 changes that are merely new to the NA line. Genuinely new in 20.26.37 (absent from ROW 20.26.36 too): the charging-history screen and its `CHARGING_SESSION_HISTORY` fields `plugInDateTimeWithOffset`/`plugOutDateTimeWithOffset`/`startSoC`/`endSoC`, the `SPIDERMAP` command, POI-sync refusal reasons, and homescreen layout editing.

## Action items

| # | Item | Why | State |
|---|---|---|---|
| 1 | Request `CHARGING_SESSION_HISTORY` alongside the other measurements and keep the raw response | The PPA measurement list is opt-in per key — a key we never name is a key we never see, however well it is documented | open |
| 2 | Map `HistoryItem` to the last-session fields that already exist in the models | The landing fields are there; nothing fills them for Porsche today | open |
| 3 | Leave `DASHCAM` alone | It is local-network video against the car's own hotspot, not a cloud read — outside what this integration does | closed (won't do) |
| 4 | Leave `SPIDERMAP` alone for now | Isochrone polygons need a SPIN per call and have no sensible entity shape | deferred |
| 5 | Watch the pin set, not just the version | Pins went 10 → 11 with no host change; a pin rotation is the cheapest early warning that a host is moving | standing |
| 6 | Re-check the two flavors on every minor bump | Identical at 20.26.37 is a measurement, not a promise | standing |

---

_See [`README.md`](README.md) for atlas methodology and
[`LEGAL.md`](LEGAL.md) for reverse-engineering disclosure._
