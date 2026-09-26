# App Atlas — Škoda (MyŠkoda)

> **Auto-generated** by `.github/workflows/app-atlas-builder.yml` ·
> Last refreshed: 2026-09-26

## Identity

| Field | Value |
|---|---|
| Android package ID | `cz.skodaauto.myskoda` |
| Expected backend | `mysmob` |
| OLA enforcement known? | No (not observed yet) |

## Configured sources (fallback chain)

| Source | Configured value |
|---|---|
| APKMirror | `skoda-auto-as/myskoda` |
| Uptodown | `cz-skodaauto-myskoda` |

## Current version

| | |
|---|---|
| Latest version-name | `8.17.0` |
| Source that responded | `google_play` |
| Previously cached version | `8.16.0` |
| Changed since last run? | **YES** |


## Discovered via APK extraction (Phase A.2)

_(Empty — Phase A.2 APK extraction not yet run for this brand, or last attempt failed. See `app_atlas/apk_extractor.py`.)_

## Cross-version diff

**8.15.0 → 8.16.0 (versionCode 260821007)** — strictly additive. Nothing was
removed or renamed, and auth, IDP, headers, Firebase config and the MQTT push
setup are all byte-identical, so no existing call path changes behaviour.

| Area | Delta |
|---|---|
| `api/vN` routes | 5 added, 0 removed |
| Predictive-maintenance body | `+predictions[]` |
| Capability ids | `+PUBLIC_API_KEY_MANAGEMENT`, `+BATTERY_HEALTH_STATE` |
| New module | Laura agent, over SSE |
| Auth / IDP / headers / Firebase / MQTT | unchanged |

**The five new routes:**

| Method | Route |
|---|---|
| `GET` / `POST` | `api/v2/public-api-keys` |
| `DELETE` | `api/v2/public-api-keys/{id}` |
| `GET` | `api/v1/vehicle-information/{vin}/battery-health` |
| `GET` | `api/v2/garage/vehicles/{vin}/users/guests/invitations` |
| `POST` | `api/v2/predictive-maintenance/vehicles/{vin}/predictions/{type}/reset` |

`public-api-keys` is the app minting keys for a caller that is not the app —
the first sign of a first-party public API surface, and worth watching whatever
we do with it.

## Action items

| # | Item | Why | State |
|---|---|---|---|
| 1 | Probe `vehicle-information/{vin}/battery-health` on a tester car | It is a read, it is per-VIN, and battery health is the one number owners ask for that we cannot currently answer | open |
| 2 | Add `BATTERY_HEALTH_STATE` + `PUBLIC_API_KEY_MANAGEMENT` to the capability-id table | The table mirrors the app's enum; a missing id reads as "unknown capability" and unknown must never hide a control | open |
| 3 | Pick up `predictions[]` in the predictive-maintenance body | Additive field on a body we already parse — cheap, and it is where the per-service due dates moved | open |
| 4 | Leave the guest-invitation route alone | It writes to somebody else's access to the car; nothing about it belongs in an unattended integration | closed (won't do) |
| 5 | Watch `public-api-keys` | If this becomes a real first-party public API it changes what we should be building against, well before the mirror endpoints notice | standing |
| 6 | No auth work needed for 8.16.0 | IDP, headers and MQTT are unchanged — this bump breaks nothing we ship | closed |

---

_See [`README.md`](README.md) for atlas methodology and
[`LEGAL.md`](LEGAL.md) for reverse-engineering disclosure._
