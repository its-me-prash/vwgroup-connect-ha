# DataPlug / plug&play cloud reader — handoff

**Status:** Audi (acpp) **live-validated** (real enrolled A5 B8) — last re-pull **2026-09-02** after a
drive + refuel, which woke up three data channels that were empty before. VW (wcg) **tester-gated**
(endpoints mapped, login not wired). New source; foundation committed on
`feat/plugandplay-cloud-reader` / `feat/acpp-carport-enrichment`. Integration (config-flow / factory /
coordinator / sensors) is left for the main OBD-solution work — see **Integration TODO** below.

> **2026-11-13 addendum (live, same A5 B8, one calm request per channel).** Prompted by a static
> analysis of the plug&play 3.6.5 app. Results:
> (a) **`vehicle/{vin}/driverlogs/{id}/polldata` exists and holds a real per-trip time series** —
> speed, rpm, coolant, acceleration, altitude and GPS every ~5 s (237 samples for a 21-minute trip).
> Live PIDs are still not streamed, but "no engine values in the cloud" was wrong. See **Per-trip time
> series (polldata)**.
> (b) **The `startData`/`endData` zeros are written by the app as constants**, so they never become
> real values, however long the trip.
> (c) **Pro values live at `vehicle/provalue?vin=`** (200, `[]` here): unlock state, not measurements.
> (d) **The `user/cars/{vin}/…` family is CARIAD CarData on `cardata.apps.emea.vwapps.io`**, not acpp.
> That host no longer resolves (NXDOMAIN), so the family is dead.
> (e) **`vehicle/{vin}/details` is PUT**, not POST.
> (f) **Paging bug, fixed in the reader:** the server returns `driverlogs`/`fuellog` oldest first, and
> the bare GET gave only the 20 oldest of 42 trips. The reader reported a last trip a month old and an
> odometer ~900 km short. It now pages like the app (`limit=100` / `limit=50`) and collapses
> server-side duplicate uploads (one trip stored 8 times).
> (g) **Second pass, same day — all open points closed:** `data_captured_at` no longer comes from
> `registrationDate`/`mainCheck`, which are user-entered vehicle details. `avgFuelConsumption` is the
> car's own average-consumption reading at trip end, in l/100 km. polldata takes `limit=300`; only
> the **highest-id** copy of a duplicated trip carries samples. The reader now maps polldata maxima,
> average speed and consumption. One live `get_status()` with the new code (11 requests, all 200)
> returned the right values, see **Verification**.

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
an **event history** (trips, refuels, score). **Real-time PIDs** (speed/rpm/coolant/boost while
driving) are **not** streamed to the cloud; for those, use Bluetooth (the separate `dataplug-reconnect`
local reader). What the cloud does get **after** a trip is a **per-trip time series** (`polldata`:
speed, rpm, coolant, acceleration, altitude, GPS at ~5 s; live-verified 2026-11-13). The trip-boundary
"snapshots" in `driverlogs[].startData/endData` are not that: the app writes constant zeros there
(see **Live PIDs — status**).

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
| `vehicle/{vin}/last-parking-position` | GET 200 | `{"recordedAt":<ms>,"gpsLocation":{lat,lon}}` | ✅ lat/lon + `recordedAt` → `position_captured_at` |
| `vehicle/{vin}/tires` | GET 200 | `[{id,mileage,manufacturer,changeDate,tireActive,...}]` (placeholder on B8) | ❌ |
| `vehicle/{vin}/driverlogs?page=&limit=&returnPollData=` | GET 200 | **driver logbook** — trips + EcoScore (full schema below). **Oldest first, default page 20** → the reader pages with `limit=100&returnPollData=false` | ✅ last trip, EcoScore, `recent_trips` |
| `vehicle/{vin}/driverlogs/{id}/polldata?page=&limit=` | GET 200 | **per-trip time series** (2026-11-13, schema below); `limit=300` honoured; samples only on the highest-id copy of a duplicated trip | ✅ newest-trip maxima on `recent_trips[0]` |
| `user/fuellog/{vin}?page=&limit=` | GET 200 | **fuel log** — refuel events, von→auf Liter (full schema below). Oldest first; the reader pages with `limit=50` | ✅ last refuel |
| `user/achievements/v2` | GET 200 | **score/ranking** points ledger (full schema below) | ✅ `score_points_total` |
| `vehicle/{vin}/vehicle_app_services` | GET 200 | push-notification toggles (schema below) | ❌ |
| `vehicle/{vin}/appointment` | GET 200 | `[]` (service appointments — empty on B8) | ❌ |
| `vehicle/{vin}/details` | GET 405 | write endpoint: the app sends **PUT** (3.6.5 code; the earlier "POST-only" guess was wrong) | — |
| `vehicle/provalue?vin={vin}` | GET 200 | `[]` here (2026-11-13). Pro-value **unlock state** for app tiles, not measurements | — nothing to map |
| `vehicle/{vin}/{provalue,measurements,status,state,statistics}` | 404 | no such resources (`provalue` sits at the path above) | — |
| `user/cars/{vin}/{config,measurements,warnings}`, `users/{id}/cars/{vin}/measurements`, `user/fingerprints/{vin}` | — | **not acpp**: CARIAD CarData at `https://cardata.apps.emea.vwapps.io` (that is why they 404'd here). The host is **NXDOMAIN** on 2026-11-13 (local, 1.1.1.1, 8.8.8.8; parent zone and acpp resolve) → dead | — |

## New data channels — full field schema (grounded 2026-09-02, post-drive)

### `vehicle/{vin}` — root snapshot

```jsonc
{ "vehicle": { "id", "vin", "carPlatform": "KWP2000" },   // carPlatform present → pre-connectivity combustion/PHEV
  "odometer": 369290.0,          // ⚠️ COARSE / rounded int-ish, and it LAGS (see odometer note)
  "batteryVoltage": 13.98,       // 12V rail read on sync (11.76 before drive → 13.98 after = alternator charged)
  "tankFuelAmount": 23.0,        // absolute litres (NOT %), 3.0 before refuel → 23.0 after
  "registrationDate": "2026-08-23T16:40:06Z",  // USER-ENTERED vehicle details: first registration and
  "mainCheck":        "2026-08-23T16:40:06Z",  // main inspection (the app PUTs them with licencePlate and
                                               // vehicleNickName). Both default to the enrollment time —
                                               // never a sync / freshness stamp.
  "licencePlate", "vehicleNickName",           // also user-entered (seen 2026-11-13)
  "vehicleSpecificDealer": { "dealer": { "kvpsId": "DEUA…" } } }
```

> **Odometer caveat (important).** The root `odometer` is coarse and stale — it stayed `369290` across a
> drive while `registrationDate`/`mainCheck` also did not move. The **precise, fresher** odometer lives
> in `driverlogs[].endData.odometer` (`369291.0` after the 01.09 trip; sub-metre float). **Recommendation:
> source `odometer_km` from the newest driverlog `endData.odometer`, fall back to root `odometer`.**
> Still true on 2026-11-13 (root 370 680 vs newest trip end 370 686), **but "newest" needs every page**:
> page 0 alone ended at 369 774, ~900 km behind (see the logbook paging note below).

> **`registrationDate` moved (2026-11-13), fixed the same day.** It now carries a 2008 date (the
> car's first registration, entered in the app), while `mainCheck` kept the enrollment default. The
> reader used to take `registrationDate or mainCheck` as `data_captured_at`, so that sensor showed
> 2008. In the app code, both fields belong to the user-editable vehicle details. The reader now sets
> `data_captured_at` to the freshest real stamp, newest trip `endTime` or parking `recordedAt`, and
> leaves it empty when there is neither. It marks the last upload; values that only change with a
> trip (odometer) can be older when the parking fix is newer than the last trip.

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
  "avgFuelConsumption": 0.0,              // l/100 km — the car's own average at trip end; 0 = no reading
  "reason": "",                           // new key by 2026-11-13, empty on all 42 trips
  "startData": { …trip-start record… },
  "endData":   { …trip-end record… },
  "ecoScore":  { …driving-style score… } }
```

`totalTripStandingTime` is in ms (one trip: 222 000 within 7.3 min).

**`avgFuelConsumption` (settled 2026-11-13 from the 3.6.5 code).** It is the app's trip column
`end_average_consumption`: the car's own average-consumption reading, taken from the dongle at trip
end. The app reads consumption from one dongle element, `FuelConsumption.AverageValuePerMileage`, whose
catalog unit is **l/100 km**. The app uploads 0 when it had no reading (it clamps ≤ 0 to 0). So it is
the trip-computer memory, not a figure the app computes for this trip, and it means what the BFF
short-term average means. Live values: 0 on short trips, 6.6–21 on longer ones, 11.2 on the newest
trip (35.7 km). The reader maps positive values to `last_trip_avg_fuel_consumption_l_100km`.

**`startData` / `endData` — trip-boundary record:**

```jsonc
{ "recordedAt": 1788273444410,       // epoch-ms                      ┐ real
  "odometer": 369291.0,              // PRECISE odometer (sub-metre)  │ values
  "gpsLocation": { "latitude": <lat>, "longitude": <lon> },  // ┘ trip start/end coordinates
  "coolant": 0.0,                    // ┐
  "engineSpeed": 0.0,                // │ ALWAYS 0: the app writes these as literal constants
  "speed": 0.0,                      // │ (plug&play 3.6.5 trip serializer). Not standstill readings;
  "acceleration": 0.0,               // │ a longer trip will not change them. 0 on all 42 live trips
  "altitude": 0.0,                   // │ (2026-11-13), including 95 km / 2 h ones. The real engine
  "isSmooth": true }                 // ┘ values are in polldata (below).
```

**`ecoScore` — per-trip driving-style rating:**

```jsonc
{ "ecoScore": 98,                    // overall 0–100
  "accelerationResult": 100, "accelerationPositiveCount": 15, "accelerationNegativeCount": 0,
  "brakeResult": 92,         "brakePositiveCount": 12,        "brakeNegativeCount": 1,   // 12/(12+1) → 92 (see note)
  "engineSpeedResult": 100,  "engineSpeedPositiveCount": 32,  "engineSpeedNegativeCount": 0,
  "speedResult": 100,        "speedPositiveCount": 32,        "speedNegativeCount": 0,
  "coolantTemperatureResult": 100, "coolantTempPositiveCount": 0, "coolantTempNegativeCount": 0 }
```

Observed on the B8: `totalElements: 2` on 2026-09-02 — a 35 s / 6.5 m shunt (29.08, EcoScore 100) and
a 4 min / 1.38 km trip (01.09, EcoScore 98). The **useful** driverlog signal is: precise odometer, trip
distance/duration, EcoScore, and the start/end GPS coordinates (a "last trip" track / device_tracker
trail). The boundary engine fields are constant zeros (see above); do not surface them.

**Paging and duplicates (live 2026-11-13, 42 entries).** The response is a Spring page (`content`,
`totalElements`, `totalPages`, `size`, `number`, `first`, `last`, `sort.unsorted: true`). Without
parameters it returns 20 entries, in **insertion order (ascending `id`, oldest first)**. Page 0 held
29.08 → 01.10; the real newest trip (01.11) was on a later page. `?page=0&limit=100&returnPollData=false`
returned all 42 in one page, and so does the reader now. The OEM app does the same thing: its restore
path walks every page (`limit=100`, `returnPollData=true`) and sorts locally. **Duplicates:** one trip
is stored **8 times**, identical except `id` (same `driverLogId` = the app's local trip id), so there
are 42 entries but 35 trips. The reader counts and lists distinct `driverLogId`s.

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
  "gpsLocation": { "latitude": <lat>, "longitude": <lon> } }
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

### `vehicle/{vin}/driverlogs/{id}/polldata` — per-trip time series (live 2026-11-13)

`{id}` is the trip's server `id` from the logbook. The app uploads the samples after the trip in
batches of 300, from its backup worker, so a phone without backup enabled may have none. One GET with
`?page=0&limit=50` on the newest page-0 trip (01.10.2026, 21.5 min, 14.2 km) answered **200**:

```jsonc
{ "content": [                         // ascending recordedAt within the trip
    { "recordedAt": 1790880371890,     // epoch-ms, median step 5.3 s
      "speed": 0.0,                    // km/h
      "engineSpeed": 0.0,              // rpm
      "coolant": 0.0,                  // °C
      "acceleration": 0.0,             // m/s², signed
      "altitude": 0.0,                 // m
      "gpsLocation": { "latitude": <lat>, "longitude": <lon> },
      "isSmooth": true } ],            // per-sample smooth-driving flag (true/false both seen)
  "totalElements": 237, "totalPages": 5, "size": 50, "number": 0,
  "first": true, "last": false, "sort": { "unsorted": true, … } }
```

- **Real values.** The 50 samples on page 0 (the first 4.3 minutes) span speed 0–77 km/h, rpm 0–2022,
  coolant 0→72 °C (warm-up), acceleration −1.66…+1.15, altitude 0→429 m, with GPS on all 50.
- **Units are not in the response.** The GET returns bare floats: no unit fields and no `odometer`,
  although the app's upload body has both (`speedUnit "km/h"`, `engineSpeedUnit "rpm"`,
  `coolantUnit "deg C"`, `accelerationUnit "m/s*s"`). The units above come from that upload body.
- **The first samples are placeholders.** Sample 1 is all zeros, sample 2 has altitude only, and
  coolant/rpm arrive with sample 3. A mapper must not read leading zeros as measurements, e.g.
  "coolant 0 °C".
- **`limit=300` is accepted** (second pass): the same trip came back as 237 samples on one page.
- **Duplicated trips:** of the 8 server copies of one trip, **only the highest `id`** carries samples
  (682). The other 7 answer 200 with `totalElements: 0`. So the copy that stands for a trip must be the
  highest-id one.
- The newest trip (01.11.2026, 51.7 min) has 459 samples.
- The logbook's own `returnPollData=true` (the app's restore path) would embed the samples in every
  trip. Not tested; too heavy for a poll.

**Mapping (implemented 2026-11-13).** Same rule as below: reuse existing fields, add no duplicates,
and keep a trip sample from hours ago away from fields that mean "now".

| target | source | note |
|---|---|---|
| `last_trip_avg_speed_kmh` (**reuse**, sensor exists) | newest trip `totalTripMileage ÷ (totalTripTime / 3 600 000)` | logbook alone, no polldata |
| `last_trip_avg_fuel_consumption_l_100km` (**reuse**) | newest trip `avgFuelConsumption` if > 0 | see the logbook note |
| `recent_trips[0]` attributes `max_speed_kmh`, `max_engine_rpm`, `max_coolant_c` (**reuse** `recent_trips`) | max over the newest trip's polldata; only positive readings count, so placeholders never give a 0 | attributes on the existing last-trip sensor, no new columns |
| `recent_trips[0]` attributes `max_braking_ms2`, `max_acceleration_ms2`, `elevation_gain_m`, `elevation_loss_m`, `smooth_share_pct`, `warmup_min` | same polldata. Braking/acceleration = strongest negative/positive **sampled** `acceleration`: at one sample per ~5 s a short brake peak falls between samples, so this is a floor, not the true peak. Elevation over a **5 m hysteresis** (raw step sums are GPS noise: 107/155 m raw vs a stable 71/121 m at 3 m and 5 m on a live trip). Smooth share among samples where the car was running. Warm-up = first coolant reading → first ≥ 80 °C (0 if already warm, none if never) | live 01.10 trip: 2.37 / 1.48 m/s², 71 / 120 m, 94 %, 6.7 min. 01.11 trip: 1.63 / 1.61 m/s², **875 / 289 m** (real: smooth series from ~352 m to ~938 m, no step over 30 m), 95 %, 15.3 min |
| `recent_trips[0]` attributes `eco_acceleration`, `eco_braking`, `eco_engine_speed`, `eco_speed`, `eco_coolant`, `eco_braking_negative_count`, `eco_acceleration_negative_count` | newest trip `ecoScore` `*Result` (0–100) and the two `*NegativeCount` | logbook alone. **A mark is the share of positively rated intervals, rounded down** (01.11: brake 190 positive / 13 negative → 93; holds for 145 of 161 marks). So `*NegativeCount` counts rated intervals, NOT hard-braking events; the 2026-09-02 reading "1 hard brake → 92" was wrong |
| `license_plate`, `vehicle_nickname` (**reuse**, sensors exist) | root `licencePlate`, `vehicleNickName` | user-entered; empty strings on the B8 until filled in, so only non-blank values are mapped |
| `last_refuel_at` (**reuse** the Škoda key + sensor) | newest `fuellog` `createdTimestamp` → ISO | one deliberate shared key, see the note in `models.py` |
| — not `current_speed_kmh`, not `engine_coolant_temperature_c` | — | those mean "now"; a value from the last trip would pass for a live reading |
| — not the GPS track as an attribute | — | hundreds of points of location history, over the recorder's attribute budget; only as a separate opt-in feature |

Fetch policy: polldata only for the newest trip (highest-id copy), `limit=300`, at most 10 pages,
cached per trip id in the client. A summary is fetched once. A trip without samples (backup off,
upload pending, request failed) is asked again after an hour, not on every poll.

### Verification (live, 2026-11-13, patched reader)

One `get_status()` against the enrolled B8: 11 requests, all 200 — the 7 snapshot resources, one
logbook page, one fuel-log page, two polldata pages. Result:

| field | old reader | new reader |
|---|---|---|
| `odometer_km` | 369 774 (page-0 trip) | **370 686** (newest trip; root 370 680) |
| last trip | 01.10.2026 | **01.11.2026**, 35.73 km, 52 min, EcoScore 97 |
| `trip_count` | 42 (incl. duplicates) | **35** |
| `data_captured_at` | 2008 (`registrationDate`) | **2026-11-13** (parking fix) |
| `last_trip_avg_speed_kmh` / `…_fuel_consumption_l_100km` | empty | **41.4 km/h / 11.2 l/100 km** |
| `recent_trips[0]` polldata maxima | — | **117 km/h, 2483 rpm, coolant 106 °C** |

## Live PIDs — status (explicit)

- **Real-time PIDs are NOT streamed to the acpp cloud.** `vehicle/{vin}/measurements`, `…/status`,
  `…/state`, `…/statistics` return **404** ("No static resource …"); the `vehicle/{vin}` family itself
  answers 200, so this is not an auth/path artefact. (`vehicle/{vin}/provalue` 404s only because the
  resource is `vehicle/provalue?vin=`, which holds unlock state, not measurements.)
- **After-the-fact engine values DO reach the cloud:** the per-trip `polldata` series above (speed, rpm,
  coolant, acceleration, altitude, GPS at ~5 s). That supersedes the earlier "the only engine values in
  the cloud are the trip-boundary snapshots".
- **The trip-boundary fields are constant zeros.** `driverlogs[].startData/endData`
  coolant/engineSpeed/speed/acceleration/altitude are written as literal constants by the app (3.6.5
  code). They are 0 on all 42 live trips, including 95 km / 2 h ones. The earlier "untested on a long
  trip" question is settled: they will never be non-zero.
- **For real-time speed/rpm/coolant/boost, use the BT-local reader** (`dataplug-reconnect`). The cloud
  and the dongle-BT path are complementary: cloud = history, snapshot and per-trip series (works
  remotely); BT = live PIDs and the extra channels the app keeps on the phone (oil temperature, boost
  pressure and speed, exhaust and intake temperature, throttle). Those are never uploaded.
- **Trip aggregates the app can upload** (`averageOilTemperature`, `max/minTurboPressure`,
  `max/minTurboRpm`, `maxThrottleValvePosition`, `maxEmissionAirTemperature`, …) appear in **none** of
  the 42 live trips (key set: the 15 keys shown above). Do not map them until a car actually sends them.

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
| `last_refuel_at` | **reuse** (Škoda hook key) | newest `fuellog` `createdTimestamp` (ms → ISO) | *mapped 2026-11-13*; shares the existing sensor instead of a parallel one |

**Priority B — nice-to-have:**

| VehicleData field | reuse / new | acpp source |
|---|---|---|
| `last_trip_duration_min` | **reuse** :1509 | newest `totalTripTime` ÷ 60000 |
| `last_trip_avg_fuel_consumption_l_100km` | **reuse** :1511 | newest `avgFuelConsumption` if > 0 — unit l/100 km settled 2026-11-13, *mapped* |
| `recent_trips` | **reuse** :1522 | the full `driverlogs.content` list (see full-logbook note in Priority C) |
| `last_trip_intake_air_temp_c` | **new** | newest `driverlogs[].averageInductionAirTemperature` (24 °C — a real, non-zero trip datum) |
| `last_refuel_odometer_km` | **new** | `fuellog.content[0].odometer` |
| `trip_count` | **new** (or `len(recent_trips)`) | distinct `driverLogId`s when every page was read, else `driverlogs.totalElements` (which counts server-side duplicate uploads) |
| `score_points_total` | **new** | Σ non-expired `achievements/v2 … points` |

**Priority C — rich / optional:**
- **Full logbook** (the owner asked for the *whole* Fahrtenbuch): put ALL trips into `recent_trips` :1522
  (list attribute), paging through every entry — not just page 0 — or a dedicated logbook entity. Per
  entry: distance / duration / EcoScore / start+end GPS. *(Paging done 2026-11-13; `recent_trips` keeps
  the newest 10 distinct trips.)* The engine values per trip are in `polldata`, not in the logbook.
- Last-trip **GPS track** (start+end coords) → a device_tracker trail or a "last trip" map card.
- EcoScore sub-scores (`brakeResult`/`accelerationResult`/`engineSpeedResult`/`speedResult`) as attributes.
- ~~Per-trip engine boundary snapshots~~ — dropped: constant zeros written by the app (see **Live PIDs**).

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
6. ~~**Unit checks before shipping**~~ *done 2026-11-13:* `avgFuelConsumption` is l/100 km (car's
   own reading at trip end) and mapped. Pagination: oldest-first, `?page=&limit=` honoured
   (`limit=100` driverlogs, `limit=50` fuellog, `limit=300` polldata, all live-verified). The reader
   walks the pages (cap 5, newest pages kept) and deduplicates by `driverLogId`, keeping the
   highest-id copy.
7. ~~**`data_captured_at`**~~ *done 2026-11-13:* freshest of newest-trip `endTime` / parking
   `recordedAt`; `registrationDate`/`mainCheck` are user-entered details and no longer used.
8. ~~**polldata**~~ *done 2026-11-13:* maxima of the newest trip on `recent_trips[0]`, see
   **Per-trip time series**.
9. **Still open:** whether `limit` above 300 is accepted on polldata (not needed: 10 × 300 covers
   ~4 h); whether trip aggregates like `maxTurboPressure` ever reach the server for a car that has
   them; and the wcg (VW) path from item 5.
10. **Candidates not built yet:** refuel price per litre and cost from `fuellog` `price`/`currency`
    (filled since the owner started entering prices: 50.08 and 136.30 EUR), which needs new fields;
    `main_inspection_due_at` from `mainCheck`, but only once it holds a future date, not the
    enrollment default; and a "service end announced" sensor via `configuration/market` +
    `user/market/shutdown/acknowledge`, which needs one probe for the market ids.

## Reference

Working, credential-driven probes used to validate this live are in the session scratchpad
(`acpp_login.py`, `acpp_read.sh`, `acpp_bff.sh`, plus 2026-09-02 re-probes of driverlogs / fuellog /
achievements / parking) — **not committed** (they read `~/.claude/private` creds and cache a token in
`~/.claude/private/acpp_token.json`). The 2026-11-13 probes (one refresh + `vehicles`, `driverlogs`,
`polldata`, `provalue`, then one `driverlogs?limit=100` and one `fuellog?limit=50` check, each a single
calm request; second pass: one `polldata?limit=300`, one `limit=1` per duplicate copy and on the
newest trip, 6 s apart, then one end-to-end `get_status()` of the patched reader) are likewise not
committed. The committed code (`cariad/api/plugandplay.py`) is the
clean-room equivalent that reuses `IDKAuth`. All live values above are from a real enrolled A5 B8;
VIN/serial/coordinates are never committed.
