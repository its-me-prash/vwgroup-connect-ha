# Deep Audit — daernsinstantfortress / cupra_we_connect

> Date: 2026-05-25 · Reviewer: claude-opus
> Repos audited:
> - HA integration: github.com/daernsinstantfortress/cupra_we_connect (104⭐, Apache-2.0)
> - Backing pip pkg: github.com/daernsinstantfortress/WeConnect-Cupra-python

## TL;DR — Architecture vs us

**Same backend, same auth client, different endpoint strategy.**

| Aspect | Daern | Ours |
|---|---|---|
| Backend | OLA (`ola.prod.code.seat.cloud.vwgroup.com`) | OLA (same) |
| Auth IDP | `identity.vwgroup.io` (EU) | Same |
| Auth client_id | `3c756d46-...@apps_vw-dilab_com` (browser-IDP) | Same |
| User-Agent | `CUPRAApp%20-%20Store/20220503 CFNetwork/...` (iOS) | `OLACupra/2.15.0 (Android 12; sdk_gphone64_x86_64; Google) Mobile` |
| OLA 2026-05-20 fix | Same 4 headers (PR #43, 2026-05-21) | Same 4 headers (v2.4.1, 2026-05-25) |
| Endpoint strategy | **Granular** (many small endpoints) | **Aggregated** (`/v5/mycar` + supplements) |
| Brand coverage | CUPRA only | 7 brands (SEAT + CUPRA + 5 others) |
| HA integration depth | Thin (pip lib does most work) | Native (entity registry, services, scout pipeline, repairs) |

## Endpoint coverage comparison

### Daern uses (9 endpoints)

```
GET /v1/user/{user_id}/vehicle/{vin}/capabilities
GET /v1/vehicles/{vin}/climatisation/status
GET /v1/vehicles/{vin}/mileage
GET /v1/vehicles/{vin}/parkingposition
GET /v2/vehicles/{vin}/climatisation/settings
GET /v2/vehicles/{vin}/status
GET /vehicles/{vin}/charging/settings
GET /vehicles/{vin}/charging/status
GET /vehicles/{vin}/connection
```

### We use (9 endpoints — different mix)

```
GET /v5/users/{user_id}/vehicles/{vin}/mycar       ← aggregated, most data
GET /v1/vehicles/{vin}/parkingposition             ← match
GET /v1/vehicles/{vin}/ranges                      ← we have, daern doesn't
GET /v2/vehicles/{vin}/status                      ← match
GET /v1/vehicles/{vin}/charging/status             ← match (different path prefix)
GET /v1/vehicles/{vin}/charging/info               ← we have, daern doesn't
GET /v2/vehicles/{vin}/climatisation               ← we use aggregate; daern splits status+settings
GET /v1/vehicles/{vin}/maintenance                 ← we have, daern doesn't
GET /v1/vehicles/{vin}/remote-availability         ← we have, daern doesn't
```

### Endpoints daern has that we DON'T

| Endpoint | Likely contains | Action |
|---|---|---|
| `/v1/vehicles/{vin}/mileage` | Dedicated mileage/odometer | **A1**: check if our `/v5/mycar` already returns this; if not, add as fallback |
| `/vehicles/{vin}/connection` | Connection-status (12V, modem) | **A2**: check if our `readiness` endpoint covers same data |
| `/vehicles/{vin}/charging/settings` (no version prefix) | Charging-rate, target SoC, etc. | **A3**: check if shape differs from our `/v1/.../charging/info` |

### Endpoints we have that daern DOESN'T

- `/v5/users/{user_id}/vehicles/{vin}/mycar` — aggregated multi-domain endpoint (this is why we don't need their granular endpoints)
- `/v1/vehicles/{vin}/ranges` — dedicated ranges
- `/v1/vehicles/{vin}/maintenance` — service intervals
- `/v1/vehicles/{vin}/remote-availability` — capability gate

**Conclusion**: our endpoint strategy is more efficient (fewer HTTP calls per poll cycle) but might miss specific fields that daern's granular endpoints surface uniquely. Worth a single-vehicle real-world compare-fixture run to confirm.

## Element parsers — what they have

Daern has 18 element classes:
```
access_status, battery_status, charging_settings, charging_status,
climatization_settings, climatization_status, connection_status,
controls, engine_state, error, generic_capability, generic_settings,
odometer_measurement, parking_position
```

Worth scanning each for fields we don't parse (Phase B work):

| Element | Worth investigating? |
|---|---|
| `engine_state.py` | Yes — we have engine state but might be missing fields |
| `connection_status.py` | Yes — corresponds to our `readiness` endpoint, compare |
| `odometer_measurement.py` | Yes — dedicated mileage shape |
| `controls.py` | Yes — command-execution helpers, see if patterns differ |

## Architectural patterns worth borrowing

### 1. Observable/Addressable pattern

Daern uses `weconnect_cupra.addressable.AddressableObject` everywhere — a strict observable pattern that emits events on state changes. We have something similar via HA's coordinator + `async_set_updated_data`, but their finer-grained emit-on-leaf-change might inspire entity update granularity improvements.

**Action B1**: review `addressable.py` for entity-update efficiency ideas. Low priority — only if HA users report stale-entity issues.

### 2. Fetcher + retry strategy

Their `Fetcher` class encapsulates the HTTP layer with auth + retry logic in a way that's a bit cleaner than our `_request()` override pattern (which is now distributed across base + seat_cupra).

**Action B2**: low-priority refactor opportunity if our request layer grows another override (e.g. for VW EU when their headers get enforced).

### 3. `fixAPI` flag pattern

Daern's API constructor has `fixAPI: bool = True` — apparently they normalize backend responses when known-bad shapes come back. We do this inline per parser without a unified switch.

**Action B3**: nice-to-have refactor for v3.x — formalize an "API normalization" toggle for users who want raw passthrough.

## What's NOT worth borrowing

- Daern's User-Agent is **iOS** (`CUPRAApp%20-%20Store/20220503 CFNetwork/...`) — that's weird for an Android app. Our `OLACupra/2.15.0 (Android 12; ...)` is more honest about what we are.
- Their codebase is much larger because the pip lib does almost everything; the HA integration is thin. Our integrated design is more HA-native and easier to maintain.

## Final assessment

Daern is a **good colleague to mirror for header values + scout signals** (already added them as 3rd OLA source in v2.4.2). For architectural inspiration, they're roughly on par — we trade their endpoint-granularity for our endpoint-aggregation efficiency. The few endpoints they have that we don't are worth a focused field-coverage audit (action items A1-A3).

**Estimated effort to apply A1+A2+A3 + element field-coverage audit**: 4-6h for a v2.5.0 PR. Not P0 since users aren't complaining, but a good v2.5.0 polish item.
