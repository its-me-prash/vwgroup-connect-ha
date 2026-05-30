# Technische Changelog-Details (v1.8.6+) / Technical changelog details

> 📖 **Bi-lingual title convention (ab v1.12.3 / since v1.12.3):** Section-Titles sind **DE / EN** geteilt durch ` / `. Body-Inhalt bleibt auf Deutsch (Audience ist primär die deutschsprachige VAG-HA-Community + DACH FB-Gruppen).

Dieses Dokument enthält die vollständigen technischen Detail-Notes für
die Releases v1.8.6 und neuer — gedacht für Contributors, Issue-Reporter,
Reviewer und alle die wissen wollen *welche* Datei *welche* Zeile geändert
hat und *warum*.

**Für End-User-freundliche Release-Notes siehe [`CHANGELOG.md`](../CHANGELOG.md).**

Ältere Releases (v1.8.5 und davor) waren bereits kompakter und sind
weiterhin direkt in `CHANGELOG.md` zu finden.

---

## [1.17.0] - 2026-05-02

### Operational Hardening Bundle / Operational Hardening Bundle

MINOR-Release. Quality-of-life Hardening basierend auf community research deep-dive (3 neue research docs in `docs/research/`). Setzt Foundation für v1.18.0 Push Bundle und v2.0.0 HACS Default Repository.

#### Quota-protective Poll-Defaults

**Old defaults:**
- `DEFAULT_SCAN_INTERVAL = 5` minutes (288 polls/day)
- `MIN_SCAN_INTERVAL = 3` minutes (480 polls/day)

**New defaults (v1.17.0):**
- `DEFAULT_SCAN_INTERVAL = 10` minutes (144 polls/day = 10% of 1500/day quota)
- `MIN_SCAN_INTERVAL = 5` minutes (288 polls/day = 19%)

**Reasoning** (from `_private/research-archive/vag-ha-integration-research.md` + community research):
The MyCupra/MySeat portal limits API calls to ~1,500/day across the official mobile app + integrations. Our old default of 5 min ate 19% of the daily budget BEFORE the official app even logged in. Pycupra's README recommends ≥ 600s default, ≥ 900s with push enabled. The HACS-Checklist (also new in v1.17.0) tracks this as `Operational Safety / Polling interval floor → ✅ done`.

