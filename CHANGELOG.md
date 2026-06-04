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

## [Unreleased]

## [2.10.11] - 2026-06-04

### Fixed

- **Data Act portal SPA: 3 new state-extraction patterns + 2-source forensic dump** (#388 swebachus v2.10.10 trace). swebachus's v2.10.10 warning log showed the portal returns a pure-SPA shell as the password page: `password_html.contains '<input'=False, contains 'state'=True, contains '__STORE__'=False`. Three new extraction patterns target the actual shapes this means: (a) Auth0 native state signature `hKFo...` regex (state tokens always start with that msgpack 2-key map marker so they are catchable even when minified into a bare string literal); (b) escaped JSON `\"state\":\"...\"` for double-encoded inline payloads; (c) URL-encoded state inside the HTML body for `window.location = "...state=X..."` patterns. The warning log now also covers `landing_html` (not just `password_html`), prints the raw URL strings, and dumps the 110-char context window around any `"state"` substring so the next failing trace pinpoints exactly where the token lives or proves the page is purely JS-rendered post-bundle.

## [2.10.10] - 2026-06-04

### Fixed

- **SEAT / CUPRA static vehicle info from garage** (#392 heidle78 v2.10.8 follow-up diag). Pre-v2.10.10 the parser never read `model`, `model_year`, `manufacturer`, or `firmware_version` from the OLA garage response, so every SEAT / CUPRA vehicle showed "Unbekannt" / `None` for those device-card fields even when the data was clearly present in the API. Now extracts them in `get_vehicles` with defensive multi-variant lookup (`model`/`modelName`, `modelYear`/`year`, `brand`/`manufacturer`/`brandName`, `firmwareVersion`/`softwareVersion`, plus a `specifications` / `vehicleSpecification` sub-block) and caches per-VIN like the existing licensePlate + nickname pattern.

## [2.10.9] - 2026-06-04

### Fixed

- **Data Act portal SPA: attribute-order-agnostic state extraction + forensic logs** (#388 Arno-MA-73 v2.10.8 trace). v2.10.7's HTML hidden-input regex required `name` to appear before `value` in the markup; some Auth0 SPA bundles ship the attributes in the opposite order and the v2.10.7 regex silently missed those. Now walks every `<input ...>` tag, captures `name` and `value` as two independent regex matches the way `idk.py:_parse_csrf_robust` already does for the main BFF flow. Adds `data-state="..."` attribute as a third extraction path. Plus full DEBUG forensic logs at every step in the SPA branch (landing/identifier/password URLs, HTML lengths, parser field key sets, state extraction source and first 12 chars on success, first-200-char dump of password HTML when nothing works) so the next failing trace surfaces what shape the portal actually returns.

## [2.10.8] - 2026-06-03

### Fixed

- **CUPRA / SEAT PHEV classification** (#392 heidle78 Formentor diag). Some OLA firmware versions ship `engines.primary.fuelType="gasoline"` but DO NOT populate a combustion range in the `ranges` block on the same response. Pre-v2.10.8 the integration derived `has_combustion` purely from the ranges block, so a Formentor PHEV came out classified as `is_hybrid=False` and `has_combustion=False`, suppressing the fuel-tank / combustion-range sensors downstream. Now also treats any non-electric `primary_engine_type` (gasoline / diesel / cng) as combustion so the PHEV flag flips correctly regardless of which response branch carries the range data on a given poll.

## [2.10.7] - 2026-06-03

### Fixed

- **Data Act portal SPA: state token extraction from HTML** (#388 Arno-MA-73 post-restart trace). v2.10.6 fixed the 405 but then failed with "no Auth0 state parameter in URL" because aiohttp's redirect-following strips the state from the final response URL on some SPA flows. Now mirrors `idk.py`'s extraction order: HTML hidden input first (most reliable, Auth0 always embeds `<input type="hidden" name="state" value="...">` in the page body even on SPA), regex over hidden inputs as fallback, JSON-embed pattern as third option, then the URL query strings as last resort. Both `password_html` (most recent) and `landing_html` (original GET) get checked.

## [2.10.6] - 2026-06-03

### Fixed

- **Data Act portal SPA password POST 405** (#388 xeonixo + Arno-MA-73). v2.10.3 POSTed the SPA password to the parsed identifier-form action URL, which returned HTTP 405 Method Not Allowed for several users. Auth0 Universal Login actually routes the SPA password submission through the SAME `/u/login?state=<x>` URL as the identifier step; differentiation happens via the body's `action` field. Now mirrors `idk.py`'s SPA fallback exactly: form-encoded POST first, JSON-content-type fallback when that lands on 4xx or back on the IDP host, follow the redirect chain. State is pulled from the password-page URL with a fallback to the original landing URL.

## [2.10.5] - 2026-06-03

EU Data Act portal: no more manual click-through. When the integration is in read-only portal mode and you opt in via the new toggle, it kicks off the Custom Data Request on its own.

### Added

- **EU Data Act portal Custom Data Request auto-kickoff** (live-trace based). At startup in read-only `data_act_portal` mode, the coordinator checks each VIN for an existing 15-min Custom Request and creates one when none exists. Uses the verified `/proxy_api/euda-apim/` endpoints captured 2026-06-03: GET `metadata/partial` to detect, CSRF + POST `requests/partial` to kick off, GET `datadelivery/{Identifier}/list` to pick up the ZIPs. The portal accepts at most one active custom request per VIN at a time so the check-then-create order is critical; we adopt an existing request if one is already running instead of double-kicking. New toggle `eu_data_act_auto_kickoff` in OptionsFlow defaults to OFF because the kickoff implies a 1-month data subscription on the user's account at the portal.
- **Repairs issue on portal session expiry**. HTTP 401 on any portal API call now opens a guided `data_act_session_expired` Repairs issue pointing the user at the Reconfigure flow. Portal sessions are cookie-bound and not refreshable, so we surface the prompt instead of silently looping.

## [2.10.4] - 2026-06-03

Two power-user tools for keeping the auth chain alive when VW rotates client_ids.

### Added

- **APK watcher: auto-issue on new OAuth client_id**. The daily atlas builder already polled VW Group APKs and extracted client_ids; now there is a diff step that compares the latest extraction against everything wired into source. When a brand-new id appears, a labeled issue gets opened so the maintainer (or anyone) can promote it into the alternates list without waiting for someone to notice manually.
- **OAuth client_id override in OptionsFlow** (power-user). When the community spots a fresh client_id in a new APK before the daily watcher catches it, paste the full `UUID@apps_vw-dilab_com` into the new field and the resolver tries it first. All existing fallbacks stay in the chain. Empty / malformed values are silently ignored.

## [2.10.3] - 2026-06-03

VW EU users finally get a working read-only path again.

### Fixed

- **Data Act portal SPA password completion** (#388 caraar12345's trace). When the portal's password page is SPA-rendered, v2.10.2 detected it but bailed out telling the user the fallback in idk.py was the route - except that route is for the BFF client, not the portal client, so users on VW EU had nowhere to land. The Data Act portal flow now finishes the SPA-rendered password page itself with a form-encoded POST that includes `action=default` and the state lifted out of the page URL, then runs the standard token exchange. The portal client_id passes the Azure WAF where the main VW Android client_id is blocked, so this is the one path most affected VW EU users can actually use for read-only data.

## [2.10.2] - 2026-06-03

EU Data Act portal flow rebuilt against a verified live trace.

### Fixed

- **Data Act portal OAuth flow** (#388, #393). The portal client uses plain authorization-code flow with `prompt=login`, not the hybrid response_type we were sending. That mismatch was the source of the "unexpected landing URL - IDP may have rejected client_id" error several users hit when the live BFF strategies all failed and the integration tried the read-only fallback. Now switched to standard code flow plus PKCE-S256 plus a token exchange against `identity.vwgroup.io/oidc/v1/token`. Hybrid fragment delivery is kept as a defensive fallback so accounts that happened to work on the old path are not regressed.
- **Data Act portal state-string order**. Was `{country}__{language}__{BRAND}`, now `{language}__{country}__{BRAND}` per the live trace. DE/DE users worked by coincidence; non-matching country/language combinations were routed to the wrong portal locale.

### Added

- **EU Data Act portal usership-verification scaffolding**. New `check_verification_state()` and `submit_usership_verification()` on the scraper detect whether the one-time EU Data Act declaration is on file per VIN and can submit it on behalf of the user when an opt-in config flag is set. The Repairs / OptionsFlow wire-up lands in v2.10.3; the methods are usable from external code today.
- **Data request submission scaffolding**. New `submit_data_request()` and `poll_for_dataset_url()` for the async ZIP delivery flow. Endpoint shapes are best-effort against the documented form fields; verified shapes ship in v2.10.3 once a live trace captures the AJAX call that populates "Ihre Dateien".

## [2.10.1] - 2026-06-03

VW EU login hotfix. The v2.10.0 SPA fix unblocked one path, but several users still hit HTTP 403 on the authorize endpoint itself - the Azure WAF in front of `identity.vwgroup.io` started rejecting the Android user-agent some time on 2026-05-31. Same finding the wider HA-VAG community converged on this week.

### Fixed

- **VW EU 403 on authorize endpoint** (#388, #393). When the initial GET to `/oidc/v1/authorize` comes back 401 or 403, retry once with a plain mobile-browser user-agent. Picks up users blocked at the WAF without affecting accounts that already work on the Android UA.
- **VW user-agent bumped** to `Volkswagen/3.61.0-android/14` to match the current shipping APK. The old `3.51.1` string is what the WAF presumably flagged.

## [2.10.0] - 2026-06-02

The biggest single release so far. VW EU login is unblocked again after the 2026-05-31 backend change, parked cars no longer show all-Unknown, and SEAT/CUPRA gets its Energy-Dashboard story plus settable battery-care.

### Added

- **One service for every vehicle command**. Pick from a dropdown of 14 actions (lock, unlock, climate, charge, lights, window heating, wake, aux heating, ventilation) on any vehicle device. The individual services still work too, no automations break.
- **Wake your car before polling it** (opt-in). When the previous poll said the car was OFFLINE, send a wake first, then poll. Trades one extra API call for getting actual data back. Off by default.
- **See in-flight commands**. New pending-action sensors tell you when a lock/unlock/climate request the app sent is still being processed by the car, so automations can wait for real ack instead of guessing with sleeps. Closes #389.
- **Trip stats per tank or charge session**. 9 new sensors for distance, time, average speed, fuel and electric consumption, plus totals you can feed into the Energy Dashboard. Filled the long-standing gap in HA-VAG land.
- **Real warning-light data on SEAT/CUPRA** from a dedicated backend endpoint, with per-category booleans (engine, brakes, tyre, oil) plus a readable message list.
- **Set the battery-care preservation mode and target SoC** directly from HA on SEAT/CUPRA. Read-side was added in v2.8.1, this completes the write side.
- **Audi plug LED colour** wired up for Q6/A6 e-tron PPE. Older Audis keep the sensor hidden.
- **Real-time charging rate** on Audi + VW EU where the firmware reports it separately from the averaged rate.
- **Rich climate-start service** that lets you set per-seat heating, glass heating, eco-vs-comfort mode, continue-while-unlocked and target temperature in one call. Audi + VW EU only.
- **Charging history with power-curve points** for SEAT/CUPRA, so the DC-fast-charge kW-vs-SoC story finally works there. Diagnostic sensor exposes the curve in attributes, ready for Lovelace charts.
- **Group B: 7 more SEAT/CUPRA endpoints**. App notifications (count + last subject + severity), permissions (owner / can-command), engine + coolant temperature, charging profiles (same shape as Skoda already had), charging modes, a service to push charging settings to the car, and the public charging-station catalog now works on SEAT/CUPRA too.

#### VW EU field parity (Group A) — 10 new sensors

- HV battery min/max temperature (separate from the average) — useful for thermal-runaway alarms on long DC charges.
- Max AC charging current split into "what you set" vs "what the wallbox actually delivers".
- Born MY24+ AC connector auto-release flag + state.
- Optimised battery use toggle (longevity vs performance, distinct from battery-care).
- Active ventilation status + countdown to end.
- Rear sunroof + Cabrio roof-cover position.
- 12V battery health bucket (low / normal / high), distinct from the existing voltage sensor.
- Last-trip absolute fuel + electric consumption totals.

#### VW NA endpoint parity (Group C)

- Subscription + capabilities sensors on VW NA (Cox-backend). Pre-v2.10.0 SEAT/CUPRA + VW EU only.
- Modern Cox two-step SPIN flow for privileged actions. The old in-body SPIN still works as fallback.
- Modern lock/unlock endpoint, falls back to the legacy one on 404.
- NA-specific climate + window-heating endpoints, falls back to EU-style on 404.

### Fixed

- **VW NA "everything Unknown" on ID.4 US 2023** (#322 roberttco). Cox migrated the response shape; we now read both old and new shapes so accounts on either firmware get real values.
- **Scout stops shouting** about warning-light error envelopes and pending-action requests. Both are bff-internal wrappers, not real new data. Closes #389.
- **VW EU login broken after 2026-05-31** (#388 BalooDK + swebachus). VW migrated the password page to a JS-rendered shape and our form POST started getting "wrong credentials" even when they were right; the Data-Act fallback then mistook the SPA's `consent.js` asset for a real consent wall. Retry the same login URL with JSON content-type, and tightened the consent-wall detection so it doesn't trip on `consent.js`. VW EU users can log in again.
- **Tire pressure on newer PPC firmware**. Same data, new branch in the response; the parser now checks both branches.

### Documented

- Active-ventilation TODO from v2.4.x is cleared — Group A above shipped the parser and entities.
- Deeplink scheme TODOs are cleared. The smali extractions don't carry URI scheme strings (they live in AndroidManifest.xml + iOS Info.plist), so the shipped schemes stay sourced from each brand's launcher metadata.

## [2.9.0] - 2026-06-02

Hardening bundle: provenance canaries + weekly watcher, SPDX license headers across all Python files, and VW account-lock detection with a guided Repair issue.

### Added

- **VW account-lock detection**. After the 2026-05-31 ecosystem-wide VW Auth chaos surfaced a new failure mode (oliverrahner on volkswagencarnet#332 reporting his brand account getting locked for ~24h after too many failed token-refresh attempts), the coordinator now tracks HTTP 423 (Locked) and HTTP 403 with throttling-marker bodies on the token endpoint. Three such responses inside a 30-minute sliding window surface a Repair issue (`account_locked`) explaining the lock + next steps (wait, raise scan_interval, optionally switch to read-only Data Act portal mode). Auto-clears on the next successful auth. Native DE translation, EN parity for the other 7 supported languages.
- **Provenance canaries + weekly watcher**. New `custom_components/vag_connect/_canaries.py` declares 5 uniquely-spelled identifier strings, one per strategic module (auth resolver, Data Act scraper, DAG flow, Scout, watchdog). Each canary is also referenced from the module it watermarks so it travels with any port. Weekly cron in `.github/workflows/canary-watch.yml` queries GitHub Code Search for the canaries outside the `its-me-prash` namespace and opens a triage issue tagged `provenance` when a foreign hit appears. Apache 2.0 permits the port; the canaries make stripping the LICENSE + NOTICE observable.

### Changed

- **SPDX-License-Identifier headers** added to all 158 Python files. Files already carried the copyright + Apache 2.0 line; this adds the machine-readable SPDX identifier on the line below so REUSE / FOSSA / SCANCODE-class license scanners pick them up without parsing free-text. Mechanical change, no behaviour impact.

## [2.8.2] - 2026-06-02

### Fixed

- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when the `vehicleHealthWarnings.warningLights` job hits a 5xx upstream. Same shape as the v2.7.4 fix for `oilLevel.error` / `tyrePressure.error` / `auxiliaryHeating.error`, one branch deeper. Closes #384 (moltke69 Audi scout).

## [2.8.1] - 2026-06-01

Closes 11 SEAT/CUPRA OLA-field parser gaps surfaced via side-by-side comparison with the pycupra reference, after the v2.5.3 OLA v1/v5 fallback chain did not fix DanielBie's offline-Leon entity coverage (issue #306).

### Added

- 11 new sensors backed by OLA fields that the seat_cupra parser was not reading: `adblue_level_pct` (% tank level for diesel SCR, separate from the existing `adblue_range_km`), `cng_level_pct` + `cng_range_km` (CNG variants like Polo TGI, Mii Ecofuel, Leon TGI), `primary_engine_range_km` (PHEV / dual-fuel parity with the existing `secondary_engine_range_km`), `charging_preferred_mode` (user-selected mode mirror), `seat_heating` (any-seat-on aggregate), `parking_light`, `external_power` (charger is actually energising the cable, distinct from `plug_connected`), `battery_care` (preservation mode flag), `energy_flow` (any HV-battery exchange happening), `area_alarm` (geofence event). All entries phantom-protected via `_DATA_PRESENT_REQUIRED` so vehicles without the underlying field stay clean.
- Translations for the 11 new entities mirrored across all 9 supported languages (DE + EN canonical, the other 7 carry the EN labels until per-language polish; cross-lang parity test pinned).

## [2.8.0] - 2026-06-01

Stable cut of the v2.8.0 series. Promotes 2.8.0rc1 + 2.8.0rc2 from release-candidate to stable with no further code changes; the rc cycle ran under 24 hours and the only reported field issue (#378 from jwaeles) was fixed in rc2.

### What is new vs v2.7.4

- Five action items from the 2026-05-30 competitive scan: MFA / Email-OTP handler, coordinator auto-reload watchdog, headless EU Data Act portal zip scraper, FCM push live activation for Audi and VW, Repairs flow for DAG-to-hybrid_full degradation.
- Five v3.0 quick wins pulled forward: auxiliary-heating entities (switch + 2 numbers + sensors) for Audi and VW, `vag_connect.open_app` service with per-brand deeplinks, brake-service plus preferred-workshop sensors for all 4 Cariad brands, per-job parser-health telemetry in diagnostics, per-brand declared-vs-observed capability snapshot in diagnostics.
- 30-day device-bound IDP cookie persistence across HA restarts to skip the email-OTP challenge.
- Roadmap consolidation: five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md` with a new "Won't do" block listing 11 explicit exclusions.
- Dead-weight cleanup: Pydantic dual-write scaffold removed (blocking-IO warning gone), `euda.py` shim retired, 6 stale v1.x docs + 12 dead probe scripts deleted.
- README rewritten for all nine languages: DE + EN canonical, the other seven mechanically synchronised. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks.

### What changed during the rc cycle (rc2 hotfixes folded in)

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction). Reported in #378.
- Two-way auth recovery for VW EU and Audi hybrid_full. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved); when the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin.

## [2.8.0rc2] - 2026-06-01

Two-way VW EU re-auth recovery + hotfix for the 2026-05-31 IDP markup migration that broke the Data Act portal fallback. Same feature set as 2.8.0rc1 plus the two fixes below.

### Fixed

- VW EU re-auth after the 2h token expiry was crashing in the Data Act portal fallback because the IDP migrated the `hmac` and `_csrf` fields out of plain `<input type="hidden">` markup into a SPA-rendered JSON block. The portal-side form parser now mirrors the multi-fallback strategy already in `idk.py:_parse_csrf_robust` (HTMLParser, regex over hidden inputs, form-action regex, and JSON/script-block extraction), so a markup migration on either side fails loudly in the regression tests instead of in production. Reported in #378.

### Changed

- Two-way auth recovery for VW EU and Audi hybrid_full strategy. After the hybrid flow succeeds, the integration now opportunistically exchanges the auth_code that Auth0 also delivers in the callback URL for a token set that may include a real refresh_token. Strictly additive: when the standard token endpoint is still Play-Integrity-walled the exchange fails silently and the hybrid-only TokenSet is kept (v2.6.0 behaviour preserved). When the wall has been loosened (as observed across the ecosystem around 2026-05-31) the upgraded TokenSet replaces the hybrid one and the next 2h boundary refreshes against `/auth/v1/idk/oidc/token` instead of triggering a full relogin. Combined with the form-parser fix above this gives two independent recovery paths (refresh + full relogin via portal fallback) so a single endpoint flap on either side does not break re-auth.

## [2.8.0rc1] - 2026-05-31

First release candidate for v2.8.0. Bundles the five action items from the 2026-05-30 competitive scan with five v3.0 quick wins pulled forward, plus a dead-weight cleanup pass and a roadmap consolidation. README rewritten across all nine supported languages for v2.7.x reality (DAG MVP positioning + honest VW EU Play-Integrity limits).

### Action items

- MFA / Email-OTP config_flow handler (#1). The VW IDP can challenge for a 6-digit code on first sign-in; the flow now captures it cleanly instead of failing with a generic `cannot_connect`.
- Coordinator auto-reload watchdog (#2). When all VINs on the hybrid_full strategy show `failure_count >= 2` and `last_good_at` is older than 2x the scan interval, the coordinator silently re-authenticates without dropping entities. Mirrors the upstream community automation pattern but internalised so users do not have to wire it themselves.
- Headless EU Data Act portal zip scraper (#3). New `cariad/auth/_data_act_scraper.py` wired as Tier 3.5 (activates only when the active strategy is `data_act_portal`). Route A probes a research-confirmed JSON endpoint; Route B is fully scaffolded behind a new `CONF_ENABLE_DATA_ACT_BROWSER` OptionsFlow toggle that drives a headless Chromium via the optional `playwright` package (NOT in `manifest.json` — 100 MB Chromium download stays opt-in). Missing-dep surfaces a `data_act_browser_missing` Repair issue.
- FCM push channel for Audi and VW now ships live activation (#4). Decoded payloads (lockState, chargingState, climateState, alarm) are fired onto the HA event bus as `vag_connect_push_event` and trigger a coordinator refresh. The Cariad Firebase sender_id / api_key / app_id are still tester-gated behind a `NotImplementedError` in `_resolve_fcm_credentials` until the live APK extraction lands; the OptionsFlow toggle label moves from "EXPERIMENTAL" to "Live (beta)".
- Repairs flow when DAG degrades to hybrid_full (#5). New `auth_strategy_degraded` issue surfaces in the HA UI after 3 consecutive successful polls confirm the resolver has silently fallen back, with two guided remediations: re-run the browser-login setup, or pin the read-only Data Act portal mode (via the new `CONF_PREFERRED_AUTH_STRATEGY` option).
- MFA / 30-day device-bound IDP cookie persistence. The VW IDP issues a cookie after a successful email-OTP that suppresses the OTP for around 30 days; until now we discarded it on every restart, reload, and 2h re-login. `TokenSet`, `TokenStorage`, and `IDKAuth` all extended to round-trip the cookie. Latent bug-fix included: the storage layer never persisted `strategy` or `auth_cookies`, so the watchdog never saw the active strategy after a restart.

### Quick wins from the v3.0 roadmap (pulled forward)

- Standheizung / auxiliary-heating surface (quick win A): switch + duration number (5–60 min) + target-temp number (16–30 °C) + new `auxiliary_heating_status` + `aux_heating_active` + `auxiliary_heating_remaining_min` sensors. Audi + VW EU only; SEAT/CUPRA flow continues to require S-PIN. Capability map declares `auxiliaryHeating` for the two new brands.
- `vag_connect.open_app` service (quick win B). Fires `vag_connect_open_app` on the HA event bus with `{vin, brand, deeplink_url, action}` so a Lovelace card can open the brand's native mobile app on the calling device via `window.location.href`. Deeplink schemes are defined in `const.DEEPLINK_SCHEMES`; the per-brand scheme strings are marked `TODO(2.8.1)` for device-side re-verification once the v2.8.1 IPA/smali pass lands.
- Brake-service + preferred-workshop sensors (quick win C). Six new sensors: `brake_fluid_change_due_at`, `brake_pads_front_inspection_due_at`, `brake_pads_rear_inspection_due_at`, `preferred_workshop_name`, `preferred_workshop_address`, `preferred_workshop_phone`. Populated for VW EU + Audi (CARIAD-BFF `serviceCare`), Skoda mysmob `maintenanceReport`, and SEAT/CUPRA OLA `maintenance` when the dealer has wired up the service plan. Phantom-protected via `_DATA_PRESENT_REQUIRED`.
- Parser-health telemetry in diagnostics (quick win D). Each brand client's `parser_stats` dict records `{success, fail, last_error[:200]}` per named job (`oil_level`, `charging`, `climatisation`, `tyre_pressure`, `auxiliary_heating`, `trip_statistics`, `service_care`, etc.) and is exported in the diagnostics dump, so a silent parser regression on one job is visible while the rest of the poll succeeds. PII redaction reuses the existing JWT/VIN/email scrubber.
- Per-brand capability advertisement in diagnostics (quick win E). New `cariad/_capabilities.py` declares the expected per-brand capability matrix; `coordinator.capabilities_snapshot()` adds the observed-this-poll view and a `drift` list flagging declared-True-but-observed-False. Lets a missing entity be triaged as "brand never supported it" vs "parser dropped a field" without reading source code.

### Housekeeping

- Dead-weight cleanup pass. Removed the v2.2.0 Pydantic dual-write scaffold (one model, return value discarded everywhere, plus a blocking-IO warning on every fresh HA startup), retired the `euda.py` v2.0 shim that had zero callers, deleted 6 stale v1.x docs and 12 dead probe scripts from the v1.27 research era.
- Roadmap consolidation. Five overlapping roadmap docs reduced to one canonical top-level `ROADMAP.md`. New "Won't do" block records the 11 things we have explicitly ruled out (MBB direct-data path, Lamborghini/Bentley/Bugatti commands, VW China, etc.) so future feature requests can point at it.
- README rewritten for all nine languages. Drops the v2.0 Big-Bang highlights and adds honest "Where we lead" + "Where the limits are" blocks. DE + EN canonical, the other seven languages mechanically synchronised.

## [2.2.0-rc1] — 2026-05-16 — "Legen — wait for it — dary" (Release Candidate)


## [2.2.0] — 2026-05-17 — "Legen — wait for it — dary" (Final)


## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion

- Cross-Brand App Atlas
- OLA watcher gains upstream as 3rd consensus source
- App Atlas covers all 7 brands

## [2.7.4] - 2026-05-31

### Fixed
- Scout no longer auto-fires on the 6-key `.error.*` envelope the Cariad BFF returns when `oilLevel` / `tyrePressure` / `auxiliaryHeating` jobs hit a 5xx upstream. v2.7.1 silenced the parent path but the single-level `.*` wildcard did not cover the 4-component child paths. Closes #371 and #373.

## [2.7.3] - 2026-05-31

### Changed
- Data Act portal auth: when the password form is missing in the response, scan the returned HTML for EU Data Act consent signals (`data act`, `consent`, `einwilligung`, `zustimmung`, `shape the future`, `datenverarbeitung`) before falling back to the generic credentials-rejected message. Surfaces a clearer instruction for users who hit the consent wall on `myvolkswagen.*` (issue #372).

## [2.7.2] - 2026-05-31

### Security
- Coordinator setup-failure log no longer prints the raw exception message at ERROR level. An aiohttp `InvalidURL` raised on the OAuth callback path could surface the full redirect URL including `access_token`, `id_token`, and `code` JWTs, all of which base64-decode to the user's email and a working access token. Log type only at ERROR; message at DEBUG.

### Fixed
- Multi-strategy auth resolver in `base.py` now also catches non-`AuthenticationError` exceptions (e.g. `aiohttp.InvalidURL`), converts them to a clean `AuthenticationError`, and falls through to the next strategy. Prevents the raw URL from leaking up to the coordinator's catch-all.

## [2.7.1] - 2026-05-31

### Fixed
- Vehicle Data Scout no longer auto-fires on `oilLevel` / `tyrePressure` / `auxiliaryHeating` branches we just promoted in v2.7.0. Closes scout-report issues #366 and #367.

## [2.7.0] - 2026-05-31

### Added
- Browser-Login (OAuth Device Authorization Grant) for Audi, Škoda, SEAT, CUPRA. Open a QR code on your phone, sign in to your Brand ID account, confirm a short code. No password stored in Home Assistant, real refresh_token from the IDP.
- Trip statistics: `last_trip_*` and `lifetime_*` sensors populate from `/tripstatistics?type=shortTerm|longTerm`.
- `warning_messages` sensor surfaces every backend warning the manufacturer app would show (Audi STO / towing-bracket alerts etc), not just the hardcoded oil/engine/brake/tyre family.
- `oilLevel` and `tyrePressure` jobs added to the selectivestatus request. Populates `oil_level_warning` binary_sensor and the existing `tire_pressure_*_bar` sensors.

### Fixed
- Per-door, per-window, sun-roof, trunk-lock state now populate on locked cars (was only on unlocked).
- Outside temperature parser tries multiple backend key variants for Audi MY24+ compatibility.
- Window heating front/back parser tries multiple JSON shape variants.
- `wake_count_today` defaults to 0 instead of Unknown.
- TIMESTAMP sensors parse ISO 8601 strings to tz-aware datetime (cures entity-add failure on subscription_expiry_at).
- Cross-language translation parity. All 8 supported languages now ship the full config_flow translation set (browser_login, browser_login_approve, menu_options, progress, errors).

### Notes
- If field labels in the config dialog render as raw keys (`brand`, `spin`, etc) after upgrade, do a hard browser refresh (Ctrl+Shift+R). Home Assistant caches translations client-side and may not pick up the new keys until the browser cache clears.

## [2.7.0b11] - 2026-05-31

### Added
- Trip statistics endpoint wired. `last_trip_*` and `lifetime_*` sensors now populate from `/vehicle/v1/vehicles/{vin}/tripstatistics?type=shortTerm|longTerm`. Closes Unbekannt on Lifetime Distance, Last Trip Distance / Avg Speed / Avg Fuel Consumption, Lifetime Avg Fuel Consumption.
- `warning_messages` text sensor showing every backend warning as `type: text`, comma-joined. Surfaces brand-specific warnings the hardcoded oil/engine/brake/tyre binary sensors miss (e.g. Audi STO / towing-bracket alerts that come through in the myAudi email notifications).
- `wake_count_today` defaults to 0 on first data load instead of None / Unbekannt. The counter only increments when the user uses the wake button; users who never wake the car now see 0 instead of "Unknown".

### Fixed
- Outside temperature parser tries multiple backend key variants (`outsideTemperature_K`, `temperatureOutside_K` under `outsideTemperatureStatus` and `temperatureOutsideStatus`). Closes Unbekannt on Audi MY24+ models where the key differs from the canonical Cariad name.
- Window heating front / back parser tries multiple JSON shape variants (`windowHeatingStatus` / `statusList` / `windowHeatingStatusList` / direct array under value). Closes Unbekannt on brands shipping the data under a non-canonical key.

## [2.7.0b10] - 2026-05-31

### Added
- `oilLevel` job in the CARIAD-BFF selectivestatus request. New binary_sensor `oil_level_warning` (Oil Level / Ölstand). Closes "Oil Level" Unbekannt gap vs upstream.
- `tyrePressure` job in the same request. Populates the existing `tire_pressure_*_bar` sensors and `tire_pressure_warning` binary_sensor. Closes per-wheel pressure Unbekannt gap.
- `auxiliaryHeating` job for future Webasto / standheizung parity.

### Fixed
- Per-door and per-window state was only populated when the car was unlocked (`overallStatus == "UNSAFE"`). On a locked car the parser left `doors_individual` / `windows_individual` empty and all per-position entities (Left Front Door, Sun Roof, etc) rendered as Unbekannt. Now always iterate the doors and windows arrays regardless of overall status.
- Trunk lock state was never extracted from the access response. Pulled from the doors array entry with name "trunk", populating the existing `trunk_locked` binary_sensor.

## [2.7.0b9] - 2026-05-31

### Changed
- DAG browser-login Phase 2: URL and user_code now live inside the form schema as pre-filled fields, not just in the description. Description rendering kept failing on real installs (translation-loader miss or HA frontend quirk). Schema fields render reliably.
- Added a QR code selector showing the verification URL. Scan with phone camera to open the login page in one tap.
- Field labels chosen so the raw-key fallback ("verification_url", "user_code", "approved_in_browser") stays readable when translations miss.
- Persistent notification and WARNING log line from b8 kept as belt-and-suspenders.

## [2.7.0b8] - 2026-05-31

### Fixed
- DAG browser-login: URL and user_code now surface through three independent paths so at least one always renders even when the others fail. (1) form description (was already in b7), (2) persistent_notification fired on form first entry, (3) WARNING log line with both values. Defense against the empty-dialog-body symptom seen on b7 even after full HA restart.
- DAG browser-login form: switched from empty `vol.Schema({})` to a single optional confirm boolean. Empty schemas caused HA's frontend to skip description rendering on at least one install.

## [2.7.0b7] — 2026-05-31 — "DAG spinner-forever fix #3 — form-based URL display (beta)"

- After b4 and b6 both failed to reliably surface the verification URL + user_code in the show_progress dialog (HA frontend cached the progress description per flow id and didn't always pick up `description_placeholders` even when the show_progress task and step_id changed), Phase 2 is now rendered as a normal config_flow form. Forms substitute placeholders via the standard text-rendering pipeline which works reliably.
- New UX:
  - URL + 6-digit code shown as plain markdown text — fully visible and copyable
  - Submit button visible from the start
  - User opens URL in their browser (any device), signs in, approves
  - When done, clicks Submit
  - Background poll task validates with VW backend
  - If poll done + tokens → advance to entry creation
  - If poll done + error → drop back to brand picker (retry)
  - If user clicked Submit before approval was complete → re-renders form with a "still waiting for browser approval" hint
- Trade-off vs show_progress: lost auto-advance (user has to click Submit once they've approved), but gained guaranteed visibility of the URL + code. Worth it.
- Translation key added: `still_waiting_browser` (DE + EN).

## [2.7.0b6] — 2026-05-31 — "DAG spinner-forever fix #2 — split phases into distinct step_ids (beta)"

- Browser-login progress dialog now reliably shows the verification URL + user_code after the device_code is acquired. The b4 attempt at a single-step two-phase flow ran into HA's frontend caching the progress description per step_id — when the same step_id returned a second `show_progress` with a different `progress_action` and new `description_placeholders`, the dialog often kept showing the first (empty) description and the spinner appeared to spin forever.
- Refactored into two distinct step_ids:
  - `browser_login_pending` — Phase 1 only (request /device_authorization). Shows "Requesting login code…".
  - `browser_login_approve` — Phase 2 only (poll /token). Shows "Open {url}, enter {code}, sign in".
- HA tears down the first dialog cleanly between phases and renders a fresh one for Phase 2, so the placeholders apply correctly the first time.

## [2.7.0b5] — 2026-05-31 — "TIMESTAMP sensors fix (beta)"

- subscription_expiry_at (and any other ISO-string sensors with TIMESTAMP device class) now parse to timezone-aware datetime in native_value. Pre-fix HA rejected the entity at add-time with 'str has no attribute tzinfo'.

## [2.7.0b4] — 2026-05-31 — "Menu + DAG progress UX fix (beta)"

- Browser-Login / Email+Password menu now passes labels in the code instead of relying on the HA translation lookup — cures empty-chevron rendering when the integration is updated without an HA restart.
- Browser-Login progress: split into two phases so the URL + user_code populate in the progress text BEFORE the long poll begins. Previously the progress UI showed only "Waiting for browser approval…" with the URL/code never appearing.

## [2.7.0b3] — 2026-05-31 — "Hassfest + test contract fixes (beta)"

- Translations: moved progress key from inside step to top-level config.progress per HA schema.
- Tests aligned with v2.7.0b1 menu split and v2.7.0b2 5-header default.

## [2.7.0b2] — 2026-05-31 — "Audi token-headers fix (beta)"

- Audi email+password login: dropped the dummy x-assertion / x-platform / x-android-package-name trio from token requests — VW backend now rejects the dummy value and lets through requests that omit the headers entirely. Matches upstream v1.19.2+ behaviour.

## [2.7.0b1] — 2026-05-31 — "Browser-Login UI (beta)"

- New config_flow menu: choose between Browser-Login (recommended) and Email + Password (legacy).
- Browser-Login wires the v2.6.0 OAuth Device Authorization Grant module into HA's show_progress flow — open a URL, enter a short code, no password stored in HA.
- Available for Audi, Škoda, SEAT, CUPRA. VW EU + Porsche stay on the email + password path.

## [2.6.0] — 2026-05-31 — "Multi-Strategy Auth (Hybrid + DAG + Data Act)"

- VW EU now logs in via OIDC hybrid flow (response_type=code id_token token) — bypasses Play Integrity wall.
- OAuth Device Authorization Grant (RFC 8628) module for Audi/Skoda/SEAT/CUPRA — browser-based, password-less, refresh-token-friendly. UI wiring lands in v2.7.0.
- Per-brand strategy resolver with automatic fallback (up to 3 tiers per brand).
- In-house EU Data Act portal auth as last-resort read-only fallback strategy.

## [2.5.13] — 2026-05-30 — "Play Integrity Wall Decoded"

- Discovered: Play Integrity attestation

## [2.5.12] — 2026-05-30 — "Market-Config Activation + Atlas Pipeline Audit"

- `refresh_audi_market_config()` was never called in v2.5.11
- Atlas-builder APK extraction pipeline broken since 2026-05-25
- Strategic update on #336 (VW GIS Migration)

## [2.5.11] — 2026-05-30 — "Field-tested Auth Hardening"

- VW EU was silently impersonating the Audi app via the `x-android-package-name` token
- Audi market-config dynamic discovery
- evcc-derived alternate OAuth `client_id` for Audi

## [2.5.10] — 2026-05-29 — "VW NA Polish (roberttco bundle, 2 of 5)"

- #323 — "Last Update value does not reflect last time data was updated"
- #325 — "Controls become disabled after using them"
- #322 — "Sensors are unknown or incorrect"

## [2.5.9] — 2026-05-29 — "Scout-Policy T1 — Parse What We Silenced"

- NEW `binary_sensor.camping_mode`
- CUPRA `battery.chargeEnergyInKwh` → `sensor.total_charged_energy_kwh`

## [2.5.8] — 2026-05-29 — "Silencer Sweep (campingMode + CUPRA charging rename)"

- Silenced 11 scout-reports in one sweep
- Why a single silencer-sweep release

## [2.5.7] — 2026-05-29 — "502 Resilience + OIDC Discovery + qmauth Fallback Chain"

- Stop misdiagnosing VW server outages as credentials failures
- OIDC discovery for token URL
- qmauth fallback chain

## [2.5.6] — 2026-05-28 — "APK-Primary Auth-Config with OAuth Client-ID Fallback Chain"

- NEW
- New module: `cariad/auth/_auth_config_resolver.py`
- OAuth client_id fallback chain

## [2.5.5] — 2026-05-28 — "App Atlas Phase A.5: Auth-Config Shield"

- App Atlas APK extraction now mines auth-config secrets too
- New `auth_secrets` bucket
- Audi

## [2.5.4] — 2026-05-28 — "VW Azure WAF Migration Emergency Hotfix (#313)"

- Audi and Volkswagen EU login failed with HTTP 403
- The fix (ported from evcc PR #30277 + PR #30292, MIT-licensed, merged hours earlier on
- Cross-reference (independent confirmations of the same migration)

## [2.5.3] — 2026-05-28 — "OLA v1↔v5 Fallback Chain (#306 Mii/Tavascan/Leon FR-KL Fix)"

- SEAT + CUPRA users on older vehicle generations (SEAT Mii Electric, CUPRA Tavascan VZ,
- `doors_locked` vs `doors_open` contradiction resolved
- Offline vehicle?

## [2.5.2] — 2026-05-28 — "Scout Pipeline Expansion"

- Vehicle Data Scout coverage widened across all 7 brands
- What this means for you
- Public framing

## [2.5.1] — 2026-05-28 — "Consent Wall Auto-Skip Hotfix"

- Audi/VW/Škoda/SEAT/CUPRA login regression — consent wall now auto-skipped
- Better error message for "Login redirect missing after password submission"
- Affected users

## [2.5.0] — 2026-05-27 — "Have You Met Mii?" (PyCupra Parity Sprint Part 1)

- 4 new binary_sensors
- Hints toward v3.0 — "Suit Up: The Push Tech Edition" 🎩

## [2.4.2] — 2026-05-27 — "Retro-Silencer Sweep + ActiveVentilation Interim"

- VW EU + Audi
- Silenced by code (3)
- Already-fixed in v2.4.1 — reporters on stale versions (4)

## [2.4.1] — 2026-05-25 — "OLA Defense + VW NA Garage + Scout Policy"

- OLA authentication — defense-in-depth
- Scout Policy

## [2.4.0] — 2026-05-23 — "Marketing-Rename: VAG Connect → VW Group Connect (Community Tribute)"

- 🪪 Marketing-Rename: "VAG Connect" → "VW Group Connect"

## [2.3.0] — 2026-05-23 — "VW North America Login Fix + Audi Route-aware Charging"

- #269 (roberttco VW NA, 2026-05-21) — VW North America Login (US/CA) endlich funktional
- #264 (moltke69 Audi, 2026-05-19) — Route-aware Smart Charging Sensoren

## [2.2.3] — 2026-05-23 — "Easter Egg + Sprint A Quick-wins"

- 🥚 Easter-Egg Service `vag_connect.show_vag` (Community Tribute)
- #270 (roberttco VW NA, 2026-05-21) — Config-flow Brand-Selection
  bleibt nach
- Scout #268 + #271 (VW EU arvcer, 2026-05-21/22) —
  `charging.chargingStatus.requests`

## [2.2.2] — 2026-05-18 — "Silencer Catch-up + Laien-friendly Names + Diesel Dashboards"

- Scout #260 silencer-fix + cross-language entity-name laien-cleanup
- Bubble Card ready-made templates für VAG Connect (`docs/lovelace/bubble-card/`)
- Bubble Card diesel variant `02b-vehicle-popup-diesel.yaml` (Audi
  S6 TDI tailored)

## [2.2.1] — 2026-05-17 — Phase 8 "alles parsen statt silencen" + Cross-Brand Expansion (continued)

- Phase 8 PR #5 — `car_type` cross-brand derivation helper
- Phase 8 PR #4 — VW EU/Audi `primary_engine_fuel_level_pct` mirror
- Phase 8 PR #3 — Porsche electric/combustion range split

## [2.1.0] - 2026-05-15 ✨🌍 Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools / Post-Big-Bang Wins — Skoda Climate-Ready + HomeRegion + User-Tools

- Skoda Climate-Ready-At Sensor
- `scripts/verify_my_vin.py` — User-facing pre-flight diagnostic
- `docs/recipes/browser-mod.md` — Cookbook für browser_mod ↔ VAG Connect

## [2.0.1] - 2026-05-15 🚨🔒 Safety-Fix: `doors_locked` False-Negative Cross-Brand / Safety-Fix: `doors_locked` False-Negative Cross-Brand

- Critical Safety-Fix: `doors_locked` zeigte fälschlich "Unlocked" für tatsächlich
- CUPRA Born MY26 `charging.rateInKmph` Parser-Fallback (closes Scout #192)

## [2.0.0] - 2026-05-15 🎯🚀 Big-Bang Release — 19 PRs in einem Schlag / Big-Bang Release — 19 PRs in one shot

- `quality_scale: platinum`
- DeviceInfo `configuration_url` + `suggested_area="Garage"`
- System Health Panel

## [1.27.2] - 2026-05-11 ⚡🔌 Scout-Felder Power-Patch + Plug-Diagnose / Scout-Felder Power-Patch + Plug Diagnostics

- ✨ Neue Entities
- 🎯 Scout Issues Closed
- 📋 Scout-Pipeline-Policy

## [1.27.1] - 2026-05-11 🚨🔧 Hotfix: device_tracker GPS-Daten / Hotfix: device_tracker GPS data

- 🐛 Root cause
- 🔧 Fix
- ✅ Was jetzt funktioniert

## [1.27.0] - 2026-05-11 🔬📋 Pre-Cariad PHEV Research + Strategic Roadmap / Pre-Cariad PHEV Research + Strategic Roadmap

- `_private/research-archive/2026-05_pre-cariad-mbb-and-golf-7-gte-audit.md`
- `_private/research-archive/2026-05_strategic-roadmap-v1.27-to-v2.0.md`
- `ROADMAP.md`

## [1.26.2] - 2026-05-09 🚨🔧 Hotfix-2: Root cause `zip_release` revertet — HACS install path / Hotfix-2: Root cause `zip_release` reverted — HACS install path

- `hacs.json`
- 🔍 Root cause
- 🔄 Reverted

## [1.26.1] - 2026-05-09 🚨 Hotfix: Integration lädt nicht in v1.25.x / Hotfix: integration won't load in v1.25.x

- `manifest.json`
- `entity_base.py:device_info`
- 🔄 Reverted

## [1.26.0] - 2026-05-09 🎯 Welle-6 Feature Backlog (#173) — 7 neue Entitäten + Cross-Brand Parity / Welle-6 Feature Backlog (#173) — 7 new entities + Cross-Brand Parity

- `sensor.<vin>_secondary_engine_range_km`
- `sensor.<vin>_next_charging_timer_id`
- `sensor.<vin>_next_charging_timer_target_soc_reachable`

## [1.25.0] - 2026-05-09 🚀 Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank) / Sprint C — Cross-Brand Parity + UX/UI + MBB VSR Phase 2 (Golf 7 GTE Tank)

- Cross-brand parity wins
- `_normalize.py`
- Porsche HTTP hardening

## [1.24.2] - 2026-05-08 🧪 Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration / Test Foundation: Property-Tests + Porsche/VW NA Parity + safe_int/float Migration

- Echter Production-Bug gefunden + gefixt
- 🧪 Property-Tests via hypothesis / Property-Tests via hypothesis
- 🧪 Porsche + VW NA Parser Parity / Porsche + VW NA Parser Parity

## [1.24.1] - 2026-05-08 🛠️ v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening / v1.24.0 CI-Failure-Fix + Doc Hygiene + Quick-Win-Hardening

- Ruff `E741` Ambiguous variable name `l`
- 🐛 Bugfix / Bugfix
- 🔒 Security / Security

## [1.24.0] - 2026-05-08 🚗 Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle) / Cross-brand Image-Entity Wiring (CUPRA/SEAT silent bug + Skoda multi-angle)

- Post-Fix
- 🐛 Bugfix — CUPRA/SEAT Silent Bug (seit OLA-Support live) / Bugfix — CUPRA/SEAT Silent Bug
- 🚀 Neu — Skoda mysmob Multi-Angle Wire-In / New — Skoda mysmob Multi-Angle Wire-In

## [1.23.0] - 2026-05-07 🚀 Audi/VW Push Foundation (Cariad FCM channel) / Audi/VW Push Foundation (Cariad FCM channel)

- Neues Modul
- Neuer Config-Flow Toggle
- Bilingual translations

## [1.22.0] - 2026-05-07 🖼️ Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic) / Skoda Widget Render → Image Entity (Bundle 2 Phase B Pragmatic)

- Neue Image-Entity
- `VagSkodaWidgetImageEntity` Klasse
- `_cache_all_images` Erweiterung

## [1.21.0] - 2026-05-07 🔄 Audi/VW MBB Legacy-Path Migration Phase 1 / Audi/VW MBB Legacy-Path Migration Phase 1

- MBB für andere Commands
- SPIN secure-token flow
- Country-detection

## [1.20.3] - 2026-05-07 🚨 Cariad-wrapper-404 Detection + Switch Hasattr-Gate (Audi/VW user-report) / Cariad-wrapper-404 Detection + Switch Hasattr-Gate

- Audi App-Push "Fahrzeug derzeit nicht erreichbar"
- Wake/Climate/Charging 404
- Single info-log per command

## [1.20.2] - 2026-05-07 🧹 Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle / Skoda Parser Hardening + Phantom-Entity Fix + Code-Hygiene Bundle

- 3 Scaffolding-Module mit `# SCAFFOLDING — NOT WIRED` Header
- ROADMAP "Standalone enhancements" Cleanup
- ROADMAP "Last updated" Header

## [1.20.1] - 2026-05-07 🔓📚 BinarySensor LOCK-class fix (#131) + Doc refresh / BinarySensor LOCK-class fix (#131) + Doc refresh

- README.md "Was noch in Arbeit ist"
- FAQ.md
- #131

## [1.20.0] - 2026-05-06 🚗 Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment / Bundle 2 Phase A: Skoda Widget + Vehicle-Info + Equipment

- `GET /api/v2/widgets/vehicle-status/{vin}`
- `GET /api/v1/vehicle-information/{vin}`
- `GET /api/v1/vehicle-information/{vin}/equipment`

## [1.19.4] - 2026-05-06 🔧📊 Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue / Bundle 1: T&C Brand-Deeplinks + Quota Repair-Issue

- Quota auto-pause polling
- `is_fixable=True` mit handler
- Per-VIN quota tracking

## [1.19.3] - 2026-05-06 🛰️ Scout-Welle 6: 5 Reports, 19 truly new paths silenced / Scout Wave 6: 5 reports, 19 truly new paths silenced

- `charging` endpoint
- `air-conditioning` endpoint
- `readiness` endpoint

## [1.19.2] - 2026-05-05 🔐 Token-Persistence über HACS-Updates (#118 fix) / Token Persistence across HACS Updates (#118 fix)

- Neues Modul
- `CariadBaseClient` Erweiterungen
- Coordinator Wire-Up

## [1.19.1] - 2026-05-04 📊 Pycupra-style API Quota Sensor / Pycupra-style API Quota Sensor

- `base.py:_capture_rate_limit_headers(headers)`
- `models.py`
- `coordinator.py:_enrich`

## [1.19.0] - 2026-05-04 🚀 CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.) / CUPRA/SEAT FCM Push Foundation (#57 Phase 1 cont.)

- Neues Push-Module
- Neuer Config-Flow Toggle
- Bilingual Translations

## [1.18.0] - 2026-05-04 🚀 Skoda MQTT Push Foundation (#57 Phase 1) / Skoda MQTT Push Foundation (#57 Phase 1)

- Neues Push-Package
- Neuer Config-Flow Toggle
- Lazy-Import-Strategie

## [1.17.7] - 2026-05-04 🌡️🔧 Skoda outside_temperature + preferred_workshop attrs / Skoda outside_temperature + preferred_workshop attrs

- Kein neuer Sensor, kein neuer Translation-Key, kein neues HACS-Manifest-Field
- `extra_state_attributes` auf bestehendem `service_due_in_days` Sensor
- Kein neuer Sensor, kein neuer Entity-ID

## [1.17.6] - 2026-05-04 🌍 HomeRegion-Helper Scaffolding (evcc port) / HomeRegion Helper Scaffolding (evcc port)

- `custom_components/vag_connect/cariad/_home_region.py`
- `tests/bruno/cariad_bff/22_GET_homeRegion.bru`
- `tests/test_v1176_homeregion.py`

## [1.17.5] - 2026-05-04 🛰️ Scout-Welle 5: 4 Community-Reports an einem Tag + 4 Verification-Pings / Scout Wave 5: 4 community reports in one day + 4 verification pings

- #118 eismarkt
- #51 Audi RS e-tron GT 404
- #48 all-actions-fail

## [1.17.4] - 2026-05-03 🎯 Bruno-CI Stufe 2 COMPLETE — Full Strict Coverage / Bruno-CI Stufe 2 Complete (Skoda + CARIAD-BFF strict)

- Skoda: +17 neue .bru files
- CARIAD-BFF: +11 neue .bru files
- `{path_suffix}` placeholder expansion

## [1.17.3] - 2026-05-03 🤖🛡️📚 Bruno-CI Stufe 2 + Lovelace Cards + 3 Research Docs

- Drift-check: 35/35 match, 0 drift, strict mode AKTIV in CI
- flex-table-card
- vehicle-info-card

## [1.17.2] - 2026-05-03 🧹🤖 Stale-Cleanup + Bruno-CI Stufe 1 / Stale-Reference Cleanup + Bruno-CI Foundation

- `tests/bruno/seat_cupra/`
- `tests/bruno/{skoda,cariad_bff}/`
- `scripts/check_bruno_url_drift.py`

## [1.17.1] - 2026-05-02 🚙🌬️🔥 Bruno Quick-Wins Bundle / Bruno Quick-Wins (Window heating fix + Ventilation + Aux Heating + Battery Care + Navigation #36 + 2× A/B-fallback)

- `Timwun/Cupra-WeConnect-Bruno-Collection`
- `upstream/pycupra`
- 🐛 Bug-Fixes / Bug-Fixes

## [1.17.0] - 2026-05-02 🛡️📚 Operational Hardening Bundle / Operational Hardening (Quota-protective polling + FAQ + HACS Checklist + Year-rollover Tests + Deactivated Notification)

- `vag-ha-integration-research.md`
- 🔄 Geändert / Changed
- ✨ Neu / Added

## [1.16.1] - 2026-05-02 🐛 SEAT/CUPRA Climate Fix + #122 Scout-Paths / SEAT/CUPRA Climate 404 Fix + SEAT scout-path registration

- #53 Climate
- #53 Phase 3 Phantom-Button
- 🐛 Bug-Fixes / Bug-Fixes

## [1.16.0] - 2026-05-02 ⏰📍 Cross-Brand UX + Skoda Charging Profiles / Cross-Brand UX + Skoda Charging Profiles (HA time platform #26 + #25/#31 read-only via charging-profiles + OTA Probe planning)

- Neue `entity.time` Sektion
- Skoda Vehicle-Information Bundle
- Charging Profile Write-Side

## [1.15.0] - 2026-05-02 🛰️🔋 Skoda Modernization Bundle / Skoda Modernization (Charging History #35 + OTA + 8 cap-ids + capability tolerance + anonymize hardening)

- #75 Skoda Kodiaq Mk2 403
- #26 Klima-Timer / Departure-Timer datetime UI
- #25 Standort-spezifischer Ladeziel + #31 Ladeprofile pro Standort

## [1.14.0] - 2026-05-02 🚗 Audi Feature Pack Bundle / Audi Feature Pack (Trip Stats + Engine Start ICE + PPC Climate Body) + Skoda Scout-Pfade #116

- #35 Ladehistorie LTS
- #51 RS e-tron GT Facelift
- PPE Auto-Detection

## [1.13.0] - 2026-05-02 🛡️ Production Hardening Bundle / Production Hardening (Capability Phase 3 + Read-only Phase 2 + Diagnostics-Polish + Process)

- ✨ Neu / Added
- 🔄 Geändert / Changed
- 🌐 Übersetzungen / Translations

## [1.12.3] - 2026-05-01 🛰️ Scout-Pfade #111 + #113 + #114 / Scout paths bundled with wildcard strategy

- fuelStatus
- vehicleHealthInspection
- departureProfiles

## [1.12.2] - 2026-05-01 🌟🛰️ Erstes Community-Scout-Report (Skoda #107 von tritanium73) / First community Scout report

- 4 unexpected findings sind bereits durch v1
- 2 Error-Reporter Findings sind transiente 502 Bad Gateway → v1

## [1.12.1] - 2026-04-30 🛰️📚 Scout-Pfade #105/#106 + Gerhard's Born Fixture + FAQ #47 / Scout paths + Born fixture + Subscription FAQ

- Wildcards
- Komplett anonymisiert
- Zweck

## [1.12.0] - 2026-04-30 🔋💡⚡🧯🔒 5-in-1 Feature-Sprint / Five features in one MINOR

- 📋 Doc-only — User-Data Handling + `[Inference]` Marker

## [1.11.1] - 2026-04-30 🐛💨 Golf 7 GTE Fuel-Range Fix (#96) + Optimistic UI (3B-Part-3)

- 🔧 **Drivetrain-Detection** liest jetzt aus 4 Quellen (statt 2): zusätzlich measurements
- 🔧 **carType="hybrid" flag** explizit erkannt → setzt has_battery=True UND
- 🔧 **Total range fallback** aus measurements

## [1.11.0] - 2026-04-30 🔆🔧 Issue #91 Closure: Light-Status, Service-Days, Max-Charge-Current

- Lichter-Status war nirgends zugänglich
- Service-Tage konnte man nur als Datum sehen, nicht als "noch X Tage"
- Max-Ladestrom war als Field da aber kein Sensor

## [1.10.2] - 2026-04-30 🚗 CUPRA Born 2026 Firmware-Shapes (Gerhard's #53 Live-Test)

- 🔋 battery
- 🔒 status
- 🚪 status

## [1.10.1] - 2026-04-30 🛡️ Defensive Coding Phase 2 (Issue #58)

- Skoda Parser
- VW EU/Audi Parser
- SEAT/CUPRA Parser

## [1.10.0] - 2026-04-29 🔋⛽ PHEV-Range-Triple + Audi-Diesel-Range (Issue #94)

- 🔋 **electric_range_km** ("Elektrische Reichweite")
- ⛽ **combustion_range_km** ("Kraftstoff-Reichweite")
- 🛣️ **total_range_km** ("Gesamtreichweite")

## [1.9.1] - 2026-04-29 🔧 Audi/VW Lock + Wake Hotfix + Capability-Filter Phase 2

- Audi S6 (Diesel)
- VW Golf 7 GTE

## [1.9.0] - 2026-04-29 🔬 Vehicle Data Scout + Error Reporter

- 📚 Documentation refresh

## [1.8.12] - 2026-04-29 🌐 Multi-Brand Connection-State (MVP-Move)

- 🟢🟡⚫ **connection_state Sensor** funktioniert jetzt nicht nur für Škoda (v1
- 🏆 **Erste VAG-Integration mit centralisiertem Multi-Brand Connection-State

## [1.8.11] - 2026-04-29 🚙 Škoda Online/Standby/Offline + Live-API-Erkenntnisse

- 🟢🟡⚫ **Verbindungsstatus-Sensor**
- 🚪 **Schiebedach, Kofferraum, Motorhaube** funktionieren jetzt
- 🔒 **Bessere Türschloss-Erkennung** auf neueren Modellen (Kodiaq 2026+) durch

## [1.8.10] - 2026-04-29 🩹 Hotfix


## [1.8.9] - 2026-04-29 🚗 CUPRA Born Bug-Fix-Bündel

- 🚪 **Türen, Fenster, Kofferraum, Motorhaube, Schiebedach** werden jetzt
- 🚗 **"Auto fährt gerade"** funktioniert wieder
- ⚡ **Lade-Power und Restzeit** werden korrekt angezeigt

## [1.8.8] - 2026-04-29 🔓 Lock / Climate / Charging für Audi 2025+ und Passat B9

- 🔒 **Lock/Unlock** funktioniert auf neuen Audi-Modellen (war vorher 404)
- ❄️ **Klimatisierung Start/Stop** funktioniert auf neuen Modellen
- ⚡ **Laden Start/Stop** funktioniert auf neuen Modellen

## [1.8.7] - 2026-04-29 🛡️ Stabilität — kein "Unavailable"-Flackern mehr

- 🌐 **Wochenend-Backend-Probleme** werden jetzt ausgesessen
- 🔁 **Einzelne fehlgeschlagene Polls** lösen kein "Unavailable" mehr aus
- 🐢 **Gateway-Timeouts (504)** werden automatisch nochmal versucht statt zu

## [1.8.6] - 2026-04-29 📚 Docs-Truthfulness Hotfix

- 🏆 **Multi-Brand-Successor-Position:** README sagt jetzt klar dass VAG Connect
- 🏷️ **Dynamic CI-Badge:** Statt hardcoded Test-Counts (die schnell veraltet
- 📝 **Aktuelle Stand & ehrliche Limits Section** in allen 8 README-Sprachen

## [1.8.5] - 2026-04-27

- `CommandProfile` enum
- Coordinator helpers `get_command_profile(vin)` /
  `set_command_profile(vin, profile)`
- VWEUClient `_post_command(vin, suffix)` helper

## [1.8.4] - 2026-04-27

- SEAT/CUPRA `command_lock` and `command_unlock` now use the SecToken
  flow
- `coordinator.async_lock` now requires S-PIN for SEAT/CUPRA brands
- `SpinError`

## [1.8.3] - 2026-04-27

- `vehicle_supports_capability(vin, capability_id)`
- `button.py` reads from the helper
- No effect on Audi / VW EU / Škoda / Porsche / VW NA

## [1.8.2] - 2026-04-27

- `CommandFailureReason` enum + `classify_command_failure()` helper
- Three-state feature model
- Capabilities cache

## [1.8.1] - 2026-04-27

- VIN masking in logs and diagnostics
- Diagnostics now redact more PII fields by default
- Issue templates

## [1.8.0] - 2026-04-26

- Per-VIN availability
- S-PIN fail-fast
- Fake writable entities removed

## [1.7.0] - 2026-04-25

- Škoda: Complete API rewrite
- Car-friendly entity names
- Škoda parking v3

## [1.6.1] - 2026-04-25

- Škoda
- GraphQL
- Bootstrap

## [1.6.0] - 2026-04-24

- SEAT/CUPRA
- SEAT/CUPRA vehicle renders
- SEAT/CUPRA window heating

## [1.5.13] - 2026-04-24

- Škoda camelCase tokens

## [1.5.12] - 2026-04-23

- Entity translations
- Škoda token exchange
- SEAT token exchange

## [1.5.11] - 2026-04-23

- Brand-specific token endpoints
- Token refresh

## [1.5.10] - 2026-04-22

- CUPRA/SEAT user_id
- Lock platform
- Nightly polling reduction

## [1.5.9] - 2026-04-22

- CUPRA auth
- CUPRA/SEAT scope
- SEAT/CUPRA/Škoda token endpoint

## [1.5.8] - 2026-04-22

- SEAT/CUPRA/Škoda auth
- English entity labels
- CUPRA/SEAT OAuth scope

## [1.5.6] - 2026-04-18

- Sicherheits- und Performance-Audit
- Sicherheit
- Performance

## [1.5.5] - 2026-04-18

- Behoben — IDK Auth-Logs erschienen als "Fehler" in HA

## [1.5.4] - 2026-04-13

- Bereinigung — README, Issues, letzter toter Sensor
- `connection_state` Sensor entfernt
- README komplett neu geschrieben

## [1.5.3] - 2026-04-13

- Audi Images
- GDC Filter
- Behoben — Log-Auswertung

## [1.5.3] - 2026-04-13

- Behoben — Log-Rauschen
- AZS Token / Audi Images funktioniert ✅

## [1.5.2] - 2026-04-13

- Behoben — Kompletter Entity-Audit: API-Realität vs. Erwartungen
- Entfernte Dead Entities
- API-Wahrheit: Was CARIAD BFF wirklich liefert

## [1.5.2] - 2026-04-13

- Behoben — Binary Sensor Audit
- 5 tote Binary-Sensor-Entities entfernt

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Audit
- 11 tote Sensoren entfernt
- Abfahrtstimer-Sensoren repariert

## [1.5.1] - 2026-04-13

- Behoben — Sensor-Qualität
- 11 tote Sensoren entfernt
- Abfahrtstimer Zeitanzeige repariert

## [1.5.0] - 2026-04-13

- v1.5.0 — Bugs & Stabilität
- Bug #32 — `is_charging` stuck nach Ladeende
- #34 — Warnleuchten als binary_sensor

## [1.4.1] - 2026-04-13

- Docs

## [1.4.1] - 2026-04-13

- Docs

## [1.4.0] - 2026-04-13

- manifest.json
- strings.json + 8 Übersetzungen
- hacs.json

## [1.3.8] - 2026-04-13

- Behoben
- CI mypy `no-any-return` Fehler

## [1.3.7] - 2026-04-13

- Behoben
- Nicht-unterstützte Fahrzeugplattformen überspringen — Issue #709

## [1.3.6] - 2026-04-13

- Behoben
- Audi Render Images — AZS Token Exchange
- `graphql.py` — `graphql_url` Override-Parameter

## [1.3.5] - 2026-04-13

- Behoben
- GraphQL 403 Audi — korrekter Portal-Client
- VW EU GraphQL 404 — korrigierte Domain

## [1.3.4] - 2026-04-13

- Behoben
- Sensor-Crash: Inspektionsdatum + Ölwechseldatum
- Kilometerangaben ohne Dezimalstellen — Issue #17

## [1.3.3] - 2026-04-13

- Auf der Geräteseite
- Auf jeder Entity
- Behoben + Hinzugefügt

## [1.3.2] - 2026-04-12

- Hinzugefügt
- Render Images für alle EU-Marken
- Code-Refactoring

## [1.3.1] - 2026-04-12

- Geändert
- 7 Image-Entities statt 1 pro Fahrzeug
- Lokales Caching

## [1.3.0] - 2026-04-12

- Hinzugefügt
- Vehicle Render Images — Issue #15

## [1.2.0] - 2026-04-12

- Hinzugefügt
- Lademodus-Steuerung — Issue #891
- Mindest-Akkustand (Min SoC) — Issue #889

## [1.1.1] - 2026-04-12

- Behoben
- #917 — Ladegeschwindigkeit/Ladeleistung zeigt "unavailable" wenn nicht geladen wird
- #927 — Options-Flow triggert kompletten Integration-Neustart

## [1.1.0] - 2026-04-12

- Hinzugefügt
- Universelle Felder für alle Marken — `coordinator._enrich()`
- Code-Qualität

## [1.0.0] - 2026-04-12

- Erstes stabiles Release

## [0.14.25] - 2026-04-12

- Hinzugefügt
- Neue Marken: Porsche + VW North America
- Config Flow

## [0.14.23] - 2026-04-12

- Alle Entities standardmäßig sichtbar
- Geändert

## [0.14.22] - 2026-04-12

- Bug: `window_heating` mapped auf `command_start_climate`
- 7 neue Entities
- `iot_class`: `cloud_polling` → `cloud_push`

## [0.14.10] - 2026-04-12

- VW EU Scope
- BRAND_AUDI client_id
- Research-Ergebnis

## [0.14.9] - 2026-04-12

- Fixed — basierend auf volkswagencarnet (MIT) Analyse

## [0.14.8] - 2026-04-12

- Auth0 400: login_url direkt verwenden
- Kombinierter POST
- Fallback

## [0.14.7] - 2026-04-12

- Auth0 UL v2: 400 Bad Request behoben

## [0.14.6] - 2026-04-12

- Auth0 Universal Login v2
- 2FA-Unterstützung

## [0.14.5] - 2026-04-12

- Auth0 Universal Login

## [0.14.4] - 2026-04-12

- Abfahrtstimer schreiben

## [0.14.3] - 2026-04-12

- IDK Login: robusteres CSRF-Parsing
- Detailliertes Schritt-Logging

## [0.14.2] - 2026-04-12

- Audi/VW Login
- AZS Token Exchange (Audi)
- VW US/CA aus Brand-Liste entfernt

## [0.14.1] - 2026-04-12

- Semver retroaktiv korrigiert: 0
- iot_class: cloud_push → cloud_polling (wir pollen, kein Push-Protokoll)
- CI: CarConnectivity-Dependencies entfernt, mypy + coverage-threshold hinzugefügt

## [0.11.0] - 2026-04-12

- Platinum Quality Scale

## [0.10.1] - 2026-04-12

- CarConnectivity und alle 5 Brand-Connectors aus manifest
- manifest

## [0.10.0] - 2026-04-12

- cariad/
- cariad/auth/idk
- cariad/api/vw_eu

## [0.9.0] - 2026-04-12

- Lizenz: MIT → **Apache 2
- Copyright: Prash Balan (@its-me-prash) in allen Dateien
- strict-typing Platinum-Regel: 0 mypy-Fehler (--disallow-untyped-defs

## [0.8.2] - 2026-04-12

- Automatische Erkennung des requests-Versionskonflikts (HA 2026
- repairs
- Stabiler Betrieb auch bei requests-Konflikt

## [0.8.1] - 2026-04-11

- Python 3

## [0.8.0] - 2026-04-11

- diagnostics
- Stale-Device-Bereinigung bei Fahrzeugwechsel
- Gold Quality Scale vollständig: runtime_data, reauth, reconfigure,

## [0.7.0] - 2026-04-09

- Abfahrtstimer (Timer 1–3): set_departure_timer Service
- number
- Gold Quality Scale: runtime_data, reauth-Flow, reconfigure-Flow

## [0.6.0] - 2026-04-08

- EntityCategory für diagnostische Sensoren
- Sensoren: Ladeleistung kW, Ladegeschwindigkeit km/h, Akkutemperatur, Ölstand

## [0.5.0] - 2026-04-06

- Abfahrtstimer-Sensor (read-only): zeigt nächsten aktiven Timer

## [0.4.6] - 2026-04-05

- Coordinator-Crash wenn GPS-Daten None zurückgeben

## [0.4.5] - 2026-04-04

- Fensterheizung: is_on nach manuellem Toggle korrekt

## [0.4.4] - 2026-04-04

- SEAT/CUPRA: fehlende user_id → 404 auf Garage-Endpoint

## [0.4.3] - 2026-04-03

- Klimatisierungstemperatur: Kelvin→Celsius für alle Marken

## [0.4.2] - 2026-04-03

- Ladeende-ETA: negativer Wert wenn Fahrzeug voll geladen

## [0.4.1] - 2026-04-02

- Config Flow reconfigure verlor Scan-Intervall nach Speichern

## [0.4.0] - 2026-04-01

- Standort-Adresse als Sensor (OpenStreetMap Geocoding)
- Fahrtrichtung (Heading) als Sensor
- Ladesäulen-Informationen: Name, Betreiber, Adresse, Leistung

## [0.3.4] - 2026-03-31

- Škoda: Mehrfache Initialisierung des MQTT-Listeners

## [0.3.3] - 2026-03-30

- Audi: AZS-Token-Refresh nach 1h zuverlässig

## [0.3.2] - 2026-03-29

- VW EU: doors_individual leer wenn overallStatus == SAFE

## [0.3.1] - 2026-03-28

- CUPRA: command_wake 405 bei manchen Modellen ignoriert

## [0.3.0] - 2026-03-27

- Individuelle Tür-Sensoren (Fahrertür, Beifahrertür, Fond, Kofferraum)
- Fensterstatus-Sensoren

## [0.2.2] - 2026-03-25

- Mehrfache Fehlerlog-Einträge bei dauerhafter Nichterreichbarkeit

## [0.2.1] - 2026-03-24

- GPS: None statt 0

## [0.2.0] - 2026-03-23

- Ladeleistung-Sensor kW
- Ladegeschwindigkeit-Sensor km/h
- Ladeende-ETA-Sensor

## [0.1.1] - 2026-03-21

- HA 2024

## [0.1.0] - 2026-03-20

- Erste Version: VW EU, Audi, Škoda, SEAT, CUPRA
- Sensoren: Akkustand, Reichweite, Kilometerstand, GPS, Türen, Fenster, Klimatisierung,
- Services: lock, unlock, start/stop Klimatisierung, flash, wake, refresh

