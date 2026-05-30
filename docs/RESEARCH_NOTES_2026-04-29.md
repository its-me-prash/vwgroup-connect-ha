# Research Notes — 2026-04-29

> **Audience:** Contributors, AI tools resuming work without prior session
> context (fresh maintainer session).
>
> **Purpose:** Single archive of every verified live-API field name, every
> reference repo path, every Pattern observation that informed the v1.8.6 →
> v1.8.12 release sprint. **If you are continuing this project, start here.**
>
> **Status of every claim:**
>
> - ✅ **VERIFIED** — confirmed against live API response in a public issue,
>   or against open-source library source code (cited inline)
> - ⚠️ **HYPOTHESIS** — plausible but not yet seen in a live response;
>   marked explicitly so it doesn't drift into "fact" later
> - ❌ **DISPROVEN** — investigated and found false; kept here so future
>   research doesn't re-investigate

---

## 1. Where each brand's API lives (verified)

| Brand | Auth flow | Base URL | Source of truth |
|---|---|---|---|
| Volkswagen EU | IDK PKCE | `https://emea.bff.cariad.digital` | `robinostlund/volkswagencarnet` |
| Audi (EU) | IDK PKCE + AZS token | `https://emea.bff.cariad.digital` | `audiconnect/audi_connect_ha` audi_services.py |
| Audi (legacy AZS) | AZS endpoint | `https://emea.bff.cariad.digital/login/v1/audi/token` | audi_connect_ha #94 |
| Audi (myAudi app discovery) | — | `https://app-api.live-my.audi.com` (vgql GraphQL) | audi_connect_ha L51-282 |
| Škoda | IDK PKCE (proprietary) | `https://mysmob.api.connect.skoda-auto.cz` | `skodaconnect/myskoda` |
| SEAT / CUPRA | IDK PKCE (CUPRA also has client_secret) | `https://ola.prod.code.seat.cloud.vwgroup.com` | `WulfgarW/pycupra` |
| Porsche | Auth0 PKCE | `https://api.ppa.porsche.com` | `CJNE/pyporscheconnectapi` |
| VW US/CA | UUID-based VW NA Auth | `https://b-h-s.spr.{cc}00.p.con-veh.net` | `matpoulin/CarConnectivity-connector-volkswagen-na` |
| EU Data Act (Sep 2026+) | TBD | `https://eu-data-act.drivesomethinggreater.com` | `pycupra/eudaconnection.py` |

---

## 2. `carCapturedTimestamp` Pattern (the Multi-Brand Connection-State foundation)

**TL;DR:** Every modern VAG backend (mysmob, OLA, CARIAD-BFF) stamps a
`carCapturedTimestamp` field on every status sub-object. It records when
the *vehicle* sent the data, not when the *backend* responded. The freshest
timestamp across all sub-objects determines the vehicle's connection state:

```
age < 30 min  → online   (live, just heard from the car)
age < 24 h    → standby  (asleep but reachable via /wakeup)
age >= 24 h   → offline  (12V flat / underground / service mode)
```

### Verified shape per brand

#### Škoda mysmob — flat, top-level

✅ Source: `skodaconnect/myskoda` 9 model files all decorate
`field_options(alias="carCapturedTimestamp")` (`models/air_conditioning.py`,
`charging.py`, `status.py`, `driving_range.py`, `software_status.py`,
`departure.py`, `auxiliary_heating.py`, `chargingprofiles.py`, plus the v2
air_conditioning variant).

```json
{
  "carCapturedTimestamp": "2026-04-29T10:13:08.487Z",
  "overall": {...},
  "detail": {...}
}
```

Endpoints that carry it: `/api/v2/vehicle-status/{vin}`,
`/api/v1/charging/{vin}`, `/api/v2/air-conditioning/{vin}`,
`/api/v3/maps/positions/vehicles/{vin}/parking`,
`/api/v3/vehicle-maintenance/vehicles/{vin}`.

#### SEAT / CUPRA OLA — top-level on most endpoints