**Migration:** Existing config entries are NOT coerced upward at upgrade — only the default for fresh installs changes. Power users who explicitly set 3min stay at 3min until they reconfigure (and even then can't go below 5min anymore).

`docs/FAQ.md` "What is the daily API request quota?" section explains this for end users.

#### Vehicle-deactivated persistent_notification

**Pattern source:** `WulfgarW/homeassistant-pycupra` v0.2.14.

**File modified:** `coordinator.py::_async_remove_stale_devices`.

When a vehicle disappears from the user's VAG account between polls (sold / ownership transferred / manufacturer-deactivated / subscription expired), the coordinator now creates a `persistent_notification` BEFORE calling `device_reg.async_remove_device()`. The notification:

- Title: "VAG Connect — Fahrzeug entfernt"
- Body: explains in German what happened, lists possible reasons (sold / ownership / subscription expired / manufacturer-deactivated), reassures that long-term-statistics history is preserved
- `notification_id` is per-VIN so multi-VIN accounts get one notification per removed vehicle
- Best-effort wrapped in try/except — notification failure must never block device removal

The log line was upgraded from `_LOGGER.info` to `_LOGGER.warning` since this represents user-impacting state change (entities will vanish on next render).

#### Year-rollover unit tests

**File:** `tests/test_v1170_datetime_boundaries.py`

**Pattern source:** Pycupra issue #33 (estimated-end timestamps showing the prior year).

Pre-emptive coverage for the recurring datetime-arithmetic bug class:
- `TestDateConversionBoundaries` (5) — sensor.py `device_class=DATE` conversion across year-end + leap day + ISO string parse + invalid input
- `TestWakeBudgetUtcMidnightReset` (2) — UTC date logic + 2025-12-31 23:30 UTC → 2026-01-01 00:30 UTC date comparison
- `TestConnectionStateTimestampBoundaries` (2) — `compute_connection_state` with naive vs tz-aware timestamps + year-end timestamp parsing roundtrip
- `TestDstTransitionParsing` (3) — Europe/Berlin spring-forward + fall-back as UTC offsets (no-ambiguity verification)

Total: 12 new tests. Don't cover every possible boundary, but cover the "if the bug exists, this would catch it" diagonal.

#### docs/FAQ.md (NEW)

End-user documentation, German + English mix. Sections:
- "What actually wakes the car?" — definitive answer (nothing about polling wakes the car) + table of which actions DO wake + Wake protection summary
- Privacy settings matrix (3-4 levels per backend → which entities degrade per level + step-by-step to change in app + troubleshooting)
- Daily API quota explanation with polls/day vs % quota table
- Reauthentication flow (and why NOT to remove-and-readd)
- Entity-ID stability policy (bug fix → keep ID, schema-change → new ID + 2-version deprecation)
- Read-only Mode explanation
- "My vehicle disappeared after a release" troubleshooting
- Bug-reporting workflow with diagnostics privacy reassurance
- Supported brands + regions table

This is the file users will be linked to from the README and from new GitHub issues.

#### docs/HACS-CHECKLIST.md (NEW)

Pre-condition audit for HACS Default Repository inclusion (planned v2.0.0). 7 sections, ~40 line items, each marked ✅ / ⚠️ / ❌ / 🔮:

- Repo structure (5 items, 3✅ 1⚠️ 1❌)
- Code quality (5 items, 4✅ 1⚠️)
- Config flow (4 items, 3✅ 1⚠️)
- Operational safety (12 items, 6✅ 4⚠️ 2❌ + 2🔮 push-related)
- CI / release (12 items, 9✅ 1❌ 2🔮)
- User-facing docs (5 items, 3✅ 1⚠️ 1❌)
- Outstanding for v2.0.0 prep (7 items)

Outstanding items list:
1. Per-vehicle log prefix
2. `requests_remaining_today` sensor
3. HTTP 500 "log once" pattern
4. PRIVACY.md
5. Live-Tests across all brands
6. EU Data Act readiness (Sep 2026 deadline)
7. CONTRIBUTING.md polish

#### New research doc in docs/research/

- **`vag-ha-integration-research.md`** — community research (project landscape + Skoda + MQTT freshness validation pattern + extended HACS checklist + 8 high-leverage contributions)

> *(Note: zwei zusätzliche pycupra research docs — `upstream-pycupra-notes.md` und `pycupra-deep-dive-2026-05-02.md` — wurden post-v1.17.0 vom Maintainer entfernt. Inhalt teilweise konsolidiert in `vag-ha-integration-research.md` und `cupra-bruno-endpoints-2026-05-02.md`.)*

Plus **`docs/upstream-contributions/wulfgar-pycupra-issues.md`** — 8 ready-to-post upstream issue drafts (no AI signature) for `WulfgarW/homeassistant-pycupra`:

1. async_step_reauth
2. requests_remaining_today sensor + repair issue
3. One-click "Retry login" actionable notification
4. Push dispatcher hardening (HANDLERS dict + unknown-type log + no-op + regression fixtures)
5. hassfest + hacs/action CI workflows
6. Year-rollover + DST unit tests
7. MQTT freshness validation pattern (myskoda PR #536 alignment)
8. FAQ.md privacy-setting matrix

#### Community: Bruno-Collection outreach

Discovered `Timwun/Cupra-WeConnect-Bruno-Collection` mid-session — 50+ verified OLA-Endpoint specs in Bruno API-Client format. Posted Issue #1 with heartfelt thank-you (German) + brand-tester invitation. Vollscan-agent extracts the complete catalog into `_private/research-archive/cupra-bruno-endpoints-2026-05-02.md` for v1.17.x / v1.18.0 implementation reference. Notably:

- `PUT /v1/users/vehicles/{vin}/destination` with full body — closes #36 Navigation in v1.17.x
- `POST /v1/vehicles/{vin}/auxiliary-heating/{start|stop}` — Webasto remote start as new SEAT/CUPRA feature
- `GET /v1/vehicles/{vin}/charging/battery-care` — completes our v1.15.0 cap-id work

#### Files modified

```
custom_components/vag_connect/
  const.py                          (poll defaults raised + reasoning comment)
  coordinator.py                    (_async_remove_stale_devices: persistent_notification + WARNING upgrade)
  manifest.json                     (1.16.1 → 1.17.0)

docs/
  FAQ.md                            (NEW — end-user FAQ)
  HACS-CHECKLIST.md                 (NEW — v2.0.0 prep audit status)
  research/
    vag-ha-integration-research.md  (NEW — community research)
    # (Note: upstream-pycupra-notes.md + pycupra-deep-dive-2026-05-02.md
    #  were added in v1.17.0 and removed by the maintainer post-merge.
    #  Content largely consolidated in vag-ha-integration-research.md
    #  and cupra-bruno-endpoints-2026-05-02.md.)
  upstream-contributions/
    wulfgar-pycupra-issues.md       (NEW — 8 ready-to-post issue drafts)

tests/
  test_v1170_datetime_boundaries.py (NEW — 12 year-rollover/DST/leap tests)
```

---

## [1.16.1] - 2026-05-02

### SEAT/CUPRA Climate Fix + #122 Scout-Paths / SEAT/CUPRA Climate 404 Fix + SEAT scout-paths

PATCH-Release. Hotfix nach Gerhard's v1.16.0 Test (#53) — climatisation 404 + #122 SEAT Scout-Report Add-On.

#### #53 SEAT/CUPRA Climate 404 Fix

**Symptom (Gerhard's log on CUPRA Born VIN ***003577):**
```
404 for https://ola.prod.code.seat.cloud.vwgroup.com/v2/vehicles/.../climatisation:
{"timestamp":"...","path":"/v2/vehicles/.../climatisation","status":404,
 "error":"Not Found","message":"No static resource v2/vehicles/.../climati..."}
```

**Root cause:** OLA backend rejects `POST /v2/vehicles/{vin}/climatisation` — the URL pattern doesn't have a Spring controller mapped. The action ("start"/"stop") must be in the URL path, not the body. Verified against `WulfgarW/pycupra/connection.py` — uses `API_CLIMATER + '/start'` template producing `/v2/vehicles/{vin}/climatisation/start`.

**Fix** (`cariad/api/seat_cupra.py`):

```python
async def command_start_climate(self, vin: str) -> None:
    await self._post_climatisation_action(vin, "start")

async def command_stop_climate(self, vin: str) -> None:
    await self._post_climatisation_action(vin, "stop")

async def _post_climatisation_action(self, vin: str, action: str) -> None:
    primary = f"{_BASE}/v2/vehicles/{vin}/climatisation/{action}"
    try:
        await self._post(primary, json={})
        return
    except APIError as err:
        if err.status != 404:
            raise
        # Fall back to legacy bare endpoint
    await self._post(
        f"{_BASE}/v2/vehicles/{vin}/climatisation",
        json={"action": action},
    )
```

**Defensive design** — same pattern as our CARIAD-BFF v1/v2 fallback:
- 404 on primary → try legacy URL with body action (in case any user actually was working with the legacy URL on different firmware)
- Non-404 errors propagate (Phase 2's `classify_command_failure` → `record_command_failure` records spin/subscription/etc properly)
- Empty body `{}` on the primary path-suffix variant — pycupra confirms no body is needed when action is in the URL

#### #53 Phase 3 Phantom-Button — Investigation, NOT yet fixed

**Symptom:** Gerhard's CUPRA Born still shows the flash button in v1.16.0 even though Capability-Filter Phase 3 (#56, shipped v1.13.0) should hide it. Pre-Phase-3 behavior was 72→71 entities after click (Phase 2 unavailable transition); now it stays at 75 entities (button stays "inactive" but persists).

**Hypotheses:**
1. OLA Capabilities-API responds with `honk-and-flash` `active=true` despite the actual command endpoint returning `400 missing-capability` — backend has stale capability metadata for his Born
2. `get_capabilities` silently fails for his account → cache empty → `command_capability_supported` returns `None` → button kept (conservative None default)
3. Cap-ID mismatch — our `cap_id_for("cupra", "command_flash")` returns `"honk-and-flash"`, real OLA might use a different ID for his Born

**Next step:** Diagnostics download requested from Gerhard. Need to inspect `vehicle_capabilities[VIN]` cache content to determine which hypothesis is correct. Fix in v1.16.2 once data arrives.

#### #122 SEAT Scout-Paths

**Source:** r1150gs Vehicle Data Scout report 2026-05-02 — 1 new field on `mycar` endpoint:

```
engines.primary  (3 keys, sample: {"3 keys"})
```

**Fix** (`cariad/_unexpected_keys.py` `EXPECTED_KEYS["cupra"]["mycar"]`):
```python
"engines",       # already registered (top-level) v1.10.2
"engines.primary",     # NEW — explicit
"engines.primary.*",   # NEW — wildcard
```

SEAT inherits via the table alias `EXPECTED_KEYS["seat"] = EXPECTED_KEYS["cupra"]` at the bottom of the file.

#### Tests

`tests/test_v1161_seat_cupra_climate_fix.py` — 2 test classes, 6 tests:

- `TestClimateEndpointFix` (4):
  - `test_start_uses_path_suffix_first` — verifies primary URL is `/climatisation/start` with empty body
  - `test_stop_uses_path_suffix_first` — same for stop
  - `test_falls_back_to_legacy_on_404` — 404 → second call with legacy URL + body action
  - `test_non_404_error_propagates_no_fallback` — 403 raises immediately, no fallback (Phase 2 stays in charge of error classification)
- `TestScoutPathsSeat` (2):
  - `test_engines_primary_registered` — both `engines.primary` + wildcard in cupra mycar set
  - `test_seat_inherits_via_alias` — paths resolve through SEAT's alias-to-cupra

#### Files modified

```
custom_components/vag_connect/
  cariad/_unexpected_keys.py      (+ engines.primary + engines.primary.* in cupra mycar)
  cariad/api/seat_cupra.py        (+ _post_climatisation_action helper +
                                   command_start_climate/stop_climate refactored)
  manifest.json                   (1.16.0 → 1.16.1)

tests/test_v1161_seat_cupra_climate_fix.py (NEW, 6 tests)
```

---

## [1.16.0] - 2026-05-02

### Cross-Brand UX + Skoda Charging Profiles / Cross-Brand UX + Skoda Charging Profiles

MINOR-Release. Long-standing UX gap geschlossen plus #25/#31 closure plus Cross-Brand OTA Probe-Plan dokumentiert für v1.17.0 Live-Test.

#### #26 HA `time` Plattform für Departure-Timer Editing

**Vorher:** `vag_connect.set_departure_timer` Service mit `departure_time` String-Parameter — User musste manuell Service-Call ausführen.

**Jetzt:** Pro VIN drei `time.{auto}_departure_timer_X_time_set` Entitäten — User editiert die Zeit direkt im HA Dashboard.

**Files:**
- `__init__.py` — `Platform.TIME` zur PLATFORMS-Liste (10. Plattform)
- `time.py` (NEW) — `VagDepartureTimerTime(VagConnectEntity, TimeEntity)`:
  - `native_value` parst `vehicle["departure_timer_X_time"]` defensive (HH:MM, HH:MM:SS, ISO datetime mit T-Splitter)
  - `async_set_value(value: time)` formattet zu `"HH:MM"` und ruft `coordinator.async_set_departure_timer(vin, timer_id, enabled=True, departure_time=hhmm)`
  - **UX**: setzen der Zeit aktiviert den Timer automatisch
- Kein neuer Service nötig — reused existierende set_departure_timer + dessen Capability-Phase-2-Bookkeeping + per-VIN-per-class-Lock
- Read-only Mode + Capability-Phase-3 Gating analog zu existierenden `VagDepartureTimerSwitch`

#### #25/#31 Skoda Charging Profiles Read-Only

**Endpoint** (verified `myskoda/models/chargingprofiles.py` + `rest_api.py`):
```
GET /api/v1/charging/{vin}/profiles
```

**Response shape:**
```json
{
  "chargingProfiles": [{
    "id": 1, "name": "Home",
    "settings": {
      "maxChargingCurrent": "MAXIMUM"|"REDUCED",
      "minBatteryStateOfCharge": {"minimumBatteryStateOfChargeInPercent": 20},
      "targetStateOfChargeInPercent": 80,
      "autoUnlockPlugWhenCharged": "PERMANENT"|"ON"|"OFF"
    },
    "preferredChargingTimes": [{"id": 1, "enabled": true,
       "startTime": "22:00", "endTime": "06:00"}],
    "timers": [{"id": 1, "enabled": false, "time": "07:30",
       "type": "RECURRING"|"ONE_OFF",
       "recurringOn": ["MONDAY", ...]}],
    "location": {"latitude": 47.39, "longitude": 8.21} | None
  }],
  "currentVehiclePositionProfile": {
    "id": 1, "name": "Home",
    "targetStateOfChargeInPercent": 80,
    "nextChargingTime": "22:00" | None
  } | None,
  "carCapturedTimestamp": "..." | None
}
```

**Why this closes #25 (location-based target SoC) elegantly:** the backend already decides which profile is active based on the vehicle's current GPS position via `currentVehiclePositionProfile`. We don't need to do client-side GPS-zone matching — Skoda's backend computes it for us.

**Files:**
- `cariad/api/skoda.py` — new `get_charging_profiles(vin)` method
- `cariad/models.py` — 5 new `VehicleData` fields (`active_charging_profile_name`, `active_charging_profile_target_soc_pct`, `next_charging_time`, `charging_profiles_count`, `charging_profiles: list`)
- `coordinator.py`:
  - New module-level pure function `_parse_charging_profiles(resp)` — flattens each profile to attr-friendly dict (drops nested objects that don't serialize cleanly), rounds GPS to 2 decimals, extracts `currentVehiclePositionProfile` to top-level fields
  - New method `refresh_charging_profiles(vin, force=False)` — brand-restricted to `skoda`, 1h cache via `_charging_profiles_fetched_at[vin]`, capability-gated via `command_capability_supported(vin, "command_charging_profiles") is False` early-return (cap-id `EXTENDED_CHARGING_SETTINGS` from v1.15.0)
  - Hooked into `_poll_loop` after Charging-History refresh
- `sensor.py`:
  - 4 new `VagSensorDescription` entries (`condition="electric"` for EV/PHEV gating, `_DATA_PRESENT_REQUIRED` for skip-if-None)
  - Extended `extra_state_attributes` on `VagConnectSensor` to surface flat `profiles` list on `active_charging_profile_name`

**Write-side deferred to v1.17.0+** — Number/Select entities for editing target_soc / max_charging_current / auto_unlock_plug per profile would need POST/PUT endpoint research + own bundle.

#### Cross-Brand OTA Probe Plan

**File:** `docs/RESEARCH_NOTES_2026-05-02_OTA_PROBE.md` (NEW)

Documents concrete `curl` probes for CARIAD-BFF (Audi+VW EU) + OLA (SEAT/CUPRA) `software-version/update-status` endpoints. Live-Tester asks documented (Audi 2024+ with Plus, VW ID.4/5/7, CUPRA Born/Tavascan, SEAT Mii electric / Tarraco e-Hybrid). Probe is read-only and safe (`GET` with valid Bearer token, no vehicle-side effects).

Adoption plan post-probe: ~2h implementation per backend if endpoint returns 200 (parser is already shape-tolerant from v1.15.0 Skoda implementation, just need to extend the brand client + remove `_DATA_PRESENT_REQUIRED` gating + add cap-id).

#### Translations

8 Sprachen — neue keys:
- `entity.sensor.{active_charging_profile_name, active_charging_profile_target_soc_pct, next_charging_time, charging_profiles_count}`
- **NEW** `entity.time` block with `departure_timer_{1,2,3}_time_set` keys

#### Tests

`tests/test_v1160_cross_brand_skoda_endpoints.py` — 4 test classes, ~20 tests:
- `TestDepartureTimerTimeEntity` (7) — native_value defensive parsing (HH:MM / HH:MM:SS / ISO datetime / garbage / None) + async_set_value dispatches with auto-enable
- `TestParseChargingProfiles` (5) — flat profiles + currentVehiclePositionProfile extracted + missing-current → no active fields + garbage tolerance + empty
- `TestGetChargingProfilesURL` (1) — URL pattern
- `TestRefreshChargingProfilesBrandRestriction` (4) — non-skoda brand skip + skoda merges into vehicle dict + capability-False skip + 1h cache
- `TestOtaProbeDocsExist` (2) — sanity that the planning docs file is present + lists both backend probe URLs

#### Files modified

```
custom_components/vag_connect/
  __init__.py                     (+ Platform.TIME)
  cariad/api/skoda.py             (+ get_charging_profiles method)
  cariad/models.py                (+ 5 charging-profiles fields)
  coordinator.py                  (+ _parse_charging_profiles pure function
                                   + refresh_charging_profiles helper
                                   + poll-loop hook)
  manifest.json                   (1.15.0 → 1.16.0)
  sensor.py                       (+ 4 charging-profile sensors
                                   + _DATA_PRESENT_REQUIRED + profiles-as-attrs)
  strings.json                    (+ 4 sensor names + entity.time block 3 keys)
  time.py                         (NEW — HA time platform implementation)
  translations/{de,en,fr,es,cs,nl,pl,sv}.json (mirrored)

docs/RESEARCH_NOTES_2026-05-02_OTA_PROBE.md (NEW — Cross-Brand OTA Probe planning)

tests/test_v1160_cross_brand_skoda_endpoints.py (NEW, ~20 tests)
```

---

## [1.15.0] - 2026-05-02

### Skoda Modernization Bundle / Skoda Modernization Bundle

MINOR-Release. Komplette Adoption der **myskoda Upstream-Updates** seit unserem PR #832 / Issue #976 Cutoff (April 2026). Research-Sweep deckte 22 PRs gemerged 2026-03 → 2026-04 ab.

#### Cross-Brand UX (#26/#25/#31) deferred — honest scoping

Bundle 3 (Cross-Brand UX per `RESEARCH_NOTES_2026-05-02.md`) wurde realistisch zu v1.16.0 verschoben:
- #26 braucht eigene HA `time`/`datetime` Plattform-Erweiterung (10. Plattform — nicht-trivial)
- #25/#31 brauchen `/v1/charging/{vin}/profiles` Endpoint-Schema-Research

Stattdessen v1.15.0 fokussiert auf was JETZT lieferbar ist aus dem myskoda-Research.

#### #35 Skoda Charging History → HA Energy Dashboard

**Endpoint** (verified myskoda `models/charging_history.py` + `rest_api.py`):
```
GET /api/v1/charging/{vin}/history?userTimezone=UTC&limit=50
```

**Response shape:**
```json
{
  "nextCursor": "<ISO datetime>" | null,
  "periods": [
    {"totalChargedInKWh": 12.5, "sessions": [
      {"startAt": "2026-04-29T08:00:00Z", "chargedInKWh": 12.5,
       "durationInMinutes": 45, "currentType": "AC"|"DC"},
      ...
    ]},
    ...
  ]
}
```

**Files:**
- `cariad/api/skoda.py` — new `get_charging_history(vin, limit=50)` method
- `cariad/models.py` — 6 new fields on VehicleData (`total_charged_energy_kwh`, `last_charging_session_kwh`, `last_charging_session_duration_min`, `last_charging_session_current_type`, `last_charging_session_start`, `recent_charging_sessions: list`)
- `coordinator.py`:
  - New module-level pure function `_parse_charging_history(resp)` — sums `chargedInKWh` across all sessions in all periods, sorts by `startAt` desc for last-session fields, builds `recent_charging_sessions` list capped at 5
  - New method `refresh_charging_history(vin, force=False)` — brand-restricted to `skoda` (CARIAD-BFF + OLA equivalent unverified), 1h cache via `_charging_history_fetched_at[vin]`, capability-gated via `command_capability_supported(vin, "command_charging_history") is False` early-return
  - Hooked into `_poll_loop` after Trip-Stats refresh as best-effort gather
- `cariad/_capabilities.py` — `command_charging_history` → `CHARGING` cap-id added to skoda map
- `sensor.py`:
  - 3 new `VagSensorDescription` entries (`condition="electric"` for EV/PHEV gating):
    - `total_charged_energy_kwh` with `device_class=ENERGY` + `state_class=TOTAL_INCREASING` (HA Energy Dashboard signal)
    - `last_charging_session_kwh` with `device_class=ENERGY` + `state_class=MEASUREMENT`
    - `last_charging_session_duration_min` with `state_class=MEASUREMENT`
  - All 3 keys added to `_DATA_PRESENT_REQUIRED` so non-Skoda vehicles + Skoda accounts without entitlement skip entity creation
  - Extended `extra_state_attributes` on `VagConnectSensor` to surface `recent_charging_sessions` + `last_session_current_type` on `total_charged_energy_kwh`

#### Skoda Software-Version + OTA Status (myskoda PR #541)

**Endpoint:** `GET /api/v1/vehicle-information/{vin}/software-version/update-status` (Skoda app v8.10.0+)

**Response schema** (verified `myskoda/models/software_status.py`):
- `status` — enum: `NO_UPDATE_AVAILABLE`, `UPDATE_SUCCESSFUL` (case-insensitive); more values likely server-side
- `currentSoftwareVersion` — string (e.g. `"3.8"`)
- `carCapturedTimestamp` — ISO 8601 datetime, nullable
- `releaseNotesUrl` — string URL, nullable

**Files:**
- `cariad/api/skoda.py::get_status` — extended `gather()` with the new endpoint as 8th item, parses into `software_*` + `ota_*` fields. Best-effort: 404 (older firmware) / 403 (no entitlement) → exception in `return_exceptions=True` and we leave fields `None`.
- `cariad/models.py` — 4 new fields: `software_version`, `software_update_status` (raw enum string), `ota_update_available` (bool derived), `ota_release_notes_url`
- `sensor.py` — new `software_version` `VagSensorDescription` (DIAGNOSTIC category), gated via `_DATA_PRESENT_REQUIRED`
- `binary_sensor.py` — new `ota_update_available` description (`device_class=UPDATE`), gated via `_DATA_PRESENT_REQUIRED`. New `extra_state_attributes` override on `VagConnectBinarySensor` exposing `release_notes_url` + `raw_status` for the OTA sensor.
- Forward-compat: unknown `status` enum values (e.g. `UPDATE_IN_PROGRESS`) treated as "update happening" (`ota_update_available=True`) so we don't have to ship a release for every new server enum.

**Cross-brand support deferred** — Research 2026-05-02 confirmed CARIAD-BFF (Audi+VW EU) and OLA (SEAT/CUPRA) don't yet expose an equivalent endpoint. v1.16.0 will probe with Live-Tests.

#### Capability-Map Skoda Extensions

8 new cap-ids in `CAPABILITY_MAP["skoda"]` (from myskoda Upstream cap-vocabulary discovery):
- `command_software_update` → `VEHICLE_HEALTH_INSPECTION` (OTA via vhi)
- `command_charging_history` → `CHARGING` (umbrella cap)
- `command_charging_profiles` → `EXTENDED_CHARGING_SETTINGS`
- `command_driving_score` → `DRIVING_SCORE`
- `command_readiness` → `READINESS`
- `command_plug_and_charge` → `PLUG_AND_CHARGE`
- `command_route_planning` → `EV_ROUTE_PLANNING`
- `command_battery_charging_care` → `BATTERY_CHARGING_CARE`

These are read-only / metadata capabilities; no command bindings yet. Phase 3 churn-prevention so future entities (driving-score sensors, route-planning, etc.) can resolve cleanly.

#### Capability-Status Tolerance

`vehicle_supports_capability` extended:
- **Top-level `errors[]` array** on the capabilities response (myskoda PR #543 schema). Values: `MISSING_RENDER`, `UNAVAILABLE_SERVICE_PLATFORM_CAPABILITIES`, `UNAVAILABLE_SOFTWARE_VERSION`. When present + non-empty → bail to `None` so we don't falsely gate every entity.
- **New transient-state status values**: `INSUFFICIENT_BATTERY_LEVEL`, `LOCATION_DATA_DISABLED`, `VEHICLE_DISABLED`. Documented; treated uniformly as "right now no" (gated). Future work could distinguish transient (battery, location) vs permanent (license) for richer UX hints.

#### Diagnostics Anonymize Hardening (myskoda `anonymize.py` patterns)

**`_mask_location_qs`** — scrubs `latitude=...&longitude=...` from URL query strings (e.g. mysmob `/maps/positions?latitude=48.13&longitude=11.57`). Previous dict-key-based `_scrub` couldn't catch these because lat/lon were inside string values. Mode-aware: `gps_round=True` rounds to 1 decimal (~11 km granularity), keeps URL valid for log debugging; default `False` mode replaces with `REDACTED` markers.

```python
_LOCATION_QS_RE = re.compile(
    r"(latitude=)(-?\d+\.?\d*)(&\s*longitude=)(-?\d+\.?\d*)",
    re.IGNORECASE,
)
```

**`_stable_hash`** — SHA-256 truncated to 12 hex chars with `vag-connect-ha` salt. Pattern from `myskoda/anonymize.py`. Lets a repeat reporter cross-link ("oh this is the same Skoda user as last week's bug ticket") without revealing real ID.

**`_HASH_KEYS` frozenset** — `user_id`, `userId`, `account_id`, `accountId` go through `_stable_hash` (output `sha256:abc123def456`) instead of bare `**REDACTED**`. Repeat reporters get the same hex digest = cross-linkable across diagnostics dumps.

**String-value chain** — `_scrub` for string values now chains `_mask_email` → `_mask_location_qs(masked, gps_round=...)` so log lines / error messages get both treatments.

#### Tests

`tests/test_v1150_skoda_modernization.py` — 5 test classes, ~30 tests:
- `TestParseChargingHistory` (5) — kWh sum, sort-by-startAt desc, recent_sessions cap, garbage tolerance, empty response
- `TestGetChargingHistoryURL` (2) — URL pattern + default/custom limit param
- `TestRefreshChargingHistoryBrandRestriction` (4) — non-skoda brand skip, skoda merges into vehicle dict, capability-False skips, 1h cache window
- `TestSoftwareVersionParsing` (2) — NO_UPDATE_AVAILABLE → False, unknown enum → True (forward-compat)
- `TestLocationQueryStringScrub` (4) — REDACTED mode + 1-decimal round mode + no-op when no lat + negative coords
- `TestStableHash` (4) — deterministic + different inputs → different hashes + empty input + salt-changes-output
- `TestUserIdHashingInScrub` (4) — user_id sha256 prefix, accountId same, repeat-stability, embedded URL scrub
- `TestSkodaCapabilityMap` (8 parametrized + 1 sanity) — all new cap-ids resolve correctly + existing v1.13.0 caps unchanged
- `TestCapabilityStatusTolerance` (3 parametrized + 3) — `errors[]` block returns None + empty errors normal path + transient status values (`INSUFFICIENT_BATTERY_LEVEL` / `LOCATION_DATA_DISABLED` / `VEHICLE_DISABLED`) treated as gated

#### Files modified

```
custom_components/vag_connect/
  binary_sensor.py                (+ ota_update_available description + extra_state_attributes for release_notes_url)
  cariad/_capabilities.py         (+ 8 new Skoda cap-ids + extended docstrings)
  cariad/api/skoda.py             (+ get_charging_history method + software-version endpoint in get_status gather + parser block)
  cariad/models.py                (+ 4 OTA fields + 6 Charging History fields)
  coordinator.py                  (+ _parse_charging_history pure function + refresh_charging_history helper
                                   + poll-loop hook + vehicle_supports_capability errors[] tolerance)
  diagnostics.py                  (+ hashlib import + _LOCATION_QS_RE + _mask_location_qs + _stable_hash
                                   + _HASH_KEYS frozenset + user_id/account_id hashing in _scrub
                                   + string-value chain for query-string GPS scrub)
  manifest.json                   (1.14.0 → 1.15.0)
  sensor.py                       (+ software_version + 3 charging-history sensors + extra_state_attributes
                                   for recent_charging_sessions)
  strings.json                    (+ 4 sensor names + 1 binary_sensor name)
  translations/{de,en,fr,es,cs,nl,pl,sv}.json
                                  (mirrored)

tests/test_v1150_skoda_modernization.py (NEW, ~30 tests)
```

---

## [1.14.0] - 2026-05-02

### Audi Feature Pack Bundle / Audi Feature Pack Bundle

MINOR-Release. Bundle 2 aus `docs/RESEARCH_NOTES_2026-05-02.md`. Drei Audi-spezifische Features in einem Release plus Skoda Scout-Pfade #116 als Add-On.

#### #24 Trip Statistics für VW EU + Audi

**Endpoint:** `GET https://emea.bff.cariad.digital/vehicle/v1/vehicles/{vin}/tripstatistics?type={shortTerm|longTerm}` (verified in audi_connect_ha + audiconnectpy + ioBroker/vw-connect, see RESEARCH_NOTES_2026-05-02 §Bundle 2 #24).

**Response shape:**
```json
{"tripDataList": {"tripData": [
  {"tripID": ..., "tripType": "shortTermReset",
   "timestamp": "2026-04-28T17:42:11Z",
   "mileage": 23, "startMileage": 41205, "overallMileage": 41228,
   "traveltime": 31, "averageSpeed": 44,
   "averageFuelConsumption": 68,           // ×10 — divide
   "averageElectricEngineConsumption": 0}, // ×10 — divide
  ...
]}}
```

**Files:**
- `cariad/api/vw_eu.py` — new `get_trip_statistics(vin, kind="shortTerm")` method (Audi inherits via `AudiClient(VWEUClient)`)
- `cariad/models.py` — extended `VehicleData` with 9 new fields:
  - `last_trip_distance_km`, `last_trip_duration_min`, `last_trip_avg_speed_kmh`
  - `last_trip_avg_fuel_consumption_l_100km`, `last_trip_avg_electric_consumption_kwh_100km`
  - `last_trip_timestamp`
  - `lifetime_distance_km`, `lifetime_avg_fuel_consumption_l_100km`, `lifetime_avg_electric_consumption_kwh_100km`
  - `recent_trips: list[dict]` (last 5)
- `coordinator.py`:
  - New module-level pure function `_parse_trip_statistics(short_resp, long_resp)` — sort by `overallMileage` desc, take `[0]`, divide consumption fields by 10, build `recent_trips` list capped at 5.
  - New method `refresh_trip_statistics(vin, force=False)` — brand-restricted to `audi`/`volkswagen`, 1h cache via `_trip_stats_fetched_at[vin]`, capability-gated via `command_capability_supported(vin, "command_trip_stats") is False` early-return, parallel `gather()` for shortTerm + longTerm.
  - Hooked into `_poll_loop` after `_async_push_update` as best-effort gather (never blocks polling).
- `cariad/_capabilities.py` — added `"command_trip_stats": "tripStatistics"` to `volkswagen` map (audi inherits via copy in line below).
- `sensor.py`:
  - 4 new `VagSensorDescription` entries with `state_class=MEASUREMENT`, conditional gating (`combustion`/`electric`)
  - New `_TRIP_STATS_KEYS` + `_TRIP_STATS_BRANDS` frozenset for setup-time gating (skip 4 sensors entirely on non-CARIAD brands so SEAT/CUPRA/Skoda/Porsche/VW NA don't get phantom "unknown" entities)
  - New `extra_state_attributes` override on `VagConnectSensor` to surface `recent_trips` on the `last_trip_distance_km` sensor (audi #113 "aggregate-in-state" + 255-char state limit avoidance).

#### #28 Audi ICE Remote Engine Start/Stop

**Source:** arjenvrh/audi_connect_ha PR #717 — confirmed via `gh pr diff 717` (Research Notes §Bundle 2 #28).

**Endpoints:**
- `PUT /vehicle/v1/engine/{VIN}/userpromptproof` (S-PIN) → `{"userPromptProof": "..."}` at top-level
- `POST /vehicle/v1/engine/{VIN}/start` with `{"securedActivationData": <token>, "spin": <pin>}`
- `POST /vehicle/v1/engine/{VIN}/stop` with no body, no S-PIN

Note: path is `/vehicle/v1/engine/{vin}/...` — NOT `/vehicle/v1/vehicles/{vin}/engine/...`. VIN must be uppercased in URL (upstream PR explicitly does `vin.upper()`).

**Files:**
- `cariad/api/audi.py`:
  - New constant `_ENGINE_BASE = "https://emea.bff.cariad.digital/vehicle/v1/engine"`
  - New method `command_engine_start(vin, spin="")` — raises `SpinError` if no PIN, two-step flow with proof extraction
  - New method `command_engine_stop(vin)` — single POST, no body
  - Uses `self._request("PUT", ...)` for step 1 (base.py only exposes `_get`/`_post` helpers; PUT goes via `_request`)
- `cariad/_capabilities.py`:
  - **Audi inheritance changed from alias to copy** — `CAPABILITY_MAP["audi"] = dict(CAPABILITY_MAP["audi"])` so audi-only patches don't pollute VW EU's table
  - Added `"command_engine_start": "engineRemoteStart"` + `"command_engine_stop": "engineRemoteStart"` to audi (NOT to volkswagen). ⚠️ [Inference] cap-id, no Live-Capabilities-Response yet.
- `coordinator.py`:
  - `_COMMAND_CLASS` registry extended with `command_engine_start`/`command_engine_stop` → `"engine"` class (start/stop serialize via shared lock)
  - New methods `async_engine_start(vin)` + `async_engine_stop(vin)` wrapping `_cariad_cmd`
- `__init__.py`:
  - New service handlers `_handle_engine_start` + `_handle_engine_stop` (both go through `_coord_writeable` for Read-only Mode v1.13.0 protection)
  - Service registry: `engine_start` + `engine_stop` with `SERVICE_VIN_SCHEMA`
  - `async_unload_entry` removes the new services on unload
- `services.yaml` — descriptions for `engine_start`/`engine_stop` documenting two-step flow + S-PIN-from-config

#### #29 PPE/PPC Climate Body conditional

**Body shape difference (verified from audi_connect_ha PR #644 + #677):**

Legacy MQB:
```json
{"targetTemperature": 21.0, "targetTemperatureUnit": "celsius",
 "climatisationWithoutExternalPower": true, "windowHeatingEnabled": true}
```

PPE/PPC (Q6/A6 e-tron, RS e-tron GT Facelift, A3 2024+ PHEV):
```json
{"climatisationMode": "comfort",            // MANDATORY, not null
 "climatisationWithoutExternalPower": true,
 "windowHeatingEnabled": true
 // targetTemperature* OMITTED — body validator rejects PPE otherwise
}
```

**Files:**
- `const.py` — new `CONF_FORCE_PPE_CLIMATE = "force_ppe_climate"`
- `cariad/api/vw_eu.py` — `command_start_climate(vin, ppe_mode: bool = False)` with conditional fallback-payload. Default `False` = legacy body (backwards-compat for all existing callers).
- `coordinator.py` — `async_start_climatisation(vin)` reads `CONF_FORCE_PPE_CLIMATE` from options/data (Audi-only), passes `ppe_mode=True` as kwarg when set.
- `config_flow.py` — extended OptionsFlow with `force_ppe_climate` boolean toggle.
- `strings.json` + 8 translations — option label + helper text describing PPE eligibility.

**Why user-overridable instead of auto-detected:**
- audi_connect_ha has `api_level` user-toggle (issues #677, #706 show even that is fragile across vehicles)
- No public PPE compatibility list — guessing from VIN/model/year would mis-fire
- Hard Rule #15: "do not endpoint-guess for PPC/PPE — risks Audi account suspension"
- Body-shape-changes on a known endpoint are safer than endpoint-guessing — server-validated

#### #116 Skoda Scout-Pfade (MavericklCS, fourth community Scout-Report)

`cariad/_unexpected_keys.py` — extensions to `EXPECTED_KEYS["skoda"]`:

```python
"driving-range": {
  ...
  # v1.14.0 (#116, MavericklCS Scout-Report 2026-05-01)
  "primaryEngineRange.engineType",
  "primaryEngineRange.currentSoCInPercent",
  "primaryEngineRange.currentFuelLevelInPercent",
  "primaryEngineRange.remainingRangeInKm",
},
"maintenance": {
  ...
  # v1.14.0 (#116, MavericklCS) — predictiveMaintenance.setting (4 keys observed)
  "predictiveMaintenance.setting",
  "predictiveMaintenance.setting.*",
}
```

`primaryEngineRange.currentSoCInPercent` on a `engineType: "gasoline"` vehicle is unusual — likely the 12V starter battery SoC (paralleling our v1.12.0 #23 `voltage_12v` work). Wait for next Scout-Report with vehicle-model context before wiring as a sensor.

#### Translations

8 Sprachen — neue keys:
- `entity.sensor.{last_trip_distance_km, last_trip_avg_speed_kmh, last_trip_avg_fuel_consumption_l_100km, last_trip_avg_electric_consumption_kwh_100km}` — sensor display names
- `options.step.init.data.force_ppe_climate` (label) + `data_description.force_ppe_climate` (helper text)

Service descriptions for `engine_start` + `engine_stop` live in `services.yaml` (German, no per-language file expansion yet).

#### Tests

`tests/test_v1140_audi_pack.py` — 19 new tests, six classes:
- `TestParseTripStatistics` (6) — pure parser exercises sort, ×10 division, recent_trips cap, garbage tolerance
- `TestGetTripStatisticsURL` (1) — URL + `type` query param
- `TestRefreshTripStatisticsBrandRestriction` (4) — non-CARIAD brand skip, audi makes 2 calls, capability-False skips, 1h cache window
- `TestAudiEngineStart` (5) — two-step flow body shapes, VIN uppercase, no-S-PIN raises, missing-proof raises, stop endpoint
- `TestPpcClimateBody` (3) — legacy body / PPE body / default-legacy backwards-compat
- `TestCapabilityMapEngineStart` (4) — Audi has, VW does not, copy-not-alias verification, trip_stats cap
- `TestScoutPathsSkoda` (2) — `primaryEngineRange.*` + `predictiveMaintenance.setting.*` registered
- `TestEngineCommandClass` (1) — engine class shared between start/stop

#### Files modified

```
custom_components/vag_connect/
  __init__.py                     (+ engine_start/engine_stop services)
  cariad/_capabilities.py         (audi inheritance copy + engine + trip_stats cap-ids)
  cariad/_unexpected_keys.py      (+ #116 Skoda scout paths)
  cariad/api/audi.py              (+ command_engine_start/stop + _ENGINE_BASE constant)
  cariad/api/vw_eu.py             (+ get_trip_statistics + ppe_mode kwarg on command_start_climate)
  cariad/models.py                (+ 9 trip-stats fields + recent_trips list)
  config_flow.py                  (+ CONF_FORCE_PPE_CLIMATE option in OptionsFlow)
  const.py                        (+ CONF_FORCE_PPE_CLIMATE)
  coordinator.py                  (+ _parse_trip_statistics module fn + refresh_trip_statistics
                                   + _COMMAND_CLASS engine entries
                                   + async_engine_start/_stop helpers
                                   + ppe_mode wiring in async_start_climatisation
                                   + trip stats refresh in poll loop)
  manifest.json                   (1.13.0 → 1.14.0)
  sensor.py                       (+ 4 trip-stats sensors + _TRIP_STATS_BRANDS
                                   + extra_state_attributes for recent_trips)
  services.yaml                   (+ engine_start/engine_stop blocks)
  strings.json                    (+ 4 sensor names + force_ppe_climate option)
  translations/{de,en,fr,es,cs,nl,pl,sv}.json
                                  (+ same as strings.json mirrored)

tests/test_v1140_audi_pack.py     (NEW, 19 tests)
```

---

## [1.13.0] - 2026-05-02

### Production Hardening Bundle / Production Hardening Bundle

MINOR-Release. Drei P0-Themen aus dem Backlog (#56/#63/#62) plus Process-Docs (#64) in einem Release. Kein Breaking-Change — alles additive Hardening + Backwards-Compat-Aliase wo Service-Renames stattfinden.

**Pre-Implementation Research:** `docs/RESEARCH_NOTES_2026-05-02.md` (423 Zeilen) deckt 13 Issues über 3 Bundles ab. Verdict-Tabelle ✅/⚠️/❌ pro Issue. Bundle 2 (v1.14.0 Audi Pack: #24/#29/#28) und Bundle 3 (v1.15.0 Cross-Brand UX: #26/#25/#31 read-only) sind ebenfalls bereits gescoped.

#### #56 Capability-Filter Phase 3 — PRE-Entity-Creation Gating

**Vorher (Phase 1+2, bis v1.12.3):**
- Phase 1 (v1.8.2): Capabilities werden bei Setup gecached (`coordinator._capabilities[vin]`)
- Phase 2 (v1.9.1): Wenn ein Command `403 spin_error` / `subscription` / `not_entitled` zurückgibt, wird `FeatureState[vin][command]` geschrieben → `vehicle_supports_capability` nutzt Phase-2-FeatureState bei `available` zu prüfen → Entity geht unavailable. Aber: Entity wurde erstellt, der User sieht "unavailable" und versteht nicht warum.

**Nachher (Phase 3, v1.13.0):** Entity wird gar nicht erst erstellt wenn das Backend sagt "kann das Auto nicht".

**Neue Datei** `custom_components/vag_connect/cariad/_capabilities.py`:
- `CAPABILITY_MAP: dict[brand, dict[command_id, cap_id]]`
- Brands: `volkswagen` (CARIAD camelCase wie `parkingLights`, `honkAndFlash`), `audi` erbt via `CAPABILITY_MAP["audi"] = CAPABILITY_MAP["volkswagen"]`, `cupra` (OLA kebab-case), `seat` erbt via Alias, `skoda` (mysmob kebab-case), `volkswagen_na` (empty — keine Cap-API), `porsche` (empty)
- `cap_id_for(brand, command_id) → str | None` pure lookup, defensiv

**Coordinator-Erweiterungen** (`coordinator.py`):
- `command_capability_supported(vin, command_id) → bool | None`
  - Tri-state: `True` (definitiv yes), `False` (definitiv no), `None` (unknown — keep entity)
  - Konservatives `None`: für Brands ohne Cap-Mapping (Porsche, VW NA) wird die Entity erstellt; Phase 2 fängt Runtime-Failures dann weiter ab
- `vehicle_supports_capability` mit Skoda-Schema-Toleranz erweitert:
  - `entry.get("active") is False` → False
  - `entry.get("user-enabled") is False` → False
  - `entry.get("license-issue")` truthy → False (Lizenz-Problem)

**Skoda Cap-Endpoint** (`cariad/api/skoda.py` neu hinzugefügt):
- `get_capabilities(vin)` → `GET /api/v1/vehicle-access/{vin}/capabilities`
- Response shape: `{capabilities: [{id, active, editable?, user-enabled?, status?, license-issue?, parameters?}]}` — anders als CARIAD-BFF `{id, status}`. Die zusätzlichen Skoda-Felder werden in `vehicle_supports_capability` mitgenommen (siehe oben).

**Platform-Gating** (alle command-sendenden Plattformen):
- `lock.py`, `climate.py`, `number.py`, `switch.py`, `button.py` checken `coordinator.command_capability_supported(vin, command_id) is not False`
- `number.py` hat lokales `_CMD_ID` dict mapping `desc.key → command_id`
- `switch.py` hat lokales `_supported(vin, cmd)` helper
- `button.py` hat den alten `_BRANDS_WITH_CAPABILITY_GATING` Allowlist gelöscht (uniform helper für alle Brands)

#### #63 Phase 2/3 — Read-only Mode Service-Side + Cloud-Refresh-Distinction + 5-min Cooldown + per-VIN Lock

**Phase 1 Recap (v1.12.0):** Read-only Mode skippt platform setup für lock/switch/button(non-refresh)/climate/number. Refresh-button bleibt (User darf Daten pullen).

**Phase 2 (v1.13.0) — Service-Side Enforcement:**
- Neue `_coord_writeable(vin)` Helper in `__init__.py`:
  ```python
  def _coord_writeable(coord, vin):
      if coord.read_only_mode:
          raise ServiceValidationError(
              translation_domain=DOMAIN,
              translation_key="read_only_mode_active",
          )
  ```
- Eingebaut in alle Command-Handler: `_handle_lock/_handle_unlock/_handle_start_clim/_handle_stop_clim/_handle_start_charge/_handle_stop_charge/_handle_start_window/_handle_stop_window/_handle_wake/_handle_flash/_handle_set_target_soc/_handle_set_clim_temp/_handle_set_departure_timer`
- Schützt vor Automatisierungen die direkt Services aufrufen (Bypass von Entity-Verstecken). Vorher konnte ein YAML-`service: vag_connect.command_lock` durch read-only durchschlüpfen.

**Phase 3 (v1.13.0) — Cloud-Refresh vs. Wake-Vehicle Distinction:**
- Neuer Service-Alias `refresh_cloud_cache` für `refresh_vehicle`. Macht klar: kein Wake, nur Cloud-Polling. `services.yaml` hat dafür eine eigene description-Sektion.
- Backwards-compat: `refresh_vehicle` bleibt als Service registriert (`async_register("refresh_vehicle", _handle_refresh)` plus `async_register("refresh_cloud_cache", _handle_refresh_cloud_cache)` mit identischem Body).

**Phase 3 (v1.13.0) — 5-min Wake-Cooldown pro VIN:**
- Konstante `_WAKE_COOLDOWN = timedelta(minutes=5)` in `coordinator.py`
- Per-VIN `_wake_last_at: dict[str, datetime]` State
- `async_wake_vehicle(vin)` checkt VOR dem 3/Tag Budget-Check:
  ```python
  if (last := self._wake_last_at.get(vin)) is not None:
      remaining = _WAKE_COOLDOWN - (now - last)
      if remaining > timedelta(0):
          raise ServiceValidationError(
              translation_domain=DOMAIN,
              translation_key="wake_cooldown_active",
              translation_placeholders={
                  "remaining_s": str(int(remaining.total_seconds())),
                  "cooldown_min": str(int(_WAKE_COOLDOWN.total_seconds() // 60)),
              },
          )
  ```
- `_wake_last_at[vin] = now` wird nach erfolgreichem Wake gesetzt (gleiche Stelle wo `_wake_count[vin]` inkrementiert wird).
- Schützt vor Click-Spam-Loops (User klickt 5× in Folge "Wake").

**Phase 3 (v1.13.0) — Per-VIN Per-Command-Class asyncio.Lock mit Timeout:**
- Konstante `_COMMAND_LOCK_TIMEOUT = 60.0` Sekunden in `coordinator.py`
- `_COMMAND_CLASS: dict[str, str]` mappt command_method → command_class (lock/climate/charge/window/wake/flash/refresh/set_value)
- `_get_command_lock(vin, command_class) → asyncio.Lock` lazy creation in `self._command_locks[(vin, command_class)]`
- `is_command_in_flight(vin, command_class) → bool` checkt `lock.locked()`
- `_cariad_cmd` wraps in `asyncio.timeout(60) + asyncio.Lock`:
  ```python
  command_class = _COMMAND_CLASS.get(method)
  if command_class is None:
      return await self._dispatch_cmd_locked(...)  # Fallback for unknown
  lock = self._get_command_lock(vin, command_class)
  async with asyncio.timeout(_COMMAND_LOCK_TIMEOUT):
      async with lock:
          return await self._dispatch_cmd_locked(...)
  ```
- `_dispatch_cmd_locked` ist die extracted Original-Logic.
- Verhindert: zwei `lock_doors` Klicks gleichzeitig (zweiter wartet bis erster fertig), `start_climatisation` + `stop_climatisation` overlap (sequenziell).
- Timeout-Fallback: hängt ein Command 60s+ → `asyncio.TimeoutError` → die wartende Command läuft weiter (kein Deadlock).

#### #62 Anonymized Diagnostics-Export Polish

**Token-Redaction expanded** (`diagnostics.py:_REDACT_KEYS`):
- Neu: `access_token`, `refresh_token`, `id_token`, `accessToken`, `refreshToken`, `idToken`, `client_secret`, `clientSecret`
- Zentralisiert die Redaction-Liste; vorher waren manche Token-Varianten nicht abgedeckt.

**Email Partial-Mask** (`diagnostics.py`):
- `_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+(\.[A-Za-z]{2,})")`
- `_mask_email(value)` → `f"{m.group(1)}***@***{m.group(2)}"` ⇒ `prash@gmail.com` → `p***@***.com`
- Erlaubt Identifizierung des Reporters wenn er sich später meldet (1. Buchstabe + TLD), ohne PII an die Öffentlichkeit zu geben.

**GPS Opt-In Rounding** (`diagnostics.py:_scrub`):
- Neuer Parameter `gps_round=False` in `_scrub`
- Wenn `True`: Lat/Lon Felder werden auf 1 Dezimalstelle gerundet (~11km Granularität)
- `async_get_config_entry_diagnostics` derived `gps_round` aus `not entry.options.get(CONF_ENABLE_REVERSE_GEOCODING, False)` — wer Reverse-Geocoding aktiv hat, hat volle Genauigkeit bereits akzeptiert

#### #64 Process & Governance

**`.github/ISSUE_TEMPLATE/scout_report.yml`** (NEU):
- YAML form für Vehicle Data Scout Reports (1-klick pre-fill aus HA Repair-Issue)
- Fields: brand-Picker (8 Brands), vehicle-Modell+Year, vag_connect_version, scout_report markdown (multi-line), privacy_confirm (checkbox)

**`.github/ISSUE_TEMPLATE/error_report.yml`** (NEU):
- YAML form für Error Reporter Dumps aus v1.9.0 Reporter Pipeline
- Fields wie scout_report + error_summary + reporter_dump markdown

**`BRAND_CAPTAINS.md`** (NEU, root):
- Initial Brand Captains Tabelle (aktuell nur Maintainer)
- "Bewährte Tester" Tabelle: Gerhard2808 (CUPRA Born), tritanium73 (Skoda), DnnsJp74 (Audi)
- "Wie werde ich Captain?" Anleitung — Captain darf Issues triagieren für seine Brand, kriegt Code-Review-Priorität
- Captain duties + Privacy notes (kein VIN/Email/Token/GPS in Issues teilen)

#### Translations

8 Sprachen (de/en/fr/es/nl/pl/cs/sv) — neue Keys in `exceptions:`:
- `wake_cooldown_active` mit `{remaining_s}` + `{cooldown_min}` placeholders
- `read_only_mode_active`

Bug-Fix entdeckt während Translation-Update: `de.json` hatte `wake_budget_exhausted` (aus v1.12.0) komplett gefehlt — nachgereicht mit synthesizer DE-Wording konsistent zu en.json:
> "Tägliches Wake-Up-Budget erschöpft ({count}/{budget}). Zum Schutz der 12V-Batterie werden bis Mitternacht UTC keine weiteren Wake-Up-Anfragen gesendet. Siehe sensor.wake_count_today."

#### Tests

Neue Datei `tests/test_v1130_production_hardening.py` mit 31 Tests:
- `TestCapabilityMap` (5) — CAPABILITY_MAP Brand-Inheritance + lookup
- `TestCommandCapabilitySupported` (8) — Tri-state Semantik + Skoda-Extras (active/user-enabled/license-issue)
- `TestCommandLock` (4) — Lazy creation + per-class isolation + is_command_in_flight
- `TestWakeCooldown` (3) — Erstes Wake / Cooldown raises / Nach Cooldown durchgeht
- `TestReadOnlyServiceBlocking` (2) — `_coord_writeable` raises + Phase 1 nicht regrediert
- `TestDiagnosticsPolish` (7) — Token-Redaction + Email-Mask + GPS-Rounding
- `TestSkodaCapabilities` (2) — Endpoint URL + Non-dict response handling

#### Doc-Refresh (rolled into v1.13.0)

- GitHub About-Section auf v1.12.3-Stand aktualisiert (war veraltet auf "68 entities, cloud push") + 2 neue Topics (`vehicle-data-scout`, `phev`)
- Master DE README + 7 Sprachen "Aktueller Stand & ehrliche Limits" Sektion komplett refresht von v1.8.12 auf v1.12.3 — alle 12 LIVE-Features dokumentiert
- Roadmap-Sektion in allen 8 READMEs vereinfacht auf "Single Source of Truth" Pointer + Tabelle der letzten 9 Releases + nächste 5 Sessions
- Bi-lingual Title Convention etabliert ab v1.12.3: Section-Titles `DE / EN`, Body bleibt deutsch

#### Files modified

```
custom_components/vag_connect/
  __init__.py                  (+ _coord_writeable, refresh_cloud_cache alias)
  button.py                    (uniform capability gate, removed _BRANDS_WITH_CAPABILITY_GATING)
  cariad/_capabilities.py      (NEW)
  cariad/api/skoda.py          (+ get_capabilities)
  climate.py                   (+ capability gate)
  coordinator.py               (+ command_capability_supported, _wake_last_at cooldown,
                                 _command_locks, _COMMAND_CLASS, _dispatch_cmd_locked,
                                 Skoda capability schema tolerance)
  diagnostics.py               (token redaction expanded, email partial mask, gps_round)
  lock.py                      (+ capability gate)
  manifest.json                (1.12.3 → 1.13.0)
  number.py                    (+ capability gate, _CMD_ID map)
  services.yaml                (refresh_vehicle desc, + refresh_cloud_cache)
  strings.json                 (+ wake_cooldown_active, + read_only_mode_active)
  switch.py                    (+ capability gate, _supported helper)
  translations/{de,en,fr,es,cs,nl,pl,sv}.json
                               (+ exceptions for cooldown + read-only;
                                 de.json also got missing wake_budget_exhausted)

.github/ISSUE_TEMPLATE/
  error_report.yml             (NEW)
  scout_report.yml             (NEW)

BRAND_CAPTAINS.md              (NEW)
docs/RESEARCH_NOTES_2026-05-02.md (NEW, 423 lines)
tests/test_v1130_production_hardening.py (NEW, 31 tests)
```

---

## [1.12.3] - 2026-05-01

### Scout-Pfade #111 + #113 + #114 mit Wildcard-Strategie / Scout paths bundled with wildcard strategy

PATCH-Release nach v1.12.2. Drei Scout-Reports in einem Release gebundlet:
- #111 von DnnsJp74 (Audi 23 Felder) — zweiter Community-Scout-Report
- #113 von Prash (Golf GTE 14 Felder)
- #114 von Prash (Audi S6 C8 20 Felder)

#### Wildcard-Strategie

Statt jeden neuen Sub-Field einzeln zu registrieren, decken Wildcards ganze Klassen ab. Stoppt das Whack-a-Mole-Pattern aus v1.12.0/1/2 wo wir bei jedem neuen Scout-Report einzeln nachregistriert haben.

Neue Wildcards in `EXPECTED_KEYS["volkswagen"]["selectivestatus"]` (Audi inherits via table alias):

```python
"fuelStatus.rangeStatus.value.*"
"fuelStatus.rangeStatus.value.primaryEngine.*"
"fuelStatus.rangeStatus.value.secondaryEngine.*"
"vehicleHealthInspection.maintenanceStatus.value.*"
"departureProfiles.departureProfilesStatus.value.*"
"userCapabilities.capabilitiesStatus.value.*"
"automation.climatisationTimer.value.*"
"automation.chargingProfiles.value.*"
"charging.chargeMode.value.*"
"charging.chargingCareSettings.*"
"vehicleHealthWarnings.warningLights.value.*"
"batteryChargingCare.value.*"  # proaktiv
"climatisationTimers.value.*"   # proaktiv
```

Plus alle 23 #111 paths einzeln (5x Climatisation Zone-Felder, 4x Readiness ConnectionState, 2x Battery Min/Max, etc.) zur expliziten Dokumentation.

#### Tests

`tests/test_v1123_111_audi_scout.py` — 8 Tests:
- 6 für #111 (verbatim payload silent + Audi inheritance + individual field paths)
- 2 für #113/#114 (verbatim payloads silent)

#### Hard Rules eingehalten

- ✅ Strict-Semver: PATCH (EXPECTED_KEYS-only update)
- ✅ Wildcard-Strategie future-proof gegen weitere Firmware-Updates
- ✅ Audi inheritance via table alias

---

## [1.12.2] - 2026-05-01

### Erstes Community-Scout-Report — Skoda #107 (tritanium73) / First community Scout report

🌟 **Erste Live-Validation der v1.9.0 Reporter Pipeline durch einen Nicht-Maintainer-Community-User.**

User `tritanium73` reichte am 2026-05-01 den ersten Vehicle Data Scout Report eines Community-Users ein. Die volle 1-Klick-Pipeline (Scout → Repair-Notification → pre-filled GitHub Issue → Maintainer-Fix) hat in der Wildbahn funktioniert.

#### Skoda mysmob EXPECTED_KEYS Erweiterungen

14 neue Pfade über 4 Endpoints in `EXPECTED_KEYS["skoda"]`:

| Endpoint | Pfade |
|---|---|
| `vehicle-status` | `renders.lightMode` + `renders.darkMode` (2-segment fix für v1.9.1 wildcard-only registry) |
| `air-conditioning` | `runningRequests`, `steeringWheelPosition`, `windowHeatingState.unspecified`, `timers`, `outsideTemperature`, `errors` |
| `driving-range` | `carType`, `primaryEngineRange` (Skoda mysmob Variante zu CARIAD-BFFs `fuelStatus.primaryEngine`) |
| `maintenance` | `maintenanceReport.capturedAt`, `preferredServicePartner`, `predictiveMaintenance`, `customerService` |

Alle Skoda-only — SEAT/CUPRA (OLA) und VW EU/Audi (CARIAD-BFF) tables unaffected.

#### Tests

`tests/test_v1122_107_skoda_scout.py` — 6 Tests inkl. Defensive-Test dass SEAT/CUPRA Inheritance NICHT von Skoda-Updates betroffen ist.

---

## [1.12.1] - 2026-04-30

### Scout-Pfade #105/#106 + Gerhard's Born Fixture (#53 consent) + #47 FAQ / Scout paths + Born fixture + Subscription FAQ

PATCH-Release nach v1.12.0. Drei orthogonale Tracks die alle aus User-Feedback / Live-Tests heute kamen.

#### Track A — #105/#106 EXPECTED_KEYS

Pattern wie #103/#104 in v1.12.0: Scout descendet eine Ebene tiefer, findet die nächste unbekannte Schicht.

**Field-Path Mapping:**

| v1.9.1 registriert | v1.12.0 registriert | v1.12.1 registriert (NEU) |
|---|---|---|
| `userCapabilities` | `userCapabilities.capabilitiesStatus` | `userCapabilities.capabilitiesStatus.value` |
| `fuelStatus` | `fuelStatus.rangeStatus` | `fuelStatus.rangeStatus.value` |
| `vehicleHealthInspection` | `vehicleHealthInspection.maintenanceStatus` | `vehicleHealthInspection.maintenanceStatus.value` |
| `vehicleHealthWarnings` | `vehicleHealthWarnings.warningLights` | `vehicleHealthWarnings.warningLights.value` |
| `departureProfiles` | `departureProfiles.departureProfilesStatus` | `departureProfiles.departureProfilesStatus.value` |
| — | `charging.chargeMode.error` | `charging.chargeMode.error.*` (wildcard) |
| — | — | `automation.climatisationTimer.error` + `.error.*` |
| — | — | `automation.chargingProfiles.error` + `.error.*` |
| — | — | `fuelStatus.rangeStatus.error.*` (proaktiv für #96 Pattern) |

**Wildcard-Strategie:** wo wir HTTP-Error-Wrapper sehen (6 standardisierte Sub-Felder pro CARIAD-Konvention: message/errorTimeStamp/info/code/group/retry), nutze `.error.*` Wildcard statt 6 explizite Pfade. Future-proof gegen neue Error-Sub-Felder.

**Audi inherits via** `EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]` (table alias) — eine Registrierung deckt beide Brands. Same-Single-Source-of-Truth seit v1.9.1.

#### Track B — Gerhard's CUPRA Born Fixture (#53 consent confirmed)

**Erste Live-Validation des Privacy-Workflows aus PR #101.**

Workflow:
1. v1.10.2 (2026-04-30 Vormittag) — Maintainer fragt Gerhard auf #53 um Erlaubnis für Fixture
2. Gerhard antwortet: "ja Fixture OK, ich hab nix zu verbergen :-)"
3. Maintainer redacted nach den Regeln aus `CONTRIBUTING.md` "Privacy & data handling" Sektion (PR #101)
4. Fixture committed mit `_meta` Block der Source + Consent-Zitat dokumentiert

**Datei:** `tests/fixtures/seat_cupra/cupra_born_2023_active_subscription_redacted.json`

**Redaction-Audit:** 7 Tests (`TestBornFixtureLoads`) verifizieren:
- Keine vollen 17-char VINs (nur `***003577`)
- Keine Email-Adressen
- Keine JWT-Tokens (`eyJ...` Pattern)
- Keine UUIDs (für userIDs/accountIDs)
- GPS gerundet auf 1 Dezimalstelle (~11 km Bucket)
- `_meta._source` startet mit "User report from issue #53"
- Brand/model/year korrekt

**Round-Trip-Tests:** 6 Tests (`TestBornFixtureParserRoundTrip`) verifizieren dass die v1.10.2 Parser-Pfade aus der Fixture allein die Werte produzieren die Gerhard live auf seinem Born sah:
- `battery_soc == 69` aus `battery.currentSocPercentage`
- `range_km == 277` aus `battery.estimatedRangeInKm` Fallback
- `plug_state == "disconnected"` + `plug_connected == False` aus `plug.connection` lowercase
- `connector_locked == False` aus `plug.lock == "unlocked"` lowercase
- `charging_state == "notReadyForCharging"` (case-insensitive comparison gegen "charging" → False)
- `doors_locked == True` aus top-level `status.locked`
- `hood_open == True` aus `status.hood.locked == "false"` (string!) Inversion

Wichtig: das ist eine **Regression-Schutz-Schicht.** Wenn jemand in v1.13.0+ den Parser refactort und dabei eine der 6 Field-Name-Varianten breakt, schlägt EIN Test in dieser Datei fehl mit klarer Born-2026-Firmware-Diagnose.

**Plus dokumentiert** im `_meta` Block die `command_flash` `400 missing-capability` Response die Gerhard sah — Future-Reference für Capability-Filter Phase 3 in v1.13.0.

#### Track C — #47 FAQ Service Plus / Subscription

**Auslöser:** Facebook-Community Frage (J.A.) ob Security & Service Plus nötig ist + verwandte Confusion in #53 / #56 Comments (third-party-review hat das in PR #101 als zu pauschal flagged).

**Was eingebaut wurde** (`CONTRIBUTING.md` neue "FAQ" Sektion):

1. **"Brauche ich Service Plus?"** — Klare Antwort: meist nein, in Portugal + manchen 2024+ Audi ja
2. **Tabelle Free vs. Subscription** für 6 Feature-Klassen
3. **Country-spezifische Restriktionen** (Portugal documented + Quelle)
4. **Diagnose-Tabelle** für Failure-Bodies — `missing-capability` vs `subscription_expired` vs `spin_error` vs `Bad Gateway` vs `404` mit Action-Empfehlung pro Pattern
5. **"App geht aber Integration nicht?"** — 3 unabhängige Gründe (different API profile, different payload shape, genuine missing-capability) referenziert zu #53 lessons
6. **Wo den Subscription-Status checken** — pro Brand-Portal aufgelistet

Verlinkt zu v1.9.1 Phase 2 (Auto-Recording-Pipeline) + v1.13.0 Phase 3 Plan (capability-filter pre-entity-creation).

#### Tests

**`tests/test_v1121_scout_and_born_fixture.py`** (neu, 19 Tests):

- `TestScoutWildcardCoverage` (5): `.value` Container registriert, `.error.*` wildcard matcht 6 Sub-Felder, automation error wrappers, Audi-Inheritance, verbatim #105 payload silent
- `TestBornFixtureLoads` (7): file existiert, valid JSON, meta block, no full VIN, no email, no JWT, no UUID, GPS rounded
- `TestBornFixtureParserRoundTrip` (6): 6 Werte aus Gerhard's Live-Test materialisieren aus der redacted Fixture
- `TestFAQDocsPresent` (1): FAQ-Sektion bleibt in CONTRIBUTING.md (regression-protection)

#### Was bleibt nach v1.12.1 für v1.13.0

(siehe ROADMAP.md "Sessioned Roadmap" Sektion mit kompletter P0/P1/P2 Priorisierung)

- **#62 Anonymized Diagnostics-Export** (war v1.13.0 ROADMAP) — jetzt mit Gerhard's Fixture als Reference-Implementation
- **#63 Phase 2/3** Read-only Mode (Command-Locking + cloud-vs-vehicle-refresh services)
- **#56 Capability-Filter Phase 3** (`capability.active && user-enabled` PRE-Entity-Creation) — Gerhard's `command_flash` 400 missing-capability ist exakt was Phase 3 verstecken würde
- **#42 / #48 / #51 Verify-Pings** — alte Bugs vermutlich gefixt durch v1.8+/v1.10+, brauchen User-Feedback

#### Hard Rules eingehalten

- ✅ Strict-Semver: PATCH (Doc-Updates + Test-Fixture + EXPECTED_KEYS-Erweiterung — keine neuen Entitäten, keine API-Änderungen, keine Coordinator-Logik-Änderungen)
- ✅ Privacy-by-default (Hard Rule #18 aus PR #101): Born-Fixture komplett redacted + 7 Audit-Tests + Source mit Consent dokumentiert
- ✅ User-Consent vor Fixture-Verwendung eingeholt (PR #101 Workflow erfolgreich getestet)
- ✅ Backwards-compat: keine bestehenden Tests gebrochen, alle Parser-Pfade unverändert

---

## [1.12.0] - 2026-04-30

### 5-in-1 Feature-Sprint: 12V (#23) + Per-Light Binary (#91 Welle 3) + Writeable Number (#91 follow-up) + Smart-Wake (#55) + Read-only Mode (#63) / Five features in one MINOR

**Theme:** "More Control + Diagnostics" — kohärenter MINOR-Sprint vor v2.0.0 mit fünf orthogonalen aber thematisch passenden Features.

#### Feature 1 — 12V Battery (Issue #23)

**Field changes:**
- `cariad/api/vw_eu.py:_SELECTIVE_STATUS_JOBS` um `lvBattery` erweitert
- `cariad/models.py:VehicleData` neue Felder `voltage_12v: float | None` + `warning_12v_low: bool | None`

**Parser:**
```python
voltage_raw = v(raw, "lvBattery", "lvBatteryStatus", "value", "batteryVoltage_V")
d.voltage_12v = safe_float(voltage_raw)  # v1.10.1 helper
if d.voltage_12v is not None:
    d.warning_12v_low = d.voltage_12v < 11.5
```

Threshold-Quelle: volkswagencarnet PR #940 + ELM327-Praxis. 12.6V = healthy, 11.5V = "go to garage soon", 10.5V = "modem can't keep itself awake — silent API outage".

**Entities:**
- Sensor `voltage_12v` (V, DEVICE_CLASS.VOLTAGE, diagnostic)
- Binary `warning_12v_low` (PROBLEM device-class)
- Beide im `_DATA_PRESENT_REQUIRED` set → Phantom-protection für Vehicles ohne lvBattery

#### Feature 2 — Per-Light Binary-Sensors (#91 Welle 3)

**Pattern:** mirror der Door/Window dynamic-creation. v1.11.0 vw_eu light parser füllt `lights_individual: dict[str, bool]`. v1.12.0 binary_sensor.py erstellt eine Entity pro key:

```python
class VagLightSensor(VagConnectEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.LIGHT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, vin, light_id):
        super().__init__(coordinator, vin, f"light_{light_id}")
        ...

async def _async_setup_light_sensors(coordinator, vin, vehicle, entities):
    lights = vehicle.get("lights_individual", {})
    for light_id in lights:
        entities.append(VagLightSensor(coordinator, vin, light_id))
```

Phantom-Protection: empty dict (vehicle deren API unbekannte Light-Element-Shape sendet) → keine Entities erstellt. Aggregate `lights_on` + `lights_count` bleiben unverändert.

#### Feature 3 — Writeable max_charge_current Number (#91 follow-up)

**Neuer Command:**
```python
async def command_set_max_charge_current(self, vin: str, ampere: int) -> None:
    await self._post_command(
        vin, "charging/settings", json={"maxChargeCurrentAC_A": int(ampere)},
    )
```

Field-Name verifiziert via #90 (Golf 7 GTE Live-Dump zeigt `maxChargeCurrentAC_A = 16` von chargingSettings GET — symmetrische PUT mit gleichem Field-Name).

**Coordinator:**
- `async_set_max_charge_current` war pre-1.12.0 `raise ServiceValidationError("feature_not_supported")` → ist jetzt `await self._cariad_cmd("command_set_max_charge_current", ampere=ampere)` mit voller v1.10.1 parse-guard + v1.9.1 FeatureState pipeline.

**Number entity:**
- 6-32 A range, step=2, mode=SLIDER, condition="electric"
- Dispatch-Branch in `VagConnectNumber.async_set_native_value` ergänzt für key=`max_charge_current`
- `[Inference]` Marker im Docstring — WRITE side body-shape verified gegen READ shape, aber nicht gegen offizielle App-Traffic.

#### Feature 4 — Smart-Wake Counter (Issue #55)

**Konstante:**
```python
_WAKE_BUDGET_PER_DAY = 3  # soft-cap, matches CC-* maintainer recommendations
```

**Logic in `async_wake_vehicle`:**
1. Read `today` (UTC date)
2. Lookup `_wake_counts[vin] = (last_date, count)`, default `(today, 0)`
3. Wenn `last_date != today`: reset count, last_date = today
4. Wenn `count >= _WAKE_BUDGET_PER_DAY`: raise `ServiceValidationError("wake_budget_exhausted", {count, budget})`
5. Increment count, push into `vehicle["wake_count_today"]`, notify HA via `async_set_updated_data`
6. Call `_cariad_cmd("command_wake")`

Wichtig: **Increment vor API-Call** (nicht nach Erfolg). Der Wake-Attempt zählt aus Backend-Perspektive auch wenn er nachträglich failed (Modem hat das Signal bereits empfangen).

**Sensor:** `wake_count_today` (TOTAL_INCREASING, diagnostic) zeigt den Counter live.

**Translation `wake_budget_exhausted`:**
> "Daily wake-up budget exhausted ({count}/{budget}). To protect the 12V battery, no further wake-up requests are sent until midnight UTC. See sensor.wake_count_today."

#### Feature 5 — Read-only Mode (#63 Phase 1)

**Const:**
```python
CONF_READ_ONLY = "read_only_mode"
```

**Coordinator helper:**
```python
def is_read_only(self) -> bool:
    options = getattr(self.entry, "options", None) or {}
    data = getattr(self.entry, "data", None) or {}
    return (
        (isinstance(options, dict) and options.get(CONF_READ_ONLY) is True)
        or (isinstance(data, dict) and data.get(CONF_READ_ONLY) is True)
    )
```

**5 Platform-Gates:**

| Platform | Gate-Verhalten |
|---|---|
| `lock.py` | `if coordinator.is_read_only(): return` (skip alles) |
| `switch.py` | dito |
| `climate.py` | dito |
| `number.py` | dito |
| `button.py` | VagRefreshButton bleibt; Flash + Wake werden geskipped |

**Options-Flow:** neue `read_only_mode` Boolean-Toggle in `VagConnectOptionsFlow`. User muss Integration nach Toggle reload — Gate greift erst beim nächsten `async_setup_entry`.

**Service-call Block:** weil die Entities gar nicht erst erstellt werden, kann der User auch keine Services callen. Ggf. extra Schutz für YAML-direct-service-call kommt in v1.12.x als Phase 2.

#### What is NOT in v1.12.0 (deferred to v1.12.1+)

- **Command Locking** (#63 Phase 2) — per-VIN per-command-class lock mit timeout, Anti-Double-Click. Eigene Session.
- **Cloud refresh vs vehicle wake distinction** (#63 Phase 3) — neue Services `vag_connect.refresh_cloud_cache` vs `vag_connect.wake_vehicle`. Eigene Session.
- **Anonymized Diagnostics-Export mit Fixtures** (#62) — eigene Session, braucht Fixture-Sammlung (siehe v1.10.2 Methodik-Note + Gerhard #53 Consent-Anfrage).
- **userCapabilities Phase 3** (#56 Phase 3) — `capability.active && capability.user-enabled` PRE-Entity-Creation. Braucht verifiziertes Capability-Vokabular pro Brand.

#### Tests

**`tests/test_v1120_features.py`** (neu, ~25 Tests):

- `Test12VBattery` (7): voltage parsing, threshold trigger/clear, no-lvBattery → None, string-form via safe_float, lvBattery in jobs list, sensor + binary registered + in `_DATA_PRESENT_REQUIRED`
- `TestPerLightSensors` (3): setup creates one entity per light, empty dict → no entities, is_on reads dict
- `TestSmartWakeCounter` (5): first wake = 1, increments, budget raises ServiceValidationError, daily reset, sensor registered
- `TestWriteableMaxChargeCurrent` (4): command payload, coordinator dispatches, Number registered, ampere/electric/range
- `TestReadOnlyMode` (6): helper reads options/data/default, lock/climate/number setup skipped, normal mode creates entities

#### Hard Rules eingehalten

- ✅ Strict-Semver: MINOR (5 neue Entitäten + 1 Option).
- ✅ Phantom-Entity-Protection für 3 der 5 neuen Entities (voltage_12v, warning_12v_low — auch wake_count_today via TOTAL_INCREASING semantics).
- ✅ `[Inference]` Marker für unverifizierte Pfade (max_charge_current WRITE body, lights element shape).
- ✅ Backwards-Compat: alle bestehenden Entitäten + Defaults unverändert.
- ✅ User-Data Handling: keine User-Daten in Tests/Fixtures, alle Test-Werte synthetisch.

---

## [1.11.1] - 2026-04-30

### Issue #96 (Golf GTE Fuel-Range Fix) + 3B-Part-3 (Optimistic UI)

#### Auslöser

**#96** — User-self-report nach v1.10.0 Test: Golf 7 GTE 2015 zeigt **immer noch keine Sprit-Reichweite** trotz v1.10.0 PHEV-Range-Triple. Deep-Research im Issue-Body identifiziert exakte Root Cause via evcc-io/evcc#19045 (Passat GTE Live-Trace) + CarConnectivity-Logs + Audi Q4 Sample.

**3B-Part-3** — laut ROADMAP geplante UX-Verbesserung (myskoda PR #832 Pattern), kombiniert mit dem #96-Fix als gleichgepoler PATCH.

#### Root Cause #96

`fuelStatus.rangeStatus` returnt auf älteren GTE-Firmwares ein `{"error": ...}` Objekt:

```json
{
  "fuelStatus": {
    "rangeStatus": {
      "error": {"message": "Bad Gateway", "code": 4007, "retry": true}
    }
  }
}
```

Pre-1.11.1 Code-Pfad:
1. `primary_engine = v(raw, "fuelStatus", "rangeStatus", "value", "primaryEngine", "type")` → `None`
2. `secondary_engine = ...` → `None`
3. `car_type = v(raw, "measurements", "fuelLevelStatus", "value", "carType")` → `"hybrid"`
4. `if car_type and "gasoline" in lower:` → False (`"hybrid"` matcht nicht)
5. `has_combustion` bleibt `False`
6. v1.10.0 `_DATA_PRESENT_REQUIRED` Phantom-Schutz blockiert `combustion_range_km` Sensor-Erstellung weil `condition="combustion"` filter False ist
7. Sensor erscheint nicht obwohl Backend-Daten in `measurements.rangeStatus.value.gasolineRange = 200` existieren

#### Fix #96 (4 Tracks im selben Parser-Block)

**`cariad/api/vw_eu.py:_parse_status` Drivetrain-Detection-Block:**

```python
# Track A: 4 statt 2 Engine-Type-Quellen
ms_primary = v(raw, "measurements", "fuelLevelStatus", "value", "primaryEngineType")
ms_secondary = v(raw, "measurements", "fuelLevelStatus", "value", "secondaryEngineType")
car_type = (
    v(raw, "fuelStatus", "rangeStatus", "value", "carType")
    or v(raw, "measurements", "fuelLevelStatus", "value", "carType")
)
for engine_type_raw in (primary_engine, secondary_engine, ms_primary, ms_secondary):
    ...
# Track A: explicit hybrid/phev string handling
if lower in {"hybrid", "phev", "plug-in hybrid", "pluginhybrid", "plug_in_hybrid"}:
    d.has_battery = True
    d.has_combustion = True
```

**Track C — total range fallback:**

```python
total_range = (
    v(raw, "fuelStatus", "rangeStatus", "value", "totalRange_km")
    or v(raw, "measurements", "rangeStatus", "value", "totalRange_km")  # NEW
)
```

**Track D — fuel level engine-block fallback:**

```python
d.fuel_level = v(raw, "measurements", "fuelLevelStatus", "value", "currentFuelLevel_pct")
if d.fuel_level is None:
    for engine_path in (primary, secondary):
        engine = v(raw, *engine_path)
        if not isinstance(engine, dict):
            continue
        if (engine.get("type") or "").lower() not in combustion_types:
            continue
        fuel_pct = safe_int(engine.get("currentFuelLevel_pct"))
        if fuel_pct is not None:
            d.fuel_level = fuel_pct
            break
```

**Track B — fuelStatus.error tolerance:** implizit gewonnen weil `v(raw, ...)` bei fehlenden Pfaden `None` returnt und der Code defensiv weiter durch die `or`-Chains der Fallbacks geht. Kein expliziter try/except nötig.

#### 3B-Part-3 — Optimistic UI

**`coordinator.py` — drei neue Helper:**

```python
def _optimistic_set(self, vin, fields) -> dict:
    """Push expected post-command values into self.vehicles[vin]
    immediately + notify HA. Returns previous-values snapshot."""

def _optimistic_revert(self, vin, previous):
    """Restore the snapshot after a failed command."""

async def _cariad_cmd_optimistic(self, vin, method, optimistic, **kwargs):
    """Like _cariad_cmd but sets optimistic state first, reverts on failure."""
```

**8 Actuator-Methoden umgestellt** auf `_cariad_cmd_optimistic`:

| Method | Optimistic Set |
|---|---|
| `async_lock` | `doors_locked = True` |
| `async_unlock` | `doors_locked = False` |
| `async_start_climatisation` | `climatisation_state="VENTILATION", climatisation_active=True` |
| `async_stop_climatisation` | `climatisation_state="OFF", climatisation_active=False` |
| `async_start_charging` | `charging_state="CHARGING", is_charging=True` |
| `async_stop_charging` | `charging_state="NOT_CHARGING", is_charging=False` |
| `async_start_window_heating` | `window_heating_front=True, window_heating_back=True` |
| `async_stop_window_heating` | `window_heating_front=False, window_heating_back=False` |

`async_flash_lights` + `async_wake_vehicle` + `async_set_target_soc` etc. **bleiben** ohne Optimistic — die haben keinen sinnvollen "after"-State (Flash ist transient, Wake hat keinen UI-State, SoC-Set ist eh ein Number-Slider).

**Failure-Pfad:**

```python
previous = self._optimistic_set(vin, optimistic)
try:
    await self._cariad_cmd(vin, method, **kwargs)  # may raise APIError
except Exception:
    self._optimistic_revert(vin, previous)
    raise  # HA shows ServiceValidationError, user sees toggle "spring back"
```

Wichtig: das v1.10.1 Coordinator-Parse-Guard + v1.9.1 FeatureState-Auto-Recording laufen weiter. Optimistic-UI ist additive UX-Layer, kein Replace.

#### Tests

**`tests/test_v1111_96_optimistic.py`** (neu, 18 Tests):

- `TestGolfGTEFuelRange` (6): full engine blocks regression, Passat error+measurements, carType=hybrid alone, engine-block fuel_level fallback, pure gasoline carType, pure EV unchanged
- `TestOptimisticLock` (3): lock flips immediately, unlock flips back, failure reverts
- `TestOptimisticClimate` (2): start sets active, stop sets off
- `TestOptimisticCharging` (2): start flips charging, stop reverts on failure
- `TestOptimisticWindowHeating` (1): both front+back flip
- `TestOptimisticHelpers` (4): _optimistic_set returns snapshot, _optimistic_revert restores, unknown VIN safely returns empty, async_set_updated_data invoked

#### Methodik-Note: Issue #96 als Vorbild für Maintainer-self-research

Issue #96 wurde vom Maintainer selbst geöffnet nach v1.10.0 Test, aber **mit komplett ausgearbeitetem Root-Cause-Audit + 4 konkreten Code-Fix-Vorschlägen + 4 externen Public-Source-Refs (evcc, CarConnectivity, Audi Q4 sample, WeConnect MQTT gist)**. Der Issue-Body war praktisch ein PR-Review im Vorhinein. Ergebnis: Implementation in <2 Stunden ohne weitere Recherche.

Lesson: Self-Research-Issues vor dem Bug-Fix erspart Spekulation und macht den Fix verifiziert (Hard Rule #8).

#### Hard Rules eingehalten

- ✅ Strict-Semver: PATCH (Bug-Fix für broken parsing + UX improvement, **keine** neuen Entitäten).
- ✅ Backwards-Compat: Vehicles deren `fuelStatus.rangeStatus.value` funktioniert sehen identisches Verhalten.
- ✅ Verifiziert gegen 4 externe Public-Source-Refs (evcc Passat trace, CarConnectivity log, Audi Q4 sample, WeConnect MQTT autodiscovery).
- ✅ Phantom-Entity-Protection bleibt unangetastet — Track A fixt nur die `has_combustion`-Detection, nicht die Phantom-Logik selbst.

#### Was bleibt nach v1.11.1 noch offen

- **#74 (Passat 2025 B9 Klima/Standort)** — wartet auf Marco's Debug-Log
- **#48, #42, #51 alte Bugs** — sollten durch v1.8.4 + v1.9.1 + v1.10.x bereits gefixt sein, brauchen Verification
- **v1.12.0 MINOR Sprint** — Per-Light Binary-Sensors + writeable max_charge_current Number + userCapabilities Phase 3 + Diagnostics-Export + Smart-Wake + 12V protection

---

## [1.11.0] - 2026-04-30

### Issue #91 Closure: Light-Status, Service-Days, Max-Charge-Current als echte Entitäten

**Auslöser:** Issue #91 (Audi S6 C8 2021) + #90 (VW Golf 7 GTE) hatten mehrere Vehicle Data Scout Findings die in v1.10.0 nur teilweise zu Entitäten wurden. v1.11.0 macht #91 vollständig fertig + bringt zusätzlichen Mehrwert.

#### Audit der #91-Punkte

| #91 Field | v1.10.0 Status | v1.11.0 Action |
|---|---|---|
| `measurements.rangeStatus.value.dieselRange` | ✅ als `combustion_range_km` umgesetzt | — |
| `measurements.fuelLevelStatus.value.currentFuelLevel_pct` | ✅ befüllt `fuel_level` Sensor (combustion) | — |
| `vehicleLights.lightsStatus.value.lights[]` | ❌ noch nicht | ✨ **`lights_on` + `lights_count`** |
| `vehicleHealthInspection` | ⚠️ als DATE-Sensor (int→date) — exact day-count verloren | ✨ **`service_due_in_days` + `oil_service_due_in_days`** als raw int |
| `vehicleHealthWarnings` | ✅ befüllt `warning_oil/engine/tyre/brakes` Binary-Sensors | — |
| `userCapabilities` | ⏳ Phase-3 (v1.12.0) | — |
| `fuelStatus` | ✅ in PHEV-Range-Logik genutzt | — |
| `maxChargeCurrentAC_A` | ⚠️ Field befüllt aber kein Sensor | ✨ **`max_charge_current_a`** read-only Sensor |

#### Neue VehicleData-Felder (`cariad/models.py`)

```python
# Service days (#91)
service_due_in_days: int | None = None
oil_service_due_in_days: int | None = None

# Vehicle lights (#91)
lights_on: bool | None = None              # any light on
lights_count: int | None = None            # count of lights on
lights_individual: dict[str, bool] = field(default_factory=dict)
```

#### Parser-Änderungen

**`cariad/api/vw_eu.py`** — neuer Lights-Block + Service-Days:

```python
# Service days — same backend ints as service_due_at, exposed raw
d.service_due_in_days = safe_int(d.service_due_at)
d.oil_service_due_in_days = safe_int(d.oil_service_at)

# Lights — defensive: try 3 known element shapes
lights_arr = v(raw, "vehicleLights", "lightsStatus", "value", "lights")
if isinstance(lights_arr, list):
    on_count = 0
    individual: dict[str, bool] = {}
    for light in lights_arr:
        # Status: "off"/"on" string OR {value: "on"} OR [{value: "on"}]
        # Name: "name" OR "id" OR location.position
        ...
    d.lights_count = on_count
    d.lights_on = on_count > 0
    if individual:
        d.lights_individual = individual
```

Per-light dict bleibt leer wenn die Element-Shape unbekannt ist — kein Phantom-Entity-Risiko.

**`cariad/api/skoda.py`** — Service-Days analog (mysmob `inspectionDueInDays` etc.).

#### Neue Sensor / Binary-Sensor Definitionen

**`sensor.py`** — 4 neue VagSensorDescription:

| Key | Unit | Device-Class | Condition | Phantom-Schutz |
|---|---|---|---|---|
| `service_due_in_days` | `d` | — | none | nein (existiert immer wenn parser was setzt) |
| `oil_service_due_in_days` | `d` | — | combustion | nein |
| `lights_count` | — | — | none | ✅ `_DATA_PRESENT_REQUIRED` |
| `max_charge_current_a` | `A` | CURRENT | electric | nein (Field oft None auf älteren Firmwares aber Sensor zeigt sauber "unbekannt") |

`max_charge_current_a` liest aus dem bestehenden `max_charge_current` Field (Backwards-Compat) — nur die Präsentation als Ampere-Sensor ist neu.

**`binary_sensor.py`** — 1 neue VagBinarySensorDescription:

| Key | Device-Class | Phantom-Schutz |
|---|---|---|
| `lights_on` | LIGHT | ✅ `_DATA_PRESENT_REQUIRED` (neu in binary_sensor.py — gleicher Pattern wie sensor.py) |

#### Translations

8 Sprachen mit konsistenten Begriffen:

| Sprache | service_due_in_days | oil_service_due_in_days | lights_count | lights_on | max_charge_current_a |
|---|---|---|---|---|---|
| DE | "Inspektion in" | "Ölwechsel in" | "Aktive Lichter" | "Lichter an" | "Max. Ladestrom" |
| EN | "Service In" | "Oil Change In" | "Lights On (Count)" | "Lights On" | "Max Charge Current" |
| FR | "Entretien dans" | "Vidange dans" | "Feux allumés (Nb)" | "Feux allumés" | "Courant de charge max." |
| ES | "Revisión en" | "Cambio de aceite en" | "Luces encendidas (Núm.)" | "Luces encendidas" | "Corriente de carga máx." |
| NL | "Service over" | "Olieverversing over" | "Lichten aan (aantal)" | "Lichten aan" | "Max. laadstroom" |
| PL | "Przegląd za" | "Wymiana oleju za" | "Włączone światła (liczba)" | "Światła włączone" | "Maks. prąd ładowania" |
| CS | "Servis za" | "Výměna oleje za" | "Rozsvícená světla (počet)" | "Světla rozsvícena" | "Max. nabíjecí proud" |
| SV | "Service om" | "Oljebyte om" | "Tända ljus (antal)" | "Ljus tända" | "Max laddström" |

#### Tests

**`tests/test_v1110_91_closure.py`** (neu, 15 Tests):

- `TestNewVehicleDataFields` (2): defaults, to_dict
- `TestVWEUParseLights` (7): no lights, empty array, 3 known shapes (name/id/list-wrapper), unknown shape (aggregate-only fallback), non-dict element skipped
- `TestServiceDaysFields` (2): VW EU populates from inspection block, missing block leaves None
- `TestSensorRegistration` (4): 4 sensors registered + lights_on binary, ampere unit + device-class CURRENT, days unit + diagnostic category, lights_count + lights_on in `_DATA_PRESENT_REQUIRED`, oil-service combustion-only

#### Architektur-Notes

- **Warum `lights_individual` als best-effort dict?** Element-Shape variiert zwischen Brand-Firmwares. Ohne verifizierte Live-Daten würde ein Hardcoded-Schema entweder false-positives (Phantom-Entities mit komischen Namen) oder false-negatives (Daten verloren) produzieren. Der Aggregate (`lights_on`/`lights_count`) ist immer korrekt; per-Light-Entitäten kommen in v1.12.0 wenn wir mehrere Live-Dumps haben.
- **Warum `max_charge_current_a` als Sensor und nicht Number?** Number würde Schreib-Operationen bedeuten — aber `command_set_max_charge_current` ist noch nicht implementiert (nur ServiceValidationError). Ein read-only Number wäre verwirrend; Sensor ist semantisch korrekter. Number kommt wenn der Command ready ist (v1.12.0+ mit Capability-Filter Phase 3).
- **Warum nicht `service_due_at` int direkt nutzen?** Der DATE-Sensor existiert seit v1.0 und Hunderte von Automatisierungen referenzieren ihn. Backwards-Compat = beide Felder befüllt.
- **Warum binary_sensor.py kriegt jetzt auch `_DATA_PRESENT_REQUIRED`?** Pre-1.11.0 war das Pattern nur in sensor.py. Mit `lights_on` brauchen wir das gleiche Verhalten in binary_sensor.py — gleiche Frozenset-Logik, separates Set für klare Scope-Trennung.

#### Hard Rules eingehalten

- ✅ Strict-Semver: MINOR (5 neue Entitäten — Binary + 4 Sensors).
- ✅ Backwards-Compat: alle bestehenden Sensoren unverändert, neue sind additiv.
- ✅ Verifiziert gegen Issue #91 + #90 Findings (lights array confirmed live, service days confirmed live, max charge current confirmed = 16 A live).
- ✅ Defensive: Light-Parsing crashed nicht bei unbekannter Shape (3 Shape-Varianten + non-dict-Filter).
- ✅ Phantom-Entity-Schutz konsistent mit v1.10.0 Pattern.

#### Was bleibt nach v1.11.0 noch offen

- Per-Light Binary-Sensors (verschoben auf v1.12.0)
- `max_charge_current_a` als writeable Number (verschoben auf v1.12.0)
- `userCapabilities` Phase 3 Capability-Filter
- `automation` + `departureProfiles` als eigene Plattform

#91 wird mit v1.11.0 als **vollständig closed** markiert — die offenen Punkte sind eigene Sessions auf neuen Issues.

---

## [1.10.2] - 2026-04-30

### CUPRA Born 2026 Firmware-Shapes (Gerhard #53 Live-Test)

**Auslöser:** Gerhard testete v1.10.0 auf seinem CUPRA Born (NUC-Test-Setup, 2026-04-30) und meldete via Vehicle Data Scout (v1.9.0 Pipeline) **19 neue Felder**. Beim Audit zeigt sich: viele sind **umbenannte** Versionen unserer bekannten Felder. Born ist auf neuerer OLA-Firmware als Rainer (#109 — unsere v1.8.9-Referenz).

**Erste Live-Validation der vollen v1.9.0 → Maintainer-Reaktion → Hotfix Pipeline.** User → Repair-Notification → 1-Klick-Issue → Fix in <12 Stunden.

#### Field-Name-Mapping (Born 2026 ↔ Rainer #109 ↔ Legacy CARIAD)

| Bedeutung | Born 2026 firmware | Rainer #109 (v1.8.9) | Legacy CARIAD (pre-v1.8.9) |
|---|---|---|---|
| Battery SoC | `battery.currentSocPercentage` (camelCase) | `currentPct` ODER `battery.stateOfChargeInPercent` | `battery.currentSOC_pct` |
| Estimated range (km) | `battery.estimatedRangeInKm` (NEU) | — | — |
| Plug connection | `plug.connection` (kurz) | `plug.connectionState` | `plug.plugConnectionState` |
| Plug lock | `plug.lock` (kurz) | `plug.lockState` | `plug.plugLockState` |
| Plug enum CONNECTED | `"connected"` (lowercase) | `"CONNECTED"` | `"CONNECTED"` |
| Plug enum LOCKED | `"locked"` (lowercase) | `"LOCKED"` | `"LOCKED"` |
| Charging state enum | `"notReadyForCharging"` (camelCase) | `"NOT_READY_FOR_CHARGING"` | dito |

#### Parser-Änderungen (`cariad/api/seat_cupra.py`)

**Battery SoC** — neue Quelle als erste Priorität:

```python
d.battery_soc = (
    v(bat, "currentSocPercentage")        # Born 2026 firmware (#53)
    or v(charge_status, "currentPct")     # Rainer #109 shape A
    or v(bat, "stateOfChargeInPercent")
    or v(bat, "currentSOC_pct")           # Legacy uppercase
)
```

**Estimated range** — neuer Fallback für `range_km` und `electric_range_km`:

```python
if d.range_km is None:
    est_range = v(bat, "estimatedRangeInKm")
    est_int = safe_int(est_range)  # v1.10.1 helper
    if est_int is not None:
        d.range_km = est_int
        if d.electric_range_km is None:
            d.electric_range_km = est_int
```

Wichtig: nur als Fallback. Der dedizierte `/v1/vehicles/{vin}/ranges` Endpoint wird bevorzugt weil er electric vs. combustion trennt (v1.10.0 PHEV-Logik).

**Plug connection + lock** — kurze Pfade + lowercase enum tolerance:

```python
plug_state_raw = (
    v(plug, "connection")              # Born 2026 firmware (#53)
    or v(plug, "connectionState")        # Rainer #109 shape
    or v(plug, "plugConnectionState")    # Legacy CARIAD
)
d.plug_state = plug_state_raw
d.plug_connected = (
    isinstance(plug_state_raw, str)
    and plug_state_raw.lower() == "connected"
)
plug_lock_raw = (
    v(plug, "lock")                    # Born 2026 firmware (#53)
    or v(plug, "lockState")              # Rainer #109 shape
    or v(plug, "plugLockState")          # Legacy CARIAD
)
d.connector_locked = (
    isinstance(plug_lock_raw, str)
    and plug_lock_raw.lower() == "locked"
) or v(plug, "externalPower") == "READY"
```

**Status endpoint top-level fallback** — Born 2026 ships flat top-level fields ALONGSIDE the structured tree:

```python
top_locked = v(status, "locked")
if isinstance(top_locked, bool) and not d.doors_locked:
    d.doors_locked = top_locked
top_hood_locked = v(status, "hood", "locked")
if isinstance(top_hood_locked, str) and d.hood_open is None:
    # hood.locked is the inverse of hood.open
    d.hood_open = top_hood_locked.lower() == "false"
```

#### EXPECTED_KEYS Erweiterung (`cariad/_unexpected_keys.py`)

Alle 19 Pfade aus Gerhard's Report sind jetzt registriert (SEAT erbt automatisch via `EXPECTED_KEYS["seat"] = EXPECTED_KEYS["cupra"]`):

| Endpoint | Neue registrierte Pfade |
|---|---|
| `mycar` | `engines`, `services` |
| `status` | `locked`, `lights`, `hood.locked`, `updatedAt` |
| `charging` | `battery.currentSocPercentage`, `battery.estimatedRangeInKm`, `plug.connection`, `plug.lock`, `charging.state`, `charging.remainingTimeInMinutes`, `charging.chargedPowerInKw`, `charging.type`, `charging.mode`, `charging.settings` |
| `charging-info` | `settings`, `chargingCareSettings`, `chargingCareStatus` |

#### Tests

**`tests/test_v1102_gerhard_born_firmware.py`** (neu, 16 Tests):

- `TestBornChargingNewShape` (8): `currentSocPercentage` camelCase, `estimatedRangeInKm` populates range, doesn't overwrite dedicated range, plug short paths + lowercase `connected`/`disconnected`/`locked`/`unlocked`, legacy uppercase still works, legacy battery still works, lowercase camelCase enum (notReadyForCharging), is_charging classification on lowercase
- `TestBornStatusTopLevelFields` (3): `status.locked` bool sets doors_locked, `status.hood.locked` string "false"/"true" inverted to hood_open
- `TestScoutFindingsRegistered` (5): all 19 paths registered + SEAT inheritance smoke

#### Methodik-Note: warum nur ~12 Stunden vom Bug-Report zum Fix

Die v1.9.0 Reporter Pipeline funktioniert genau wie geplant:

1. **2026-04-29 19:43:** v1.9.0 published (Vehicle Data Scout + Error Reporter)
2. **2026-04-30 ~08:06:** Gerhard fährt v1.10.0 das Polling — Scout sieht 19 neue Felder
3. **2026-04-30 ~08:16:** Repair-Notification erscheint in seinem HA — er klickt "Mehr erfahren" → öffnet pre-filled GitHub-Issue
4. **2026-04-30 ~08:30:** Gerhard postet den Scout-Output als Comment auf #53
5. **2026-04-30 nachmittag:** Maintainer sieht das, baut v1.10.2

**Crowd-sourced Bug-Discovery wie designed.** Ohne v1.9.0 hätten wir nie erfahren dass Gerhard's Born stille leere Felder hat — er hätte einfach gedacht "die Integration funktioniert nicht für mich".

#### Hard Rules eingehalten

- ✅ Strict-Semver: PATCH (Bug-Fix für broken parsing, **keine** neuen Entitäten — die `range_km`/`electric_range_km`-Population ist Wiederherstellung von vorher gewünschtem Verhalten).
- ✅ Backwards-kompatibel: alle drei Field-Namen-Varianten werden in Reihenfolge probiert. Rainer's #109 Shape funktioniert weiter.
- ✅ Verifiziert gegen Gerhard's Live-Dump (#53 Comment 2026-04-30).
- ✅ SEAT inherits CUPRA — kein separates Wiring nötig.

---

## [1.10.1] - 2026-04-30

### Defensive Coding Phase 2 (Issue #58)

**Pattern-Quelle:** myskoda issues #503 (`CHARGING_INTERRUPTED` neu in Firmware), #207 (`NOT_ACTIVATED` neu), PR #565 (`NO_UPDATE_AVAILABLE` neu) — VAG ships new enum values without warning, Integrations die nicht tolerieren brechen über Nacht. Plus Live-Beobachtungen aus eigenen Logs: `int("12.5")` ValueErrors auf Skoda-Charging-Endpoint, `float("MAXIMUM")` ValueErrors auf VW-Settings-Endpoint.

**Strategie:** statt jedes `int()`/`float()`/`enum-Vergleich` einzeln in try/except zu wrappen — drei zentrale Helfer mit klarem Vertrag.

#### Neue Helfer (`cariad/_util.py`)

```python
def safe_int(value, default=None) -> int | None:
    """NEVER raises. Accepts int, bool, float, "12", "12.5", "  42  ".
    Returns default for None, "", "abc", dict, list."""

def safe_float(value, default=None) -> float | None:
    """NEVER raises. Same coverage."""

def safe_enum(value, known_values, *, log_name="enum",
              default=None, case_insensitive=True) -> str | None:
    """Return value if known, else log + return default.
    Case-insensitive by default — original casing preserved on match."""
```

Vertrag: alle drei sind **pure** (keine Side-Effects außer dem Warning-Log in `safe_enum`), idempotent, und werfen nie Exceptions aller Art (TypeError, ValueError, OverflowError).

#### Anwendung

**`cariad/api/skoda.py`:**

| Pre-1.10.1 | Post-1.10.1 |
|---|---|
| `int(remaining)` (`remainingTimeToFullyChargedInMinutes`) | `safe_int(remaining)` |
| `float(temp_val)` (`targetTemperature.temperatureValue`) | `safe_float(...)` |

**`cariad/api/vw_eu.py`:**

| Pre-1.10.1 | Post-1.10.1 |
|---|---|
| `int(meta["model_year"])` mit try/except | `safe_int(meta.get("model_year"))` |
| `int(remaining_min)` (`remainingChargingTimeToComplete_min`) | `safe_int(...)` |
| `float(max_ac)` (`maxChargeCurrentAC_A`) | `safe_float(...)` |

**`cariad/api/seat_cupra.py`:**

| Pre-1.10.1 | Post-1.10.1 |
|---|---|
| `int(remaining)` (legacy + new field paths) | `safe_int(remaining)` |

**`coordinator.py:_poll_loop`** — neuer try/except um `to_dict() + _enrich()`:

Pre-1.10.1: ein einziges Parser-Problem (z.B. `_enrich` ruft `_reverse_geocode` mit unerwarteten lat/lon-Werten) hat den ganzen Vehicle-Poll zerschossen → Vehicle wurde als komplett gefailt markiert, alle Sensoren auf "unavailable", obwohl der eigentliche `get_status` erfolgreich war.

Post-1.10.1: dedizierter try/except wrapper:

```python
try:
    data = result.to_dict()
    data["_client"] = self._cariad_client
    data["_poll_failed"] = False
    enriched = await self._enrich(data)
except Exception as parse_err:  # noqa: BLE001
    _LOGGER.warning(
        "VAG Connect: post-parse failure for %s — keeping previous data: %s",
        mask_vin(vin), parse_err,
    )
    old = self.vehicles.get(vin, {})
    old["_poll_failed"] = True
    fresh[vin] = old
    self.vehicle_success[vin] = False
    self.vehicle_failure_count[vin] = self.vehicle_failure_count.get(vin, 0) + 1
    record_error(self.error_buffer, exception=parse_err, ...)
    continue
```

Folgen:
- Vehicle bleibt mit den **vorherigen** Daten sichtbar (graceful degradation, kein "unavailable" wegen einem einzelnen kaputten Feld).
- Failure landet automatisch im Error Reporter Ring-Buffer (v1.9.0 Pipeline) → User kann mit 1 Klick das GitHub-Issue öffnen.
- `_poll_failed=True` markiert den Datensatz für Diagnostics-Export.

#### Tests

**`tests/test_v1101_defensive.py`** (neu, 16 Tests):

- `TestSafeInt` (5): pass-through int, truncate float, parse numeric/decimal string, garbage → default, bool subclass
- `TestSafeFloat` (4): pass-through, decimal string, garbage, bool
- `TestSafeEnum` (7): known value, unknown logs+default, explicit default, case-insensitive (preserves original), strict case-sensitive opt-in, none/empty, non-string coerced
- `TestParserHardening` (3): Skoda decimal-string remaining minutes (myskoda #503), VW EU max_charge_current as enum string ("MAXIMUM"), model_year int/string interop
- `TestCoordinatorParseGuard` (1): Error Reporter receives parse-fail exceptions correctly

#### Architektur-Notes

- **Warum nicht `safe_str`?** Strings brauchen keine Konvertierung — wenn der Wert schon ein String ist, hat sich nichts geändert. `safe_enum` deckt die einzige String-spezifische Defensive-Anwendung ab (Vergleich gegen erlaubte Werte).
- **Warum `safe_enum` mit Warning-Log statt silent default?** Wir wollen aktiv erfahren wenn VAG einen neuen Enum ausrollt — sonst übersehen wir Drift. Die Warning ist actionable (enthält Field-Name + Wert) und der Vehicle Data Scout aus v1.9.0 sieht den Pfad eh als "unbekannt".
- **Warum nicht alle `int()`/`float()` ersetzen?** Viele sind in Code-Pfaden wo der Wert garantiert ein bekannter Typ ist (z.B. unmittelbar nach `if isinstance(x, int): ...`). Die Helfer sind nur für API-Surface-Konvertierungen sinnvoll.
- **Generic `except Exception` Audit:** ein paar Stellen in den Brand-Clients haben noch bare `except Exception: # noqa: BLE001` — diese sind alle **bewusste** "best effort"-Bookkeeping-Calls (Image-Fetch, Token-Exchange, Error-Reporter). Die wurden nicht angerührt; siehe Phase-2-Issue Comments für die Begründung.

#### Hard Rules eingehalten

- ✅ Strict-Semver: PATCH (Bugfix-Charakter, keine neuen Entitäten, keine neuen API-Endpoints).
- ✅ Backwards-kompatibel: Helfer geben gleiche Werte zurück wenn der Input bereits korrekt typisiert war.
- ✅ Tests vor Implementation an den heißen Stellen verifiziert (`safe_int("12.5") == 12`, `safe_float("MAXIMUM") is None`).
- ✅ Coordinator-Wrapper feedbackt in v1.9.0 Reporter Pipeline → konsistente UX bei jeder Art von Fehler.

---

## [1.10.0] - 2026-04-29

### PHEV Range Triple + Audi Diesel Range — Issue #94 + Scout-driven Entities aus #91

**Auslöser:** Issue #94 (PHEV-User wollen elektrische + Verbrennungs-Reichweite separat sehen), Issue #91 (Audi S6 C8 2021 Live-Test zeigt `measurements.rangeStatus.value.dieselRange = 190` als unbekannten Pfad). Erste MINOR-Release die die Vehicle Data Scout findings (v1.9.0) in echte HA-Entitäten überführt.

#### Neue Felder

**`custom_components/vag_connect/cariad/models.py`** — VehicleData um 3 Felder erweitert:

```python
electric_range_km: int | None = None     # batterie-only Reichweite
combustion_range_km: int | None = None   # Petrol/Diesel/CNG/LPG Reichweite
total_range_km: int | None = None        # kombinierte Reichweite (PHEVs)
```

`range_km` bleibt als "Headline-Number" für Backwards-Compat — existierende Dashboards / Automatisierungen brechen nicht.

#### Parser-Änderungen

**`custom_components/vag_connect/cariad/api/vw_eu.py:_parse_status`** — komplett umgebaute Range-Logik:

API-Pfade pro Drivetrain:

| Quelle | Pfad | Beispiel-Vehicle |
|---|---|---|
| Pure EV | `charging.batteryStatus.value.cruisingRangeElectric_km` | ID.4, e-tron GT |
| PHEV (modern) | `fuelStatus.rangeStatus.value.{primaryEngine,secondaryEngine}.{type,remainingRange_km}` | Golf 7 GTE 2015+ (#90) |
| Total (Hybrid) | `fuelStatus.rangeStatus.value.totalRange_km` | Golf 7 GTE |
| Diesel (Audi älter) | `measurements.rangeStatus.value.dieselRange` | S6 C8 2021 (#91, sample 190 km) |
| Benzin (Audi älter) | `measurements.rangeStatus.value.gasolineRange` | (proaktiv für ICE-Audis) |

Neue Logik:

1. **Iteration über beide Engine-Blöcke** (`primaryEngine` + `secondaryEngine`). Klassifizierung nach `engine.type` (`electric`/`ev` → `electric_range_km`, `gasoline`/`petrol`/`diesel`/`gas`/`cng`/`lpg` → `combustion_range_km`). Kein Hardcoding "primary == electric" — manche Firmwares vertauschen es.
2. **Fallback auf `measurements.rangeStatus`-Pfad** wenn kein `fuelStatus`-Block (Audi S6 C8 2021). Akzeptiert sowohl skalare `int`-Werte als auch `{distanceInKm: int}`-Wrapper.
3. **`total_range_km` separat** — nur gesetzt wenn `totalRange_km` explizit publiziert wird.
4. **Headline `range_km` Priorität:** elektrisch (für `has_battery=True`) → total → Verbrennung.

Pre-1.10.0 hatte 2 Bugs:
- `battery_range` von `cruisingRangeElectric_km` überschrieb manchmal den `total_range_km` (Reihenfolge im Code)
- `combustionRange` wurde nirgends in ein eigenes Feld geschrieben — verloren für PHEV-User

**`custom_components/vag_connect/cariad/api/skoda.py:get_status`** — Driving-Range Block:

Skoda mysmob hat dieselbe Per-Engine-Struktur, aber unter `electricRange.distanceInKm` + `combustionRange.distanceInKm` + `totalRangeInKm`. Pre-1.10.0 las nur `combustionRange` als Skalar — auf neueren Firmwares mit Wrapper-Form (Kodiaq iV) war das `None`. Fix: liest jetzt beide Formen (gewrappt als Default, flacher Skalar als Fallback) und befüllt alle 3 Felder.

#### Sensor-Definitionen

**`custom_components/vag_connect/sensor.py`** — 3 neue `VagSensorDescription`:

| Key | Translation Key | Icon | Condition | Unit |
|---|---|---|---|---|
| `electric_range_km` | electric_range_km | mdi:battery-charging-outline | electric | km |
| `combustion_range_km` | combustion_range_km | mdi:gas-station | combustion | km |
| `total_range_km` | total_range_km | mdi:map-marker-distance | (none) | km |

Alle drei: `device_class=DISTANCE`, `state_class=MEASUREMENT`, `suggested_display_precision=0`.

#### Phantom-Entity-Schutz (#94 acceptance criteria)

Neuer `_DATA_PRESENT_REQUIRED` Frozenset in `sensor.py`:

```python
_DATA_PRESENT_REQUIRED: frozenset[str] = frozenset({
    "electric_range_km",
    "combustion_range_km",
    "total_range_km",
})
```

`async_setup_entry` filtert pro VIN: wenn `vehicle.get(desc.data_key) is None` UND der Key im `_DATA_PRESENT_REQUIRED`-Set ist → Entity wird NICHT erstellt. Reine EVs bekommen also nicht den `combustion_range_km`-Sensor als "unknown", reine ICE keinen `electric_range_km`. Per-key opt-in — bestehende Sensoren behalten ihr "create-immer, populate-später" Verhalten.

Wichtig: das Set ist **additiv zur** `condition`-Filterung (`electric`/`combustion`). Beide müssen gleichzeitig "ja" sagen damit eine Entity entsteht. Verhindert double-trouble: ein PHEV mit `has_battery=True` + `has_combustion=True` aber ohne API-Daten für eines der beiden → richtige Filterung.

#### Translations

8 Sprachen (de/en/fr/es/nl/pl/cs/sv) mit konsistenten Begriffen:

| Sprache | Electric | Combustion | Total |
|---|---|---|---|
| DE | Elektrische Reichweite | Kraftstoff-Reichweite | Gesamtreichweite |
| EN | Electric Range | Fuel Range | Total Range |
| FR | Autonomie électrique | Autonomie carburant | Autonomie totale |
| ES | Autonomía eléctrica | Autonomía combustible | Autonomía total |
| NL | Elektrisch bereik | Brandstofbereik | Totaal bereik |
| PL | Zasięg elektryczny | Zasięg paliwa | Zasięg łączny |
| CS | Elektrický dojezd | Dojezd na palivo | Celkový dojezd |
| SV | Elektrisk räckvidd | Bränsleräckvidd | Total räckvidd |

#### Tests

**`tests/test_v1100_phev_ranges.py`** (neu, 13 Tests):

- `TestVehicleDataFields` (2): Defaults sind None, to_dict round-trips
- `TestVWEUParseRanges` (5): PHEV mit primary=electric/secondary=gasoline; vertauschte Engine-Positionen; Audi diesel-only Fallback; pure EV (kein combustion); wrapped `{distanceInKm: int}` form
- `TestSkodaParseRangesUnit` (1): Kodiaq PHEV shape mit allen 3 Werten
- `TestSensorGating` (5): `_DATA_PRESENT_REQUIRED` enthält die 3 Keys; alle 3 SensorDescriptions registriert; combustion hat gas-station icon + condition; electric hat battery icon + condition; total hat keine condition

#### Was NICHT in v1.10.0 ist

- **`vehicleHealthWarnings` als neue Binary-Sensors:** Parser + Felder existieren schon seit v1.0 (warning_engine/oil/tyre/brakes — gefüllt aus `vehicleHealthWarnings.warningLights.value`). Die Vehicle Data Scout Findings #90 + #91 hatten den Pfad nur als top-level `vehicleHealthWarnings` gemeldet (ungeparster wrapper) — v1.9.1 hat das `EXPECTED_KEYS` registriert, der Parser darunter funktioniert seit jeher.
- **`vehicleHealthInspection` als neuer Date-Sensor:** existiert schon als `service_due_at` (DATE-device-class, parsed aus `inspectionDue_days`), v1.9.1 hat den Top-Level-Pfad registriert.
- **`maxChargeCurrentAC_A` als Number-Entity:** Feld existiert bereits in VehicleData als `max_charge_current` (float). Das Number-Platform-Wiring kommt in v1.10.1 separat.
- **Defensive Coding Phase 2 (#58):** verschoben auf v1.10.1 — eigene Session, separater PR.
- **`automation` + `departureProfiles` Plattform:** Architekturarbeit, kommt in v1.11.0+.

#### Auswirkung auf Bestandsbenutzer

- **Reine EV-Besitzer (ID.4 etc.):** sehen jetzt `electric_range_km` zusätzlich zur bestehenden `range_km`. Kein neuer Verbrennungs-Sensor (Phantom-Schutz).
- **Reine ICE-Besitzer:** sehen jetzt `combustion_range_km`. Kein neuer Elektro-Sensor.
- **Audi S6 C8 2021 (TDI):** sieht jetzt korrekten `combustion_range_km` (z.B. 190 km) statt nichts.
- **PHEV-Besitzer (Golf GTE etc.):** sehen alle drei (45 elektrisch + 520 Sprit + 565 gesamt) statt nur eines.

#### Hard Rules eingehalten

- ✅ Nichts spekuliert — alle Pfade sind verifiziert (gegen #90 #91 Live-Daten + bestehende Skoda-Fixtures + audi_connect_ha source).
- ✅ Keine bestehenden Tests gebrochen — Backwards-Compat via `range_km`.
- ✅ Brand-localized Translations in 8 Sprachen.
- ✅ Strict-Semver — MINOR weil neue Sensoren (3 neue Entitäten).

---

## [1.9.1] - 2026-04-29

### Hotfix #92 (Audi S6 C8 2021 Lock + Wake) + Vehicle Data Scout Coverage (#90, #91) + Capability-Filter Phase 2 (#56)

Erste reale Bug-Reports an die v1.9.0 Vehicle Data Scout & Error Reporter
Pipeline. Maintainer Prash testete v1.9.0 sofort nach Release auf seinem
Audi S6 C8 (2021, MJ 2021) + VW Golf 7 GTE — beide Reports kamen via
1-Klick-Workflow ins Repo (#90, #91, #92), genau wie das v1.9.0 Design
es vorgesehen hatte. Erfolgs-Validierung für die ganze Reporter-Pipeline.

#### Änderungen

**`custom_components/vag_connect/cariad/api/vw_eu.py`** (2 Bug-Fixes):

- `command_lock(vin, spin="")` — Signatur erweitert. Pre-1.9.1 sandte
  immer `{"action": "lock"}` ohne S-PIN. Premium Audi-Modelle wie der
  S6 C8 antworten mit `403 spin_error` (Body:
  `{"error":{"message":"spin_error","spinState":"DEFINED","remainingTries":3}}`).
  Fix: gleiche S-PIN-Behandlung wie `command_unlock` — wenn die S-PIN
  konfiguriert ist, wird sie ins Payload aufgenommen sowohl beim
  combined `/access/lock-unlock`-Endpoint als auch beim separaten
  `/access/lock`-Fallback.
- `command_wake(vin)` — von bareem `self._post` auf `self._post_command`
  umgestellt. Pre-1.9.1 traf `vehicle/v1/.../vehicleWakeup` direkt; bei
  premium Audi-Modellen gibt's das nur unter `/vehicle/v2/...`. Der
  `_post_command`-Helper hat seit v1.8.5 (Session 3A) den v1→v2 Fallback,
  jetzt wird er auch für Wake genutzt.

**`custom_components/vag_connect/coordinator.py`**:

- `async_lock(vin)` — Brand-Erkennung erweitert: bei `audi`/`volkswagen`
  wird die S-PIN aus den Options/Data gelesen und an `command_lock(vin, spin=...)`
  übergeben. Bei SEAT/CUPRA bleibt der Pre-Check für fehlende S-PIN
  (raises `ServiceValidationError`); bei Audi/VW wird der Call ohne S-PIN
  zugelassen (für ältere Modelle ohne Premium-S-PIN-Anforderung) — schlägt
  er dann fehl, klassifiziert ihn die neue Phase-2-Pipeline automatisch
  als `SPIN_REQUIRED`.
- `_cariad_cmd` — komplett umgebaut für Phase 2:
  - Bei Erfolg: `record_command_success(vin, method)` — flippt
    `supported_by_vehicle` + `entitled_by_account` + `available_now`
    auf True und löscht `last_error`.
  - Bei Fehler: `classify_command_failure(err)` → ableitet
    `CommandFailureReason` aus Body + Status; `record_command_failure(...)`
    aktualisiert die FeatureState. Exception wird trotzdem propagiert.
  - Beide Calls in try/except — Bookkeeping darf nie das Command-Ergebnis
    beeinflussen.
- `is_command_known_unsupported(vin, command)` — neuer Helper.
  Konservativ: nur True wenn `supported_by_vehicle is False` ODER
  `entitled_by_account is False`. Transient errors (UNKNOWN, BACKEND_ERROR,
  VEHICLE_UNREACHABLE) lassen die Flags auf None und der Helper bleibt False.

**`custom_components/vag_connect/entity_base.py`**:

- `_command_id: str | None = None` — neues Class-Attribut. Subklassen
  setzen es auf z.B. `"command_lock"` um Phase-2-Gating zu aktivieren.
- `available` Property erweitert: zusätzlich zur per-VIN Verfügbarkeit
  prüft sie jetzt `coordinator.is_command_known_unsupported(vin, command)`
  wenn `_command_id` gesetzt ist. Sensoren ohne Command bleiben
  unverändert.

**`_command_id` Annotationen** in command-bound Entities:

- `lock.py:VagDoorLock` → `command_lock`
- `button.py:VagFlashButton` → `command_flash`
- `button.py:VagWakeButton` → `command_wake`
- `climate.py:VagClimate` → `command_start_climate`
- `switch.py:VagLockSwitch` → `command_lock`
- `switch.py:VagClimatisationSwitch` → `command_start_climate`
- `switch.py:VagChargingSwitch` → `command_start_charging`
- `switch.py:VagWindowHeatingSwitch` → `command_start_window_heating`

**`custom_components/vag_connect/cariad/exceptions.py`**:

- `classify_command_failure(exc)` — Body-Content-Sniffing vor
  Status-Code-Klassifikation:
  - `spin_error` / `spinState` (case-insensitive) → `SPIN_REQUIRED`
    (vorher fälschlich `NOT_ENTITLED` weil 403)
  - `subscription` + (`expired`|`lapsed`) → `SUBSCRIPTION_EXPIRED`
  - `not_entitled` / `not-entitled` / `license_required` /
    `license-required` / `entitlement` → `NOT_ENTITLED`
- Verifizierte Marker-Strings dokumentiert mit Issue-Quellen
  (#92 für spin_error, #47/#42 für subscription, #51 für not_entitled).

**`custom_components/vag_connect/cariad/_unexpected_keys.py`** —
`EXPECTED_KEYS["volkswagen"]["selectivestatus"]` (Audi inherits)
um 13 neue Pfade erweitert basierend auf Issues #90 + #91:

| Path | Quelle | Bemerkung |
|---|---|---|
| `measurements.rangeStatus.value.dieselRange` | #91 (S6 TDI) | sample 190km |
| `measurements.rangeStatus.value.gasolineRange` | proaktiv (Petrol-Pendant) | |
| `measurements.fuelLevelStatus.value.currentFuelLevel_pct` | #91 | sample 26% |
| `charging.chargingSettings.value.maxChargeCurrentAC_A` | #90 (Golf 7 GTE) | sample 16A |
| `charging.chargeMode` | #90 | top-level Block |
| `climatisation.climatisationSettings.value.targetTemperature_F` | #90 | sample 73°F |
| `climatisation.climatisationSettings.value.climatisationWithoutExternalPower` | #90 | bool |
| `vehicleLights.lightsStatus.value.carCapturedTimestamp` | #90+#91 | timestamp |
| `vehicleLights.lightsStatus.value.lights` | #90+#91 | array |
| `userCapabilities` | #90+#91 | top-level |
| `fuelStatus` | #90+#91 | top-level (verschieden von `measurements.fuelLevelStatus`) |
| `vehicleHealthInspection` | #90+#91 | service-due Block |
| `vehicleHealthWarnings` | #90+#91 | warning Block |
| `automation` | #90 | smart-charging Block |
| `departureProfiles` | #90 | Nachfolger von `departureTimers` |

#### Tests

**`tests/test_v191_hotfix.py`** (neu, 18 Tests):

- `TestAudiLockSpin` (4): no-spin omits field, spin kwarg → payload,
  client default spin, coordinator forwards Audi spin
- `TestVWEUWake` (2): wake → `_post_command` dispatch, v1 404 → v2
- `TestClassifyAndAutoRecord` (7): spin_error in body, subscription,
  not_entitled, status fallback, `is_command_known_unsupported`
  state machine (transient = False, missing-capability = True,
  subscription = True, success = back to False), `_cariad_cmd`
  auto-recording on failure
- `TestScoutKeyRegistration` (5): diesel range, max charge ampere,
  top-level diagnostic blocks, lights nested, audi == volkswagen
  inheritance smoke

#### Architektur-Notes

- **Warum kein "MISSING_CAPABILITY" auto-flip auf 404?** 404 kann auch
  ein Endpoint-Versions-Mismatch sein (Hauptgrund für den v1→v2
  Fallback). Wir bleiben bei `WRONG_API_PROFILE` für 404 und nur
  explizite Body-Marker (`missing-capability`, `missing_capability`)
  führen zu permanenter Hide.
- **Warum nicht alle Brand-Capabilities-IDs in button.py erweitern?**
  Wir haben verifizierte Capability-IDs nur für SEAT/CUPRA (OLA Vocab).
  Audi/VW EU haben eine andere Capability-Vokabular die wir noch nicht
  gegen Live-Vehicles abgeglichen haben — Phase 2 nutzt deshalb das
  Per-Command-FeatureState-System (lernt durch Beobachten von 403er),
  nicht Capability-Lookup-vor-Entity-Creation.
- **Warum Lock + Window-Heating-Switch + Climatisation-Switch _command_id
  haben aber nicht jeden Sensor?** Sensors haben kein Backend-Action;
  die Phase-2-Logik bringt nur Wert für Entitäten die ein Command auslösen.
  Read-only-Entities bleiben sichtbar solange `is_vehicle_available` True
  ist.
- **Warum keine UI-Texte für die Phase-2 "unavailable"-States?** HA's
  Standard-Mechanik ist gut: Entity wird ausgegraut, State zeigt
  "Unavailable". Eigene Repair-Issues für Subscription-Renewal kommen
  in v1.10.0 (Diagnostics + Smart-Wake Sprint).

#### Rückwärtskompatibilität

- Alle Änderungen sind additive Verhaltens-Verbesserungen.
- `_command_id` defaults to `None` → keine alte Subklasse bekommt
  unbeabsichtigtes Hide-Verhalten.
- `record_command_success` / `record_command_failure` existieren seit
  v1.8.2 — Phase 2 nutzt sie nur konsequenter.

---

## [1.9.0] - 2026-04-29

### Vehicle Data Scout + Error Reporter — Crowd-Sourced Bug-Discovery via 1-Klick Reporter Pipeline

**Versionssprung-Begründung:** Erste **MINOR-Release nach strikter Semver-Disziplin**
(siehe Roadmap-Sektion „Semver-Korrektur ab v1.9.0"). Zwei neue Sensoren = MINOR,
nicht PATCH. Folgereihen entsprechend verschoben (v1.9.1 Capability-Filter,
v1.9.2 Defensive Coding Phase 2, v1.9.3 Optimistic Lock/Climate, v1.10.0
Diagnostics + Smart-Wake + 12V).

**Pattern-Quelle:** `tillsteinbach/CarConnectivity-*` "Unexpected Keys found"
War unsere ergiebigste API-Erkenntnisquelle (CC-seatcupra #109 Rainer's CUPRA Born,
CC-skoda #50 Kodiaq iV 2026 Live-Dump). Wir bauen das gleiche Pattern in unsere
Integration ein — plus Error-Sammlung — und senken die Hürde von „Issue selbst
schreiben" auf „1 Klick auf vorausgefüllten GitHub-Link" oder „1 Klick auf Copy
für Forum/Facebook".

#### Neue Module (3, alle pure-Python — Unit-test-bar ohne HA)

**`custom_components/vag_connect/cariad/_unexpected_keys.py`** (neu, 392 Zeilen):

- `UnexpectedField` dataclass: `path`, `sample_masked`, `endpoint`, `first_seen_at`
- `EXPECTED_KEYS: dict[brand][endpoint] -> set[str]` — registrierte Felder pro
  Brand+Endpoint. SEAT inherits CUPRA, Audi inherits VW EU. 5 Brands aktiv,
  jeweils 5–7 Endpoints abgedeckt.
- `_path_matches(path, expected_paths)` — Wildcard-Matching mit `*` als Segment
  (z.B. `doors.*.locked` matcht `doors.frontLeft.locked`)
- `mask_value(value, max_len=80)` — anonymisiert: VIN-Regex (17-stellig) →
  `mask_vin`, Email → `***@***`, JWT-shape → `[token]`, UUID → `[uuid]`,
  Float → 1 Dezimalstelle (kills GPS-Präzision auf ~11 km)
- `detect_unexpected(brand, endpoint, response, max_depth=6)` — Generator,
  yieldet `UnexpectedField` für nicht-registrierte Pfade. Stoppt rekursiv
  bei `max_depth` (Schutz gegen pathologische Responses). Brand/endpoint
  ohne Registry-Eintrag → silent (keine false positives).

**`custom_components/vag_connect/cariad/_error_reporter.py`** (neu, 208 Zeilen):

- `ErrorRecord` dataclass — frozen, alle Felder maskiert
- `ErrorRingBuffer` mit `_MAX_ERRORS = 20` (begrenzt Memory + Diagnostics-Größe)
- 2 zusätzliche Regexes über `_unexpected_keys` hinaus:
  - `_BEARER_RE` — `Bearer\s+[A-Za-z0-9._-]+`
  - `_OPAQUE_TOKEN_RE` — `\b[A-Za-z0-9+/]{32,}={0,2}\b`
- `_redact(text, max_len=500)` — strippt VIN/Email/JWT/UUID/Bearer/opaque
- `record_error(buffer, *, exception, brand, vin, model_year, firmware, endpoint)` —
  **NEVER raises**. Außenliegender try/except baut bei Buffer-Failure einen
  minimal Fallback-Record `ErrorReporterFailure`. Hält letzte 12 Traceback-Zeilen
  (~3 Frames + Headers — genug zum Debuggen, klein genug für GitHub-URL-Limit)
- `serialise_for_diagnostics(buffer)` — JSON-safe Liste für HA-Diagnostics

**`custom_components/vag_connect/cariad/_reporter_pipeline.py`** (neu, 230 Zeilen):

- `build_unexpected_keys_report(findings, brand, model_year, firmware, integration_version)` —
  Markdown mit Tabelle (Path | Sample | Endpoint | First seen) + Privacy-Footer
- `build_error_report(records, brand, integration_version)` — Markdown mit Section
  pro Error, Tracebacks in fenced code blocks
- `github_issue_url(title, body, *, repo_url, labels, body_max=6500)` — baut
  pre-filled Issue-URL mit URL-encoded Query-Params, **truncates body bei 6500B**
  (GitHub URL limit ~8KB) und appendet Marker
- `ensure_unexpected_keys_issue(hass, *, entry_id, findings, brand, ...)` — `ir.async_create_issue`
  mit `translation_key="vehicle_data_scout_findings"`, `learn_more_url` zeigt auf
  pre-filled GitHub-URL. Empty findings → `ir.async_delete_issue` (cleanup).
- `ensure_error_reporter_issue(...)` — gleicher Aufbau, severity=ERROR statt
  WARNING, `translation_key="error_reporter_findings"`
- `clear_reporter_issues(hass, entry_id)` — wird beim Entfernen der Integration
  gerufen

#### Geänderte Dateien

**`custom_components/vag_connect/cariad/api/base.py`** (+9 Zeilen):

- `last_raw_responses: dict[str, dict[str, Any]] = {}` — opt-in Stash für
  Brand-Clients. Coordinator iteriert das nach jedem erfolgreichen Poll und
  füttert es in `detect_unexpected`. Brand-Client opt-in heißt: kein Forced-Change
  in Audi/Porsche/VW NA — die bleiben silent bis sie selbst Endpoints stashen.

**`custom_components/vag_connect/cariad/api/skoda.py`** (+15 Zeilen):

- Stash der 7 gefetcheten Endpoints (vehicle-status, charging, air-conditioning,
  parking, driving-range, maintenance, readiness) in `last_raw_responses`.
  Skipped wenn payload kein dict (Exception aus `asyncio.gather`).

**`custom_components/vag_connect/cariad/api/seat_cupra.py`** (+13 Zeilen):

- Stash der 5 wichtigsten Endpoints (mycar, status, charging, charging-info,
  climatisation). SEAT erbt automatisch über `EXPECTED_KEYS["seat"] = EXPECTED_KEYS["cupra"]`.

**`custom_components/vag_connect/cariad/api/vw_eu.py`** (+10 Zeilen):

- Stash von `selectivestatus` und `parkingposition`. Audi erbt über `AudiClient(VWEUClient)`
  und `EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]`.

**`custom_components/vag_connect/coordinator.py`** (+125 Zeilen):

- Imports: `ErrorRingBuffer`, `record_error`, `ensure_error_reporter_issue`,
  `ensure_unexpected_keys_issue`, `UnexpectedField`, `detect_unexpected`
- Neue Felder im `__init__`:
  - `self.unexpected_findings: dict[str, dict[str, UnexpectedField]] = {}` —
    per-VIN, de-duped per Path (gleiche Drift bei jedem Poll = nur 1 Record)
  - `self.error_buffer: ErrorRingBuffer = ErrorRingBuffer()`
- `_poll_loop` — neue Hooks:
  - Nach erfolgreichem Poll für VIN: `self._scan_for_unexpected_keys(vin)` (try/except)
  - Nach Per-VIN-Exception: `record_error(buffer, exception=result, brand, vin,
    model_year, firmware, endpoint="get_status")` (try/except, NEVER raises)
  - Nach jedem Poll-Cycle: `self._refresh_reporter_issues()` (try/except)
  - Nach Outer-Exception: `record_error(buffer, exception=err, brand, endpoint="poll_loop")`
    + `_refresh_reporter_issues()`
- Neue Methoden:
  - `_scan_for_unexpected_keys(vin)` — iteriert `client.last_raw_responses`,
    de-duped per Path
  - `_refresh_reporter_issues()` — flatten + delegiert an pipeline-Funktionen,
    lazy-import um Circular zu vermeiden
  - `reporter_findings_count()` — sum von distinct paths über alle VINs
  - `reporter_error_count()` — `len(buffer)`

**`custom_components/vag_connect/sensor.py`** (+85 Zeilen):

- 2 neue `VagSensorDescription` mit `data_key=""`:
  - `api_observer_findings` (icon `mdi:radar`, EntityCategory.DIAGNOSTIC)
  - `error_reporter_count` (icon `mdi:alert-circle-outline`, EntityCategory.DIAGNOSTIC)
- `_REPORTER_KEYS` frozenset für Dispatch in `async_setup_entry`
- Neue Klasse `ReporterSensor(VagConnectSensor)`:
  - `native_value` reads from `coordinator.unexpected_findings[vin]` (per-VIN)
    bzw. `coordinator.reporter_error_count()` (account-wide)
  - `extra_state_attributes` zeigt Preview (max 5 Pfade / 3 Exception-Typen)
    + `report_url` Pointer auf GitHub Issues

**`custom_components/vag_connect/diagnostics.py`** (+22 Zeilen):

- Imports: `serialise_for_diagnostics`
- Neue Felder in der Diagnostics-Response:
  - `unexpected_findings`: `{masked_vin: [{path, sample, endpoint, first_seen_at}]}`
  - `error_buffer`: full `serialise_for_diagnostics(buffer)`
- Beide bereits in `mask_value` / `_redact` durchgelaufen — keine Doppel-Redaction nötig

**`custom_components/vag_connect/strings.json` + 8 translations** (de/en/fr/es/nl/pl/cs/sv):

- 2 neue Sensor-Namen (`api_observer_findings`, `error_reporter_count`),
  brand-localized:
  - DE: "API-Beobachter" / "Fehler-Berichter"
  - EN: "Vehicle Data Scout" / "Error Reporter"
  - FR: "Observateur d'API" / "Rapporteur d'erreurs"
  - ES: "Observador de API" / "Reportador de errores"
  - NL: "API-waarnemer" / "Foutmelder"
  - PL: "Obserwator API" / "Raporter błędów"
  - CS: "Pozorovatel API" / "Hlásič chyb"
  - SV: "API-spanare" / "Felrapportör"
- 2 neue Issue-Translations (`vehicle_data_scout_findings`, `error_reporter_findings`)
  pro Sprache mit Title + ausführlicher Markdown-Description (1-Klick-Anleitung
  + Facebook/Forum-Workflow + Privacy-Footer)

**`custom_components/vag_connect/manifest.json`**:

- `version`: `1.8.12` → `1.9.0`

#### Tests

**`tests/test_reporter.py`** (neu, 18 Tests):

- `TestUnexpectedKeys` (10 Tests): registered-keys not flagged, unknown-keys
  flagged, unregistered brand silent, SEAT==CUPRA inheritance, Audi==VW
  inheritance, mask_value redaction (VIN, GPS, JWT, UUID, Email), wildcard
  path matching
- `TestErrorReporter` (4 Tests): ring buffer evicts oldest, record_error
  masks all sensitive substrings, record_error never raises (BoomBuffer
  fixture), serialise_for_diagnostics is JSON-safe
- `TestReporterPipeline` (4 Tests): unexpected-keys report renders table,
  empty findings = empty string, error report renders fenced traceback,
  GitHub URL pre-filled and decodable, body truncation works,
  ensure_*_issue creates/deletes via mocked HA registry, error-issue
  severity is ERROR

#### Privacy-Audit

Jede der folgenden Substrings darf NICHT in der Diagnostics-Response landen:

- Voller VIN (17 chars)
- Bearer-Token, JWT, opaque base64 token (>=32 chars)
- userID (UUID v4)
- Email-Adresse
- GPS-Koordinaten mit > 1 Dezimalstelle (~11 km Bucket)

Verifiziert via `test_record_error_masks_sensitive_data` mit kombiniertem
String, der alle 5 Pattern-Typen enthält. Plus dedizierte `mask_value`
Unit-Tests für jeden Typ einzeln.

#### Architektur-Notes

- **Warum opt-in pro Brand-Client?** Audi inherits VW EU automatisch. Andere
  Brands (Porsche, VW NA) bleiben silent bis sie eine `EXPECTED_KEYS`-Tabelle
  und `last_raw_responses`-Stash haben. Verhindert false-positives für nicht-getunte Brands.
- **Warum Per-VIN für Vehicle Data Scout, Account-wide für Error Reporter?**
  Drift ist Vehicle-spezifisch (Firmware, Modelljahrgang). Errors sind oft
  Auth/Rate-Limit (account-wide). Trennung spiegelt die Ursachen.
- **Warum De-Dup per Path?** Drift bei jedem Poll → ohne De-Dup hätte der Buffer
  in 1 Stunde 720 identische Einträge. De-Dup hält ihn klein und den Report lesbar.
- **Warum NEVER-raises?** Error-Reporter ist Infrastruktur. Ein Bug im Reporter
  würde sonst die Integration killen — genau das Gegenteil von dem, was wir wollen.
- **Warum kein Auto-Push?** GDPR (Anwender muss aktiv konsentieren), HACS-Regeln
  (kein automatischer Telemetry-Send), GitHub ToS (Bot-Issues = Spam-Risiko).
  1-Klick + opt-in ist die Best Practice.

#### Was kommt NICHT in v1.9.0

- **Capability-Filter Phase 2** (#56) — separates Release v1.9.1
- **Defensive Coding Phase 2** (#58) — separates Release v1.9.2
- **Anonymized Diagnostics-Export Service** mit Reset-Button — Teil von v1.10.0
- **Push notifications** für neue Findings — bewusst nicht (nutzt schon HA Repair-System)

---

## [1.8.12] - 2026-04-29

### MVP-Move — Multi-Brand Connection-State (Helper-Extraction + Apply auf alle 4 CARIAD-Brands)

Erweitert das `carCapturedTimestamp` Pattern aus v1.8.11 (Skoda-only) auf
**alle vier CARIAD-basierten Brand-Clients**: VW EU, Audi, SEAT, CUPRA.
Macht uns zur **ersten VAG-HA-Integration mit centralisiertem
Multi-Brand Connection-State**.

**Methodik:** vor Implementation **3 parallele Recherche-Agents** losgeschickt
(CC-skoda Issues, myskoda Issues + recent merged PRs, volkswagencarnet
Issues + PRs). Plus laufender Agent für audi_connect_ha. Erkenntnisse alle
verifiziert gegen echte Live-API-Responses (Hard Rule #8 — keine Spekulation).

**Bestätigung aus volkswagencarnet Issue #921 (ID.4 2025 Live-Dump):**
VW EU CARIAD-BFF `selectivestatus` returns `carCapturedTimestamp` auf
JEDEM sub-object — aber **TIEFER geschachtelt** als Skoda mysmob:

```
access.accessStatus.value.carCapturedTimestamp
charging.batteryStatus.value.carCapturedTimestamp
charging.chargingStatus.value.carCapturedTimestamp
charging.chargingSettings.value.carCapturedTimestamp
charging.plugStatus.value.carCapturedTimestamp
climatisation.climatisationStatus.value.carCapturedTimestamp
climatisation.climatisationSettings.value.carCapturedTimestamp
measurements.rangeStatus.value.carCapturedTimestamp
measurements.odometerStatus.value.carCapturedTimestamp
measurements.fuelLevelStatus.value.carCapturedTimestamp
parkingposition.carCapturedTimestamp        ← separate endpoint
```

Format ist gemischt: ISO-Strings UND pre-parsed `datetime`-Objekte.

**`cariad/_util.py` — neuer Helper `compute_connection_state(*sub_objects)`:**

- **Rekursiver Walk** durch dicts und lists, sammelt jeden datetime
  unter `carCapturedTimestamp` (oder konfigurierbarem `timestamp_keys` Tupel)
- **Akzeptiert** sowohl ISO-Strings als auch pre-parsed `datetime`
- **Naive datetimes** werden als UTC interpretiert
- **Defensive** gegen: BaseException-Sub-Objects (asyncio.gather mit
  `return_exceptions=True`), corrupt ISO-Strings, missing fields
  (myskoda PR #565)
- **Returns** `(state, last_seen_at)` — `(None, None)` wenn nichts gefunden
- Thresholds: `<30 min → "online"`, `<24 h → "standby"`, `>=24 h → "offline"`

**Apply auf 4 Brand-Clients:**

1. `cariad/api/skoda.py` — Refactor: hardgekodeter v1.8.11-Block ersetzt
   durch `compute_connection_state(...)` Aufruf. Behavior identisch, Code 40
   Zeilen kürzer.
2. `cariad/api/seat_cupra.py` — Apply: am Ende von `get_status` mit den
   9 OLA-Sub-Objects.
3. `cariad/api/vw_eu.py` — Apply: in `get_status` direkt nach `_parse_status`.
   Helper handles die nested `.value.carCapturedTimestamp` Pfade durch
   den rekursiven Walk.
4. `cariad/api/audi.py` — Inheritance: `AudiClient(VWEUClient)` überschreibt
   `get_status` nicht, profitiert daher automatisch.

**Tests** (`tests/test_cariad.py::TestComputeConnectionState`, 12 neue):
top-level + nested patterns, freshest wins, datetime + str + naive, corrupt
strings, exception sub-objects, threshold boundaries, custom timestamp_keys.
Plus alle 10 v1.8.11 Skoda-Tests bleiben grün (Refactor-Garantie).

**`manifest.json`:** 1.8.11 → 1.8.12

**Bewusst NICHT in v1.8.12 enthalten** (eigene Sessions geplant):

- `readiness.connectionState.isOnline` als Master-Health-Sensor
- `InsufficientBatteryLevel` Stale-Cache-Verlängerung (volkswagencarnet #940)
- `devicePlatform: WCAR/MBB_ODP/PPC/PPE` Plattform-Routing
- `engineType.primaryEngineType` für saubere EV/PHEV/ICE-Detection
- `TermsAndConditionsError` spezifische Detection im Auth-Flow (volkswagencarnet PR #307)
- `windowHeatingStatus[]` Array-Pfad für Audi/VW EU
- Service Discovery Pattern (volkswagencarnet PR #314)

**Bestätigt unsere Strategie 1:1**: skodaconnect/myskoda PR #536
implementiert exakt dieselbe Logik intern (ältere Events ignorieren).
Wir machen das gleiche, exposen aber als User-facing Sensor.

**Quellen** (verifiziert):
- robinostlund/volkswagencarnet Issue #921 (ID.4 2025), #940 (12V),
  PRs #301 (Readiness), #307, #310, #314, #316/#317
- tillsteinbach/CC-skoda Issue #50, CC-seatcupra #109
- skodaconnect/myskoda PR #536, #565

## [1.8.11] - 2026-04-29

### Session 3S — Škoda `carCapturedTimestamp` connection-state + #50 Live-API-Erkenntnisse

Schließt **#54 (GitHobi)** "Standby vs Offline" und integriert die wichtigsten
Live-API-Erkenntnisse aus dem Kodiaq iV 2026 Komplettdump in
`tillsteinbach/CarConnectivity-connector-skoda` Issue **#50**. Plus: PRs aus
`skodaconnect/myskoda` (#503, #536, #565) wurden ausgewertet — **myskoda PR #536
fährt GENAU dieselbe `carCapturedTimestamp`-Strategie wie unsere v1.8.11**, was
unseren Ansatz unabhängig bestätigt.

**Methodisch (wichtig nach v1.8.9-Lerneinheit):** vor diesem PR wurden ZWEI
parallele Recherche-Agents losgeschickt — einer für CC-skoda Issues, einer für
myskoda Issues + recent merged PRs. Erst danach Code geschrieben, damit nichts
wichtiges verpasst wird.

**`cariad/api/skoda.py` — `_parse_status` erweitert:**

1. **Neuer `compute_connection_state(...)` Block:** sammelt
   `carCapturedTimestamp` aus allen 7 Status-Sub-Objects (status, charging,
   ac, parking, driving_range, maintenance, readiness), nimmt den
   freshesten Wert und mappt: `<30min` → `online`, `<24h` → `standby`,
   `>=24h` → `offline`. Defensive `try/except ValueError` für korrupte
   Backend-Timestamps. Wenn kein Timestamp gefunden → `None` (myskoda
   PR #565 Pattern: das Feld ist nicht garantiert).
2. **`vehicle-status.detail` Block:** parst `sunroof`, `trunk`, `bonnet`
   (CLOSED/OPEN/UNSUPPORTED). Pre-v1.8.11 für Škoda nie populiert.
   `UNSUPPORTED` lässt das Feld auf `None` (Karoq Diesel ohne Sunroof
   zeigt korrekt keine Entity).
3. **`overall.reliableLockStatus`** als bevorzugte Lock-Quelle vor
   `doorsLocked`/`locked` (Kodiaq 2026+).
4. **`charging.fullyChargedAt`** als ISO-Timestamp wird zuerst probiert
   (kein Drift durch Poll-Latency). Fallback auf
   `remainingTimeToFullyChargedInMinutes`.

**`cariad/models.py`** — neues Field `last_seen_at: Any | None` mit
Comment: "wann das AUTO zuletzt Daten geliefert hat" vs. das existierende
`last_updated_at` "wann WIR zuletzt gepollt haben".

**`sensor.py`** — neue `VagSensorDescription` für `connection_state`,
`EntityCategory.DIAGNOSTIC`, icon `mdi:car-connected`.

**Translations (9 Files)** — `connection_state` in EN/DE/FR/ES/NL/PL/CS/SV
+ strings.json.

**Tests** (`tests/test_cariad.py::TestSkodaGetStatus`, 10 neue):

1. `test_v1811_connection_state_online_when_recent`
2. `test_v1811_connection_state_standby_under_24h`
3. `test_v1811_connection_state_offline_over_24h`
4. `test_v1811_connection_state_none_when_no_timestamp` — defensive (myskoda PR #565)
5. `test_v1811_freshest_timestamp_across_subobjects` — multi-source (myskoda PR #536)
6. `test_v1811_detail_block_sunroof_trunk_bonnet`
7. `test_v1811_detail_unsupported_stays_none`
8. `test_v1811_reliable_lock_status_preferred`
9. `test_v1811_charging_fully_charged_at_iso_timestamp`
10. `test_v1811_charging_interrupted_state_not_charging` — myskoda #503 Regression-Test

Plus neuer helper `_url_routing_client(by_path)` für saubere Multi-Endpoint-Mocks.

**Bewusst NICHT in v1.8.11 enthalten** (eigene Sessions geplant):

- `/v3/garage` Fallback für #75 Kodiaq Mk2 — Hard Rule #8 (keine Spekulation,
  myskoda-Source bestätigt v3 existiert nicht)
- `specification` Felder (`trimLevel`, `engine.type`, `manufacturingDate`,
  `systemModelId`) → Device-Info-Erweiterung
- `renders` / `compositeRenders` (Light/Dark, 4 Auflösungen) → Image-Refactor v1.10
- `batteryProtectionLimitOn` / `batteryCareModeTargetValueInPercent` →
  Battery-Care eigene Session
- `seatHeatingActivated` Dict → Seat-Heating eigene Session
- `timers[]` / `runningRequests[]` → Departure-Timer eigene Session
- `/api/v1/trip-statistics/{vin}/single-trips` → Trip-Stats v1.10.x
- `/api/v1/charging/{vin}/history` mit Cursor-Pagination → eigene Session
- `/v2/widgets/vehicle-status/{vin}` als leichter Endpoint → Session 6 Smart-Wake
- `devicePlatform: MBB_ODP` vs `WCAR` Plattform-Routing → Capability-Filter Session
- AdBlue Range für Diesel (CC-skoda #24) → eigene kleine Session
- Token-Hardening / 429-Backoff → bereits in v1.8.7 Defensive Pass abgedeckt

**Quellen** (verifiziert während Recherche):
- `tillsteinbach/CarConnectivity-connector-skoda` Issue #50 (Kodiaq iV 2026
  Live-Dump), #44, #23, #24, #8, #41
- `skodaconnect/myskoda` Issue #503, #461, #495, #458, #416, #237, #207
- `skodaconnect/myskoda` PRs #536 (Pattern-Bestätigung), #565
  (Optional fields), #537 (MY26 Capabilities)
- `tillsteinbach/CarConnectivity-connector-skoda` PR #36 (Maintenance fields)

## [1.8.10] - 2026-04-29

### Hotfix — Legacy CARIAD-flat doors fallback Inversionsbug (Pre-v1.8.9-Bug)

Ein-Zeilen-Hotfix gegen einen latenten Bug der seit Einführung des
Legacy-Fallback-Pfads in v1.8.9 vorhanden war. Aufgedeckt durch den
v1.8.9 Regression-Test `test_v189_status_legacy_flat_fallback_still_works`,
der in CI im PR #82 als FAIL durchlief. Der PR wurde trotzdem gemerged
weil Branch-Protection auf required-checks im Repo nicht aktiviert ist —
das ist eine separate Process-Lücke die in einem eigenen Hotfix adressiert
wird.

**Bug:**

Im `cariad/api/seat_cupra.py` Legacy-Fallback-Block (für sehr alte
Firmware oder zukünftige API-Änderungen wo unsere neuen pycupra-Pfade
nichts liefern) stand:

```python
for key in ("doorClosedLeftFront", "doorClosedRightFront", ...):
    val = v(access_s, key)
    ...
    doors_legacy[door_id] = not val   # ❌ INVERSION-BUG
```

Das `not val` invertierte die Semantik: das CARIAD-BFF-Field heißt
`doorClosed*` — also `True` bedeutet "Tür IST geschlossen", was unserer
`doors_individual`-Konvention (True == closed) **direkt** entspricht.
Das `not val` war daher falsch, und Tür-Entities würden für jedes
Modell, das tatsächlich diese flachen Pfade liefert, die invertierte
Information melden.

**Fix:**

```python
doors_legacy[door_id] = bool(val)   # ✅ direkt, ohne Inversion
```

**Impact:** Aktuelle CUPRA Born / Formentor / Tavascan Modelle nutzen die
neuen `status.doors.{position}.{locked,open}` Pfade aus v1.8.9, also
trifft sie der Bug **nicht** in Praxis. Der Bug betrifft nur den
defensiven Fallback-Pfad — der nur fires wenn keine der neuen
strukturierten Pfade Daten liefert. Realistisch dürfte das auf keinem
heute aktiven SEAT/CUPRA-Modell passieren. Trotzdem wichtig zu fixen
weil:

1. Der bestehende Regression-Test (12. Test in v1.8.9) muss grün sein
2. Kommt eine zukünftige OLA-API-Änderung die uns auf den Fallback
   wirft, würden Tür-Entities silently invertierte Werte zeigen
3. CI auf main muss grün sein — `main` mit failing tests blockt jede
   nachfolgende PR

**Tests:** keine Änderungen nötig — der bestehende v1.8.9 Test
`test_v189_status_legacy_flat_fallback_still_works` testet das korrekte
Verhalten und passt jetzt mit dem gefixten Code.

### Hotfix — Legacy CARIAD-flat doors fallback inversion bug (English)

One-line hotfix for a latent bug present since the legacy-fallback path
was introduced in v1.8.9. Caught by the v1.8.9 regression test
`test_v189_status_legacy_flat_fallback_still_works` which failed in CI on
PR #82 but the PR was merged anyway because branch protection on
required checks is not enabled in the repo (separate process gap to be
addressed).

**Bug:** in `seat_cupra.py` legacy-fallback block, `doors_legacy[door_id]
= not val` inverted the semantics — the CARIAD-BFF field is named
`doorClosed*`, so `True` means "door IS closed", matching our
`doors_individual` convention (True == closed) directly. The `not val`
was wrong.

**Fix:** `doors_legacy[door_id] = bool(val)`.

**Impact:** current CUPRA Born / Formentor / Tavascan models use the new
`status.doors.{position}.{locked,open}` paths from v1.8.9, so the bug
doesn't hit them in practice. Only matters if a future OLA API change
forces us onto the fallback path. Still must be fixed because: (1)
existing regression test must pass, (2) silent inversion in fallback
would hide as a real bug later, (3) main with failing tests blocks
every subsequent PR.

**Tests:** no changes needed — the existing v1.8.9 test now passes with
the fixed code.

## [1.8.9] - 2026-04-29

### Session 3C — CUPRA/SEAT OLA Status JSON-Pfade gefixt + Per-Window Entities + Live-API-Erkenntnisse

**Bug-Fix-Bündel** für Gerhards 19 fehlende Entities (CUPRA Born) und alle
SEAT/CUPRA-Modelle. Vor v1.8.9 las unser Parser aus
`/v2/vehicles/{vin}/status` mit CARIAD-BFF-typischen flachen Feldnamen
(`doorsOpenedCount`, `doorClosedLeftFront`, `trunk: "OPEN"` etc.). Diese
Felder existieren auf dem OLA-Backend
(`ola.prod.code.seat.cloud.vwgroup.com`) **nicht** — Konsequenz: Tür-,
Fenster-, Kofferraum-, Motorhauben- und Schiebedach-Entities blieben
permanent leer.

**Methodik (wichtig):** Wo möglich nehmen wir Field-Namen aus echten
Live-API-Responses (verifiziert via `tillsteinbach/CarConnectivity-connector-seatcupra`
Issues #5, #8, #18, #21, #50, #51, #109) und stellen sie an die Spitze der
`v(...) or v(...) or ...` Pfad-Listen. Die alten geratenen Pfade bleiben als
defensiver Fallback.

#### `cariad/api/seat_cupra.py` — `_parse_status` Status-Block neu geschrieben

**Doors / Windows / Trunk / Hood / Sunroof** (verifiziert gegen
`WulfgarW/pycupra/vehicle.py` ~Z. 3100-3325):

- **Per-Door:** `status.doors.{frontLeft,frontRight,rearLeft,rearRight}.{locked,open}`
  → `doors_individual` dict + abgeleitete `doors_open` und `doors_locked` aggregates
- **Per-Window (NEU):** `status.windows.{frontLeft,...}` (string `"closed"`/`"open"`)
  → `windows_individual` dict + `windows_open` aggregate
- **Trunk:** `status.trunk.{open,locked}` als nested object (statt flat string)
- **Hood:** `status.hood.open` (newer firmware)
- **Sunroof:** dreifach-Pfad `status.sunRoof` (Großbuchstabe R, top-level —
  CC-seatcupra **#5** verifiziert) ODER `status.sunroof` (pycupra) ODER
  `status.windows.sunroof` (firmware variance)
- **Engine (NEU):** top-level `status.engine: 'on'/'off'` (CC-seatcupra
  **#50**) → setzt `is_driving=True` und `vehicle_state="DRIVING"` wenn
  `engine='on'`. Behebt das verbreitete "vehicle_state immer parked"-Problem
  (CC-seatcupra **#18**)

**Defensiv:** Wenn keine der neuen Pfade Daten liefert, Fallback auf den
pre-v1.8.9 CARIAD-BFF-style Code (für sehr alte Firmware oder zukünftige
API-Änderungen).

#### `cariad/api/seat_cupra.py` — Charging-Endpoint Live-Response Erkenntnisse (#109)

**Methodik-Korrektur:** Reihenfolge der Pfad-Suche umgedreht — Rainer's
verifizierte Live-Response-Felder zuerst, alte geratene Pfade als Fallback.

OLA `/v1/vehicles/{vin}/charging` returns one of two shapes (live verifiziert):
- **Shape A:** `{"status": ..., "currentPct": ..., "remainingTime": ...,
  "chargeMode": ..., "preferredChargeMode": ..., "active": false}`
- **Shape B:** `{"state": ..., "chargedPowerInKw": ...,
  "remainingTimeInMinutes": ..., "type": ..., "mode": ...}`

Field-Reihenfolge jetzt korrekt:
- `charging_state`: `state` → `status` → `chargingState` (Legacy)
- `charging_power_kw`: **`chargedPowerInKw` (mit "d", verified)** → `chargePowerInKw` (Legacy)
- `remaining`: **`remainingTimeInMinutes` / `remainingTime` (verified)** → `remainingTimeToFullyChargedInMinutes` (Legacy)
- `charging_type`: `type` → `chargeType` (Legacy)
- `target_soc`: **`targetSoc_pct` (lowercase soc, verified)** → `targetSOC_pct` (Legacy uppercase)
- `is_charging` jetzt case-insensitive (`charging` ODER `CHARGING`)
- **`autoUnlockPlugWhenCharged: 'permanent'`** als 3. truthy-Wert (CC-seatcupra **#51** —
  vorher nur `"on"` matched, `"permanent"` Konfiguration wurde fälschlich
  als deaktiviert angezeigt)

#### `cariad/api/seat_cupra.py` — Climate robustness (#8, #21)

- `climatisation_state == "unsupported"` (CC-seatcupra **#21**) wird jetzt
  korrekt als inaktiv behandelt — vorher leer (zufällig korrekt, aber
  unklar dokumentiert)
- `targetTemperatureCelsius` (Rainer #109 Variante ohne "In") als zusätzlicher
  Pfad neben `targetTemperatureInCelsius`
- `climatisation_active` False-Set erweitert auf `(None, "OFF", "off", "Off", "unsupported")`

#### `cariad/models.py` — neues Field `windows_individual: dict[str, bool]`

Mirror von `doors_individual`. Keys: `frontLeft` / `frontRight` / `rearLeft` /
`rearRight`. Value `True` == Fenster geschlossen.

#### `binary_sensor.py` — neuer `VagWindowSensor` + Setup-Hook

Pro Fenster eine Binary-Sensor-Entity (`device_class=WINDOW`), Naming
`Window Front Left` etc. Nur erstellt wenn `windows_individual` Daten enthält
(SEAT/CUPRA initial; andere Marken folgen wenn deren API es liefert).

#### Tests (12 neue) — `tests/test_cariad.py::TestSeatCupraGetStatus`

1. `test_v189_status_parses_doors_per_position` — pycupra-Pfade door-Mapping
2. `test_v189_status_parses_windows_per_position` — neuer windows_individual
3. `test_v189_status_parses_trunk_hood_nested_objects` — nested {open, locked}
4. `test_v189_status_sunroof_in_windows_subtree` — sunroof in windows.sunroof
5. `test_v189_status_sunroof_top_level_camelCase` — `sunRoof` Großbuchstabe (#5)
6. `test_v189_status_engine_on_implies_driving` — engine='on' → DRIVING (#50, #18)
7. `test_v189_status_engine_off_does_not_force_driving` — engine='off' lässt vehicle_state in Ruhe
8. `test_v189_charging_shape_b_chargedPowerInKw_remaining_minutes` — #109 Shape B
9. `test_v189_charging_settings_targetSoc_pct_lowercase` — #109 lowercase variant
10. `test_v189_auto_unlock_permanent_is_truthy` — `permanent` als truthy (#51)
11. `test_v189_climatisation_trigger_unsupported_is_inactive` — `unsupported` → inaktiv (#21)
12. `test_v189_status_legacy_flat_fallback_still_works` — defensiver Fallback intakt

#### Bewusst NICHT in v1.8.9 enthalten (eigener Scope, geplant für v1.8.10+)

Alles aus dem Deep-Dive der CC-seatcupra-Issues, was eigene Entities oder
zusätzliche API-Calls braucht:

- **Capability-Filter** (CC-seatcupra **#64**) — `capability.active &&
  capability.user-enabled` vor Entity-Creation prüfen. Sehr wahrscheinlich
  weiteres Stück für Gerhards 19 fehlende Entities. Eigene Session
  (Erweiterung des bestehenden Capability-Cache).
- **`/maintenance` Endpoint** (CC-seatcupra **#44**) — separater API-Call mit
  4 neuen Sensoren (inspectionDueDays/Km, oilServiceDueDays/Km).
- **Multi-Zone Klima** (CC-seatcupra **#10, #109**) — `zoneFrontLeftEnabled`,
  `zoneFrontRightEnabled` als eigene Switches.
- **Battery Care Mode** (CC-seatcupra **#20, #51**) —
  `batteryCareModeEnabled`, `batteryCareTargetSocPercentage` als eigene
  Switch + Number.
- **`windowHeatingStatus[]` Array** (CC-seatcupra **#5, #8**) — strukturierter
  Array `[{windowLocation, windowHeatingState}]` statt unsere flat
  `windowHeatingStateFront/Rear` Pfade. Eigene Refactor-Session.
- **`/ventilation/start|stop` Service** (CC-seatcupra **#43**) — neuer
  HA-Service.
- **Trip-Statistics** (CC-seatcupra **#22**, MasterTim17 fork hat Code) —
  v1.10.x.
- **Departure-Timer Toggle** (CC-seatcupra **#70**) — v1.9.x.
- **`carCapturedTimestamp`-Freshness-Pattern** für CUPRA — wird in v1.8.10
  zentral für Škoda eingeführt (Session 3S) und kann später auf CUPRA + Audi
  expandiert werden.

### Session 3C — CUPRA/SEAT OLA Status JSON Paths Fixed + Per-Window Entities + Live-API Findings (English)

Bug-fix bundle for Gerhard's 19 missing entities (CUPRA Born) and all
SEAT/CUPRA models. Pre-v1.8.9 read `/v2/vehicles/{vin}/status` using
CARIAD-BFF-style flat field names that don't exist on the OLA backend.

**Methodology:** real-world API field names (verified via tillsteinbach
`CarConnectivity-connector-seatcupra` issues #5, #8, #18, #21, #50, #51,
#109) are placed at the head of `v(...) or v(...) or ...` chains. Old
inferred paths kept as defensive fallback.

**`seat_cupra.py` `_parse_status`** — verified against pycupra source:
per-door `status.doors.{position}.{locked,open}`, per-window
`status.windows.{position}`, nested `status.trunk.{open,locked}` and
`status.hood.open`, sunroof at THREE positions (`sunRoof` top-level from
#5, plus pycupra paths), engine top-level → DRIVING inference (#50, #18).

**Charging endpoint #109 paths reordered** — `chargedPowerInKw` (with "d"),
`remainingTimeInMinutes`, `targetSoc_pct` (lowercase) now first;
`auto_unlock_charge` recognises `"permanent"` (#51); climate handles
`"unsupported"` state (#21).

**`models.py`** — new `windows_individual` field. **`binary_sensor.py`** —
new `VagWindowSensor` per-window entity.

**12 new tests** in `TestSeatCupraGetStatus` covering both the new
structured paths and all live-API-response findings.

**Deliberately NOT in v1.8.9** (own scope): capability filter (#64),
`/maintenance` endpoint (#44), multi-zone climate (#10, #109), battery
care mode (#20, #51), `windowHeatingStatus[]` array (#5, #8),
`/ventilation` service (#43), trip stats (#22), departure timer toggle
(#70). All planned for v1.8.10+.

## [1.8.8] - 2026-04-29

### Session 3B — CARIAD v1/v2 + combined/separate endpoint dispatch für Lock/Climate/Charging

Erweitert das v1/v2-Fallback-Pattern aus Session 3A (4 Set-Value-Commands)
auf die sechs verbleibenden Hauptkommandos: `lock`, `unlock`,
`climate_start`, `climate_stop`, `charging_start`, `charging_stop`. Plus:
schließt einen versteckten Bug aus dem Pre-1.8.8-Code, in dem `except
Exception` Auth-Failures, Rate-Limits und 5xx-Errors als
Endpoint-Mismatches fehlinterpretierte und still den Fallback-Pfad
ansprach.

**`cariad/api/vw_eu.py` — neuer Helper `_post_command_with_fallback_paths`:**

Dispatcht in dieser Reihenfolge, jeder Aufruf via bestehendes
`_post_command` (das schon v1→v2 Fallback macht):

1. `primary_suffix` (combined endpoint) auf v1
2. `primary_suffix` auf v2 (bei v1-404)
3. `fallback_suffix` (separate endpoint) auf v1 (bei v2-404)
4. `fallback_suffix` auf v2 (bei v1-404)

**Kritische Verschärfung**: Fallback wird **nur** bei HTTP 404 ausgelöst.
Auth-Failures (401), Permission-Errors (403), Rate-Limits (429),
Backend-5xx und transiente Netzwerk-Fehler propagieren wie sie sollen
und werden vom Coordinator über `classify_command_failure` korrekt
klassifiziert.

**Refactor — 6 Commands nutzen den Helper:**

- `command_lock`: `access/lock-unlock` → `access/lock`
- `command_unlock`: `access/lock-unlock` → `access/unlock` (S-PIN in
  beiden Payloads, falls gesetzt)
- `command_start_climate`: `climatisation/start-stop` →
  `climatisation/start` (mit Default-Parametern wie vorher: 21°C,
  Window-Heating, ohne externe Stromversorgung)
- `command_stop_climate`: `climatisation/start-stop` →
  `climatisation/stop`
- `command_start_charging`: `charging/start-stop` → `charging/start`
- `command_stop_charging`: `charging/start-stop` → `charging/stop`

**`AudiClient` profitiert automatisch** über `VWEUClient`-Inheritance —
keine separaten Audi-Änderungen.

**Tests** (`tests/test_cariad.py::TestVWEUFallbackPaths`):

- 4 neue Tests:
  1. v1-Primary 404 → v2-Primary genutzt (kein Fallback-Endpoint
     berührt)
  2. Beide Primaries 404 → Fallback-Endpoint v1 genutzt
  3. **Regressionstest**: 500 vom Primary löst KEINEN Fallback aus
     (Hauptzweck dieser Session — vorheriger Code hätte still den
     Fallback-Endpoint angefragt und einen Backend-Hiccup als
     Endpoint-Mismatch maskiert)
  4. `command_unlock` mit S-PIN passt PIN in alle drei Payloads
     (combined v1, combined v2, separate v1)
- Existing Smoke-Tests in `TestVWEUCommands` bleiben ohne Anpassung
  pass — alle 6 Commands akzeptieren weiterhin 204 vom ersten Endpoint
  und brauchen nie den Fallback-Pfad im Happy-Path-Test.

**Bewusst NICHT in dieser Session enthalten** (Scope-Disziplin):

- **PPC/PPE Graceful Degradation per VIN-Heuristik** (`devicePlatform`
  Detection, Skip command-entities für E³-1.2-Vehicles): kommt in
  v1.8.9 — eigener Scope mit Repair-Notice + Tracking-Issue.
- **Optimistic-Update + State-Restoration** für lock/climate
  (`skodaconnect/homeassistant-myskoda` #832 Pattern): braucht eigenen
  Hotfix mit UI-Layer (entity availability state machine), nicht hier.
- **LEGACY_MBB Routing** für ältere T6/MQB Vehicles: blockiert auf
  T6-Logs von Tobias (#76); kein spekulatives Code-Schreiben.

### Session 3B — CARIAD v1/v2 + Combined/Separate Endpoint Dispatch for Lock/Climate/Charging (English)

Extends the v1/v2 fallback pattern from Session 3A (4 set-value commands)
to the six remaining main commands: `lock`, `unlock`, `climate_start`,
`climate_stop`, `charging_start`, `charging_stop`. Also: closes a
hidden bug in pre-1.8.8 code where `except Exception` misclassified
auth failures, rate limits and 5xx errors as endpoint mismatches and
silently called the fallback path.

**`cariad/api/vw_eu.py` — new helper `_post_command_with_fallback_paths`:**

Dispatches in this order, each call via the existing `_post_command`
(which already handles v1→v2 fallback):

1. `primary_suffix` (combined endpoint) on v1
2. `primary_suffix` on v2 (on v1-404)
3. `fallback_suffix` (separate endpoint) on v1 (on v2-404)
4. `fallback_suffix` on v2 (on v1-404)

**Critical narrowing**: fallback fires **only** on HTTP 404. Auth
failures (401), permission errors (403), rate limits (429), backend
5xx and transient network errors propagate as they should and are
correctly classified by the coordinator via `classify_command_failure`.

**Refactor — 6 commands use the helper:** `command_lock`,
`command_unlock`, `command_start_climate`, `command_stop_climate`,
`command_start_charging`, `command_stop_charging`. `AudiClient` benefits
automatically via `VWEUClient` inheritance.

**Tests** (`tests/test_cariad.py::TestVWEUFallbackPaths`):

4 new tests including the key regression test that a 500 on the
primary endpoint must NOT trigger the fallback (the main purpose of
this session — the previous code would have silently called the
fallback and masked a backend hiccup as an endpoint mismatch).

**Deliberately NOT in this session** (scope discipline):

- PPC/PPE graceful degradation via VIN heuristic — v1.8.9.
- Optimistic-update + state restoration for lock/climate (myskoda
  #832) — needs its own UI-layer hotfix.
- LEGACY_MBB routing for older T6/MQB — blocked on T6 logs from
  Tobias (#76); no speculative code.
## [1.8.7] - 2026-04-29

### Defensive Programming Pass — Retry-Härtung + Stale-Cache + Token-Refresh-Schutz

Auswertung der unabhängigen Multi-Source-Audit (`docs/AUDIT_2026-04-29.md`):
**Sechs von sechs untersuchten Reference-Repos** (we_connect_id, myskoda,
audi_connect_ha, pycupra, volkswagencarnet, CarConnectivity-Connectors)
haben dieselben Stabilitätsprobleme dokumentiert. v1.8.7 schließt vier
davon zentral statt punktuell pro API-Client.

**`cariad/api/base.py` — `_request()` Retry-Layer:**

- **HTTP 504 Gateway Timeout** ist jetzt Teil der Retry-Liste (war vorher
  fatal). Tritt regelmäßig auf der CARIAD BFF an Wochenenden auf
  (Quelle: `mitch-dc/volkswagen_we_connect_id` #165).
- **Server-Error Retries** auf 3 Versuche erhöht (war 2): 3s/6s/12s
  exponential backoff für 500/502/503/504.
- **Transiente Netzwerk-Fehler** werden jetzt mit demselben Backoff
  gehandhabt: `ClientConnectorError` (DNS/Connection refused),
  `ServerDisconnectedError` (Mid-Stream-Abbruch),
  `ClientPayloadError`, `asyncio.TimeoutError`. Wurden vorher als fatal
  raised und teilweise von oberen Schichten als Auth-Failure
  fehlinterpretiert (Quelle: `mitch-dc/volkswagen_we_connect_id` #166).
  Nach 4 erfolglosen Versuchen wird `APIError(0, ...)` mit prefix
  `"transient: ..."` raised — eindeutig unterscheidbar von HTTP-Errors.

**`cariad/api/base.py` — `_refresh_tokens()` Storm-Protection:**

- **Maximal 3 Token-Refresh-Versuche pro rollender Stunde.** Sliding
  Window mit `time.monotonic()`-Timestamps in `_refresh_history`. Bei
  Überschreitung wird `AuthenticationError("Token refresh storm — please
  reauthenticate")` raised; der Coordinator triggert daraufhin den
  HA-Reauth-Flow statt weiter zu loopen. Verhindert das Spirale-Pattern
  aus `skodaconnect/myskoda` #976 und
  `robinostlund/homeassistant-volkswagencarnet` #683, bei dem das
  Backend nach wiederholten Login-Versuchen die IP / das Konto temporär
  sperrt.

**`coordinator.py` — Failure-Tolerance + Stale-Cache:**

- **`is_vehicle_available(vin)` toleriert jetzt bis zu 3 aufeinanderfolgende
  Poll-Failures** bevor die Verfügbarkeit auf False kippt
  (`_FAILURE_TOLERANCE = 3`, Pattern aus `mitch-dc/volkswagen_we_connect_id`
  #215). Single-Poll-Hiccups auf der CARIAD BFF brechen Automatisierungen
  nicht mehr ab.
- **Stale-Cache-Window von 6 Stunden** (`_STALE_CACHE_WINDOW`):
  selbst nach Überschreitung der Failure-Tolerance bleibt das Fahrzeug
  verfügbar wenn der letzte erfolgreiche Poll innerhalb der letzten 6h
  lag. Pattern aus `skodaconnect/homeassistant-myskoda` #731 — User
  bevorzugen "alt aber sichtbar" über "unavailable", weil
  Automatisierungen weiter funktionieren und `last_updated_at` die
  Staleness signalisiert.
- Neue per-VIN Tracking-Dicts: `vehicle_failure_count` (Reset auf 0 bei
  jedem Erfolg) und `vehicle_last_good_at` (Timestamp letzter Erfolg —
  später auch für Diagnostics in Session 4).
- Lazy-Init mit `getattr(...)`-Fallback, damit Coordinators die vor
  v1.8.7 ohne `__init__` instanziiert wurden (Tests, Reload nach
  Upgrade) nicht crashen.

**Tests:**

- `tests/test_cariad.py::TestBaseClientHardening` — 5 neue Tests:
  504-Retry, ClientConnectorError-Retry, persistente Transient → APIError(0),
  Refresh-Storm-Protection, Refresh-Window-Pruning.
- `tests/test_coordinator.py::TestVehicleAvailabilityTolerance` — 7 neue
  Tests: Toleranz unter Schwelle, Verfügbarkeit über Schwelle ohne
  Recent-Good, Stale-Window-Hit, Stale-Window-Miss, Legacy-Coord-Fallback.
- `asyncio.sleep` wird in Retry-Tests gepatched, damit die Suite nicht
  länger läuft — der existierende 500-Test wartete vorher 9s, jetzt
  ohne Patch 21s; mit Patch in Sekundenbruchteilen.

**Bewusst NICHT in dieser Session enthalten** (Scope-Disziplin):

- EULA-Repair-Issue (`ir.async_create_issue` mit Direktlink): braucht
  eigene Translation-Strings in 8 Sprachen, kommt in v1.8.8.
- Generic-`except Exception` Audit quer durch alle API-Clients: größerer
  Refactor, eigener Hotfix.

### Defensive Programming Pass — Retry Hardening + Stale-Cache + Token-Refresh Guard (English)

Synthesis of the independent multi-source audit
(`docs/AUDIT_2026-04-29.md`): **six out of six reference repos**
investigated (we_connect_id, myskoda, audi_connect_ha, pycupra,
volkswagencarnet, CarConnectivity connectors) have documented the same
stability issues. v1.8.7 closes four of them centrally instead of
per-API-client.

**`cariad/api/base.py` — `_request()` retry layer:**

- **HTTP 504 Gateway Timeout** added to the retry list (was previously
  fatal). Routine on the CARIAD BFF on weekends (source:
  `mitch-dc/volkswagen_we_connect_id` #165).
- **Server-error retries raised to 3 attempts** (was 2): 3s/6s/12s
  exponential backoff for 500/502/503/504.
- **Transient network errors** now retried with the same backoff:
  `ClientConnectorError` (DNS / connection refused),
  `ServerDisconnectedError` (mid-stream disconnect),
  `ClientPayloadError`, `asyncio.TimeoutError`. Previously raised as
  fatal and sometimes misclassified by upper layers as auth failure
  (source: `mitch-dc/volkswagen_we_connect_id` #166). After 4 failed
  attempts, surfaces as `APIError(0, ...)` with `"transient: ..."`
  prefix — unambiguously distinguishable from HTTP errors.

**`cariad/api/base.py` — `_refresh_tokens()` storm protection:**

- **Maximum 3 token-refresh attempts per rolling hour.** Sliding window
  using `time.monotonic()` timestamps in `_refresh_history`. Exceeding
  raises `AuthenticationError("Token refresh storm — please
  reauthenticate")`; the coordinator then triggers the HA reauth flow
  instead of looping. Prevents the spiral pattern from
  `skodaconnect/myskoda` #976 and
  `robinostlund/homeassistant-volkswagencarnet` #683, where the backend
  temporarily bans the IP / locks the account after repeated login
  attempts.

**`coordinator.py` — failure tolerance + stale-cache:**

- **`is_vehicle_available(vin)` now tolerates up to 3 consecutive poll
  failures** before flipping availability to False
  (`_FAILURE_TOLERANCE = 3`, pattern from
  `mitch-dc/volkswagen_we_connect_id` #215). Single-poll hiccups on the
  CARIAD BFF no longer break automations.
- **Stale-cache window of 6 hours** (`_STALE_CACHE_WINDOW`): even past
  the failure tolerance, the vehicle stays available if the last
  successful poll was within the last 6h. Pattern from
  `skodaconnect/homeassistant-myskoda` #731 — users strongly prefer
  "old but visible" over "unavailable", because automations keep
  working and `last_updated_at` signals the staleness.
- New per-VIN tracking dicts: `vehicle_failure_count` (reset to 0 on
  each success) and `vehicle_last_good_at` (last-success timestamp,
  also surfaced in diagnostics in Session 4).
- Lazy-init with `getattr(...)` fallback so coordinators built before
  v1.8.7 without `__init__` (tests, post-upgrade reload) don't crash.

**Tests:**

- `tests/test_cariad.py::TestBaseClientHardening` — 5 new tests:
  504-retry, ClientConnectorError retry, persistent-transient →
  APIError(0), refresh-storm protection, refresh-window pruning.
- `tests/test_coordinator.py::TestVehicleAvailabilityTolerance` — 7 new
  tests: tolerance under threshold, unavailable over threshold without
  recent good, stale-window hit, stale-window miss, legacy coord fallback.
- `asyncio.sleep` patched in retry tests so the suite doesn't slow down
  — the existing 500 test previously waited 9s; without the patch now
  21s; with the patch sub-second.

**Deliberately NOT in this session** (scope discipline):

- EULA repair issue (`ir.async_create_issue` with deeplink): needs its
  own translation strings in 8 languages, ships in v1.8.8.
- Generic-`except Exception` audit across all API clients: larger
  refactor, its own hotfix.
## [1.8.6] - 2026-04-29

### Docs Truthfulness Hotfix — README + 8 translations + CI badge

Pure documentation release. Kein Code-Change, keine Verhaltensänderung —
nur die README-Familie auf den realen v1.8.5-Stand bringen und die strategische
Multi-Brand-Successor-Positionierung aufnehmen.

**Was korrigiert wurde:**

- **README.en.md sagte "cloud-push architecture"** — falsch seit v1.8.0
  (`iot_class` ist `cloud_polling`). Jetzt korrekt.
- **README.en.md sagte "14 services"**, README.md sagte "16 services" —
  beide jetzt vereinheitlicht auf die echte Zahl (14, verifiziert in
  `services.yaml`).
- **Hardcoded Test-Badge** ("Tests-337/337" in 7 Übersetzungen,
  "Tests-363/363" im DE-Master) ersetzt durch dynamischen
  GitHub-Actions-CI-Badge — driftet nicht mehr auseinander.

**Was neu hinzugekommen ist (in allen 8 Sprachen identisch):**

1. **Successor-Box** direkt nach dem Pitch: Aktiv gepflegter Multi-Brand-Nachfolger
   für `mitch-dc/volkswagen_we_connect_id` (archiviert 2025-10-29) und
   `skodaconnect/homeassistant-skodaconnect` (deprecated 2025-03-14). Eine
   Integration für Audi, VW, Škoda, SEAT, CUPRA, Porsche und VW US/CA.
2. **"Aktueller Stand & ehrliche Limits (v1.8.5)" Section** mit fünf
   transparenten Disclaimern:
   - Capability-Gating aktuell nur SEAT/CUPRA Flash/Wake
   - CARIAD v1/v2 Auto-Fallback aktuell nur 4 Set-Value Commands
   - Image-Plattform: kein offizielles Render-API existiert
   - PPC/PPE-Plattform (Audi Q5 2025, Q6 e-tron, A5/S5, A6 e-tron):
     Graceful Degradation statt 404, Endpoints noch nicht reverse-engineered
   - Privacy-Voraussetzung "Standort teilen" in der App muss aktiv sein

**Warum jetzt:**

Die unabhängige Multi-Source-Audit vom 29.04.2026 (siehe
`docs/AUDIT_2026-04-29.md`) hat festgestellt: Code und Releases sind weiter
als die README. Vor neuen Features (Session 3B/3C/3S) sollten Tester und
HACS-Browser realistische Erwartungen bekommen — sonst sieht die Integration
für sich beim ersten Klick "kaputt" aus, obwohl sie bewusst capability-gated
oder graceful-degraded.

### Docs Truthfulness Hotfix — README + 8 Translations + CI Badge (English)

Pure documentation release. No code change, no behaviour change — just
aligning the README family to the actual v1.8.5 state and adding the
strategic multi-brand-successor positioning.

**What was corrected:**

- README.en.md said "cloud-push architecture" — wrong since v1.8.0
  (`iot_class` is `cloud_polling`). Now correct.
- README.en.md said "14 services", README.md said "16 services" — both
  now unified to the real count (14, verified in `services.yaml`).
- Hardcoded test badge ("Tests-337/337" in 7 translations,
  "Tests-363/363" in the DE master) replaced by a dynamic
  GitHub Actions CI badge — no more drift.

**What was added (identically in all 8 languages):**

1. **Successor box** right after the pitch: active multi-brand successor
   to `mitch-dc/volkswagen_we_connect_id` (archived 2025-10-29) and
   `skodaconnect/homeassistant-skodaconnect` (deprecated 2025-03-14).
   One integration for Audi, VW, Škoda, SEAT, CUPRA, Porsche and VW US/CA.
2. **"Current state & honest limits (v1.8.5)" section** with five
   transparent disclaimers:
   - Capability-gating currently only SEAT/CUPRA flash/wake
   - CARIAD v1/v2 auto-fallback currently only 4 set-value commands
   - Image platform: no official render API exists
   - PPC/PPE platform (Audi Q5 2025, Q6 e-tron, A5/S5, A6 e-tron):
     graceful degradation instead of 404, endpoints not yet
     reverse-engineered publicly
   - Privacy prerequisite "Share my position" must be enabled in the app

**Why now:**

The independent multi-source audit on 2026-04-29 (see
`docs/AUDIT_2026-04-29.md`) found: code and releases are ahead of the
README. Before shipping new features (Session 3B/3C/3S), testers and
HACS browsers should get realistic expectations — otherwise the
integration looks "broken" on first click, when it is in fact
deliberately capability-gated or graceful-degraded.

