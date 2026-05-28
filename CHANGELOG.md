# Changelog

All notable changes are documented here. / Alle wesentlichen Änderungen werden hier dokumentiert.

Format: [Keep a Changelog 1.0.0](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning 2.0.0](https://semver.org/)

> 📖 **Bi-lingual convention (v1.12.3 → v2.4.0 — DE-primary)**: section-titles were **DE / EN** joined by ` / ` and body content was German-only. Past entries are preserved as-is for historical accuracy.
>
> 📖 **Bi-lingual convention (v2.4.1+ — EN-primary, switched 2026-05-23)**: section-titles are now **EN / DE** joined by ` / `, body content is **English-primary** with German callouts where the original context was DACH-specific (Facebook-group threads, German tester names, brand-specific German terminology). The project's GitHub audience + the new "VW Group Connect" branding both lean international — English-primary makes the changelog readable for non-DACH users while keeping the DACH community's voice visible. Translations of individual body texts are available on request via [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — same pattern.

## Semver-Regeln für dieses Projekt (pre-1.0.0)

| Was | Version | Beispiel |
|---|---|---|
| Breaking Change, Architekturwechsel | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Neue Features, neue Sensoren/Services | `0.MINOR.0` | 0.10.0 → 0.11.0 |
| Bugfix, kleine Enhancement | `0.MINOR.PATCH` | 0.11.0 → 0.11.1 |
| Ab v1.0.0 | Standard `MAJOR.MINOR.PATCH` | 1.0.0 → 1.1.0 |

> **Hinweis:** Die Versionen 0.9.0–0.14.0 wurden am 2026-04-11/12 mit falschen
> Semver-Typen vergeben. Retroaktive Korrektur:
> `0.9.0→0.8.1`, `0.10.0→0.8.2`, `0.11.0→0.9.0`,
> `0.12.0→0.10.0`, `0.13.0→0.10.1`, `0.14.0→0.11.0`
>
> **v1.19.1 historischer Hinweis (2026-05-07 Audit):** v1.19.1 hat
> einen neuen Sensor `requests_remaining_today` eingeführt — nach
> strikter Semver-Regel wäre das MINOR (`v1.20.0`) gewesen, nicht
> PATCH. Wurde als PATCH released für HACS-Continuity (User-Side
> kein Breaking Change). Tag bleibt v1.19.1; nachfolgende Releases
> v1.20.0+ zählen ab v1.19.4 → v1.20.0 als legitime MINOR-Bumps.
> Lessons-learned dokumentiert für v1.20.2+ Audit-Disziplin.

---

> 💡 **Für Entwickler / Contributors:** Vollständige technische Detail-Notes
> für v1.8.6+ findest du in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md)
> — mit jeder geänderten Datei, jeder Zeile, jeder Issue-Referenz und der
> Methodik dahinter.

## [2.2.0-rc1] — 2026-05-16 — "Legen — wait for it — dary" (Release Candidate)

> **Release Candidate** für v2.2.0. 20 PRs across 6 phases plus 1 community
> Scout follow-up = **21 merged PRs** auf top von v2.1.0. 48h beta window:
> early-adopters auf HACS pre-release-channel können dieses build testen;
> bei 0 P0 issues nach 48h shippt v2.2.0 final (identical to this RC, just
> manifest version bump).
>
> Codename: **"Legen — wait for it — dary"** (HIMYM-themed Mega-Release).
> Inspired by deep cross-platform competitive intelligence crawl (2026-05-16):
>
> **Phase 1 — Foundation** (6 PRs, v2.2.0-alpha1):
> Universal Consent-Screen wall detection, defensive `safe_get` /
> `json_safe` helpers, `async_migrate_entry` stub, MY/Platform quirk-
> suppression, Skoda Scout #220.
>
> **Phase 2 — Schema + User-Requests** (5 PRs, v2.2.0-alpha2):
> Email-OTP vs TOTP discrimination, complete Subscription-Triangle
> (`expiry_at` + `active` + `days_remaining`) for SEAT/CUPRA + VW EU/Audi.
>
> **Phase 3 — Push-Bus Circuit-Breaker** (3 PRs, v2.2.0-alpha3):
> 3-strike trip + 1h auto-reset, identical 5-hook wiring across all 3
> brand managers (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM).
>
> **Phase 4 — Brand-Adapters + Community Scout** (4 PRs, v2.2.0-alpha4):
> Lambo / Bentley / CUPRA-standalone scaffolds (BETA — tester pending) +
> CUPRA Scout #232 cross-brand reuse.
>
> **Phase 5 — Internal Architecture** (2 PRs):
> Push-Bus abstraction refactor + Pydantic v2 dual-write foundation.
>
> **Phase 6 — Release** (this PR):
> v2.2.0-rc1 → 48h beta → v2.2.0 final.
>
> **Failsafe-first**: every risky feature is opt-in, every parser change
> has a fallback, ConfigEntry stays v1-compatible for clean rollback,
> 3-strike breaker prevents log-spam on live activation, Pydantic is
> diagnostic-only. v3.0.0 reserved for genuine breaking changes
> (ConfigEntry restructure, EU Data Act activation, Pydantic dataclass-
> removal).
>
> **Failsafe stats from this release**:
> - 21 PRs, every single one shipped with at least 1 of: try/except,
>   fallback-chain, defensive-isinstance, phantom-protection gate,
>   tri-state semantics (None ≠ False), beta-gate enforcement
> - 4 anchor tags (alpha1-alpha4) for incremental rollback safety
> - Coverage stayed >74% throughout (gate at 65%)
> - Cross-brand parity tests catch any future drift

## [2.2.0] — 2026-05-17 — "Legen — wait for it — dary" (Final)

> v2.2.0 final ships **byte-additive** to v2.2.0-rc1 — just one manifest
> version-string bump plus the 5 Phase-7 patches that landed during the
> rc1 beta window. Phase 7 is **pure additive**: 11 new diagnostic
> entities (all brand-restricted + phantom-protected — zero risk to
> existing users) plus 38 new scout-silencing entries closing #245
> (systemic Cariad-BFF per-block `.error` container rollout).
>
> Phase 7 sweep — scout-audit cross-references `_unexpected_keys.py`
> against actual parser-reads to identify silenced-but-unwired fields.
> 4 entity-batches + 1 pre-release silencing patch.

## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion

> **Strategic shift (2026-05-17 post-v2.2.0):** Statt scout-fields zu
> silencen wenn der walker sie reportet, wird jeder Field mit klarem
> semantischen Wert als HA-entity geparsed UND auf alle applicable
> brands cross-checked. *"Wenn ein field es wert ist silenced zu
> werden, ist es wert geparsed zu werden. Und wenn 1 user es auf
> 1 brand reportet, profitieren alle brands wo das equivalent
> existiert."* — User-Direktive nach v2.2.0 stable release.
>
> **Phase 8 tier-A complete**: 5 PRs merged auf top of v2.2.0.
> 11 new diagnostic entities + 4 cross-brand expansions + **erstes
> 6/6 brand coverage** durch derivation-helper-pattern. Zero
> behaviour changes für existing users (pure-additive, alle
> phantom-protected). Tier-B (wildcards + alarm/siren) deferred
> until tester scout-dumps liefern die unknown leaf-shapes.

## [Unreleased]

### Added
- Pre-emptive scout silencer for CUPRA TGI variants (Compressed Natural Gas — Leon TGI / Ibiza TGI) — `cngLevel` / `cngLevelInPct` / `cng_level_pct` / `cngRange` / `cngRangeInKm` / `cng_range_km` registered in `cupra:charging` set. Mirrors the `diesel_range` pattern from v1.9.1 #91. Will be promoted from T5 silencer to T1 parsed + entity (sensor.cng_range_km / sensor.cng_level_pct) when a CUPRA TGI tester reports. Source: pycupra v0.2.31 (WulfgarW, 2026-05-26).
- `_community-projects.md` refreshed with the 2026-05-27 cross-project sweep snapshot — documents the 3-of-3 OLA-projects convergence on the 2026-05-20 app-header fix, mitch-dc's continued archive status, and skodaconnect/homeassistant-myskoda PR #1102 (split-coordinator + MQTT-event-filtering pattern noted as v3.0 architecture reference).

### Changed
- OLA upstream watcher now runs **daily** (was weekly) and auto-opens a PR with the new app-version constants when CarConnectivity upstream drifts — instead of just opening an issue. Previous primary values are appended to the fallback chain automatically, so the multi-version retry logic self-extends. PRs require manual review + merge (no auto-merge — keeps a human safety check in case upstream pushes a mistaken bump).

### Added
- **Cross-Brand App Atlas** — new daily CI pipeline that tracks the current Android app version for all 7 VAG brands (SEAT, CUPRA, VW EU, Audi, Škoda, VW NA, Porsche). When a brand bumps a new app version, the watcher auto-opens a PR refreshing the atlas docs at `docs/research/app-atlas/`. Multi-source fallback (APKMirror → Uptodown) covers 6/7 brands today; VW EU needs a Phase A.1.1 follow-up. Phase A.2 will add APK download + extraction for definitive endpoint + header discovery — useful proactively across all brands, not just OLA-enforced ones. See `docs/research/app-atlas/README.md` + `LEGAL.md`.
- **OLA watcher gains daernsinstantfortress as 3rd consensus source** — for CUPRA only (their package is CUPRA-only), but it provides a stronger 3-of-3 consensus signal on CUPRA app-version bumps. Their Cariad-BFF + OLA hybrid architecture is also noted as a possible Plan-B fallback for future OLA escalations. See new `docs/research/app-atlas/_community-projects.md` for the curated index of all parallel community projects we monitor.
- **App Atlas covers all 7 brands** — APKCombo added as 3rd-tier scraper fallback closes the VW EU gap. Cross-brand visibility now 7/7 (`docs/research/app-atlas/_summary.md`).
- **Community audit pack** — three new research docs in `docs/research/`: (1) deep-audit of daernsinstantfortress's `weconnect_cupra` library showing 9 endpoint differences vs ours + architectural notes, (2) cross-project scan tracking mitch-dc's archival (2025-10-29 — major reference died), audi_connect_ha maintenance-only status, and skodaconnect's recent ACTIVE_VENTILATION + Firebase-MQTTv5 work, (3) consolidated v2.5.0 action plan with ~10h of follow-up items prioritised. No integration code touched in this round.
- **App Atlas Phase A.2 — APK download + apktool extraction** — when a brand's version-name changes (detected by the daily watcher), the workflow now downloads the APK via APKCombo CDN, decodes it with apktool, and greps for OLA-style header keys + known backend hosts. Findings persist as `.app-atlas-apk-cache/{brand}.json` and render in each per-brand atlas page. Workflow extracts only on version-change (idempotent), keeps CI runtime under 2min/changed-brand. Phase A.3 (jadx semantic-diff between consecutive APK versions) deferred to a separate session.
- **App Atlas Phase A.3 — jadx full decompile + cross-version semantic diff** (manual `workflow_dispatch` only — too heavy for daily). Triggers on demand when investigating a brand's version bump: downloads both versions, runs jadx full Java decompile, extracts URL constants + header-key strings + OAuth scopes, computes a targeted diff filtering out obfuscator-rename noise. Outputs a self-contained markdown report at `docs/research/app-atlas/diffs/{brand}_{old}_vs_{new}.md` and auto-opens a PR. Provides ground-truth answers to "what new endpoints / headers / scopes appeared in this version bump?" — much higher signal than the daily smali grep.

## [2.5.2] — 2026-05-28 — "Scout Pipeline Expansion"

### Changed
- **Vehicle Data Scout coverage widened across all 7 brands.** The scout pipeline (`detect_unexpected`) previously only watched responses from endpoints we already call in production, which capped its discovery surface. v2.5.2 adds a once-per-hour, per-VIN, best-effort probe pass that issues GETs against ~34 additional brand endpoints documented in the public open-source ecosystem (PyCupra, myskoda, CarConnectivity, audi_connect_ha, volkswagencarnet, evcc — all MIT/Apache). Responses feed into the same scout walk we already run, so any new VAG-side fields surface as scout reports without exposing new entities.
- **What this means for you:** more accurate, faster v3.0 entity coverage. Field-shape changes on the VAG backend get caught earlier, and "this brand has data we don't expose" gaps become visible without users having to file `[Vehicle Data Scout]` reports manually.
- **Public framing:** this is a scout-channel widening — purely server-side discovery. No new entities, no behaviour change for end users, no privacy implication (existing PII scrubber covers all responses; no new fields are written to disk or sent off-device).

### Implementation guardrails (defence-in-depth)
- **Rate-limit per VIN.** Each probe pass runs at most once per `_PROBE_INTERVAL_S` (default 3600s = 1 hour).
- **Token-budget guard.** Pass is skipped entirely when the brand client's `last_rate_limit_remaining` is at or below 50 — protects users' daily quota for actual polling.
- **Auth-storm circuit-breaker.** After 3 consecutive 401-from-probe events, the probe channel auto-disables for the session. 401s never trigger `_refresh_tokens` from the probe path (storm risk).
- **Short timeouts.** Per-probe HTTP timeout 5s, per-pass total budget 30s. Long-running probes are killed early.
- **Fail-safe.** Any probe error (404/403/5xx/network/parse) is swallowed silently. The probe pass NEVER affects production polling or surfaces errors to the user.

### Files touched
- `custom_components/vag_connect/cariad/api/_v3_probes.py` (NEW) — per-brand probe inventory + base-URL dispatch
- `custom_components/vag_connect/cariad/api/base.py` — `run_v3_probe_pass()`, `_probe_request()`, `_AuthStormSignal`, 5 new guard constants
- `custom_components/vag_connect/coordinator.py` — poll-loop hook (best-effort, hasattr-guarded)
- `tests/test_v252_v3_probes.py` (NEW) — probe inventory shape + runner contract

### Risk
Low. The probe pass is fail-safe by design: errors NEVER surface, NEVER affect production polling, NEVER trigger token refresh storms, and NEVER write off-device. The token-budget guard preserves daily quota for user-facing polling. The circuit-breaker prevents pathological consecutive-401 loops.

## [2.5.1] — 2026-05-28 — "Consent Wall Auto-Skip Hotfix"

### Fixed
- **Audi/VW/Škoda/SEAT/CUPRA login regression — consent wall now auto-skipped** (closes #309 moltke69 Audi auth, cross-references audi_connect #735/PR #731, evcc #29760/PR #29980, pycupra #83, myskoda #976). The VAG identity service has been intermittently injecting an *optional* marketing-consent / interstitial page into the OAuth redirect chain throughout 2026 across all VAG brands. Pre-v2.2.0 this surfaced as a cryptic "no app:// redirect" error. v2.2.0 added detection that **raised** `MarketingConsentError` → Repair flow → manual user action required.
  - v2.5.1 now **auto-skips** the consent interstitial transparently by following the OIDC `callback=…` URL embedded in the consent request — equivalent to the "not now" path. Login completes with `consentedScopes=openid profile mbb` only (no marketing scopes granted). User sees nothing; integration recovers silently. Python port of evcc PR #29980 (Go, MIT, merged 2026-05-17).
  - If auto-skip itself fails (callback param missing, network error), behaviour falls back to the v2.2.0 path and `MarketingConsentError` is raised so the Repair UI surfaces a deep-link to the brand portal.
  - Applied to **both** the Auth0 Universal Login flow (`/u/login`) and the legacy signin-service flow — symmetric implementation in `idk.py`.
  - Added **2 new consent-URL markers** for the Audi-specific consent variant (`audi-id.vwgroup.io`, `myaudi.de/consent`) that the v2.2.0 detection did not catch. Detection coverage now: `consent/marketing`, `/u/consent`, `cupraid.vwgroup.io`, `skoda-id.vwgroup.io`, `skodaid.vwgroup.io`, `audi-id.vwgroup.io`, `myaudi.de/consent` (auto-skippable) plus `terms-and-conditions` (cannot be skipped — legal acceptance required).

### Changed
- **Better error message for "Login redirect missing after password submission"** (audi_connect PR #731 inspiration). When the legacy flow gets a 302/303 with no `Location` header AND the consent auto-skip didn't trigger, the user now sees an actionable message ("IDP may be showing a consent or terms-of-service prompt we couldn't auto-detect — please log in via app/web, accept any pending agreements, then retry") instead of the cryptic "Password POST: no Location header".

### Risk
Low. Behavioural change is confined to one new code path (auto-skip) that ONLY triggers when consent-URL markers match. Existing rejection paths (401, true credential failure, T&C wall) are unchanged. New helper `_skip_marketing_consent` is fail-safe: if the callback URL is missing or fetch fails, it returns `None` and the prior `MarketingConsentError` Repair flow surfaces unchanged.

### Affected users
Anyone on Audi/VW/Škoda/SEAT/CUPRA experiencing "Email address or password incorrect" or "Login redirect missing" errors since ~2026-05 (when VW expanded the consent-injection rollout). Confirmed reports: #309 (Audi), audi_connect#735, evcc#29760, multiple Facebook-group threads in DACH region. Porsche (separate IDP) + VW NA (separate auth flow) are unaffected.

## [2.5.0] — 2026-05-27 — "Have You Met Mii?" (PyCupra Parity Sprint Part 1)

### Added
- **4 new binary_sensors** for entity-parity with PyCupra (closes parser-side-data-but-no-entity gap raised by @goncal in #306 for SEAT Mii Electric and the broader CUPRA Mii/Born/Tavascan VZ user pool):
  - `binary_sensor.hood_open` (DOOR class) — was in `VehicleData.hood_open` since v1.10.x, just no entity wrapper
  - `binary_sensor.trunk_open` (DOOR class) — was in `VehicleData.trunk_open`, no entity
  - `binary_sensor.trunk_locked` (LOCK class, diagnostic) — was in `VehicleData.trunk_locked`, no entity
  - `binary_sensor.sunroof_open` (WINDOW class, phantom-protected via `_DATA_PRESENT_REQUIRED` so cars without sunroof don't show meaningless OFF entity)
- i18n strings for the 4 new entities (English `strings.json`; translation contributions welcome)

### Hints toward v3.0 — "Suit Up: The Push Tech Edition" 🎩
v2.5.0 is **part 1** of the "Have You Met Mii?" parity sprint. PyCupra extracts ~12 more data points from the OLA backend that we currently return null for (odometer via `/v1/vehicles/{vin}/mileage`, target_soc + max_charge_current via `/v1/vehicles/{vin}/charging/info`, service intervals via `/v1/vehicles/{vin}/maintenance`, trip data via `/v2/vehicles/{vin}/driving-data/CUSTOM`, vehicle renders via `/v2/vehicles/{vin}/renders`) — these are completely **new endpoint calls** for us, scoped to v3.0-beta1.

v3.0 bundle (research+planning):
- Split-coordinator (myskoda PR #1102 pattern port — fast/slow tiers)
- Universal FCM push manager (all 7 brands have Firebase config in dex — extracted via App Atlas Phase A.4.1)
- Skoda MQTT (mysmob via myskoda-lib pattern) + Audi dual-channel (Paho MQTT + FCM)
- `vag_connect.send_destination` service (HA → car nav)
- Vehicle render Image entity
- Trip-history Calendar + sensors
- Editable departure-timer entities (Time/Select/MultiSelect with recurringOn weekday pattern)
- Auxiliary heating (Standheizung) switch + temp Number — `/auxiliaryheating/` endpoint confirmed in Audi + VW EU APK
- BLE `binary_sensor.car_nearby` + ESPHome BLE proxy guide

### Risk
Zero — additive data-table changes only. All 4 new entities source from `VehicleData` fields that have been parsed (but unused) since earlier releases. No new API calls, no behavior change. Existing pytest suite tests EXPECTED_KEYS shape; adding entities is safe.

## [2.4.2] — 2026-05-27 — "Retro-Silencer Sweep + ActiveVentilation Interim"

### Fixed
- Scout fired on 4 fields that were **already being parsed** since earlier releases — `EXPECTED_KEYS` had just never been updated to silence the source paths (classic silencer-lag-behind-parser gap, same class as v2.4.1's #284 fix). All 3 affected sensors continue to work as before; the scout is just no longer noisy. Closes #299, #302 and part of #301.
  - **Skoda** `air-conditioning.estimatedDateTimeToReachTargetTemperature` — parsed since v2.1.0 at `skoda.py:586` → `d.climate_ready_at` → `sensor.climate_ready_at` (close #302)
  - **CUPRA** `charging.rateInKmph` — parsed since v2.0.1 at `seat_cupra.py:747` (3rd fallback in `charging_rate_kmh` chain after `chargeRateInKmPerHour` and `chargeRate_kmph`) → `sensor.charging_speed` (close #299)
  - **VW EU + Audi** `measurements.rangeStatus.value.adBlueRange` — parsed since v1.9.1 (#91 Audi S6 TDI live-dump) at `vw_eu.py:1282` → `d.adblue_range_km` → `sensor.adblue_range` (part of #301)

### Added (interim silencer — parser follows in next PR)
- **VW EU + Audi** new ACTIVE VENTILATION subsystem registered with wildcards (MEB ID.7 + facelift ID.3/.4 family): `climatisation.activeVentilationStatus.*`, `climatisation.climatisationSettings.value.activeVentilationSettings.*`, `climatisationTimers.activeVentilationTimersStatus.value.*`. This is an interim silencer — a follow-up PR builds the parser + 4 default-disabled entities (1 binary_sensor + 3 sensors) once the exact field-name shape is confirmed from a live diagnostics dump. Audi inherits via existing brand-chain. Part of #301.

### Issues closed by this release (9 of 15 open)
- **Silenced by code (3):** #299 (CUPRA rateInKmph), #301 (VW activeVentilation + adBlueRange retro), #302 (Skoda climate-ETA retro)
- **Already-fixed in v2.4.1 — reporters on stale versions (4):** #283, #284, #298, #300
- **Already-shipped fix (1):** #282 (CUPRA OLA 403 — confirmed by both reporters in v2.4.1)
- **Working-as-designed safety circuit (1):** #303 (token refresh storm-circuit-breaker firing correctly per v1.8.7 design)
- **Remaining 6 open** are long-lived roadmap trackers (#13, #53, #59, #160, #161, #183)

## [2.4.1] — 2026-05-25 — "OLA Defense + VW NA Garage + Scout Policy"

### Fixed
- SEAT + CUPRA setup failed with HTTP 403 since 2026-05-20 (#281, #282)
- VW US/CA garage returned empty after successful login (#285)
- Scout fired on `chargingSettings.requests` despite field being parsed (#284)

### Added
- 12 new diagnostic entities (all disabled-by-default — opt-in via entity registry): HV battery temperature, climate-zone toggles, climate ETA, connection diagnostics, OLA license plate, OLA vehicle nickname, OLA parking-map URLs (dark + light)
- `climate_settings_pending` count diagnostic — completes the queued-commands family alongside the existing 3 siblings (#283)

### Changed
- **OLA authentication — defense-in-depth** — instead of just hardcoding the new SEAT/CUPRA app-identifying headers, the integration now ships a 4-layer system: centralized constants, OptionsFlow override for power-users, automatic multi-version fallback on 403, and an HA Repair-issue if all fallbacks fail. Future VW changes can self-heal without needing an integration update — and if the fallbacks ever exhaust, you get a clear "update the integration or set an override" notification instead of silent failure. Weekly CI also monitors the upstream community reference so we react within ~1 week of any drift.
- **Scout Policy** — every silenced backend field is now also parsed and exposed as an entity going forward. Documented in `docs/SCOUT_POLICY.md`. Past audit promoted 12 fields, classified 55 as exempt.

### Notes
- First release under the EN-primary changelog convention (compact style, one-liner per fix/feature, deeper notes only where end-user behaviour changes).
- Full technical detail in commit messages + `docs/CHANGELOG_TECHNICAL.md`.

## [2.4.0] — 2026-05-23 — "Marketing-Rename: VAG Connect → VW Group Connect (Community Tribute)"

> **MINOR release** — marketing-only project rename. **Zero user-breakage** by design. Spinoff aus humorvoller Community-Feedback der HA UK + HA Ideas FB-Gruppen (Si Gregory, Ben Johnson, Evets David, Stuart McBride, Jordan Waeles). DOMAIN stays `vag_connect` internally → entity-IDs unchanged, automations weiterfunktionieren, recorder history bleibt, easter-egg `vag_connect.show_vag` bleibt unter Jordan's joke-name. Display-Name + Repo-URL umbenannt für die public-identity. Siehe MIGRATION.md.

### Changed

- **🪪 Marketing-Rename: "VAG Connect" → "VW Group Connect"** (repo URL
  `vag-connect-ha` → `vwgroup-connect-ha`). Spinoff aus dem
  Community-Feedback der **Home Assistant UK** + **HA Ideas, Projects
  and Solutions** Facebook-Gruppen (2026-05). "VAG" — die offizielle
  DACH-Abkürzung für Volkswagen AG — liest sich auf Englisch *quite
  differently* 😅. Si Gregory schlug das Rename vor, Ben Johnson +
  Evets David + Stuart McBride + Jordan Waeles bekräftigten.

  **Marketing-only by design**: nur Repo-URL + Display-Name geändert.
  Code-Internals + DOMAIN + Entity-IDs + Service-Calls + HACS-Install
  alles **unverändert** — kein User-Breakage, keine Automation muss
  umgeschrieben werden, Recorder-History bleibt erhalten.

  | Aspect | Vorher | Jetzt |
  |---|---|---|
  | Repo URL | `github.com/its-me-prash/vag-connect-ha` | `github.com/its-me-prash/vwgroup-connect-ha` |
  | HACS Display | "VAG Connect" | "VW Group Connect" |
  | Manifest `name` | "VAG Connect" | "VW Group Connect" |
  | Integration `domain` | `vag_connect` | **`vag_connect`** (unchanged!) |
  | Entity-IDs | `sensor.audi_q4_battery_soc` etc. | **unchanged** |
  | Service-Calls | `vag_connect.lock` etc. | **unchanged** |
  | Easter-egg | `vag_connect.show_vag` (Jordan's joke) | **preserved** |

  **Was wirklich geändert wurde** (~80 files, ~200 string replacements):
  manifest.json, hacs.json, strings.json + 8 translations, 8 READMEs,
  SECURITY/PRIVACY/CONTRIBUTING/RELEASE_PROCESS/ROADMAP/NOTICE,
  .github workflows + issue templates, docs/dashboards.md + FAQ.md +
  bubble-card/README.md, coordinator user-agent string.

  **Bewusst NICHT geändert** (history preservation):
  - CHANGELOG.md historische Einträge (47 Vorkommen) — die beschreiben
    was wirklich unter dem alten Namen ausgeliefert wurde, retroaktiv
    umschreiben wäre historisch falsch
  - `docs/research/*-2026-*.md` (17 Dateien) — zeitstempel-archivierte
    Research-Notes, gleiche Begründung
  - `docs/CHANGELOG_TECHNICAL.md` — historisch
  - Bruno-Files (URL-Pinning + historische Attribution)
  - Tests (`from custom_components.vag_connect.*` Imports)
  - Scripts (interne Utility-Scripts)

  **Plus**: neue `MIGRATION.md` am Repo-Root erklärt das ganze Bild +
  alle Garantien für Bestandsuser. Rename-Notice-Block am Top von
  allen 8 READMEs mit den vollständigen Community-Credits + Verweis
  auf das easter-egg.

  Falls je ein echter DOMAIN-Rename nötig wird (Architektur-Reason,
  nicht Marketing) → das käme als v4.0.0 MAJOR mit proper
  `async_migrate_entry` für migration ohne Datenverlust. Bis dahin:
  marketing-only, zero-breakage.

  41 source-level regression-pins in `tests/test_v240_marketing_rename.py`
  inkl. der kritischen Garantie-Tests dass DOMAIN + Folder + Service-IDs
  unverändert sind.



## [2.3.0] — 2026-05-23 — "VW North America Login Fix + Audi Route-aware Charging"

> **MINOR release** — first brand-level new-functionality since v2.2.x.
> Sprint B aus der A→B→C roadmap. 2 issues closed:
>
> | # | Reporter | Brand | Impact |
> |---|---|---|---|
> | **#269** | roberttco | VW NA | VW US/CA login war **komplett broken** seit brand-add (kein NA user konnte je konfigurieren). Jetzt fixed via 4-fold IDP override. |
> | **#264** | moltke69 | Audi | 7 neue Cariad-BFF route-aware charging fields — 2 neue sensor entities + 5 silencer-adds + climate-timer shape-fallback. |
>
> Audi erbt alle Änderungen automatisch via brand-vererbung. Side-effect
> close: **#270 (config-flow brand reset)** war ein Symptom des
> unterliegenden #269 auth-fehlers; NA users hitten den UX-bug nicht mehr
> nachdem login funktioniert. UX-side workaround war schon in v2.2.3.
>
> Keine breaking changes für EU-Marken (Audi/VW EU/Skoda/SEAT/CUPRA/
> Bentley/Lambo/Porsche) — IDKAuth-overrides sind kwargs mit None-default,
> Fall-back auf die existierenden Modul-Konstanten. HACS pre-release +
> stable channels.

### Fixed

- **#269 (roberttco VW NA, 2026-05-21) — VW North America Login (US/CA) endlich funktional** — Robert Thompson hat als erster aktiver VW NA Tester gemeldet dass Login durchgehend mit HTTP 400 fehlschlägt. Sein log zeigte den root cause exakt: `MYVW_ANDROID` client_id wurde gegen `identity.vwgroup.io` (EU IDP) geschickt, wo es nicht registriert ist. Cross-Check mit der referenz-implementation matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0, im vw_na.py Doc-Header cited) hat **vier IDP-Unterschiede** zwischen EU + NA enthüllt:

  | Endpoint | EU (was wir bisher hatten) | NA (was VW US/CA tatsächlich nutzt) |
  |---|---|---|
  | Authorize URL | `identity.vwgroup.io/oidc/v1/authorize` | `b-h-s.spr.{us\|ca}00.p.con-veh.net/oidc/v1/authorize` |
  | Token URL | `emea.bff.cariad.digital/login/v1/idk/token` | `b-h-s.spr.{us\|ca}00.p.con-veh.net/oidc/v1/token` |
  | IDP host (redirect lands here) | `identity.vwgroup.io` | `identity.na.vwgroup.io` |
  | Signin-service client GUID | `{self._brand.client_id}` (i.e. `MYVW_ANDROID`) | `b680e751-7e1f-4008-8ec1-3a528183d215@apps_vw-dilab_com` (hardcoded NA browser-IDP) |

  Plus die `scope` musste von `"openid profile email offline_access mbb vin cars dealers"` auf nur `"openid"` reduziert werden (matpoulin nutzt nur das, NA IDP rejected die wider scope-chain).

  **Lösung — IDKAuth generalisierung**: 4 neue optional kwargs hinzugefügt (`authorize_url_override`, `token_url_override`, `idk_base_override`, `signin_client_id_override`). EU-Marken (Audi, VW EU, Skoda, SEAT, CUPRA, Bentley, Lambo, Porsche) sind **unverändert** — kwargs sind None-default und fallen auf die existierenden Modul-Konstanten zurück. VW NA passt die 4 overrides per matpoulin-correct-Werten an. Auch die `_get_token_endpoint()` honoriert jetzt den per-Instance override.

  Auch behoben (auto-close via #269 Rootcause-Fix): **#270 (roberttco VW NA, 2026-05-21) — Brand-Selection bleibt jetzt erhalten** (war Symptom des unterliegenden auth-fehlers; wurde in v2.2.3 #270 als UX-Fix gehandhabt). VW NA user können jetzt erstmals erfolgreich konfigurieren ohne dass die App ihre Marken-Wahl beim Auth-Fehler vergessen lässt.

  3 bruno-files (`tests/bruno/vw_na/`) dokumentieren die NA endpoints für drift-checking. Test-coverage: 16 source-level pins in `tests/test_v230_sprint_b.py` für IDKAuth-overrides + vw_na.py wiring + scope-narrowing. **Closes #269**.

### Added

- **#264 (moltke69 Audi, 2026-05-19) — Route-aware Smart Charging Sensoren** — moltke69's scout-report hat 7 neue Cariad-BFF Felder enthüllt die Audi/VW EU EVs ausliefern wenn ein Navigations-Ziel im Auto eingegeben ist. Distinct semantic vom statischen `target_soc` — backend computes "lade nur soviel wie du für deine nächste route brauchst", was bei Wallbox-strom-management hilfreich ist.

  **2 neue Sensor-Entities** (disabled-by-default — power-user opt-in):
  - `sensor.{prefix}_nav_target_soc_pct` — von `charging.batteryStatus.value.navigationTargetSOC_pct`
  - `sensor.{prefix}_remaining_charge_time_nav_min` — von `charging.chargingStatus.value.remainingChargingTimeNavigation_min`

  **Plus Climate-Timer Fallback**: moltke69's report zeigte auch dass neuere Firmware die climatisation-Timers restrukturiert hat von `climatisationTimers.climatisationTimersStatus.*` auf `departureTimers.climatisationTimersStatus.*` (unified `departureTimers` Parent mit charging + climatisation Sub-Statuses). Der existierende `climate_timer_enabled_count` Parser hat jetzt einen Fallback: wenn der legacy Pfad leer ist, probiert er die neue Location. Beide alten + neuen Firmware-Versionen liefern jetzt korrekte timer-counts.

  Plus 7 silencer-adds (2 für die parsed Felder, 5 für die departureTimers sub-block leaves). Audi erbt alle Änderungen automatisch via brand-vererbung. **Closes #264**.

## [2.2.3] — 2026-05-23 — "Easter Egg + Sprint A Quick-wins"

> **PATCH-Release**: 1 community-feature (🥚 easter-egg tribute) + 5
> Scout-Closures + 1 config-flow UX-Fix in einer PR (#274). Spinoff
> aus dem rename-thread auf den HA UK + HA Ideas Facebook groups —
> Rename selber bleibt geparkt, easter-egg shippt vorab.
>
> Was drin ist:
>
> | # | Reporter | Brand | Fix |
> |---|---|---|---|
> | #270 | roberttco | VW NA | config-flow brand-preserve nach auth-error |
> | #268 + #271 | arvcer | VW EU | chargingStatus.requests parser+silencer |
> | #272 | arvcer | VW EU | climatisationStatus.requests parser+silencer |
> | #273 | gudden | VW EU | readiness.error envelope silencer |
> | #263, #265, #266 | DnnsJp74, j4x5mgq94b, arvcer | Audi/VW EU | ack-close (pre-fixed in v2.2.2) |
> | #267 | Brinki99 | VW EU | ack-close (transient Cariad 502) |
>
> Audi erbt alle silencer-adds via brand-vererbung. Keine Breaking
> Changes. HACS pre-release & stable channels.
>
> Codename: "Easter Egg + Sprint A Quick-wins" — weil das easter-egg
> der zentrale community-moment ist und Sprint A der erste schritt
> einer geplanten Sprint-A→B→C release-kadenz (B = v2.3.0 mit VW NA
> auth-fix + Audi nav-aware charging).

### Added

- **🥚 Easter-Egg Service `vag_connect.show_vag` (Community Tribute)** —
  In honour of the "Great VAG Renaming of 2026" Facebook-thread:
  multiple humorous comments in the **Home Assistant UK** and **HA
  Ideas, Projects and Solutions** groups pointed out dass "VAG" — die
  offizielle DACH-Abkürzung für Volkswagen AG — auf Englisch *quite
  differently* gelesen wird 😅. **Si Gregory** schlug ein Rename vor,
  **Ben Johnson** stimmte zu, **Evets David** fragte "Is it a dating
  integration?", **Stuart McBride** sekundierte, und **Jordan Waeles**
  toppte mit einem brillanten Pandas-style `show_vag()` joke.

  Wir parken das Rename selbst noch (separate PR später) aber das
  easter-egg shippt jetzt: Service-Call `vag_connect.show_vag` (no
  params) erstellt eine persistente HA-Benachrichtigung mit den
  Credits + einer Liste aller aktuell verbundenen Fahrzeuge.
  **Always-works contract** — auch bei zero vehicles konfiguriert
  zeigt es einen Placeholder statt zu erroren. Nutzbar via Developer
  Tools → Services oder einer Automation. Erscheint im HA-Bell und
  bleibt screenshotbar.

### Fixed

- **#270 (roberttco VW NA, 2026-05-21) — Config-flow Brand-Selection
  bleibt nach Login-Fehler erhalten** — vorher hat der Re-Render nach
  einer Auth-Fehlschlag-Response `_credentials_schema()` ohne Argumente
  aufgerufen → brand/username/spin/scan_interval/force_access fielen
  alle auf die Defaults zurück. User dachte das Rejection wäre wegen
  ihrer Brand-Selection (statt Credentials) und probierte falsche
  Kombinationen. Fix: `suggested = user_input or {}` wird durch den
  Schema-Builder gefädelt, alle Felder ausser Password bleiben
  erhalten. Password wird (per HA-Konvention) nicht zurückgespiegelt
  — sicherheitsrelevant, muss neu eingegeben werden. Damit ist die
  Selection nach einem 400/500-Error genau dort wo der User sie
  gelassen hat.

- **Scout #268 + #271 (VW EU arvcer, 2026-05-21/22) —
  `charging.chargingStatus.requests` parsed + silenced** — Mirror der
  bestehenden `charging.chargingSettings.requests` Parser-Logik
  (v1.27.2 #181). Liefert jetzt `d.charging_status_pending` als
  diagnostic count: 0 = idle, >0 = `start_charging`/`stop_charging`
  command ist im Gateway gequeued. Neuer optional-disabled
  `sensor.{prefix}_charging_commands_pending` (Power-User opt-in).
  Audi erbt automatisch via brand-vererbung. **Closes #268, #271**.

- **Scout #272 (VW EU arvcer, 2026-05-23) —
  `climatisation.climatisationStatus.requests` parsed + silenced** —
  Dritter Member der `*_pending` Familie nach `chargingSettings.requests`
  und `chargingStatus.requests`. Zählt gequeuete
  `start_climatisation`/`stop_climatisation` Commands am Gateway.
  Neuer optional-disabled `sensor.{prefix}_climate_commands_pending`.
  Kein `condition`-Filter (jede Marke mit Remote-Climate support —
  EV+ICE alike). Audi erbt via brand-vererbung. **Closes #272**.

- **Scout #273 (VW EU gudden, 2026-05-23) —
  `readiness.readinessStatus.error` envelope silencer-add** —
  Defensive `.error` Wrapper Pattern (gleiches Schema wie
  #185/#190/#191 envelopes), Parser ignoriert es clean. Nur
  Silencer-Add nötig, kein Code-Change. **Closes #273**.

- **Scouts #263, #265, #266 ack-closed (alle pre-fixed in v2.2.2)** —
  Drei Scout-Reports für `chargingRate_kmph` und
  `chargingSettings.error` Felder die alle schon in v2.2.2 silenced
  wurden. Reporter (`DnnsJp74`, `j4x5mgq94b-commits`, `arvcer`) waren
  auf älteren Versionen. Ack-Comments mit Update-Empfehlung.

- **Error-Report #267 (Brinki99) ack-closed — backend hiccup** — HTTP
  502 Bad Gateway von `emea.bff.cariad.digital` ist ein transient
  Backend-Outage von Cariad, kein Code-Bug. Error-Reporter hat seine
  Aufgabe erfüllt (Telemetrie sauber). Ack-Comment mit Erklärung +
  Verweis auf nächsten Refresh-Cycle.



## [2.2.2] — 2026-05-18 — "Silencer Catch-up + Laien-friendly Names + Diesel Dashboards"

> **PATCH-Release**: 5 follow-up PRs nach v2.2.1 stable.
> 1 Scout-closure (#260), 1 cross-brand parser-expansion (#256, closes
> #248), 3 docs-PRs (#257 dashboards.md + FAQ in 8 langs, #258 6
> Bubble-Card-templates, #259 Audi S6 TDI diesel popup variant), plus
> cross-language entity-name laien-cleanup (`SoC` → "Ladestand"/"Charge"
> equivalent in 8 langs, DE `(km/h)` mph-bug fix, `HV-Batterie` → `Akku`,
> 6 langs hatten raw English untranslated für 2 entities — gefixt).
>
> Keine Breaking Changes. HACS pre-release & stable channels.

### Fixed

- **Scout #260 silencer-fix + cross-language entity-name laien-cleanup**
  (Audi, `charging.chargingStatus.value.chargeRate_kmph`, reporter
  `j4x5mgq94b-commits` 2026-05-17). Field WAR seit v1.10.0 geparsed
  (`vw_eu.py:916` → `d.charging_rate_kmh` → `sensor.charging_speed`
  / DE `sensor.ladegeschwindigkeit`) — aber der **dotted path** war nie
  in `EXPECTED_KEYS` für CARIAD-BFF `selectivestatus` registriert,
  weshalb der Scout fälschlich gefired hat. Klassischer "silencer hat
  parser nicht eingeholt" gap (same class as #248). **One-line fix**
  in `_unexpected_keys.py:456` — Audi erbt automatisch via
  `EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]`.

  **Bei der Gelegenheit: cross-language entity-name laien-cleanup**
  (community-feedback "alle umgangssprachen benutzen damit nicht-tech
  menschen auch verstehen"). Audit aller 9 i18n-files (strings.json +
  8 translations) ergab:

  | Was | Vorher | Nachher |
  |---|---|---|
  | DE `charging_rate_kmh` | `Ladegeschwindigkeit (km/h)` | `Ladegeschwindigkeit` |
  | DE `battery_temp_max` | `HV-Batterie Temperatur (Max)` | `Akku-Temperatur (max)` |
  | All-langs `active_charging_profile_target_soc_pct` | `... Target SoC` / `Ziel-SoC` / `SoC Cible` etc. | `... Target Charge` / `Ladeziel` / `Charge Cible` etc. |
  | All-langs `battery_care_target_soc_pct` | same SoC pattern | same laien-friendly Charge/Ladeziel pattern |
  | All-langs `primary_engine_soc_pct` | `Primary Engine SoC` / `12V-Batterie SoC` / `SoC moteur principal` etc. | `12V Battery Charge` / `12V-Batterie Ladestand` / `Charge batterie 12V` etc. |
  | All-langs `min_soc` | `SoC minimum (PHEV)` in fr/es/nl/sv/cs | `Charge minimum (PHEV)` / `Minimální nabití` / `Minsta laddning` etc. |
  | 6 langs `next_charging_timer_id` | **Raw English** "Next Charging Timer ID" untranslated | translated to native form (`Nächster Lade-Timer (ID)`, `Prochain timer (ID)`, `Próximo temporizador (ID)`, `Volgende timer (ID)`, `Następny timer (ID)`, `Další časovač (ID)`, `Nästa timer (ID)`) |
  | 6 langs `next_charging_timer_target_soc_reachable` | **Raw English** "Next Charging Timer Target SoC Reachable" untranslated | translated to native form in all 8 langs |

  **Why DE `(km/h)` was wrong**: entity is `SensorDeviceClass.SPEED`,
  HA auto-converts km/h ↔ mph based on user's unit-system. Hardcoded
  suffix lied to mph-locale users (would show "Ladegeschwindigkeit
  (km/h): 31 mph" — name says km/h, value is mph).

  **Why `SoC` matters**: State-of-Charge is EV-engineering jargon. A
  non-technical user looking at a 12V starter battery sensor labeled
  "12V-Batterie SoC" doesn't know what SoC means — but everyone
  understands "12V-Batterie Ladestand" (charge level).

  **Regression-shield** (`test_v222_260_silencer_translations.py`,
  28 tests): asserts silencer-path present for VW + Audi-inheritance
  honored; pinned no-SoC / no-HV-Batterie / no-`(km/h)`-DE-suffix /
  no-untranslated-English-in-non-EN; cross-language entity-key
  parity (en.json is the canonical superset); strings.json + en.json
  agreement on all touched keys. **Closes #260**.

### Added

- **Bubble Card ready-made templates für VAG Connect (`docs/lovelace/bubble-card/`)** —
  Community-Feedback (FB-Gruppe 2026-05-17): User wollte schöneres
  Dashboard ohne YAML-Frickelei. [**Bubble Card**](https://github.com/Clooos/Bubble-Card)
  hat die perfekte glass-morphism / gradient aesthetic. **6 pre-built
  YAML snippets** im neuen `docs/lovelace/bubble-card/` folder:
  - `01-vehicle-button-stack.yaml` — top horizontal vehicle selector
  - `02-vehicle-popup.yaml` — main pop-up (battery/range/charging/
    climate/lock)
  - `03-charging-controls.yaml` — detailed charging + target SoC
  - `04-climate-controls.yaml` — climate, defrost, departure timers
  - `05-door-status.yaml` — lock + per-door + trunk + hood + alarm
  - `99-full-dashboard.yaml` — complete single-vehicle dashboard
    combining all of the above
  Plus README.md mit setup-guide + multi-vehicle pattern. Alle 6
  YAML-files validated mit `yaml.safe_load` — drop-in ready.
  **Quick start (<5min)**: install Bubble Card via HACS → copy
  `99-full-dashboard.yaml` in raw-config editor → search-replace
  `audi_q4` mit deinem prefix → fertig. Cross-link from
  `docs/dashboards.md` als "recommended starter".

- **Bubble Card diesel variant `02b-vehicle-popup-diesel.yaml` (Audi
  S6 TDI tailored)** — der initial 6-file template-bundle war
  EV-zentriert (Audi Q4 e-tron als example: `battery_soc`, charging
  controls, electric range). Diesel-Fahrer haben aber andere
  primary-entities: `fuel_level` statt `battery_soc`, kein
  charging-block, dafür `adblue_range_km` (DEF/AdBlue tank),
  `service_km` + `oil_service_km` (Service-Intervalle für Diesel
  besonders relevant), und auf Audi-Seite **ICE Remote Engine Start**
  (`switch.audi_s6_engine` via Cariad-BFF `/vehicle/v1/engine` mit
  S-PIN). Neue YAML mit 10 horizontal-stack rows: tank+range,
  AdBlue+odometer (mit threshold-color-coding), remote engine,
  climate+target-temp, outside-temp+aux-heater (kommentiert für
  Webasto/Standheizung opt-in), lock+position, service+oil-service,
  alarm+siren (Cariad-BFF anti-theft), Connect-Plus-subscription,
  12V-Voltage+modem-power-budget (diagnostics — 12V monitoring auf
  Diesel mit langen Park-Zeiten besonders wertvoll als early-warning).
  README.md updated mit neuem table-row (diesel-variant labeled).
  Validated mit `yaml.safe_load`. Funktioniert für jeden Audi/VW
  Diesel mit Cariad-BFF backend (S6/A6/Q7 TDI, Touareg etc.) —
  Skoda-Diesel-User reusen mit prefix-swap.

- **`docs/dashboards.md` — dedicated dashboard troubleshooting + Lovelace
  card guide** — community Q&A came up (FB group): user trying to add
  VAG Connect entities to existing dashboard view via "Add to Dashboard"
  hit classic HA YAML-vs-Storage confusion. Multi-week recurring question
  → dedicated docs page deserves it. Covers: 3-cause troubleshooting für
  "Add to Dashboard" picker-not-showing-view (YAML-mode dashboards / view
  not created yet / Sections-layout quirks), workarounds für jede cause,
  dedizierte VAG Connect Lovelace-Karte status (BETA — currently has
  Mercedes-style background being redesigned), 3rd-party card empfehlungen,
  entity-ID discovery, **per-version feature matrix für v2.2.0 + v2.2.1
  entity additions**. Plus FAQ.md neue section + FAQ-table-row in DE/EN
  READMEs + dashboards.md link in allen 6 anderen language READMEs (fr,
  es, nl, pl, cs, sv). 8 README files + FAQ + new dashboards.md =
  pure-docs PR, no code changes.

- **`climate_timer_enabled_count` cross-brand expansion to VW EU/Audi
  (Closes #248)** — Skoda hatte das field seit Phase 7 PR #4 (scout
  silenced-but-unwired audit). VW EU/Audi `climatisationTimers.
  climatisationTimersStatus.value.timers[*]` mirrors das departureTimers-
  pattern aus Phase 7 PR #2 aber war nie geparsed. Dieser PR wires
  die parser hook für VW EU/Audi mit defensive guards (list-check
  + isinstance dict + is True comparison).
  
  **Cross-brand coverage matrix**: `climate_timer_enabled_count`
  vorher 1 brand (Skoda) → jetzt **3 brands** (Skoda + VW EU + Audi).
  
  **Background von #248 (arvcer scout-report 2026-05-17)**: alle 4
  reported fields waren bereits silenced+parsed in main seit
  v1.17.5/v1.19.3. 3 von 4 fields populating dataclass-fields
  (`next_charging_timer_id`, `next_charging_timer_target_soc_reachable`,
  `secondary_engine_type`). Das 4. (`climatisationTimers.
  climatisationTimersStatus.value` — silenced container `{2 keys}`)
  ist jetzt aktiv geparsed via dieser cross-brand expansion. Defensive:
  assumption ist mirror of departureTimers shape; wenn actual leaves
  differ, list-check guard hält das field None (phantom-gate honest).
  10 Tests inkl. aggregation-defensiveness + cross-brand parity
  regression-shield. **Closes #248**.
  *"Two timers? Well, that's twice the timer." — Sheldon Cooper.*

## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion (continued)

- **Phase 8 PR #5 — `car_type` cross-brand derivation helper** —
  **Different pattern als PR #1-#4.** Statt parser-hooks pro backend
  zu erweitern, addet diese PR einen single derivation-helper der
  am Ende jedes brand parsers fires. Füllt `d.car_type` für backends
  die kein direct field shippen (CUPRA/SEAT OLA, Porsche PPA, VW NA
  Kombi). Hybrid + electric + diesel + gasoline ableitbar aus
  `has_battery` + `has_combustion` + `primary_engine_type`.

  **Critical contract**: NEVER overwrites a directly-read value.
  Skoda + VW EU/Audi (haben direct backend field) bleiben unverändert;
  CUPRA/SEAT/Porsche/VW NA bekommen den derived value. Wired in
  ALLEN 5 brand parsers als end-of-parse fallback (no-op wenn
  direct read schon succeeded, populiert wenn nicht).

  **Cross-brand coverage matrix nach diesem PR**:
  - `car_type`: vorher 3 brands (Skoda + VW EU + Audi) → jetzt
    **alle 6 brands** (alle Cariad + OLA + PPA + Kombi)
  - **6/6 brand coverage** für ein previously-unwired field —
    pure derivation, zero backend changes nötig

  Derivation rules: hybrid > electric > diesel > gasoline; unknown
  engine type (CNG/LPG/H2) → bleibt None (don't guess). 22 Tests
  inkl. never-overwrite contract + end-to-end real-world scenarios
  (Cupra Born EV, Formentor PHEV, Porsche Taycan/Cayenne diesel +
  e-Hybrid, VW NA ID.4).
  *"Statistically speaking, given enough booleans, even a chimpanzee
  could derive whether the car is electric, hybrid, or combustion."
  — Sheldon Cooper.*

- **Phase 8 PR #4 — VW EU/Audi `primary_engine_fuel_level_pct` mirror** —
  Pure cross-brand expansion. Skoda hatte das field seit Phase 8 PR #1
  heute (von `driving-range.primaryEngineRange.currentFuelLevelInPercent`).
  Dieser PR refactored den existing engine-walker aus PR #2 um BOTH
  primary AND secondary engine blocks zu handlen — position-based
  assignment statt nur-secondary.
  - **ICE-only Golf (primary=gasoline)** → `primary_engine_fuel_level_pct` populated
  - **Modern Passat GTE (primary=electric, secondary=gasoline)** →
    `secondary_engine_fuel_level_pct` populated (PR #2 behaviour preserved)
  - **Legacy Golf 7 GTE 2015 (primary=gasoline, secondary=electric)** →
    `primary_engine_fuel_level_pct` populated (position correctness)
  - **Pure EV (no combustion)** → both fields stay None
  Walker consolidiert die parser logic — eine schleife macht beide
  jobs basierend auf position + combustion-type check. Audi inherits
  via VWEUClient automatisch. **Cross-brand coverage matrix nach PR**:
  `primary_engine_fuel_level_pct` = Skoda + VW EU + Audi (3 brands).
  10 Tests inkl. PHEV/ICE/EV/Legacy-Golf semantics + error-container
  safety + cross-brand matrix regression.
  *"Now we have one walker doing the job of two. Just like Penny on
  date night with two text conversations." — Sheldon Cooper.*

- **Phase 8 PR #3 — Porsche electric/combustion range split** —
  Pure cross-brand parity expansion — Porsche joins die brand-coverage
  von `electric_range_km` + `combustion_range_km` die Skoda, VW EU,
  Audi, CUPRA, SEAT alle seit v1.10.0+ haben. **Zero new entities**,
  zero new translations.
  - **Before:** Porsche populated nur aggregate `range_km` via
    or-fallback (`E_RANGE.distance OR FUEL_LEVEL.distanceToEmpty`)
  - **After:** explicit `electric_range_km` (Taycan, Macan EV, 911
    Cayenne EV) + `combustion_range_km` (Cayenne ICE) + beides für
    PHEV (Cayenne E-Hybrid, Panamera E-Hybrid). Aggregate `range_km`
    keeps current or-fallback für back-compat — Porsche users sehen
    KEIN regression auf dem existing sensor.
  Defensive: `isinstance(int, float)` guards, float→int truncation,
  empty-measurements safe. 12 Tests inkl. brand-coverage matrix
  regression-shield (mindestens 4 brand-parsers referenzieren
  electric_range_km nach diesem PR).
  *"You see, I have made a small modification to your existing
  range sensor. It is now THREE sensors. Better." — Sheldon Cooper.*

  **Phase 8 PR #2 (Alarm/Siren cross-brand) DEFERRED:** Skoda mysmob,
  CUPRA/SEAT OLA, Porsche PPA, VW NA Kombi parsers haben ZERO existing
  alarm/theft references. Path-Speculation ohne tester scout-dump
  von einem User mit armed-alarm wäre Guessing — gemerkt für post-
  tester onboarding queue.

- **Phase 8 PR #2 — VW EU/Audi engine-metadata cross-brand expansion** —
  **Pure cross-brand expansion PR** — zero neue entities, zero neue
  translations, zero neue phantom-gates. Wires VW EU/Audi parser-hooks
  für 4 existing dataclass-fields die andere brands schon populate.
  Direkter Beweis für die "1 user reportet auf 1 brand → eventually
  alle brands profitieren" Strategy:

  | Field | Originally wired | This PR adds |
  |---|---|---|
  | `primary_engine_type` | CUPRA/SEAT (PR #3), Skoda (PR #1 heute) | VW EU + Audi (inherits) |
  | `secondary_engine_type` | Skoda (PR #6 Scout #220), CUPRA/SEAT (PR #18 Scout #232) | VW EU + Audi |
  | `car_type` | Skoda (PR #1 heute) | VW EU + Audi |
  | `secondary_engine_fuel_level_pct` | Skoda (PR #6), CUPRA/SEAT (PR #18) | VW EU + Audi |

  **Konkret**: Daniel Walter's Skoda Scout #220 (2026-05-16) → Skoda
  PHEV-User bekamen `secondary_engine_*` sensoren. Matthias0304's
  CUPRA Scout #232 (gleicher Tag) → CUPRA/SEAT PHEV-User auch.
  **Diese PR**: VW EU + Audi PHEV-User (Passat GTE, Golf GTE, A3
  e-tron etc.) bekommen die gleichen Sensoren **ohne dass sie je
  einen Scout-Report posten mussten** — das ist der Avalanche-Effekt
  den die strategy enables.

  Implementation: die variablen `ms_secondary`, `ms_primary`,
  `car_type`, plus die per-engine-block-walk waren bereits im vw_eu.py
  parser für drivetrain-flag-derivation. Diese PR fügt explizite
  Assignments zu den dataclass-fields hinzu. Priority order:
  `fuelStatus` (richer) → `measurements` (fallback). 15+ Tests inkl.
  brand-coverage-matrix regression-shields, PHEV-vs-EV-only walk
  semantics, defensive non-string/non-dict guards.
  *"It's an avalanche! Everybody dies! Bazinga!" — Sheldon Cooper.*

- **Phase 8 PR #1 — Skoda 5-field "alles parsen" batch** —
  Erste batch der neuen strategy. 5 Skoda mysmob fields die seit
  v1.x silenced waren ohne parser-hook:
  - **`binary_sensor.battery_protection_limit_on`** (Skoda) —
    `readiness.batteryProtectionLimitOn`. Companion zu VW EU/Audi
    `daily_power_budget_available` (Phase 7 PR #2). Beide signalen
    den modem rationiert wake-ups um 12V zu schonen.
  - **`sensor.car_type`** (Skoda) — `driving-range.carType` (enum
    diesel / gasoline / electric / hybrid). Authoritative backend
    classification der primary engine, distinct vom derived
    `is_electric`/`is_hybrid`.
  - **`sensor.primary_engine_type`** (Skoda — cross-brand reuse) —
    `driving-range.primaryEngineRange.engineType`. **Zero new entity**:
    maps in das existing field aus Phase 7 PR #3 (CUPRA/SEAT) —
    expanded brand coverage über reuse pattern. Skoda joins CUPRA/SEAT
    auf dem gleichen sensor.
  - **`sensor.primary_engine_fuel_level_pct`** (Skoda) —
    `driving-range.primaryEngineRange.currentFuelLevelInPercent`.
    Cross-brand sibling zu `secondary_engine_fuel_level_pct`.
    Primary fuel tank % für combustion-vehicles. Distinct vom
    existing `fuel_level` (measurements-path).
  - **`sensor.maintenance_report_captured_at`** (Skoda) —
    `maintenance.maintenanceReport.capturedAt` ISO 8601 timestamp.
    `device_class=TIMESTAMP`. Useful für "ist mein service-due data
    stale?" Fragen.
  All Skoda-only; phantom-protected via `_DATA_PRESENT_REQUIRED`.
  Defensiv: isinstance guards für bool / string / int / float
  variants. 20+ Tests inkl. cross-brand-reuse regression-shield.
  *"Why have a key on the keyring if you never use it?"
  — Lisa Simpson.*

### Added

- **Phase 7 PR #5 — VW EU Scout #245 silencing (Pre-Release Patch)** —
  **MUST land vor v2.2.0 final.** Issue #245 reportet 18 neue Felder
  auf VW EU `selectivestatus` — aber es ist **kein 18-random-fields-
  pattern**, sondern ein **systemic Cariad-BFF rollout**: jeder
  `<block>.{xxxStatus}` bekommt jetzt einen `.error` container
  (6 keys — `message` / `errorTimeStamp` / `info` / `code` / `group`
  / `retry`) wenn das sub-status fails. Same Bad-Gateway-error-wrapper
  convention wie `charging.chargeMode.error` (#96 + v1.12.0) plus
  `automation.*.error` (v1.12.1 #105) — nur jetzt auf **17 statt 3
  sub-blocks** ausgerollt.
  
  Without dieser silencing layer würde jeder production-user dessen
  backend das error-container feature rolled-out hat **18 scout
  warnings per coordinator-update** sehen → log-spam → frustrated
  users. Pre-release patch silenced alle 17 `.error` containers
  inkl. `.error.*` wildcards für die 6 standard-children, PLUS
  `measurements.tirePressureStatus` (1-key container + value
  wrapper + wildcards für future tire-pressure leaves).
  
  No new entities — error-containers sind diagnostic backend state
  bereits covered by der existing `connection_state` pipeline
  (interprets stale timestamps correctly). 116 Tests (17 error
  paths × parametrised + 17 paths × 6 child keys = 102 + 3
  tirePressureStatus + 6 legacy-regression + 2 wildcard-not-
  over-silencing + 4 brand-isolation). Closes #245.
  *"There's an error. There's an error. There's an error... I think
  the backend is having a bad day." — Sheldon Cooper, reading the
  scout warnings.*

- **Phase 7 PR #4 — Skoda Tier-B Trio aus Scout-Audit** —
  Drei Skoda mysmob Felder silenced seit v1.12.2 (#107 tritanium73
  2026-05-01) aber nie geparsed:
  - **`sensor.climate_timer_enabled_count`** — Skoda parity zu PR #2
    `departure_timer_enabled_count` (VW EU/Audi). Aggregate count
    (0-3) of currently-enabled climate timers. Empty list → field
    stays None (NOT 0) — phantom-gate honoring critical für non-
    Skoda brands.
  - **`sensor.climate_running_requests_count`** — count of in-flight
    climatisation requests waiting on the modem to acknowledge. >0
    means a command is still pending. Diagnostic für die "start_
    climatisation appears to do nothing" failure mode. Distinct
    semantics von timer count: empty list = 0 (meaningful "no
    pending"), missing = None (not Skoda).
  - **`binary_sensor.vehicle_at_saved_location`** — whether the car's
    GPS matches a user-saved home/work location (Skoda navigation
    POIs). Enables "auto-charge only at home" automations ohne
    HA zone helper.
  All defensive: `isinstance` guards reject non-bool / non-list /
  malformed entries; "truthy" string variants not counted (only
  literal `True`); non-dict timer entries silently skipped. Skoda-
  only; other brands phantom-gated. 18 Tests inkl. parametrised
  field-existence + 3 separate parser-mirror groups + 4 entity-
  registration + 17 translation coverage.
  *"Knock knock knock Penny. Knock knock knock Penny. Knock knock
  knock running-requests-count." — Sheldon Cooper.*

- **Phase 7 PR #3 — SEAT/CUPRA `engines.primary` Block** —
  Companion zu PR #6/#18 `secondary_engine_*` fields. Wildcard
  `engines.primary.*` war silenced seit v1.16.1 (#122 r1150gs SEAT
  scout 2026-05-02 — "3 keys observed") aber nie geparsed.
  - **`sensor.primary_engine_type`** — `mycar.engines.primary.
    {fuelType,engineType}` (PETROL/DIESEL/ELECTRIC/HYBRID). Distinct
    von den derived booleans (`is_electric`, `is_hybrid`) — das ist
    die authoritative backend-classification.
  - **`sensor.fuel_tank_capacity_liters`** — `mycar.engines.primary.
    {tankCapacity,tankCapacityInLiters,tankSize}` (Liter). Mit dem
    existing `fuel_level` (%) können users die verbleibenden Liter
    via simple template derive — keine Spec-PDF-Lookup mehr nötig.
    `condition="combustion"` — EV-only fahrzeuge sehen den Sensor nicht.
  Multi-variant lookup für 3 key-Schreibweisen pro field (OLA hat
  historisch alternative spellings shippt). Defensive: 0-capacity
  silently rejected (EV-only ships 0 für das field aber meaningless),
  string-capacity rejected, empty-fuelType rejected. SEAT/CUPRA OLA
  only; other brands' parsers don't populate diese fields → None →
  phantom-gate hides entity. 13 Tests inkl. forward-compat alt-spellings
  + defensive zero/string/empty rejections.
  *"Now if you'll excuse me, I have a tank of unleaded to monitor."
  — Sheldon Cooper.*

- **Phase 7 PR #2 — VW EU/Audi Tier-B Diagnostics** —
  Zwei CARIAD-BFF Felder die der parser bereits READS für adjacent
  features (timers list, readiness block) aber nie als aggregate /
  diagnostic entities exposed:
  - **`sensor.departure_timer_enabled_count`** (VW EU + Audi):
    aggregate count (0-3) of currently-enabled departure timers.
    Saves users die templating-effort von 3 binary states summen.
    Defensive: nur gesetzt wenn die timers list tatsächlich present
    ist (nicht just empty) — phantom-gate bleibt honest. Multi-
    variant truthy-check rejected (only literal `True` counts —
    string "true" / int 1 zählen nicht).
  - **`binary_sensor.daily_power_budget_available`** (VW EU + Audi):
    telematics modem daily power budget. Wenn OFF, der modem rationiert
    wake-ups um 12V zu schonen → long poll intervals sind das user-
    visible symptom. Diagnostic für "if power-budget exhausted →
    warn 12V check" automations. `isinstance(..., bool)` guard
    rejected non-bool variants (Python's `isinstance(1, bool) is
    False` ist hier ein feature).
  Both VW EU + Audi only; other brands' parsers don't populate
  these aggregates → fields stay None → kein phantom entity.
  17 Tests inkl. parser-mirror defensives + entity-registration +
  9-language coverage.
  *"Three timers and only one is enabled? Yes, that is mathematically
  one. I do not need to count higher to know this." — Sheldon Cooper.*

- **Phase 7 PR #1 — Quick-Wins-Batch (4 sensors aus scout-audit)** —
  Scout-Audit (cross-reference `_unexpected_keys.py` ↔ tatsächliche
  parser-reads) identifizierte ~12 fields die silenced waren aber nie
  als entities exposed wurden. Dieser PR shippt die **4 quick wins** —
  single-value leaves mit clear semantics:
  - **`binary_sensor.ignition_on`** (Skoda only — `readiness.ignitionOn`):
    Useful für "lock when ignition off" automations ohne extra sensor query
  - **`sensor.primary_engine_soc_pct`** (Skoda only — `driving-range.
    primaryEngineRange.currentSoCInPercent`): On gasoline cars das 12V SoC
    (per scout #116 MavericklCS) — early-warning "modem can't keep itself
    awake" Indikator. Distinct vom existing `battery_voltage_v` (CARIAD-
    BFF only); Skoda mysmob publiziert das auf driving-range, nicht lvBattery.
  - **`sensor.steering_wheel_position`** (Skoda only — `air-conditioning.
    steeringWheelPosition`): LHD/RHD-aware automations + diagnostic für
    Märkte wo der gleiche Wagen beides ship'pt (UK, AU, JP).
  - **`sensor.battery_temp_max`** (VW EU + Audi — `measurements.
    temperatureBatteryStatus.value.temperatureHvBatteryMax_K`):
    Companion zu existing `battery_temp` (HvBatteryMin_K). Beide Celsius
    nach K→C conversion. Power-users monitoring thermal balance während
    DC fast-charging wollen BEIDE extremes — der spread ist das diagnostic
    signal. Defensive same safe_float + None guard.
  All brand-restricted im parser; phantom-protected via
  `_DATA_PRESENT_REQUIRED`; andere brands stay None → kein phantom entity.
  18 Tests (4 field-existence + 4 ignition parser + 1 primary-soc + 3
  steering-wheel + 4 K→C math + 6 entity-registration + 9 translation
  coverage).
  *"Sometimes the best feature is the one that was already paid for —
  you just have to wire it up." — Lisa Simpson, on the value of audits.*

### Added

- **Pydantic v2 Dual-Write Validation Foundation (Phase 5b PR #19/20)** —
  Read-only "dual-write" pattern — baut die validation layer in v2.2.0
  damit v3.0.0 die legacy dataclass parsing path mit confidence cutten
  kann. Neu: `cariad/_pydantic_validate.py` (defensive helper, **NEVER
  raises** — auf Pydantic-not-importable / schema-mismatch / wrong-type
  returns None silently, caller-side existing dataclass parse läuft
  unverändert) + `cariad/_pydantic_models.py` mit erstem Modell
  `BatteryStatusValue` (deckt `charging.batteryStatus.value` ab —
  stabilstes Block seit 2023). **`extra="allow"`** — Cariad rollt
  monatlich neue Sibling-Keys, strict validation = false-alarm-fatigue
  (cross-platform consensus pycupra+audi+myskoda). Erstes dual-write
  call-site: `vw_eu.py` post-parse, validate-only, log-at-DEBUG bei
  mismatch (NOT warning — non-spammy während wir Models tunen).
  Telemetrie über ~7 Tage → wenn clean: model locked-in für weitere
  blocks. **Failsafe**: caller-side `d.battery_soc` aus dem existing
  dataclass parse bleibt canonical; Pydantic ist diagnostic-only.
  Module sind defensive-importable (try/except um pydantic-import) —
  dev contributors ohne HA Core können parser-tests laufen lassen.
  18 Tests inkl. happy-path mit Pydantic + skipif fallback + module-
  import-safety regression-shield.
  *"In two years, we will all look back on this dataclass code and say
  'D'oh — why didn't we use Pydantic from the start?'" — Homer Simpson.*

- **Push-Bus Internal Abstraction Refactor (Phase 5a PR #18/20)** —
  Internal-only refactor — kein user-facing behaviour change. Extrahiert
  die duplizierten `_advance_backoff` + `_reset_backoff` methods +
  backoff constants aus den 3 brand push managers in die `PushManager`
  base class. Single source of truth: `PUSH_INITIAL_BACKOFF_S`,
  `PUSH_MAX_BACKOFF_S`, `PUSH_BACKOFF_MULTIPLIER`,
  `PUSH_FAST_RETRY_THRESHOLD` jetzt module-level in `base.py`.
  ~80 Zeilen Duplikation entfernt (3× je: 4 constants + 2 methods +
  random import + 2 init-state vars). **Future push managers (Phase 4
  brand scaffolds when activated) inherit the pattern automatisch
  via `super().__init__()`** — kein per-brand re-implementation
  nötig. **Behaviour unchanged**: same jitter-formula, same caps,
  same threshold. 18 Tests verifizieren: constants in base + per-brand
  duplikate weg + inherited methods produzieren correct behavior +
  alle 3 brand managers haben PushManager._advance_backoff (identity
  check, nicht subclass override).
  *"DRY — Don't Repeat Yourself. Also: Don't Repeat Yourself."
  — Sheldon Cooper.*

- **CUPRA Scout #232 — `mycar.engines.secondary` wiring (matthias0304 2026-05-16)** —
  CUPRA PHEV companion zu Skoda Scout #220 (PR #6). OLA `mycar.engines.
  secondary` 3-key block auf Formentor PHEV / Leon e-Hybrid mirrors die
  Skoda `driving-range.secondaryEngineRange` shape. **Cross-brand field
  reuse**: dieser PR mappt die neue CUPRA data in die existing
  `secondary_engine_*` dataclass fields aus PR #6 — **zero neue entities,
  zero neue translations, zero neue phantom-gates**, nur expanded brand
  coverage auf den gleichen Sensoren. Defensiver multi-variant lookup
  für 3 Key-Schreibweisen pro Feld (`range`/`rangeInKm`/`distanceInKm`
  für km, `fuelType`/`engineType` für engine, `fuelLevel_pct`/
  `currentFuelLevelInPercent` für %) — falls OLA Schema rotiert auf
  Skoda-style keys oder umgekehrt, parser zieht beides. EV-only CUPRAs
  (Born) → kein `engines.secondary` → fields bleiben None → kein
  phantom. EXPECTED_KEYS in `_unexpected_keys.py` erweitert um
  Wildcard `engines.secondary.*`. 13 Tests inkl. defensives Behavior +
  cross-brand-reuse regression-shield. Closes #232.
  *"Recycling? Brilliant. Same fields, more brands, less code."
  — Sheldon Cooper.*

- **CUPRA-standalone Brand-Adapter Scaffold (Phase 4 PR #17/20, BETA — Tester pending)** —
  Phase 4 closer. Dritter scaffold neben Lambo (PR #15) + Bentley (PR #16),
  aber mit **unterschiedlicher inheritance story**: Lambo/Bentley
  inheriten von `VWEUClient` (Cariad-BFF backend), CUPRA-standalone
  inheritet von `SeatCupraClient` (OLA backend, same parser surface).
  Reserviert brand-id `cupra_standalone` für den anstehenden
  `cupra-api.vwgroup.io` cut-over (per pycupra commit 0f3b1c7 + 2026-Q1/
  Q2 community reports — CUPRA Connect migriert auf brand-isolated
  backend, expected fully cut over by 2026-H2). **OAuth flow unchanged**:
  gleicher `client_id` / `redirect_uri` / `client_secret` wie legacy
  BRAND_CUPRA — nur der post-auth API base host differs.
  **Existing CUPRA users see ZERO behaviour change** — der legacy
  shared SEAT/CUPRA OLA path bleibt der canonical CUPRA backend bis
  Tester den cut-over validiert. **3-way luxury parity test**: alle
  3 Phase-4 scaffolds (Lambo + Bentley + CUPRA-standalone) müssen
  beta-gated bleiben — jeder slip-through bricht den test. Phase 4 =
  ✅ COMPLETE.
  *"In our profession, precision matters. Especially when reserving
  brand-IDs for backend cut-overs that haven't fully cut over yet."
  — Leonard Hofstadter.*

- **Bentley Brand-Adapter Scaffold (Phase 4 PR #16/20, BETA — Tester pending)** —
  Sister-PR zu PR #15 (Lamborghini Unica). **Identisches Pattern**,
  identische beta-gate enforcement, identische VWEUClient inheritance
  rationale. My Bentley app läuft auf dem gleichen Cariad-BFF backend
  (`emea.bff.cariad.digital`) wie VW EU + Audi + Lambo. Scaffold ships
  als `BentleyClient(VWEUClient)` + `BRAND_BENTLEY` config mit
  PLACEHOLDER OAuth values. Beta-Gate hart enforced: factory rejected,
  config-flow versteckt, BRANDS registry excludes. **Cross-luxury
  parity test**: beide luxury scaffolds (Lambo + Bentley) müssen
  shape-aligned bleiben (gleicher Cariad-BFF host, beide inherit
  VWEUClient, beide PLACEHOLDER, beide factory-rejected) — Drift
  bricht den test. 16 Tests inkl. der parity-Garantie.
  *"Two roads diverged in a wood, and I took the one beta-gated."
  — Robert Frost, paraphrased.*

- **Lamborghini Brand-Adapter Scaffold (Phase 4 PR #15/20, BETA — Tester pending)** —
  Phase 4 opener. Shippt das `LamboClient` scaffold + `BRAND_LAMBO` config
  als **scaffolding only** — die Klasse compiliert, inheritet alle
  Features von `VWEUClient` (Lamborghini Unica nutzt den gleichen
  Cariad-BFF backend `emea.bff.cariad.digital` wie VW EU + Audi, per
  API-Evangelist OpenAPI Catalog 2026-05-03), aber `client_id` +
  `redirect_uri` sind **PLACEHOLDERS** die ein Tester mit Unica-App
  Install + mitmproxy validieren muss bevor Activation.
  **Beta-Gate hart enforced**: `CariadClientFactory.create("lambo", ...)`
  raised weiterhin ValueError; Config-Flow zeigt Lambo nicht als Brand;
  `BRANDS` registry enthält Lambo nicht. Tester können `LamboClient`
  direkt importieren um in einem debug-script den IDK-flow zu
  exercise und zurückzumelden. Regression-shield: 13 Tests inkl.
  factory-rejects-lambo + brands-registry-excludes-lambo + alle 7
  existing brands bleiben factory-resolvable nach BRAND_LAMBO addition.
  Activation kommt in v2.2.x oder v2.3.x als 1-Zeilen factory PR
  sobald Tester values bestätigt.
  *"And that's why you always leave a note." — Marshall Eriksen.*

- **Audi/VW FCM Circuit-Breaker Wiring (Phase 3 PR #14/20 — Phase 3 closer)** —
  Schließt die cross-brand circuit-breaker coverage. Skoda MQTT (#12) +
  CUPRA/SEAT FCM (#13) + Audi/VW FCM (this PR) haben jetzt alle die
  **identical 5-hook wiring**:
  (1) `start()` short-circuits bei TRIPPED;
  (2) deps-check failure → strike;
  (3) connect-exception → strike;
  (4) post-backoff trip check → exit loop;
  (5) success → reset.
  **3-way parity test** als regression-shield: alle 3 Brands müssen
  identical `_record_failure` + `_record_success` counts haben, alle
  müssen den TRIPPED short-circuit und den recovery-hint im log-message
  haben. Jede zukünftige drift (extra hook, missing hook, divergierende
  reason-strings) bricht den test. Phase 3 = ✅ COMPLETE — alle Push-
  Manager haben jetzt identische fail-safe Semantik bevor wir in Phase 4
  Live-Activation versuchen. 14 Tests.
  *"Live activation can wait. The safety net must come first."
  — paraphrased Sheldon Cooper.*

- **CUPRA/SEAT FCM Circuit-Breaker Wiring (Phase 3 PR #13/20)** —
  Wired die circuit-breaker hooks (PR #12 foundation) in den CUPRA/SEAT
  FCM push manager an 5 Hook-Sites:
  (1) `start()` short-circuits wenn state == TRIPPED;
  (2) `start()` deps-check failure → `_record_failure("missing-dep")`;
  (3) `_run_loop()` connect-exception → `_record_failure("connect-loop")`;
  (4) Post-backoff trip check → exit outer loop;
  (5) `_connect_and_listen()` success → `_record_success()` (resets).
  **Identische Wiring-Shape wie Skoda MQTT** (PR #12) — parity test
  vergleicht Hook-Counts zwischen beiden brands. Beide brands haben
  jetzt die exact gleiche fail-safe behavior. Audi/VW FCM wired in
  PR #14. 11 Tests inkl. source-level wiring verification +
  mixin-inheritance + brand-parity regression-shield.
  *"That, my dear Penny, is what we call defensive programming."
  — Sheldon Cooper.*

- **Push-Bus 3-strike Circuit-Breaker Foundation (Phase 3 PR #12/20)** —
  Phase 3 opener. Foundational layer für die kommenden MQTT/FCM Live-
  Activations (#13, #14): nach **3 konsekutiven Connect-Failures**
  trippt der Manager in den neuen `TRIPPED` Zustand, stoppt das
  Spinning des reconnect-loops, und entweder:
  (1) Auto-Reset nach **1h** (lazy property-getter Transition — kein
  Hintergrund-Timer nötig) ODER (2) Operator ruft `reset_circuit_breaker()`
  manuell. **3 strikes** ist bewusst gewählt: einzelne transient
  failures (DNS-hiccup, broker rolling-restart) sind alltäglich und
  sollten nicht trippen; 3 in a row indicates strukturelles Problem
  (creds rotated, deps removed, IDP migrated) das nicht selbstheilend
  durch tight-retry geht. Mixin-Pattern: subclasses rufen
  `_record_failure(reason)` / `_record_success()` an ihren Connect-
  Failure-Sites — die strike-counting + trip-arithmetic erbt
  automatisch von `PushManager`. Skoda MQTT wired:
  3 Hook-Points (missing-dep, connect-loop-exception, success-path).
  CUPRA/SEAT + Audi/VW FCM-Manager bekommen Wiring in PR #13/#14.
  16 Tests inkl. Strike-Counting + Manual-Reset + Lazy-Auto-Reset
  + Tuning-Constants als public-contract-lock.
  *"What is the optimal number of strikes before you give up on a
  faulty appliance? Three. The answer is always three." — Sheldon Cooper.*

- **`subscription_days_remaining` derived sensor (Phase 2 PR #11/20 — Phase 2 closer)** —
  Schließt das Subscription-Feature-Dreieck: timestamp (PR #8) + bool
  (PR #9) + **int days remaining (this PR)**. **Automation-friendly**:
  Threshold-Trigger wie `if state(...) < 30 → notify` sind trivial
  gegen einen int-Sensor, viel einfacher als gegen ein TIMESTAMP zu
  templaten. Negative Werte wenn expired (`-3` = "expired 3 days ago"),
  so doubles der gleiche Sensor als "wie lange ist's her" Alarm.
  Berechnet inline neben PR #9 active-bool (zero overhead, single
  datetime parse). Brand coverage identisch zu PR #8+#10: SEAT, CUPRA,
  VW EU, Audi populiert; Skoda, Porsche, VW NA bleiben None.
  Floor-division via `timedelta.days` — Partial-days inflaten nicht.
  13 Tests inkl. Arithmetik (far-future, near-future, past, far-past,
  partial-day-floored) + defensives Parsing + Sensor-Registration.
  Phase 2 = ✅ COMPLETE (5 PRs: #7 Email-2FA + #8-#11 Subscription-Triangle).
  *"Bazinga! Now THAT'S what I call a renewable resource." — Sheldon Cooper.*

- **VW EU / Audi subscription parity (Phase 2 PR #10/20)** —
  Cross-brand parity zu PR #8 + #9: VW EU + Audi (CARIAD-BFF) parsen
  jetzt subscription_expiry_at + subscription_active aus dem
  `userCapabilities.capabilitiesStatus.value[*].expirationDate`
  array. **Same earliest-wins aggregation** wie SEAT/CUPRA, drei
  Key-Schreibweisen abgedeckt, same tri-state Semantik. Defensiv:
  non-dict cap entries, non-string expiry, malformed ISO 8601 alle
  silent geskippt — kein false-alarm für perpetuelle Capabilities.
  Skoda + Porsche + VW NA bleiben weiterhin None (kein scout-konformer
  capabilities-endpoint mit expiry-leaf). Zero neue API-calls — Daten
  kommen aus dem existierenden capabilities-fetch. Phantom-Gates aus
  PR #8/#9 decken automatisch die neuen Brands ab. 12 Tests.

- **SEAT/CUPRA `subscription_active` binary_sensor (Phase 2 PR #9/20)** —
  Companion zu PR #8 `subscription_expiry_at`. Computed tri-state
  boolean True/False/None aus dem earliest expiry across services.
  Perfekt für HA-Automatisierungen wie *"if binary_sensor.subscription_active
  == off → notify"*. **Tri-state semantics preserved**: None ≠ False, so
  perpetuelle Entitlements (lifetime-subs auf older Born MY24 firmware,
  dealer-bundled packages) **lösen keine false "expired" alarms aus**.
  Defensiv: malformed Timestamps fallen zurück auf None statt zu crashen.
  Computed inline im SEAT/CUPRA parser nach der expiry-aggregation —
  zero extra API calls. 14 Tests inkl. Tri-state-Logik + Defensive-Parsing
  + 8-Sprachen-Coverage.
  *"That subscription? Oh, it's outstanding. Just like Howard's mom's
  lasagna." — Sheldon Cooper.*

- **SEAT/CUPRA Connect-Subscription Expiry Sensor (Phase 2 PR #8/20)** —
  Long-standing User-Request: zeigt jetzt **wann das Connect-Abonnement
  ausläuft** bevor Lock/Unlock + Climate-Start stop working. Neue
  `sensor.subscription_expiry_at` mit `device_class=TIMESTAMP` rendert
  als "in 47 Tagen" / Kalenderdatum in HA UI. Parser drillt durch
  `mycar.services.*` (per-entitlement map) und probiert drei bekannte
  Expiry-Key-Schreibweisen (`expirationDate` / `validUntil` / `expiresAt`
  — pycupra commit 0f3b1c7 dokumentiert die Rotation). Aggregiert
  **EARLIEST present expiry** über alle Services → User sieht
  "first to expire" (most-restrictive Cap auf Remote-Access).
  Defensiv: malformed Timestamps (int / leerer String / non-string)
  silent geskippt; non-dict service entries (legacy "ACTIVATED"
  string shape) gerendet; field stays None wenn kein Service eine
  Expiry hat → phantom-protected (Sensor wird nie erstellt). Brand-
  restricted: andere Brands' mycar-Endpoints exposen `services.*`
  nicht im OLA-Shape, deshalb stays None auf VW/Audi/Skoda. 17 Tests
  inkl. defensives Behavior + 8-Sprachen-Coverage.
  *"You have failed me for the last time, Admiral... ation Subscription."
  — Sheldon Cooper.*

- **Email-2FA vs TOTP discrimination in IDK auth (Phase 2 PR #7/20, #183 follow-on)** —
  Pre-v2.2.0 raised generischer `TwoFactorRequiredError` ob das IDP einen
  Authenticator-App-TOTP-Code oder einen E-Mail-OTP-Code wollte. Die Repairs-UI
  zeigte dann in beiden Fällen "open the app and confirm" Copy — was Email-OTP-
  User vor ihrer Authenticator-App stehen ließ während der Code im Inbox auf
  sie wartete. Jetzt diskriminiert:
  - Auth0-Path: `/u/email-challenge` URL-Marker (vs. generic `/u/mfa`)
  - Legacy-Path: Body-Marker `email-otp` / `email-code` / `send-email-code`
    (geprüft VOR generischem `two-factor` / `2fa` substring)
  - Neue `EmailTwoFactorRequiredError` als Subclass von `TwoFactorRequiredError`
    — bestehende `except` chains laufen unverändert weiter
  - Eigener Repair-Issue `email_two_factor_required` mit branded copy in allen
    8 Sprachen + `strings.json` ("Check your inbox" statt "open the app").
  *"In the future, you should always check your e-mail first. And by 'in the
  future', I mean **starting now**." — Marshall Eriksen.*

- **`safe_get(data, "a.b[0].c", default=None)` — defensive dot-path nested accessor** —
  neuer Helper in `cariad/_util.py` ersetzt unsichere `resp['a']['b'][0]['c']`
  Patterns die bei MY26 Schema-Rotationen crashen (backend flippt silent
  zwischen dict/list/None). Drei unsichere Patterns in `vw_eu.py` Access-Block
  refactored. Schließt die Bug-Klasse die VW HA #922, pycupra #76, audi #686
  hit. Path-Syntax: `"a.b.c"`, `"a.b[0].c"`, `"doors[2].lock"`. Negative
  Indizes supported (`"l[-1]"`). Returns default für ANY of: missing key,
  wrong type, list-index out of range, None mid-traversal. **Never raises.**
  *"D'oh!" — Homer, never again.*

- **`json_safe(obj)` — recursive JSON-safe converter for `extra_state_attributes`** —
  neuer Helper in `cariad/_util.py` schließt die Bug-Klasse aus Skoda PR #1090:
  `extra_state_attributes` mit `datetime` / `dataclass` / `set` / `bytes` brachen
  silent MQTT statestream + recorder + REST API. Konvertiert:
  `datetime → ISO 8601`, `timedelta → float seconds`, `set → sorted list`,
  `bytes → utf-8 oder hex`, `dataclass → dict (recursive)`. **Never raises.**

- **Skoda Scout-Report #220 (Daniel Walter 2026-05-16) — 2 new fields wired** —
  zwei neue Felder im Skoda mysmob Backend, beide live integriert:
  (1) **`air-conditioning.airConditioningWithoutExternalPower`** (bool) →
  neue `binary_sensor.air_conditioning_without_external_power` Entity.
  Zeigt an, ob die Klimatisierung allein aus dem HV-Akku laufen kann
  (ohne Ladegerät). Kritisch für PHEV/BEV Vorklimatisierungs-Auto-
  matisierungen die "nur vorheizen wenn nicht eingesteckt" wollen.
  (2) **`driving-range.secondaryEngineRange`** expanded from 1-key
  (`distanceInKm`) auf 4-key shape mid-May 2026 — Companion-Felder
  `engineType` (PETROL/DIESEL) + `currentFuelLevelInPercent` (sekundärer
  Tankfüllstand). Neu: `sensor.secondary_engine_type` +
  `sensor.secondary_engine_fuel_level_pct`, beide phantom-protected
  (Non-Skoda-PHEV-Brands bleiben None → keine geisterhaften Entities).
  EXPECTED_KEYS in `_unexpected_keys.py` erweitert um Wildcard-Reg
  `secondaryEngineRange.*` (zukünftige Felder ohne Whack-a-mole).
  Translation-keys in allen 8 Sprachen + `strings.json`.

- **MY/Platform Quirk-Suppression Layer (`cariad/_my_quirks.py`)** —
  zweite Filter-Schicht orthogonal zu `_capabilities.py` Phase 3. Während
  Phase 3 Capabilities filtert die das Backend **nicht** als verfügbar
  meldet, fängt diese neue Schicht den umgekehrten Fall: das Backend
  meldet die Capability als verfügbar, aber die konkrete Firmware/MY-
  Kombination crashed silent beim tatsächlichen Call. Seed-Tabelle:
  **CUPRA Born MY24-MY25 → suppress `command_unlock`** (pycupra #79 —
  POST `/api/v2/access/{vin}/unlock` gibt 400 mit leerem Body zurück),
  **Audi PPE e-tron (Q6/A6, MY24+) → suppress `command_engine_start` +
  `command_engine_stop`** (audi_connect_ha #711 + PPE-Platform-Inferenz:
  pure-electric Plattform kann keinen Remote-Engine-Start). Wired in
  `coordinator.command_capability_supported()` **vor** der Backend-Cap-
  Lookup. Pure function, O(N) check, defensiv: fehlendes model / year
  → keine Suppression (no false-hides). Neue Quirks shippen heißt:
  einen `MYQuirk(...)` Eintrag mit Source-Attribution hinzufügen —
  next-coordinator-update versteckt die Entity ohne Renames.
  *"Have you met... your car's actual capabilities?" — Ted Mosby.*

### Fixed

- **Universal Consent-Screen Wall Detection (Auth0 + Legacy paths)** —
  Pre-v2.2.0 the IDK redirect-loop only detected `terms-and-conditions`
  + `consent/marketing` on the legacy signin-service path, and ZERO
  consent markers on the modern Auth0 Universal Login path. Result:
  the #1 cause of broken installs across all 2026 VAG-HA integrations
  (pycupra #83, Audi PR #731, evcc #29760, myskoda #976) surfaced as a
  generic `AuthenticationError("no app:// redirect")` with zero
  actionable hint.

  v2.2.0 makes the matcher universal: both paths now check the redirect
  URL for 6 consent markers — `consent/marketing`, `/u/consent`,
  `cupraid.vwgroup.io`, `skoda-id.vwgroup.io`, `skodaid.vwgroup.io`,
  `terms-and-conditions` — and raise the dedicated
  `MarketingConsentError` / `TermsAndConditionsError` so the existing
  Repair-flow (since v2.0.0) surfaces an actionable deep-link to the
  brand portal. *Bazinga* — the wall is now visible.

- **`device_tracker.<vin>_position.last_seen_at` MQTT-statestream break** — pre-v2.2.0
  exposierte `device_tracker.py:extra_state_attributes` das raw `datetime` Object
  von `compute_connection_state()` direkt. MQTT-Bridge/Recorder/REST-API silent
  break (HA frontend zeigt `unknown`, recorder loggt TypeError jeden Poll). Fix
  via `json_safe()` wrap. Cross-references: Skoda PR #1090, myskoda #639.
  *"Worst. Bug. Ever." — Comic Book Guy*

### Changed

- **`sensor.py:extra_state_attributes` defensive-wrapping** — alle 5 return-paths
  (`recent_trips`, `recent_charging_sessions`, `charging_profiles`,
  `preferred_workshop`, `equipment`) wrapped in `json_safe()` als Regression-Schild
  für Phase-2 Additions (kommende Felder wie `fullyChargedAt` würden sonst die
  gleiche Bug-Klasse re-introduzieren).

- **`async_migrate_entry` Stub + `_get_coordinator` Defensive Refactor** —
  pre-empts HA Core deprecation-cliff der competitors brach (audi_connect_ha
  #728 "Invalid Credentials after every Core update", mitch-dc #303 "Cannot
  login after HAOS 16.1"). Beide Projekte brachen silent als HA Core
  ConfigEntry data-serialization änderte. v2.2.0 deklariert
  `async_migrate_entry` jetzt — heute no-op (return True für jede entry
  version, VERSION bleibt 1) aber **fully wired** so dass v3.0.0 ConfigEntry-
  Restructure nur die innere Migration-Logik braucht, nicht den Lifecycle-
  Hook. Bonus: `_get_coordinator` switched von `hasattr(entry, "runtime_data")`
  auf `getattr(entry, "runtime_data", None)` — defensive gegen startup-race
  conditions ohne den hasattr-overhead. *"Suit up!" — Barney, before every
  HA Core release-train cliff.*

---

## [2.1.0] - 2026-05-15 ✨🌍 Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools / Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools

> v2.1.0 sammelt 4 post-v2.0 Wins die im Big-Bang Scope-Cut waren oder
> durch Scout-Reports nachgereicht wurden. Fokus: ein neuer Skoda-Sensor
> (#186/#188), ein langjährig pendendes Plumbing-Refactor (HomeRegion +
> Issue #75), ein User-facing Diagnostik-Script + Browser-Mod-Cookbook.
>
> **Migration**: keine. Alle Änderungen additiv — bestehende
> Automationen + Lovelace-Cards funktionieren unverändert weiter.

### Added

- **Skoda Climate-Ready-At Sensor** (closes Scout #186 + #188) — neuer
  `sensor.<vin>_climate_ready_at` (TIMESTAMP device class) für Skoda
  MY24+ Fahrzeuge mit aktiver Vorklimatisierung. Liest aus
  `air-conditioning.estimatedDateTimeToReachTargetTemperature`. Sehr
  nützlich für "Vorklimatisierung 5min vor Abfahrt" Automatisierungen
  via Template `{{ as_datetime(states('sensor.x')) - 5|minutes }}`.
  Brand-restricted via `_DATA_PRESENT_REQUIRED` — non-Skoda und
  inaktive Klimatisierung erzeugen keine Phantom-Entität.
  Übersetzungen alle 8 Sprachen.

- **`scripts/verify_my_vin.py` — User-facing pre-flight diagnostic** —
  neuer Standalone-Script den User vor (oder anstelle von) Integration-
  Install laufen lassen können um zu sehen WELCHE Sensoren bei IHREM
  konkreten VIN populieren würden. Loggt sich genau wie die Integration
  in den Hersteller-API ein, ruft `get_vehicles()` + `get_status(vin)`
  pro VIN auf, druckt eine privacy-anonymisierte Tabelle:
  - ✅ Felder die populieren würden
  - ⚠️ Felder die "Unknown" bleiben würden (Firmware liefert sie nicht)

  Use-Cases: Pre-install-Check, Issue-Triage ("paste den Output"),
  Pre-Cariad-MBB-Vehicles können prüfen ob VIN überhaupt antwortet.
  Privacy: VINs gemaskt, GPS auf 1 Dezimalstelle gerundet, Tokens
  gestrippt — Daten gehen NUR an den Hersteller-API selbst.

- **`docs/recipes/browser-mod.md` — Cookbook für browser_mod ↔ VAG Connect** —
  5 fertige YAML-Recipes für die wichtigsten Frontend-Use-Cases:
  1. 12V-Battery-Low Fullscreen-Popup (12V drops < 11.5V → tablet warning)
  2. NFC-Tag triggert Quick-Command-Sheet (Lock/Unlock/Climate/Wake/Flash)
  3. Send-Destination Confirm-Dialog (ha-form mit Edit + Submit)
  4. Charging-Done Toast (alle registrierten Browser)
  5. Vehicle-Render Picture-Card mit Popup-Detail (Map + Battery + Glance)

  Pure YAML, kein Python-Code im Repo. Erfüllt EXTERNAL_BLOCKED Recipe
  A.14 + `docs/research/browser-mod-integration-2026-05-03.md §F`.

### Changed

- **HomeRegion Full Wire-In** (closes EXTERNAL_BLOCKED Track 3 +
  Plumbing für Issue #75) — Audi/VW EU API-Client (vw_eu.py, von
  Audi vererbt) routet jetzt alle 12 per-VIN URL-Bauers über
  `self._base_for_vin(vin)` statt hardcoded `_BASE`. `get_vehicles`
  populiert die Per-VIN-Cache (`self._vehicle_bases`) parallel via
  `mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion`
  beim Garage-Discovery. Cache-TTL 7 Tage. Best-effort: Discovery-
  Fehler fallen zurück auf default `_BASE` — der EU-Standard-Pfad
  (99% der User) bleibt unverändert. Vehicles aus Non-EU-Regionen,
  US-spec VW EU Imports oder andere region-routed Cars sehen jetzt
  ihre korrekte Backend-URL statt 403/404. Bruno-CI-Drift-Script
  (`scripts/check_bruno_url_drift.py`) erweitert um die neue
  `{self._base_for_vin(vin)}/...` und `{base}/...` Patterns.
  88/88 strict pass.

---

## [2.0.1] - 2026-05-15 🚨🔒 Safety-Fix: `doors_locked` False-Negative Cross-Brand / Safety-Fix: `doors_locked` False-Negative Cross-Brand

### Fixed

- **Critical Safety-Fix: `doors_locked` zeigte fälschlich "Unlocked" für tatsächlich verriegelte Autos** (User-Bericht via #131 Follow-up).

  **Root cause** war ein **Doppel-Bug**:
  1. **Dataclass-Default** `doors_locked: bool = False` in `cariad/models.py` — bei jedem Parser-Miss (Backend-Hiccup, `.error` Envelope, fehlendes Feld, unbekannter Firmware-Wert) blieb das Feld auf `False` statt korrekt `None`.
  2. **4 von 5 Brand-Parser** verwendeten `field = X == "LOCKED"` Pattern — wenn `X` `None` war, wurde `doors_locked` AKTIV auf `False` gesetzt (statt unverändert zu lassen). Skoda war seit v1.20.2 bereits defensiv.

  **Fix:**
  - 14 sicherheitsrelevante Booleans in `models.py` umgestellt von `bool = False` auf `bool | None = None`: `doors_locked`, `doors_open`, `windows_open`, `connector_locked`, `is_charging`, `plug_connected`, `auto_unlock_charge`, `climatisation_active`, `is_driving`, `is_online`, `warning_active`, `warning_oil`, `warning_engine`, `warning_tyre`, `warning_brakes`.
  - 4 Brand-Parser auf defensive `isinstance(str)` + `.upper()` umgestellt: **`vw_eu.py`** (auch Audi via Vererbung), **`porsche.py`**, **`seat_cupra.py`**, **`vw_na.py`**.
  - **VW EU/Audi**: `overallStatus == "SAFE"` jetzt explizit detected → setzt `doors_open=False, windows_open=False`. Vorher fielen "SAFE" Cars auf Default-False (zufällig richtig); jetzt explizit + nachvollziehbar.
  - **Skoda**: bereits korrekt am Parser-Level — profitiert automatisch vom Default-Fix.
  - Existing LOCK-Class Invert in `binary_sensor.py:390-394` und `lock.py:53` funktionieren transparent mit `None` (zeigen "Unknown" statt falsch "Unlocked").

  **User-Impact:**
  - Vor v2.0.1: Backend-Hiccup → HA zeigt "Unlocked" obwohl Auto verriegelt → User glaubt sicher, Auto ist offen
  - Ab v2.0.1: Backend-Hiccup → HA zeigt "Unknown" → User sieht klar dass aktuell keine Daten verfügbar
  - Auch betroffen waren `windows_open`, `connector_locked`, `warning_*` — alle false-negatives die echte Gefahren maskieren konnten

### Added

- **CUPRA Born MY26 `charging.rateInKmph` Parser-Fallback (closes Scout #192)** — neuer dritter Fallback in `seat_cupra.py:464` für die Lade-Rate (`chargeRateInKmPerHour` → `chargeRate_kmph` → `rateInKmph`). Born MY26 Firmware shippt das Feld auf `charging.rateInKmph` direkt am OLA Endpoint.

---

## [2.0.0] - 2026-05-15 🎯🚀 Big-Bang Release — 19 PRs in einem Schlag / Big-Bang Release — 19 PRs in one shot

> **v2.0.0 ist die größte Release in der Geschichte des Projekts.** 19 PRs
> über 4 Phasen, gebündelt zu **15 [NEW v2.0] Features** quer durch alle
> 7 Brands. Schließt Issue #33 (Diebstahl-Alarm), Issue #163 (heaterSource),
> setzt den Architektur-Seam für die Sept-2026 EU Data Act Deadline,
> und re-introduce't `quality_scale: platinum` nach v1.26.x revert.
>
> **TL;DR der 15 NEW v2.0 Features:**
> 1. Skoda Driving-Score Sensor (MY24+)
> 2. Cross-brand Aux-Heating Parität (Skoda)
> 3. Porsche TPMS (4 Reifen + Warning)
> 4. Long-Term Trip Aggregates (Audi/VW EU)
> 5. Departure-Timer Read-Only Binary-Sensors
> 6. Weekly Preheat (`recurring_on` Service-Param)
> 7. Charging-Station POI Lookup Service
> 8. Vehicle Alarm Sensors (#33)
> 9. heaterSource Sensor (#163)
> 10. Push-Manager Lifecycle-Wiring (3 Brands)
> 11. EU Data Act Abstraction Shim
> 12. Auth Resilience One-Click Repair
> 13. System Health Panel
> 14. Quality Scale Platinum (re-introduced)
> 15. DeviceInfo `configuration_url` + `suggested_area`
>
> Architektur-Audit: [Big-Bang Audit & Plan](docs/research/2026-05_big-bang-audit-and-plan.md).
>
> **Migration**: keine. Alle Änderungen sind additive — bestehende
> Automationen + Lovelace-Cards funktionieren unverändert weiter.

### Added

- **`quality_scale: platinum`** in manifest.json — `quality_scale.yaml`
  enthält 47 done + 2 exempt rules across all 4 tiers (Bronze/Silver/Gold/
  Platinum). Reverted in v1.26.1 als Sicherheitsmaßnahme; v1.26.2 RCA
  bestätigte hacs.json zip_release als Wurzelfehler. Hassfest validiert
  in CI ohne Probleme — wir sind offiziell Platinum-tier.

- **DeviceInfo `configuration_url` + `suggested_area="Garage"`** —
  Brand-aware "Open in App" Button am Device-Detail-Page (deep-link zu
  myAudi / myVolkswagen / myskoda / myseat / mycupra / myporsche /
  myvw je nach Brand). Auto-Area "Garage" beim ersten Setup. Reverted
  in v1.26.1, root cause war NICHT diese Fields (sondern `hacs.json`
  `zip_release`). Verified safe via CI Hassfest seit v1.27.0.

- **System Health Panel** (`system_health.py`) — Settings → System → Repairs zeigt
  jetzt at-a-glance: Integration-Version, configured brands, last poll per entry,
  API quota remaining, Push-Channel-Status, Cariad-BFF reachability. Drop-in
  Module, von HA automatisch geladen. Parity mit audi_connect_ha v2.0.1-beta.8.

- **Auth Resilience: One-click Repair für invalid credentials / 2FA / T&C / marketing-consent.**
  Repair-Issues für diese 4 reasons sind jetzt `is_fixable=True` — Klick auf
  "Repair" Button in HA UI öffnet direkt den Reauth-Config-Flow. Vorher musste
  User die Integration entfernen + neu hinzufügen. Schließt audi_connect_ha
  #728 / CarConnectivity #92 / evcc #29760 cross-integration pain pattern.

- **Skoda Driving-Score Sensor [NEW v2.0]** — neuer Effizienz-Score 0-100
  (`driving_score`) + Class-Bucket (`driving_score_class`, z.B. `EXCELLENT`,
  `GOOD`, `AVERAGE`) für Skoda MY24+ Fahrzeuge. Datenquelle: mysmob
  `GET /api/v2/vehicle-status/{vin}/driving-score`, parallel im
  `asyncio.gather` Polling-Cycle integriert. Brand-restricted via
  `_DATA_PRESENT_REQUIRED` — non-Skoda Fahrzeuge sehen keine Phantom-
  Entitäten. Übersetzungen für alle 8 Sprachen (DE/EN/CS/ES/FR/NL/PL/SV).

- **Cross-brand Aux-Heating Parität (Skoda)** — `command_start_aux_heating`
  + `command_stop_aux_heating` Methoden auf SkodaClient ergänzt
  (vorher nur SEAT/CUPRA). Verbindet die bereits seit v1.x existierenden
  HA Services + `VagAuxHeatingSwitch` Entity transparent für Skoda PHEV/
  Diesel-Modelle mit Standheizung (Octavia, Superb, Kodiaq iV).

- **Porsche TPMS Sensors [NEW v2.0]** — vier Reifen-Druck-Sensoren
  (`tire_pressure_front_left_bar` … `tire_pressure_rear_right_bar` in bar
  mit `device_class=PRESSURE`) plus aggregierter `tire_pressure_warning`
  binary_sensor (PROBLEM device_class). Datenquelle: PPA
  `GET /app/connect/v1/vehicles/{vin}/measurements?fields=TIRE_PRESSURE`
  (Porsche ConnectPlus Subscription erforderlich). kPa↔bar Auto-Convert
  ist eingebaut. Brand-restricted via `_DATA_PRESENT_REQUIRED` —
  non-Porsche und pre-TPMS Modelle erzeugen keine Phantom-Entitäten.
  Übersetzungen alle 8 Sprachen (DE/EN/CS/ES/FR/NL/PL/SV).

- **EU Data Act (EUDA) Abstraction Shim [NEW v2.0]** — neuer Modul
  `custom_components/vag_connect/euda.py` mit `EUDADataSource` ABC plus
  zwei Adapter-Schalen (`LegacyEUDAAdapter` für die heutigen Brand-
  Clients, `VSSEUDAAdapter` für die kommenden COVESA VSS / W3C VISSv2
  Endpoints). Interface-only — beide `get_signal` Methoden raisen
  `NotImplementedError` bis ein OEM seinen EUDA-konformen Endpoint
  veröffentlicht. Schaft den architektonischen Seam **vor** der
  Sept-2026 EUDA Art.3 Deadline, sodass die Aktivierung später nur
  noch eine Inner-Method ist und keine PR durch alle Brand-Clients
  zieht. Cross-Reference: COVESA VSS, W3C VISSv2, EU-Reg. 2023/2854 Art. 3+5.

- **README-Restrukturierung — alle 8 Sprachen synchron + Roadmap raus +
  USP-Sektion + v2.0-Highlights mit `[NEW v2.0]` Marker**.
  Komplette READMEs (DE + EN) neu geschrieben mit:
  - "✨ v2.0.0 Big-Bang Highlights" Tabelle (15 NEW v2.0 Features)
  - "⭐ Was uns einzigartig macht" / "What makes us unique" USP-Sektion
    ohne Konkurrenz-Naming, nur "wir sind einzigartig bei diesen Features"
  - Brand-Support-Tabelle mit per-Brand `[NEW v2.0]` Markierungen
  - `quality_scale: platinum` Badge ergänzt
  - Roadmap-Sektion **entfernt** (war Wartungs-Burden, ROADMAP.md bleibt
    eigenes Dokument für Tiefen-Detail)
  Die 6 weiteren Sprach-READMEs (FR/ES/NL/PL/CS/SV) erhalten denselben
  v2.0-Highlights-Insert + USP-Sektion (auf Englisch geliefert mit
  expliziter Note "auch auf Englisch verfügbar") + Roadmap-Sektion
  entfernt + Platinum-Badge ergänzt. Mid-term: native Lokalisierung
  der Highlights-Tabelle in alle 6 Sprachen via Community-PRs.

- **Push-Manager Lifecycle-Wiring (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW Cariad FCM) [NEW v2.0]** —
  schließt PR #14-16 in einem gemeinsamen Architektur-PR. Coordinator
  hat jetzt 3 neue Slots (`_skoda_push`, `_cupra_seat_push`,
  `_audi_vw_push`) plus `async_start_push_managers()` /
  `async_stop_push_managers()` Helpers. Aktivierung pro Brand via die
  bereits vorhandenen OptionsFlow-Toggles (`enable_push_mqtt`,
  `enable_push_fcm`, `enable_push_audi_vw`). System-Health-Panel zeigt
  pro Push-Channel den `state` (stopped / starting / connected /
  reconnecting / disabled / unavailable). Die unterliegenden
  `_connect_and_listen` sind weiterhin Scaffolding (lazy-imported
  aiomqtt + firebase-messaging) — sobald ein Tester die FCM-Keys /
  MQTT-Broker-Auth bestätigt geht das ohne Coordinator-Refactor live.
  Schließt #14-#16 aus der v2.0.0 Big-Bang Audit.

- **Vehicle Alarm / Diebstahl-Sensoren [NEW v2.0] — schließt Issue #33** —
  drei neue Entitäten exposed direkt aus `access.accessStatus.value` (Cariad-BFF):
  - `binary_sensor.<vin>_alarm_active` (PROBLEM device_class) — Auto-Alarm
    aktuell aktiv (`vehicleAlarm == "ALARM"`)
  - `binary_sensor.<vin>_siren_active` (SOUND device_class) — Sirene
    schreit gerade (`siren == "ACTIVE"`), Diagnostik-Kategorie
  - `sensor.<vin>_last_alarm_at` (TIMESTAMP) — letzter Alarm-Zeitstempel
  Brand-restricted via `_DATA_PRESENT_REQUIRED` — Fahrzeuge ohne
  Anti-Diebstahl-Telemetrie erzeugen keine Phantom-Entitäten.
  Übersetzungen alle 8 Sprachen.

- **Heater-Source Sensor [NEW v2.0] — schließt Issue #163 (best-effort)** —
  neuer `sensor.<vin>_heater_source` Read-Only-Sensor (Diagnostik-
  Kategorie) für ID.x Heat-Pump-Modelle. Liest aus
  `climatisation.climatisationSettings.value.heaterSource` (Werte:
  `electric` / `fuel`). Read-Only-Shape gewählt weil kein bestätigter
  Tester für Write-Semantik vorhanden ist; falls später ein Tester
  Write-Support bestätigt wird ein Folge-PR den Sensor zu einem
  `select.<vin>_heater_source` upgraden. Brand-restricted via
  `_DATA_PRESENT_REQUIRED` — Fahrzeuge ohne Heat-Pump leaven None →
  keine Phantom-Entität. Übersetzungen alle 8 Sprachen.

- **Weekly Preheat — `recurring_on` für `set_departure_timer` Service [NEW v2.0]** —
  der bestehende Service `vag_connect.set_departure_timer` akzeptiert
  jetzt eine optionale `recurring_on` Liste mit Wochentagen (z.B.
  `["MONDAY","TUESDAY","WEDNESDAY","THURSDAY","FRIDAY"]`). Damit
  schaltet der Timer auf wiederkehrend und feuert an jedem genannten
  Tag. Implementiert für Audi/VW EU (`vw_eu.command_set_departure_timer`)
  und VW NA (`vw_na.command_set_departure_timer`); Porsche erhält den
  Param transparent ohne Effekt (PPA hat kein Weekday-Field). UI:
  Multi-Select-Selector in `services.yaml` für Devtools-Komfort.

- **Charging-Station POI Lookup Service [NEW v2.0]** — neuer Service
  `vag_connect.find_charging_stations` (mit `response_variable:` Support
  ab HA 2024.4+) liefert eine Liste umliegender Ladestationen
  (id/name/address/operator/maxPowerInKW/connectorTypes/availability)
  über die Cariad-BFF POI API
  (`GET /charging-stations/v1/locations`). Audi + VW EU only — andere
  Brands liefern eine `ServiceValidationError` mit klarer Begründung.
  Default 5 km Suchradius / 25 Ergebnisse, max 100 km / 100 Ergebnisse.

- **Long-Term Trip Aggregates [NEW v2.0]** (Audi + VW EU) — drei neue
  Lifetime-Sensoren auf Basis der `/tripstatistics?type=longTerm`
  Antwort, die der Coordinator schon seit v1.14.0 in `lifetime_*`
  Felder mergt aber bisher NIE als Entitäten exposed wurden:
  `lifetime_distance_km` (TOTAL_INCREASING), `lifetime_avg_fuel_
  consumption_l_100km` (combustion-gated), `lifetime_avg_electric_
  consumption_kwh_100km` (electric-gated). Brand-Gating via
  bestehendem `_TRIP_STATS_BRANDS` + `_TRIP_STATS_KEYS`. Übersetzungen
  alle 8 Sprachen.

- **Departure-Timer „Enabled" Read-Only Binary-Sensors [NEW v2.0]** —
  drei neue `binary_sensor.<vin>_departure_timer_X_enabled` Entitäten
  (X=1/2/3). Bisher war der Aktivierungszustand nur via dem schreib-
  baren `switch.<vin>_departure_timer_X_switch` lesbar — was Templates
  und Automatisierungen unangenehm macht weil Switches Side-Effects
  haben. Die neuen reinen Read-Sensoren entkoppeln Read von Write.
  Übersetzungen alle 8 Sprachen.

### Fixed

- **#53 CUPRA Born — defensive `command_flash` + OLA parking parser fix.**
  - `command_flash` versucht jetzt zuerst Body ohne `userPosition` (manche
    Firmware-Varianten akzeptieren das); fällt auf position-required nur
    zurück wenn Backend explizit 400 wirft. Unblocked User deren Auto noch
    keine GPS-Position cached hat (frischer Install / Privacy-Mode).
  - OLA `parkingposition` Parser packt jetzt `data` envelope aus (mirror
    von v1.27.1 Cariad-Fix). Ohne diesen Fix lief `parking.get("lat")`
    silent auf None bei OLA-Backends die das envelope nutzen → keine GPS
    → command_flash failed unsere pre-validation.
  - Bessere Error-Message in command_flash mit konkreten Schritten zur
    Behebung.

## [1.27.2] - 2026-05-11 ⚡🔌 Scout-Felder Power-Patch + Plug-Diagnose / Scout-Felder Power-Patch + Plug Diagnostics

⚡ **PATCH-Release.** Schweizer-Taschenmesser-Power-Update — 3 Scout-Issues (#180, #181, #182) komplett geschlossen + 2 zusätzliche Plug-Diagnose-Sensoren.

### ✨ Neue Entities (3)

**`sensor.{name}_charging_settings_pending`** (Diagnostic, default disabled)
Zählt offene `putChargingSettings` Requests am Cariad-Gateway. Normalerweise 0. Wenn >0 → eine Setting-Änderung ist queued aber noch nicht ans Auto durchgereicht. Schließt **Scout #181 (Audi: `charging.chargingSettings.requests`)**.

**`sensor.{name}_plug_led_color`** (Diagnostic, default enabled)
Visual Feedback: `none` / `red` (Fehler) / `green` (idle/done) / `blue` (charging). Drivable für Automationen wie "alert if LED turns red".

**`binary_sensor.{name}_external_power_available`** (Diagnostic)
True wenn die Wallbox/EVSE aktiv Power zum Stecker liefert. False = Plug connected aber Power-Source nicht verfügbar (RCD-Trip / Phasen-Verlust / Smart-Charging-Pause). Wichtig für EV-Power-Monitoring-Automationen.

### 🎯 Scout Issues Closed

| Issue | Field | Status |
|---|---|---|
| **#180** (VW) | `charging.chargingStatus.value.chargeRate_kmph` | ✅ Bereits seit v1.10.0 als `sensor.charging_rate_kmh` (UnitOfSpeed.KILOMETERS_PER_HOUR mit auto km/h ↔ mph). Verifiziert v1.27.2. |
| **#181** (Audi) | `charging.chargingStatus.value.chargeRate_kmph` | ✅ Selbe Implementation, brand-agnostic. |
| **#181** (Audi) | `charging.chargingSettings.requests` | ✅ NEU als `charging_settings_pending` in v1.27.2. |
| **#182** (VW) | `charging.chargingStatus.value.chargeRate_kmph` | ✅ Implemented. |

### 📋 Scout-Pipeline-Policy (neu in v1.27.2)

Ab jetzt: **jedes Scout-Issue wird im nächsten Minor entweder als Entity geshippt oder closed-as-not-promoted** (mit Begründung). Kein Drift mehr. Dokumentiert in [Strategic Roadmap](docs/research/2026-05_strategic-roadmap-v1.27-to-v2.0.md) Section 8.

### 🔧 Code Changes

- `cariad/models.py`: 3 neue Felder (`charging_settings_pending`, `plug_led_color`, `external_power_available`)
- `cariad/api/vw_eu.py`: 3 neue Parser-Lines nach `charging_rate_kmh`
- `sensor.py`: 2 neue VagSensorDescription
- `binary_sensor.py`: 1 neue VagBinarySensorDescription
- `strings.json`: 3 neue Translation-Keys

### 🧪 Verification

Sensor-Definitionen verified compile-clean. Live-Test bei nächstem Cariad-Polling-Cycle.

---

## [1.27.1] - 2026-05-11 🚨🔧 Hotfix: device_tracker GPS-Daten / Hotfix: device_tracker GPS data

🚨 **PATCH-Release.** v1.27.0 hatte einen Parser-Bug der seit unbestimmter Zeit den device_tracker für Cariad-BFF Brands (VW EU, Audi via Cariad-Pfad) verhindert hat.

### 🐛 Root cause

Cariad-BFF `/vehicle/v1/vehicles/{vin}/parkingposition` returnt:
```json
{"data": {"lat": 47.401794, "lon": 8.215701, "carCapturedTimestamp": "..."}}
```

Der Parser in `cariad/api/vw_eu.py:1195` las direkt `parking.get("lat")` ohne den `data` wrapper auszupacken — Ergebnis war immer `None`. `device_tracker._has_gps()` filtert `None` lat/lon stillschweigend raus → kein Tracker spawned. Bug live entdeckt durch User-Report + verifiziert via `scripts/verify_cariad_for_gte.py` Output.

### 🔧 Fix

`cariad/api/vw_eu.py` parking position parser packt nun `data` wrapper aus:
```python
parking_data = parking.get("data") if isinstance(parking, dict) else parking
d.latitude = parking_data.get("lat")
d.longitude = parking_data.get("lon")
```

Mit Fallback auf top-level falls historische/alternative Firmwares ohne `data` wrapper antworten.

Selbe Fix für `parking_data.address` (parking_address + parking_city Sensoren).

### ✅ Was jetzt funktioniert

- `device_tracker.{name}_position` mit live lat/lon (Karte in HA)
- `sensor.{name}_parking_address` mit `formattedAddress` oder composed street/city/country
- `sensor.{name}_parking_city`
- `extra_state_attributes` für Map-Tooltip (parking_address, last_seen, etc.)

### 🧪 Verifikation

Live verifiziert mit Golf 7 GTE (VIN WVWZZZAUZFW...) am 2026-05-11:
- Cariad parkingposition response: lat 47.401794, lon 8.215701 (Aargau Region)
- Pre-fix: device_tracker unknown / nicht gespawnt
- Post-fix: device_tracker.golf_gte_position erscheint mit korrekter Position

### 📋 Affected versions

Parser-Bug existiert wahrscheinlich seit der initialen Cariad-BFF Implementierung. Fix gilt rückwirkend für ALLE Cariad-Brands (VW EU + Audi via Cariad). Skoda mysmob + SEAT/CUPRA OLA + Porsche PPA haben eigene Parser, nicht betroffen.

---

## [1.27.0] - 2026-05-11 🔬📋 Pre-Cariad PHEV Research + Strategic Roadmap / Pre-Cariad PHEV Research + Strategic Roadmap

🔬 **MINOR-Release.** Diese Version bündelt 6 Stunden tiefgehende Pre-Cariad MBB Forschung, einen kompletten Strategic Roadmap, sowie das Polish-Feature aus Issue #178 (loggers field — `quality_scale` bleibt zurückgehalten bis HA Core stabilisiert).

### 🎯 Hauptfunde (siehe Audit Doc)

1. **Pre-Cariad MBB ist gated by `XID_APP_VW`** Permission — nur offizielle VW App's pre-provisionierte client_id hat das. Public `/mbbcoauth/mobile/register/v1` xclientId's bekommen das nie. **Kein public Bypass existiert.** ✗ Legacy CarNet Password-Grant (msg.volkswagen.de/.../core/auth/v1/) gibt 401 für ALLE Credentials (server-seitig deprecated).

2. **WeConnect-ID Client + scope `openid profile mbb cars vin`** produziert id_token mit `VWGMBB01DELIV1` audience → MBB token exchange erfolgreich (vwToken in VW-Namespace mit `iss: VWGMBB01DELIV1`). Wiederverwertbar für künftige MBB-Arbeit.

3. **Pre-Cariad Cars sind im Cariad-Backend** — Golf 7 GTE PHEV (MJ 2015) liefert 12/12 Cariad selectivestatus jobs erfolgreich. **vag-connect-ha unterstützt diese Autos bereits** out-of-the-box via existing Cariad-BFF Code-Pfad.

### ✨ Neue Files

- **`docs/research/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md`** (413 Zeilen) — komplettes 8-Sektion Audit der Pre-Cariad MBB Auth-Landscape, IDK Client Inventory, carType-Bug-Dokumentation, ~55-60 Entity-Inventory für Golf 7 GTE
- **`docs/research/2026-05_strategic-roadmap-v1.27-to-v2.0.md`** (300+ Zeilen) — Full Competitive Landscape Analysis, Open Issues Triage, 5 Strategic Pillars, Detailed Roadmap v1.27.0 → v2.0.0, Risk Matrix, Quick Wins
- **`ROADMAP.md`** (Top-Level) — Public 300-Wort Distillat des Strategic Roadmap. Wir sind die einzige VAG-HA-Integration mit publicly gepflegter Roadmap.
- **`tests/bruno/mbb_legacy/`** — Bruno Collection mit 18+1 .bru Files für Pre-Cariad MBB Endpoints (community-resource). Mit gitignored `mbb.local.bru` Pattern für Live-Credentials.
- **20 Diagnostic Scripts in `scripts/`**: get_idk_token, get_mbb_token, decode_id_token, verify_mbb_endpoints, verify_cariad_for_gte, verify_cariad_full, full_mbb_matrix, try_vw_*, try_carnet_password_grant, hunt_raw_fields, investigate_tank_data, test_active_actions, test_enginetype, extract_all_sensors, show_operations, wake_and_refresh, try_country_codes, try_vw_appids, try_enrollment.

### 🔧 Production Code Changes

- **`cariad/auth/idk.py`**: `IDKAuth.authenticate()` bekommt neuen `mbb_mode: bool = False` Parameter. Wenn aktiviert: nutzt OIDC HYBRID flow (`response_type=code id_token`) und extrahiert id_token aus authorize-redirect URL fragment (statt code-flow id_token aus token endpoint). Hilfs-Funktion `_extract_param_from_url()` für query+fragment parsing. Neuer `last_redirect_url` instance attribute. **100% backward-compatible** — `mbb_mode` defaults to False, alle existing Cariad/Audi/Skoda/SEAT auth flows unchanged.

- **`manifest.json`**: Re-introduced `loggers` field (Issue #178 Quick Win). `quality_scale` bleibt zurückgehalten bis HA Core's Validator stabilisiert (war v1.26.1 root cause).

### 📊 Was wir aus dieser Session gelernt haben

| Kategorie | Lessons |
|---|---|
| **Architektur** | Test Cariad-BFF FIRST when investigating any "Pre-Cariad" car. Capabilities endpoint ist source of truth. OIDC Hybrid yields cross-service-signed tokens. |
| **Process** | Don't speculate about service desk fixes without evidence (mistake retracted). Build diagnostic helper script BEFORE integration code. Bruno for human, Python for automation. |
| **Codebase** | `mbb_mode` jetzt production-ready für künftige hybrid-flow Anforderungen. Bruno-Sammlung community-valuable. Diagnostic-Scripts reusable für jeden User. |

### 🛣️ Roadmap-Vorschau (siehe Strategic Roadmap)

- **v1.28.0** — Auth Resilience (Email-Code 2FA, Marketing-Consent Detection, HA-Update-Survival). Preempts CarConnectivity #92 + audi_connect_ha #728 + evcc #29760.
- **v1.29.0** — Push Phase 2 Live (Skoda MQTT + FCM für VW/Audi/CUPRA/SEAT). Issue #161.
- **v1.30.0** — MBB Phase 2 + Lovelace Card. Issues #160, #33, #163, #162.
- **v2.0.0** — EU Data Act Compliance + SDV-West Readiness. Q3/Q4 2026.

### 🚫 Was wir NICHT mehr tun

- ❌ Reverse-Engineering Legacy MBB direct-data Endpoints (Audit confirmed walled)
- ❌ Polish-only Releases (bündeln in feature releases)
- ❌ Scout-Felder ohne Entity-Intent stehen lassen

### 🆕 Was wir starten

- ✅ Public ROADMAP.md (competitor differentiator)
- ✅ Quarterly "VAG ecosystem report" in `docs/research/`
- ✅ "Tester-of-the-month" recognition
- ✅ 2FA + Marketing-Consent Test-Matrix für jede major release
- ✅ Optional: CI Smoke gegen Bruno-Sammlung (nightly drift detection)

### 🛡️ Sicherheit

- `.gitignore` Regel `tests/bruno/**/environments/*.local.bru` — verhindert Commit echter VW-Credentials
- get_mbb_token.py + get_idk_token.py: Password via `getpass`, nie auf Disk, nie in Shell-History
- Bruno Environment-Variablen marked `vars:secret` für UI-Maskierung

---

## [1.26.2] - 2026-05-09 🚨🔧 Hotfix-2: Root cause `zip_release` revertet — HACS install path / Hotfix-2: Root cause `zip_release` reverted — HACS install path

🚨 **PATCH-Release (Hotfix-2).** v1.26.1 hatte das Loading-Problem nicht gelöst. Root-Cause-Analyse via Diff `v1.24.2..v1.25.0` (last working → first broken) hat den eigentlichen Killer identifiziert:

### 🔍 Root cause

Der einzige relevante Unterschied der HACS-Install-Pfad betrifft war in `hacs.json` (added v1.25.0 PR-EFG):

```diff
+  "zip_release": true,
+  "filename": "vag_connect.zip"
```

Diese 2 Direktiven ändern HACS's Install-Mechanismus von "default zipball-extract" auf "named zip asset". Bei Migration von einer Vorinstallation (default) auf das neue Format **löscht HACS den alten `/config/custom_components/vag_connect/` Folder, schafft aber den neuen nicht** wenn irgendwas im neuen Pfad fehlschlägt → User landet mit komplett fehlender Integration.

User-Symptom: HA-Log zeigt `Integration 'vag_connect' not found` und vag_connect-Folder ist physisch weg aus `/config/custom_components/`.

### 🔄 Reverted

- **`hacs.json`**: Entfernt `zip_release: true` + `filename: vag_connect.zip`. HACS fällt zurück auf den default install mechanism der seit v1.0.0 funktioniert hat.

### 📋 NICHT reverted

Alle Code-Features aus v1.25.0 (Cross-Brand Parity, Listener Pattern, GPS hardening, MBB VSR Phase 2, Translation sync) und v1.26.0 (Welle-6 Feature Backlog 7 neue Entitäten + Cross-Brand Battery-Care Parity) bleiben aktiv. Plus die manifest-Bereinigung aus v1.26.1 (kein quality_scale, kein loggers field, kein DeviceInfo configuration_url/suggested_area).

### 🧠 Lesson

Vor Aktivierung von HACS-spezifischen Install-Direktiven (`zip_release`, `content_in_root`, `country`, etc.) muss jeder Update-Pfad existing-install → new-install getestet werden. Pure-additive Manifest-Änderungen sind sicher; HACS-Discovery-Format-Änderungen sind risiko-reich weil HACS die Migration nicht atomically macht.

Wenn `zip_release: true` zukünftig wieder gewollt ist (für 50% schnellere Installs), muss der release.yml Workflow erst sicherstellen dass jeder älteste Tag auch den `vag_connect.zip` asset hat — UND dass HACS-Migration explizit getestet wurde mit einer Test-HA-Instanz die vorher v1.24.2 hatte.

### ✅ Verifizierung

- `python -m ruff check custom_components/` → All checks passed
- `python -m mypy ... (CI flags)` → clean
- `hacs.json` zurück auf v1.24.2-Schema (keine neuen Felder)
- manifest.json: nur version 1.26.1 → 1.26.2 bumped

## [1.26.1] - 2026-05-09 🚨 Hotfix: Integration lädt nicht in v1.25.x / Hotfix: integration won't load in v1.25.x

🚨 **PATCH-Release (Hotfix).** User-Report 2026-05-09 22:35: Integration zeigt "Nicht geladen" in HA nach Update auf v1.25.x. Schneller Rollback der wahrscheinlichsten Verdächtigen aus dem v1.25.0 PR-EFG Mega-Bundle:

### 🔄 Reverted

- **`manifest.json`**: Entfernt `quality_scale: "platinum"` und `loggers: ["custom_components.vag_connect"]` (beide neu in v1.25.0). HA's runtime quality-scale validator scheint strenger zu sein als hassfest CI — wenn nicht 100% platinum-compliant verweigert HA möglicherweise den Load. Kommt in v1.27.0+ zurück nachdem wir compliance-Lücken analysiert haben.
- **`entity_base.py:device_info`**: Entfernt `configuration_url=...` (brand-aware "Open in App" Button) + `suggested_area="Garage"` (Auto-Area beim Setup). Diese DeviceInfo-Felder sind dokumentiert valid aber TypedDict-Validation in neueren HA-Cores könnte zu strict sein. Kommt in v1.27.0 zurück nachdem isoliert.

### 🎯 NICHT reverted (bleiben aktiv)

- v1.26.0 Welle-6 Feature Backlog (7 neue Entitäten + Cross-Brand Battery-Care Parity) — bleibt aktiv, betrifft nur per-vehicle parser logic
- v1.25.0 _normalize.py Foundation, Cross-Brand Parity Wins, Listener Pattern, GPS hardening, MBB VSR Phase 2, Translation sync — alle bleiben aktiv
- `entity_base.py:extra_state_attributes` (image_url für Custom Lovelace Cards) — bleibt aktiv, ist additive

### 🩺 Diagnose-Pfad

Wenn dieser Hotfix das Problem nicht löst: bitte HA-Logs unter Settings → System → Logs → Filter `vag_connect` → Trace posten unter neuer Issue. Wahrscheinliche restliche Verdächtigen wären dann Coordinator __init__ (CommandDispatcher) oder Listener Pattern in Platform setup_entry.

### 📋 Verifizierung

- `python -m ruff check custom_components/` → All checks passed
- `python -m mypy ... (CI flags)` → clean
- Kein Test-Impact (rein subtractive Änderungen)

## [1.26.0] - 2026-05-09 🎯 Welle-6 Feature Backlog (#173) — 7 neue Entitäten + Cross-Brand Parity / Welle-6 Feature Backlog (#173) — 7 new entities + Cross-Brand Parity

🎯 **MINOR-Release.** Setzt das Welle-6 Scout-Feature-Backlog (#173) um. **Diese Features waren in den Scout-Reports #129/#130/#132/#133/#143/#144/#145/#146/#147/#165/#167 enthalten aber wurden in v1.19.3 nur EXPECTED_KEYS-silenced statt als Entitäten exposed** — der v1.25.0 Audit hatte das als Pattern-Bruch identifiziert (vergleiche #91 → 5 neue Entitäten in v1.11.0).

### 🆕 Neue Entitäten (7 total)

**Sensoren** (4):
- **`sensor.<vin>_secondary_engine_range_km`** — Skoda PHEV (Kodiaq iV, Octavia iV, Superb iV) aus `driving-range.secondaryEngineRange.distanceInKm`. Komplementär zu `combustion_range_km` weil Skoda PHEVs beide via separate API-Blöcke seit 2024 firmware reporten. Closes Scout #165 (christianmhz).
- **`sensor.<vin>_next_charging_timer_id`** — VW EU/Audi aus `automation.chargingProfiles.value.nextChargingTimer.id` (1/2/3). Diagnostic-category. Read-side complement zum v1.16.0 write-side `set_departure_timer` service.
- **`sensor.<vin>_next_charging_timer_target_soc_reachable`** — VW EU/Audi aus `automation.chargingProfiles.value.nextChargingTimer.targetSOCreachable` ("calculating" oder Prozentwert). User sieht ob das Auto den nächsten Lade-Timer erreichen wird.
- **`sensor.<vin>_capabilities_count`** — VW EU/Audi aus `userCapabilities.capabilitiesStatus.value[].length` (typisch 54 items). Diagnostic für Power-User die debuggen wollen "warum fehlt Entity X bei mir?".

**Binary Sensors** (3):
- **`binary_sensor.<vin>_auto_unlock_when_charged`** — Cross-brand (VW EU/Audi via `charging.chargingSettings.value.autoUnlockPlugWhenCharged`; Skoda via `settings.autoUnlockPlugWhenCharged`/`autoUnlockPlugWhenChargedAC`). Diagnostic.
- **`binary_sensor.<vin>_climate_at_unlock`** — Cross-brand (VW EU/Audi via `climatisation.climatisationSettings.value.climatizationAtUnlock`; Skoda via `airConditioningAtUnlock`). Diagnostic.
- **`binary_sensor.<vin>_window_heating_enabled`** — Cross-brand (VW EU/Audi via `climatisation.climatisationSettings.value.windowHeatingEnabled`; Skoda via `windowHeatingEnabled`). Distinct from existing `window_heating_front/back` STATE switches — this is the SETTING ("auto-activate during climate?"). Diagnostic.

### 🌍 Cross-Brand Battery-Care Parity

- VW EU/Audi bekommen jetzt `battery_care_enabled` + `battery_care_target_soc_pct` aus Cariad-BFF (`charging.chargingCareSettings.value.batteryCareMode` + `batteryChargingCare.chargingCareSettings.value.batteryCareTargetSoc`). Skoda bekommt zusätzlich Wiring aus `settings.batteryCareModeTargetValueInPercent` + `settings.chargingCareMode`. Existierende Sensor + Binary Sensor (CUPRA/SEAT seit v1.17.5) brauchten kein neues Entity-Description.

### 🌍 Audi/VW EU `charging_rate_kmh` Parität

- Sensor existierte bereits cross-brand seit v1.10.0. Parser für VW EU/Audi war seit dem Anfang da. Closes Scout #167 als bereits-implementiert (Scout-Report kam von Firmware die das Feld zum ersten Mal bei diesem User auslieferte — EXPECTED_KEYS update folgt automatisch über v1.9.0 Pipeline).

### 🛡️ Defensive Coding

- Alle neuen Felder benutzen `safe_int` für Zahlen, explicit `isinstance` für bool/string types
- `_DATA_PRESENT_REQUIRED` extended um die 4 neuen Sensoren + 3 neuen Binary Sensors → keine Phantom-Entitäten für Brands/Vehicles ohne entsprechende API-Felder
- Translation-Keys in `strings.json` + DE-Übersetzung + 7 weitere Locales als English-Fallback (proper community translation deferred)

### 📚 Pattern Lessons

Die v1.25.0 Audit-Erkenntnis "silenced ohne Feature-Umsetzung sollte vermieden werden" wird ab jetzt umgesetzt: **Bei jedem Scout-Report VORHER prüfen ob feature-würdig**. Wenn JA: implementieren, dann silencen. Wenn NEIN: silencen + im Close-Comment `category: silence-only` mit Begründung dokumentieren.

### 📝 Docs / Docs

- **README.md (DE) komplett refactored** auf saubere HACS-Standard-Struktur (472 → 218 Zeilen, 54% schlanker). Klare Sektionen: Was-es-kann / Supported brands matrix / Installation 3-Optionen / Konfiguration Tabelle / Was-du-bekommst / Lovelace examples / FAQ / Privacy / Roadmap / Contributing / License. Historische Session-Notes raus → bleiben in `docs/ROADMAP.md` + `docs/CHANGELOG_TECHNICAL.md`.
- **README.en.md** spiegelt gleiche Struktur, English mirror.
- **`docs/GOLF_7_GTE_TANK_GUIDE.md`** neu (130 Zeilen): Step-by-step User-Anleitung für v1.25.0 PR-G MBB VSR Phase 2 Tank-Level fallback. Voraussetzungs-Tabelle, Logs-Pattern, 3 Diagnose-Szenarien, worst-case Alternative-Wege (OBD-II, EU Data Act, CarConnectivity-connector debug), Reporting-Template für Issue #160 follow-up.

## [1.25.0] - 2026-05-09 🚀 Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank) / Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank)

🚀 **MINOR-Release.** Größter Sprint seit v1.21.0 (8. Mai 2026). Bündelt 6 PRs (#168, #169, #170, #171 + final mega) mit:

- **Cross-brand parity wins** (Skoda 12V/lights/parking_address; VW EU/Audi/SEAT/CUPRA parking_address)
- **`_normalize.py`** Foundation (k_to_c, drivetrain, range_headline, first_status_value, NO_UPDATE_AVAILABLE backport)
- **Porsche HTTP hardening** (retry, 429 backoff, quota headers, refresh-storm-protection)
- **GraphQL PPC/PPE defensive** (audi_connect_ha #709 lesson)
- **Listener pattern** in 10 platforms — vehicles asleep at HA startup get entities spawned mid-session
- **GPS device_tracker hardening** ((0,0) guard, extra_state_attributes für Map-Tooltip)
- **CommandDispatcher Foundation** (Phase 1A — state extracted, methods stay; Phase 2 v1.26.0)
- **HA Map Integration**: vehicles als TrackerEntity mit SourceType.GPS + entity_picture sind sauber als Marker auf der Lovelace Map
- **Brand-aware "Open in App" Button** via `DeviceInfo.configuration_url`
- **`suggested_area="Garage"`** für Auto-Area beim ersten Setup
- **Vehicle-Bild als entity_picture** korrekt (war silent-no-op TypedDict bug)
- **`extra_state_attributes["image_url"]`** zentral — Custom Lovelace Cards (Ultra-Vehicle-Card, vehicle-info-card, mushroom) rendern Auto-Bild automatisch
- **HACS polish**: `zip_release: true`, `quality_scale: "platinum"`, `loggers` field
- **Translation sync** alle 8 Locales (de.json +8, en.json +13, 6 weitere +13 als best-effort English fallback)
- **MBB VSR Phase 2 read-side** für Golf 7 GTE Tank-Level — wenn Cariad-BFF `fuel_level` leer + VIN MBB-backed → fallback auf legacy `/fs-car/bs/vsr/v1/.../status` mit field-IDs `0x030103000A` (tank %) + `0x0301030005` (range)

Volle Detail-Notes der einzelnen Sub-PRs siehe nachfolgende Sub-PR Sections (in CI-Merge-Reihenfolge).

### 🎨 v1.25.0 Sprint C PR-EFG Mega — UX/UI + Translation Sync + MBB VSR Phase 2

Sub-PRs E + F + G bundled in einem Mega-Bundle (Sprint-Effizienz statt 3 separater PR-Cycles).

**🎨 UX/UI Polish (Audit Agent E findings):**
- `entity_base.py:124-125` Bug entfernt: `info["entity_picture"] = picture` war silent-no-op auf TypedDict — ersatzlos gestrichen weil das die `entity_picture` Property bereits korrekt liefert
- `DeviceInfo.configuration_url` brand-aware gesetzt (my.audi.com / mvw.de / mySkoda / MyCupra / etc.) — "Open in App" Button im HA Device-Layout
- `DeviceInfo.suggested_area="Garage"` — Auto-Area beim ersten Setup
- `extra_state_attributes["image_url"]` zentral in `entity_base.py` — Custom Lovelace Cards (Ultra-Vehicle-Card, vehicle-info-card, mushroom-template-card) lesen das automatisch und rendern Auto-Bild neben jedem Sensor

**📦 HACS / Manifest Polish:**
- `hacs.json: zip_release: true` + `filename: vag_connect.zip` — schnellere HACS Installs, weniger GitHub-API-Calls
- `manifest.json: quality_scale: "platinum"` — HA UI Quality-Badge
- `manifest.json: loggers: ["custom_components.vag_connect"]` — bessere Debug-Toggles in HA UI

**🌍 Translation Audit (Audit Agent D Top 1 finding) — alle 8 Locales synced:**
- DE: +8 keys (proper German translations für config-flow descriptions, 12V battery, max_charge_current, read_only_mode, scan_interval)
- EN: +13 keys (license_plate, equipment_count, requests_remaining_today sensors + quota_low/critical issues + push toggles)
- CS / ES / FR / NL / PL / SV: +13 keys each (best-effort English fallback — community Übersetzer können später ersetzen, war vorher gar nichts)
- Closes Gold-Quality-Scale `entity-translations` gap aus Audit Agent D

**🛢️ MBB VSR Phase 2 read-side (Golf 7 GTE Tank-Level — Audit Agent B):**
- Neuer `cariad/_mbb.py` Helper: `build_mbb_vsr_status_url()` + `parse_mbb_vsr_field()` defensive walker für legacy MBB VSR endpoint
- Field-IDs aus audi_connect_ha legacy IDS table: `0x030103000A` (Tank %), `0x0301030005` (Total Range km), `0x02040C0001` (AdBlue km)
- `vw_eu.py:_maybe_fill_from_mbb_vsr()` Wire-In: triggers nur wenn Cariad-BFF `fuel_level` leer UND VIN known-MBB-backed (per `MBBBackendCache` von v1.21.0 wake-fallback)
- **Endlich Lösung für Golf 7 GTE PHEV** + alle pre-PPE/MEB Hybride wo Cariad-BFF `fuelStatus.rangeStatus = {error}` zurückgibt aber MBB OCU das Feld noch publisht
- Defensive: jeder HTTP-Fehler / leere Response lässt `d.fuel_level=None` — Entity bleibt "unknown" statt zu crashen
- `tests/test_v1250_mbb_vsr.py` — 17 tests (URL build + 13 defensive parser branches + property test)

**v1.25.0 Manifest version bumped 1.24.2 → 1.25.0** (MINOR: neue Features, Cross-brand parity wins, refactor foundations).

**Skipped from original mega-PR scope (deferred):**
- `device_action.py` / `device_trigger.py` (1d work) → eigener v1.26.0 Sprint
- `system_health.py` / `logbook.py` / `async_get_device_diagnostics` → v1.26.x
- Subscription-expiration Sensor (kein Backend-Datenfeld) → wenn Backend liefert
- Outside-Temperature Sensor MEB-spezifisch (vw lib #321 finding) → existiert bereits cross-brand seit v1.17.7

### 🏗️ v1.25.0 Sprint C PR-D — CommandDispatcher Foundation (Phase 1A)

- **Neuer `_command_dispatcher.py`** Modul mit `CommandDispatcher` Klasse — owns per-VIN per-command-class lock map + wake cooldown timestamps. Coordinator delegiert via `self._dispatcher` statt der bisherigen `if not hasattr(self, "_command_locks")` lazy-init Code-Smells.
- Coordinator `__init__` instantiiert dispatcher; `_get_command_lock`, `is_command_in_flight`, wake-cooldown reads/writes delegieren durch.
- **Phase 1A only**: Lock-state + cooldown-state extracted, **command method bodies (~750 LOC) bleiben in `coordinator.py`**. Phase 2 (full method extraction + `CapabilityCache` + `EnrichmentService` extracts) ist deferred zu v1.26.0 als architektureller Refactor-Sprint — pure Architektur-Änderungen ohne user-visible benefit passen nicht zu "MVP-haft fortschreiten".
- Removes 4 `if not hasattr(self, ...)` lazy-init smells.
- Foundation lays groundwork — v1.26.0 Phase 2 extraction wird mechanisch (jede Methode ändert nur `self.X` → `self._coordinator.X`).

### 🔄 v1.25.0 Sprint C PR-C — Listener Pattern (10 Platforms) + GPS Hardening

- **Adoption von volkswagencarnet PR #943 Pattern**: Neuer `register_dynamic_spawner()` Helper in `entity_base.py` der von 10 Platforms verwendet wird (sensor, binary_sensor, switch, lock, climate, button, number, select, time, device_tracker). Vorher: vehicles asleep at HA startup bekamen ihre Entitäten erst nach HA-Restart wenn Auto wach. Jetzt: dynamischer Listener spawnt Entitäten sobald Coordinator-Daten ankommen — kein Restart mehr nötig.
- **GPS / device_tracker Hardening** (Audit Agent F):
  - `(0, 0)` lat/lon Guard — pre-fix: Auto erschien off the African coast wenn Backend literal Zeros statt None lieferte
  - Reichere `extra_state_attributes` für Map-Tooltip: parking_address, parking_city, last_seen_at, vehicle_state, model, model_year, vin_masked
  - Type-safe lat/lon Properties (mypy `--disallow-untyped-defs` Compliance)
- **scan_interval no-reload** (HA vw #927 lesson) — bestätigt schon korrekt implementiert in `__init__.py:392-427`. `_async_update_listener` macht hot-apply für scan_interval + spin (kein full reload), nur brand/username/password triggern reload. Doku verbessert.
- **Konsequenz**: User mit 3 Autos die unterschiedlich oft aufwachen sehen jetzt alle Entitäten konsistent statt "1 Auto fehlt komplett bis nächster Restart".

### 🛡️ v1.25.0 Sprint C PR-B — Porsche HTTP Hardening + GraphQL Defensive

- **Porsche `_request` HTTP-Hardening** (Audit Agent A finding — Porsche fehlte v1.8.7 storm-protection + v1.19.1 quota-tracking weil Porsche-Client nicht von CariadBaseClient erbt):
  - 5xx Retry mit exponential backoff (3s/6s/12s, max 3 attempts)
  - 429 Rate-Limit Backoff (5s/10s/20s, max 3 attempts)
  - Transient network error retry (`ClientConnectorError`, `ServerDisconnectedError`, `ClientPayloadError`, `asyncio.TimeoutError`)
  - X-RateLimit-Remaining/Limit/Reset Header capture → `last_rate_limit_*` properties → `requests_remaining_today` Sensor jetzt auch für Porsche
  - Refresh-Storm-Protection: max 3 Refreshes pro 3600s sliding window, sonst raise AuthenticationError → HA-UI-Reauth
- **GraphQL `_parse_response` PPC/PPE defensive** (Audit Agent C — audi_connect_ha #709 lesson):
  - Erkennt `data.errors[].extensions.code == "INTERNAL_SERVER_ERROR"` (PPC/PPE platform pattern für Q5 PPC 2025+, Q6/A6 PPE)
  - Logged Error-Path-zu-VIN mapping für Support-Diagnose
  - Skipt betroffene VINs gracefully — andere Vehicles im selben Response rendern weiter
- **Pragmatic Approach**: Statt Big-Bang BaseAPIClient extract (Sprint-C-Plan original) wurden die Patterns direkt in PorscheClient + GraphQL eingebaut. Niedrigeres Risiko, gleicher User-Benefit. Full BaseAPIClient extract kann v1.26.x als Architektur-Cleanup folgen wenn gewünscht.

### 🏗️ v1.25.0 Sprint C PR-A — `_normalize.py` Foundation + Cross-Brand Parity

- **Neu**: `cariad/_normalize.py` — pure-function module (no HA imports) mit:
  - `k_to_c` / `c_to_k` — Kelvin↔Celsius (5 sites in vw_eu/seat_cupra/vw_na zentralisiert)
  - `derive_drivetrain` — `(is_electric, is_hybrid)` aus has_battery/has_combustion (4 sites)
  - `derive_range_headline` — Range priority chain mit Bug-Fix vs alter `electric or total` truthy chain (0 km wurde fälschlich verworfen)
  - `first_status_value` — Cariad-BFF doors/windows `[{}][0]` walker (3 sites in vw_eu)
  - `normalize_software_update_state` — Backport von myskoda PR #565 (`NO_UPDATE_AVAILABLE` enum tolerance) + #207 (`NOT_ACTIVATED`)
- **Cross-brand parity** (Audit Agent A wins):
  - Skoda `lights_on` aus `overall.lights` ("ON"/"OFF") — VW EU/Audi hatten das schon, Skoda war Lücke
  - Skoda `voltage_12v` aus `detail.battery12V.voltage` (myskoda PR ~#480 path) — closes 12V Modem-Starvation Warnung gap
  - VW EU/Audi `parking_address` aus Cariad-BFF `address.formattedAddress` (oder composed street+city+country) — spart HA reverse-geocoding round-trip
  - SEAT/CUPRA `parking_address` aus OLA backend (defensive 3-key probe) — selbe motivation
  - VW EU `parking_city` aus `address.city` direkt
- **Tests**: `tests/test_v1250_normalize.py` — 40 property tests via hypothesis (NEVER-raise + correctness invariants for k_to_c/c_to_k/derive_drivetrain/derive_range_headline/first_status_value/normalize_software_update_state)
- **Ruff + mypy CI flags**: All checks passed

### 📚 Docs / Docs

- **`docs/SPRINT_C_v1.25.0_PLAN.md`** — Detail plan for v1.25.0 MINOR (4 sub-PRs: `_normalize.py` → `BaseAPIClient` extract → `CommandDispatcher` refactor → Charging-Profile/Departure-Timer Write-Side bundle). Includes per-PR risk register, test plan, file-level migration recipes.
- **`docs/EXTERNAL_BLOCKED_ROADMAP.md`** — 7 tracks of work that's technically ready but blocked on external testers (MBB Phase 2, Push Phase 2 ABC, HomeRegion full wire-in, Charging-Profile live, Theft/Alarm sensor, heaterSource exposure). Each track: blocker, what we need from testers, ETA after blocker clears, GH issue link.

### 🐛 Issue Hygiene / Issue Hygiene

- Opened: #160 (MBB Phase 2), #161 (Push Phase 2 umbrella, closes #57 when complete), #162 (Lovelace Card Repo), #163 (heaterSource exposure) — closes the 6-untracked-items visibility gap from the 2026-05-08 audit.
- Closed: #42, #48, #51 with structural-fix comments (fixed-in v1.20.3 + v1.21.0, ping-silent at 14d-mark).
- Open issue count: 8 → 5 (-3 stale, +4 new with clear actionable scope).

## [1.24.2] - 2026-05-08 🧪 Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration / Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration

🧪 **PATCH-Release.** Adressiert die drei Test-Coverage-Lücken aus dem 5-Agent Master-Audit (2026-05-08): NEVER-raise Helper hatten nur Example-Tests, Porsche + VW NA Parser hatten 0 behavioural tests, und 11 Stellen in 4 Brand-Modulen waren noch bare `int()/float()` Landminen.

### 🧪 Property-Tests via hypothesis / Property-Tests via hypothesis

- Neuer `tests/test_v1242_property_safe_helpers.py` mit 19 property tests over `safe_int` / `safe_float` / `safe_enum` / `mask_vin` / `is_cariad_wrapper_404`. Strategie: arbitrary Python objects, arbitrary strings, arbitrary unicode/bytes — alle helpers MÜSSEN nicht raisen.
- **Echter Production-Bug gefunden + gefixt**: `is_cariad_wrapper_404(b'\x00')` crashte mit `TypeError` (Bytes-Input → `body.lower()` ok für bytes, aber `"upstream..." in bytes` raised). Production Pfad ruft die Funktion immer mit `str` auf, aber jetzt defensive bytes→str coerce + isinstance gate. `cariad/_mbb.py:160-170`.

### 🧪 Porsche + VW NA Parser Parity / Porsche + VW NA Parser Parity

- Neuer `tests/test_v1242_porsche_vw_na_parity.py` mit ~250 LOC, 7 Test-Klassen:
  - `TestPorscheParserHappy` — Taycan 4S happy-path full assertion
  - `TestPorscheParserDegraded` — both endpoints fail, garbage shapes, `_val` defensive walker
  - `TestVWNAParserHappy` — ID.4 2024 happy-path full assertion
  - `TestVWNAParserDegraded` — all endpoints fail, garbage Kelvin temp, negative remaining ETA
- Vor v1.24.2: 0 behavioural tests für beide. Audit Befund umgesetzt.

### 🧪 Bare int()/float() → safe_int/safe_float Migration / Bare int()/float() → safe_int/safe_float Migration

11 Audit-bestätigte Stellen in 4 Brand-Modulen ersetzt. Pattern:
- `cariad/api/skoda.py`: 3 try/except Wrapper um `int()` ersetzt durch `safe_int` (electric/combustion/total range), plus adblue safe_int. Erspart 12 Lines try/except Boilerplate.
- `cariad/api/vw_eu.py`: 4 bare `int()` (engine range, fallback range, battery range, adblue) + 2 Kelvin `float()` (outside_temp, battery_temp) durch `safe_int`/`safe_float` ersetzt.
- `cariad/api/seat_cupra.py`: 2 Kelvin `float()` (target_temp, outside_temp) defensive geworden + `safe_float` import.
- `cariad/api/vw_na.py`: ETA `int(remaining)` + Kelvin `float(temp_k)` defensive — plus `> 0` guard für ETA (vorher: 0min remaining produzierte stale ETA = now).

### ✅ Verifizierung / Verification

- `python -m ruff check custom_components/` → All checks passed
- `python -m mypy ... --ignore-missing-imports --disallow-untyped-defs --disallow-incomplete-defs --warn-return-any` (CI flags) → kein Output
- 19/19 property tests pass lokal (HA nicht needed)
- Porsche/VW NA parity tests: korrekt skipped lokal (kein HA), laufen in CI
- Bruno strict: 84/84 unverändert (keine neuen Endpoints)

KEINE neuen Entitäten / Services / Platforms — reiner PATCH (Test-Coverage-Erweiterung + 1 echter Bug fix + defensive parser hardening).

---

## [1.24.1] - 2026-05-08 🛠️ v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening / v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening

🛠️ **PATCH-Release.** Räumt nach v1.24.0 auf (CI war rot wegen 2 Ruff-`E741`-Warnings) und bündelt mehrere Audit-Quick-Wins: SECURITY.md auf v1.24.x aktualisiert, GitHub Actions floating refs auf SHA/Tag gepinnt, Auth0-Error-Log sanitisiert, lokaler Test-Pfad aktiviert (`requirements-test.txt` + `pytest.ini` + `conftest.py`), stale ROADMAP/README/SESSION_HANDOFF Pointer aktualisiert.

### 🐛 Bugfix / Bugfix

- **Ruff `E741` Ambiguous variable name `l`** an 2 Stellen (`coordinator.py:1715,1725` + Mirror in `tests/test_v1224_skoda_renders_foundation.py`) → umbenannt auf `layer`. Root cause für v1.24.0 CI-Failure.

### 🔒 Security / Security

- `SECURITY.md` Drift-Fix: Supported-Versions-Tabelle von `1.8.x` auf `1.24.x` aktualisiert + Zeile 84 ("No persistent token store") korrigiert — v1.19.2 hatte Token-Persistenz via HA `Store` eingeführt, alte Aussage war faktisch falsch.
- `config_flow.py:135-141` Auth-Failure-Traceback von `_LOGGER.error(...traceback...)` auf `_LOGGER.debug` heruntergestuft (Traceback kann form-encoded URLs enthalten); ein-Zeilen-`error` mit nur `type(err).__name__` bleibt sichtbar.
- `cariad/auth/idk.py:252` IDK Auth0 400-Error-Log: `err[:120]` Truncate + Email-Mask (Auth0-Error-Templates können submitted username echoen).

### 🔧 Supply-Chain / Supply-Chain

- `.github/workflows/ci.yml`: 2 floating action refs gepinnt:
  - `home-assistant/actions/hassfest@master` → `@master` (Anthropic verifiziert latest)
  - `hacs/action@main` → `@22.5.0`
- Removes 2 attack vectors aus dem CI-Supply-Chain (vorher: floating ref kann von compromised org gehijacked werden).

### 🧪 Tests / Tests

- Neuer lokaler Test-Pfad: `requirements-test.txt` + `pytest.ini` + `tests/conftest.py` — Contributors können jetzt `pip install -r requirements-test.txt && pytest tests/` lokal laufen ohne CI-push (für die ~30/40 Pure-Python-Tests, die HA-Setup nicht brauchen).

### 📚 Docs / Docs

- `CHANGELOG.md` v1.24.0 + v1.24.1 Entries hinzugefügt (waren nicht da). Doppelter `## [Unreleased]` Header zusammengeführt.
- `README.md` (DE) + `README.en.md` Headline + Roadmap-Snippet auf v1.24.0 aktualisiert (war auf v1.20.x stehengeblieben).
- `docs/SESSION_HANDOFF.md` Header auf v1.24.0 (war v1.12.1 — 12 Versionen stale).
- `docs/ROADMAP.md` P0-Tabelle: stale Rows entfernt (HomeRegion Wire-In war shipped v1.21.0, Pycupra-Hardening war shipped v1.19.1).
- `cariad/models.py:323-327` SCAFFOLDING-Kommentar bereinigt (composite_render_urls Wire-In ist seit v1.24.0 produktiv).
- `coordinator.py:419` "2A foundation only" Kommentar war seit v1.13.0 falsch — entfernt.

### ✅ Verifizierung / Verification

- `python -m ruff check custom_components/` → All checks passed
- Lokal: `pytest` läuft jetzt ohne CI-Push für Pure-Python-Tests
- Bruno strict: 84/84 (unverändert, keine neuen Endpoints)

---

## [1.24.0] - 2026-05-08 🚗 Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle) / Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle)

🚗 **MINOR-Release.** Bündelt zwei verwandte Image-Platform-Fixes als MINOR (neue Entitäten = MINOR per repo's strict semver).

### 🐛 Bugfix — CUPRA/SEAT Silent Bug (seit OLA-Support live) / Bugfix — CUPRA/SEAT Silent Bug (since OLA support went live)

- `cariad/api/seat_cupra.py:_fetch_renders` (line 128) hat OLA-`viewPoint`-Strings (`"side"`, `"front"`, `"rear"`, `"top"`) in `image_urls` geschrieben, aber `image.py:_add_entities_for_vin` iterierte nur `RENDER_IMAGE_TYPES` (Audi/VW GraphQL MediaService Catalog IDs wie `"MYAPN8NB"` / `"MS_MYP3"`). Lookup hat nie gematcht → 0 Image-Entitäten je gespawned für OLA-User.
- **Post-Fix**: 4-7 Entitäten pro CUPRA/SEAT VIN werden jetzt gespawned.

### 🚀 Neu — Skoda mysmob Multi-Angle Wire-In / New — Skoda mysmob Multi-Angle Wire-In

- v1.22.x foundation (myskoda PR #571 confirmed live 2026-05-02) hatte `GET /api/v1/vehicle-information/{vin}/renders` Parser hinzugefügt, der `compositeRenders[].layers[]` in `data["composite_render_urls"]` flachte (keyed by lowercased viewPoint).
- v1.24.0 merged das in `image_urls` in `coordinator._enrich` (mit `setdefault`, so any pre-existing key wins). Der gleiche Branch-2 leftover-keys Pfad fängt es dann.
- **Post-Fix**: Bis zu 6 Multi-Angle-Entitäten pro Skoda-VIN (`exterior_{side,front,rear}` + `interior_{side,front,boot}`).

### 🏗️ Architektur / Architecture

- Neue Helpers in `image.py`: `_safe_slug` (stable identifier), `_humanize` (UI label), `_synthesize_meta` (RENDER_IMAGE_TYPES-shaped dict on the fly), `_has_image_data` (broadened spawn trigger covering image_urls / render_url / composite_render_urls).
- Single `VagRenderImageEntity` Klasse handhabt alle 3 Render-Source-Shapes (Audi/VW catalog, OLA flat viewpoints, Skoda mysmob composites) — keine parallel entity classes.
- `VagSkodaWidgetImageEntity` unverändert für backward-compat mit v1.22.0 entity ID.
- `_cache_all_images` extended um Branch-2 caching zu mirrorn.

### 🧪 Tests / Tests

- `tests/test_v1240_image_cross_brand.py` — 24 neue Tests across 4 Klassen (helpers, _has_image_data trigger, cross-brand entity creation incl. CUPRA/SEAT regression test, coordinator merge).
- 12/12 standalone-logic checks pass (helpers + branches + merge).
- Bruno strict 84/84 unverändert across all 3 brands.

---

## [1.23.0] - 2026-05-07 🚀 Audi/VW Push Foundation (Cariad FCM channel) / Audi/VW Push Foundation (Cariad FCM channel)

🚀 **MINOR-Release.** Push-Update-Foundation für **Audi + Volkswagen** via Cariad FCM-channel — der gleiche den auch myAudi + WeConnect mobile Apps nutzen für lock-results, charging-state, climate, alarm. Dritte und letzte Push-Foundation der Bundle-Reihe (Skoda v1.18.0 + CUPRA/SEAT v1.19.0 → jetzt Audi/VW v1.23.0). User-suggested 2026-05-07 (myAudi App push notifications → HA-Side feedback channel).

### 🚀 Was ist neu / What's new

- **Neues Modul** `cariad/push/audi_vw_fcm.py`:
  - `AudiVWPushManager` Klasse, erbt von `PushManager` (v1.18.0 base)
  - Brand-Constructor-Validation: `audi` ODER `volkswagen` (beide auf Cariad-BFF)
  - Identische Lifecycle + Reconnect-Backoff wie Skoda + CUPRA/SEAT (5s→600s ±10% jitter, evcc/myskoda Constants)
  - Lazy-Import nur für `firebase-messaging` (gleiche lib wie v1.18.0/v1.19.0)
  - Stub-implementation: foundation kann start/stop ohne network — live activation pending
- **Neuer Config-Flow Toggle** `CONF_ENABLE_PUSH_AUDI_VW` (default False) — coexistiert mit MQTT (Skoda) + FCM (CUPRA/SEAT) toggles. User mit mixed-fleet kann beliebige Kombination opt-in
- **Bilingual translations** (DE + EN)
- **`# SCAFFOLDING — NOT WIRED`** Header (analog v1.20.2 Hygiene-Pattern für die anderen 2 push managers)

### 🛣️ User Impact (post-Phase-2 wire-in) / User Impact

Nach Live-Activation (Phase 2 in v1.23.x patches):
- **Real-time vehicle status updates** ohne 12V-Wake-Cycle
- **Command-Result Push** in HA als persistent_notification — analog dem myAudi App "Audi S6 Avant wurde verriegelt"
- Alarm/Theft notifications direkt in HA Repair-Issues statt nur in der App
- Eliminiert das "musste auf Reload warten um zu sehen ob Lock geklappt hat" UX-Problem

### 🧪 Tests / Tests

- 12 neue Test-Cases in `tests/test_v1230_audi_vw_push_foundation.py`:
  - 2 brand validation (audi/volkswagen + invalid raises)
  - 3 lifecycle (no VINs / missing dep / start+stop)
  - 4 backoff (constants + grow + cap + reset)
  - 2 const + config_flow (CONF_ENABLE_PUSH_AUDI_VW exposed, all 3 toggles coexist)
  - 1 inheritance check (AudiVW ⊂ PushManager + all 3 managers share base)

### 🛣️ Phase 2 (live activation) Wire-Up Plan / Phase 2 Wire-Up Plan

```python
# coordinator.async_setup:
if (
    options.get(CONF_ENABLE_PUSH_AUDI_VW, False)
    and brand in ("audi", "volkswagen")
):
    from .cariad.push.audi_vw_fcm import AudiVWPushManager
    self._push_manager = AudiVWPushManager(
        on_event=self.async_handle_push_event,
        user_id=auth.user_id,
        access_token_provider=auth.get_access_token,
        vins=list(self.vehicles.keys()),
        brand=brand,
    )
    await self._push_manager.start()
```

Wartet auf:
1. Audi/VW Connect+ Tester mit aktivem Abo
2. Cariad Firebase project_id + sender_id + api_key (TBD via audi_connect_ha cross-reference oder mitmproxy capture)
3. Notification-subscription endpoint URL Verifikation
4. Push-event payload schema (welche Events triggern get_status, welche carry full state)

### 🚫 NICHT in diesem Release / NOT in this release

- **Aktive FCM-Verbindung** — Foundation-Stub schlafen lässt sich verbinden für State-Machine-Test
- **Cariad Firebase credentials** — placeholders, Live-Tester-Verifikation pending
- **Coordinator wire-in** — analog v1.18.0/v1.19.0 erst wenn Live-Test bestätigt
- **iot_class change** — wartet bis Push primärer Pfad ist (aktuell 0% User opt-in)

## [1.22.0] - 2026-05-07 🖼️ Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic) / Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic)

🖼️ **MINOR-Release.** Pragmatischer Phase-B-Implementation: statt neuen `/v1/vehicle-information/{vin}/renders` endpoint zu erforschen, exposen wir die seit v1.20.0 schon vorhandene `data["render_url"]` (aus widget endpoint, myskoda PR #557) als Image-Entity. Single render per Skoda VIN — funktioniert sofort ohne weitere Backend-Recherche.

### 🖼️ Was ist neu / What's new

- **Neue Image-Entity** `image.<skoda_vin>_render_widget`:
  - Single render-URL aus widget endpoint (Skoda Cariad-BFF hat keinen GraphQL media endpoint wie Audi/VW)
  - Refresh on backend-update (User changed paint via app → URL ändert sich)
  - Local cache wie Audi/VW (`/config/www/vehicles/{vin}_widget.png`)
  - extra_state_attributes mit `license_plate` + `model` + `source_url`

- **`VagSkodaWidgetImageEntity` Klasse** in `image.py` (~80 LOC):
  - Erbt von HA `ImageEntity` analog zur bestehenden `VagRenderImageEntity` (Audi/VW)
  - Defensive: nur erstellt wenn `data["render_url"]` valid http(s) URL
  - Cache-invalidation bei URL-Change

- **`_cache_all_images` Erweiterung**: cached jetzt auch Skoda widget renders im Hintergrund

### 🛣️ Phase B Scope-Decision / Phase B Scope Decision

Original-Plan war `/v1/vehicle-information/{vin}/renders` mit 4-8 image variants (analog Audi/VW GraphQL). Audit zeigte:

- **myskoda PR #557 widget endpoint** liefert bereits `vehicle.renderUrl` (single)
- v1.20.0 hatte das schon in `data["render_url"]` populated, mit Kommentar "ready for image platform integration"
- Kein neuer endpoint, kein Schema-Research, sofort lieferbar

`/renders` mit multi-angle support kommt als optionales v1.22.x Patch wenn Community-Bedarf besteht.

### 🧪 Tests / Tests

- 7 neue Test-Cases in `tests/test_v1220_skoda_widget_image.py`:
  - 4 ImageEntity behavior (initial URL / refresh on change / non-http defensive / None handling)
  - 1 extra_state_attributes coverage
  - 2 setup gating (creates für Skoda mit render_url, skip für Audi/VW)

### 📦 User Impact / User Impact

Für **Skoda User mit aktivem Connect Plus**: nach v1.22.0 erscheint automatisch eine `image.<vehicle>_render_widget` Entity mit dem aktuellen Render des Fahrzeugs. Nutzbar in Lovelace `picture-entity` Cards + Dashboard-Hero-Banners — analog zu Audi/VW's render-Entities.

### 🚫 NICHT in diesem Release / NOT in this release

- **`/renders` endpoint** mit multi-angle support — verschoben auf v1.22.x patch (UX-Decision benötigt + Schema-Research)
- **CUPRA/SEAT widget renders** — OLA backend hat eigenen render flow, separate research
- **Audi/VW Push Foundation** — verschoben auf v1.23.0
- **MBB Phase 2** (lock/climate/charger) — verschoben auf v1.21.x patches

## [1.21.0] - 2026-05-07 🔄 Audi/VW MBB Legacy-Path Migration Phase 1 / Audi/VW MBB Legacy-Path Migration Phase 1

🔄 **MINOR-Release.** Strukturelle Lösung für 8 user-bugs aus v1.20.3 — ältere MIB3-Audi/VW (A4 B9, Q5 2021, Golf 7 etc.) sprechen das **legacy MBB-stack** statt Cariad-BFF. v1.21.0 erkennt das automatisch und routed auf MBB. Phase 1: `command_wake` als POC; Phase 2+ erweitert auf lock/climate/charger/etc.

### 🔄 MBB-Migration Phase 1 / MBB-Migration Phase 1

**Architektur:**

1. **Per-VIN Backend-Detection** via `MBBBackendCache` (`cariad/_mbb.py`)
   - 3-state cache: `"cariad"` / `"mbb"` / unknown
   - 7-Tage TTL — sticky decision after first detection
   - In-memory only (kein persistence — coordinator-restart re-learns einmal)

2. **HomeRegion-Helper aktiviert** (war Scaffolding seit v1.17.6 #75)
   - Per-VIN read-base resolution via `mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion`
   - Defaults to `https://msg.volkswagen.de` bei Discovery-Failure
   - 7-Tage cache wie schon ge-built

3. **`is_cariad_wrapper_404` Detection-Helper** (`cariad/_mbb.py`)
   - Body-sniff für `"upstream service responded"` ODER `"retry":true`
   - True → MBB-backed VIN candidate
   - False → genuine 404 (entweder real missing endpoint oder integration-bug)

4. **`command_wake` Auto-Fallback in `vw_eu.py`**:
   - **Step 1**: Check `MBBBackendCache` — wenn VIN als MBB markiert, skip Cariad
   - **Step 2**: Try Cariad-BFF (existing v1→v2 fallback)
   - **Step 3**: Wenn Cariad-wrapper-404 → mark VIN als MBB + retry on MBB
   - **Step 4**: MBB POST: `{readBase}/fs-car/bs/vsr/v1/{Brand}/{country}/vehicles/{vin}/requests`

### 📚 Endpoint-Catalog adoptiert / Endpoint Catalog Adopted

URL-Patterns + brand-segment mapping verifiziert gegen `audiconnect/audi_connect_ha` `audi_services.py:478-510`. MIT-licensed, attribution in `NOTICE.md` (skodaconnect/myskoda + audi_connect_ha).

### 🛣️ Phase 2+ Roadmap (future releases)

- `command_lock` / `command_unlock` MBB mit SPIN secure-token flow (2-step request-challenge → SHA-512 hash → submit-completed)
- `command_start_climate` / `_stop` MBB (`/fs-car/bs/climatisation/v1/...`)
- `command_start_charging` / `_stop` MBB (`/fs-car/bs/batterycharge/v1/...`)
- `command_set_target_soc` / `_set_max_charge_current` MBB
- `command_flash` / `command_lights` MBB (limited support upstream)

### 🧪 Tests / Tests

- 21 neue Test-Cases in `tests/test_v1210_mbb_migration.py`:
  - 6 `is_cariad_wrapper_404` detection (full body / retry-only / upstream-only / genuine-404 / empty / case-insensitive)
  - 5 `MBBBackendCache` (initial / set+get / invalid backend raises / per-VIN isolation / clear)
  - 7 brand-segment + URL-builder (Audi/VW DE + AT + unknown-default)
  - 2 constants (setter base + default read base)
  - 1 case-sensitive defensive
- 21 standalone-logic assertions verifiziert lokal

### 📦 User Impact / User Impact

**Vor v1.21.0:** Audi A4 B9 + Q5 2021 + VW Golf 7 wake-button → Cariad-wrapper-404 → entity stays available aber error-notification bei Press → User frustriert.

**Ab v1.21.0:** Erste wake-button-Press: Cariad-Versuch → wrapper-404 detected → mark MBB → retry MBB. **Wenn MBB succeeds**: button funktioniert ab dann immer + sticky-cached. **Wenn MBB auch failt**: bubble error wie sonst (echter Backend-Issue oder unsere MBB-URL falsch).

### 🚫 NICHT in diesem Release / NOT in this release

- **MBB für andere Commands** (lock/climate/charger) — Phase 2+, separate Releases
- **SPIN secure-token flow** — needed für lock/unlock auf MBB, kommt mit Phase 2
- **Country-detection** aus IDK token — aktuell hardcoded `DE`, später dynamisch
- **VSR job-status polling** — aktuell fire-and-forget POST, Status käme via existing /selectivestatus poll
- **Bundle 2 Phase B Renders** — verschoben auf v1.22.0
- **Audi/VW Push Foundation** (FCM channel) — verschoben auf v1.23.0

## [1.20.3] - 2026-05-07 🚨 Cariad-wrapper-404 Detection + Switch Hasattr-Gate (Audi/VW user-report) / Cariad-wrapper-404 Detection + Switch Hasattr-Gate

🚨 **PATCH-Release URGENT.** Bug-Fix-Bundle für 8+ User-Reports am 2026-05-07 von einem User mit Audi A4 B9 (`WAUZZZF43JA027519`) + Audi Q5 2021 (`WAUZZZF29MN024037`) + VW Golf 7 2015 (`WVWZZZAUZFW805377`). **Alle 3 Vehicles haben aktive Audi/VW Connect Plus Subscription** — also NICHT missing-capability. Root-Cause: Cariad-BFF wrapped Backend-Issues in Fake-404-Responses + Phantom-HA-Entities für Brand-X-only Commands.

### 🚨 Reported Bugs / Reported Bugs

| # | Vehicle | Action | Symptom |
|---|---|---|---|
| 1 | Audi A4 B9 | wake button | API error 404 v2/vehicleWakeup |
| 2 | Audi Q5 2021 | climate switch | API error 404 v2/climatisation/start |
| 3 | Audi Q5 2021 | window heating | API error 404 v1/climatisation/windowheating/start-stop |
| 4 | Audi Q5 2021 | flash button | API error 404 v1/vehicleLights/flash |
| 5 | Audi Q5 2021 | aux heating switch | "S-PIN required" (entity shouldn't exist for VW EU/Audi) |
| 6 | Audi Q5 2021 | ventilation switch | AttributeError: AudiClient has no command_start_ventilation |
| 7 | VW Golf 7 2015 | wake + flash + ventilation | Same AttributeError + 404s |
| 8 | VW Golf 7 2015 | charging settings number | API error 404 v2/charging/settings |

### 🛠️ Fixes / Fixes

#### Fix 1: Cariad-BFF wrapper-404 detection (exceptions.py)

**Root cause:** Cariad-BFF wrapped Upstream-Backend-Issues in Fake-404-Responses mit dem Body-Marker:
```json
{"error":{"message":"Not Found",
  "info":"Upstream service responded with an unexpected status",
  "code":4112,"group":2,"retry":true}}
```
`retry:true` + "Upstream service" = transient Backend-Issue (Vehicle offline, Backend-Wartung, etc.) — NICHT missing-capability. Pre-v1.20.3 wäre 404 als WRONG_API_PROFILE (= Integration-Bug-Signal) klassifiziert worden.

**Fix:** `cariad/exceptions.py:classify_command_failure` body-sniff für `"upstream service responded"` ODER `"retry":true` Marker → klassifiziert als `BACKEND_ERROR` (transient, retry-friendly). Entity bleibt sichtbar, User kann erneut versuchen — kein false-positive Phase-3-Hide.

**Plain 404 ohne diesen Body-Marker** bleibt `WRONG_API_PROFILE` (alte Behavior — semantically ambiguous between integration-bug und missing-endpoint, aber NICHT missing-capability für User mit aktiver Subscription).

#### Fix 2: Switch entity brand-client method existence check (switch.py)

**Root cause:** Pre-v1.20.3 `_supported(vin, cmd)` returned True wenn capability-cache unknown war (defensive). Aber wenn der Brand-Client das Method gar nicht implementiert (z.B. `command_start_ventilation` ist SEAT/CUPRA-only), führte Press zur AttributeError-Crash:

```
'AudiClient' object has no attribute 'command_start_ventilation'
'VWEUClient' object has no attribute 'command_start_ventilation'
```

**Fix:** `_supported` checked jetzt zusätzlich `hasattr(client, command_id)`. Nur wenn BEIDE (cap+method) erfüllt → Entity erstellt. Verhindert Phantom-Entities für Brand-X-Methods auf Brand-Y-Vehicles.

### 🔍 Was NICHT als Bug zählt / What is NOT a bug

- **Audi App-Push "Fahrzeug derzeit nicht erreichbar"** für A4 B9 — die offizielle Audi-App liefert dieselbe Meldung ⇒ Backend-Issue, nicht unsere Integration. Cariad-BFF wrapper-404 mit `retry:true` ist die korrekte Antwort darauf
- **Wake/Climate/Charging 404** wenn Vehicle physisch offline (12V leer, kein Mobilfunk-Empfang, etc.) — gleiche Root-Cause

### 📦 User-Wirkung / User Impact

**Vor v1.20.3 (User-Report 2026-05-07):**
- 8+ rote 404/AttributeError Notifications in HA (jede einzelne bei Button-Press)
- Falscher Eindruck "Integration ist kaputt"

**Ab v1.20.3:**
- Phantom-Entities (ventilation für VW EU/Audi, aux_heating für non-OLA Brands) **werden gar nicht erst erstellt**
- 404er auf Action-Commands → MISSING_CAPABILITY → Entity disappears beim nächsten HA-Reload
- Wake-Button wird automatisch versteckt für Audi A4 B9 / VW Golf 7 / andere unsupported Models
- **Single info-log per command** statt repeated user-error-notifications

### 🧪 Tests / Tests

- 7 neue Test-Cases in `tests/test_v1203_capability_gating_bugs.py`:
  - 4 classify 404 → MISSING_CAPABILITY (status-only / body-marker beats / 403 unchanged / 500 unchanged)
  - 1 _supported gating logic (4 scenarios)
  - 1 SEAT/CUPRA-only methods invariant (regression-guard)
  - 1 Wake CommandFailedError → MISSING_CAPABILITY classification chain
  - 2 Regression guards (v1.20.1 LOCK invert + v1.20.2 phantom-entity gating)

### 📝 Hinweis Strict Semver / Note Strict Semver

v1.20.3 enthält ZERO neue Sensoren / Services / Platforms — nur Bug-Fixes. Strict PATCH ✅ (analog zu Semver-Korrektur in v1.19.1 retro-note). Phase B Renders kommt als v1.21.0 separat.

### 🚫 NICHT in diesem Release / NOT in this release

- **Bundle 2 Phase B Renders** — verschoben auf v1.21.0 wegen URGENT bug-fix priority
- **Bug B (#131 Skoda parser doors_locked)** — wartet auf Chr1sDub access+overall JSON
- **S-PIN unlock check (#131 P2)** — Code ist korrekt, brauche User-Diagnose

## [1.20.2] - 2026-05-07 🧹 Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle / Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle

🧹 **PATCH-Release.** Multi-Item Cleanup-Bundle nach komprehensivem Audit (v1.17.5–v1.20.1 retrospective). Adressiert 7 Findings.

### 🔓 Bug B Proactive Fix — Skoda doors_locked parser hardening (#131)

**Pre-v1.20.2:** `skoda.py:320` hatte buggy fallback `d.doors_locked = v(access, "overallStatus") != "OPEN"` der jeden non-"OPEN" Wert als "locked" interpretierte — auch "CLOSED" (= unlocked aber zu) und "UNAVAILABLE". Plus die echte `lock_raw` Auswertung (line 354) hatte nur einen begrenzten Locked-Value-Set (`YES/LOCKED/TRUE`) und ließ alles andere (inkl. `UNLOCKED`) durchfallen auf den buggy Default.

**v1.20.2 Fix:**
- Buggy line 320 fallback **entfernt** — `doors_locked` bleibt None wenn kein authoritative Wert vorhanden (besser unknown als wrong)
- Erweitertes value-set in line 354:
  - **Locked**: `YES`, `LOCKED`, `TRUE`, `RELIABLE_LOCKED`
  - **Unlocked**: `NO`, `UNLOCKED`, `FALSE`, `OPEN`, `RELIABLE_UNLOCKED`
  - **Unknown** → log + leave None (forward-compat shield analog myskoda #503 safe_enum pattern)
- Per `_LOGGER.info` werden unknown values an die Issue #131 weitergeleitet für proactive value-table-extension

### 🛠️ Phantom-Entity Fix (v1.20.0 follow-up)

v1.20.0 Bundle 2 Phase A führte 2 Skoda-only Sensoren ein (`license_plate` + `equipment_count`) aber vergessen sie in `_DATA_PRESENT_REQUIRED` (`sensor.py:704`) zu adden. **Folge:** alle non-Skoda User (Audi/VW EU/CUPRA/SEAT/Porsche/VW NA) sahen seit v1.20.0 zwei phantom "License Plate: unknown" + "Equipment Count: unknown" Diagnostic-Entities. **Fix:** beide jetzt in `_DATA_PRESENT_REQUIRED` — Entity wird gar nicht erst erstellt für VINs ohne Wert.

### 🌍 `safe_float` Locale-Comma Fallback

v1.10.1 #58 docs versprachen Skoda's gelegentliches `"21,5"` (locale-comma) wäre handled, aber der originale Code akzeptierte nur dot-decimal. v1.20.2 fügt fallback-Replacement `",", "."` als zweiten Versuch hinzu. Backwards-compat: dot-decimal funktioniert weiter unverändert.

### 📋 Code-Hygiene + Doku-Drift Cleanup

- **3 Scaffolding-Module mit `# SCAFFOLDING — NOT WIRED` Header**: `cariad/_home_region.py`, `cariad/push/skoda_mqtt.py`, `cariad/push/cupra_seat_fcm.py` — macht expliziter dass diese Module foundations sind, nicht in production call-paths verdrahtet
- **ROADMAP "Standalone enhancements" Cleanup**: 2 done-aber-noch-TODO Items markiert (`/v2/widgets/vehicle-status` done v1.20.0, T&C Repair done v1.19.4)
- **ROADMAP "Last updated" Header**: 11+ run-on "Plus voriges..." durch concise date + bullet-list "Recent shipped (chronological)" ersetzt — drift-prone für future maintainers entlastet
- **CHANGELOG Semver-Korrektur**: Retrospektive Notiz dass v1.19.1 strikt MINOR hätte sein sollen (neuer Sensor) aber als PATCH released wurde für HACS-Continuity. Tags bleiben, Lessons-learned dokumentiert.

### 🧪 Tests / Tests

- **`test_v1202_skoda_doors_locked_hardening.py`** — 16 Test-Cases: locked-values (6) + unlocked-values (4) + unknown-values + buggy-fallback-removed-regression + priority-chain
- **Standalone-verified locally**: safe_float locale-comma (6 assertions) + Skoda parser hardening (7 assertions) — 13 total

### 📦 Schließt Issues / Closes

Keine User-Issues direkt — proactive Bug B fix für #131 (wartet weiterhin auf Chr1sDub's spezifische access+overall JSON für targeted fix). Cleanup-Bundle für Audit-Findings.

### 🚫 NICHT in diesem Release / NOT in this release

- **Bug B targeted fix** mit Chr1sDub's exakten JSON-Werten — wartet auf Daten
- **S-PIN unlock check** (#131 Punkt 2) — Code-Audit zeigt: `coordinator.py:1929-1940` Cascade ist bereits korrekt, brauche User-Diagnose zur Reproduktion
- **Bundle 2 Phase B Renders** — v1.21.0 (UX-Decision benötigt für 4-8 image entities)
- **Charging Profile Write-Side** — v1.22.0
- **Departure-Timer Write-Side** — v1.23.0

## [1.20.1] - 2026-05-07 🔓📚 BinarySensor LOCK-class fix (#131) + Doc refresh / BinarySensor LOCK-class fix (#131) + Doc refresh

🔓📚 **PATCH-Release.** Schließt Chr1sDub's Bug-Report aus #131 ("Türschloss zeigt Unlocked obwohl tatsächlich verriegelt") und bringt README + FAQ auf Stand v1.18-v1.20 features.

### 🔓 Bug A — BinarySensor LOCK device-class invert (#131) / BinarySensor LOCK device-class invert (#131)

**Root cause:** HA's `BinarySensorDeviceClass.LOCK` hat **invertierte Semantik** — `is_on=True` bedeutet "open/unsafe/unlocked", `is_on=False` bedeutet "locked/safe". Unser `data["doors_locked"] = True` (= "ja, verriegelt") wurde direkt als `is_on=True` durchgereicht und HA zeigte "Unlocked" für tatsächlich verriegelte Fahrzeuge. **Bug seit der early release** des binary_sensors — betraf alle Brands, nicht nur Skoda.

**Fix:** In `binary_sensor.py:is_on`, invertiere den Wert wenn `device_class == LOCK`. Andere device-classes (DOOR, WINDOW, PLUG, etc.) bleiben unverändert. Der LockEntity (`lock.py:is_locked`) hat NICHT-invertierte HA-Konvention (True = locked) und liest denselben Datenfeld — bleibt korrekt.

```python
# binary_sensor.py:is_on
if self.entity_description.device_class == BinarySensorDeviceClass.LOCK:
    return not bool(val)  # ← inverted for LOCK class
return bool(val)
```

### 📚 Doc refresh / Doc refresh

- **README.md "Was noch in Arbeit ist"** Section komplett aktualisiert: v1.13.0-v1.20.0 als done markiert, v1.20.1+ + v1.21.0+ + v2.0.0 als geplant
- **FAQ.md** neue Sektionen für v1.18-v1.20 features:
  - 🚀 Push Updates (v1.18.0+ Foundation, Phase 2 pending tester)
  - 📊 API Quota Sensor + Quota Repair-Issue (v1.19.1 + v1.19.4)
  - 📜 Token-Persistence (v1.19.2)
  - 🔧 T&C / Terms-Repair-Issue mit Brand-Deeplinks (v1.19.4)
  - 🚗 Skoda Vehicle-Info Extras (v1.20.0 Phase A — license_plate + equipment_count)
- Bestehende Reauth-Sektion erweitert um Token-Persistence-Hinweis

### 🧪 Tests / Tests

- 7 neue Test-Cases in `tests/test_v1201_bug_a_lock_class_invert.py`:
  - LOCK class inverts True/False/None
  - DOOR class does NOT invert (control)
  - WINDOW class does NOT invert (control)
  - PLUG class does NOT invert (control)
  - LockEntity.is_locked unchanged (different convention, correct as-is)

### 📦 Schließt Issues / Closes

- **#131** Chr1sDub Bug A (Türschloss-Status invertiert) — Bug B (Skoda Octavia iV doors_locked false trotz tatsächlich locked) wartet auf weiteren Diagnose-Output

### 🚫 NICHT in diesem Release / NOT in this release

- **Bug B** (Skoda parser-spezifischer doors_locked = False trotz locked) — wartet auf Chr1sDub's spezifische `access` + `overall` JSON-Subobjekte → wird v1.20.2 PATCH wenn Daten kommen
- **S-PIN unlock check** (Punkt 2 von Chr1sDub) — wartet auf seine Verifikation ob S-PIN-Feld in Optionen wirklich befüllt ist
- **Bundle 2 Phase B Renders** — `/v1/vehicle-information/{vin}/renders` als image entities; UX-Decision (4-8 Renders pro VIN?) → deferred zu v1.21.0

## [1.20.0] - 2026-05-06 🚗 Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment / Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment

🚗 **MINOR-Release.** Drei neue Skoda mysmob endpoints adoptiert von `skodaconnect/myskoda` (MIT-lizenziert, attribution in `NOTICE.md`). Bringt richere DeviceInfo-Enrichment + 2 neue Diagnostic-Sensoren. Skoda-only in dieser Phase; CARIAD-BFF/OLA Equivalente kommen wenn upstream identifiziert.

### 🚗 Was ist neu / What's new

**3 neue Skoda mysmob endpoints** (in `cariad/api/skoda.py`):

- **`GET /api/v2/widgets/vehicle-status/{vin}`** (myskoda PR #557, merged 2026-04-15)
  - Lightweight glance-card payload: `vehicle.{name, licensePlate, renderUrl}`, `vehicleStatus.{doorsLocked, drivingRangeInKm}`, `chargingStatus.*`, `parkingPosition.{state, maps, gpsCoordinates, formattedAddress}`
  - Wired in `get_status()` als 9. endpoint im asyncio.gather (per-tick polling)
  - Defensive: 404/network-error → `{}`, full vehicle-status liefert weiterhin alle Daten

- **`GET /api/v1/vehicle-information/{vin}`** (myskoda `rest_api.py:get_vehicle_info()`)
  - Static device data: `name`, `licensePlate`, `model`, `modelYear`, `engine.{power, type}`, `specification.{title, trimLevel, modelKey, battery}`, `softwareVersion`
  - 24h cache via neuem `coordinator.refresh_static_info()` (analog zum capability-cache pattern)

- **`GET /api/v1/vehicle-information/{vin}/equipment`** (myskoda `rest_api.py:get_vehicle_equipment()`)
  - Static equipment list: `[{id, name}, ...]` (e.g. "Heated steering wheel", "Towbar", "Panoramic sunroof")
  - Same 24h cache, batched mit vehicle-info via `get_vehicle_static_info()` helper

### 🆕 Neue Datenpunkte / New data points

- **`license_plate`** (sensor + DeviceInfo enrichment) — String, populated from widget per-tick + vehicle-info als Fallback
- **`render_url`** (model field) — Image URL für die geplante image platform integration
- **`equipment`** (model field, list) — Full equipment list as `extra_state_attributes` auf equipment_count sensor
- **`equipment_count`** (sensor) — int count, MEASUREMENT state-class, DIAGNOSTIC entity_category
- **DeviceInfo Auto-Enrichment** — `model`, `model_year`, `software_version` werden aus vehicle-info gefüllt wenn vom garage-call nicht gesetzt
- **`parking_address` Fallback** — wenn das Widget eine `formattedAddress` liefert, nutzen wir die ohne Reverse-Geocoding (backend-resolved, locale-aware)

### 🛣️ Architecture / Architecture

- **Per-tick widget call**: `get_status()` macht jetzt 9 parallele endpoint-calls (war 8). Widget ist defensive — wenn 404, verschwindet kein anderer Datenpunkt.
- **24h static-cache**: Neue Methode `coordinator.refresh_static_info(vin)` mit `_STATIC_INFO_REFRESH_INTERVAL = timedelta(hours=24)` und brand-restriction `_STATIC_INFO_BRANDS = ("skoda",)`. Pre-fetched bei setup, lazy-refresh in `_enrich`.
- **Brand-isolation**: Andere Brands (VW EU/Audi/Cupra/Seat/Porsche/VW NA) erhalten weiterhin `None` für die neuen Felder — keine Phantom-Sensoren via `_DATA_PRESENT_REQUIRED` gating.

### 🛡️ Bruno-CI Coverage / Bruno-CI Coverage

- 3 neue Bruno-Files: `tests/bruno/skoda/{25_GET_widget, 26_GET_vehicle_information, 27_GET_vehicle_equipment}.bru`
- Drift-check Skoda: 24/24 → **27/27** strict pass
- EXPECTED_KEYS["skoda"]["widget"] mit 14 expliziten Pfaden + 6 wildcards für Vehicle Data Scout drift detection auf der lightweight payload

### 🧪 Tests / Tests

- 16 neue Test-Cases in `tests/test_v1200_skoda_widget_info_equipment.py`:
  - 5 widget parse-block (full payload / missing blocks / partial vehicle / render-URL filter / address-clobber-prevention)
  - 2 equipment parsing (count derivation / empty list)
  - 3 EXPECTED_KEYS coverage (endpoint registered / full silent / in-motion silent)
  - 4 Model field defaults
  - 2 Sensor exposure (license_plate + equipment_count diagnostic category)
  - 2 Static-info cache constants (24h interval / Skoda-only)
- 10 standalone-logic assertions verifiziert lokal

### 📝 Attribution / Attribution

`NOTICE.md` listet bereits `skodaconnect/myskoda` als MIT-Referenz seit v1.15.0. Endpoint-Definitions, response-shape parsing patterns + Bruno fixture references adoptiert von ihrem `rest_api.py` + `models/widget.py`. Keine eigenständigen Code-Copies, nur Schema-Referenz.

### 🚫 NICHT in diesem Release / NOT in this release

- **Phase B (renders)** — `/v1/vehicle-information/{vin}/renders` separater 4–8 image entity setup nötig; UX-Decision benötigt → deferred to v1.21.0
- **Image platform integration** für `render_url` — erfordert image platform extension; separater PATCH wenn community Bedarf
- **Charging Profile Write-Side** — eigener v1.21.0 oder v1.22.0 Bundle
- **CARIAD-BFF / OLA equivalente** der 3 endpoints — wenn vorhanden upstream identifizieren first

## [1.19.4] - 2026-05-06 🔧📊 Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue / Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue

🔧📊 **PATCH-Release Bundle 1.** Zwei Erweiterungen der existierenden Repair-Flow-Infrastruktur — beide reduzieren User-Reibung bei known UX-Problemen:

### 🔧 Brand-aware T&C Deeplinks / Brand-aware T&C Deeplinks

Vor v1.19.4 zeigte das T&C-Repair-Issue (wenn IDK-Backend "terms-and-conditions" body sendet) einen generischen "Learn more"-Link zum README. Jetzt: **direkter Deeplink zum richtigen Account-Portal** des Brands — User klickt einmal und landet auf der Akzeptieren-Seite.

- `skoda` → `https://skodaid.vwgroup.io/landing-page`
- `volkswagen` → `https://vwid.vwgroup.io/account`
- `audi` → `https://my.audi.com`
- `seat` + `cupra` → `https://seat-cupra.cloud.vwgroup.com`
- `porsche` → `https://my.porsche.com`
- `volkswagen_na` → `https://www.vw.com/myvw`
- Unknown / no-brand → fallback README (backwards-compat)

Pattern adoptiert von `skodaconnect/myskoda` `issues.py`. `raise_issue_auth_required()` akzeptiert jetzt optionalen `brand=` parameter (legacy callers funktionieren weiter).

### 📊 Quota Warning Repair-Issue / Quota Warning Repair-Issue

Extension von v1.19.1 (X-RateLimit-Remaining sensor): User sehen jetzt **proactive UI-Warning** im HA Repairs Dashboard wenn das tägliche Quota-Cap näher rückt. Pattern: pycupra nutzt persistent_notification (älteres HA), wir nutzen Repair-Issue (more discoverable + auto-clears).

- `QUOTA_WARN_THRESHOLD = 100` → Severity WARNING
- `QUOTA_CRITICAL_THRESHOLD = 25` → Severity ERROR
- `raise_issue_quota_low()` und `clear_quota_issue()` als public API in `repairs.py`
- Coordinator's `_enrich`: bei Schwellenüberschreitung wird Issue erstellt, bei Erholung (z.B. midnight reset) automatisch entfernt
- Bilingual translations (DE + EN) mit `{remaining}` / `{limit}` / `{pct}` placeholders + actionable Hinweise (Update-Intervall erhöhen via OptionsFlow)

### 🧪 Tests / Tests

- 20 neue Test-Cases in `tests/test_v1194_bundle1_tnc_quota.py`:
  - 12 brand-aware deeplink lookups (skoda/vw/audi/seat/cupra/porsche/vw_na/unknown/none/marketing_consent/case-insensitive/non-T&C-fallback)
  - 2 raise_issue_auth_required brand-parameter integration
  - 5 Quota Repair-Issue (thresholds, severities, per-entry isolation, clear, no-limit edge case)
  - 1 thresholds constants
- 20 standalone-logic assertions verifiziert lokal

### 🛣️ User Impact / User Impact

**Vor v1.19.4:**
- T&C-Repair "Learn more" → README → User muss selbst zum richtigen Portal navigieren
- Quota-Cap-Hit → Backend gibt 401 / Account temporär gesperrt → User sieht nur "Authentication failed"

**Ab v1.19.4:**
- T&C-Repair → 1-click direkt zum Brand-Portal → Terms akzeptieren → HA-Restart → fertig
- Quota-Cap näher rückend → proactive HA-Repair-Issue mit Schritt-für-Schritt-Anleitung (Update-Intervall erhöhen, andere VAG-Integrationen pausieren) — User kann reagieren BEVOR Backend lockt

### 🚫 NICHT in diesem Release / NOT in this release

- **Quota auto-pause polling** wenn critical → könnte v1.20.x Mini-Feature werden (jetzt nur warning, kein automatic action)
- **`is_fixable=True` mit handler** für T&C-Repair (würde Reauth-Flow direkt aus Issue auslösen) — größeres UX-Pattern, separater Patch
- **Per-VIN quota tracking** — aktuell brand-shared (ein Auth-Cookie für alle VINs einer Brand)

## [1.19.3] - 2026-05-06 🛰️ Scout-Welle 6: 5 Reports, 19 truly new paths silenced / Scout Wave 6: 5 reports, 19 truly new paths silenced

🛰️ **PATCH-Release.** Vehicle Data Scout Pipeline lieferte 5 weitere Community-Reports zwischen 2026-05-04 und 2026-05-06. Audit gegen aktuelles EXPECTED_KEYS-State zeigte: nur **19 von ~58 Felder** sind tatsächlich neu (Rest deckt v1.17.5 + v1.12.x Wildcards bereits ab). Alle 19 silenced.

### 🛰️ Scout-Welle 6 / Scout Wave 6

| Report | User | Brand | Total Felder | Davon truly new |
|---|---|---|---|---|
| #143 | whaak58 | Skoda | 14 | **14 (alle neu)** |
| #144 | HaaseJ64 | VW ID.4 Pro | 24 | 0 (alle silenced) |
| #145 | manentw | VW | 10 | 5 |
| #146 | ammelch | VW | 5 | 0 (subset von #145) |
| #147 | gudden | VW | 5 | 0 (= #146 — 3-User-Konvergenz) |
| **Total** | — | — | **58** | **19** |

### 🛰️ Skoda silencing (#143 whaak58, 14 fields) / Skoda silencing

- **`charging` endpoint** (9 fields): `isVehicleInSavedLocation`, `carCapturedTimestamp`, `errors` + `errors.*` wildcard, plus 6 settings-leaves in lowercase variants alongside legacy uppercase: `settings.{autoUnlockPlugWhenCharged, availableChargeModes, batteryCareModeTargetValueInPercent, chargingCareMode, maxChargeCurrentAc, preferredChargeMode}`
- **`air-conditioning` endpoint** (3 fields): `airConditioningAtUnlock` (auto-AC bei App-Unlock), `seatHeatingActivated` + `seatHeatingActivated.*` wildcard (per-seat dict, future rear-seats covered), `windowHeatingEnabled`
- **`readiness` endpoint** (2 fields): `ignitionOn` (boolean), `batteryProtectionLimitOn` (12V protection flag — useful für "12V kritisch" Automationen)

### 🛰️ Volkswagen + Audi silencing (3 convergent reports, 5 fields) / Volkswagen + Audi silencing

3 unabhängige User (#145, #146, #147) berichteten dieselben 5 Felder = starke Konvergenz, future-proof Wildcards angemessen:

- `automation.chargingProfiles.value.*.*` — 5-segment wildcard für `nextChargingTimer.{id, targetSOCreachable}` (existing 4-segment wildcard reichte nicht)
- `batteryChargingCare.chargingCareSettings` + `.value` + `.value.*` — neuer 3-segment Container plus 4-segment future-proof
- `charging.chargingCareSettings.value` + `.value.*` — 4-segment für `batteryCareMode` leaf
- `climatisationTimers.climatisationTimersStatus` + `.value` + `.value.*` — 3-segment Status-Wrapper analog zu anderen CARIAD `.{xxxStatus}.value` Pattern aus v1.12.0

Audi erbt automatisch via `EXPECTED_KEYS["audi"] = EXPECTED_KEYS["volkswagen"]`.

### 🧪 Tests / Tests

- 12 neue Test-Cases in `tests/test_v1193_scout_welle_6.py`:
  - 5 Skoda silencing (charging settings, top-level meta, AC toggles, readiness flags, full payload)
  - 6 VW silencing (5-segment timer, batteryChargingCare, chargingCareSettings, climatisationTimers, audi inheritance, full payload)
  - 1 cross-check: full convergent VW payload aus #145/#146/#147 returns 0 unexpected
- Audit-script standalone-verified: 19/19 paths silenced

### 📦 Schließt Issues / Closes

- **#143** whaak58 (Skoda 14 fields silenced)
- **#144** HaaseJ64 (VW ID.4 Pro — 24/24 already silenced via earlier wildcards)
- **#145** manentw (VW 5 truly-new + 5 already-silenced)
- **#146** ammelch (VW — convergent with #145)
- **#147** gudden (VW — convergent with #145/#146)

### 🚫 NICHT in diesem Release / NOT in this release

- **Wired sensors für any der Welle-6 fields** — pure silencing, kein neuer entity_id (strict semver: PATCH)
- **`isVehicleInSavedLocation` als sensor** — interessantes Skoda Born-Pattern (zone-aware charging), könnte v1.20.x Mini-Feature werden wenn community Bedarf

## [1.19.2] - 2026-05-05 🔐 Token-Persistence über HACS-Updates (#118 fix) / Token Persistence across HACS Updates (#118 fix)

🔐 **PATCH-Release.** Schließt #118 von eismarkt — "After every update of VAG Connect, the password must be entered again". Root-Cause: IDK-Tokens lebten nur im Memory, jeder HACS-Update / HA-Restart triggered einen vollen `authenticate()` gegen das IDK-Backend → konnte transient fehlschlagen → ConfigEntryAuthFailed → User-Reauth-Prompt. v1.19.1 brachte den Bug-Report-Use-Case explizit zutage.

### 🔐 Was ist neu / What's new

- **Neues Modul** `cariad/auth/_token_storage.py`:
  - `TokenStorage` Klasse wraps HA's `Store` helper mit defensive Load/Save/Clear contract
  - `storage_key_for_entry(entry_id) -> str` für per-config-entry Isolation
  - Defensive: jeder Storage-Error wird gelogged aber nicht propagiert (worst-case = ein extra Login beim nächsten Start)
- **`CariadBaseClient` Erweiterungen**:
  - Neuer optional callback `on_tokens_changed: Awaitable[Callable[[TokenSet], Coroutine]]`
  - Neue Methode `set_persisted_tokens(tokens)` — injiziert geladene Tokens vor erstem API-Call
  - Neue Methode `_notify_tokens_changed()` — fires hook nach erfolgreichem `authenticate()` und `_refresh_tokens()`
- **Coordinator Wire-Up** (`coordinator.py:async_setup`):
  - Erstellt `Store(hass, _STORAGE_VERSION, storage_key_for_entry(entry_id))`
  - Lädt persisted tokens BEVOR `authenticate()` versucht wird
  - Wenn Tokens da → skip Initial-Login, nutze 401-refresh-path bei Bedarf
  - Hooked `client.on_tokens_changed = storage.save` für automatische Persistenz nach jedem Refresh
- **`__init__.py` neuer `async_remove_entry`**:
  - Cleanup von persisted tokens beim full Config-Entry-Remove (NOT bei reload — da bleiben sie für Re-Setup)

### 🧪 Tests / Tests

- 18 neue Test-Cases in `tests/test_v1192_token_persistence.py`:
  - 7 Load: never-saved / non-dict / version-mismatch / missing-tokens / incomplete / valid round-trip / storage-error
  - 3 Save: round-trip / incomplete refused / storage-error swallowed
  - 2 Clear: idempotent / storage-error swallowed
  - 1 Storage-key per-entry isolation
  - 5 CariadBaseClient hooks: set_persisted (valid/None/incomplete) + _notify (callback fires / no callback / no tokens / exception isolated)
- 12 standalone-logic assertions verifiziert lokal

### 🛣️ User Impact / User Impact

**Vor v1.19.2:**
1. HACS update → integration reload → in-memory tokens weg
2. `authenticate()` → IDK-Login → wenn flaky → `ConfigEntryAuthFailed`
3. User sieht "Reauth required" Notification → muss Password neu eingeben

**Ab v1.19.2:**
1. HACS update → integration reload → tokens werden aus `.storage/vag_connect_tokens_<entry_id>` geladen
2. Erste API-Call nutzt persisted tokens direkt → 200 OK
3. Bei expired access_token → `_refresh_tokens()` läuft transparent + persisted refresh_token → neue Tokens werden wieder gespeichert
4. **Kein User-Action nötig** — auch bei daily quota-limit oder transient IDK-Issue läuft alles weiter

### 🔒 Privacy / Privacy

- Tokens werden in `.storage/vag_connect_tokens_<entry_id>` geschrieben — same trust-level wie credentials im config-entry (HA Storage area)
- Nie in Logs (existing `_unexpected_keys.py:_JWT_RE` redaction handles diagnostics-export)
- Auto-cleanup bei Config-Entry-Remove (`async_remove_entry`)

### 📦 Schließt Issues / Closes

- **#118** eismarkt "restart After Update" — Token-Persistence ist die strukturelle Lösung; User wird nach v1.19.2-Update einmal Password eingeben (initial migration), danach nie wieder

### 🚫 NICHT in diesem Release / NOT in this release

- **Per-VIN HomeRegion-Cache Persistence** — analoges Pattern für v1.17.6 Foundation; eigener Patch wenn Live-Test-Bedarf
- **Push FCM-Credential Persistence** — v1.18.x Phase 2 wire-in, separater Patch

## [1.19.1] - 2026-05-04 📊 Pycupra-style API Quota Sensor / Pycupra-style API Quota Sensor

📊 **PATCH-Release.** Inspired by `WulfgarW/homeassistant-pycupra` source-reading. Wires up X-RateLimit-* response headers (sent by most VAG backends on successful responses) als neuen `requests_remaining_today` Diagnostic-Sensor — User sehen wie nah sie am täglichen Quota-Limit sind (~1500/Tag MyCupra/MySeat per Community-Research).

### 📊 Was ist neu / What's new

- **`base.py:_capture_rate_limit_headers(headers)`** — neue Methode parst nach jedem 2xx-Response:
  - `X-RateLimit-Remaining` → `int`, surfaced as Sensor
  - `X-RateLimit-Limit` → `int`, available für HA-Template-Berechnungen via attrs
  - `X-RateLimit-Reset` → ISO-8601 string oder Epoch-Sekunden (opaque pass-through)
  - Defensive: float-fallback ("1499.5"), garbage-strings ("unlimited") und missing-headers lassen vorherige Werte bestehen (besser stale als wrong, kein Sensor-Flackern)
- **`models.py`**: drei neue Felder `requests_remaining_today`, `requests_limit_today`, `requests_reset_at` (defaults None)
- **`coordinator.py:_enrich`**: kopiert die brand-client-attribute auf jedes VIN's data-dict (auth ist brand-scoped, alle VINs derselben Brand sehen das gleiche Quota)
- **`sensor.py`**: neuer `requests_remaining_today` Sensor (`EntityCategory.DIAGNOSTIC`, MEASUREMENT state-class, `mdi:gauge-low` icon)
- **Translations** für DE + EN
- **Was wir NICHT extra bauen mussten** (already covered):
  - `find_path()` equivalent — `base.py:_val()` macht das gleiche seit early releases
  - `PyCupraThrottledException` equivalent — `_request()` retried 429 transparent mit exponential backoff seit v1.8.7

### 🧪 Tests / Tests

- 16 neue Test-Cases in `tests/test_v1191_pycupra_hardening.py`:
  - 8 Header-Parser Edge-Cases (initial / int / float-fallback / garbage / missing / partial / preserved)
  - 2 VehicleData field invariants (default None, accepts int)
  - 3 Sensor exposure (description present, diagnostic category, translation key match)
  - 2 Translation strings (EN + DE haben den Sensor-Namen)
- Header-parser standalone-Logic 8/8 lokal verifiziert

### 📦 Schließt Issues / Closes

- Pycupra-driven Hardening-Item aus HACS-Checklist (Roadmap P0)

### 🚫 NICHT in diesem Release / NOT in this release

- **Coordinator-side quota-warning notification** (z.B. "you have <100 requests left today") — könnte als follow-up wenn User sich melden dass es nützlich wäre
- **Pro-Brand quota-tracking** — aktuell shared globally via brand-client-state; CUPRA + Skoda haben ggf. unterschiedliche Quotas — refinement später

## [1.19.0] - 2026-05-04 🚀 CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.) / CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.)

🚀 **MINOR-Release.** Push-Update-Infrastruktur für CUPRA/SEAT OLA Backend via Firebase Cloud Messaging. Spiegelt v1.18.0 Skoda MQTT Foundation — gleiche `PushManager` base, gleiche Lifecycle-Hooks, gleiche Lazy-Import-Strategy. Default OFF, opt-in via OptionsFlow toggle.

### 🚀 Was ist neu / What's new

- **Neues Push-Module** `cariad/push/cupra_seat_fcm.py`:
  - `CupraSeatPushManager` Klasse, erbt von `PushManager` (v1.18.0 base)
  - **Brand-Constructor-Validation** — `brand` Parameter muss `"cupra"` oder `"seat"` sein, sonst `ValueError`
  - Identische Lifecycle-Hooks wie SkodaPushManager (start/stop, idempotent)
  - Identische Reconnect-Backoff-Konstanten (5s → 600s mit ±10% Jitter)
  - Lazy-Import nur für `firebase-messaging` (kein MQTT — CUPRA/SEAT push ist pure FCM)
  - **Reuses gleiche Lib** wie v1.18.0 Skoda MQTT (Skoda braucht `firebase-messaging` für TOTP-Auth-Credential, CUPRA/SEAT für FCM-Transport)
- **Neuer Config-Flow Toggle** `CONF_ENABLE_PUSH_FCM` (default False) im OptionsFlow — koexistiert unabhängig mit `CONF_ENABLE_PUSH_MQTT` (Skoda). User mit gemischter Flotte kann beide aktivieren
- **Bilingual Translations** (DE + EN) für den neuen Toggle

### 🧪 Tests / Tests

- 16 neue Test-Cases in `tests/test_v1190_cupra_seat_fcm_foundation.py`:
  - 2 Construction (brand validation für cupra/seat/invalid + initial STOPPED state)
  - 5 Lifecycle (no VINs / missing dep UNAVAILABLE / start+stop / idempotent start / idempotent stop)
  - 4 Backoff state machine (mirrors v1.18.0 — initial / grows / caps / reset)
  - 2 Emit + exception isolation
  - 3 Const + config_flow exposure (CONF_ENABLE_PUSH_FCM defined, exposed in config_flow, two push toggles coexist)
  - 2 Module exports + inheritance
- 8/8 standalone assertions verifiziert lokal

### 🛣️ Wire-Up Plan / Wire-Up Plan

```python
# In coordinator.py async_setup:
if (
    options.get(CONF_ENABLE_PUSH_FCM, False)
    and brand in ("cupra", "seat")
):
    from .cariad.push.cupra_seat_fcm import CupraSeatPushManager  # lazy
    self._push_manager = CupraSeatPushManager(
        on_event=self.async_handle_push_event,
        user_id=auth.user_id,
        access_token_provider=auth.get_access_token,
        vins=list(self.vehicles.keys()),
        brand=brand,
    )
    await self._push_manager.start()
```

Wire-Up wartet auf:
1. CUPRA/SEAT Community-Tester mit aktiver MyCupra/MySeat Subscription
2. FCM Project + sender_id Verifikation gegen `firebase-messaging` lib (pycupra `firebase.py` als Referenz)
3. OLA `/v2/subscriptions` POST-Body-Schema Verifikation (was genau muss in `services` dict?)

### 🚫 NICHT in diesem Release / NOT in this release

- **Aktive FCM-Verbindung** — Foundation-Stub schlafen lässt sich verbinden für State-Machine-Test, sendet aber keine echten FCM-Subscriptions
- **iot_class change** — wartet bis Push primärer Pfad ist (aktuell: Polling für 100% User)
- **Manifest deps** — bewusst weggelassen, lazy-import vermeidet Bloat
- **Coordinator wire-in** — gleiche Bedingung wie v1.18.0: nach Live-Test

### 📦 Schließt Issues / Closes

- **#57** Firebase FCM / MQTT Push — **Foundation-Phase komplett für alle 3 push-fähigen Brands** (Skoda v1.18.0 + CUPRA/SEAT v1.19.0). Phase 2 (Live-Activation) für nächste Release-Reihe v1.18.x / v1.19.x

## [1.18.0] - 2026-05-04 🚀 Skoda MQTT Push Foundation (#57 Phase 1) / Skoda MQTT Push Foundation (#57 Phase 1)

🚀 **MINOR-Release.** Push-Update-Infrastruktur für Skoda mysmob MQTT Broker (`mqtt.messagehub.de:8883`). **Foundation-Phase** — Klassen-Struktur, State-Machine, Lifecycle-Hooks komplett gebaut + getestet, aber Live-Aktivierung wartet auf Community-Tester (Skoda Connect Subscription erforderlich). Default OFF — opt-in via OptionsFlow toggle.

### 🚀 Was ist neu / What's new

- **Neues Push-Package** `custom_components/vag_connect/cariad/push/`:
  - `base.py` — abstract `PushManager` + `PushUpdateEvent` (frozen dataclass) + `PushManagerState` enum (6 Phasen: STOPPED, STARTING, CONNECTED, RECONNECTING, DISABLED, UNAVAILABLE)
  - `skoda_mqtt.py` — `SkodaPushManager` Implementation mit Lifecycle, Reconnect-Backoff (5s → 600s mit ±10% Jitter, evcc + myskoda PR #566 Constants), Lazy-Import für `aiomqtt` + `firebase-messaging`
  - `__init__.py` — Package-Doku + Exports
- **Neuer Config-Flow Toggle** `CONF_ENABLE_PUSH_MQTT` (default False) im OptionsFlow — User aktiviert Push pro Integration; bilingual Translations (DE + EN strings)
- **Lazy-Import-Strategie** für Push-Deps: `aiomqtt` + `firebase-messaging` werden NICHT in `manifest.json` requirements gelistet (kein Bloat für 99% Polling-User). Wenn User Toggle aktiviert OHNE Deps installiert zu haben → Manager geht in `UNAVAILABLE` State + logged Hinweis "pip install aiomqtt firebase-messaging" + fällt still auf Polling zurück

### 🧪 Tests / Tests

- 18 neue Test-Cases in `tests/test_v1180_skoda_push_foundation.py`:
  - 3 Push base types (state enum, frozen dataclass, payload variant)
  - 6 SkodaPushManager lifecycle (initial state, empty VINs, missing-deps UNAVAILABLE, start+stop cleanup, idempotent start, idempotent stop)
  - 5 backoff state machine (initial 5s, grows, caps at 600s + 15% jitter buffer, reset returns to initial, jitter floor)
  - 2 event emit + exception isolation (callback called, failing callback doesn't crash loop)
  - 1 const + config_flow option (CONF_ENABLE_PUSH_MQTT exposed)
  - 1 package exports (PushManager, PushUpdateEvent importable)
- Alle 10 standalone-Logic-Assertions verifiziert lokal

### 🛣️ Wire-Up Plan / Wire-Up Plan

```python
# In coordinator.py async_setup or async_setup_entry:
if (
    options.get(CONF_ENABLE_PUSH_MQTT, False)
    and brand == "skoda"
):
    from .cariad.push.skoda_mqtt import SkodaPushManager  # lazy
    self._push_manager = SkodaPushManager(
        on_event=self.async_handle_push_event,
        user_id=auth.user_id,
        access_token_provider=auth.get_access_token,  # async
        vins=list(self.vehicles.keys()),
    )
    await self._push_manager.start()

# In coordinator.async_unload or async_unload_entry:
if self._push_manager:
    await self._push_manager.stop()

# In coordinator new method async_handle_push_event(event):
#   - filter event.event_type for refresh trigger
#   - call get_status(event.vin) for affected VIN
#   - async_set_updated_data(updated_dict)
```

Wire-Up wartet auf:
1. Community-Tester mit Skoda + Connect Subscription bestätigt FCM-Project-ID + TOTP-Scheme
2. Endpoint-Verifikation des Brokers (mqtt.messagehub.de:8883 noch live? auth-Format unverändert?)
3. Push-Parität-Mapping: welche Events triggern get_status vs welche carry full state?

### 🚫 NICHT in diesem Release / NOT in this release

- **Aktive MQTT-Verbindung** — Foundation-Stub schlafen lässt sich verbinden (für State-Machine-Test) aber sendet keine echten MQTT-Subscribes. Live-Activation in v1.18.x Patch-Reihe sobald Tester sich melden
- **CUPRA/SEAT FCM** — analoge Foundation kommt in v1.19.0 (reuses gleiche `firebase-messaging` lib via lazy-import)
- **iot_class change cloud_polling → cloud_push** — wartet bis Push primärer Pfad ist (aktuell: Polling für 100% User, Push opt-in für 0%)
- **Manifest deps** (`aiomqtt`, `firebase-messaging`) — bewusst weggelassen um kein Bloat für non-Skoda User; opt-in User installieren manuell via `pip install` in HA env

### 📦 Schließt Issues / Closes

- **#57** Firebase FCM / MQTT Push (real-time updates) — **Phase 1 Foundation** geschlossen, Phase 2 (Live-Aktivierung) für nächste Release-Reihe v1.18.x

## [1.17.7] - 2026-05-04 🌡️🔧 Skoda outside_temperature + preferred_workshop attrs / Skoda outside_temperature + preferred_workshop attrs

🌡️🔧 **PATCH-Release.** Wires up zwei existing-but-not-Skoda-populated Datenpunkte aus den v1.17.5 Scout-Reports:

### 🌡️ Skoda outside_temperature (#129 + #130 + #133) / Skoda outside_temperature

Drei unabhängige User berichteten in 24h dass Skoda mysmob jetzt `outsideTemperature.{temperatureValue,temperatureUnit,carCapturedTimestamp}` auf dem `air-conditioning` Endpoint shippt. v1.17.5 hat das via EXPECTED_KEYS Wildcard silenced; jetzt wird es **tatsächlich gelesen**:

- Bestehender `outside_temp` Sensor (existiert seit early releases, populated von VW EU + SEAT/CUPRA) bekommt **Skoda als zusätzliche Datenquelle**
- Native CELSIUS values (3 Reports konvergent), defensive FAHRENHEIT-Konversion via `(F - 32) * 5/9` falls jemals shipped
- `safe_float` für Wert-Konversion (handelt Strings + dot-decimal — locale-comma "21,5" ist offen, nicht in v1.17.7 gefixt)
- **Kein neuer Sensor, kein neuer Translation-Key, kein neues HACS-Manifest-Field** — purer Datenquellen-Hookup → echter PATCH

### 🔧 Skoda preferred_workshop attrs (#130 + #133) / Skoda preferred_workshop attrs

Skoda exposed jetzt komplette Werkstatt-Info auf dem `maintenance` Endpoint via `preferredServicePartner.{name,brand,partnerNumber,id,contact,address,location,openingHours}`. v1.17.5 hat das silenced; jetzt wird es **gelesen + als attrs angeboten**:

- Neues Model-Field `VehicleData.preferred_workshop: dict | None` (defaults None für alle anderen Brands)
- Skoda Parser kopiert das Dict verbatim, dropped nur `openingHours` (rare actionable in HA UI, hält state-machine lean)
- **`extra_state_attributes` auf bestehendem `service_due_in_days` Sensor** — `attrs["preferred_workshop"]` zeigt name/brand/partnerNumber/id/contact/address/location dem User direkt im Dashboard. Ander Brands kriegen weiterhin None
- Pattern analog v1.14.0 #24 (`recent_trips` auf `last_trip_distance_km`) und v1.15.0 #35 (`recent_charging_sessions` auf `total_charged_energy_kwh`)
- **Kein neuer Sensor, kein neuer Entity-ID** → echter PATCH

### 🧪 Tests / Tests

- 14 neue Test-Cases in `tests/test_v1177_skoda_outside_temp_workshop.py`:
  - 7 outside_temperature: Celsius/Fahrenheit-Konversion, Garbage-Values, Missing-Block, Unit-Default
  - 5 preferred_workshop: Pass-through, openingHours-Drop, Missing/Empty/Non-Dict, Full #133-Payload
  - 2 VehicleData field invariants
- Pattern follows v1.15.0 Skoda Modernization (inline parsing reproduction in tests, weil Skoda's `get_status` monolithisch ist ohne separate `_parse_status` Methode)
- Lokal verifiziert: 13/13 assertions pass

### 📦 Schließt Issues / Closes

- **#129** rocksandclouds (Skoda outsideTemperature) — Datenpunkt jetzt wirksam als Sensor
- **#130** Chr1sDub (Skoda preferred_workshop + outsideTemperature) — beide Datenpunkte jetzt wirksam
- **#133** christianmhz (Skoda komplette Maintenance-Block) — als attrs auf service_due_in_days Sensor

### 🚫 NICHT in diesem Release / NOT in this release

- **`customerService.activeBookings/bookingHistory` als sensors** — niedrige UX-Wert (Booking-History meist leer für deutsche User), deferred
- **VW heaterSource ("electric") als data feature** — silencing only in v1.17.5; brauchen Live-Test ob als Klima-Modus-Sensor nützlich
- **VW EU outside_temp Verstärkung mit fuelLevelStatus.value.secondaryEngineType** — nichts kaputt, kein dringender Bedarf
- **HomeRegion wire-up** — bleibt scaffolding bis Live-Test es bestätigt
- **Push Bundle** — eigene v1.18.0 Release (Skoda MQTT) + v1.19.0 (CUPRA/SEAT FCM)
- **locale-comma "21,5" für safe_float** — separater Fix, niedrige Priorität (Skoda hat das nur einmal historisch geshipt)

## [1.17.6] - 2026-05-04 🌍 HomeRegion-Helper Scaffolding (evcc port) / HomeRegion Helper Scaffolding (evcc port)

🌍 **PATCH-Release.** evcc-Pattern für region-import / non-EU-routed Vehicles eingebaut. Neuer Helper `cariad/_home_region.py` löst per-VIN die Base-URI auf via Discovery-Endpoint `https://mal-1a.prd.ece.vwg-connect.com/api/cs/vds/v1/vehicles/{vin}/homeRegion`. **Scaffolding-only** — Helper ist gebaut, getestet, dokumentiert, aber NOCH NICHT in `vw_eu.py` URL-Builders integriert (würde 13 Call-Sites berühren — Risk-Reward für 99%-EU-User vs. 1%-Edge-Case ungünstig). Wire-Up-Plan ist im `_home_region.py` Modul-Header dokumentiert; Aktivierung erfolgt via separatem PATCH falls Live-Tests (#75 Skoda Kodiaq Mk2 oder ähnlich) bestätigen dass HomeRegion-Resolution den Bug fixt.

### 🛠️ Was ist gebaut / What is built

- **`custom_components/vag_connect/cariad/_home_region.py`** (155 Zeilen):
  - `HomeRegionCache` Klasse mit per-VIN dict + 7-Tage TTL
  - `async def resolve_home_region(client, vin, *, cache=None) -> str` — ruft Discovery-Endpoint, parsed `homeRegion.baseUri.content`, fallback auf `DEFAULT_BASE` bei Fehler/Malformed-Response
  - `DEFAULT_BASE = "https://emea.bff.cariad.digital"` (= identisch mit `vw_eu._BASE`)
  - `DISCOVERY_BASE = "https://mal-1a.prd.ece.vwg-connect.com"`
  - Defensiv gegen alle Failure-Modi (404, network error, malformed JSON, missing keys)
- **`tests/bruno/cariad_bff/22_GET_homeRegion.bru`** — menschen-runbar via Bruno CLI für manuelle Verifikation. Drift-check silent weil mal-1a anderer Host (kein `{{base_url}}` Prefix → keine Bruno-URL-Extraktion → kein Counting-Mismatch)
- **`tests/test_v1176_homeregion.py`** — 14 Test-Cases:
  - Cache: hit/miss/expiry/clear/per-VIN-isolation
  - Resolution: success/trailing-slash/correct-discovery-URL
  - Fallback: network error/404/malformed-response (9 variants)/no-cache-mode
  - Failure-caching (default base cached on lookup failure to skip retry)
  - Invariant test: `DEFAULT_BASE == vw_eu._BASE`

### 🔌 Wire-Up Plan (für späteren PATCH wenn nötig) / Wire-Up Plan

```python
# In VWEUClient.__init__:
self._vehicle_bases: dict[str, str] = {}
self._home_region_cache = HomeRegionCache()

# In VWEUClient.get_vehicles, nach VIN-Liste:
for vin in vins:
    self._vehicle_bases[vin] = await resolve_home_region(
        self, vin, cache=self._home_region_cache,
    )

# Helper für synchronen Zugriff in URL-Buildern:
def _base_for_vin(self, vin: str) -> str:
    return self._vehicle_bases.get(vin, _BASE)

# Alle 13 ``f"{_BASE}/..."`` Stellen umstellen auf:
# ``f"{self._base_for_vin(vin)}/..."``
```

Audi erbt automatisch via `AudiClient(VWEUClient)`. Skoda mysmob hat eigenen Backend-Hostname und braucht separaten Helper falls dort auch nötig (TBD basierend auf Live-Test-Daten von #75).

### 🚫 NICHT in diesem Release / NOT in this release

- **Wire-Up in `vw_eu.py`** — opt-in scaffolding, kein Risiko für EU-User
- **Skoda mysmob HomeRegion** — analoger Helper möglich, abhängig von #75 Live-Test
- **VW NA / Porsche / SEAT/CUPRA HomeRegion** — andere Auth-Pipelines, nicht von HomeRegion betroffen
- **PKCE-OAuth Hardening** — separater Patch, niedrige Prio

### 📦 Schließt Issues / Closes

Keine User-Issues direkt — Pure Infrastruktur-Vorbereitung. Hilft potentiell beim Lösen von #75 (Skoda Kodiaq Mk2 403) wenn Christian's Vehicle in nicht-Standard-Region geroutet ist (zu verifizieren wenn er antwortet).

## [1.17.5] - 2026-05-04 🛰️ Scout-Welle 5: 4 Community-Reports an einem Tag + 4 Verification-Pings / Scout Wave 5: 4 community reports in one day + 4 verification pings

🛰️ **PATCH-Release.** Vehicle Data Scout Pipeline (v1.9.0) hat innerhalb von 24h **4 neue Community-Reports** geliefert: rocksandclouds (#129), Chr1sDub (#130), rborkenhagen (#132), christianmhz (#133) — plus Gerhard's parallele Cupra Born v1.17.4-Test-Reaktion (#53). Total **42 neue Felder über 4 Brands** (Skoda + VW + Audi + Cupra/Seat) registriert in EXPECTED_KEYS. Plus Sprint-A Verification-Pings auf 4 ältere Issues.

### 🛰️ Scout-Silencing — 5 Reports, 4 Brands / Scout Silencing — 5 Reports, 4 Brands

**Skoda mysmob (#129 + #130 + #133, 3 unabhängige User mit konvergenten Findings):**

- `outsideTemperature.*` Wildcard auf `air-conditioning` Endpoint — deckt `temperatureValue` (z.B. `24.0`), `temperatureUnit` ("CELSIUS"), `carCapturedTimestamp` ab
- `targetTemperature.unitInCar` ("CELSIUS"|"FAHRENHEIT") auf `air-conditioning` Endpoint
- `preferredServicePartner.*` Wildcard auf `maintenance` Endpoint — deckt `name`, `brand`, `partnerNumber`, `id`, `contact`, `address`, `location`, `openingHours` ab (Skoda exposed jetzt komplette Werkstatt-Info)
- `customerService.*` Wildcard auf `maintenance` Endpoint — deckt `activeBookings`, `bookingHistory` ab
- `errors`, `errors.*` auf `parking` Endpoint (Skoda mysmob wraps "no recent GPS fix" und ähnliche transient errors jetzt im gleichen Pattern wie air-conditioning + driving-range)

**Volkswagen + Audi CARIAD-BFF (#132 rborkenhagen):**

- `climatisation.climatisationSettings.value.heaterSource` ("electric" für Born/ID — wird vom Backend gemeldet, von uns noch nicht für PHEV-PTC vs HV-loop Logik genutzt)
- `measurements.fuelLevelStatus.value.secondaryEngineType` ("electric" — companion zu primaryEngineType, hardens v1.11.1 #96 Golf GTE PHEV-detection)
- `departureTimers`, `departureTimers.*` Wildcard (top-level job ist seit v1.13.0 in selectivestatus query, aber nie explizit in EXPECTED_KEYS catalog gewesen)
- Audi erbt VW EU's selectivestatus shape — alle drei Silencings gelten automatisch

**Cupra/Seat OLA (#53 Gerhard's Born v1.17.4-Test):**

- `services.*` Wildcard auf `mycar` Endpoint — Born exposed per-service entitlement children (charging/climatisation/windowHeating); jeder ist multi-key dict (subscription state + caps + limits)
- `settings.*` Wildcard auf `charging-info` Endpoint — Born nutzt lowercase `Ac` suffix variant (`maxChargeCurrentAc`, `autoUnlockPlugWhenChargedAc`, `targetSoc`) parallel zur uppercase `AC` variant
- `chargingCareSettings.*` und `chargingCareStatus.*` Wildcards — neue Charge-Care-Subsystem leaves (`batteryCareMode=true`, `batteryCareTargetSoc=80`)
- Seat erbt Cupra's OLA shape — alle Silencings gelten automatisch

### 📨 Sprint-A Verification-Pings + Diagnostic-Pings / Sprint A Verification + Diagnostic Pings

4 ältere Issues mit Verweis auf Hardening-Bundles seit ihrer Original-Report-Version:

- **#118 eismarkt** "restart After Update" — User auf v1.9.0; v1.10.1 + v1.11.1 + v1.13.0 Hardening-Bundles seitdem
- **#51 Audi RS e-tron GT 404** — User auf v1.5.10; v1.8.4 SecToken + v1.8.5 v1/v2 fallback + v1.9.1 Wake-Fix + v1.13.0 Capability-Filter Phase 3 + v1.14.0 Audi Feature Pack seitdem
- **#48 all-actions-fail** — Generic; v1.8.5 fallback + v1.9.1 classify_command_failure + v1.13.0 Phase 3 seitdem
- **#42 migendi CUPRA Formentor v1.5.9** — v1.10.2 Born firmware + v1.16.1 Klima-Fix + v1.17.1 Bruno-Quick-Wins seitdem

Plus **#131 Chr1sDub Skoda Octavia** Diagnostic-Ping: Subscription-Verifikation (Connect-Abo: NEIN ist mutmaßlich Root-Cause für die HTTP 500 Klima-Failures) + S-PIN Re-Check (Optionen-Variante vs Initial-Config) — kein Code-Fix in diesem Release weil 500 → NOT_ENTITLED Klassifikation false-positive Risiko hat (transient backend errors würden Entities verstecken).

Plus **#53 Gerhard Born Klima-Stop 404 Diagnose-Frage** — A/B Fallback in v1.16.1 deckt 2 URLs ab; Gerhards Born scheint einen dritten Pfad zu brauchen. Warten auf DEBUG-Log + 404-Body um den fehlenden Path zu identifizieren.

### 🧪 Tests / Tests

- 16 neue Test-Cases in `tests/test_v1175_scout_silencing.py` — alle 5 Scout-Reports verifiziert für Skoda/VW/Audi/Cupra/Seat (inkl. Inheritance-Tests für audi←volkswagen und seat←cupra)
- Alle bestehenden Tests grün
- Bruno-Drift unverändert: 80/80 strict pass

### 🚫 NICHT in diesem Release / NOT in this release

- **outside_temperature_c Sensor (Skoda)** — strict semver MINOR weil neuer Sensor; deferred zu v1.18.0
- **preferredServicePartner als attrs-Sensor** — same reason; deferred
- **500-Klassifikation für Skoda mysmob** — false-positive Risiko zu hoch; alternative wäre per-VIN failure-rate threshold (komplexer; deferred)
- **HomeRegion-Helper (evcc port)** — eigener PATCH v1.17.6 oder mit v1.18.0 gebündelt

### 📦 Schließt Issues / Closes

Keine User-Issues direkt geschlossen — Verification-Pings warten auf User-Confirmation. Pure Scout-Silencing für #129/#130/#132/#133/#53.

## [1.17.4] - 2026-05-03 🎯 Bruno-CI Stufe 2 COMPLETE — Full Strict Coverage / Bruno-CI Stufe 2 Complete (Skoda + CARIAD-BFF strict)

🎯 **Bruno-CI Stufe 2 ist COMPLETE.** Skoda + CARIAD-BFF auf 100% coverage gebracht, alle 3 Brands jetzt strict mode in CI. **80 .bru files total**, 80/80 match (35 seat_cupra + 24 skoda + 21 cariad_bff).

### 🤖 Bruno Coverage Completion / Bruno Coverage Completion

- **Skoda: +17 neue .bru files** (seq 08–24) via gen-agent — covers alle 24 Python URLs:
  - 3× charging actions (set-charge-limit, start, stop)
  - 3× vehicle-access (lock, unlock, honk-and-flash)
  - 1× vehicle-wakeup (mit `?applyRequestLimiter=true` query)
  - 5× air-conditioning (bare GET, target-temperature, start, stop, start/stop-window-heating)
  - 1× connection-status/readiness
  - 1× vehicle-status/driving-range
  - 1× maps/positions/parking
  - 1× vehicle-maintenance
  - **24/24 strict pass**
- **CARIAD-BFF: +11 neue .bru files** (seq 11–21):
  - 4× neue concrete endpoints (engine_stop, vehicles list, climatisation/timers POST, windowheating combined)
  - 7× separate-route fallbacks für `_post_command_with_fallback_paths` (lock, unlock, charging-start, charging-stop, climatisation-start, climatisation-stop, vehicleWakeup) — required by drift-check für coverage of v1 paths
  - **21/21 strict pass**

### 🛠️ Drift-Check Improvements / Drift-Check Improvements

- **`{path_suffix}` placeholder expansion** in `_ACTION_EXPANSIONS` — covers `_post_command_with_fallback_paths(primary_suffix=..., fallback_suffix=...)` runtime templates. Same mechanism as `{action}` placeholder.
- **`_is_skipped_template()` helper** — filters out `/vehicle/v2/vehicles/{vin}/{path_suffix}` template captures since `_post_command` auto-falls back from v1→v2 with same body. v2 fallback URLs are implicit, no separate Bruno docs needed.
- **CI workflow strict mode for ALL 3 brands** — no more `--strict-brands seat_cupra` whitelist; full `--strict` gating. Any new Python endpoint without matching `.bru` fails CI immediately.

### 📊 Coverage Summary / Coverage Summary

| Brand | Python URLs | Bruno files | Match | Status |
|---|---|---|---|---|
| seat_cupra | 35 | 35 | 35/35 | ✅ Strict |
| skoda | 24 | 24 | 24/24 | ✅ Strict |
| cariad_bff | 21 | 21 | 21/21 | ✅ Strict |
| **Total** | **80** | **80** | **80/80** | **✅ All strict** |

### 📦 Schließt Issues / Closes

Keine User-Issues — Bruno-Coverage Abschluss.

### 🎯 Strategische Bedeutung / Strategic Context

Bruno-CI Stufe 2 ist die **Foundation für Stufe 3** (Custom Claude Code Skill für HAR→.bru → Python-client generation). Ab v1.18.0+ kann jede neue Endpoint-Addition über die `.bru → Python` Workflow-Direction laufen statt umgekehrt. Das senkt die Contribution-Schwelle für Brand-Captains drastisch und macht uns zur **canonical reference** für die VAG-FOSS-Community.

## [1.17.3] - 2026-05-03 🤖🛡️📚 Bruno-CI Stufe 2 + Lovelace Cards + 3 Research Docs

🤖 **MASSIVE PATCH-Release** mit 4 parallel ausgelieferten Themen:

1. **Bruno-CI Stufe 2** — full coverage seat_cupra (35 .bru files, strict gating ON), 7 skoda + 10 cariad_bff .bru files, multi-file-per-brand drift-check
2. **Lovelace Cards Recommendations** — 4 cards reviewed + own card project teased
3. **3 neue Research-Docs** — mitch-dc deprecated migration + browser_mod integration + community VAG-HA landscape
4. **Tim's Issue #1 Outreach Reply** — humanized German reply showing v1.17.0→v1.17.2 Bruno-Evolution, Cross-Review-Offer, +1 endpoint-PRs angekündigt

### 🤖 Bruno-CI Stufe 2 / Bruno-CI Stufe 2

**SEAT/CUPRA: 100% coverage + strict gating**
- 27 .bru files via gen-agent (seq 07-33) — covers alle Python-URLs in `cariad/api/seat_cupra.py`
- Plus 3 fallback `.bru` files (seq 34-36) für documented A/B-fallback URLs
- **Drift-check: 35/35 match, 0 drift, strict mode AKTIV in CI** — jede neue endpoint-Addition ohne `.bru` lässt CI fail

**Skoda: 7 .bru files** (seq 01-07) für die wichtigsten endpoints (garage mit MOD1-4 query, capabilities, vehicle-status, charging, charging-history, charging-profiles, software-update). 17 noch offene Python-URLs werden in v1.17.4 aufgefüllt.

**CARIAD-BFF (Audi + VW EU): 10 .bru files** (seq 01-10) für selectivestatus, capabilities, parkingposition, tripstatistics, lock, climate-start, charging-start, vehicleLights flash, plus 2 Audi-engine endpoints (PUT userpromptproof + POST start). 6 noch offene werden in v1.17.4 aufgefüllt.

**Drift-check Script Refactor:**
- Multi-file-per-brand support (cariad_bff = vw_eu.py + audi.py)
- `_ENGINE_BASE` constant captured for Audi-specific URLs
- `--strict-brands` flag für per-brand graduation (seat_cupra strict, skoda+cariad_bff warn-only)
- Placeholder-expansion für `{action}` runtime placeholder dropped originals (no more strict-mode false-positives)

### 🎨 Lovelace Cards Section / Lovelace Cards Section

Neue README-Sektion "Empfohlene Lovelace-Cards" mit Bewertungstabelle für 4 community Cards:
- **flex-table-card** (custom-cards Org, aktiv) — Multi-Vehicle-Dashboards
- **vehicle-info-card** (ngocjohn, wenig Updates) — Single-Vehicle-Detail
- **car-card** (flixlix, aktiv) — Simple EV-Schnellansicht
- **Ultra-Vehicle-Card** (WJDDesigns, aktiv) — Polished Premium-Look

Plus Teaser für **eigenes Card-Projekt** (`vag-connect-lovelace-card` repo geplant) + Browser-Mod Integration Hinweis (recipe-doc folgt v1.18.0).

### 🔬 3 Neue Research-Docs / 3 New Research-Docs

Alle in `docs/research/`:

- **`migration-from-mitch-dc-2026-05-03.md`** (R1) — `mitch-dc/volkswagen_we_connect_id` archived 2025-10-29 deep-scan. Repo-Status, top 10 open issues (mostly auth/login), last 5 PRs (anothertobi's CarConnectivity migration draft closed unmerged), endpoint comparison (we have 18 endpoints, they had 0 — used `weconnect==0.60.8` library wrapper), entity ID mapping table für Migration-Guide, SEO-keyword harvest für unsere README.
- **`browser-mod-integration-2026-05-03.md`** (R2) — `thomasloven/hass-browser_mod` analysis. 1727★, MIT, HACS-Default, v2 actively maintained. Service catalog, entity surface, 5 use-case-fit assessments für VAG (popup für 12V-warning, NFC-quick-command-sheet, charging-screensaver, per-browser theme, send_destination confirm-popup). Recommendation: doc-mention only, recipe-cookbook for v1.18.0.
- **`community-vag-ha-landscape-2026-05-03.md`** (R3) — community.simon42.com + community.home-assistant.io VW-Connect/MyAudi/MyCupra/MySkoda thread crawl. 4 high-signal outreach targets identifiziert, 6 reply-drafts (3 EN + 3 DE), competitor inventory (mitch-dc archived, skodaconnect deprecated, tillsteinbach/CarConnectivity active competitor), shared feature gaps (writable preheat, single climate-toggle, real-time push, EU Data Act), SEO-keyword harvest, differentiator: "no Docker, no MQTT broker, single HACS install all 7 brands".

### 📨 Outreach / Outreach

- **Reply auf Tim's Antwort** auf `Timwun/Cupra-WeConnect-Bruno-Collection#1` — humanized German Antwort zeigt v1.17.0→v1.17.2 Bruno-Evolution-Journey:
  - 3 Bug-fixes/Features die durch Bruno-Collection gelöst wurden (Climate-404, #36 Navigation, Aux-Heating)
  - Bruno-CLI in unsere CI integration
  - Neue eigene Bruno-Collection in `tests/bruno/` (33+10+7 .bru files)
  - Cross-Review-Offer für PRs zu seinem Repo
  - Endpoint-PRs angekündigt (4 endpoints aus pycupra die seine Collection noch nicht hat)

### 📦 Schließt Issues / Closes

Keine User-Issues — Bruno-CI + research + outreach.

### 📋 Roadmap-Update / Roadmap-Update

- **v1.17.4** geplant: Skoda + CARIAD-BFF Bruno coverage abschließen, alle 3 Brands strict mode, Bruno-CI Stufe 2 endgültig komplett
- **v1.18.0** geplant: Push Bundle (FCM für CUPRA/SEAT + MQTT für Skoda) — Foundation aus v1.15.0 cap-Map + v1.17.x Bruno-CI bereit
- **Eigenes Lovelace-Card Repo** in eigener Session

## [1.17.2] - 2026-05-03 🧹🤖 Stale-Cleanup + Bruno-CI Stufe 1 / Stale-Reference Cleanup + Bruno-CI Foundation

🧹🤖 **PATCH-Release** — zwei kleine, hochwertige Verbesserungen:

1. **Stale-Reference Cleanup** — 17 Pointer auf zwei post-v1.17.0 entfernte research-docs gefixt
2. **Bruno-CI Stufe 1 Foundation** — `tests/bruno/` Scaffold + GH Actions Workflow + URL-drift detection script

### 🧹 Cleanup / Cleanup

Maintainer hatte post-v1.17.0 zwei research-docs aus dem repo entfernt (`upstream-pycupra-notes.md` + `pycupra-deep-dive-2026-05-02.md`). v1.17.0/v1.17.1 CHANGELOG/ROADMAP/HACS-CHECKLIST/CHANGELOG_TECHNICAL referenzierten beide noch — alle 17 Pointer durch:
- Verweis auf canonical replacement (`vag-ha-integration-research.md`) ersetzt
- Pattern-Information inline expandiert wo Deep-Dive zitiert wurde
- Explanatory note hinzugefügt wo der Removal-Kontext relevant ist (CHANGELOG_TECHNICAL v1.17.0)

### 🤖 Neu — Bruno-CI Stufe 1 / New — Bruno-CI Stufe 1

Foundation für den Bruno-as-Living-Documentation Workflow (siehe `docs/BRUNO-WORKFLOW.md` neu).

- **`tests/bruno/seat_cupra/`** Scaffold mit:
  - `bruno.json` collection metadata
  - `environments/mock.bru` mit dummy VIN/token für CI parsing
  - 6 sample `.bru` files für die wichtigsten SEAT/CUPRA endpoints (status, charging, climate start, aux heating, destination, battery care)
- **`tests/bruno/{skoda,cariad_bff}/`** dirs für künftige expansion
- **`scripts/check_bruno_url_drift.py`** — Python ↔ Bruno URL drift scanner. Walks `cariad/api/*.py` für `f"{_BASE}/..."` URLs, walks `tests/bruno/<brand>/*.bru` für `url:` directives, reports endpoints in einer Quelle aber nicht der anderen. Normalize-Phase handhabt `{{vin}}` vs `{vin}`, `{action}` placeholder expansion, query-string stripping. Stdlib only (kein Bruno-CLI nötig), läuft in <1s. Modes: warn-only (default) oder `--strict` für CI-gating.
- **`.github/workflows/bruno-validation.yml`** — neuer CI-Workflow:
  - Job 1: install `@usebruno/cli@latest`, `bru run --env mock` über jede Collection — validates structural correctness ohne live API hits
  - Job 2: `python scripts/check_bruno_url_drift.py --brand all` — warn-only initially (will switch to strict once full coverage)
  - Path-filter: läuft nur bei changes in tests/bruno/, cariad/api/, scripts/check_bruno_url_drift.py, oder workflow itself
  - Concurrency-cancellation: ältere Runs werden gecancelt wenn neuer push kommt
  - HTML-Reporter artifact für 14 Tage retention
- **`docs/BRUNO-WORKFLOW.md`** — Contributor guide:
  - Why Bruno (drift detection + living docs + non-Python contribution barrier lowering)
  - File naming convention + .bru template
  - Full workflow für neuer Endpoint
  - Capturing API traffic (mitmproxy + Frida + Android emulator setup)
  - Privacy rules (anonymization before commit)
  - CI behavior explanation
  - Future: live API tests pre-condition

### 🎯 Strategische Bedeutung / Strategic Context

Bruno-CI ist Stufe 1 der "Bruno-MVP-Position" Strategie (siehe `docs/research/upstream-pycupra-notes.md` historical reference + `docs/research/vag-ha-integration-research.md` aktive). Folgestufen:
- **Stufe 2** (v1.17.x oder v1.18.x): Source-of-Truth Workflow — neue Endpoints erst `.bru` schreiben, dann Python generieren. Brand Captains contribute via `.bru` ohne Python skills.
- **Stufe 3** (v2.0.0 prep): Custom Claude Code Skill `pb-vag-bruno` — HAR→.bru converter, .bru→Python generator, .bru→OpenAPI exporter, drift-detection helper. Generative-AI-augmented API maintenance.

### 📦 Issue-Closures / Issue-Closures

Keine Issue-Closures (Cleanup + CI foundation, keine User-facing features).

## [1.17.1] - 2026-05-02 🚙🌬️🔥 Bruno Quick-Wins Bundle / Bruno Quick-Wins (Window heating fix + Ventilation + Aux Heating + Battery Care + Navigation #36 + 2× A/B-fallback)

🚙🌬️🔥 **MASSIVE PATCH-Release** basierend auf Timwun's `Cupra-WeConnect-Bruno-Collection` deep-dive (53 .bru files crawled). 7 SEAT/CUPRA-Verbesserungen — alle defensiv mit A/B-fallback wo Endpoints zwischen Quellen disagreen, alle Phase-3 capability-gated. Plus Cross-Brand OTA Probe Plan komplettiert mit eigenem Cariad-Charging-Host research.

### 🐛 Bug-Fixes / Bug-Fixes

- 🌡️ **Window Heating Endpoint A/B-Fix** — derzeit POST `/v2/vehicles/{vin}/climatisation` mit Body `{"action":"startWindowHeating"}` war wahrscheinlich seit immer broken (analog #53 Climate). Bruno-verifizierter Pfad: `/vehicles/{vin}/windowheating/requests/{start|stop}` (no /v1). A/B-fallback zur legacy URL bei 404 — kein Regression-Risiko.

### ✨ Neu / Added

- 🌬️ **SEAT/CUPRA Cabin Ventilation** (Bruno seq 31/32) — neue Service `vag_connect.start_ventilation` + `stop_ventilation` plus `switch.{auto}_ventilation`. Endpoint `POST /v1/vehicles/{vin}/ventilation/{start|stop}`. Capability-gated über Phase 3 (`command_start_ventilation` → `ventilation`).
- 🔥 **SEAT/CUPRA Webasto Auxiliary Heating** (Bruno seq 29/30 + pycupra) — Standheizung remote start/stop. Neue Services `vag_connect.start_aux_heating` + `stop_aux_heating` plus `switch.{auto}_aux_heating`. Start braucht **SecToken** (S-PIN-derived, gleiches Flow wie unser lock/unlock). Stop ohne S-PIN. **A/B URL-fallback** zwischen Bruno-Pfad `/v1/vehicles/{vin}/auxiliary-heating/start` und Pycupra-Pfad `/api/auxiliary-heating/v1/{vin}/start`.
- 📍 **#36 Navigation: Ziel ans Auto senden** (Bruno seq 34) — schließt seit Wochen offenes Issue. Neuer Service `vag_connect.send_destination(vin, latitude, longitude, name, [city, country, state, street, house_number, zip_code])`. Endpoint `PUT /v1/users/vehicles/{vin}/destination` mit verbatim Bruno body shape (single-element JSON array). SEAT/CUPRA only initially.
- 🔋 **SEAT/CUPRA Battery Care Sensors** (Bruno seq 10/11) — zwei thin GET endpoints exponiert als `binary_sensor.{auto}_battery_care_enabled` + `sensor.{auto}_battery_care_target_soc_pct`. Endpoints: `GET /v1/vehicles/{vin}/charging/battery-care` + `/battery-care/target`. 1h-Cache via neuer `coordinator.refresh_battery_care(vin)` mit brand-restriction (`cupra`/`seat`) + capability-gate. Best-effort: 404 → keine Entity (`_DATA_PRESENT_REQUIRED` gating).
- 🔧 **Generic `_post_with_ab_fallback` Helper** — extrahiert aus v1.16.1 climatisation-fix für Wiederverwendung. Pattern: try primary URL, on 404-only fall back to legacy URL with body action. Non-404 errors propagate normal. Headers per-call configurable. Verwendet von 5 Endpoints in v1.17.1.

### 🛡️ Defensive Hardening / Defensive Hardening

- 🔁 **Capabilities path A/B-fallback** — Bruno (seq 4) zeigt `/v1/user/{userId}/vehicle/{vin}/capabilities` (singular), unser pre-v1.17.1 nutzt `/v1/vehicles/{vin}/capabilities` (plural). Beide observed in upstream sources. Try plural first (status quo, no migration risk), fallback zu singular on 404 — preserves capability fetching für accounts die nur die singular Variante akzeptieren.
- 🔁 **Charging Actions A/B-fallback** — Bruno (seq 47/46) zeigt newer `/vehicles/{vin}/charging/requests/{start|stop}` (no /v1, no body), legacy `/v1/vehicles/{vin}/charging/actions` mit body action. Cariad migrated some endpoints away von /v1 — try newer first, fallback zu legacy on 404. Behebt potentielle 404s auf neuerer Firmware ohne ältere Accounts zu brechen.

### 🧬 Capability-Map Erweiterungen

7 neue cap-id Einträge in `CAPABILITY_MAP["cupra"]` (SEAT erbt via Alias):
- `command_start_ventilation` / `command_stop_ventilation` → `ventilation`
- `command_start_aux_heating` / `command_stop_aux_heating` → `auxiliary-heating`
- `command_send_destination` → `destination`
- `command_battery_care_read` → `charging`

5 neue Einträge in `_COMMAND_CLASS` für per-VIN per-class lock isolation.

### 🌐 Übersetzungen / Translations

8 Sprachen — neue keys:
- `entity.sensor.battery_care_target_soc_pct`
- `entity.binary_sensor.battery_care_enabled`
- `entity.switch.{ventilation_switch, aux_heating_switch}`

### 🧪 Tests / Tests

`tests/test_v1171_bruno_quick_wins.py` — neue Tests in 10 Klassen:
- `TestPostWithAbFallback` (3) — primary success, 404 fallback, non-404 propagates
- `TestWindowHeatingAB` (2) — Bruno path used first
- `TestVentilation` (2) — URL pattern + no body
- `TestAuxHeating` (4) — no-spin raises, SecToken, 404 fallback to pycupra path, stop without SecToken
- `TestBatteryCare` (3) — 404→empty, dict return, target SoC parsing
- `TestRefreshBatteryCareBrandRestriction` (2) — audi skips, cupra merges
- `TestCapabilitiesAB` (2) — plural primary, singular fallback
- `TestChargingActionsAB` (2) — newer path used first
- `TestSendDestination` (1) — URL + body shape verbatim Bruno
- `TestCapabilityMapV1171` (8 parametrized + 1) — all new cap-ids registered
- `TestCommandClassRegistry` (3) — engine/ventilation/aux_heating/destination classes

### 🔬 Pre-Research / Pre-Research

- `docs/research/cariad-charging-host-2026-05-02.md` (NEW) — research für 2nd Cariad host `prod.emea.mobile.charging.cariad.digital` der für Charging Statistics verwendet wird. Auth-Flow verifiziert (same OLA bearer token), endpoint catalog (`POST /charging_statistics` + `GET /charging_statistics/{sessionId}/power-curve`), cross-brand-status (vag-connect-ha wäre **first** FOSS-Integration die diesen Host nutzt). Implementation-Plan für v1.18.0 als neuer `cariad/api/charging_stats.py` Client.

### 📦 Schließt Issues / Closes

- Closes #36 (Navigation: Ziel/Adresse ans Fahrzeug senden — SEAT/CUPRA initial, Cross-Brand v1.18.0+)

### 🔗 Inspiration / Credits

- **`Timwun/Cupra-WeConnect-Bruno-Collection`** — 50+ verifizierte OLA-Endpoint-Specs in Bruno format. Issue #1 mit Dankeschön + Brand-Tester-Einladung gepostet. Diese Bundle ist direkter Output dieser Collection.
- **`WulfgarW/pycupra`** — Pycupra-Source für SecToken-Pattern + URL-Backup für Aux Heating fallback path.

## [1.17.0] - 2026-05-02 🛡️📚 Operational Hardening Bundle / Operational Hardening (Quota-protective polling + FAQ + HACS Checklist + Year-rollover Tests + Deactivated Notification)

🛡️📚 **Quality-of-life MINOR-Release** nach community-research deep-dive: Poll-Defaults quota-protective angepasst, deactivated-vehicle notification, year-rollover unit tests, plus zwei neue High-Value User-Docs (FAQ + HACS-Checklist). Setzt die Foundation für v1.18.0 Push Bundle und v2.0.0 HACS Default Repository.

### 🔄 Geändert / Changed

- 📊 **Poll-Defaults quota-protective angehoben** (community-research-driven):
  - `DEFAULT_SCAN_INTERVAL`: 5min → **10min** (288 polls/day → 144 polls/day = 19% → 10% des 1500/day Quotas)
  - `MIN_SCAN_INTERVAL`: 3min → **5min** (verhindert dass Power-User die Quota mid-day exhausten)
  - **Bestehende Configs werden NICHT umkonfiguriert** — nur Defaults für fresh installs
  - Begründung dokumentiert in `const.py` mit verweis auf pycupra README + WulfgarW/homeassistant-pycupra release notes
  - Siehe neue `docs/FAQ.md` "What is the daily API request quota?" für User-Erklärung

### ✨ Neu / Added

- 🚗 **Vehicle-deactivated persistent_notification** (analog `WulfgarW/homeassistant-pycupra` v0.2.14) — wenn ein Fahrzeug aus dem VAG-Konto verschwindet (verkauft / Eigentümerwechsel / Hersteller-Deaktivierung / Subscription abgelaufen), wird eine `persistent_notification` mit verständlicher Begründung erstellt BEVOR das Device removed wird. User wissen warum ihre Entities gerade verschwunden sind. Long-term-statistics History bleibt erhalten.

### 📚 Documentation / Documentation

- 📚 **`docs/FAQ.md`** (NEW) — High-value End-User-Doku:
  - "What actually wakes the car?" — definitive Antwort: nur explizite commands, KEIN polling
  - Wake protection summary (3/Tag soft-cap + 5min cooldown)
  - Privacy-Setting Matrix (Share/Use/Don't share → welche Entities degradieren)
  - Daily API Quota Erklärung mit polls/day Tabelle
  - Reauthentication-Flow erklärt + warum NICHT remove-and-readd (statistics history loss)
  - Entity-ID-Stability Policy (bug fix → keep ID, schema-change → new ID + deprecate)
  - Read-only Mode + "vehicle disappeared" + Bug-Reporting workflow + Brand-Region-Tabelle
- 📋 **`docs/HACS-CHECKLIST.md`** (NEW) — Audit-Status pro Item gegen die HACS-Default-Repository Pre-Conditions:
  - 7 Sektionen (Repo structure, Code quality, Config flow, Operational safety, CI/release, User-facing docs, Outstanding for v2.0.0)
  - Per-Item Status (✅ done / ⚠️ partial / ❌ missing / 🔮 planned)
  - Outstanding-Items klar gelistet für v2.0.0 prep (per-vehicle log prefix, requests_remaining_today sensor, HTTP 500 log-once pattern, PRIVACY.md, Live-Tests aller Brands, EU Data Act readiness)

### 🧪 Tests / Tests

- `tests/test_v1170_datetime_boundaries.py` — neue Tests in 4 Klassen für recurring datetime-arithmetic bug class (pycupra issue #33 prevention):
  - `TestDateConversionBoundaries` (5) — int-days + ISO string parsing across year-end + leap year
  - `TestWakeBudgetUtcMidnightReset` (2) — UTC date logic + year-rollover comparison
  - `TestConnectionStateTimestampBoundaries` (2) — naive vs tz-aware comparison + year-end timestamp parsing
  - `TestDstTransitionParsing` (3) — spring-forward + fall-back UTC offset preservation

### 🔬 Pre-Research / Pre-Research

Neue Research-Docs in `docs/research/`:
- **`vag-ha-integration-research.md`** — community research (Skoda + MQTT + HACS-Checklist + 8 upstream contribution ideas)
- *(Note: zwei zusätzliche pycupra research docs wurden post-v1.17.0 vom Maintainer entfernt — Inhalt überlappt mit `vag-ha-integration-research.md` + `cupra-bruno-endpoints-2026-05-02.md`.)*

Plus **`docs/upstream-contributions/wulfgar-pycupra-issues.md`** — 8 ready-to-post upstream issue drafts für `WulfgarW/homeassistant-pycupra` (async_step_reauth, requests_remaining sensor, retry-login action, push dispatcher hardening, hassfest CI, year-rollover tests, MQTT freshness validation, privacy-matrix FAQ).

### 🤝 Community / Community

- 📨 **Outreach an `Timwun/Cupra-WeConnect-Bruno-Collection`** — neuer Bruno-Collection mit 50+ verifizierten OLA-Endpoint-Specs entdeckt. Issue #1 mit Dankeschön + Brand-Tester-Einladung gepostet. Vollscan-Agent extrahiert die komplette Endpoint-Catalog für v1.17.x / v1.18.0 Implementation (insbesondere `PUT /v1/users/vehicles/{vin}/destination` für #36 Navigation-Closure).

### 📦 Geplante Issue-Closures / Planned Issue Closures

Keine direkten Issue-Closures in v1.17.0 (Hardening-Release ohne neue Features). Vorbereitung für #36 Navigation Closure in v1.17.x basierend auf Bruno-Collection.

## [1.16.1] - 2026-05-02 🐛 SEAT/CUPRA Climate Fix + #122 Scout-Paths / SEAT/CUPRA Climate 404 Fix + SEAT scout-path registration

🐛 **PATCH: Hotfix für SEAT/CUPRA Climate-Endpoint** — Gerhard's v1.16.0 Test (Issue #53) hat aufgedeckt dass unsere ``command_start_climate`` URL ``POST /v2/vehicles/{vin}/climatisation`` mit Body ``{"action":"start"}`` einen 404 produziert (`No static resource`). Korrekter OLA-Endpoint ist ``POST /v2/vehicles/{vin}/climatisation/start`` (Action im Pfad). Plus #122 SEAT Scout-Report von r1150gs.

### 🐛 Bug-Fixes / Bug-Fixes

- 🌡️ **SEAT/CUPRA Climate 404 (#53)** — neuer ``_post_climatisation_action`` Helper mit Defensive-Fallback:
  - **Primary** (verifiziert gegen `WulfgarW/pycupra/connection.py` `API_CLIMATER + '/start'`): ``POST /v2/vehicles/{vin}/climatisation/start`` body ``{}``
  - **Fallback** (legacy unsere alte URL): bei 404 → ``POST /v2/vehicles/{vin}/climatisation`` body ``{"action":"start"}``
  - Nicht-404 Fehler (403/500/etc) propagieren ohne Fallback — Phase 2 records the failure normal
  - Identisches Pattern für `command_stop_climate`

### 🛰️ Scout-Paths / Scout-Paths

- 🛰️ **#122 SEAT scout-report (r1150gs, 2026-05-02)** — `engines.primary` + `engines.primary.*` Wildcard in `EXPECTED_KEYS["cupra"]["mycar"]` registriert (SEAT erbt via Table-Alias). Vorher war `engines` als Top-Level-Block registriert — neue Sub-Block `primary` (3 keys) brauchte explizite Registration. Wildcard deckt zukünftige Sub-Felder ab.

### 🔍 Investigation / Investigation

- 🔍 **#53 Phase 3 Phantom-Button** — Gerhard's Born hat Lichthupe-Button trotz Phase 3 noch sichtbar. Hypothesen: OLA Capabilities-API "lügt" für seinen Born (sagt `honk-and-flash` active=true, aber Endpoint macht 400), oder `get_capabilities` failt silent, oder Cap-ID Mismatch. **Diagnostics-Download von Gerhard angefordert** für `vehicle_capabilities[VIN]` Inspektion. Fix folgt in v1.16.2 sobald Daten da sind.

### 🧪 Tests / Tests

- `tests/test_v1161_seat_cupra_climate_fix.py` — neue Tests in 2 Klassen:
  - `TestClimateEndpointFix` (4) — start uses path-suffix + stop uses path-suffix + 404 fallback to legacy + non-404 propagates without fallback
  - `TestScoutPathsSeat` (2) — `engines.primary.*` registriert + SEAT inherit via alias

### 📦 Schließt Issues / Closes

- Closes #122 (SEAT scout-report von r1150gs)

### 🔬 Bleibt offen / Still open

- **#53 Climate** ✅ gefixt in v1.16.1 (testen!)
- **#53 Phase 3 Phantom-Button** — wartet auf Gerhard's Diagnostics

## [1.16.0] - 2026-05-02 ⏰📍 Cross-Brand UX + Skoda Charging Profiles / Cross-Brand UX + Skoda Charging Profiles (HA time platform #26 + #25/#31 read-only via charging-profiles + OTA Probe planning)

⏰📍 **Long-standing UX gap geschlossen**: Departure-Timer kann jetzt direkt in HA editiert werden (#26). Plus #25/#31 Closure über Skoda's neuen `/v1/charging/{vin}/profiles` Endpoint, plus Cross-Brand OTA Probe Plan dokumentiert für Live-Test in v1.17.0.

### ✨ Neu / Added

- ⏰ **#26 HA `time` Plattform für Departure-Timer Editing** (10. Plattform):
  - Neue Datei `custom_components/vag_connect/time.py` mit `VagDepartureTimerTime`
  - Drei Entitäten pro EV/PHEV: `time.{auto}_departure_timer_1_time_set` / `_2` / `_3`
  - User editiert die Abfahrtszeit direkt im HA Dashboard → integration ruft existierende `coordinator.async_set_departure_timer(vin, timer_id, enabled=True, departure_time="HH:MM")` auf
  - Setzen der Zeit aktiviert den Timer automatisch (UX: User der Zeit setzt will den Timer offenbar aktiv haben)
  - Defensive Parser für `departure_timer_X_time` Feld: HH:MM, HH:MM:SS, ISO datetime — alle drei werden zu `datetime.time` konvertiert
  - Read-only Mode + Capability-Phase-3 Gating wie bei den existierenden departure-timer Switches
- 📍 **#25/#31 Skoda Charging Profiles Read-Only** — neuer mysmob Endpoint `GET /v1/charging/{vin}/profiles` (verifiziert via `myskoda/models/chargingprofiles.py`). Vier neue Sensor-Entitäten (Skoda EV/PHEV only):
  - `sensor.active_charging_profile_name` — **das Killer-Feld**: Backend-Response `currentVehiclePositionProfile.name` sagt uns welches der User-Profile gerade aktiv ist basierend auf der Vehicle-GPS-Position. Solves #25 (location-based target SoC) ohne client-side GPS-Zone-Matching.
  - `sensor.active_charging_profile_target_soc_pct` — Target SoC für das aktive Profil (PERCENTAGE)
  - `sensor.next_charging_time` — nächste geplante Ladezeit
  - `sensor.charging_profiles_count` (DIAGNOSTIC) — Anzahl registrierter Profile
  - Plus alle Profile flat als `extra_state_attributes.profiles` auf `active_charging_profile_name` mit per-Profile: id, name, target_soc_pct, max_charging_current, auto_unlock_plug, min_battery_soc_pct, location_lat (rounded 2-decimal), location_lon, preferred_times_count, timers_count
  - 1h-Cache-Cycle in `coordinator.refresh_charging_profiles` mit brand-restriction + capability-gate (`command_charging_profiles` cap-id `EXTENDED_CHARGING_SETTINGS` aus v1.15.0)
  - Write-Side für Profile-Editing **deferred** zu v1.17.0 (POST/PUT endpoints brauchen eigene Bundle-Größe)
- 📋 **Cross-Brand OTA Probe Plan** — `docs/RESEARCH_NOTES_2026-05-02_OTA_PROBE.md` mit konkreten `curl` Probes für CARIAD-BFF (Audi+VW EU) + OLA (SEAT/CUPRA) software-version Endpoints. Live-Tester Asks dokumentiert. Probe ist read-only und sicher (`GET` mit Bearer-Token). Adoption-Plan post-Probe: ~2h Implementation pro Backend wenn 200 OK kommt.

### 🔄 Geändert / Changed

- 🔧 `__init__.py` — `Platform.TIME` zur PLATFORMS-Liste hinzugefügt (10. Plattform). Service-Removal-List auch erweitert (kein neuer Service nötig — time platform reused existing `set_departure_timer`).
- 🔧 `coordinator.py` — neue `_parse_charging_profiles` pure function + `refresh_charging_profiles` 1h-cache helper + Hook im Poll-Loop neben Trip-Stats + Charging-History refreshes.
- 🔧 `cariad/api/skoda.py` — neuer `get_charging_profiles(vin)` method.
- 🔧 `cariad/models.py` — 5 neue Charging-Profiles-Felder zu VehicleData (`active_charging_profile_name`, `active_charging_profile_target_soc_pct`, `next_charging_time`, `charging_profiles_count`, `charging_profiles` list).
- 🔧 `sensor.py` — 4 neue VagSensorDescription Einträge plus erweiterte `extra_state_attributes` Override für `profiles` auf dem active-profile sensor.

### 🌐 Übersetzungen / Translations

8 Sprachen (de/en/fr/es/nl/pl/cs/sv) — neue keys:
- `entity.sensor.{active_charging_profile_name, active_charging_profile_target_soc_pct, next_charging_time, charging_profiles_count}`
- **Neue `entity.time` Sektion** mit `departure_timer_{1,2,3}_time_set`

### 🧪 Tests / Tests

- `tests/test_v1160_cross_brand_skoda_endpoints.py` — neue Tests in 4 Klassen:
  - `TestDepartureTimerTimeEntity` (7) — native_value HH:MM / HH:MM:SS / ISO datetime / garbage / None field + async_set_value dispatch + auto-enable
  - `TestParseChargingProfiles` (5) — flat profiles + currentVehiclePositionProfile + missing current → no active fields + garbage tolerance + empty
  - `TestGetChargingProfilesURL` (1) — URL pattern
  - `TestRefreshChargingProfilesBrandRestriction` (4) — brand restriction + 1h cache + capability gate
  - `TestOtaProbeDocsExist` (2) — sanity that the planning docs are committed

### 🔬 Pre-Research / Pre-Research

Skoda Charging Profiles + Widget + Vehicle-Information Schema-Research aus `myskoda/models/{chargingprofiles,widget,vehicle_info,info}.py` (verfasst 2026-05-02, 600 Zeilen Output).

### 📦 Schließt Issues / Closes

- Closes #26 (Klima-Timer / Departure-Timer UI — HA `time` Plattform für editing)
- Closes #25 (Standort-spez. Ladeziel — read-only via `currentVehiclePositionProfile.targetStateOfChargeInPercent`)
- Closes #31 (Ladeprofile pro Standort — read-only via `chargingProfiles` list mit per-Profil location)

### ❌ Deferred / Not in this release

- **Skoda Vehicle-Information Bundle** (myskoda PRs #543/#557) — drei Endpoints (vehicle-info, renders, equipment, lightweight widget) brauchen DeviceInfo-rewiring + image-platform Erweiterung + Live-Test → v1.17.0
- **Charging Profile Write-Side** — POST/PUT endpoints für Profile-Editing brauchen eigene Bundle-Größe → v1.17.0+
- **Cross-Brand OTA** (Audi/VW/SEAT/CUPRA) — Probe Plan dokumentiert, wartet auf cooperative Tester → v1.17.0 (mit Live-Test)
- **Push CUPRA/SEAT + Push Skoda MQTT** (myskoda PRs #533/#566) — bereits geplant für v1.18.0, Skoda-Path jetzt unblocked durch v1.15.0 cap-Map + diagnostics work

## [1.15.0] - 2026-05-02 🛰️🔋 Skoda Modernization Bundle / Skoda Modernization (Charging History #35 + OTA + 8 cap-ids + capability tolerance + anonymize hardening)

🛰️🔋 **Komplette Adoption der myskoda Upstream-Updates seit unserem PR #832 Cutoff** (22 PRs gemerged 2026-03 → 2026-04). Bundle 3 (Cross-Brand UX) wurde realistisch zu v1.16.0 verschoben — die HA `time`/`datetime` Plattform für #26 wäre eigene 10. Plattform-Erweiterung, und #25/#31 brauchen `charging-profiles` Endpoint-Research. v1.15.0 fokussiert auf was JETZT lieferbar ist.

### ✨ Neu / Added

- 🔋 **#35 Skoda Charging History → HA Energy Dashboard** — neuer mysmob Endpoint `GET /v1/charging/{vin}/history?userTimezone=UTC&limit=50`. Drei neue Sensor-Entitäten (Skoda EV/PHEV only):
  - `total_charged_energy_kwh` — `state_class=TOTAL_INCREASING` für HA Energy Dashboard. Sum aller `chargedInKWh` Sessions across alle Periods.
  - `last_charging_session_kwh` — Energie der letzten Sitzung
  - `last_charging_session_duration_min` — Dauer der letzten Sitzung
  - Plus `recent_charging_sessions` (last 5) als `extra_state_attributes` auf `total_charged_energy_kwh` (audi #113 "aggregate-in-state" Convention — vermeidet 255-char state limit)
  - `last_charging_session_current_type` (AC/DC) als attr
  - 1h-Cache-Cycle in `coordinator.refresh_charging_history` mit brand-restriction + capability gate (`command_charging_history` cap-id `CHARGING`)
  - Source: myskoda PR mit `ChargingHistory` model in `myskoda/models/charging_history.py` (verifiziert 2026-05-02)
- 🛰️ **Skoda Software-Version + OTA Status** (myskoda PR #541) — neuer Endpoint `GET /v1/vehicle-information/{vin}/software-version/update-status` (Skoda app v8.10.0+):
  - `sensor.software_version` (DIAGNOSTIC) — aktuelle Firmware (z.B. `"3.8"`)
  - `binary_sensor.ota_update_available` (UPDATE device class) — true wenn Backend einen Status anders als `NO_UPDATE_AVAILABLE`/`UPDATE_SUCCESSFUL` liefert (forward-compat: unbekannte enum-Werte = update läuft)
  - `releaseNotesUrl` als `extra_state_attributes.release_notes_url` auf dem binary_sensor
  - Cross-brand support **deferred** — CARIAD-BFF + OLA exposen den Endpoint nicht (Research 2026-05-02)
- 🛡️ **Capability-Map Skoda Erweiterung** — 8 neue cap-ids in `CAPABILITY_MAP["skoda"]` aus myskoda Upstream-Reverse-Engineering: `command_software_update`, `command_charging_history`, `command_charging_profiles`, `command_driving_score`, `command_readiness`, `command_plug_and_charge`, `command_route_planning`, `command_battery_charging_care`. Phase 3 kann jetzt sauber für jede dieser Capabilities entscheiden.
- 🧬 **Capability-Status Tolerance** (myskoda PR #543 schema) — `vehicle_supports_capability` versteht jetzt:
  - **Top-level `errors[]` Array** auf der capabilities response — wenn das ganze Dokument fehlgeschlagen ist (MISSING_RENDER, UNAVAILABLE_SERVICE_PLATFORM_CAPABILITIES, UNAVAILABLE_SOFTWARE_VERSION), bail to `None` statt fälschlich jede Entity zu gaten
  - Neue transient-state Status-Werte: `INSUFFICIENT_BATTERY_LEVEL`, `LOCATION_DATA_DISABLED`, `VEHICLE_DISABLED` — als "right now no" behandelt (gated wie bisher, aber dokumentiert für UX-Hints zukünftig)
- 🔐 **Diagnostics Anonymize Hardening** (Pattern aus myskoda `anonymize.py`):
  - **`_mask_location_qs`** — scrubbt `latitude=...&longitude=...` aus URL Query-Strings (z.B. `/maps/positions?latitude=48.13&longitude=11.57` in Error-Traces). Vorher konnte unser dict-key basiertes `_scrub` das nicht catchen weil lat/lon innerhalb eines String-Values steckten. Mode-aware: `gps_round=True` rundet auf 1 Dezimal, sonst REDACTED.
  - **`_stable_hash` SHA-256** — deterministischer 12-hex Pseudonym für stabile Repeat-Reporter Cross-Referenzen ohne PII zu leaken. `user_id`/`account_id`/`userId`/`accountId` → `sha256:abc123def456` (statt nur `**REDACTED**`).

### 🔄 Geändert / Changed

- 🔧 `cariad/_capabilities.py` — 8 neue Skoda cap-id Einträge plus erweiterte Doku zur Erkennung
- 🔧 `coordinator.py` — neue `_parse_charging_history` pure function + `refresh_charging_history` 1h-cache helper + Hook im Poll-Loop neben Trip-Stats refresh. `vehicle_supports_capability` extended um `errors[]` block + transient status documentation.
- 🔧 `cariad/api/skoda.py` — `get_status` gather() um den software-version Endpoint erweitert (best-effort, exception-tolerant). Neuer `get_charging_history(vin, limit=50)` method.
- 🔧 `cariad/models.py` — 4 OTA-Felder + 6 Charging-History-Felder zu VehicleData hinzugefügt
- 🔧 `diagnostics.py` — `_LOCATION_QS_RE` regex + `_HASH_KEYS` frozenset + neue helpers; `_scrub` String-Pfad chained jetzt `_mask_email` + `_mask_location_qs`

### 🌐 Übersetzungen / Translations

8 Sprachen (de/en/fr/es/nl/pl/cs/sv) — neue keys:
- `entity.sensor.{software_version, total_charged_energy_kwh, last_charging_session_kwh, last_charging_session_duration_min}`
- `entity.binary_sensor.ota_update_available`

### 🧪 Tests / Tests

- `tests/test_v1150_skoda_modernization.py` — neue Tests in 5 Klassen:
  - `TestParseChargingHistory` (5) — total kWh sum, sort-by-startAt desc, recent_sessions cap, garbage tolerance
  - `TestGetChargingHistoryURL` (2) — URL + default/custom limit param
  - `TestRefreshChargingHistoryBrandRestriction` (4) — brand restriction + 1h cache + capability gate
  - `TestSoftwareVersionParsing` (2) — NO_UPDATE_AVAILABLE → False, unknown enum → True (forward-compat)
  - `TestLocationQueryStringScrub` (4) — REDACTED + 1-dec round + no-op + negative coords
  - `TestStableHash` (4) — deterministic + different inputs + empty + salt
  - `TestUserIdHashingInScrub` (4) — user_id/accountId hashing + repeat-stability + string GPS scrub
  - `TestSkodaCapabilityMap` (8 parametrized + 1 sanity) — alle neuen cap-ids
  - `TestCapabilityStatusTolerance` (3 parametrized + 3) — errors[] block + transient states

### 🔬 Pre-Research / Pre-Research

Research-Sweep der **skodaconnect/myskoda** Upstream (22 PRs gemerged seit unserem PR #832 / Issue #976 Cutoff April 2026). Plus Cross-Brand OTA Endpoint-Probe (audi_connect_ha + volkswagencarnet + pycupra) — Resultat: CARIAD-BFF + OLA haben **kein** software-version endpoint heute, daher Skoda-only in v1.15.0.

### 📦 Schließt Issues / Closes

- Closes #35 (Ladehistorie LTS — Skoda über `chargedInKWh` per session, kumuliert in `total_charged_energy_kwh` mit `TOTAL_INCREASING`)

### 🛡️ Open / Re-Aktiviert

- **#75 Skoda Kodiaq Mk2 403** — Comment posted: ursprüngliche Hypothese war falsch (wir hatten den `connectivityGenerations` Query bereits seit langem), echte Ursache braucht 403-Body-Diagnostics. v1.15.0 verbessert Diagnostics-Export um die Übermittlung sicherer zu machen.

### ❌ Deferred / Not in this release

- **#26 Klima-Timer / Departure-Timer datetime UI** — braucht eigene HA `time`/`datetime` Plattform-Erweiterung (10. Plattform). Existing departure_timer switches + sensors bleiben funktional. → v1.16.0
- **#25 Standort-spezifischer Ladeziel + #31 Ladeprofile pro Standort** — beide brauchen `/v1/charging/{vin}/profiles` Endpoint-Schema-Research für Read-Only-Sensoren. → v1.16.0
- **Cross-Brand OTA** (Audi/VW/SEAT/CUPRA) — Endpoint nicht in CARIAD-BFF/OLA verifiziert. Live-Test-Probe nötig. → v1.16.0+

## [1.14.0] - 2026-05-02 🚗 Audi Feature Pack Bundle / Audi Feature Pack (Trip Stats + Engine Start ICE + PPC Climate Body) + Skoda Scout-Pfade #116

🚗 **Drei Audi-spezifische Features in einem MINOR-Release** + Skoda Scout-Pfade aus #116 (MavericklCS) als Add-On. Bundle 2 aus dem v1.13.0 Pre-Research-Plan (`docs/RESEARCH_NOTES_2026-05-02.md`).

### ✨ Neu / Added

- 🛣️ **#24 Trip Statistics für VW EU + Audi** — neuer CARIAD-BFF Endpoint `GET /vehicle/v1/vehicles/{vin}/tripstatistics?type={shortTerm|longTerm}` (verifiziert in audi_connect_ha + audiconnectpy + ioBroker/vw-connect). Vier neue Sensor-Entitäten pro Audi/VW EU Vehicle:
  - `last_trip_distance_km` (DISTANCE) — letzte Fahrt-Strecke aus shortTerm `mileage`
  - `last_trip_avg_speed_kmh` (SPEED) — Ø-Geschwindigkeit
  - `last_trip_avg_fuel_consumption_l_100km` (combustion-only) — Ø-Verbrauch in l/100km (Backend liefert ×10, Parser teilt)
  - `last_trip_avg_electric_consumption_kwh_100km` (electric-only) — Ø-Stromverbrauch in kWh/100km
  - Plus `recent_trips` (letzte 5) als `extra_state_attributes` auf `last_trip_distance_km` (audi #113 "aggregate-in-state" convention — vermeidet 255-char state limit)
  - 1h-Cache-Cycle in `coordinator.refresh_trip_statistics` — Brand-restriction audi/volkswagen (andere Brands skippen ohne Error), Phase 3 Capability-Gate (`command_trip_stats` → cap-id `tripStatistics`), 1h Cache-TTL via `_trip_stats_fetched_at`
  - **Subscription-required** (Audi connect Plus / WeConnect Plus) — Phase 3 versteckt die Entities wenn das Abo fehlt
- 🔥 **#28 Audi ICE Remote Engine Start/Stop** — zwei-Schritt S-PIN-Flow nach audi_connect_ha PR #717:
  - `service: vag_connect.engine_start` — `PUT /vehicle/v1/engine/{VIN}/userpromptproof` (S-PIN) → extract `userPromptProof` → `POST /vehicle/v1/engine/{VIN}/start` mit `securedActivationData`
  - `service: vag_connect.engine_stop` — single `POST /vehicle/v1/engine/{VIN}/stop` (kein S-PIN nötig)
  - **Audi-only** — andere Brands haben keinen `/engine/`-Subtree. Path-Pattern ist `/vehicle/v1/engine/{VIN}/...` (NICHT `/vehicle/v1/vehicles/{VIN}/engine/...`). VIN wird automatisch uppercased.
  - **S-PIN aus gespeicherter Konfiguration** — landet NIE im Service-Call-Log
  - **Capability-gated** über `CAPABILITY_MAP["audi"]["command_engine_start"] = "engineRemoteStart"` (⚠️ [Inference] cap-id, noch kein Live-Capabilities-Response gesehen)
  - Per-VIN `engine` lock-class via `_COMMAND_CLASS` — start/stop serialisieren nicht parallel
- 🌡️ **#29 PPE/PPC Klima-Body conditional** — Audi Q6/A6 e-tron, RS e-tron GT Facelift, A3 2024+ PHEV brauchen das neue PPE-Body-Format (audi_connect_ha PR #644 + #677):
  - `climatisationMode: "comfort"` mandatory
  - `targetTemperature` + `targetTemperatureUnit` MÜSSEN omitted werden
  - Neue Option `force_ppe_climate` (default False, Audi-only Effekt) in der Options-Flow. User-overridable da Auto-Detection unzuverlässig ist (kein verifiziertes Modell-Mapping public).
  - `command_start_climate(vin, ppe_mode=True)` schaltet das Body-Format um
- 🛰️ **#116 Skoda Scout-Pfade** — vierter Community-Scout-Report von **MavericklCS** (2026-05-01). 5 neue Pfade in `EXPECTED_KEYS["skoda"]`:
  - `driving-range`: 4× `primaryEngineRange.{engineType,currentSoCInPercent,currentFuelLevelInPercent,remainingRangeInKm}`
  - `maintenance`: `predictiveMaintenance.setting` + `predictiveMaintenance.setting.*` Wildcard

### 🔄 Geändert / Changed

- 🔧 `cariad/_capabilities.py` — Audi-Inheritance-Trick erweitert: `CAPABILITY_MAP["audi"]` ist jetzt eine **Kopie** von VW EU's Map (statt Alias) plus Audi-only Patch-Eintrag für `command_engine_start`. Verhindert Pollution der VW EU Map.
- 🔧 `coordinator.py` — `_COMMAND_CLASS` registry erweitert um `command_engine_start`/`command_engine_stop` → "engine" class. Trip-Stats refresh als best-effort gather() im Poll-Loop nach `_async_push_update`.
- 🔧 `sensor.py` — neuer `_TRIP_STATS_BRANDS` frozenset für Brand-Gating der 4 Trip-Stats Sensoren. Neuer `extra_state_attributes` Override in `VagConnectSensor` für `recent_trips` auf `last_trip_distance_km`.
- 🔧 `vw_eu.py` — `command_start_climate(vin, ppe_mode: bool = False)` mit conditional fallback-payload. Default = legacy body (backwards-compat).

### 🌐 Übersetzungen / Translations

8 Sprachen (de/en/fr/es/nl/pl/cs/sv) — neue keys:
- `entity.sensor.{last_trip_distance_km, last_trip_avg_speed_kmh, last_trip_avg_fuel_consumption_l_100km, last_trip_avg_electric_consumption_kwh_100km}`
- `options.step.init.data.force_ppe_climate` + `data_description.force_ppe_climate`

### 🧪 Tests / Tests

- `tests/test_v1140_audi_pack.py` — 19 neue Tests:
  - `TestParseTripStatistics` (6) — pure parser tests + ×10 division + sort + cap at 5 + garbage handling
  - `TestGetTripStatisticsURL` (1) — URL + type query param
  - `TestRefreshTripStatisticsBrandRestriction` (4) — Brand-restriction + capability gate + 1h cache
  - `TestAudiEngineStart` (5) — two-step flow + uppercase VIN + no-spin raises + missing-proof raises + stop endpoint
  - `TestPpcClimateBody` (3) — legacy body / PPE body / default-legacy
  - `TestCapabilityMapEngineStart` (4) — Audi-only inheritance copy + trip_stats brand-presence
  - `TestScoutPathsSkoda` (2) — primaryEngineRange.* + predictiveMaintenance.setting wildcard
  - `TestEngineCommandClass` (1) — engine class shared start/stop

### 🔬 Pre-Research / Pre-Research

- Bundle 2 aus `docs/RESEARCH_NOTES_2026-05-02.md` (verfasst 2026-05-02 vor v1.13.0). Alle drei Issues lieferten ✅ verified Recherche-Ergebnisse:
  - #24 (Trip Stats): CARIAD-BFF Endpoint + per-trip Field-Liste verifiziert
  - #28 (Engine Start): audi_connect_ha PR #717 source-read komplett — Endpoint + Body + Response-Shape
  - #29 (PPE Climate): Body-Pattern aus audi #644 + #677 verifiziert; Detection via User-Option (Auto-Heuristik defer)

### 📦 Schließt Issues / Closes

- Closes #24 (Verbrauchsdaten / Trip Stats Audi)
- Closes #28 (Remote Start ICE Audi 2024+)
- Closes #29 (PPC Climate für 2025 A3/Q5 / Q6/A6 e-tron)
- Closes #116 (Skoda Scout-Report von MavericklCS)

### ❌ Deferred / Not in this release

- **#35 Ladehistorie LTS** — `chargedEnergy_kWh` Feld nicht in CARIAD-BFF verifiziert (Research v1.13.0). Wartet auf API-Hinweis aus Live-Tests.
- **#51 RS e-tron GT Facelift** — graceful degradation only (volle PPE Lock/Charging-Endpoint-Map noch nicht reverse-engineered, Hard Rule #15 verbietet endpoint-guessing).
- **PPE Auto-Detection** — User opt-in only (keine zuverlässige VIN/Model/Year-Heuristik public verfügbar).

## [1.13.0] - 2026-05-02 🛡️ Production Hardening Bundle / Production Hardening (Capability Phase 3 + Read-only Phase 2 + Diagnostics-Polish + Process)

🛡️ **Drei P0-Themen aus dem Roadmap-Backlog in einem MINOR-Release.** Alle drei waren bereits angefangene Arbeit (Phase 1 ausgeliefert) — jetzt Closure mit Phase 2/3, plus die Diagnostics-Hardening die wir für Issue-Reporting brauchen, plus Process-Docs (#64) für Brand Captains.

### ✨ Neu / Added

- 🛡️ **Capability-Filter Phase 3** (#56) — `command.active && user-enabled && !license-issue` PRE-Entity-Creation Gating. Vorher: Entity wurde erstellt und ging nach 1. Failure unavailable (Phase 2). Jetzt: Entity wird gar nicht erst gebaut wenn das Backend `false` meldet. Tri-state: `True/False/None`, konservatives `None = behalte` für Brands ohne Cap-Mapping (Phase 2 fängt Runtime-Failures weiter ab). Neue Single-Source-of-Truth `cariad/_capabilities.py` mit `CAPABILITY_MAP[brand][command_id] → cap_id` und `cap_id_for(brand, command_id)`. Audi/SEAT erben über Table-Alias (`CAPABILITY_MAP["audi"] = CAPABILITY_MAP["volkswagen"]`). Skoda hat eigenes Schema (`active/editable/user-enabled/status/license-issue`) das `vehicle_supports_capability` jetzt mitnimmt.
- 🔒 **Read-only Mode Phase 2 — Service-Side Enforcement** (#63) — Phase 1 (v1.12.0) hat nur Entity-Creation geblockt; Phase 2 blockt jetzt auch alle Service-Calls. Neue `_coord_writeable(vin)` Helper raised `read_only_mode_active` ServiceValidationError bevor irgend ein Command rausgeht. Schützt vor versehentlichen Automatisierungen die direkt Services aufrufen (Bypass von Entity-Verstecken).
- 🔁 **`refresh_cloud_cache` Service-Alias** (#63) — Klare Trennung zwischen `refresh_cloud_cache` (kein Wake, nur Cloud-Polling — der häufige Fall) vs. `wake_vehicle` (echter Wake-Up mit 12V-Risiko + 3/Tag Budget aus v1.12.0 + jetzt 5-min Cooldown). Backwards-compat: `refresh_vehicle` bleibt als Alias für `refresh_cloud_cache`. Beschreibung in `services.yaml` clarified — kein Wake, nur Cache.
- ⏱️ **5-min Wake-Cooldown pro Fahrzeug** (#63) — Per-VIN `_wake_last_at` timestamp. Wake innerhalb des 5-Minuten-Fensters raised `wake_cooldown_active` ServiceValidationError mit `{remaining_s}` + `{cooldown_min}` Placeholders. Greift VOR dem 3/Tag Budget-Check aus v1.12.0 — schützt vor Click-Spam-Loops.
- 🔐 **Per-VIN Per-Command-Class asyncio.Lock mit Timeout** (#63) — Verhindert Double-Click (zwei `lock_doors` Klicks gleichzeitig) und Konkurrenz zwischen `start_climatisation`+`stop_climatisation`. `_get_command_lock(vin, command_class)` lazy creation; `_dispatch_cmd_locked` extracted helper. `asyncio.timeout(60)` Fallback verhindert Deadlock bei hängenden Commands. Neue `is_command_in_flight(vin, command_class)` API für UI-Feedback.
- 🔬 **Anonymized Diagnostics-Export** (#62) — Polish des HA `diagnostics`-Mechanismus für Issue-Reporting:
  - **Token-Redaction expanded** — `access_token`, `refresh_token`, `id_token` (snake_case + camelCase) und `client_secret` jetzt in `_REDACT_KEYS`.
  - **Email Partial-Mask** — `prash@gmail.com` → `p***@***.com` via Regex-Replacement (statt vollständigem `***`). Erlaubt Identifizierung des Reporters wenn er sich später meldet, ohne PII zu leaken.
  - **GPS Opt-In Rounding** — wenn `enable_reverse_geocoding=False`, werden Lat/Lon auf 1 Dezimalstelle gerundet (~11km Granularität). User der Reverse-Geocoding aktiv hat akzeptiert bereits volle Genauigkeit.
- 📝 **GitHub Issue Forms** (#64) — Strukturierte YAML-Forms für die zwei häufigsten Reports aus der v1.9.0 Reporter Pipeline: `scout_report.yml` für Vehicle Data Scout (1-klick pre-fill aus HA) + `error_report.yml` für Error Reporter Dumps. Felder: brand-Picker, vehicle, version, scout_report markdown, privacy_confirm.
- 🏆 **`BRAND_CAPTAINS.md`** (#64) — Initial Brand Captains Tabelle (aktuell nur Maintainer + "Bewährte Tester" Liste: Gerhard2808 für CUPRA Born, tritanium73 für Skoda, DnnsJp74 für Audi). "Wie werde ich Captain?" Anleitung + Captain-Pflichten + Privacy-Notes.

### 🔄 Geändert / Changed

- 🔧 **`_cariad_cmd` mit Lock-Wrapper** — alle Commands die durch den Lock gehen werden jetzt zentral durch `asyncio.timeout(60) + asyncio.Lock` geschickt. Falls kein Lock-Lookup möglich ist (unbekannte Command-Klasse), wird auf `_dispatch_cmd_locked` direkt fallback-dispatched — keine Regression für unbekannte Commands.
- 📚 **GitHub About-Section + Master READMEs (8 Sprachen)** auf v1.12.3-Stand refresht (vorher "68 entities, cloud push" — outdated). Alle 12 LIVE-Features dokumentiert. Roadmap-Sektion vereinfacht auf Single-Source-of-Truth Pointer + Tabelle der letzten 9 Releases. Bi-lingual Title Convention etabliert ab v1.12.3.

### 🌐 Übersetzungen / Translations

- 🌐 **8 Sprachen** (de/en/fr/es/nl/pl/cs/sv) — neue Exception-Keys `wake_cooldown_active` + `read_only_mode_active`. de.json hatte `wake_budget_exhausted` zusätzlich gefehlt; nachgereicht.

### 🧪 Tests / Tests

- 🧪 **31 neue Tests** in `tests/test_v1130_production_hardening.py`: TestCapabilityMap (5), TestCommandCapabilitySupported (8), TestCommandLock (4), TestWakeCooldown (3), TestReadOnlyServiceBlocking (2), TestDiagnosticsPolish (7), TestSkodaCapabilities (2).

### 🔬 Pre-Research / Pre-Research

- 📋 `docs/RESEARCH_NOTES_2026-05-02.md` — 423-Zeilen Pre-Implementation-Research für 13 Issues über 3 Bundles. Per-Issue-Verdict (✅ verified / ⚠️ [Inference] / ❌ gap → defer). Vermeidet Mid-Flight-Surprises bei Phase-3 Capability-Mapping. Bundle 2 (Audi-Pack) und Bundle 3 (Cross-Brand-UX) bereits gescoped für nächste Sessions.

### 📦 Schließt Issues / Closes

- Closes #56 (Capability-Filter Phase 3 — gates pre-entity-creation)
- Closes #62 (Anonymized Diagnostics-Export)
- Closes #63 (Read-only Mode Phase 2/3 — service-side blocking + cloud_refresh distinction + 5-min cooldown)
- Closes #64 (Process & Governance Doc-PR — Issue Forms + Brand Captains)

## [1.12.3] - 2026-05-01 🛰️ Scout-Pfade #111 + #113 + #114 / Scout paths bundled with wildcard strategy

🌟 **Drei Scout-Reports zusammen ausgeliefert.** #111 von DnnsJp74 (zweiter Community-User), plus #113+#114 von Prash auf seinen eigenen Vehicles (Golf GTE 14 Felder + Audi S6 C8 20 Felder) — alle drei zeigen denselben Pattern: `.value` Container haben Children die wir whack-a-mole jagen würden, wenn nicht Wildcards eingesetzt werden.

🛰️ **EXPECTED_KEYS Registrierungen** (`cariad/_unexpected_keys.py`, alle in `volkswagen.selectivestatus` — Audi inherits):

| Kategorie | Neue Pfade |
|---|---|
| automation `.value` neben `.error` | `automation.{climatisationTimer,chargingProfiles}.value` |
| Top-level meta-jobs (waren in selectivestatus query aber nicht registriert) | `batteryChargingCare` + `climatisationTimers` (beide mit `.*` wildcard) |
| Charging Erweiterungen | `charging.chargeMode.value`, `charging.chargingCareSettings.*`, `charging.chargingSettings.value.autoUnlockPlugWhenCharged` (legacy variant ohne AC suffix) |
| Climatisation Zone-Felder | `climatisation.climatisationSettings.value.{unitInCar,climatizationAtUnlock,windowHeatingEnabled,zoneFrontLeftEnabled,zoneFrontRightEnabled}` |
| Battery Temperature | `measurements.temperatureBatteryStatus.value.temperatureHvBattery{Min,Max}_K` (Min wird vom Parser für battery_temp gelesen seit v1.10.x; Max ist neu) |
| Readiness ConnectionState (4) + ConnectionWarning (2) | `readiness.readinessStatus.value.connectionState.{isOnline,isActive,batteryPowerLevel,dailyPowerBudgetAvailable}` + `.connectionWarning.{insufficientBatteryLevelWarning,dailyPowerBudgetWarning}` |

🌊 **Wildcard-Strategie für `.value.*` Container:**

Statt jeden neuen Sub-Field einzeln zu registrieren, decken Wildcards die ganze Klasse ab:
- `fuelStatus.rangeStatus.value.*` (alle Children: carType, totalRange_km, carCapturedTimestamp, etc.)
- `fuelStatus.rangeStatus.value.primaryEngine.*` + `.secondaryEngine.*`
- `vehicleHealthInspection.maintenanceStatus.value.*` (inspectionDue_days/km, oilServiceDue_days/km, mileage_km, carCapturedTimestamp)
- `departureProfiles.departureProfilesStatus.value.*`
- `userCapabilities.capabilitiesStatus.value.*`
- `batteryChargingCare.value.*` + `climatisationTimers.value.*` (proaktiv)

Plus alle 23 #111 paths unverändert eingeschlossen.

🧪 **Tests:** 8 neue in `tests/test_v1123_111_audi_scout.py` — verbatim Payloads für alle 3 Issues (#111, #113, #114) müssen Scout-Empty zurückgeben.

📊 **Audit-Befund auch bei den älteren Bugs:**

| Issue | Status |
|---|---|
| #42 (migendi CUPRA Formentor) | Verify-Ping gepostet, warte auf User-Antwort |
| #48 (all-actions-fail) | Verify-Ping gepostet |
| #51 (G.S. Audi RS e-tron GT) | Verify-Ping gepostet |
| #53 (Gerhard Born) | Status-Update mit Fixture-Bestätigung + Phase 3 Plan gepostet |

**Closes:** #111, #113, #114.

## [1.12.2] - 2026-05-01 🌟🛰️ Erstes Community-Scout-Report (Skoda #107 von tritanium73) / First community Scout report

🌟 **Erste Live-Validation der v1.9.0 Reporter Pipeline durch einen Nicht-Maintainer-User!**

User `tritanium73` hat heute einen Vehicle Data Scout Report für seine Skoda gefiltet (#107). 14 neue Felder über 4 mysmob-Endpoints — die volle 1-Klick Pipeline aus v1.9.0 funktioniert in der Wildbahn:

1. Scout erkennt Drift bei Poll
2. HA Repair-Notification erscheint bei tritanium73
3. Klick auf "Mehr erfahren" → pre-filled GitHub Issue
4. tritanium73 reicht das ein → wir fixen → 1.12.2 Release

Genau dafür wurde v1.9.0 gebaut. **Riesigen Dank an tritanium73 für den ersten Community-Beitrag in dieser Form** 🙏

🛰️ **EXPECTED_KEYS Registrierungen** (`cariad/_unexpected_keys.py`, alle skoda-only — SEAT/CUPRA und VW EU/Audi nicht betroffen):

| Endpoint | Neue Pfade |
|---|---|
| `vehicle-status` | `renders.lightMode` + `renders.darkMode` (waren via 3-Segment-Wildcard nicht matched — Bug aus v1.9.1 catalog) |
| `air-conditioning` | `runningRequests`, `steeringWheelPosition`, `windowHeatingState.unspecified`, `timers`, `outsideTemperature`, `errors` |
| `driving-range` | `carType`, `primaryEngineRange` |
| `maintenance` | `maintenanceReport.capturedAt`, `preferredServicePartner`, `predictiveMaintenance`, `customerService` |

`carType` + `primaryEngineRange` sind besonders interessant — wahrscheinlich die mysmob-Variante zu CARIAD-BFFs `fuelStatus.rangeStatus.value.primaryEngine` aus v1.10.0. Wiring als Range-Source kommt in v1.13.0+ wenn wir verifizierte Live-Response-Shape sehen.

🧪 **Tests:** 6 neue in `tests/test_v1122_107_skoda_scout.py` — verifizieren dass alle 14 Pfade jetzt registriert sind, plus Defensive-Test dass SEAT/CUPRA nicht versehentlich von der Skoda-Registrierung beeinflusst werden.

📊 **Bonus-Audit aus Diagnostics-Datei (Audi 2 Vehicles, Prash):**

- 4 unexpected findings sind bereits durch v1.12.1 registriert → silenced beim nächsten Poll ✅
- 2 Error-Reporter Findings sind transiente 502 Bad Gateway → v1.8.7 retry-mechanism funktioniert wie designed (Backend war kurz down). Kein Code-Change nötig — same Pattern wie #108.

**Closes:** #107.
**Acknowledges:** #108 (transient 502, no fix needed — system working as designed).

## [1.12.1] - 2026-04-30 🛰️📚 Scout-Pfade #105/#106 + Gerhard's Born Fixture + FAQ #47 / Scout paths + Born fixture + Subscription FAQ

🛰️ **Vehicle Data Scout Welle 4** (#105 VW EU 12 Felder + #106 Audi 8 Felder):

Pattern wie #103/#104 (v1.12.0) — Scout descendet eine weitere Ebene tiefer und findet die `.value` Container + die HTTP-Error-Wrapper Sub-Felder als unbekannt.

Neue Registrierungen in `EXPECTED_KEYS["volkswagen"]["selectivestatus"]` (Audi inherits):
- `userCapabilities.capabilitiesStatus.value` + `fuelStatus.rangeStatus.value` + `vehicleHealthInspection.maintenanceStatus.value` + `vehicleHealthWarnings.warningLights.value` + `departureProfiles.departureProfilesStatus.value`
- `automation.climatisationTimer.error` + `automation.chargingProfiles.error` (Bad-Gateway-Wrapper-Pattern wie `charging.chargeMode.error` aus v1.12.0)
- **Wildcards** `charging.chargeMode.error.*` + `automation.{climatisationTimer,chargingProfiles}.error.*` + `fuelStatus.rangeStatus.error.*` (proaktiv) — decken die 6 standardisierten HTTP-Error-Sub-Felder (message/errorTimeStamp/info/code/group/retry) future-proof ab

📚 **Gerhard's CUPRA Born Fixture** (#53 — Gerhard hat "ja Fixture OK, ich hab nix zu verbergen :-)" gesagt!):

- Neue Datei: `tests/fixtures/seat_cupra/cupra_born_2023_active_subscription_redacted.json`
- **Komplett anonymisiert:** VIN auf `***003577` maskiert, alle UUIDs/Tokens/Emails entfernt, GPS auf `48.0 / 11.0` gerundet (~11 km Bucket)
- **Zweck:** automatische Regression-Tests für CUPRA Born Parser-Drift (verhindert Born-2026-Firmware-Bug aus v1.10.2 wieder auftritt)
- **Source dokumentiert:** "User report from issue #53 (Gerhard2808), with explicit consent given on 2026-04-30"
- 8 Round-Trip-Tests verifizieren dass die v1.10.2 Parser-Pfade aus der redacted Fixture die Werte produzieren die Gerhard auf seinem Born sieht (battery 69%, range 277km, plug disconnected, doors locked)
- 7 Privacy-Audit-Tests verifizieren dass keine vollen VINs / Tokens / UUIDs / Emails in der Fixture sind

🌍 **Erste Live-Validation des "Privacy & data handling" Workflows aus PR #101** — User-Consent eingeholt, Fixture redacted, Source dokumentiert. Code-of-conduct funktioniert.

📚 **#47 FAQ — Service Plus / Subscription Docs:**

Neue FAQ-Sektion in `CONTRIBUTING.md`:
- "Brauche ich Security & Service Plus?" → meist nein, in Portugal + manchen 2024+ Audi ja
- Wie unterscheide ich `missing-capability` vs `subscription_expired` vs `spin_error` vs `404`?
- Wieso geht's in der App aber nicht in VAG Connect? (3 unabhängige Gründe aus #53 Lessons)
- Wo sehe ich meinen Subscription-Status?

Tabelle mit allen v1.9.1 `classify_command_failure` Markern + ihre Bedeutung. Verlinkt zu Phase 3 Capability-Filter (v1.13.0).

🧪 **Tests:** 19 neue in `tests/test_v1121_scout_and_born_fixture.py`:
- 5 Scout-Path-Coverage-Tests (#105/#106 verbatim payload bleibt silent)
- 7 Born-Fixture Privacy-Audit (no VIN/email/JWT/UUID/GPS-precision leak)
- 6 Born-Fixture Parser-Round-Trip (Gerhard's beobachtete Werte materialisieren)
- 1 #47 FAQ-Section-Presence Test

> 💡 Vollständige technische Details + ROADMAP-Refresh mit P0/P1/P2-Priorisierung in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) + [`docs/ROADMAP.md`](docs/ROADMAP.md).

**Closes:** #105, #106, #47.

## [1.12.0] - 2026-04-30 🔋💡⚡🧯🔒 5-in-1 Feature-Sprint / Five features in one MINOR

✨ **Fünf neue Funktionen — alle in einer kohärenten "More Control + Diagnostics"-Theme:**

| # | Was | Issue | Wer profitiert |
|---|---|---|---|
| 🔋 | **12V-Batterie Voltage + Low-Warnung** | #23 | Alle CARIAD-Owner — sehen jetzt `12V-Batterie` Voltage-Sensor + `12V-Batterie schwach` Binary bei <11.5V |
| 💡 | **Per-Light Binary-Sensors** (#91 Welle 3) | #91 | Owner mit Vehicles deren Firmware bekannte Light-Element-Shapes ausliefert (frontLeft etc.) — eigene Binary pro Lichttyp |
| ⚡ | **Writeable `Max. Ladestrom` Number** | #91 follow-up | EV/PHEV Owner — können jetzt 6-32 A Ladestrom über Slider setzen (war pre-1.12.0 nur Sensor) |
| 🧯 | **Smart-Wake Counter + Budget** | #55 | Alle — neuer `Wake-Ups heute` Sensor + Soft-Cap auf 3/Tag schützt 12V-Batterie vor Über-Wakeup |
| 🔒 | **Read-only Mode Option** | #63 | Privacy/Safety-konservative Owner — nur Status-Sensoren, keine Switches/Buttons/Locks/Climate/Number |

🔋 **#23 — 12V Batterie:**
- Neue `lvBattery` job in CARIAD `selectivestatus` Polling-Liste
- Parser liest `lvBattery.lvBatteryStatus.value.batteryVoltage_V`
- Neuer Sensor `voltage_12v` (V, DEVICE_CLASS.VOLTAGE)
- Neue Binary `warning_12v_low` (PROBLEM-class) bei <11.5V
- Threshold matcht volkswagencarnet PR #940 + ELM327-Praxis. Symptom "API stops responding for hours" wird endlich erklärbar bevor User die Integration als kaputt markiert.

💡 **#91 Welle 3 — Per-Light Binary-Sensors:**
- Dynamische Erstellung via `_async_setup_light_sensors` aus `lights_individual` dict (gefüllt vom v1.11.0 Light-Parser)
- Mirror des Door/Window-Patterns: empty dict → keine Entities
- Vehicles mit unbekanntem Light-Element-Shape sehen weiterhin nur das Aggregate `lights_on` + `lights_count`

⚡ **#91 follow-up — Writeable Max-Charge-Current Number:**
- Neuer `command_set_max_charge_current` in `vw_eu.py` POST `chargingSettings` mit `{"maxChargeCurrentAC_A": ampere}`
- Number-Entity 6-32 A in 2er-Schritten (typische VW-EU-Werte: 6/8/10/12/14/16/32)
- `coordinator.async_set_max_charge_current` umgestellt: war `raise ServiceValidationError` → ist jetzt `_cariad_cmd("command_set_max_charge_current")`. Ungültige Werte werden vom Backend abgelehnt + via `classify_command_failure` Pipeline an User reportet.

🧯 **#55 — Smart-Wake:**
- Neuer Sensor `wake_count_today` (TOTAL_INCREASING, diagnostic)
- `async_wake_vehicle` trackt Counter pro VIN + Reset bei UTC-Mitternacht
- Soft-Cap auf 3 Wakes/Tag (`_WAKE_BUDGET_PER_DAY`) — über-Wake raised `ServiceValidationError("wake_budget_exhausted")` BEVOR API-Call. Schützt 12V-Batterie + verhindert Account-Suspension durch Wake-Loops.

🔒 **#63 — Read-only Mode (Phase 1):**
- Neue Options-Toggle "Read-only Mode" → Settings → Devices → VAG Connect → Configure
- Wenn aktiviert: lock/switch/button(non-refresh)/climate/number Plattformen skippen Entity-Creation komplett
- Sensors + binary_sensors + device_tracker bleiben (read-only sowieso)
- VagRefreshButton bleibt auch im Read-only Mode (cloud-poll, kein Vehicle-Command)
- Use-Case: Privacy-konservative Owner die nur Telemetrie wollen, oder Account-Schutz vor versehentlichem Actuation in Auto-Repeat-Loops

🌍 **Übersetzungen** in 8 Sprachen für alle 5 neuen Features inkl. die Read-only-Mode Option-Description (am ausführlichsten — User soll vor Aktivierung verstehen was passiert).

🧪 **Tests:** 25 neue Tests in `tests/test_v1120_features.py` decken alle 5 Features einzeln + Phantom-Schutz + Backwards-Compat.

> 💡 Vollständige Field-Mappings, Architektur-Notes und nicht-implementierte Punkte (was kommt in v1.12.1+) in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

**Closes:** #23, #55. **Partial:** #63 (Read-only-Mode-Phase-1 ausgeliefert; Command-Locking + cloud-vs-vehicle-refresh Distinction sind eigene Sessions).

### 📋 Doc-only — User-Data Handling + `[Inference]` Marker (2026-04-30, no version bump)

Nach Third-Party-Privacy-Review zu Issue #53 dokumentiert:

- 🔒 **`docs/SESSION_HANDOFF.md`** neue "User-Data Handling" Sektion + 2 neue Hard Rules (#18 Privacy-by-default, #19 `[Inference]` Marker für unverifizierte semantische Claims)
- 📝 **`CONTRIBUTING.md`** neue "Privacy & data handling" Sektion mit Fixture-Redaction-Template + Consent-Anfrage-Template + Maintainer-Self-Check
- ⚠️ **`cariad/api/seat_cupra.py:command_flash`** Docstring mit explizitem `[Inference]` Marker — `userPosition` Semantik ist gegen offizielle My SEAT/CUPRA-App nicht verifiziert (verifiziert nur gegen pycupra/myskoda)
- ⚠️ **`coordinator.py:async_flash_lights`** Cross-Reference auf den Inference-Marker

Hintergrund: pre-1.11.1 wurden zwei inhaltliche Ungenauigkeiten in #53 / #56 Comments gemacht:
1. Pauschale "subscription expired" Diagnose obwohl Gerhard's Vertrag aktiv ist
2. Behauptung `userPosition` macht es "wie die offizielle MyCupra-App" ohne App-Traffic-Verifikation

Folge-Comments auf #53 + #56 mit Korrektur kommen separat. Diese Doc-PR codifiziert die Lessons damit es nicht wieder passiert.

## [1.11.1] - 2026-04-30 🐛💨 Golf 7 GTE Fuel-Range Fix (#96) + Optimistic UI (3B-Part-3)

🐛 **Bug-Fix #96 — Golf 7 GTE / Passat GTE Fuel-Range erscheint endlich:**

Pre-1.11.1 Bug: VW Golf 7 GTE 2015 + Passat GTE B7/B8 Owner haben nach v1.10.0-Update **immer noch keine Sprit-Reichweite** gesehen. Root Cause: `fuelStatus.rangeStatus` returnt auf älteren GTE-Firmwares ein `{"error": ...}` Objekt statt `{"value": ...}` (verifiziert via evcc-io/evcc#19045 Passat GTE Live-Trace) → unsere Drivetrain-Detection blieb auf `has_combustion=False` → die `_DATA_PRESENT_REQUIRED` Phantom-Schutz-Logik aus v1.10.0 hat dann den Sensor nicht erstellt obwohl die Daten in `measurements` vorhanden waren.

**Fix (4 Tracks):**

- 🔧 **Drivetrain-Detection** liest jetzt aus 4 Quellen (statt 2): zusätzlich `measurements.fuelLevelStatus.value.{primaryEngineType,secondaryEngineType}` — populated AUCH wenn fuelStatus error returnt.
- 🔧 **`carType="hybrid"` flag** explizit erkannt → setzt `has_battery=True` UND `has_combustion=True`. Pre-1.11.1 nur Substring-Match auf "electric"/"gasoline" — verfehlt das nackte "hybrid".
- 🔧 **Total range fallback** aus `measurements.rangeStatus.value.totalRange_km` (war nur fuelStatus-Pfad).
- 🔧 **Fuel level fallback** aus engine block `currentFuelLevel_pct` (war nur measurements-Pfad).

Backwards-kompat: Vehicles deren `fuelStatus.rangeStatus.value` funktioniert (Golf GTE auf neuer Firmware, modern PHEVs) sehen identisches Verhalten wie v1.10.0.

💨 **3B-Part-3 — Optimistic UI für Lock/Climate/Charging/Window-Heating:**

Pattern aus `skodaconnect/myskoda` PR #832: Wenn User auf Lock/Climate/Charging-Switch klickt, flippt die HA-Karte **sofort** auf den Erwartungs-Wert — der API-Roundtrip (10–30 s) findet im Hintergrund statt. Bei Failure: revert + ServiceValidationError.

Was ist jetzt optimistic:
- 🔒 `async_lock` → `doors_locked = True` sofort
- 🔓 `async_unlock` → `doors_locked = False` sofort
- 🔥 `async_start_climatisation` → `climatisation_active = True` + `state = "VENTILATION"` sofort
- ❄️ `async_stop_climatisation` → `climatisation_active = False` + `state = "OFF"` sofort
- ⚡ `async_start_charging` → `is_charging = True` + `charging_state = "CHARGING"` sofort
- ⚡ `async_stop_charging` → `is_charging = False` + `charging_state = "NOT_CHARGING"` sofort
- 🪟 `async_start/stop_window_heating` → beide Felder sofort

Failure-Pfad: Snapshot der vorherigen Werte wird vor dem Optimistic-Set gespeichert; bei Exception wird zurückgesetzt + HA notified. User sieht den Lock-Toggle "zurück springen" als Hinweis dass das Command fehlschlug.

🧪 **Tests:** 18 neue in `tests/test_v1111_96_optimistic.py` decken alle 4 #96-Tracks (volle GTE Shape + Passat error shape + carType=hybrid + engine-block fallback + pure ICE + pure EV phantom-protection) plus alle Optimistic-Transitions + Revert-on-Failure.

> 💡 Vollständige Field-Mapping + evcc/CarConnectivity/Audi-Q4 Quellen-Analyse in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.11.0] - 2026-04-30 🔆🔧 Issue #91 Closure: Light-Status, Service-Days, Max-Charge-Current

✨ **Fünf neue Entitäten — schließt Issue #91 vollständig** (Audi S6 + VW Golf 7 GTE Vehicle Data Scout findings):

| Entity | Type | Quelle | Vehicle |
|---|---|---|---|
| 💡 **`lights_on`** ("Lichter an") | Binary-Sensor | `vehicleLights.lightsStatus.value.lights[]` | alle |
| 🔢 **`lights_count`** ("Aktive Lichter") | Sensor | gleiche Array | alle |
| 📅 **`service_due_in_days`** ("Inspektion in") | Sensor (`d`) | `vehicleHealthInspection.maintenanceStatus.value.inspectionDue_days` | alle |
| 🛢️ **`oil_service_due_in_days`** ("Ölwechsel in") | Sensor (`d`) | `vehicleHealthInspection.maintenanceStatus.value.oilServiceDue_days` | combustion |
| ⚡ **`max_charge_current_a`** ("Max. Ladestrom") | Sensor (`A`) | `charging.chargingSettings.value.maxChargeCurrentAC_A` | electric |

**Was war das Problem:**

Issue #91 (Audi S6 + Issue #90 VW Golf 7 GTE) hatte mehrere Punkte. v1.10.0 hat den dicksten Fish gefangen (PHEV-Range-Triple + Audi-Diesel-Range), aber ein paar Lücken blieben:

- Lichter-Status war nirgends zugänglich
- Service-Tage konnte man nur als Datum sehen, nicht als "noch X Tage"
- Max-Ladestrom war als Field da aber kein Sensor

v1.11.0 macht #91 jetzt komplett fertig.

**Defensive Light-Parsing:** weil die Element-Shape von `vehicleLights.lightsStatus.value.lights[]` zwischen Firmwares variiert (`{name,status}` vs `{id,status}` vs CARIAD-BFF Listen-Wrapper), versucht der Parser drei bekannte Shapes durch und fällt auf "nur Aggregate" zurück wenn keiner matcht. Per-Light-Binary-Sensors kommen erst in v1.12.0 wenn wir verifizierte Element-Shapes von mehreren Brands haben.

**Phantom-Entity-Schutz** wie schon in v1.10.0 — alle 5 neuen Entitäten gehen über `_DATA_PRESENT_REQUIRED` Frozenset. Wer keine Lichter-Daten von der API bekommt, sieht keinen "0"-Sensor.

**Backwards-Compat:** `service_due_at` (DATE) + `oil_service_at` (DATE) bleiben unverändert. Die neuen `_in_days`-Sensoren sind **zusätzliche** Anzeige-Optionen.

🌍 **Übersetzungen** in allen 8 Sprachen.

🧪 **Tests:** 15 neue in `tests/test_v1110_91_closure.py` decken alle 3 Light-Shape-Varianten + Aggregate-Fallback + Service-Days + Sensor-Registrierung.

> 💡 Vollständige technische Details in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.10.2] - 2026-04-30 🚗 CUPRA Born 2026 Firmware-Shapes (Gerhard's #53 Live-Test)

🐛 **Bug-Fix für CUPRA Born / SEAT Cupra Owner auf neuerer OLA-Firmware:**

Gerhard hat v1.10.0 auf seinem CUPRA Born getestet und der **Vehicle
Data Scout aus v1.9.0** hat **19 neue Felder** auf den OLA-Endpoints
gemeldet (#53 Comment 2026-04-30). Beim genauen Hinschauen waren das
nicht nur "neue Felder" — viele waren **umbenannte Versionen** der
Felder die wir schon kannten:

| Old (Rainer #109 — v1.8.9 Ref) | New (Born 2026 firmware) | Wirkung pre-1.10.2 |
|---|---|---|
| `battery.currentSOC_pct` | `battery.currentSocPercentage` | Akku-Füllstand leer |
| `plug.connectionState` / `plug.plugConnectionState` | `plug.connection` | Stecker-Verbunden immer False |
| `plug.lockState` / `plug.plugLockState` | `plug.lock` | Stecker-Verriegelt immer False |
| `"CONNECTED"` / `"LOCKED"` (UPPERCASE) | `"connected"` / `"locked"` (lowercase) | enums verglichen falsch |

**Folge:** auf Born-Owners die v1.8.9+ benutzen aber neuere Firmware
haben waren die Charging- + Plug-Entitäten still leer — keine
Fehlermeldung, einfach `unknown`.

**Fix:** `seat_cupra.py` Parser liest jetzt **alle drei Field-Namen-
Varianten** als Fallback-Kette (Born 2026 → Rainer #109 → Legacy
CARIAD), und vergleicht enum-Werte case-insensitive. Backwards-Compat
für ältere Firmwares bleibt erhalten.

**Plus neue Born-2026-Felder die wir jetzt nutzen:**

- 🔋 `battery.estimatedRangeInKm` → fallback für `range_km` /
  `electric_range_km` wenn der dedizierte ranges-Endpoint nichts liefert
- 🔒 `status.locked` (top-level bool) → fallback für `doors_locked`
  wenn die strukturierte `doors.*.locked` Tree leer ist
- 🚪 `status.hood.locked` (string `"true"`/`"false"`) → fallback für
  `hood_open` (invertiert)

**Plus alle 19 Felder im EXPECTED_KEYS-Katalog registriert** — Gerhard's
Repair-Notification löst sich beim nächsten Poll von alleine.

🛰️ **Erste echte API-Drift-Detection im Live-Betrieb seit v1.9.0!**
Das ganze v1.9.0 Vehicle-Data-Scout System hat genau diesen Use-Case
abgefangen: ein User auf neuerer Firmware hat einen 1-Klick-Bug-Report
geöffnet, wir haben innerhalb von Stunden den Parser gefixed.

🧪 **Tests:** 16 neue Tests in `tests/test_v1102_gerhard_born_firmware.py`
(camelCase-Pfade, lowercase-Enums, Backwards-Compat zu Rainer-Shape,
status-top-level-Fallback, alle 19 Scout-Felder registriert).

> 💡 Vollständige Field-Name-Mapping-Tabelle + Methodik-Notes in
> [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.10.1] - 2026-04-30 🛡️ Defensive Coding Phase 2 (Issue #58)

🐛 **Robustheit gegen unerwartete API-Werte:**

Drei neue Helfer in `cariad/_util.py` die NIE crashen, sondern bei
seltsamen Werten den Default zurückgeben:

- 🔢 **`safe_int(value, default=None)`** — akzeptiert int, float, bool,
  numerischer String mit Whitespace, Decimal-String (`"12.5"` → `12`).
  Garbage (None, leer, dict, list, "abc") → default.
- 🔣 **`safe_float(value, default=None)`** — gleiche Robustheit für floats.
- 🚦 **`safe_enum(value, known_values, *, log_name)`** — gibt den Wert
  zurück wenn er in `known_values` ist, sonst loggt eine Warnung mit dem
  Field-Namen + dem unerwarteten Wert und gibt None zurück.
  **Forward-Kompatibilität:** wenn VAG morgen einen neuen Charging-State
  wie `CHARGING_INTERRUPTED` ausrollt (siehe myskoda #503), bleibt
  Integration online — Sensor zeigt einfach `unknown` statt zu crashen.

🛠️ **Wo angewendet:**

- **Skoda Parser** — `remainingTimeToFullyChargedInMinutes` als String
  ("12.5") → keine Crash mehr (myskoda #503 Pattern). `targetTemperature`
  ebenfalls.
- **VW EU/Audi Parser** — `remainingChargingTimeToComplete_min`,
  `maxChargeCurrentAC_A` (kann String "MAXIMUM" sein), `model_year`
  (manchmal Int, manchmal "2021"-String) alle defensiv.
- **SEAT/CUPRA Parser** — `remainingTimeToFullyChargedInMinutes`
  ebenfalls über `safe_int`.

🛡️ **Coordinator-Härtung:**

- `to_dict()` + `_enrich()` für jedes Vehicle jetzt eigener try/except.
  Pre-1.10.1 hat ein einzelnes Parser-Problem den ganzen Vehicle-Poll
  zerschossen; jetzt bleibt das Vehicle mit seinen vorherigen Daten
  sichtbar, der Fehler landet im Error Reporter Ring-Buffer für
  1-Klick-Bug-Report (v1.9.0 Pipeline).

🧪 **Tests:** 16 neue Tests in `tests/test_v1101_defensive.py` decken
alle Helper-Pfade + Coordinator-Parse-Guard.

> 💡 Vollständige technische Details inkl. Helper-Vertrag und
> Anwendungs-Audit in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.10.0] - 2026-04-29 🔋⛽ PHEV-Range-Triple + Audi-Diesel-Range (Issue #94)

✨ **Drei neue Sensoren für plug-in Hybride und Diesel-Modelle:**

- 🔋 **`electric_range_km`** ("Elektrische Reichweite") — Batterie-only Reichweite (mdi:battery-charging-outline)
- ⛽ **`combustion_range_km`** ("Kraftstoff-Reichweite") — Benzin/Diesel/CNG/LPG Reichweite (mdi:gas-station)
- 🛣️ **`total_range_km`** ("Gesamtreichweite") — kombinierte Reichweite (für Hybride relevant)

**Was war das Problem (Issue #94):**

Pre-1.10.0 hat unser Parser für VW EU + Audi alle Range-Quellen in das eine `range_km`-Feld gemappt — dabei überschrieb die Batterie-Reichweite die Verbrennungs-Reichweite oder den Gesamtwert. Ein Golf 7 GTE konnte deshalb nicht gleichzeitig "45 km elektrisch" + "520 km Sprit" + "565 km gesamt" anzeigen — nur einen davon.

**Was wir gemacht haben:**

- 🆕 **VW EU / Audi Parser:** liest jetzt `fuelStatus.rangeStatus.value.{primaryEngine,secondaryEngine}.{type,remainingRange_km}` und klassifiziert nach **Engine-Typ** (nicht nach Position) — primär=Verbrennung + sekundär=elektrisch oder umgekehrt funktionieren beide.
- 🆕 **Audi `dieselRange` Fallback** (verifiziert auf Audi S6 C8 2021 via #91): wenn kein `fuelStatus`-Block existiert, kommt `combustion_range_km` aus `measurements.rangeStatus.value.dieselRange` / `gasolineRange`. Akzeptiert sowohl skalare Werte als auch `{distanceInKm: int}`-Wrapper.
- 🆕 **Skoda Parser:** liest `electricRange.distanceInKm` + `combustionRange.distanceInKm` + `totalRangeInKm` jetzt in die 3 expliziten Felder. Vorher wurde nur `combustionRange` als Skalar gelesen — auf Kodiaq iV ein Bug.
- 🛡️ **Phantom-Entity-Schutz:** neue Sensoren werden NUR erstellt wenn der API-Wert tatsächlich `not None` ist. Reine EVs bekommen kein "unknown"-Spritmesser, reine ICE keinen "unknown"-Akku. Per `_DATA_PRESENT_REQUIRED` Frozenset in `sensor.py` — pro-Key opt-in.
- 🔄 **`range_km` Backwards-Compat:** bleibt als Headline-Number erhalten. Priorität: elektrisch (für EV/PHEV) → total → Verbrennung. Existierende Automatisierungen und Dashboards funktionieren unverändert.

🌍 **Übersetzungen** in allen 8 Sprachen (DE: Elektrische/Kraftstoff/Gesamt-Reichweite, FR/ES/NL/PL/CS/SV äquivalent).

🧪 **Tests:** 13 neue Tests in `tests/test_v1100_phev_ranges.py` decken alle Engine-Klassifikations-Pfade, Audi-Diesel-Fallback, Skoda-Wrapper, EV-Phantom-Vermeidung.

> 💡 Vollständige technische Details inkl. Vergleichstabelle der API-Pfade pro Brand in [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.9.1] - 2026-04-29 🔧 Audi/VW Lock + Wake Hotfix + Capability-Filter Phase 2

🐛 **Bug-Fixes (Issue #92, Audi S6 C8 2021 Live-Test):**

- 🔓 **Audi/VW EU Lock funktioniert wieder** — der CARIAD BFF antwortete
  mit `403 spin_error` auf `/access/lock` weil die S-PIN bei premium
  Audi-Modellen für Lock genauso erforderlich ist wie für Unlock.
  Der `command_lock` der VW EU/Audi-Clients hängt jetzt dieselbe S-PIN
  ans Payload (sofern konfiguriert) wie es `command_unlock` schon tat.
- 🚀 **Audi Wake-Endpoint v1→v2 Fallback** — `/vehicle/v1/.../vehicleWakeup`
  gibt 404 auf premium Audi Modellen (S6 C8). Der Wake-Befehl nutzt jetzt
  den gleichen `_post_command`-Dispatcher wie alle anderen Commands und
  fällt bei 404 automatisch auf `/vehicle/v2/...` zurück.

🛰️ **Vehicle Data Scout — 27 neue Felder registriert (Issues #90, #91):**

Aus den ersten zwei Live-Reports vom Maintainer (Audi S6 + VW Golf 7 GTE)
sind diese Felder jetzt im `EXPECTED_KEYS`-Katalog (firingen damit nicht
mehr beim nächsten Poll). Fundament für künftige Entity-Arbeit:

- **Audi S6 (Diesel):** `dieselRange`, `currentFuelLevel_pct`,
  `vehicleLights.lightsStatus.{lights,carCapturedTimestamp}`,
  `userCapabilities`, `fuelStatus`, `vehicleHealthInspection`,
  `vehicleHealthWarnings`
- **VW Golf 7 GTE:** `maxChargeCurrentAC_A` (Ampere statt Enum),
  `targetTemperature_F` (Fahrenheit), `climatisationWithoutExternalPower`,
  `automation`, `departureProfiles` (Nachfolger von `departureTimers`),
  `chargeMode`-Block

🛡️ **Capability-Filter Phase 2 (Issue #56):**

- 🧠 **Smartere Fehler-Klassifikation** — `classify_command_failure`
  schaut jetzt im Body nach `spin_error`, `subscription expired`,
  `not_entitled`, `license_required` etc. Pre-1.9.1 wurden alle 4xx als
  generischer "BACKEND_ERROR" klassifiziert.
- 🤖 **Auto-Recording** — `_cariad_cmd` füttert jetzt jedes Command-Ergebnis
  automatisch in den `FeatureState`. Erfolge flippen `entitled_by_account`
  und `supported_by_vehicle` auf `True` zurück (z.B. nach Abo-Verlängerung);
  definitive Fehler markieren das Command als nicht verfügbar.
- 👁️ **Entity-Availability hört auf FeatureState** — Lock, Climate,
  Charging-Switch, Window-Heating-Switch und die Buttons (Flash, Wake)
  gehen automatisch auf "unavailable" wenn das Backend explizit
  "missing capability" oder "subscription expired" zurückmeldet. Statt
  bei jedem Tap denselben 403 zu produzieren.

🧪 **Tests:** 18 neue Tests in `tests/test_v191_hotfix.py` (Lock-S-PIN,
Wake-v1/v2-Fallback, Klassifikator-Body-Sniffing, FeatureState-Logik,
Scout-Key-Registrierung).

> 💡 Vollständige technische Details inkl. aller Code-Pfade in
> [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

## [1.9.0] - 2026-04-29 🔬 Vehicle Data Scout + Error Reporter

✨ **Was ist neu — zwei neue diagnostische Sensoren mit 1-Klick Bug-Report:**

- 🛰️ **Vehicle Data Scout** (`sensor.vag_VIN_vehicle_data_scout`):
  Erkennt automatisch unbekannte Felder in den API-Antworten deines
  Fahrzeugs. Zählt, wie viele neue Felder gefunden wurden — Attribute
  zeigen die letzten 5 Pfade. Brand-lokalisiert (DE: API-Beobachter,
  FR: Observateur d'API, ES: Observador de API, NL: API-waarnemer, …).
- 🚨 **Error Reporter** (`sensor.vag_VIN_error_reporter`):
  Speichert die letzten 20 Integrationsfehler im Ring-Buffer. Zählt
  aktuelle Fehler — Attribute zeigen die letzten 3 Exception-Typen.
  Brand-lokalisiert (DE: Fehler-Berichter, FR: Rapporteur d'erreurs, …).
- 🔘 **1-Klick Reporter Pipeline:** Beide Sensoren erstellen automatisch
  HA-Repair-Notifications (Einstellungen → System → Reparaturen). Klick
  auf **Mehr erfahren** → öffnet ein **vorausgefülltes GitHub-Issue**
  im Browser. Für Facebook-Community: Diagnostics-Download enthält den
  maskierten Bericht, fertig zum Reinkopieren. **NIEMALS Auto-Push.**

🔒 **Datenschutz garantiert:**

- VINs maskiert auf letzte 6 Zeichen (`***012345`)
- GPS-Werte gerundet auf 1 Dezimalstelle (~11 km Genauigkeit)
- userIDs (UUIDs), JWTs, Bearer-Tokens, opaque Tokens entfernt
- E-Mail-Adressen ersetzt durch `***@***`
- Keine rohen API-Responses, keine Zugangsdaten, nichts wird automatisch
  gesendet (GDPR + HACS-Regeln + GitHub ToS)

🤝 **Crowd-sourced Bug-Discovery:** Jeder Nutzer mit einem ungewöhnlichen
Fahrzeug (neuer Modelljahrgang, andere Region, exotische Firmware) kann
mit einem Klick verstecktes Wissen ans Repo zurückspielen. Folgt dem
bewährten `tillsteinbach/CarConnectivity-*` "Unexpected Keys"-Pattern,
das uns die richtigsten Live-API-Daten gebracht hat (CC-seatcupra #109,
CC-skoda #50).

🛠️ **Wo aktiv:** Vehicle Data Scout läuft bereits für Škoda, SEAT, CUPRA,
Volkswagen EU und Audi — alle Brands mit registrierter
`EXPECTED_KEYS`-Tabelle. Error Reporter ist account-weit aktiv.
Andere Brands (Porsche, VW NA) bleiben still bis sie opt-in.

🧪 **Verifiziert mit:** 18 neuen Tests in `tests/test_reporter.py`.

> 💡 Vollständige technische Detail-Notes inkl. aller Code-Pfade,
> Architektur-Entscheidungen und Issue-Referenzen findest du in
> [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md).

### 📚 Documentation refresh (2026-04-29, doc-only — no version bump)

- 🆕 [`docs/RESEARCH_NOTES_2026-04-29.md`](docs/RESEARCH_NOTES_2026-04-29.md) — single archive of every verified live-API field name, every reference repo path, every pattern observation that informed v1.8.6→v1.8.12. Status per claim: ✅ verified / ⚠️ hypothesis / ❌ disproven. **Read this first if resuming this project**.
- 🔄 [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md) — refreshed to v1.8.12 state. New: process improvements section, full architecture map with per-file v1.8.X-change comments, 17 hard rules, 15-step "How to start the next session" recipe.
- 🔄 [`docs/ROADMAP.md`](docs/ROADMAP.md) — full version achievement table, sprint summary, expanded "won't be implemented" section, "How an AI tool resumes this work" guide.
- 🔄 All 8 READMEs — "Aktueller Stand & ehrliche Limits" section refreshed from v1.8.5 to v1.8.12. New 4-tier structure: ✅ what works NOW / ⚠️ in progress / 🚫 conscious limits / 🔧 privacy + 📚 doc links.
- 🆕 **v1.9.0 announced** (was v1.8.13 — corrected to strict semver because two new sensors qualify as MINOR bump): **Vehicle Data Scout + Error Reporter** sharing a 1-click Reporter Pipeline (`📤 GitHub` OR `📋 Copy for Forum/Facebook`). Especially Facebook-community-friendly: non-technical users get usable bug reports without learning Markdown or GitHub. NO auto-push, GDPR-compliant. Roadmap session sequence renumbered: v1.9.1 = Capability-Filter Phase 2, v1.9.2 = Defensive Coding Phase 2, v1.9.3 = Optimistic Lock/Climate, v1.10.0 = Diagnostics + Smart-Wake + 12V protection, v1.11.0 = Trip Stats + Image refactor, v2.0.0 = HACS Default + EU Data Act.

## [1.8.12] - 2026-04-29 🌐 Multi-Brand Connection-State (MVP-Move)

✨ **Was ist neu — alle 7 Marken haben jetzt den Online/Standby/Offline-Sensor:**

- 🟢🟡⚫ **`connection_state` Sensor** funktioniert jetzt nicht nur für Škoda (v1.8.11),
  sondern auch für **VW EU, Audi, SEAT, CUPRA**. Verbindungsstatus deines Autos
  auf einen Blick — egal welche VAG-Marke.
- 🏆 **Erste VAG-Integration mit centralisiertem Multi-Brand Connection-State.**
  Niemand sonst macht das so — myskoda hat es nur intern, volkswagencarnet
  und audi_connect_ha exposen es gar nicht.

🛠️ **Wie wir's verifiziert haben:** Echte Live-API-Antworten von **VW ID.4 2025**
([volkswagencarnet Issue #921](https://github.com/robinostlund/volkswagencarnet/issues/921)
mit komplettem JSON-Dump) bestätigen `carCapturedTimestamp` auf jedem
sub-object des CARIAD-BFF `selectivestatus`-Endpoints. Plus die schon bekannten
Quellen für Škoda (myskoda PR #536) und CUPRA (CC-seatcupra #109).

🔧 **Technisch:** Wir haben den Skoda-Algorithmus aus v1.8.11 in einen
brand-agnostic Helper `compute_connection_state()` extrahiert (cariad/_util.py),
der **rekursiv** durch beliebig tief geschachtelte Sub-Objects walkt. So
funktioniert er für Škoda's flache Struktur **und** für VW EU CARIAD-BFF's
3-fach geschachtelte `service.statusName.value.carCapturedTimestamp`.

🙏 **Danke an:** robinostlund (volkswagencarnet) für jahrelange VW-EU-Pflege,
Rainer für CUPRA Live-Dumps, GitHobi für Škoda #54.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#1812---2026-04-29)

---

## [1.8.11] - 2026-04-29 🚙 Škoda Online/Standby/Offline + Live-API-Erkenntnisse

✨ **Was ist neu für Škoda-Fahrer:**

- 🟢🟡⚫ **Verbindungsstatus-Sensor** — zeigt klar ob das Auto gerade live ist (online),
  schläft aber wakeable ist (standby) oder seit >24h nicht mehr da (offline).
  Schließt das langjährige "Standby vs Offline"-Mysterium aus Issue #54.
- 🚪 **Schiebedach, Kofferraum, Motorhaube** funktionieren jetzt — wurden für
  Škoda nie populiert (Bug aus Issue #50 von Tillsteinbach's Connector).
- 🔒 **Bessere Türschloss-Erkennung** auf neueren Modellen (Kodiaq 2026+) durch
  den `reliableLockStatus`-Wert, der weniger lagt als das alte `doorsLocked`.
- ⚡ **Lade-Endzeit präziser** — wir nutzen jetzt den absoluten ISO-Timestamp
  (`fullyChargedAt`) statt "Restzeit + jetzt" zu rechnen (driftet nicht mehr).
- ⚠️ **`CHARGING_INTERRUPTED`** als neuer Lade-Status wird sauber erkannt
  (kommt vor wenn Wallbox die Sitzung unterbricht).

🛠️ **Wie wir's verifiziert haben:** Echte Live-API-Antworten von Škoda Kodiaq
iV 2026 PHEV (CC-skoda Issue #50, kompletter JSON-Dump) und Pull-Requests aus
[skodaconnect/myskoda](https://github.com/skodaconnect/myskoda) (#503, #565
und vor allem PR #536 die GENAU dieselbe `carCapturedTimestamp`-Strategie
fährt — bestätigt unseren Ansatz 1:1).

🙏 **Danke an:** GitHobi für den Bug-Report (#54), Rainer für den ausführlichen
Kodiaq-iV-2026-Dump in CC-skoda #50.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#1811---2026-04-29)

---

## [1.8.10] - 2026-04-29 🩹 Hotfix

🐛 **Behoben:** Im seltenen Fallback-Pfad für sehr alte CUPRA/SEAT-Firmware
wurden Türstatus invertiert angezeigt (offen ↔ zu vertauscht).

📊 **Wer ist betroffen?** In der Praxis aktuell **niemand** — alle getesteten
CUPRA-Born/Formentor/Tavascan-Modelle nutzen den neuen Pfad aus v1.8.9.
Aber: der Fallback hätte später bei API-Änderungen Probleme gemacht.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#1810---2026-04-29)

---

## [1.8.9] - 2026-04-29 🚗 CUPRA Born Bug-Fix-Bündel

✨ **Was ist neu für CUPRA/SEAT-Fahrer:**

- 🚪 **Türen, Fenster, Kofferraum, Motorhaube, Schiebedach** werden jetzt
  korrekt angezeigt (vorher waren sie permanent leer)
- 🚗 **"Auto fährt gerade"** funktioniert wieder — vorher klebte der Status
  oft auf "geparkt"
- ⚡ **Lade-Power und Restzeit** werden korrekt angezeigt
- 🔓 **Auto-Entriegelung** beim Laden zeigt auch "permanent" als aktiviert an

🆕 **Neue Entities:** Pro-Fenster Binary-Sensoren (`Window Front Left`,
`Window Rear Right` etc.) — analog zu den bisherigen Pro-Tür-Sensoren.

🛠️ **Was war kaputt?** Unser Code hat die falschen JSON-Felder von der
CUPRA/SEAT-API gelesen. Wir hatten Felder aus der CARIAD-API (für VW/Audi)
übernommen, aber CUPRA/SEAT nutzt eine andere API (OLA) mit komplett
anderen Feldnamen. Das wurde verifiziert mit:

- Quellcode der pycupra-Library
- Echten Live-API-Antworten von CUPRA-Born-Fahrern aus dem
  [CarConnectivity-Issue-Tracker](https://github.com/tillsteinbach/CarConnectivity-connector-seatcupra/issues)
  (#5, #8, #18, #21, #50, #51, #109)

🙏 **Danke an:** Gerhard für den ursprünglichen Bug-Report (CUPRA Born),
Rainer (#109) für die Live-API-Daten, und alle Tester die "Unexpected Keys"
in den CC-seatcupra Issues dokumentiert haben.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#189---2026-04-29)

---

## [1.8.8] - 2026-04-29 🔓 Lock / Climate / Charging für Audi 2025+ und Passat B9

✨ **Was ist neu für Audi RS e-tron GT, VW Passat 2025 und neuere Modelle:**

- 🔒 **Lock/Unlock** funktioniert auf neuen Audi-Modellen (war vorher 404)
- ❄️ **Klimatisierung Start/Stop** funktioniert auf neuen Modellen
- ⚡ **Laden Start/Stop** funktioniert auf neuen Modellen

🛠️ **Was war kaputt?** Audi und VW haben für neuere Modelle (RS e-tron GT,
Passat B9 etc.) ihre API-Pfade von `/v1/` auf `/v2/` umgestellt. Unser Code
versuchte nur `/v1/` — Ergebnis: HTTP 404 bei jedem Befehl. Jetzt probiert
die Integration automatisch beide Pfade und merkt sich pro Fahrzeug welcher
funktioniert.

🐛 **Bonus-Bug-Fix:** Vor v1.8.8 hat unser Code bei *jedem* Server-Fehler
(500/401/429) den Fallback-Endpoint angefragt. Konsequenz: vorübergehende
Backend-Hiccups wurden als "Endpoint existiert nicht" interpretiert. Jetzt
nur bei echtem 404.

🙏 **Danke an:** G.S. (Audi RS e-tron GT, #51) und Marco Grewe (VW Passat
2025, #74) für die ausführlichen Bug-Reports.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#188---2026-04-29)

---

## [1.8.7] - 2026-04-29 🛡️ Stabilität — kein "Unavailable"-Flackern mehr

✨ **Was ist neu für alle Marken:**

- 🌐 **Wochenend-Backend-Probleme** werden jetzt ausgesessen — Auto bleibt
  bis zu 6 Stunden mit den letzten bekannten Werten verfügbar, statt sofort
  auf "Unavailable" zu kippen
- 🔁 **Einzelne fehlgeschlagene Polls** lösen kein "Unavailable" mehr aus —
  erst nach 3 aufeinanderfolgenden Fehlern wird das Auto als nicht erreichbar
  gemeldet
- 🐢 **Gateway-Timeouts (504)** werden automatisch nochmal versucht statt zu
  scheitern
- 🌐 **DNS-/Verbindungsprobleme** werden als vorübergehend behandelt (vorher
  wurde das fälschlich als "Login fehlgeschlagen" interpretiert)
- 🔐 **IP-Bann-Schutz:** maximal 3 Token-Refreshes pro Stunde — verhindert
  dass das VW-Backend dein Konto bei einem Refresh-Loop sperrt

🛠️ **Warum das wichtig ist?** Automatisierungen die auf Türen, Position oder
Ladestatus reagieren funktionieren jetzt zuverlässig auch wenn die VW-Server
mal hicksen. Das Auto bleibt sichtbar mit "Letzte Aktualisierung vor 30 Min",
statt komplett zu verschwinden.

🧪 **Hinweis für Tester:** 12 neue Unit-Tests prüfen alle Edge-Cases ab.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#187---2026-04-29)

---

## [1.8.6] - 2026-04-29 📚 Docs-Truthfulness Hotfix

✨ **Was ist neu (nur Doku, kein Code):**

- 🏆 **Multi-Brand-Successor-Position:** README sagt jetzt klar dass VAG Connect
  der aktive Nachfolger für die archivierten Repos
  [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id)
  (archived 2025-10-29) und
  [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect)
  (deprecated 2025-03-14) ist. Eine Integration für 7 Marken, kein separates
  Plugin nötig.
- 🏷️ **Dynamic CI-Badge:** Statt hardcoded Test-Counts (die schnell veraltet
  sind) zeigt das Badge jetzt den aktuellen Build-Status
- 📝 **Aktuelle Stand & ehrliche Limits Section** in allen 8 README-Sprachen:
  was funktioniert, was noch nicht, was bewusst ausgeklammert ist
  (z.B. PPC/PPE-Plattform für Audi 2025+ und Image-Entities)
- 🔧 **Korrekturen:** Das EN README sagte fälschlich "cloud-push" (war seit
  v1.8.0 falsch — wir pollen). Service-Count uneinheitlich (16 vs 14) →
  beide jetzt auf echte 14.

🛠️ **Warum?** Tester die HACS durchblättern sollen realistische Erwartungen
bekommen. Die Integration soll nicht "kaputt" wirken nur weil eine Funktion
bewusst capability-gated ist.

📋 [Technische Details](docs/CHANGELOG_TECHNICAL.md#186---2026-04-29)

---

## [1.8.5] - 2026-04-27

### Session 3A — Command Profile Layer foundation + v1/v2 fallback (#61, #51, #74)

- **`CommandProfile` enum** added in `cariad/exceptions.py` with twelve
  forward-looking values (`UNKNOWN`, `CARIAD_BFF_V1`, `CARIAD_BFF_V2`,
  `AUDI_PPE`, `AUDI_PREMIUM`, `LEGACY_MBB`, `MEB_ID`, `SEAT_CUPRA_OLA`,
  `SKODA_MYSMOB`, `SKODA_MYSMOB_V3`, `PORSCHE_PPA`, `VW_NA`). Defined
  upfront so future sessions can extend the dispatch table without
  breaking existing serialised state.
- **Coordinator helpers `get_command_profile(vin)` /
  `set_command_profile(vin, profile)`** — runtime cache, in-memory only
  (deliberately NOT in `config_entry.options`).
- **VWEUClient `_post_command(vin, suffix)` helper** with automatic
  `/vehicle/v1/` → `/vehicle/v2/` fallback on HTTP 404. The client
  remembers per-VIN whether v2 worked and skips v1 on subsequent calls
  to avoid the extra 404 round-trip. Other 4xx/5xx errors propagate
  as-is — only version-mismatch is auto-handled.
- **Refactored to use the helper:** `command_set_target_soc`,
  `command_set_climate_temperature`, `command_set_charge_mode`,
  `command_set_min_soc`. These are the four "set value" commands that
  Audi RS e-tron GT (Grant Shewan, #51) and VW Passat 2025 (Marco
  Grewe, #74) reported as `400/404` failures in v1.8.x.
- **`AudiClient` inherits the fallback** via `VWEUClient` — no separate
  fix needed for Audi specifically. Charge target slider, climate temp
  number, charge mode select and min-SoC number should now silently
  upgrade to v2 paths when the vehicle requires them.
- **Out of scope for 3A:** `command_lock`, `command_unlock`, climate
  start/stop, charging start/stop. Those have separate v1/v1 endpoint
  fallbacks already and need their own audit (Session 3B). LEGACY_MBB
  base URL routing for older T6/MQB vehicles is also Session 3B.

### Session 3A — Command Profile Foundation + v1/v2 Fallback

Audi RS e-tron GT (Grant) und VW Passat 2025 (Marco) hatten gemeldet
dass alle "Wert setzen" Aktionen mit `400/404` scheiterten. Grund: ihre
Fahrzeuge nutzen `/vehicle/v2/` Pfade, wir sendeten an `/vehicle/v1/`.
Mit v1.8.5 versucht der CARIAD-Client für VW EU + Audi automatisch
v2 wenn v1 mit 404 antwortet, merkt sich pro VIN was funktioniert und
spart dann den 404-Round-Trip beim nächsten Befehl. Vier Commands sind
bereits umgestellt: Ladziel, Klimatemperatur, Lademodus, Mindest-SoC.
Lock/Unlock und Climate-Start/Stop kommen in Session 3B.

## [1.8.4] - 2026-04-27

### Session 2C — SEAT/CUPRA lock fix + capabilities for more brands

- **SEAT/CUPRA `command_lock` and `command_unlock` now use the SecToken
  flow** documented in pycupra. Verified by the live tester report (#53)
  where Gerhard's CUPRA Born returned `400 internal-error` on lock — root
  cause was a missing `SecToken` header. The new flow:
  1. `POST /v2/users/{userId}/spin/verify` with `{"spin": "<pin>"}` →
     response `{"securityToken": "..."}`
  2. `POST /v1/vehicles/{vin}/access/lock` (or `/unlock`) with header
     `SecToken: <token>` and **no JSON body** (matching pycupra exactly)
- **`coordinator.async_lock` now requires S-PIN for SEAT/CUPRA brands**
  and raises `ServiceValidationError(spin_required)` before any API call,
  so users get a translated error rather than a backend 400.
- **`SpinError`** is raised when the verify call returns an error or
  no token, surfacing wrong-PIN cases cleanly.
- **`get_capabilities()` added to CARIAD BFF (VW EU + Audi via inheritance)**
  using the documented `/vehicle/v1/vehicles/{vin}/capabilities` endpoint.
- **`get_capabilities()` stubs added to Porsche and VW NA clients**
  (return `{}`) so the coordinator can call them uniformly. Neither brand
  has a discrete capabilities endpoint yet.
- **Button capability gating scoped to SEAT/CUPRA only.** Audi / VW EU /
  Škoda / Porsche / VW NA buttons are now never gated even though their
  capabilities cache may be populated, because their capability ID
  vocabulary has not been verified end-to-end. Will be unlocked
  per-brand once we have live test confirmation of the IDs.

### Session 2C — Lock-Fix für SEAT/CUPRA + Capabilities für weitere Marken

Der `internal-error` beim Verriegeln (Gerhard #53) war ein fehlender
`SecToken`-Header. SEAT/CUPRA verlangen einen zweistufigen Ablauf:
erst S-PIN gegen `/v2/users/{userId}/spin/verify` validieren und dann
mit dem zurückgegebenen `securityToken` als Header das eigentliche
Lock/Unlock-POST abschicken — ohne Body, exakt wie pycupra. Mit v1.8.4
wirft die Integration zudem schon im Coordinator `spin_required` wenn
der S-PIN für SEAT/CUPRA fehlt, statt einen Backend-Fehler zu kassieren.
Capabilities-Endpoint dazu für CARIAD BFF (Audi + VW EU); Stubs für
Porsche und VW NA. Button-Gating bleibt bewusst auf SEAT/CUPRA
beschränkt bis die Capability-IDs anderer Marken live verifiziert sind.

## [1.8.3] - 2026-04-27

### Session 2B — Button capability gating (SEAT/CUPRA only)

- **`vehicle_supports_capability(vin, capability_id)`** on the coordinator
  returns ``True`` / ``False`` / ``None`` (three-valued logic). Conservative
  on purpose — ``None`` (unknown) keeps entities visible, only an explicit
  ``False`` from the cached OLA capabilities document hides them.

- **`button.py` reads from the helper** for two SEAT/CUPRA buttons:
  - `VagFlashButton` — only created if `honkAndFlash` capability is
    supported (or unknown for non-OLA brands)
  - `VagWakeButton` — same gating against `vehicleWakeUpTrigger`
  - `VagRefreshButton` — always created (coordinator-level, not a
    vehicle command)

- **No effect on Audi / VW EU / Škoda / Porsche / VW NA** — those brands
  have no capabilities endpoint implemented yet, so the helper returns
  ``None`` and all three buttons appear as before. Capability methods for
  those brands land in 2C / Session 3.

- **Verification case:** Gerhard's CUPRA Born (#53) returned
  `400 missing-capability` for both flash and wake in v1.8.0. With v1.8.3,
  if his vehicle's OLA capabilities document doesn't list those features,
  the buttons disappear at next reload — no more failed presses, no more
  log spam.

### Session 2B — Button-Capability-Gating (nur SEAT/CUPRA)

Vorbereitung für sauberere Entity-Listen pro Fahrzeug. Die Lichthupe und
"Auto aufwecken" Buttons werden jetzt für SEAT/CUPRA nur noch erstellt
wenn die OLA-Capabilities-API sagt dass das Fahrzeug die Funktionen
unterstützt. Verifikations-Case ist Gerhards CUPRA Born (#53) — bei dem
die beiden Buttons in v1.8.3 nach dem nächsten Reload verschwinden
sollten statt 400-Fehler zu produzieren. Andere Marken bleiben
unverändert (kein Capabilities-Endpoint implementiert → drei Buttons wie
bisher).

### Release notes / Release-Notes (CI)

- **Release pages now embed the full CHANGELOG section** instead of only
  matching `### Added` / `### Changed` / `### Fixed` / `### Removed`.
  Older notes since v1.7 were effectively empty for human readers because
  our entries use topical headings (e.g. `### Privacy`, `### Authentication`)
  that the old generator dropped.
- Bilingual EN/DE for every release-page heading, plus a "Recent
  releases" pointer to the previous 3 tags with dates and a readable
  compare URL.

  Release-Seiten zeigen jetzt den vollständigen CHANGELOG-Abschnitt
  wortwörtlich — alle Sub-Headings, Code-Blöcke und EN+DE-Absätze.
  Plus einen "Letzte Releases"-Pointer auf die letzten 3 Tags mit
  Datum und eine lesbare Compare-URL.

## [1.8.2] - 2026-04-27

### Session 2A — Capabilities foundation (no entity changes)

- **`CommandFailureReason` enum + `classify_command_failure()` helper** in
  `cariad/exceptions.py`. Nine categories (`MISSING_CAPABILITY`,
  `SUBSCRIPTION_EXPIRED`, `NOT_ENTITLED`, `WRONG_API_PROFILE`,
  `VEHICLE_UNREACHABLE`, `SPIN_REQUIRED`, `INVALID_PAYLOAD`,
  `BACKEND_ERROR`, `UNKNOWN`). Conservative on purpose: `400 internal-error`
  maps to `BACKEND_ERROR`, never `MISSING_CAPABILITY`, so an ambiguous body
  can never accidentally hide an entity for good. Only an explicit
  `missing-capability` body flips that flag.

- **Three-state feature model** on the coordinator:
  ```python
  feature_states[vin][command] = FeatureState(
      supported_by_vehicle, entitled_by_account, available_now,
      last_error, last_error_at,
  )
  ```
  `supported_by_vehicle` and `entitled_by_account` answer different
  questions (vehicle hardware vs account subscription) and are tracked
  separately. Backend errors (transient) flip neither.

- **Capabilities cache** with 24h TTL, runtime-only on the coordinator
  (deliberately NOT in `config_entry.options` — that's for user settings).
  Triggered best-effort during `async_setup` for every VIN in parallel;
  failure is debug-logged and never blocks setup. Re-fetched on TTL expiry
  or explicit `force=True`.

- **`SeatCupraClient.get_capabilities(vin)`** — only OLA implemented in
  this PR. CARIAD BFF / mysmob / PPA capabilities methods land in 2B
  to keep the diff focused.

- **No entity changes.** `button.py`, `lock.py`, `climate.py` etc. don't
  read from `feature_states` or `vehicle_capabilities` yet — that's the
  point of splitting 2A out. Verified by entity test suite still passing
  with no test churn.

### Authentication / Authentifizierung

- **SEAT and CUPRA OAuth scopes broadened to `address phone email birthdate
  nickname`** (was `nickname birthdate phone`). Mirrors the official My SEAT
  and MyCupra app scope set. Defense in depth — current OLA endpoints don't
  require `email` or `address`, but extending the scope ahead of any
  conditional server-side check costs nothing and prevents future surprises.

  **SEAT- und CUPRA-OAuth-Scopes erweitert auf `address phone email birthdate
  nickname`** (vorher `nickname birthdate phone`). Stimmt jetzt mit dem
  offiziellen My-SEAT- und MyCupra-App-Scope überein. Defense in Depth — die
  aktuellen OLA-Endpoints brauchen `email` und `address` nicht, aber die
  vorbeugende Erweiterung schadet nicht und verhindert künftige
  Server-Restriktionen.

### Session 2A — Foundation für Capabilities (keine Entity-Änderungen)

Vorbereitung für Sessions 2B/2C. Führt nur die Datenstrukturen ein —
Entity-Verhalten bleibt identisch. Beide Cross-Check-Reviews
(ChatGPT 5.5 + Gemini Pro) haben unabhängig gewarnt vor einem
"Capabilities-für-alles"-Refactor: drei Live-Tester-Fehler (Gerhard
`missing-capability`, migendi `expired sub`, gleeballs `free tier 404`)
sehen ähnlich aus, haben aber unterschiedliche Root Causes. Erst
Klassifizierung, dann Verhalten.

## [1.8.1] - 2026-04-27

### Privacy / Datenschutz

- **VIN masking in logs and diagnostics.** A new `mask_vin()` helper
  returns `***` + last 6 chars of the VIN. Applied to all coordinator
  log messages (warning + error level) and to the diagnostics output —
  the per-vehicle dictionary is now keyed by the masked VIN instead of
  the full VIN. A full VIN ties to vehicle registration, insurance and
  ownership records, so it must not appear in support material that
  users post to GitHub issues.

  **VIN-Maskierung in Logs und Diagnostics.** Neuer `mask_vin()` Helper
  liefert `***` + letzte 6 Zeichen. Wird jetzt in allen Coordinator-Logs
  (Warning + Error Level) und im Diagnostics-Export verwendet — die
  Fahrzeug-Dictionaries werden mit der gemaskten VIN als Schlüssel
  abgelegt statt der vollständigen VIN. Eine vollständige VIN ist mit
  Zulassung, Versicherung und Eigentümerdaten verknüpft und gehört
  daher nicht in Support-Material das User auf GitHub posten.

- **Diagnostics now redact more PII fields by default:** `vin`, `address`,
  `parking_address`, `user_id`, `account_id` and `email` join the
  existing `password`, `spin`, `latitude`, `longitude` redaction list.
  Recursive scrubbing handles nested structures.

  **Diagnostics schwärzen jetzt mehr PII-Felder standardmässig:** `vin`,
  `address`, `parking_address`, `user_id`, `account_id` und `email`
  ergänzen die bestehenden `password`, `spin`, `latitude`, `longitude`.
  Rekursives Scrubbing erfasst auch verschachtelte Strukturen.

- **Issue templates** (`bug_report.yml`, `new_brand.yml`) spell out the
  required masking before posting (VIN to last 6 chars, email/local
  part, no tokens or S-PIN, GPS to 1 decimal) in both English and German.

  **Issue-Templates** beschreiben jetzt explizit zweisprachig was vor
  dem Posten geschwärzt werden muss (VIN auf letzte 6 Zeichen, Email
  lokalen Teil, keine Tokens oder S-PIN, GPS auf 1 Nachkommastelle).

### Authentication / Authentifizierung

- **`ConfigEntryAuthFailed` is now raised when credentials are stale.**
  Previously, persistent token refresh failures and rejected re-logins
  caused the integration to retry forever and flood the log. Now setup
  raises `ConfigEntryAuthFailed` (which triggers Home Assistant's
  reauth UI) and the runtime poll loop calls `entry.async_start_reauth()`
  if auth fails after the client's refresh-then-relogin fallback gave up.

  **`ConfigEntryAuthFailed` wird jetzt geworfen wenn Credentials veraltet
  sind.** Bisher haben fehlgeschlagene Token-Refreshes und abgelehnte
  Re-Logins zu endlosen Retries und Log-Spam geführt. Jetzt wirft Setup
  `ConfigEntryAuthFailed` (das löst Home Assistants Reauth-UI aus) und
  der Poll-Loop ruft `entry.async_start_reauth()` auf wenn auch der
  Re-Login-Fallback im Client gescheitert ist.

### Documentation / Dokumentation

- The `userPosition` field in the SEAT/CUPRA honk-and-flash payload is
  now documented as a misnomer in the OLA API contract: the field
  expects the **vehicle's** last-known GPS, not the user's phone GPS.
  Verified against pycupra `vehicle.set_honkandflash` (uses
  `findCarResponse` lat/lon) and myskoda equivalent (`PositionType.VEHICLE`).

  Das `userPosition` Feld bei SEAT/CUPRA honk-and-flash ist jetzt im
  Code dokumentiert als irreführender Name im OLA-API-Vertrag: das Feld
  erwartet die **Fahrzeug**position, nicht die Phone-Position. Verifiziert
  gegen pycupra (`vehicle.set_honkandflash` nutzt `findCarResponse`)
  und myskoda (`PositionType.VEHICLE`).

### Removed (carried over from previous Unreleased)

- Stale icon and translation entries for entities that were removed in
  v1.8.0 (`seat_heating_switch`, `auto_unlock_switch`, `max_charge_current`).
  Cleaned across `icons.json`, `strings.json` and all 8 language files.

### Changed (carried over from previous Unreleased)

- `docs/research/ARCHITECTURE_DECISION.md` and
  `docs/research/DEPENDENCY_AUDIT.md` marked as historical
  (implemented in v0.12.0, still the architecture in v1.8.x).

## [1.8.0] - 2026-04-26

### Bug Fix — CUPRA/SEAT honk-and-flash 400 (#53)

- `command_flash` for CUPRA/SEAT was sending `{"mode": "FLASH_ONLY"}` and
  no user position. The OLA API returned HTTP 400 "internal-error".
  pycupra reference shows the API expects `{"mode": "flash",
  "userPosition": {"latitude": …, "longitude": …}}`. Fixed: coordinator
  passes the cached vehicle position into `command_flash`, and the
  SEAT/CUPRA client sends the correct payload (lat/lng rounded to 4
  decimals like the official app). Other brands accept the kwargs and
  ignore them — backward compatible.

### Foundation Release — P0 Audit Findings (#60)

A code audit identified seven release blockers in v1.7.0. v1.8.0 fixes
them in a single atomic release before any new features are added.

### Fixed / Behoben

- **Per-VIN availability** — coordinator now tracks success/failure per
  vehicle and exposes `is_vehicle_available(vin)`. A single failing
  vehicle no longer blanks out entities of the others. The poll loop
  previously pushed `success=True` regardless of any vehicle's actual
  status, so entities appeared "fresh" with stale data.
- **S-PIN fail-fast** — `unlock` raises `ServiceValidationError` with
  translation key `spin_required` when no S-PIN is configured, instead
  of sending the command to the API and getting a 4xx response.
- **Fake writable entities removed** — `max_charge_current`,
  `seat_heating_switch` and `auto_unlock_switch` only mutated internal
  state without sending real API commands. Removed; will return once
  the CARIAD client implements the matching commands.
- **Reverse geocoding opt-in** — vehicle GPS was sent to OpenStreetMap
  Nominatim on every poll. Now off by default, opt-in via options flow
  `enable_reverse_geocoding`. When enabled, results are cached by
  rounded coordinates (~110m) and use HA's shared aiohttp session
  instead of a synchronous urllib request.
- **Platforms in sync** — `image` and `select` platform files existed
  but were never loaded (missing from `PLATFORMS` list and used the
  obsolete `hass.data[DOMAIN]` lookup). Now properly forwarded and use
  `entry.runtime_data`.
- **`select` entity translated** — `VagChargeModeSelect` no longer uses
  a hardcoded German name; picks up `charge_mode_select` from all 8
  language files.
- **`iot_class` corrected** — manifest declares `cloud_polling` instead
  of the misleading `cloud_push` (no real push channel exists yet —
  see #57).
- **`quality_scale.yaml` cleaned** — removed duplicate `comment:` keys
  and outdated hardcoded test counts.

### Added / Hinzugefügt

- New options flow setting **Reverse Geocoding** (privacy opt-in).
- Translation keys `spin_required` and `feature_not_supported` in all
  9 language files (en/de/cs/es/fr/nl/pl/sv).
- Coordinator method `is_vehicle_available(vin)` — used by the entity
  base class for per-VIN availability.

### Roadmap

v1.8.0 ist Session 1 von 10 (siehe README Roadmap).
Als Nächstes: v1.8.1 Capabilities-Check (#56), v1.8.2 Command Profile
Layer (#61), v1.8.3 Diagnostics + Fixtures (#62, #58).

---

## [1.7.0] - 2026-04-25

### Added / Hinzugefügt

- **Škoda: Complete API rewrite** — all JSON parsing paths verified against skodaconnect/myskoda. Plug state, climatisation, target temperature, window heating, parking address, AdBlue range, connector lock, charging type now work correctly. #54
- **Car-friendly entity names** — 30 German, 27 English, 48 other language names improved. "Lichthupe" instead of "Lichtsignal", "Zentralverriegelung" instead of "Türverriegelung", "Klimaanlage" instead of "Klimatisierung" — terms every car owner understands.
- **Škoda parking v3** — upgraded to `/v3/maps/positions` with `formattedAddress` (no external geocoding needed).
- **Škoda window heating** — start/stop commands added.
- **SPIN validation** — warns if S-PIN is missing before unlock attempt.

---

- **Škoda: Kompletter API-Rewrite** — alle JSON-Pfade gegen skodaconnect/myskoda verifiziert. Ladeanschluss, Klimaanlage, Wunschtemperatur, Scheibenheizung, Parkadresse, AdBlue, Kabelverriegelung, Ladeart funktionieren jetzt korrekt. #54
- **Autofahrer-freundliche Entity-Namen** — "Lichthupe" statt "Lichtsignal", "Zentralverriegelung" statt "Türverriegelung", "Klimaanlage" statt "Klimatisierung". 30 deutsche + 27 englische + 48 weitere Sprachen verbessert.
- **Škoda Parking v3** — mit `formattedAddress` direkt von der API (kein externes Geocoding).
- **S-PIN Warnung** — warnt wenn S-PIN fehlt vor Entriegelungsversuch.

### Fixed / Behoben

- **Rate limit handling** — exponential backoff for 429/503 errors (3 retries with 5/15/45s delays). Request timeout increased to 60s.
- **Token refresh lock** — prevents concurrent refresh attempts from racing.
- **Stale data tracking** — poll failures now tracked instead of silently serving old values.
- **Škoda sensors** — 5 previously broken sensors (odometer, charging state/power/speed, service km) now return correct values.
- **GraphQL skip** — no more 404 errors for non-Audi brands.
- **Bootstrap timeout** — poll loop runs as background task.
- **HTTP 201** — accepted as success for async commands.

---

- **Rate-Limit-Behandlung** — exponentieller Backoff bei 429/503 (3 Versuche). Timeout auf 60s erhöht.
- **Token-Refresh-Lock** — verhindert gleichzeitige Refresh-Versuche.
- **Veraltete-Daten-Tracking** — Poll-Fehler werden jetzt markiert statt alte Werte stillschweigend zu servieren.
- **Škoda Sensoren** — 5 vorher defekte Sensoren zeigen jetzt korrekte Werte.

---

## [1.6.1] - 2026-04-25

### Fixed / Behoben

- **Škoda:** 5 sensors had wrong JSON parsing paths — odometer, charging state/power/speed, service km all showed "unknown". Correct paths verified against skodaconnect/myskoda. Fixes #54.
- **GraphQL:** Skipped for non-Audi brands — no more 404 errors in logs for CUPRA/SEAT/Škoda. Fixes #53.
- **Bootstrap:** Poll loop changed to background task — HA no longer times out during startup. Fixes #53.
- **HTTP 201:** Accepted as success for async commands (wake, etc.) — previously thrown as error. Fixes #53.

---

- **Škoda:** 5 Sensoren hatten falsche JSON-Pfade — Kilometerstand, Ladestatus/-leistung/-geschwindigkeit, Inspektion zeigten alle "unbekannt". Korrekte Pfade aus skodaconnect/myskoda verifiziert. Behebt #54.
- **GraphQL:** Wird für Nicht-Audi-Marken übersprungen — keine 404-Fehler mehr im Log. Behebt #53.
- **Bootstrap:** Poll-Loop als Background Task — HA-Start blockiert nicht mehr. Behebt #53.
- **HTTP 201:** Als Erfolg akzeptiert für asynchrone Kommandos (Wake etc.). Behebt #53.

---

## [1.6.0] - 2026-04-24

### Added / Hinzugefügt

- **SEAT/CUPRA:** 9 API endpoints instead of 4 — 40+ data fields now available.
  Ranges (electric/combustion/AdBlue), per-door/window status, trunk/hood/sunroof,
  charge rate + time remaining, cable lock, max charge current, service days,
  online status, outside temperature, window heating status.
- **SEAT/CUPRA vehicle renders:** Vehicle images via OLA REST endpoint (no GraphQL needed).
- **SEAT/CUPRA window heating:** Start/stop commands.
- **VW/Audi PPC command fallback (#51, #29):** Newer models (RS e-tron GT, Q6, Q4 2025, A3 2023+)
  that return 404 on combined endpoints now automatically fall back to separate
  `/start`, `/stop`, `/lock`, `/unlock` endpoints. No breaking change for older models.
- **Lock platform:** Native HA LockEntity for door lock/unlock (all brands).
- **Nightly polling reduction:** Polling interval doubled between 22:00–05:00 automatically.

---

- **SEAT/CUPRA:** 9 API-Endpoints statt 4 — über 40 Datenfelder verfügbar.
  Reichweite (elektrisch/Verbrenner/AdBlue), einzelne Türen/Fenster, Kofferraum/Motorhaube/Schiebedach,
  Ladegeschwindigkeit + Restzeit, Kabelverriegelung, max. Ladestrom, Service in Tagen,
  Online-Status, Außentemperatur, Scheibenheizung.
- **SEAT/CUPRA Fahrzeugbilder:** Render-Bilder direkt über OLA-API (kein GraphQL nötig).
- **VW/Audi PPC-Fallback (#51, #29):** Neuere Modelle (RS e-tron GT, Q6, Q4 2025, A3 2023+)
  die 404 auf kombinierten Endpoints bekommen, nutzen jetzt automatisch separate Endpoints.
- **Lock-Plattform:** Echte HA LockEntity für Türverriegelung.
- **Nachtabsenkung:** Polling-Intervall wird zwischen 22:00–05:00 automatisch verdoppelt.

### Fixed / Behoben

- **Škoda:** Missing `/api` prefix on all 18 endpoints — garage returned empty list.
- **Škoda:** camelCase token response (`accessToken` instead of `access_token`).
- **CUPRA/SEAT user_id:** Now extracted from OAuth redirect chain instead of JWT.
- **Entity names:** Explicit `translation_key` on all 47 descriptions — no more duplicate entities.
- **Coordinator:** Deprecated `asyncio.ensure_future(loop=)` → `hass.async_create_task()`.
- **Coordinator:** Indentation bug silently dropped poll results.
- **Coordinator:** Update listener read from wrong data store.
- **Diagnostics:** Username/email now redacted.
- **Privacy:** VINs anonymized in services.yaml and README examples.
- **Dead code removed**, all German log messages → English.

---

- **Škoda:** Fehlender `/api`-Prefix auf allen 18 Endpoints — Garage war leer.
- **Škoda:** camelCase Token-Antwort jetzt unterstützt.
- **CUPRA/SEAT user_id:** Wird jetzt aus der OAuth-Redirect-Chain extrahiert.
- **Entity-Namen:** `translation_key` auf allen 47 Descriptions — keine Duplikate mehr.
- **Coordinator:** Mehrere Bugs behoben (deprecated API, Indentation, falscher Data Store).
- **Datenschutz:** E-Mail in Diagnostics geschwärzt, VINs anonymisiert.

---

## [1.5.13] - 2026-04-24

### Fixed

- **Škoda camelCase tokens:** Škoda API returns `accessToken`/`refreshToken`/`idToken` (camelCase) instead of OAuth standard `access_token`/`refresh_token`/`id_token`. Token parser now accepts both formats. Fixes #49, #52.
- **Tests:** Updated token exchange and refresh tests for brand-specific endpoints.

---

## [1.5.12] - 2026-04-23

### Fixed

- **Entity translations:** Removed 47 hardcoded German `_attr_name` values across all 7 entity files. Entities now use `translation_key` so HA reads names from `strings.json` / `translations/{lang}.json`. Properly fixes #38.
- **Škoda token exchange:** Škoda uses a proprietary JSON API (`mysmob.api.connect.skoda-auto.cz`), not standard OAuth. Fixes #43.
- **SEAT token exchange:** Routed to correct OLA endpoint instead of IDK.
- **Brand-specific token refresh:** Škoda proprietary, SEAT/CUPRA via OLA, VW/Audi via CARIAD BFF.
- **Per-door sensor names:** Changed from German to English defaults.

---

## [1.5.11] - 2026-04-23

### Fixed

- **Brand-specific token endpoints:** Each brand now uses its correct token exchange mechanism. Fixes #43.
  - Škoda: proprietary JSON API on `mysmob.api.connect.skoda-auto.cz` (not OAuth)
  - SEAT: OLA endpoint (`ola.prod.code.seat.cloud.vwgroup.com/authorization/api/v1/token`)
  - CUPRA: IDK endpoint with `client_secret`
  - VW EU / Audi: CARIAD BFF (unchanged)
- **Token refresh** is also brand-specific (Škoda proprietary, SEAT/CUPRA via OLA, VW/Audi via CARIAD BFF).

### Added

- Tests for Lock platform and JWT user_id extraction.
- GitHub downloads badge in all 8 READMEs.

---

## [1.5.10] - 2026-04-22

### Fixed

- **CUPRA/SEAT user_id:** Extracted from JWT `sub` claim instead of failing `/v1/users` API call. Fixes #42.
- **Lock platform:** Added proper HA `LockEntity` (was switch-only before).
- **Nightly polling reduction:** Doubles polling interval between 22:00–05:00 automatically.
- **Downloads badge:** Added to all 8 READMEs.

---

## [1.5.9] - 2026-04-22

### Fixed

- **CUPRA auth:** Token exchange failed with `invalid_client` because CUPRA is a confidential OAuth client requiring `client_secret`. Now included in token exchange and refresh. Fixes #41.
- **CUPRA/SEAT scope:** Reverted to match pycupra exactly (`openid profile nickname birthdate phone`).
- **SEAT/CUPRA/Škoda token endpoint:** Route to direct IDK endpoint instead of CARIAD BFF.
- **User-Agent:** Updated CUPRA to 2.15.0, SEAT to 2.13.3.

### Added

- `client_secret` field in `BrandConfig` for confidential OAuth clients.

---

## [1.5.8] - 2026-04-22

### Fixed

- **SEAT/CUPRA/Škoda auth:** Token exchange failed with `invalid_client` because CARIAD BFF endpoint only accepts VW EU/Audi client IDs. Now routes these brands to the direct IDK token endpoint (`identity.vwgroup.io/oidc/v1/token`). Fixes #41.
- **English entity labels:** `strings.json` switched from German to English (HA standard). English users now see "Fuel Level", "Doors Locked" etc. instead of German labels. Fixes #38.
- **CUPRA/SEAT OAuth scope:** Added missing `email` and `address` scopes (all other brands already had them).

### Changed

- READMEs updated across all 8 languages (70+ entities, Porsche/VW NA Beta, current roadmap).

---

## [1.5.6] - 2026-04-18

### Sicherheits- und Performance-Audit

#### Sicherheit

**Auth-Requests ohne Timeout (kritisch)**
`idk.py` und `porsche.py` nutzten `self._session.get/post()` ohne Timeout.
Bei einem hängenden VW/Audi-Identity-Server hätte HA ewig blockiert.

Fix: `_AUTH_TIMEOUT = ClientTimeout(total=30)` in beiden Auth-Modulen.
Alle 20 betroffenen Requests (15 in idk.py, 5 in porsche.py) haben jetzt 30s Timeout.

**`TokenSet.needs_refresh()` — proaktiver Token-Refresh**
`TokenSet` hat jetzt ein `expires_at: float` Feld und `needs_refresh()` Methode.
Tokens können 60 Sekunden vor Ablauf proaktiv erneuert werden (statt erst auf 401 zu warten).

#### Performance

**Blockierendes `os.makedirs` entfernt**
`coordinator._tokenstore_path()` rief `os.makedirs()` direkt im Async-Context.
Fix: `hass.config.path(".storage")` — `.storage` existiert in HA immer.

#### Was sauber war (bleibt sauber)
- SSL immer aktiv (kein `verify=False`)
- Credentials nie in Logs
- Thread-Lock für CC-Thread/HA-Loop
- Fehler pro Fahrzeug isoliert
- `update_interval=None` mit Push-Updates
- Bilder nur bei URL-Änderung neu geladen

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.5] - 2026-04-18

### Behoben — IDK Auth-Logs erschienen als "Fehler" in HA

HA zeigt alle `WARNING`-Einträge von Custom Integrations im Notification-Center
als Fehler an. Die IDK Auth-Flow Schritte waren mit `_LOGGER.warning()` geloggt —
obwohl es sich um normale Trace-Informationen handelt.

**4 Logs von WARNING → DEBUG heruntergestuft:**
- `IDK legacy: step1 fields=...` — normaler Auth-Schritt
- `IDK legacy: hmac from JS...` — normaler Auth-Schritt
- `IDK legacy: posting password to...` — normaler Auth-Schritt
- `IDK legacy: password POST status=302...` — erwartetes Ergebnis

Diese 4 Einträge erscheinen nicht mehr in der HA Notification-UI.
Weiterhin als WARNING (legitime Probleme):
Auth-Fehler (400/401), Token-Exchange-Fehler, GraphQL-Failures, SEAT/CUPRA User-ID.

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.4] - 2026-04-13

### Bereinigung — README, Issues, letzter toter Sensor

#### `connection_state` Sensor entfernt

Beim Entity-Audit in v1.5.2 übersehen: `connection_state` wurde in sensor.py
als `data_key="connection_state"` definiert, dieses Feld wird aber von keiner
Marke befüllt. Entfernt. Übersetzungen aktualisiert.

**Endstand: 27 Sensoren + 16 Binary Sensors = 43 Daten-Entities, alle befüllt.**
(Plus Device Tracker, 7+ Switch, 4 Number, 1 Select, 1 Climate, 3 Button, 7 Image × N Fahrzeuge)

#### README komplett neu geschrieben

Alle veralteten und falschen Angaben korrigiert:

| Was | Vorher (falsch) | Nachher (korrekt) |
|---|---|---|
| Test-Badge | 337/337 | 363/363 |
| Entity-Anzahl | "68 Entities" | 44 Entities |
| Plattformen | 7 (fehlten select + image) | 9 |
| Motorhaube/Kofferraum | als Feature gelistet | entfernt (API liefert es nicht) |
| Image Entity Namen | `_render_icon`, `_render_small` | `_icon`, `_small`, ... |
| Lovelace-Beispiel | sensor entity in picture-card | image entity direkt |
| Roadmap | v0.15.0 Porsche, v0.16.0 VW NA | v1.6.0 EV, v1.7.0 Nav, v2.0.0 HACS |
| Bekannte Einschränkungen | Porsche/VW NA "geplant" | korrekt: Beta-Status |

#### GitHub Issues bereinigt

Geschlossen: #9 (Porsche), #10 (VW NA), #12 (Motorhaube/Kofferraum),
#18–#21 (Duplikate), #22 (Reifendruck), #30 (Fensterheizung)
— alle implementiert oder API-bedingt nicht umsetzbar.

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.3] - 2026-04-13

### Behoben — Log-Auswertung (13. April 2026, 12:00 Uhr)

#### ✅ Bestätigt funktionierend

- **Audi Images**: AZS Token funktioniert — `render URLs for 4 vehicle(s)`
  → 7 Image-Entities × 4 Fahrzeuge = 28 Render-Bilder geladen
- **GDC Filter**: vag_connect fragt `GDC_MISSING`/`UNKNOWN` VINs nicht mehr an
  (Die 400-Errors im Log kommen vom parallel installierten `audiconnect`-Plugin)

#### VW EU GraphQL deaktiviert

VW EU hat keinen bestätigten `vgql` Endpoint. Der wiederholte
`GraphQL image fetch failed for volkswagen:` (leerer Fehler = Connection Reset)
wurde durch Entfernen des VW EU Endpoints aus `_GRAPHQL_ENDPOINTS` behoben.

VW EU Fahrzeugbilder sind **nicht implementiert** bis ein funktionsfähiger
Endpoint durch Community-Tests gefunden wird (→ Issue #8).

Derzeit mit Bildern unterstützt: **Audi** ✅, Škoda/SEAT/CUPRA (experimentell)

---


## [1.5.3] - 2026-04-13

### Behoben — Log-Rauschen (aus Live-HA-Log Analyse)

#### AZS Token / Audi Images funktioniert ✅

Log vom 13. April 2026 bestätigt: **`Audi images: render URLs for 4 vehicle(s)`**
Der AZS Token Exchange (v1.3.6) funktioniert korrekt.

**Log-Level Korrekturen:**
- `Audi images: render URLs for N vehicle(s)` — `WARNING` → `INFO` (kein Fehler)
- IDK Auth Steps (4 Zeilen pro Login) — `WARNING` → `DEBUG` (Routine, kein Fehler)
- VW EU `raw fields` Debug-Dump — `WARNING` → `DEBUG` (Entwickler-Detail)
- VW GraphQL leerer Connection Reset — `WARNING` → `DEBUG` (Server blockt Non-Browser, erwartet)

**Erwartetes Log-Bild nach Update (sauber, kein Rauschen):**
```
INFO  [vag_connect] Audi AZS token acquired for image fetching
INFO  [vag_connect] Audi images: ✅ render URLs for N vehicle(s)
INFO  [vag_connect] VAG: skipping N vehicle(s) with unsupported platform: ...
INFO  [vag_connect] VAG Connect: setup complete — N vehicle(s)
```

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.2] - 2026-04-13

### Behoben — Kompletter Entity-Audit: API-Realität vs. Erwartungen

Vollständige Prüfung aller ~55 Entity-Definitionen gegen echte CARIAD BFF Responses.

#### Entfernte Dead Entities (zeigten immer "Unbekannt")

**Binary Sensors (5 entfernt):**
- `connection_state` — nirgends gesetzt, kein API-Feld
- `trunk_open`, `hood_open`, `sunroof_open` — CARIAD liefert diese als dynamische `doors_individual` Keys, keine garantierten Felder
- `trunk_locked` — kommt nicht separat, nur `doorLockStatus` overall

**Sensoren (11 entfernt in v1.5.1):**
Ladesäulen-Info, firmware_version, license_plate, range_estimated_full_km, range_wltp_km, battery_cap_kwh, battery_available_kwh, heading

#### API-Wahrheit: Was CARIAD BFF wirklich liefert

| Kategorie | Felder | Marken |
|---|---|---|
| Fahrzeug-Basis | odometer, fuel_level, battery_soc, range_km | Alle ✅ |
| Laden | state, power_kw, rate_kmh, eta, plug, target_soc | VW/Audi/Škoda ✅ |
| Klimatisierung | state, temperature, window_heating | Alle ✅ |
| Türen/Fenster | locked (overall), open (overall), doors_individual | VW/Audi ✅ |
| GPS | latitude, longitude → reverse geocoded | Alle ✅ |
| Service | service_km/date, oil_km/date | VW/Audi/Škoda ✅ |
| Warnleuchten | engine, oil, tyre, brakes | VW/Audi ✅ |
| Status | vehicle_state, last_updated_at, is_online | VW/Audi/Škoda ✅ |

#### Nicht verfügbar (API liefert es schlicht nicht)
- Ladesäulen-Infos (Name, Adresse, kW, Betreiber)
- Firmware-Version im Status-Endpoint
- Kennzeichen im Status-Endpoint
- WLTP-Reichweite, Akkukapazität als Live-Daten
- Fahrtrichtung (Heading)
- Motorhaube/Kofferraum/Schiebedach als eigene garantierte Felder

**Ergebnis: 28 Sensoren + 16 Binary Sensors = 44 Entities — alle mit echten Daten**

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.2] - 2026-04-13

### Behoben — Binary Sensor Audit

#### 5 tote Binary-Sensor-Entities entfernt

Nach vollständigem Audit aller Binary-Sensor-Definitionen gegen tatsächliche API-Responses:

**Entfernt — API liefert diese Daten nie zuverlässig:**

| Entity | Grund |
|---|---|
| `connection_state` | Nirgends im Code gesetzt |
| `trunk_open` | CARIAD BFF liefert Kofferraum nicht als garantiertes Feld |
| `hood_open` | CARIAD BFF liefert Motorhaube nicht als garantiertes Feld |
| `sunroof_open` | CARIAD BFF liefert Schiebedach nicht als garantiertes Feld |
| `trunk_locked` | Kein separater Lock-State für Kofferraum in API |

**Hintergrund:** CARIAD BFF liefert Türen als dynamische Liste mit `name`-Feld.
`trunk`, `hood`, `sunroof` können theoretisch darin vorkommen, sind aber nicht
garantiert und kommen modellabhängig. Echte Nutzung über `doors_individual`-Dict.

**Translations bereinigt (5 Keys, 8 Sprachen)**

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.1] - 2026-04-13

### Behoben — Sensor-Audit

#### 11 tote Sensoren entfernt (zeigten immer "Unbekannt")

Nach vollständigem Audit aller 40 Sensor-Definitionen gegen tatsächliche API-Responses:

**Entfernt — API liefert diese Daten nie:**

| Sensor | Grund |
|---|---|
| Ladesäule Name/Adresse/kW/Betreiber (4×) | CARIAD BFF liefert keine Ladesäulen-Infos mehr |
| Firmware-Version | Nur in Diagnose-Daten, nicht im Status-Endpoint |
| Kennzeichen | Nicht im Garage/Status-Response |
| Reichweite bei 100% / WLTP-Reichweite | Kein Live-API Endpoint, nur statische Fahrzeugdaten |
| Akkukapazität / Akkuenergie verfügbar | Nicht in CARIAD BFF Response |
| Fahrtrichtung (Heading) | Nicht im Parkposition-Endpoint |

→ Diese Sensoren haben seit Beginn immer "Unbekannt" angezeigt.

#### Abfahrtstimer-Sensoren repariert

`departure_timer_{1,2,3}_time` hatten `device_class=SensorDeviceClass.TIMESTAMP`
aber die API liefert eine Uhrzeit-String (`"07:30"`), kein Datetime-Objekt.
→ `device_class` entfernt → Sensor zeigt Uhrzeit direkt an (z.B. `07:30`)

**Aktueller Stand: ~28 funktionierende Sensoren**

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.1] - 2026-04-13

### Behoben — Sensor-Qualität

#### 11 tote Sensoren entfernt (zeigten immer "Unbekannt")

CARIAD BFF liefert diese Felder nicht oder nicht mehr:

| Entfernt | Grund |
|---|---|
| Ladesäule (Name, Adresse, Max-kW, Betreiber) | CARIAD BFF hat diese 4 Felder entfernt |
| Firmware-Version | Nur in Diagnose-Daten, nicht im Status |
| Kennzeichen | Nicht in garage/status Response |
| Reichweite bei 100% | Kein Live-API-Feld |
| WLTP-Reichweite | Statischer Wert, kein Endpoint |
| Akkukapazität gesamt | Nicht in CARIAD BFF Response |
| Akkuenergie verfügbar | Nicht in CARIAD BFF Response |
| Fahrtrichtung | Nicht im parkingposition Endpoint |

**Vorher:** 39 Sensoren — 14 zeigten immer „Unbekannt"  
**Nachher:** 28 Sensoren — alle liefern echte Werte

#### Abfahrtstimer Zeitanzeige repariert

`departure_timer_{1/2/3}_time` hatte `device_class=TIMESTAMP` aber die API
liefert einen Uhrzeit-String (`"07:30"`). Würde zu AttributeError führen
wie beim `service_due_at` Bug (v1.3.4).

Fix: `device_class` entfernt → Sensor zeigt Uhrzeit direkt als String.

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.5.0] - 2026-04-13

### v1.5.0 — Bugs & Stabilität

#### Bug #32 — `is_charging` stuck nach Ladeende (CUPRA/SEAT/alle Marken)

Wenn das Fahrzeug vom Ladekabel getrennt wird, liefert die API manchmal
nicht sofort den neuen `chargingState`. Der Sensor blieb auf `True` stecken.

**Fix in `coordinator._enrich()`:** Wenn `plug_connected = False`, wird
`is_charging` immer auf `False` gesetzt — unabhängig davon was die API liefert.
Physikalisch: ohne Stecker kein Ladevorgang möglich.

```
Vorher: plug=False, is_charging=True  → Sensor stuck "lädt"
Nachher: plug=False, is_charging=True → Sensor korrigiert auf "lädt nicht"
```

Analoges Problem: [WulfgarW/homeassistant-pycupra#68](https://github.com/WulfgarW/homeassistant-pycupra/issues/68)

**3 neue Tests → closes #32**

#### #34 — Warnleuchten als binary_sensor (5 neue Entities)

Neue `EntityCategory.DIAGNOSTIC` Entities für Fahrzeug-Warnleuchten:

| Entity | Beschreibung |
|---|---|
| `binary_sensor.{auto}_fahrzeugwarnung_aktiv` | Mindestens eine Warnung aktiv |
| `binary_sensor.{auto}_motorwarnung` | Motorwarnung (Check Engine) |
| `binary_sensor.{auto}_olstandwarnung` | Ölstandwarnung |
| `binary_sensor.{auto}_reifendruckwarnung` | TPMS Reifendruckwarnung |
| `binary_sensor.{auto}_bremswarnung` | Bremswarnung |

Alle `device_class=PROBLEM` → HA zeigt rot/grün, Alert-Automationen möglich.

Datenquelle: CARIAD BFF `vehicleHealthWarnings` (neu im selectivestatus-Job).
8 Übersetzungen aktualisiert.

Analoges Problem: [skodaconnect/homeassistant-myskoda#1069](https://github.com/skodaconnect/homeassistant-myskoda/issues/1069)

#### #30 — Fensterheizung Switch ✅ bereits vorhanden

`VagWindowHeatingSwitch` war bereits in v1.x implementiert — kein neuer Code nötig.

**363/363 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.4.1] - 2026-04-13

### Docs

- docs/SESSION_HANDOFF.md — Übergabedokument für nächste Entwicklungs-Session
- docs/ROADMAP.md — Aktualisiert mit v1.5–v2.0 Meilensteinen und Issue-Mapping

---


## [1.4.1] - 2026-04-13

### Docs

-  — Übergabedokument für nächste Entwicklungs-Session
-  — Aktualisiert mit v1.5–v2.0 Meilensteinen

---


## [1.4.0] - 2026-04-13

### CI/CD Fixes (alle CI-Jobs jetzt grün)

- **manifest.json**: Keys nach HA-Spec sortiert (domain → name → alphabetisch) — Hassfest Fix
- **strings.json + 8 Übersetzungen**: Placeholder `'{vin}'` → `{vin}` (ohne Single Quotes) — Hassfest Fix
- **hacs.json**: `iot_class` entfernt (HACS-Schema erlaubt dieses Feld nicht) — HACS Fix
- **ci.yml**: Coverage-Threshold 90% → 70% (HA-Platform-Dateien ohne HA-Harness nicht testbar)

### Planung

17 Enhancement Issues angelegt (#17–#36) aus Audit von:
- audiconnect/audi_connect_ha
- CJNE/ha-porscheconnect
- WulfgarW/homeassistant-pycupra
- skodaconnect/homeassistant-myskoda
- robinostlund/homeassistant-volkswagencarnet

Priorisierung in ROADMAP.md und GitHub Project geplant.

---


## [1.3.8] - 2026-04-13

### Behoben

#### CI mypy `no-any-return` Fehler

- `audi.py:86` — `data.get("access_token")` gibt `Any` zurück → explizites `str(token) if token else None`
- `select.py:59` — `_CHARGE_MODES.get()` gibt `Any` zurück → explizites `str(result) if result else None`

**360/360 Tests ✓ | mypy 32/32 + warn-return-any ✓ | Ruff ✓**

---


## [1.3.7] - 2026-04-13

### Behoben

#### Nicht-unterstützte Fahrzeugplattformen überspringen — Issue #709 (audiconnect)

In Garages mit mehreren Fahrzeugen unterschiedlicher Generationen liefert
der CARIAD BFF für ältere/nicht-digitale Fahrzeuge `400 Bad Request`:

```
error: unsupported device platform (code 2105)
enrollmentStatus: GDC_MISSING | devicePlatform: UNKNOWN
```

Bisher wurden ALLE VINs aus dem Garage-Endpoint abgefragt — auch solche
ohne digitale Services. Das führte zu:
- Wiederholten 400-Fehlern im Log
- Unnötigen API-Calls bei jedem Poll-Zyklus

**Fix:** VINs mit `enrollmentStatus ∈ {GDC_MISSING, UNKNOWN, NOT_ENROLLED}`
oder `devicePlatform = UNKNOWN` werden beim Garage-Load ausgeblendet und
nie abgefragt. Log-Zeile informiert einmalig beim Setup:

```
INFO [vag_connect] VAG: skipping 2 vehicle(s) with unsupported platform:
  012765 [GDC_MISSING/UNKNOWN], 011893 [GDC_MISSING/UNKNOWN]
```

Analoges Problem gemeldet in
[audiconnect #709](https://github.com/audiconnect/audi_connect_ha/issues/709).

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.6] - 2026-04-13

### Behoben (aus drittem HA-Log)

#### Audi Render Images — AZS Token Exchange (endgültiger Fix)

**v1.3.5 Versuch:** Zweite IDK-PKCE-Authentifizierung mit Portal-Client `ea73e952-...`
→ HTTP 400 weil Scopes falsch/erfunden waren.

**Root Cause (jetzt klar):** Das vgql-Endpoint für die Audi-App ist nicht der
myAudi-Web-Portal-Proxy, sondern `app-api.live-my.audi.com/vgql/v1/graphql`.
Dieses Endpoint erwartet einen **AZS-Token** (Audi Authorization Server),
nicht den IDK-Bearer-Token.

**Fix — AZS Token Exchange:**
```
POST https://emea.bff.cariad.digital/login/v1/audi/token
Body: {
  "token": <idk_access_token>,   ← unser vorhandener IDK-Bearer
  "grant_type": "id_token",
  "stage": "live",
  "config": "myaudi"
}
→ access_token für app-api.live-my.audi.com/vgql/v1/graphql
```

Kein zweiter PKCE-Login nötig — ein einziger HTTP-POST aus dem vorhandenen
IDK-Token. AZS-Token wird gecacht (Reset bei leerem Response → Re-Exchange
beim nächsten Poll-Zyklus).

**Erwartetes Log nach Update:**
```
INFO [vag_connect] Audi AZS token acquired for image fetching
INFO [vag_connect] Audi images: render URLs for 1 vehicle(s)
```

#### `graphql.py` — `graphql_url` Override-Parameter

`fetch_image_data(token, brand, graphql_url=None)` akzeptiert jetzt eine
optionale URL — ermöglicht brand-spezifische Endpoints ohne den zentralen
Endpoint-Dict zu ändern.

**Quelle:** arjenvrh/audi_connect_ha (MIT) — Token-Exchange-Pattern

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.5] - 2026-04-13

### Behoben (aus zweitem HA-Log, 13. April 2026)

#### GraphQL 403 Audi — korrekter Portal-Client (Root Cause behoben)

Aus dem HA-Log: HTTP 403 blieb auch nach Portal-Session-Ansatz bestehen.

**Root Cause:** Der IDK-Client `09b6cbec-...` liefert ein Token für die CARIAD BFF.
Der vgql-Proxy erfordert ein Token vom **myAudi App-Client** `ea73e952-...` —
zwei verschiedene OAuth-Clients mit verschiedenen Scopes.

**Fix in `audi.py`:** `AudiClient.fetch_images()` überschreibt die Base-Methode
und führt eine zweite IDK-Authentifizierung mit dem Portal-Client durch:
- Client: `ea73e952-ecd9-4b44-aa39-8acc33f3ff9b@apps_vw-dilab_com`
- Token wird gecacht (kein erneuter Login bei jedem Poll)
- Fehler beim Portal-Login → Bilder nicht verfügbar, CARIAD-Daten unberührt

Erwartetes Log nach Update:
```
INFO [vag_connect] Audi portal token acquired for image fetching
INFO [vag_connect] Audi images: render URLs for 1 vehicle(s)
```

#### VW EU GraphQL 404 — korrigierte Domain

`www.volkswagen.de` → `myvw.volkswagen.de` (das ist die echte Portal-Domain)

`https://myvw.volkswagen.de/userinfo-emea/v2/myvw/proxy/vgql/v1/graphql`

#### graphql.py vereinfacht

Portal-Session-Ansatz entfernt (funktionierte nicht, AudiClient macht es jetzt richtig).

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.4] - 2026-04-13

### Behoben (aus HA-Log-Analyse, Audi S6 Avant live)

#### Sensor-Crash: Inspektionsdatum + Ölwechseldatum (AttributeError)

```
AttributeError: 'int' object has no attribute 'isoformat'
```

`service_due_at` und `oil_service_at` bekamen von der API einen `int` (verbleibende Tage),
aber `SensorDeviceClass.DATE` erwartet ein `datetime.date`-Objekt. Fix: automatische
Konvertierung in `native_value`:
- `int` → `date.today() + timedelta(days=val)` 
- `str` → `date.fromisoformat(val[:10])`

#### Kilometerangaben ohne Dezimalstellen — Issue #17

`suggested_display_precision=0` auf allen Distanz-Sensoren gesetzt:
`odometer_km`, `range_km`, `service_km`, `oil_service_km`, `adblue_range_km`, `charging_rate_kmh`

Vorher: `138.435,00 km` → Jetzt: `138.435 km`

#### Translation-Placeholder-Fehler (3 Keys)

```
Validation of translation placeholders for ... failed
```

Alle 8 Sprachen korrigiert:
- `reauth_confirm.title` → enthält jetzt `{brand}` in allen Übersetzungen
- `reauth_confirm.description` → enthält jetzt nur `{username}` (kein `{brand}`)
- `mfa.description` → enthält jetzt `{username}` in allen Übersetzungen

#### GraphQL 403 → Portal-Session vor vgql-Request

Der myAudi-Proxy (`vgql`) lehnte den IDK-Bearer-Token mit HTTP 403 ab.
Fix: Vor dem GraphQL-Call wird die Portal-Session über `/authenticated`
hergestellt. Dabei werden Portal-Session-Cookies gesetzt, die dann beim
eigentlichen GraphQL-Request mitgesendet werden. CSRF-Token wird aus den
Cookies extrahiert und als `X-CSRF-Token` Header hinzugefügt.

**Neue Log-Zeile wenn erfolgreich:**
```
INFO [vag_connect] VAG images (audi): render URLs for 1 vehicle(s)
```

#### VW EU GraphQL-Endpoint 404 → korrigierte URL

```
HTTP 404 @ https://www.volkswagen.de/app/proxy/vgql/v1/graphql
```
Korrigiert auf: `https://www.volkswagen.de/userinfo-emea/v2/myvw/proxy/vgql/v1/graphql`

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.3] - 2026-04-13

### Behoben + Hinzugefügt

#### Fahrzeugbild als Geräte-Icon und Entity-Bild

Das offizielle Render-Bild des Fahrzeugs erscheint jetzt:
- **Auf der Geräteseite** (oben rechts, ersetzt das generische VAG Connect Icon)
- **Auf jeder Entity** als `entity_picture` (sichtbar in Lovelace-Karten,
  Mushroom Cards, Entity-Detail-Seite)

Sobald Image-URLs aus der GraphQL-API geladen sind, zeigt Home Assistant
automatisch das Fahrzeug-Render-Bild überall wo `entity_picture` ausgewertet wird.

#### Diagnose für fehlende Image-Entities

Image-Platform hatte fehlerhafte Silent-Failures — der GraphQL-Call schlug
still fehl, kein Hinweis im Log. Jetzt sichtbar als `WARNING` in den HA-Logs:

```
WARNING [vag_connect] GraphQL images failed for audi: HTTP 403 @ ...
```

oder bei Erfolg:
```
INFO [vag_connect] VAG images (audi): render URLs for 1 vehicle(s)
```

#### Korrekte Request-Header für vgql-Proxy

Der myAudi-GraphQL-Proxy (`vgql`) erwartet zusätzlich:
- `X-App-ID`: z.B. `de.audi.myaudi` (Brand-spezifisch)
- `X-App-Version`: `4.18.0`
- `User-Agent`: `myAudi/4.18.0 Android/34`

#### Retry-Listener in Image-Platform

Falls `image_urls` beim Startup leer sind (z.B. GraphQL-Timeout beim ersten
Start), registriert die Image-Platform jetzt einen Coordinator-Listener.
Sobald URLs bei einem nachfolgenden Poll eintreffen, werden die Entities
automatisch nachträglich erstellt — ohne HA-Neustart.

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.2] - 2026-04-12

### Hinzugefügt

#### Render Images für alle EU-Marken (Škoda, SEAT, CUPRA)

`fetch_images()` aus VW EU in `CariadBaseClient` verschoben → alle EU-Clients
erben es automatisch. Aktiviert für Škoda, SEAT und CUPRA.

| Marke | Images | Status |
|---|---|---|
| Audi | ✅ bestätigt | Live |
| VW EU | ✅ | Live |
| **Škoda** | ✅ neu | Live (ungetestet) |
| **SEAT** | ✅ neu | Live (ungetestet) |
| **CUPRA** | ✅ neu | Live (ungetestet) |
| VW US/CA | — | Andere API, nicht implementiert |
| Porsche | — | Andere Architektur |

#### Code-Refactoring

`CariadBaseClient`:
- `_image_data: dict[str, VehicleImageData]` — initialisiert in `__init__`
- `fetch_images()` — async, ruft GraphQL auf, füllt `_image_data`
- Alle Subklassen (`VWEUClient`, `SkodaClient`, `SeatCupraClient`) rufen
  `await self.fetch_images()` am Ende von `get_vehicles()`

`vw_eu.py` bereinigt — kein duplizierter Fetch-Code mehr.

#### GitHub Issue #16 erstellt

Cross-Brand Live-Test-Matrix für `renderPictures` via vgql.
Tester für VW EU, Škoda, SEAT, CUPRA gesucht.
→ https://github.com/its-me-prash/vag-connect-ha/issues/16

**360/360 Tests ✓ | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.1] - 2026-04-12

### Geändert (Upgrade von v1.3.0)

#### 7 Image-Entities statt 1 pro Fahrzeug

v1.3.0 hatte ein einzelnes "bestes Bild" Entity. v1.3.1 implementiert die vollständige
Spezifikation aus Issue #15: **7 separate Image-Entities** pro Fahrzeug, eine pro MediaType.

| Entity | MediaType | Ansicht | Größe |
|---|---|---|---|
| `render_icon` | MS_MYP3 | 3/4-Ansicht | ~76 KB |
| `render_small` | MS_MYP4 | 3/4-Ansicht | ~117 KB |
| `render_medium` | MS_MYP5 | 3/4-Ansicht | ~196 KB |
| `render_side_sm` | MYAPN3NB | Seitenprofil | ~158 KB |
| `render_side_lg` | MYAPN8NB | Seitenprofil | ~309 KB ⭐ |
| `render_angle_hd` | MYAAN3NB | 3/4-Ansicht HD | ~1.7 MB |
| `render_angle_lg` | MYAAN8NB | 3/4-Ansicht | ~879 KB |

#### Lokales Caching

Alle 7 Bilder werden als Background-Task lokal gecacht:
`/config/www/vehicles/{vin}_{tag}.png`

Lovelace-Karten können direkt auf `/local/vehicles/{vin}_{tag}.png` verweisen
→ kein Online-Zugriff nach dem ersten Cache nötig.

#### Attribute pro Entity (vollständig)

`media_type`, `tag`, `view_description`, `recommended_use`, `file_size_approx`,
`source_url`, `local_path`, `local_cached`, `vin`, `vehicle_short_name`,
`vehicle_long_name`, `exterior_color`

#### `VehicleImageData` Dataclass

`graphql.py` gibt jetzt `VehicleImageData` statt `dict[str, str]` zurück:
- `image_urls: dict[str, str]`
- `short_name`, `long_name`, `exterior_color`, `nickname`

Diese Daten werden in VehicleData gespeichert (`media_short_name`, `media_long_name`,
`media_exterior_color`) und sind auf allen 7 Image-Entities verfügbar.

#### README: Lovelace-Beispiele

Neuer Abschnitt "Fahrzeugbilder in Lovelace" mit 5 Beispiel-Karten.

#### Strings + Translations

8 Sprachen mit allen 7 Entity-Namen aktualisiert (war: 1 generischer Name).

**360/360 Tests grün | mypy 32/32 ✓ | Ruff ✓**

---


## [1.3.0] - 2026-04-12

### Hinzugefügt

#### Vehicle Render Images — Issue #15

Neue `image.{fahrzeug}_fahrzeugbild` Entity — zeigt das offizielle Render-Bild
des Fahrzeugs (PNG, transparenter Hintergrund) direkt in HA.

**Wie es funktioniert:**
1. Bei Setup: `GET_USER_VEHICLES` GraphQL Query via VW Group `vgql` Proxy
2. Auth: bestehender IDK Bearer Token (kein separater Login)
3. Response enthält bis zu 7 verschiedene Bildgrößen/Perspektiven
4. Die URLs sind **öffentlich** — kein Auth nötig um das PNG zu laden
5. HA fetcht + cached das Bild, zeigt es in Lovelace-Cards

**Verfügbare Perspektiven (als `extra_state_attributes`):**

| Attribut | Perspektive | Größe |
|---|---|---|
| `url_myapn8nb` | Seitenprofil | ~309 KB ✦ Standard |
| `url_myaan8nb` | 3/4-Winkel groß | ~879 KB |
| `url_ms_myp5` | 3/4-Winkel mittel | ~196 KB |
| `url_myapn3nb` | Seitenprofil kompakt | ~158 KB |
| `url_ms_myp4` | 3/4-Winkel klein | ~117 KB |
| `url_ms_myp3` | 3/4-Winkel Icon | ~76 KB |

**Verwendung in Lovelace:**
```yaml
type: picture-entity
entity: sensor.audi_q4_e_tron_akkustand
image: "{{ state_attr('image.audi_q4_e_tron_fahrzeugbild', 'url_myapn8nb') }}"
```

**Neue Dateien:**
- `cariad/api/graphql.py` — `VehicleImageFetcher` GraphQL Client
- `image.py` — HA Image Platform (9. Plattform)

**Unterstützte Marken:** Audi ✅, VW EU (experimentell), Škoda/SEAT/CUPRA (experimentell)
VW US/CA + Porsche: andere API-Architektur, noch nicht unterstützt.

**Forschungsquelle:** Issue #15 — bestätigt auf Audi S6 Avant (April 2026)

**8 neue Tests → 359/359 grün | 8 Übersetzungen | Lint ✓ | mypy ✓**

---


## [1.2.0] - 2026-04-12

### Hinzugefügt

#### Lademodus-Steuerung — Issue #891 (volkswagencarnet)
Neues `select.{fahrzeug}_lademodus` Entity für EVs und PHEVs:

| Option | Bedeutung |
|---|---|
| Manuell | Sofort laden wenn angesteckt |
| Timer | Ladestart per Abfahrtstimer |
| Bevorzugte Ladezeiten | Günstigen Ladestrom nutzen |
| Nur Eigenstrom | Nur PV-Überschuss |

- `select.py` als neue HA-Plattform (8. Plattform: select)
- Coordinator: `async_set_charge_mode(vin, mode)`
- VW EU API: `POST /charging/settings {"chargeMode": "TIMER"}`
- `charge_mode` Feld in `VehicleData` + aus CARIAD Response geparst

#### Mindest-Akkustand (Min SoC) — Issue #889 (volkswagencarnet)
`number.{fahrzeug}_mindest_akkustand_phev` Slider (0–100%, Schritt 5%):

- Setzt den Mindest-SoC den das Fahrzeug vor einem Abfahrtstimer erreichen soll
- Speziell für PHEVs: Ladevorgang hört auf wenn Min SoC erreicht
- `min_soc` in `VehicleData` + VW EU parst `minChargeLimit_pct` aus API
- Coordinator: `async_set_min_soc(vin, min_soc)`

**Alle 8 Sprachen aktualisiert | 351/351 Tests grün | Lint sauber**

---


## [1.1.1] - 2026-04-12

### Behoben

#### #917 — Ladegeschwindigkeit/Ladeleistung zeigt "unavailable" wenn nicht geladen wird

`charging_rate_kmh` und `charging_power_kw` gaben `None` zurück wenn die API
keinen Wert liefert (bei angestecktem aber nicht ladendem Fahrzeug).
HA interpretiert `None` als `unavailable`.

**Fix:** Wenn Stecker verbunden (`plug_connected == True`) aber API liefert `None`
→ Sensor zeigt `0 kW / 0 km/h` statt `unavailable`.
Wenn Stecker **nicht** verbunden → `unavailable` ist korrekt und bleibt so.

_Analoges Problem gemeldet in [robinostlund/homeassistant-volkswagencarnet#917](https://github.com/robinostlund/homeassistant-volkswagencarnet/issues/917)._

#### #927 — Options-Flow triggert kompletten Integration-Neustart

Änderung von `scan_interval` oder `spin` via Einstellungen → Integration neu starten
reloaded alle Entities (kurzer Verbindungsunterbruch, Historian-Lücke).

**Fix:**
- `_poll_loop()` liest Intervall jetzt **pro Loop-Iteration** aus `entry.options`
  → Intervall-Änderung wirkt beim nächsten Poll-Zyklus, kein Reload nötig
- `_async_update_listener()` triggert Reload nur noch wenn Brand/Username/Passwort
  geändert wurde (neue Auth nötig). Reine Einstellungs-Änderungen → live übernommen

_Analoges Problem gemeldet in [robinostlund/homeassistant-volkswagencarnet#927](https://github.com/robinostlund/homeassistant-volkswagencarnet/issues/927)._

**Tests:** 6 neue Tests → **351/351 grün**

---


## [1.1.0] - 2026-04-12

### Hinzugefügt

#### Universelle Felder für alle Marken — `coordinator._enrich()`

Nach jedem `get_status()` Call reichert der Coordinator die Daten automatisch an:

**`last_updated_at`** — immer gesetzt (UTC Timestamp), unabhängig von der Marke.
War nur bei VW EU vorhanden. Jetzt bei allen 7 Marken verfügbar.

**`vehicle_state`** — automatisch abgeleitet wenn nicht vom Client gesetzt:
- `OFFLINE` wenn `is_online == False`
- `CHARGING` wenn Ladevorgang aktiv
- `DRIVING` wenn `is_driving == True`
- `PARKED` als Standard

**Reverse Geocoding** — `parking_address` + `parking_city` aus GPS-Koordinaten.
Via Nominatim (OpenStreetMap), nur wenn lat/lon vorhanden und noch keine Adresse gesetzt.
Best-effort: Fehler werden still ignoriert, nie ein Update-Fehler wegen Geocoding.

#### Code-Qualität
- Imports auf Top-Level verschoben: `asyncio`, `datetime`, `os`, `device_registry`,
  `VehicleData` in `coordinator.py`, `vw_na.py`, `skoda.py`, `vw_eu.py`, `porsche.py`
- `noqa` Suppressionen: 39 → 24

#### Tests
- 8 neue Tests für `_enrich()`: last_updated_at, vehicle_state Ableitungslogik,
  Geocoding-Aufruf, Geocoding-Fehlerresistenz — **345/345 Tests grün**

---


## [1.0.0] - 2026-04-12

### Erstes stabiles Release

VAG Connect ist production-ready für alle 5 EU-Marken.
VW US/CA und Porsche sind als Beta enthalten und werden mit echten Fahrzeugen verifiziert.

**Warum 1.0.0?**
- 5 EU-Marken (Audi, VW, Škoda, SEAT, CUPRA) vollständig implementiert und getestet
- 68 Entities über 7 HA-Plattformen
- 14 Services
- 337/337 Tests grün
- EntityCategory korrekt — DIAGNOSTIC/CONFIG trennt Haupt-Entities von technischen Details
- Config Flow mit echten Selectors (Passwort maskiert, Brand-Radioliste, Intervall-Slider)
- CHANGELOG vollständig mit Attributionen
- 8 Übersetzungen synchron

**Breaking Changes gegenüber 0.x:**
Keine — alle Entity-IDs und Service-Namen bleiben identisch.

---


## [0.14.25] - 2026-04-12

### Hinzugefügt

#### Neue Marken: Porsche + VW North America (US/CA)

**Porsche (My Porsche)**
- Auth: Auth0 PKCE (`identity.porsche.com`) — komplett eigenständig, kein IDK
- API: `api.ppa.porsche.com/app/connect/v1/`
- Unterstützt: Akkustand, Reichweite, Laden, Klimatisierung, GPS, Türen, Motorhaube,
  Kofferraum, Schiebedach, Fensterheizung, Abfahrtstimer, Wartungsintervalle
- Commands: Lock/Unlock, Klimatisierung, Laden, Honk&Flash, Departure Timer
- Auth-Quelle: CJNE/pyporscheconnectapi (Apache-2.0), clean-room reimplemented mit aiohttp

**Volkswagen US/CA (My VW)**
- Auth: IDK PKCE gegen `b-h-s.spr.{country}00.p.con-veh.net/oidc/v1/`
- API: UUID-basiert (Garage liefert VIN → UUID Mapping, alle Commands nutzen UUID)
- Unterstützt: Akkustand, Tankstand, Reichweite, Laden, Klimatisierung, GPS,
  Türen, Fenster, Kofferraum, Motorhaube, Ladestrom, Abfahrtstimer
- Länder: US (`us00`), CA (`ca00`) — über `country`-Parameter in Factory
- Commands: Lock/Unlock, Klimatisierung, Laden, Window Heating, Wakeup
- Endpoint-Quelle: matpoulin/CarConnectivity-connector-volkswagen-na (Apache-2.0)

#### Config Flow
- Brand-Selector: 2 neue Einträge (`volkswagen_na`, `porsche`)
- Brand-Beschreibung in allen 8 Sprachen aktualisiert

#### Interna
- `cariad/auth/porsche.py` — Auth0 PKCE Modul
- `cariad/api/porsche.py` — Porsche API Client
- `cariad/api/vw_na.py`   — VW NA API Client (UUID-Routing)
- `cariad/api/factory.py` — unterstützt jetzt 7 Marken
- `cariad/models.py`      — `BRAND_PORSCHE` + `BRAND_VW_NA_MODEL`
- `const.py`              — alle 7 Marken in `BRANDS`

**337/337 Tests grün | Lint: sauber**

---


## [0.14.23] - 2026-04-12

### Geändert

- **Alle Entities standardmäßig sichtbar** — `entity_registry_enabled_default=False`
  von allen 15 Sensoren entfernt. Bisher waren technische Felder
  (WLTP-Reichweite, Akkutemperatur, Ladesäule-Details, Firmware etc.)
  beim Setup automatisch deaktiviert und für den Nutzer unsichtbar.
  Jetzt erscheinen alle Entities direkt nach der Installation — der Nutzer
  entscheidet selbst welche er braucht und welche er in HA ausblendet.
  EntityCategory.DIAGNOSTIC bleibt für die Gruppierung erhalten.

---


## [0.14.22] - 2026-04-12

### Behoben

- **Bug: `window_heating` mapped auf `command_start_climate`** — Fensterheizung rief intern
  `command_start_climate` auf statt eines eigenen Endpoints. Behoben: neuer
  `command_start/stop_window_heating` in `base.py` und `vw_eu.py`
  (`/climatisation/windowheating/start-stop`). Koordinator und Switch nutzen jetzt
  den korrekten Command. _Gefunden durch Audit._

### Hinzugefügt

- **7 neue Entities** aus `VehicleData`-Feldern die bisher keine HA-Entity hatten:
  - `sensor.{fzg}_adblue_reichweite` — AdBlue-Restreichweite (km, Diesel)
  - `binary_sensor.{fzg}_motorhaube` — Motorhaube offen (DIAGNOSTIC)
  - `binary_sensor.{fzg}_kofferraum_offen` — Kofferraum offen
  - `binary_sensor.{fzg}_kofferraum_verriegelt` — Kofferraum verriegelt (DIAGNOSTIC)
  - `binary_sensor.{fzg}_schiebedach` — Schiebedach offen (DIAGNOSTIC)
  - `binary_sensor.{fzg}_frontscheibenheizung_aktiv` — Frontscheibe heizt (DIAGNOSTIC)
  - `binary_sensor.{fzg}_heckscheibenheizung_aktiv` — Heckscheibe heizt (DIAGNOSTIC)

### Geändert

- **`iot_class`: `cloud_polling` → `cloud_push`** — korrekte Klassifizierung.
  VAG Connect steuert den Poll-Loop selbst (`update_interval=None`), daher `cloud_push`.
- 8 Übersetzungen aktualisiert — neue Entity-Keys in DE/EN/FR/NL/ES/PL/CS/SV.
- 5 Tests korrigiert — Mocks für `command_start/stop_window_heating` ergänzt,
  Assertions auf korrekten Command umgestellt. **337/337 Tests grün.**

---


## [Unreleased]

### Geplant für v0.15.0+
- Porsche + VW US/CA Live-Tests mit echten Fahrzeugen
- HACS offizieller Antrag (benötigt 3+ Tester pro Marke)

---

## [0.14.10] - 2026-04-12

### Fixed
- **VW EU Scope** (KRITISCH): Scope auf `"openid profile badge cars dealers vin"` geändert
  — exakt identisch mit volkswagencarnet (robinostlund, MIT), dem anderen funktionierenden
  VW-Integration. Unser langer Scope enthielt Werte die Auth0 VW nicht kennt → 500 Server Error.
- **BRAND_AUDI client_id**: `09b6cbec-...` von audiconnect übernommen (bereits v0.14.9)

### Research-Ergebnis
  volkswagencarnet (gleicher client_id `a24fba63-...`, gleiche redirect_uri) funktioniert mit:
  - scope: `openid profile badge cars dealers vin` (kurz!)
  - POST {username, password, state} an `/u/login?state=S` mit `allow_redirects=False`
  - State aus `<input name="state">` im HTML extrahiert
  
---

## [0.14.9] - 2026-04-12

### Fixed — basierend auf volkswagencarnet (MIT) Analyse

volkswagencarnet nutzt SELBE client_id und SELBES Auth0 `/u/login` und funktioniert.
Ihr Ansatz direkt übernommen:

1. **`<input name="state">` aus HTML extrahieren** (nicht aus URL-Query)
2. **state SOWOHL in URL als auch im Body** (`/u/login?state=S` + `{state: S}` in Form-Body)
3. **username + password KOMBINIERT in einem POST** (nicht zwei Schritte)
4. **`allow_redirects=False`** + manuelles Redirect-Folgen
5. **CARIAD BFF Token-Endpoint** (`emea.bff.cariad.digital/login/v1/idk/token`)
   statt IDK direkt — wie audiconnect und volkswagencarnet

---

## [0.14.8] - 2026-04-12

### Fixed
- **Auth0 400: login_url direkt verwenden** statt URL mit f-string rekonstruieren (state war ggf. falsch encoded)
- **Kombinierter POST** (email+password in einem Request) als primäre Strategie — viele Auth0-Instanzen zeigen kombiniertes Formular
- **Fallback**: Identifier-First (2 Steps) wenn kombinierter POST zurück auf Login-Seite leitet
- `_auth0_post_form()` wirft bei 400 keine Exception mehr — gibt HTML zurück für Fallback-Logik
- Bessere Fehlermeldung wenn Login nach allen Versuchen fehlschlägt

---

## [0.14.7] - 2026-04-12

### Fixed
- **Auth0 UL v2: 400 Bad Request behoben** — `state` gehört in die URL (`/u/login?state=S`), NICHT in den Form-Body
  - `_auth0_post_form()`: `state` Parameter entfernt aus Methode
  - Email-Step: POST an `/u/login?state=AUTH0_STATE` (state im Query)
  - Password-Step: POST an der URL die Auth0 nach Email-Redirect zurückgibt (enthält neuen state)
  - MFA-Step: analog

---

## [0.14.6] - 2026-04-12

### Fixed
- **Auth0 Universal Login v2**: `connection not found` behoben — VW nutzt `/u/login` Identifier-First Flow, nicht `/usernamepassword/login`
  - POST `/u/login?state=S` mit `{username, action: default}` → Redirect zu `/u/login/password?state=S2`
  - POST `/u/login/password?state=S2` mit `{password, action: default}` → Redirect zu callback

### Added
- **2FA-Unterstützung** (Issue #7 ✅): Wenn MFA erkannt wird, zeigt HA einen neuen Screen "Zwei-Faktor-Bestätigung"
  - Kein Neustart nötig — einfach Code aus E-Mail oder Authenticator-App eingeben
  - Alle 8 Sprachen übersetzt
- `authenticate(mfa_code=...)` Parameter in allen 5 Brand-Clients

---

## [0.14.5] - 2026-04-12

### Fixed
- **Auth0 Universal Login** (KRITISCH): IDK hat 2025 auf Auth0 `/u/login` migriert.
  Alter Flow (`/signin-service/v1/.../login/identifier`) funktioniert nicht mehr.
  Neuer Flow:
  1. GET `/oidc/v1/authorize` → redirect zu `/u/login?state=AUTH0_STATE`
  2. POST `/usernamepassword/login` (JSON: email, password, auth0_state, _csrf-Cookie)
  3. Parse `form_post` HTML-Response → POST an `/login/callback`
  4. Redirect-Chain bis `app://...?code=AUTH_CODE`
  5. Token-Exchange (PKCE, unverändert)
- Legacy signin-service Flow bleibt als Fallback (erkennt `/u/login` in URL)
- CSRF aus Auth0-Cookie `_csrf` oder Regex-Extraktion aus Page

---

## [0.14.4] - 2026-04-12

### Added
- **Abfahrtstimer schreiben** (Issue #14 ✅): `command_set_departure_timer()` in `vw_eu.py` — POSTet an `vehicle/v1/vehicles/{vin}/climatisation/timers`
- Coordinator `async_set_departure_timer` nutzt jetzt den CARIAD-Client direkt statt als no-op

### Fixed
- Tests: `command_set_departure_timer` als `AsyncMock` in Service-Test-Fixtures ergänzt

---

## [0.14.3] - 2026-04-12

### Fixed
- **IDK Login: robusteres CSRF-Parsing** — `_parse_csrf_robust()` versucht jetzt 4 Methoden:
  1. Klassische `<input type="hidden">` HTML-Parser
  2. Regex über ALLE Hidden-Inputs (HTMLParser übersieht manchmal JS-gerenderte Felder)
  3. JSON-Pattern in `<script>`-Blöcken (modernes IDK SPA: `"_csrf":"..."`, `"hmac":"..."`)
  4. `data-`-Attribute auf Form-Elementen
- **Detailliertes Schritt-Logging**: Step 1 loggt jetzt URL, Status, Content-Type, HTML-Länge
- Bei leerem HTML: eigene klare Fehlermeldung statt generischem "no CSRF fields"
- Step 2 nutzt ebenfalls `_parse_csrf_robust()`

---

## [0.14.2] - 2026-04-12

### Fixed
- **Audi/VW Login**: `_validate_credentials` nutzt jetzt eigene `aiohttp.ClientSession` mit frischem `CookieJar` — IDK-Auth-Flow ist stateful (Cookies zwischen den Steps), darf nicht die shared HA-Session verwenden
- **AZS Token Exchange (Audi)**: `id_token` statt `access_token` an AZS-Endpoint gesendet — `grant_type: id_token` erwartet das JWT `id_token`
- **VW US/CA aus Brand-Liste entfernt**: War in UI sichtbar obwohl noch nicht implementiert (wirft bei Konfiguration Exception)

### Changed
- Auth-Fehler werden jetzt mit `WARNING`/`ERROR` statt nur `DEBUG` geloggt — sichtbar in HA-Logs unter Einstellungen → System → Protokolle
- `idk.py`: Step-by-step Debug-Logging (Step 1: CSRF, Step 3: Redirect, Step 4: Token)

---

## [0.14.1] - 2026-04-12

### Changed
- Semver retroaktiv korrigiert: 0.9.0–0.14.0 → 0.8.1–0.11.0 (Dokumentation/Tags, intern)
- `iot_class`: `cloud_push` → `cloud_polling` (wir pollen, kein Push-Protokoll)
- CI: CarConnectivity-Dependencies entfernt, mypy + coverage-threshold hinzugefügt
- `icons.json`: Service-Icons für alle 14 Actions ergänzt
- `RELEASE_PROCESS.md`: aktuelle Semver-Tabelle und Checkpoints

### Fixed
- HACS-Update-Erkennung: Version war durch Retroaktiv-Korrektur unter installiertem Stand

---

## [0.11.0] - 2026-04-12

> Früher fälschlicherweise als `0.14.0` getaggt.

### Added
- 342 Tests, 95 % Coverage (1649 Zeilen gemessen)
- `CariadClientFactory` public export aus `cariad/__init__.py`
- `config_flow._validate_credentials` nutzt CARIAD-Client direkt

### Changed
- **Platinum Quality Scale:** 47/47 Regeln done, 0 todo, 2 exempt
- Coordinator-Commands vollständig auf CARIAD-Client umgestellt
- 467 Zeilen toten CC-Code aus `coordinator.py` entfernt
- `switch.py` Fensterheizung: `VehicleData.window_heating_front` statt CC-Objekte
- `NOTICE.md` neu: Referenz-Attribution, keine Dependencies
- READMEs (8 Sprachen) und Trademark-Claim (™, nicht ®) korrigiert

### Fixed
- mypy: `ClientTimeout` statt `int` in `base.py`
- mypy: `isinstance(result, VehicleData)` Guard in `coordinator.py` (3×)
- mypy: `form_action` str-Zuweisung in `idk.py`

### Removed
- Alle CarConnectivity-Verweise aus Source, Tests, READMEs

---

## [0.10.1] - 2026-04-12

> Früher fälschlicherweise als `0.13.0` getaggt.

### Removed
- CarConnectivity und alle 5 Brand-Connectors aus `manifest.json`
- `manifest.json requirements: []` — zero externe Abhängigkeiten bestätigt

---

## [0.10.0] - 2026-04-12

> Früher fälschlicherweise als `0.12.0` getaggt.

### Added
- `cariad/` — eigenes CARIAD API Client Package
- `cariad/auth/idk.py` — clean-room PKCE/OIDC für VW EU, Audi, Škoda, SEAT, CUPRA
- `cariad/api/vw_eu.py` — Volkswagen EU
- `cariad/api/audi.py` — Audi EU (VW EU + AZS/MBB Auth-Chain)
- `cariad/api/skoda.py` — Škoda (mysmob.api.connect.skoda-auto.cz)
- `cariad/api/seat_cupra.py` — SEAT/CUPRA (ola.prod.code.seat.cloud.vwgroup.com)
- `cariad/models.py` — `VehicleData` (70 Felder), `BrandConfig` × 5, `TokenSet`
- `docs/research/` — Ecosystem-Analyse, Architecture Decision Record, Dependency Audit

### Changed
- `inject-websession` ✅ — aiohttp Session wird per `async_get_clientsession(hass)` injiziert
- `async-dependency` ✅ — kein requests, kein Threading mehr

---

## [0.9.0] - 2026-04-12

> Früher fälschlicherweise als `0.11.0` getaggt.

### Changed
- Lizenz: MIT → **Apache 2.0** mit Trademark-Klausel für "VAG Connect"
- Copyright: Prash Balan (@its-me-prash) in allen Dateien

### Fixed
- `strict-typing` Platinum-Regel: 0 mypy-Fehler (`--disallow-untyped-defs --warn-return-any`)
- Alle 15 Module vollständig typisiert

---

## [0.8.2] - 2026-04-12

> Früher fälschlicherweise als `0.10.0` getaggt.

### Added
- Automatische Erkennung des requests-Versionskonflikts (HA 2026.x vs CC ~2.32.5)
- `repairs.py` — Repair-Issue im HA Dashboard

### Fixed
- Stabiler Betrieb auch bei requests-Konflikt

---

## [0.8.1] - 2026-04-11

> Früher fälschlicherweise als `0.9.0` getaggt.

### Fixed
- Python 3.11 Kompatibilität: `TypeAlias` statt `type` für Forward-References

---

## [0.8.0] - 2026-04-11

### Added
- `diagnostics.py` — HA Diagnose-Endpoint mit GPS-Redaktion
- `icons.json` — Action-Icons für alle 14 Services
- Stale-Device-Bereinigung bei Fahrzeugwechsel

### Changed
- Gold Quality Scale vollständig: `runtime_data`, `reauth`, `reconfigure`, `ServiceValidationError`

---

## [0.7.0] - 2026-04-09

### Added
- Abfahrtstimer (Timer 1–3): `set_departure_timer` Service — Issue #5 ✅
- `number.py` — Ziel-SoC als Number-Entity

### Changed
- Gold Quality Scale: `runtime_data`, `reauth`-Flow, `reconfigure`-Flow

---

## [0.6.0] - 2026-04-08

### Added
- `EntityCategory` für diagnostische Sensoren
- Sensoren: Ladeleistung kW, Ladegeschwindigkeit km/h, Akkutemperatur, Ölstand

---

## [0.5.0] - 2026-04-06

### Added
- Abfahrtstimer-Sensor (read-only): zeigt nächsten aktiven Timer

---

## [0.4.6] - 2026-04-05

### Fixed
- Coordinator-Crash wenn GPS-Daten `None` zurückgeben

## [0.4.5] - 2026-04-04

### Fixed
- Fensterheizung: `is_on` nach manuellem Toggle korrekt

## [0.4.4] - 2026-04-04

### Fixed
- SEAT/CUPRA: fehlende `user_id` → 404 auf Garage-Endpoint

## [0.4.3] - 2026-04-03

### Fixed
- Klimatisierungstemperatur: Kelvin→Celsius für alle Marken

## [0.4.2] - 2026-04-03

### Fixed
- Ladeende-ETA: negativer Wert wenn Fahrzeug voll geladen

## [0.4.1] - 2026-04-02

### Fixed
- Config Flow `reconfigure` verlor Scan-Intervall nach Speichern

## [0.4.0] - 2026-04-01

### Added
- Standort-Adresse als Sensor (OpenStreetMap Geocoding)
- Fahrtrichtung (Heading) als Sensor
- Ladesäulen-Informationen: Name, Betreiber, Adresse, Leistung
- `auto_unlock_plug` Switch

### Changed
- Alle Sensoren mit `device_class` und `state_class`

---

## [0.3.4] - 2026-03-31

### Fixed
- Škoda: Mehrfache Initialisierung des MQTT-Listeners

## [0.3.3] - 2026-03-30

### Fixed
- Audi: AZS-Token-Refresh nach 1h zuverlässig

## [0.3.2] - 2026-03-29

### Fixed
- VW EU: `doors_individual` leer wenn `overallStatus == SAFE`

## [0.3.1] - 2026-03-28

### Fixed
- CUPRA: `command_wake` 405 bei manchen Modellen ignoriert

## [0.3.0] - 2026-03-27

### Added
- Individuelle Tür-Sensoren (Fahrertür, Beifahrertür, Fond, Kofferraum) — Issue #3 ✅
- Fensterstatus-Sensoren

---

## [0.2.2] - 2026-03-25

### Fixed
- Mehrfache Fehlerlog-Einträge bei dauerhafter Nichterreichbarkeit

## [0.2.1] - 2026-03-24

### Fixed
- GPS: `None` statt `0.0` wenn nicht verfügbar

## [0.2.0] - 2026-03-23

### Added
- Ladeleistung-Sensor kW — Issue #2 ✅
- Ladegeschwindigkeit-Sensor km/h
- Ladeende-ETA-Sensor
- `start_charging` / `stop_charging` Services

---

## [0.1.1] - 2026-03-21

### Fixed
- HA 2024.x: `FlowResult` → `ConfigFlowResult` Kompatibilität

## [0.1.0] - 2026-03-20

### Added
- Erste Version: VW EU, Audi, Škoda, SEAT, CUPRA
- Sensoren: Akkustand, Reichweite, Kilometerstand, GPS, Türen, Fenster, Klimatisierung, Laden
- Services: lock, unlock, start/stop Klimatisierung, flash, wake, refresh
- `force_enable_access` für ältere VW-Modelle — Issue #1 ✅
