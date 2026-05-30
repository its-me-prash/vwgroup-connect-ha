# HACS-Safe Integration Checklist — Audit Status

> **Source:** Compiled from research notes
> (`_private/research-archive/vag-ha-integration-research.md` §6).
> **Audit date:** 2026-05-02 (post v1.16.1, during v1.17.0 prep).
> **Purpose:** Pre-condition for HACS Default Repository inclusion
> (planned for v2.0.0 release).

Legend: ✅ done · ⚠️ partial · ❌ missing · 🔮 planned

---

## Repo structure

| Item | Status | Notes |
|---|---|---|
| `custom_components/<domain>/manifest.json` with full metadata | ✅ | domain, name, version, documentation, issue_tracker, codeowners, requirements, iot_class, config_flow, dependencies — all present |
| `hacs.json` at repo root | ✅ | name, content_in_root: false, country: "DE" |
| `README.md` describing brands + install + config + privacy/quota | ⚠️ | Brands ✅, install ✅, config ⚠️ partial (privacy/quota refs FAQ.md as of v1.17.0), pre-v1.17.0 doesn't link FAQ |
| `LICENSE` (Apache 2.0 or MIT) | ✅ | Apache 2.0 |
| `info.md` (HACS-displayed) | ❌ | Could be added; HACS displays README by default — info.md is optional refinement |

---

## Code quality

| Item | Status | Notes |
|---|---|---|
| Async only (aiohttp, no blocking I/O on event loop) | ✅ | `cariad/api/base.py::_request` uses aiohttp.ClientSession |
| All API calls behind a single Coordinator per bucket | ⚠️ | Single coordinator with multiple async helpers (refresh_trip_statistics, refresh_charging_history, refresh_charging_profiles). 3-bucket polling refactor planned for v1.19.0+ |
| Strict typing in CI | ✅ | mypy strict in `Lint & Validate` workflow |
| Defensive parsing for nested dict access | ✅ | `safe_int`/`safe_float`/`safe_enum` (v1.10.1), `_val()` helper, `safe_path` planned port from pycupra `find_path()` |
| No URLs in `strings.json` / translations | ✅ | Verified — hassfest CI catches this |

---

## Config flow