✅ Source: `tillsteinbach/CarConnectivity-connector-seatcupra` issue #109
(Rainer's CUPRA Born live dump 2026-03-27).

```json
"climatisationStatus": {
  "carCapturedTimestamp": "2026-03-27T12:42:30Z",
  "remainingClimatisationTimeInMinutes": 0,
  "climatisationState": "off"
}
"chargingSettings": {
  "carCapturedTimestamp": "2026-03-27T12:42:29Z",
  "maxChargeCurrentAC": "maximum",
  ...
}
```

#### VW EU CARIAD-BFF — TIEFER geschachtelt: `service.statusName.value.carCapturedTimestamp`

✅ Source: `robinostlund/volkswagencarnet` issue #921 (ID.4 2025 live dump
2026-02-16, Belgium user).

```json
{
  "access": {
    "accessStatus": {
      "value": {
        "carCapturedTimestamp": "2026-02-16T10:13:10.616Z",
        "overallStatus": "safe",
        ...
      }
    }
  },
  "charging": {
    "batteryStatus":   {"value": {"carCapturedTimestamp": "...", "currentSOC_pct": 25}},
    "chargingStatus":  {"value": {"carCapturedTimestamp": "...", "chargingState": "off"}},
    "chargingSettings":{"value": {"carCapturedTimestamp": "...", "targetSOC_pct": 80}},
    "plugStatus":      {"value": {"carCapturedTimestamp": "...", "plugConnectionState": "disconnected"}}
  },
  "climatisation": {
    "climatisationSettings": {"value": {"carCapturedTimestamp": "...", "targetTemperature_C": 20.5}},
    "climatisationStatus":   {"value": {"carCapturedTimestamp": "...", "climatisationState": "off"}},
    "windowHeatingStatus":   {"value": {"carCapturedTimestamp": "...", "windowHeatingStatus": [...]}}
  },
  "measurements": {
    "rangeStatus":              {"value": {"carCapturedTimestamp": "...", "totalRange_km": 83}},
    "odometerStatus":           {"value": {"carCapturedTimestamp": "...", "odometer": 18249}},
    "fuelLevelStatus":          {"value": {"carCapturedTimestamp": "...", "currentSOC_pct": 25, "carType": "electric"}},
    "temperatureBatteryStatus": {"value": {"carCapturedTimestamp": "...", "temperatureHvBatteryMin_K": "278.65"}},
    "temperatureOutsideStatus": {"value": {"carCapturedTimestamp": "...", "temperatureOutside_K": "278.15"}}
  },
  "readiness": {
    "readinessStatus": {
      "value": {
        "connectionState": {
          "isOnline": true,
          "isActive": false,
          "batteryPowerLevel": "comfort",
          "dailyPowerBudgetAvailable": true
        },
        "connectionWarning": {
          "insufficientBatteryLevelWarning": false,
          "dailyPowerBudgetWarning": false
        }
      }
    }
  }
}
```

`/parkingposition` is a **separate endpoint** with **flat** structure:
```json
{"data": {"lon": 4.x, "lat": 50.x, "carCapturedTimestamp": "..."}}
```

#### Audi CARIAD-BFF — identical to VW EU (same backend, same shape)

✅ Source: `audiconnect/audi_connect_ha` audi_models.py L51-282. Endpoint
URL identical: `https://emea.bff.cariad.digital/vehicle/v1/vehicles/{vin}/selectivestatus`.
Inheritance pattern in our code: `AudiClient(VWEUClient)` doesn't override
`get_status` — automatically benefits from VW EU code.

### Important format quirks

- **String vs datetime:** `volkswagencarnet`'s lib pre-parses timestamps to
  Python `datetime` objects before storing. Live JSON is always strings.
  Our helper `compute_connection_state` accepts both.
