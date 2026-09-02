# DataPlug / plug&play cloud reader — handoff

**Status:** Audi (acpp) **live-validated** (real enrolled A5 B8) — last re-pull **2026-09-02** after a
drive + refuel, which woke up three data channels that were empty before. VW (wcg) **tester-gated**
(endpoints mapped, login not wired). New source; foundation committed on
`feat/plugandplay-cloud-reader` / `feat/acpp-carport-enrichment`. Integration (config-flow / factory /
coordinator / sensors) is left for the main OBD-solution work — see **Integration TODO** below.

> **2026-09-02 addendum.** After the owner drove the car a little and refuelled, a fresh pull surfaced
> data channels + fields we were NOT ingesting. The big ones: a full **driver logbook** (`driverlogs`)
> with GPS tracks, **precise odometer**, **EcoScore** (per-trip engine snapshots exist too, but read
> 0/at-standstill on the observed trips — unproven); a **fuel log**
> (`fuellog`, "von→auf Liter"); the **GPS `recordedAt`** freshness stamp; and the account **score/ranking**
> ledger (`achievements/v2`). Full field schemas + recommended mapping in **New data channels** and
> **Recommended VehicleData mapping** below. Two earlier statements are corrected there: (a) the carport
> 500 is solved (single-tag `Accept-Language`), and (b) the "no engine telemetry in the cloud at all"
> claim is refined — continuous live PIDs are indeed absent, but the logbook stores trip-boundary engine
> snapshots.

## Why this exists

The plug&play apps — `de.audi.connectplugandplay` (Audi connect plug&play) and
`de.volkswagen.vwconnect` (VW We Connect Go) — pair a **TEXA OBD dongle** with OLD cars that have
**no built-in connectivity**. Those cars are invisible to the modern CARIAD BFF and to the
EU-Data-Act portal, so **this is the only cloud read path** for a dongle-equipped Touareg / e-up! /
pre-connectivity A4/A5/Golf, etc. It is attestation-free and hands out a **durable refresh token**.

The dongle uploads a **snapshot** on sync (odometer, 12V battery, fuel, service, tyres, warnings) plus
an **event history** (trips, refuels, score). **Continuous live PIDs** (speed/rpm/coolant/boost while
driving) are **not** in the cloud — `provalue` / `measurements` / `status` all 404 (see **Live PIDs —
status**). They stay dongle-local and are read over Bluetooth (the separate `dataplug-reconnect` local
reader). The one nuance: the logbook DOES carry engine-value **snapshots at each trip's start/end**
(coolant, engineSpeed, speed, acceleration, altitude) — but those are captured at standstill, so on the
trips observed so far they read 0. Real-time engine data still requires the BT-local path.

## Audi (acpp) — validated flow

| step | value |
|---|---|
| client_id | `ec6198b1-b31e-41ec-9a69-95d42d6497ed@apps_vw-dilab_com` |
| authorize | `https://identity.vwgroup.io/oidc/v1/authorize` (authorization_code + PKCE) |
| scope | `openid email profile` — **not** `… https://audiid.vwgroup.io/account` (→ `consent_required`) |
| redirect | `acpp://de.audi.connectplugandplay/oauth2redirect/identitykit` |
| token | `https://prod.acpp.cariad.digital/token` — plain OAuth, **no x-qmauth**, returns refresh_token |
| data base | `https://prod.acpp.cariad.digital` |

Reuse of the existing auth stack (no new login code needed for Audi):

```python
IDKAuth(session, BRAND_AUDI_ACPP, token_url_override="https://prod.acpp.cariad.digital/token")
```

`BRAND_AUDI_ACPP.name == "audi_acpp"` (NOT `"audi"`) so `IDKAuth._exchange_code()` takes the
plain-OAuth branch instead of the CARIAD BFF x-qmauth branch, and honours the `token_url_override`.