| Item | Status | Notes |
|---|---|---|
| Initial step with timeouts on every network call | ✅ | `CariadBaseClient._request` has `_REQUEST_TIMEOUT = ClientTimeout(total=30)` |
| `async_step_reauth` for credential refresh | ✅ | Implemented since v1.8.x — preserves entity_ids + statistics history |
| `async_step_reconfigure` for changing options | ⚠️ | We have OptionsFlow (poll interval, S-PIN, reverse-geocoding, read-only, force_ppe_climate) but no dedicated reconfigure for brand-switch scenarios |
| Discovery uses vehicle capabilities — no entity for unsupported feature | ✅ | Capability-Filter Phase 3 (#56, since v1.13.0) — gates PRE-Entity-Creation per brand cap-id |

---

## Operational safety

| Item | Status | Notes |
|---|---|---|
| Master kill switch ("Mutable" toggle) | ✅ | Read-only Mode (`CONF_READ_ONLY`, since v1.12.0) — Phase 2 enforces service-side since v1.13.0 |
| Polling interval floor | ✅ | v1.17.0: floor 5min, default 10min. Pre-v1.17.0 was 3min/5min. |
| Nightly throttle window | ⚠️ | Hardcoded 22:00–05:00 doubles interval (since pre-v1.10.x). Not configurable yet. Could expose as `CONF_NIGHTLY_REDUCTION` toggle. |
| Per-vehicle log prefix | ❌ | Logs are mixed across VINs — multi-vehicle setups are harder to debug. Planned for v1.17.x or v1.18.0. |
| On failed user action: persistent_notification | ⚠️ | We have `ServiceValidationError` + Repair Issues (Vehicle Data Scout, Error Reporter). Persistent notification with actionable button (per pycupra v0.2.10) not implemented. |
| Unknown push-notification type: log + no-op | 🔮 | N/A — push not yet implemented (v1.18.0) |
| Out-of-order push event drop | 🔮 | N/A — push not yet implemented (v1.18.0). Pattern: stamp each MQTT event with the API's last-update timestamp + reject older events (myskoda PR #536 reference) |
| HTTP 500 from upstream: log once, continue with cached data | ⚠️ | We retry with backoff (`_request` has 3-attempt 5xx retry). We don't deduplicate the WARNING log. Planned for v1.17.x. |
| Vehicle "offline": surface as binary sensor | ✅ | `binary_sensor.{auto}_connection_state` (since v1.8.12) shows online/standby/offline |
| Daily quota near-zero: HA Repair Issue | ❌ | Need `requests_remaining_today` sensor first (planned for v1.17.x — surfaces the OLA `X-RateLimit-Remaining` response header as a diagnostic sensor) |
| Vehicle deactivated startup notification | ✅ | v1.17.0 — `_async_remove_stale_devices` raises persistent_notification before device removal |

---

## CI / release

| Item | Status | Notes |
|---|---|---|
| hassfest action | ✅ | `HA Hassfest` workflow runs on every PR |
| hacs/action validate | ✅ | `HACS Validation` workflow runs on every PR |
| pytest with fixtures | ✅ | 600+ tests across 30+ test files. Per-feature fixtures (Born, etc.) under `tests/fixtures/` |
| pytest fixtures for known push types | 🔮 | N/A — push not yet implemented |
| Year-end / DST boundary tests | ✅ | `tests/test_v1170_datetime_boundaries.py` (v1.17.0) |
| MQTT out-of-order event test | 🔮 | N/A — MQTT not yet implemented |
| Malformed API payload tests | ✅ | `tests/test_v1101_defensive_coding.py` + per-bundle defensive tests |
| Daily-quota exhaustion test | ❌ | Pending `requests_remaining_today` sensor implementation |
| Vehicle-offline test | ✅ | `tests/test_cariad.py::TestComputeConnectionState` |
| Capability-gated entity creation test | ✅ | `tests/test_v1130_production_hardening.py::TestCommandCapabilitySupported` + per-platform tests |
| mypy strict | ✅ | Required CI check |
| ruff | ✅ | Required CI check |
| Release notes pattern | ✅ | "Neu / Added", "Geändert / Changed", "Bug-Fixes / Bug-Fixes" — bilingual since v1.12.3 |
| Semver with vX.Y.Z tags | ✅ | Strict-Semver going-forward since v1.9.0; PATCH/MINOR/MAJOR per `manifest.json` rules |

---

## User-facing docs

| Item | Status | Notes |
|---|---|---|
| `FAQ.md` (privacy, quota, what-wakes-the-car, credential-rotation, entity-id stability) | ✅ | Created v1.17.0 (`docs/FAQ.md`) |
| `PRIVACY.md` describing data read + stored locally | ❌ | Privacy notes are scattered across README + diagnostics docstrings. Should be consolidated. |
| `CONTRIBUTING.md` pointing community to issues/discussions | ⚠️ | We have a `CONTRIBUTING.md`. Doesn't explicitly say "no Discord scrape" but the spirit is there via the Issue Forms (#64). |
| `BRAND_CAPTAINS.md` | ✅ | Initial Captains + "Bewährte Tester" list (#64, v1.13.0) |
| Issue templates (Bug Report, Scout Report, Error Report) | ✅ | `.github/ISSUE_TEMPLATE/*.yml` (#64, v1.13.0) |

---

## Outstanding before HACS Default submission (v2.0.0 prep)

Pre-conditions for v2.0.0 / HACS Default Repository inclusion:

1. **Per-vehicle log prefix** — multi-VIN debug-ability
2. **`requests_remaining_today` sensor** — quota visibility (needs per-brand X-RateLimit-Remaining header parsing)
3. **HTTP 500 "log once" pattern** — clean logs in production
4. **`PRIVACY.md`** — consolidated privacy reference for end users
5. **Live-Tests across all brands** — Brand Captains coverage matrix complete
6. **EU Data Act readiness** — port pycupra `EUDAConnection` (September 2026 EU deadline)
7. **CONTRIBUTING.md polish** — explicit issue-template-first guidance

Items in flight (planned for upcoming releases):

- v1.17.x: `safe_path` port, exception-taxonomy extension, `requests_remaining_today` sensor (pycupra-pattern-driven hardening)
- v1.18.0: Push (CUPRA/SEAT FCM + Skoda mysmob MQTT)
- v1.19.0+: Bucket-flag-style polling refactor (TTL-flag pattern: `BUCKET_TTL = {1: 120, 2: 600, 3: 1800}` per data-class, single coordinator with per-key `_due()` check)
- v2.0.0: HACS Default + EU Data Act