- **Missing field is allowed:** `skodaconnect/myskoda` PR #565 documented
  that `carCapturedTimestamp` is NOT guaranteed (e.g.
  `SoftwareStatus.NO_UPDATE_AVAILABLE` doesn't include it). Our helper
  returns `(None, None)` instead of fabricating a value (Hard Rule #8).
- **Multiple sub-objects, freshest wins:** different sub-systems update at
  different cadences (charging more often than door state). Take the max.
- **Naive timestamps:** some backends return tz-naive — assume UTC.
- **HTTP 207 Multi-Status:** VW EU `selectivestatus` returns 207, not 200.
  Handled in `cariad/api/base.py:_request` (status list `200, 201, 202, 207`).

### Implementation reference in this repo

`custom_components/vag_connect/cariad/_util.py:compute_connection_state(*sub_objects)`
— recursive walk through dicts and lists, brand-agnostic.

---

## 3. Per-brand JSON pitfalls (Live-API field name divergence)

**Why this matters:** different VAG backends use confusingly similar but
different field names. Pre-v1.8.9 we had several parser bugs because we
copy-pasted CARIAD-BFF field names into the OLA parser. The lesson: every
field name should be sourced from a verified live response, not assumed.

### CUPRA / SEAT OLA — verified divergent fields

✅ Source: pycupra/connection.py + CC-seatcupra #109 (Rainer's CUPRA Born live dump).

| Field meaning | OLA actual | What we used pre-v1.8.9 | Fix in |
|---|---|---|---|
| Charging power kW | `chargedPowerInKw` (with "d") | `chargePowerInKw`, `chargePower_kW` | v1.8.9 |
| Remaining charge time | `remainingTimeInMinutes` or `remainingTime` | `remainingTimeToFullyChargedInMinutes`, `remainingChargingTime` | v1.8.9 |
| Charge target % | `targetSoc_pct` (lowercase soc) | `targetSOC_pct`, `targetStateOfChargeInPercent` | v1.8.9 |
| Charging state | `state` or `status` | `chargingState` | v1.8.9 |
| Charging type | `type` | `chargeType`, `chargingType` | v1.8.9 |
| Doors per position | `status.doors.{frontLeft,frontRight,rearLeft,rearRight}.{locked,open}` | `doorsOpenedCount`, `doorClosedLeftFront` | v1.8.9 |
| Windows per position | `status.windows.{frontLeft,...}` (string `"closed"`/`"open"`) | `windowsOpenedCount` | v1.8.9 |
| Trunk | `status.trunk.{open,locked}` (nested object) | `trunk: "OPEN"` (flat string) | v1.8.9 |
| Hood | `status.hood.open` (newer firmware) | `hoodOpen: bool` | v1.8.9 |
| Sunroof (3 possible positions!) | `status.sunRoof` (camelCase R, top-level — CC-seatcupra #5) **OR** `status.sunroof` **OR** `status.windows.sunroof` | `sunroofOpen: bool` | v1.8.9 |
| Engine state | top-level `status.engine: "on"/"off"` (CC-seatcupra #50) | not parsed | v1.8.9 |
| Auto-unlock plug | `"on"` / `"off"` / **`"permanent"`** (3 values, CC-seatcupra #51) | only `"ON"` was checked | v1.8.9 |
| Climate state "unsupported" | `climatisationState: "unsupported"` valid (CC-seatcupra #21) | unknown enum, treated as inactive correctly by accident | v1.8.9 documented |

### VW EU CARIAD-BFF — observed shapes

✅ Source: volkswagencarnet PR #650, issue #921, audi_connect_ha audi_models.py.

- `chargingState` (no extra "d", unlike OLA `chargedPowerInKw`)
- `chargePower_kW` (with `_kW` suffix)
- `currentSOC_pct`, `targetSOC_pct` (uppercase SOC)
- `cruisingRangeElectric_km`, `totalRange_km`
- `maxChargeCurrentAC` is a **string**: `"reduced"` / `"maximum"`, not a number
- `windowHeatingStatus` is a **list**: `[{windowLocation: "front", windowHeatingState: "off"}, {windowLocation: "rear", ...}]`
- `engineType.primaryEngineType`: `"electric"` / `"gasoline"` / `"diesel"` / `"hybrid"` (single string)
- `carType` separate field, mostly redundant with `engineType.primaryEngineType`

### Škoda mysmob — observed shapes

✅ Source: CC-skoda #50 (Kodiaq iV 2026 live dump), myskoda model classes.

- `vehicle-status.overall.{doorsLocked, doors, windows, lights, locked}` (all string `"YES"`/`"NO"` / `"CLOSED"`/`"OPEN"` / `"OFF"`)
- `vehicle-status.overall.reliableLockStatus: "LOCKED"` — newer firmware
  (Kodiaq 2026+), prefer over `doorsLocked` because it doesn't lag
- `vehicle-status.detail.{sunroof, trunk, bonnet}` — values
  `"CLOSED"` / `"OPEN"` / **`"UNSUPPORTED"`**. The `UNSUPPORTED` value
  must NOT be parsed as False (Karoq Diesel doesn't have a sunroof; the
  entity should stay None, not show "closed")
- `vehicle-status.renders` and `vehicle-status.compositeRenders` —
  Light/Dark Mode in 4 resolutions (`oneX`, `oneAndHalfX`, `twoX`, `threeX`)
- `charging.status.fullyChargedAt` — absolute ISO timestamp; prefer over
  `remainingTimeToFullyChargedInMinutes + now()` because the latter
  drifts (computed car-side, received with poll latency)
- `charging.status.state`: known values include `"CHARGING"`, `"READY"`,
  **`"CHARGING_INTERRUPTED"`** (myskoda #503, added Feb 2026 — our
  `is_charging = state == "CHARGING"` is correct-by-design here)
- Capabilities returned as objects with `{active, editable, user-enabled,
  status, license-issue, parameters}`. `status` can be a string
  (`"location-data-disabled"`, `"missing-license"`, `"initially-disabled"`)
  OR a list. Status arrays like `[2003]` are also seen.
- `devicePlatform`: `"MBB_ODP"` (classic ICE/PHEV — Kodiaq, Karoq) or
  `"WCAR"` (MEB-EV — Enyaq) — **plattform discriminator** for routing
- `systemModelId`: 6-character unique code (e.g. `PS7DYC` Kodiaq 2026
  PHEV, `NU733D` Karoq 2023 TDI, `5AZJJ2` Enyaq 2022)
- 12V drain signal: capabilities return
  `{"isEnabled": false, "status": ["Deactivated", "InsufficientBatteryLevel"]}`
  on every capability including measurements (volkswagencarnet #940)

### Audi CARIAD-BFF — extras beyond VW EU

✅ Source: audi_connect_ha audi_services.py / audi_models.py.

Extra `selectivestatus` jobs Audi requests beyond what VW EU does:
`activeVentilation`, `auxiliaryHeating`, `batteryChargingCare`,
`batterySupport`, `chargingProfiles`, `chargingTimers`, `departureProfiles`,
`departureTimers`, `honkAndFlash`, `hybridCarAuxiliaryHeating`, `lvBattery`,
`oilLevel`, `vehicleHealthInspection`, `vehicleHealthWarnings`,
`vehicleLights`.

PPE/PPC climate body requirement (audi_connect_ha PR #644 + issue #677):
- **`climatisationMode: "comfort"` is mandatory** (NOT `null`) on
  Q6 e-tron, A6 e-tron, A3 2024+ PHEV
- `targetTemperature` and `targetTemperatureUnit` must be **omitted**
  for PPE — body shape with valid PPE example:
  ```json
  {
    "climatisationWithoutExternalPower": true,
    "climatizationAtUnlock": false,
    "windowHeatingEnabled": true,
    "climatisationMode": "comfort",
    "zoneFrontLeftEnabled": false,
    "zoneFrontRightEnabled": false,
    "zoneRearLeftEnabled": false,
    "zoneRearRightEnabled": false
  }
  ```

ICE Engine Start (audi_connect_ha PR #717, two-step S-PIN flow):
1. `PUT /engine/{VIN}/userpromptproof` with S-PIN body → response includes
   `securedActivationData`
2. `POST /engine/{VIN}/start` with `securedActivationData` from step 1

`devicePlatform` field does **NOT** exist in Audi vehicle response —
checked audi_models.py thoroughly. Plattform detection in audi_connect_ha
is a User-side `api_level` (0/1) toggle, which is fragile (issues #677, #706
show one car works at level 1, sibling car doesn't).

---

## 4. Reference repositories — what to look up where

| Repo | License | Best source for |
|---|---|---|
| `skodaconnect/myskoda` | MIT | mysmob endpoint shapes, `carCapturedTimestamp` field decoration, model classes |
| `skodaconnect/homeassistant-myskoda` | MIT | HA-side patterns (UX for stale/standby/offline), wakeup limits, smart-polling |
| `tillsteinbach/CarConnectivity-connector-skoda` | Apache-2.0 | Live API issue tracker — esp. issue #50 (Kodiaq iV 2026 complete dump) |
| `tillsteinbach/CarConnectivity-connector-seatcupra` | Apache-2.0 | Live OLA dumps (issue #109 Rainer CUPRA Born), unexpected key reports |
| `tillsteinbach/CarConnectivity-connector-volkswagen` | Apache-2.0 | VW EU OAuth flow, login-form-drift fixes |
| `WulfgarW/pycupra` | Apache-2.0 | Verified OLA endpoint paths (`pycupra/const.py`), `EUDAConnection` (EU Data Act precursor) |
| `WulfgarW/homeassistant-pycupra` | Apache-2.0 | SEAT/CUPRA HA-side patterns |
| `audiconnect/audi_connect_ha` | MIT | Audi-specific endpoints, Trip Statistics URL pattern, ICE engine start S-PIN flow, PPE climate body shape |
| `arjenvrh/audi_connect_ha` | MIT | Audi AZS token flow (legacy form, pre-myAudi-app-update) |
| `robinostlund/volkswagencarnet` | Apache-2.0 | **Years of VW EU experience.** Live ID.4 dumps, capability/status discovery, recent merged PRs (#301 Readiness, #307 T&C, #314 Service Discovery) |
| `mitch-dc/volkswagen_we_connect_id` | Apache-2.0 | **ARCHIVED 2025-10-29.** Historical issue forensics only. Lessons: 502/503 retry (#165), transient-error misclassification (#166), 3-failure tolerance (#215) |
| `CJNE/pyporscheconnectapi` | MIT | Porsche Auth0 + PPA endpoints |
| `matpoulin/CarConnectivity-connector-volkswagen-na` | Apache-2.0 | VW US/CA UUID-based endpoint pattern |
| `evcc-io/evcc` | MIT | `vehicle/seat/cupra/api.go` confirms OLA endpoints; `evcc/discussions/16562` confirms CARIAD v1 → 400 for newer models |

### Strategic context (state of the ecosystem as of 2026-04-29)

- `mitch-dc/volkswagen_we_connect_id` **archived 2025-10-29** —
  marketplace gap, this repo is the active multi-brand successor
- `skodaconnect/homeassistant-skodaconnect` **deprecated 2025-03-14** —
  successor is `homeassistant-myskoda`
- `tillsteinbach/WeConnect-python` / `WeConnect-cli` / `WeConnect-MQTT` —
  EOL announced for 2026; ecosystem migrating to multi-brand
  `CarConnectivity-*` connector framework
- VW Group publicly announced PPC/PPE = E³ 1.2 architecture for Audi 2025+
  (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift). **Public**
  reverse-engineering of this backend has not happened yet — neither
  audi_connect_ha nor CarConnectivity nor evcc has a working solution

---

## 5. Patterns that work (verified across multiple repos)

| Pattern | Confidence | Repos confirming | Where we apply it |
|---|---|---|---|
| 502/503/504 weekend backend outages — exponential backoff retry | VERY HIGH (6/6) | we_connect_id #165, myskoda #235/#731, audi forum, pycupra #39, CC-seatcupra #49, volkswagencarnet #683 | `cariad/api/base.py` v1.8.7 |
| Token-refresh storm → IP ban after repeated 401s | HIGH (5/6) | we_connect_id #143/#289, myskoda #976, volkswagencarnet #683/#507, CC-vw 0.10.2 | `cariad/api/base.py:_refresh_tokens` v1.8.7 (max 3/h sliding window) |
| 12V battery drain via wake-on-poll | HIGH (4/6) | myskoda #612/#751/#762, audi forum, pycupra "wake-up call" doc | Planned Session 6 (smart-wake) |
| 404 ≠ auth-fail (capability missing for newer models) | HIGH | audi #207, CC-seatcupra #49 | `cariad/api/base.py` v1.8.7 strict status code discrimination |
| Stale-but-visible > Unavailable on transient errors | HIGH | myskoda #731, we_connect_id #215 | `coordinator.py` v1.8.7 (3-failure tolerance + 6h cache) |
| `carCapturedTimestamp` as freshness authority | CONFIRMED | myskoda 9 model files, volkswagencarnet #921, audi audi_models.py L51-282, CC-seatcupra #109 | `cariad/_util.py:compute_connection_state` v1.8.12 |
| HA 255-char state limit blown by JSON-blob states | CONFIRMED | audi #113 | Coding convention: aggregate in state, JSON in attributes |
| Optimistic-update + state restoration after lock/climate set | MEDIUM | myskoda #832 | Planned Session 3B-Part-3 |
| Restart as refresh workaround | ANTI-PATTERN | CarConnectivity-mqtt-homeassistant docs | Use `RestoreEntity` + persistent state cache instead |
| Endpoint guessing for PPC/PPE | DO NOT | (no public reverse-engineering exists) | Graceful degradation only — Hard Rule #8 |
| Wake automatically in coordinator | UNIVERSAL ANTI-PATTERN | myskoda #762, every reference repo | Wake stays a manual service action only |

---

## 6. Hypothesis corrections (mistakes that made it into earlier audits)

These were claims in earlier audits or AI-generated analyses that turned
out to be wrong. Documented here so they don't get re-investigated.

| Original hypothesis | Reality (verified) | Source of truth |
|---|---|---|
| Skoda Standby/Offline derives from `lastConnected` + `connectionState.isActive` | Wrong. It derives from `carCapturedTimestamp` only. `lastConnected` field doesn't exist in mysmob. | grep on cloned `skodaconnect/myskoda` repo: zero hits for `lastConnected`; nine hits for `carCapturedTimestamp` |
| CUPRA missing 19 entities solved by `/v1/vehicles/{vin}/access/status` endpoint | Wrong. Endpoint is `/v5/users/{userID}/vehicles/{vin}/mycar`. Field paths in `/v2/vehicles/{vin}/status` were wrong (CARIAD-BFF style applied to OLA). | `pycupra/const.py:141` `API_MYCAR = '{baseurl}/v5/users/{userId}/vehicles/{vin}/mycar'` |
| VW EU Vehicle Image API exists somewhere we haven't found | Wrong. There is no official render-image API. App images come from un-authenticated marketing CDN URLs (`digitalrenderingservice.apps.emea.vwapps.io/...`) | Grep on we_connect_id, WeConnect-python, WeConnect-MQTT — zero matches |
| Škoda `/v3/garage` exists as fallback for Kodiaq Mk2 #75 (`/v2/garage` 403) | Wrong. `/v3/garage` does not exist in mysmob. myskoda source (`auth/authorization.py`) only references `/v1/authentication/...` and `/v2/garage` | grep on cloned `skodaconnect/myskoda` repo: zero hits for `v3/garage` |
| Audi `devicePlatform` field exists in vehicle response for plattform detection | Wrong. Not in audi_models.py. Plattform detection in audi_connect_ha is User-side `api_level` toggle, fragile (issues #677, #706) | audi_models.py line-by-line review |

---

## 7. Methodology — how to research safely (don't repeat 1.8.9)

The v1.8.9 ship-with-failing-test incident happened because:
1. Branch protection wasn't enabled — failing CI didn't block merge
2. `gh pr checks --watch` returned exit 0 on "completed" not "all green"
3. Recursion through agent-style prompts assumed the previous research
   step had checked everything

After v1.8.10 hotfix the fix-and-process changes were:
- ✅ Branch protection on `main` enforces all 5 status checks (gh api PUT)
- ✅ CI watcher exit code is no longer trusted alone — explicit
  `gh pr checks <num>` is parsed for "non-SUCCESS count: 0"
- ✅ Doc-only PRs that don't touch `custom_components/**` now also
  trigger `changelog_check.yml` (paths extension to `CHANGELOG.md` and
  `docs/CHANGELOG_TECHNICAL.md`)

### Research-Agent recipe (used 4× during v1.8.6-v1.8.12 sprint)

When you need to understand a corner of the VAG API ecosystem:

1. **Identify the canonical reference repo** for that brand — see Section 4.
2. **Spawn a parallel agent with `gh issue list --state all`** for that
   repo. Give it a focused brief: what fields you need to know, what
   pattern you're looking for, and what you already have (so it doesn't
   re-research).
3. **Insist on verified source** — every claim must cite either an issue
   URL with a JSON dump OR a file path in the cited repo. Hard Rule #8
   (don't guess) becomes "the agent doesn't guess either."
4. **Cross-reference at least 2 repos** for any pattern before treating
   it as fact. v1.8.7 patterns were validated across 6/6 repos before we
   shipped.
5. **Live-test issue dumps are gold** — `tillsteinbach/CarConnectivity-*`
   issues with title "Unexpected Keys" are particularly valuable because
   users post complete API responses.

### What to do AFTER a research agent comes back

1. Re-read the audit doc you're about to update — don't just append.
2. If the agent found a hypothesis correction (Section 6 above), document
   it explicitly so future research doesn't re-investigate.
3. If the agent identified a feature not yet in our roadmap, add it to
   `docs/ROADMAP.md` with the cited issue URL.
4. Bump CHANGELOG.md (human-friendly) AND docs/CHANGELOG_TECHNICAL.md
   (full citations) — they live in sync.

---

## 8. Architecture orientation map (where lives what)

```
custom_components/vag_connect/
├── __init__.py              PLATFORMS list (10), service registration
├── coordinator.py           VagConnectCoordinator — own poll loop, per-VIN
│                            availability, capabilities cache, command profile,
│                            failure tolerance + stale-cache (v1.8.7)
├── entity_base.py           VagConnectEntity — per-VIN availability check
├── config_flow.py           Setup + Options flow (reverse_geocoding opt-in)
├── const.py                 Brand IDs, conf keys
├── manifest.json            Single source of truth for version
├── strings.json             English source for translations
├── translations/{8 langs}   Mirror of strings.json
├── sensor.py                ~30 sensor descriptions, including
│                            connection_state (v1.8.11), vehicle_state
├── binary_sensor.py         ~16 binary sensors + per-door + per-window
│                            (v1.8.9 added windows_individual)
├── switch.py, button.py, climate.py, number.py, lock.py, image.py, select.py,
│   device_tracker.py        Other platforms
└── cariad/
    ├── _util.py             mask_vin (privacy) + compute_connection_state
    │                        (v1.8.12 — brand-agnostic, recursive timestamp walk)
    ├── exceptions.py        APIError, AuthenticationError,
    │                        TermsAndConditionsError, MarketingConsentError,
    │                        TwoFactorRequiredError, RateLimitError,
    │                        TokenExpiredError, SpinError, VehicleCommandError,
    │                        CommandProfile (12-value enum, v1.8.5),
    │                        CommandFailureReason (10-value enum, v1.8.2)
    ├── models.py            BrandConfig (1 per brand), VehicleData (~80 fields)
    ├── factory.py           CariadClientFactory.create(brand, ...)
    ├── auth/
    │   ├── idk.py           IDK PKCE — VW EU, Audi, Škoda, SEAT, CUPRA, VW NA
    │   └── porsche.py       Auth0 PKCE — Porsche
    └── api/
        ├── base.py          CariadBaseClient — _request with v1.8.7 retry
        │                    layer (504 added, transient errors, refresh storm
        │                    guard); _post; _refresh_tokens
        ├── vw_eu.py         VWEUClient — selectivestatus parsing,
        │                    _post_command_with_fallback_paths v1/v2 dispatch
        │                    (v1.8.5 + v1.8.8), connection_state via helper
        │                    (v1.8.12)
        ├── audi.py          AudiClient(VWEUClient) — adds AZS token + vgql
        │                    GraphQL render-image fetcher
        ├── skoda.py         SkodaClient — mysmob endpoints, detail block
        │                    (v1.8.11), reliableLockStatus (v1.8.11),
        │                    fullyChargedAt (v1.8.11), connection_state
        │                    refactored to helper (v1.8.12)
        ├── seat_cupra.py    SeatCupraClient — OLA endpoints, SecToken lock
        │                    flow (v1.8.4), pycupra-style status paths (v1.8.9),
        │                    Live-API charging fields (v1.8.9), connection_state
        │                    via helper (v1.8.12)
        ├── porsche.py       PorscheClient — api.ppa.porsche.com
        ├── vw_na.py         VWNorthAmericaClient — VW US/CA
        └── graphql.py       VehicleImageFetcher — Audi vgql GraphQL only
```

### Reading order for a new contributor

1. `docs/SESSION_HANDOFF.md` (this repo's README for contributors)
2. This file (`docs/RESEARCH_NOTES_2026-04-29.md`) — verified API facts
3. `docs/CHANGELOG_TECHNICAL.md` — what changed and why, with citations
4. `cariad/api/base.py` — start of the request lifecycle
5. `cariad/_util.py:compute_connection_state` — example of a clean,
   well-tested, brand-agnostic helper
6. `cariad/api/skoda.py` — most recent example of a brand client
   following all current patterns (v1.8.11 + v1.8.12 refactor)

---

## 9. EU Data Act (Sep 2026) — head start

`pycupra` already ships an `EUDAConnection` handler ready for when
EU Data Act takes effect:

```python
# pycupra/const.py
EUDA_BASE_URL = "https://eu-data-act.drivesomethinggreater.com"
# pycupra/eudaconnection.py:1215
PROXY_API_PATH = "/proxy_api/vum/v2/users/me/relations/{vin}"
```

When the regulation lands, our work is to add `cariad/api/euda.py`
mirroring the pycupra implementation. We don't need to reverse-engineer
from scratch.