**Header gotcha (live-verified):** the `carport` (master-data) endpoint reads the language from
`Accept-Language` and needs a **single** tag. It **500s** when the header is absent and **400s** on a
multi-value / q-weighted value (`"de-DE, en-US;q=0.9"`). A bare `"de-DE"` returns 200. `_get()` now
sends a single tag on every request. *(This supersedes the earlier "carport 500 / lang-param mismatch,
TODO" note — solved.)*

### Data endpoints (Bearer `<acpp access token>`)

Only VINs **enrolled in the account** exist — an unknown VIN returns
`404 {"message":"Vehicle with vin ... does not exist"}` (the owner's S6 was not enrolled → 404). All
data endpoints are VIN-addressed; there is no per-user garage resource, so enumerate cars via `GET /vehicles`.

| path | method | returns | mapped? |
|---|---|---|---|
| `vehicles` | GET 200 | array of the `vehicle/{vin}` snapshot shape → we take the VINs | ✅ `get_vehicles()` |
| `vehicle/{vin}` | GET 200 | root snapshot (odometer, 12V, fuel L, sync dates, dealer) | ✅ partial |
| `vehicle/{vin}/warning-lights` | GET 200 | `{"warningLights":[...]}` | ✅ count/active |
| `vehicle/{vin}/carport` | GET 200 | factory master data (model/engine/fuel/power/colors/dates) | ✅ enriched |
| `vehicle/{vin}/last-parking-position` | GET 200 | `{"recordedAt":<ms>,"gpsLocation":{lat,lon}}` | ⚠️ lat/lon only — `recordedAt` **NOT** mapped |
| `vehicle/{vin}/tires` | GET 200 | `[{id,mileage,manufacturer,changeDate,tireActive,...}]` (placeholder on B8) | ❌ |
| `vehicle/{vin}/driverlogs` | GET 200 | **driver logbook** — trips + EcoScore + engine snapshots (0 on observed trips / unproven) (full schema below) | ❌ **NEW** |
| `user/fuellog/{vin}` | GET 200 | **fuel log** — refuel events, von→auf Liter (full schema below) | ❌ **NEW** |
| `user/achievements/v2` | GET 200 | **score/ranking** points ledger (full schema below) | ❌ **NEW** |
| `vehicle/{vin}/vehicle_app_services` | GET 200 | push-notification toggles (schema below) | ❌ |
| `vehicle/{vin}/appointment` | GET 200 | `[]` (service appointments — empty on B8) | ❌ |
| `vehicle/{vin}/details` | GET 405 | POST-only endpoint | — |
| `vehicle/{vin}/{provalue,measurements,status,state,statistics}` | 404 | **live PIDs are NOT stored** (dongle-local only) | — |
| `user/fingerprints/{vin}` | 404 | not present | — |
| `user/cars/{vin}/…` | 404 | wrong family (early dead end); the live family is `vehicle/{vin}/…` | — |

## New data channels — full field schema (grounded 2026-09-02, post-drive)

### `vehicle/{vin}` — root snapshot

```jsonc
{ "vehicle": { "id", "vin", "carPlatform": "KWP2000" },   // carPlatform present → pre-connectivity combustion/PHEV
  "odometer": 369290.0,          // ⚠️ COARSE / rounded int-ish, and it LAGS (see odometer note)
  "batteryVoltage": 13.98,       // 12V rail read on sync (11.76 before drive → 13.98 after = alternator charged)
  "tankFuelAmount": 23.0,        // absolute litres (NOT %), 3.0 before refuel → 23.0 after
  "registrationDate": "2026-08-23T16:40:06Z",  // STALE "Datenstand" stamp — did NOT move across the drive;
  "mainCheck":        "2026-08-23T16:40:06Z",  // NOT a real reg date. Use driverlog endTime / parking
                                               // recordedAt for TRUE freshness (this stamp is unreliable).
  "vehicleSpecificDealer": { "dealer": { "kvpsId": "DEUA…" } } }
```

> **Odometer caveat (important).** The root `odometer` is coarse and stale — it stayed `369290` across a
> drive while `registrationDate`/`mainCheck` also did not move. The **precise, fresher** odometer lives
> in `driverlogs[].endData.odometer` (`369291.0` after the 01.09 trip; sub-metre float). **Recommendation:
> source `odometer_km` from the newest driverlog `endData.odometer`, fall back to root `odometer`.**

### `vehicle/{vin}/driverlogs` — driver logbook (Fahrtenbuch) — **the big find**

Paginated (`content[]`, `totalElements`). Each entry is one trip:

```jsonc
{ "id": 121022141,
  "driverLogId": "x-coredata://…/Trip/p2",
  "remark": "01.09.2026",              // trip date label
  "manualtrip": false,
  "startTime": 1788273197740,          // epoch-ms
  "endTime":   1788273444410,          // epoch-ms
  "totalTripTime": 246670,             // ms (≈ 4 min 7 s)
  "totalTripMileage": 1.3778710913,    // km (precise float)
  "totalTripStandingTime": 0.0,
  "averageInductionAirTemperature": 24,   // °C — Ansauglufttemperatur
  "avgFuelConsumption": 0.0,              // unit unconfirmed (0 on observed trips) — VERIFY before labelling
  "startData": { …engine snapshot at trip start… },
  "endData":   { …engine snapshot at trip end… },
  "ecoScore":  { …driving-style score… } }
```

**`startData` / `endData` — engine + position snapshot at each trip boundary:**

```jsonc
{ "recordedAt": 1788273444410,       // epoch-ms
  "odometer": 369291.0,              // PRECISE odometer (sub-metre) — fresher than root
  "gpsLocation": { "latitude": 47.696…, "longitude": 8.064… },  // trip start/end coordinates → GPS track
  "coolant": 0.0,                    // coolant temp   ┐
  "engineSpeed": 0.0,                // RPM            │ engine-value snapshot fields —
  "speed": 0.0,                      // km/h           │ present in schema, but 0 on the
  "acceleration": 0.0,               // g              │ observed trips (captured at standstill)
  "altitude": 0.0,                   // m              ┘
  "isSmooth": true }
```

**`ecoScore` — per-trip driving-style rating:**

```jsonc
{ "ecoScore": 98,                    // overall 0–100
  "accelerationResult": 100, "accelerationPositiveCount": 15, "accelerationNegativeCount": 0,
  "brakeResult": 92,         "brakePositiveCount": 12,        "brakeNegativeCount": 1,   // 1 hard brake → 92
  "engineSpeedResult": 100,  "engineSpeedPositiveCount": 32,  "engineSpeedNegativeCount": 0,
  "speedResult": 100,        "speedPositiveCount": 32,        "speedNegativeCount": 0,
  "coolantTemperatureResult": 100, "coolantTempPositiveCount": 0, "coolantTempNegativeCount": 0 }
```

Observed on the B8: `totalElements: 2` — a 35 s / 6.5 m shunt (29.08, EcoScore 100) and a
4 min / 1.38 km trip (01.09, EcoScore 98). The **useful** driverlog signal is: precise odometer, trip
distance/duration, EcoScore, and the start/end GPS coordinates (a "last trip" track / device_tracker
trail). The raw engine-snapshot fields exist but are boundary-at-rest (0 here); do not over-promise them.

### `user/fuellog/{vin}` — fuel log (Tankungen, "von→auf Liter")

Paginated (`content[]`). Each entry is one refuel event:

```jsonc
{ "id": 5653155,
  "fuelLogId": "x-coredata://…/RefuellingStop/p1",
  "createdTimestamp": 1788273155000,   // epoch-ms
  "amount": 21.0, "amountUnit": "l",           // litres ADDED
  "postFuelAmount": 24.0, "postFuelAmountUnit": "l",  // tank AFTER fill → "3 L → +21 L → 24 L"
  "odometer": 369290.0,                        // odometer at refuel
  "mileageSinceFueled": 0.0, "mileageSinceFueledUnit": "km",
  "currency": "EUR", "price": 0.0,             // price/station captured only if the user fills them in
  "shopCoordinates": { "latitude": 0.0, "longitude": 0.0 },  // station GPS (0/0 = not captured here)
  "stationName": "", "stationAddress": "",
  "driverName": "null null", "hasBeenShown": true }
```

The "von→auf Liter" the owner asked for = `postFuelAmount - amount` before → `postFuelAmount` after
(here **3 L → 24 L**, +21 L). `amount` = litres added, `postFuelAmount` = tank level after.

### `vehicle/{vin}/last-parking-position` — parking GPS + freshness

```jsonc
{ "recordedAt": 1788289854000,   // epoch-ms — REAL freshness of the fix (NOT mapped today)
  "gpsLocation": { "latitude": 47.696…, "longitude": 8.064… } }
```

Before the drive this was `0/0` (null-island, no fix); after driving+parking it became a real fix with a
real `recordedAt`. `recordedAt` is the **true position age** and is fresher than the root
`registrationDate`/`mainCheck` "Datenstand" — map it onto the existing `position_captured_at` field
(models.py:798), not a new column.

### `user/achievements/v2` — score / ranking (gamification ledger)

Account-level (not per-VIN), paginated. A points ledger — this is the "Score/Ranking" surface, distinct
from the per-trip EcoScore above:

```jsonc
{ "content": [
    { "id": 138082031, "special_purpose": "SCORE_FULL_REGISTRATION", "points": 3000,
      "achievedAt": 1785883324000, "expirationDate": 0 },          // 0 = never expires
    { "id": 138082030, "special_purpose": "SCORE_DAILY_POINTS", "points": 120,
      "achievedAt": 1785883279000, "expirationDate": 1819749599000 },
    { "special_purpose": "MONTHLY_POINT_JOB", "points": 0, … } ] }
```

`special_purpose` seen: `SCORE_FULL_REGISTRATION` (3000), `SCORE_DAILY_POINTS` (120 each),
`MONTHLY_POINT_JOB`. Sum the non-expired `points` for a "total score" figure if surfaced.

### `vehicle/{vin}/vehicle_app_services` — push-notification toggles

```jsonc
{ "settings": [ { "setting_name": "notifications_warning",    "setting_enabled": true },
                { "setting_name": "notifications_refuel",     "setting_enabled": true },
                { "setting_name": "notifications_inspection", "setting_enabled": true },
                { "setting_name": "notifications_oil",        "setting_enabled": true },
                { "setting_name": "notifications_tire",       "setting_enabled": true },
                { "setting_name": "notifications_challenge",  "setting_enabled": true },
                { "setting_name": "notifications_all",        "setting_enabled": true } ] }
```

Config/diagnostic only — not vehicle telemetry.

## Live PIDs — status (explicit)

- **Continuous / real-time PIDs are NOT in the acpp cloud.** `vehicle/{vin}/provalue`,
  `…/measurements`, `…/status`, `…/state`, `…/statistics` all return **404** ("No static resource …").
  Gegenprobe: the `vehicle/{vin}` family itself answers 200, so these specific resources genuinely do
  not exist — it is not an auth/path artefact.
- **The only engine values in the cloud** are the trip-boundary snapshots inside
  `driverlogs[].startData/endData` (coolant, engineSpeed, speed, acceleration, altitude) — captured at
  standstill, hence 0 on the short trips seen. Whether a longer motorway trip populates non-zero boundary
  values is **untested**.
- **For real-time speed/rpm/coolant/boost, use the BT-local reader** (`dataplug-reconnect`). The cloud
  and the dongle-BT path are complementary: cloud = history + snapshot (works remotely, no car nearby);
  BT = live PIDs (car in range only).

## Recommended VehicleData mapping (priority)

`get_status()` today fills: `odometer_km`, `has_combustion`, `warning_count/active`, `model_year`,
`voltage_12v`, `fuel_level_liters`, `data_captured_at`, `latitude/longitude`, plus the carport enrichment
(`manufacturer`, `model`, `engine_power`, `registration_date`, colors, `engine_torque_nm`,
`engine_cylinders`, `engine_displacement_ccm`, `engine_code`, `fuel_type`, `transmission`,
`warranty_until`).

**Important — reuse the existing trip/position fields, do NOT invent parallel ones.** `models.py`
`VehicleData` already carries a CARIAD-BFF trip-statistics family (`last_trip_distance_km` :1508,
`last_trip_duration_min` :1509, `last_trip_avg_speed_kmh` :1510,
`last_trip_avg_fuel_consumption_l_100km` :1511, `last_trip_timestamp` :1513,
`last_trip_start_odometer_km` :1723, `recent_trips` :1522) plus `position_captured_at` :798. Brand
clients are **mutually exclusive per vehicle**, so the acpp driverlog mapper should **populate those same
fields** (they already have HA sensors) rather than add `last_trip_*` / `gps_recorded_at` duplicates —
adding `last_trip_distance_km` again would redefine/clobber the dataclass field. Only fields with no
existing home are genuinely new. Semantics note: the BFF parser stores consumption as int×10÷10 and backs
`last_trip_distance_km`'s attributes with `recent_trips`; acpp gives a plain float and no such attribute
backing, so match the value, not the parser.

**Priority A — map now (clear value):**

| VehicleData field | reuse / new | acpp source | note |
|---|---|---|---|
| `odometer_km` | reuse (change source) | newest `driverlogs[].endData.odometer` → fallback root `odometer` | root lags & is coarse |
| `last_trip_distance_km` | **reuse** :1508 | newest `driverlogs[].totalTripMileage` | sensor exists |
| `last_trip_timestamp` | **reuse** :1513 | newest `driverlogs[].endTime` (ms → ISO) | sensor exists |
| `last_trip_start_odometer_km` | **reuse** :1723 | newest `driverlogs[].startData.odometer` | sensor exists |
| `position_captured_at` | **reuse** :798 | `last-parking-position.recordedAt` (ms → ISO) | true position age; has carry-forward-TTL machinery |
| `last_trip_eco_score` | **new** | newest `driverlogs[].ecoScore.ecoScore` (0–100) | acpp-specific, no BFF equivalent |
| `last_refuel_liters_added` | **new** | `fuellog.content[0].amount` | litres added (21) |
| `last_refuel_tank_before_l` | **new** | `postFuelAmount − amount` | the **"von"** side (3) |
| `last_refuel_tank_after_l` | **new** | `fuellog.content[0].postFuelAmount` | the **"auf"** side (24) → renders "3 → 24" |
| `last_refuel_at` | **new** | `fuellog.content[0].createdTimestamp` (ms → ISO) | TIMESTAMP |

**Priority B — nice-to-have:**

| VehicleData field | reuse / new | acpp source |
|---|---|---|
| `last_trip_duration_min` | **reuse** :1509 | newest `totalTripTime` ÷ 60000 |
| `last_trip_avg_fuel_consumption_l_100km` | **reuse** :1511 | newest `avgFuelConsumption` — **verify unit is l/100km first** (0 on observed trips) |
| `recent_trips` | **reuse** :1522 | the full `driverlogs.content` list (see full-logbook note in Priority C) |
| `last_trip_intake_air_temp_c` | **new** | newest `driverlogs[].averageInductionAirTemperature` (24 °C — a real, non-zero trip datum) |
| `last_refuel_odometer_km` | **new** | `fuellog.content[0].odometer` |
| `trip_count` | **new** (or `len(recent_trips)`) | `driverlogs.totalElements` |
| `score_points_total` | **new** | Σ non-expired `achievements/v2 … points` |

**Priority C — rich / optional:**
- **Full logbook** (the owner asked for the *whole* Fahrtenbuch): put ALL trips into `recent_trips` :1522
  (list attribute), paging through every entry — not just page 0 — or a dedicated logbook entity. Per
  entry: distance / duration / EcoScore / start+end GPS. This is where "all engine snapshots" live
  (schema-complete but 0-valued so far).
- Last-trip **GPS track** (start+end coords) → a device_tracker trail or a "last trip" map card.
- EcoScore sub-scores (`brakeResult`/`accelerationResult`/`engineSpeedResult`/`speedResult`) as attributes.
- Per-trip engine boundary snapshots (coolant/rpm/speed/accel) — low value while they read 0; revisit if a
  long trip shows non-zero.

Reuse the existing `_epoch_ms_to_date` helper; add an ms→ISO-**datetime** sibling for the trip/refuel/
position timestamps (ms since epoch, same as carport dates but wanting time-of-day, not just the date).

## Token does NOT open the BFF

The acpp access token (`aud` = the acpp client itself, `scp: profile email openid`) is **not
BFF-whitelisted**: `emea.bff.cariad.digital/vehicle/v1/*` → `403 "clientId in the token claim is
either unknown or not whitelisted"`. Confirms the BFF client-whitelist gate; this is not a wall
bypass, it is its own silo. (Consistent with `vag_connect_apk_sweep` client sweep.)

## VW (wcg) — mapped, tester-gated

| | value |
|---|---|
| client_id | `ac42b0fa-3b11-48a0-a941-43a399e7ef84@apps_vw-dilab_com` |
| IDP | `identity.legacy.vwgroup.io` — **legacy `signin-service`, not Auth0** |
| data base | `https://prod.wcg.cariad.digital` |
| data paths | `vehicles/{vin}/{measurements,warnings,config,series/measurements}` (note `vehicles` **plural**) |
| garage list | `api/v1/users/{user_id}/vehicles` |

**Blocker:** `IDKAuth.authenticate()` targets Auth0 Universal Login; against the legacy
signin-service it returns `HTTP 400` at the identifier POST
(`identity.legacy.vwgroup.io/signin-service/v1/{client_id}/login/identifier`). Implement the
signin-service legs (identifier → authenticate → code) — `auth/_vweu_twoway_login.py` already has
this pattern — then point `token_url_override` at the legacy token endpoint. Not live-testable here
(no VW dongle car available); gate behind a tester like the other unvalidated paths. The wcg data
channels (driverlogs/fuellog equivalents) are unmapped — expect a similar but plural-path shape.

## Integration TODO (for the main OBD-solution work)

1. **config-flow**: add a "DataPlug / plug&play (OBD dongle)" source option (email+password; Audi
   ready, VW behind a tester flag).
2. **factory.py**: register `PlugAndPlayCloudClient` (acpp) — already mirrors the
   `(session, brand, email, password, spin="")` constructor and exposes `authenticate()` +
   `get_status(vin)`. *(Done in `feat/acpp-carport-enrichment` — verify it's present.)*
3. **VehicleData mapping**: extend `get_status()` with the **Priority A** fields above. **Reuse** the
   existing BFF trip/position columns (`last_trip_distance_km`, `last_trip_timestamp`,
   `last_trip_start_odometer_km`, `last_trip_duration_min`, `last_trip_avg_fuel_consumption_l_100km`,
   `recent_trips`, `position_captured_at`) — do NOT add duplicates (they would clobber the dataclass
   fields) — and switch `odometer_km` to the precise driverlog source. Add ONLY the genuinely-new
   columns to `models.py`: `last_trip_eco_score`, `last_trip_intake_air_temp_c`,
   `last_refuel_liters_added` / `_tank_before_l` / `_tank_after_l` / `_at` / `_odometer_km`,
   `trip_count`, `score_points_total`. Extend `get_raw_snapshot()` to also fetch `driverlogs` +
   `user/fuellog/{vin}` — page through ALL driverlog entries for the full logbook, not just page 0.
4. **Poll cadence**: snapshot + history only update when the dongle syncs (after a drive); a slow poll
   is fine. No live PIDs here — pair with the BT-local reader for real-time data.
5. **wcg**: implement the legacy signin-service login + wire `WCGCloudClient`, tester-gated.
6. **Unit checks before shipping**: confirm `avgFuelConsumption` unit, and whether `driverlogs`/`fuellog`
   pagination is newest-first or needs an explicit sort/`?page=` param (only 1–2 entries observed).

## Reference

Working, credential-driven probes used to validate this live are in the session scratchpad
(`acpp_login.py`, `acpp_read.sh`, `acpp_bff.sh`, plus 2026-09-02 re-probes of driverlogs / fuellog /
achievements / parking) — **not committed** (they read `~/.claude/private` creds and cache a token in
`~/.claude/private/acpp_token.json`). The committed code (`api/plugandplay.py`) is the clean-room
equivalent that reuses `IDKAuth`. All live values above are from a real enrolled A5 B8; VIN/serial are
never committed.
