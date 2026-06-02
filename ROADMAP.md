# Roadmap

Single source of truth. Replaces the five previous roadmap docs that were left over from the v1.x era. Last updated 2026-05-31, after v2.7.4 shipped.

## Current state

**v2.7.4** is the live release on `main`. The integration covers all 7 VW Group brands in a single Home Assistant component, with Quality Scale Platinum.

The big strategic event of this cycle was the 2026-05-27 VW Auth wall (Play Integrity attestation enforcement on the Cariad BFF token endpoint). Most of v2.5.x, v2.6.0, and v2.7.0 was an emergency response to that wall. The integration is now structured around a multi-strategy resolver (browser-login plus hybrid flow plus Data Act portal) so that no single backend change can kill auth on any brand again.

Where we lead (no other HA-VAG project ships these today):

- OAuth Device Authorization Grant (RFC 8628) browser-login for Audi, Skoda, SEAT, CUPRA
- Multi-strategy auth resolver with up to 3 fallback tiers per brand
- In-house EU Data Act portal as read-only fallback
- Server-side attestation gate watcher (weekly probe, auto-alerts on gate-flip)
- Vehicle Data Scout with 1-click bug reports
- All 7 brands in one integration

Where the limits are (honest):

- VW EU is Play-Integrity-walled at the token endpoint. Python cannot sign the X-Assertion JWS. VW EU users get no real refresh_token and are forced into a ~2h re-login cycle. This hits every Python-based VAG integration, not just ours.
- The EU Data Act compliance deadline is 2026-09-12. From that date VW must offer direct owner data access without attestation. Our Data Act portal path is positioned for that day.

## v2.8.0 (in-flight)

Action items #1 to #5 from the 2026-05-30 competitive scan, plus the dead-weight cleanup that came out of the same audit.

1. README rewrite for v2.7.x reality. Drop the v2.0 Big-Bang highlights. Add Where-we-lead and Where-the-limits-are blocks. DE plus EN canonical, 6 other languages mechanically updated. Already merged on the staging branch.
2. Dead-weight cleanup (task #44). Remove the Pydantic dual-write scaffold that never grew past one model and caused blocking-IO warnings, remove the `euda.py` v2.0 shim that had zero callers, retire 6 stale v1.x docs, retire 12 dead probe scripts from the v1.27 research era. Already merged on the staging branch.
3. Coordinator stale-state watchdog for hybrid_full. Silent re-authenticate when all VINs have failure_count >= 2 and last_good_at is older than 2x scan_interval. Mirrors the upstream community automation pattern (template trigger reload every 5 min) but internalised so users do not have to wire it themselves. Already merged on the staging branch.
4. 30-day device-bound IDP cookie persistence. The VW IDP issues a cookie after a successful email-OTP that suppresses the OTP for around 30 days. Until now we discarded it on every restart, reload, and 2h re-login. TokenSet, TokenStorage, and IDKAuth all extended to round-trip the cookie. Already merged on the staging branch.
5. Roadmap consolidation (this doc, task #43). Five overlapping ROADMAP files reduced to one canonical top-level file. The deleted files are listed under the v2.5 to v2.7 done block below.

Target ship. Tag v2.8.0 once #1 to #5 are reviewed and the staging branch is merged.

## v2.11.0 (planned, post-v2.10.0)

Medium- and low-priority items surfaced during the 2026-06-02 competitor scan against the major HA-VAG integrations in the ecosystem. None of these are urgent, but all are within the existing parser surface so they cost little to add.

### SEAT/CUPRA OLA endpoints we do not yet poll

- `/v1/vehicles/{vin}/notifications`. Surface in-vehicle notification count + last subject as a sensor so HA users can trigger automations on "you have unread messages in the car".
- `/v1/vehicles/{vin}/permissions`. Owner vs co-driver detection. Useful for HA automations that should only fire for the primary user.
- `/v1/vehicles/{vin}/measurements/engines`. Engine-specific measurements (separate from the existing per-VIN charge/climate endpoints). Likely overlap with mycar.engines but worth a direct probe.
- `/v1/vehicles/{vin}/charging/profiles`. Charge-time profile list, SEAT/CUPRA flavour of the Skoda profiles we already parse since v1.16.0.
- `/v1/vehicles/{vin}/charging/modes` + `/v2/` variant. Settable enumeration of allowed charge modes. Read-only equivalent already lands via `charging_preferred_mode` (v2.8.1); the settable surface is the gap.
- `/v1/vehicles/{vin}/charging/actions/update-settings`. PUT for charge plan changes. Wire as a HA service.
- `/v1/charging/points` (no VIN). Public POI catalog. Similar to our existing `find_charging_stations` but SEAT-naming.

### Field additions surfaced by the VW-specific competitor (vw_vehicle.py)

- `hv_battery_min_temperature` + `hv_battery_max_temperature`. We collapse to a single `battery_temp`; the min/max pair is more useful for thermal-management diagnostics.
- `charge_max_ac_setting` vs `charge_max_ac_ampere`. Distinguish the user-requested setting from the actual deliverable amperage.
- `available_charge_modes`. List attribute on the `charge_mode` sensor showing what the user is allowed to pick.
- `auto_release_ac_connector_state` + `auto_release_ac_connector`. Born MY24+ feature where the connector auto-releases at full charge.
- `optimised_battery_use`. Battery-preservation flag distinct from the existing `battery_care` field (v2.8.1).
- `active_ventilation_state` + `active_ventilation_remaining_time`. Ventilation as a separate mode from climatisation, VW EU specific.
- `sunroof_rear_closed` + `roof_cover_closed`. Rear sunroof + Cabrio top status; we expose only the front sunroof today.
- `connection_state_battery_power_level`. 12V battery health (low/normal/high) for long-park diagnostics, distinct from the existing voltage_12v + warning_12v_low fields.
- `last_trip_total_fuel_consumption_l` + `last_trip_total_electric_consumption_kwh`. Total per-trip (we have averages, not totals).

### Field additions surfaced by audi_connect_ha (v2.1.0)

- `plug_led_color`. Audi-specific HW: the charging port LED reports its current color. Useful as a glance-sensor in HA dashboards.
- `actual_charge_rate`. Real-time charge rate sensor; we expose only the averaged `charging_rate_kmh`.
- shortterm / longterm trip aggregator reset endpoints. Buttons on the entity card to reset trip counters from HA.

### Per-attribute `_last_updated` timestamps

Pattern from the VW-specific competitor: every property has a sibling `{field}_last_updated` that records when the value last came from the backend. Useful for users to debug stale entities directly in Dev Tools without downloading a diagnostics dump. Scope is a refactor (one sibling per VehicleData field), so this is genuinely a v3.0+ item even though the concept is simple.

## v3.0 (planned)

Genuinely pending. Nothing here is committed to a date. This is the post-2.8 backlog.

**Split coordinator (fast and slow tiers).** Port the upstream community pattern of a fast 5 to 15 min poll for charging, climate, lock, position, and a slow 4 to 6h poll for trip stats, maintenance, health. Drops API quota use on garaged cars without losing freshness on the things that matter.

**Push live activation.** Push manager foundation has shipped per-brand since v1.18 (Skoda MQTT), v1.19 (CUPRA and SEAT FCM), and v1.23 (Audi and VW Cariad FCM). Wire-in is blocked on per-brand testers confirming the live FCM project ID, TOTP scheme, and broker auth handshake. After this lands, polling cadence drops to backup role (30 to 60 min) and API quota use drops 80%+.

**EU Data Act 2026-09-12 promotion.** Our `_data_act_portal.py` is already shipped as a read-only fallback. On 2026-09-12 we expect VW to be legally required to expose direct owner data access without attestation. At that point. Lift Data Act portal from read-only fallback to primary path for VW EU. Drop the 2h re-login. Either retire or downgrade the hybrid_full strategy.

**Command channel rewrite for write-side.** Read path is solid. Write-side (lock, climate-start, charging-start, set-target-soc) still routes through the same Cariad BFF endpoints that are now attestation-gated. Once push live activation lands, write-commands also dispatch via push where supported, with HTTP fallback.

**BLE proximity detection.** `binary_sensor.car_nearby` derived from HA Bluetooth scan against the brand-specific advertising name pattern. Optional ESPHome BLE proxy guide. Drives garage-door automations and arrival scenes.

**Phone-as-Key lifecycle (Audi MDK).** `sensor.mdk_paired_devices_count`, `sensor.mdk_expires_at`, `binary_sensor.mdk_expires_soon`, `event.mdk_lifecycle`. Read-only surfacing of the OEM MDK state.

**send_destination service.** `vag_connect.send_destination(lat, lng, label, vin)`. The OEM endpoint is documented per-brand, the wiring is mostly mechanical, but it needs a tester per brand to confirm the nav screen actually receives the destination.

**Anti-theft event suite.** `event.alarm_triggered` exists since v2.0.0 via the binary sensors but the full DWAP event surface (door, exterior, interior, movement, panic, trailer subtype split) plus `event.geofence_zone_transition`, `event.speed_exceeded`, `event.valet_zone_violation`, `event.vts_tracking_started`, `event.child_presence_detected` is not wired yet.

**Vehicle Health Pro.** Service-due predictions in km as well as days. Today we expose days only. The km variant exists in the Audi BFF response under `serviceData.maintenance.value.distance` but is not parsed.

## Won't do (and why)

So that users do not file feature requests for these.

- **MBB direct-data path.** The `XID_APP_VW` permission gate is structural and not bypassable from public clients. Verified during the May 2026 Pre-Cariad audit. We won't reverse-engineer legacy MBB direct-data endpoints.
- **Anything that requires Play Integrity attestation.** Python cannot generate a signed X-Assertion JWS because the signing key lives in Google's mobile-app-attestation service. This is the root cause of the VW EU 2h re-login. Workaround is Data Act portal once the 2026-09-12 deadline forces it.
- **VW China (2026+).** Different stack (CEA and XPeng platform), undocumented, near-zero HA user base.
- **Lamborghini, Bentley, Bugatti commands.** No verified public API for any of the three. Lamborghini has an interesting telemetry API but nothing actionable for HA.
- **Ducati (motorcycles).** Out of scope.
- **MAN, Scania (commercial fleet).** Different use case and different API.
- **Ford Explorer Electric.** FordPass plus Ford Auth plus Ford API. Out of scope. The Ford Explorer Electric is a VW MEB-based vehicle but the customer-facing app and API are pure Ford. Use `marq24/ha-fordpass`.
- **VW EU Vehicle Render Image API.** No official render API exists for VW EU. Marketing CDN URLs are not authenticated and are not stable. Skoda widget renders and OLA viewPoints (CUPRA and SEAT) do exist and are wired.
- **Skoda `/v3/garage` fallback for Kodiaq Mk2.** Endpoint does not exist in the mysmob backend. Verified by source scan of the upstream Skoda community library (zero matches).
- **HACS Default repo flip.** Held until the EU Data Act path goes primary and the VW EU 2h re-login pain is gone. Pushing default-status while VW EU is still walled would cause a surge of confused 1-star reviews that are not actually bugs in the integration.
- **HOW-we-discovered-things content in public docs.** Public docs describe what users get and how to use it. The discovery methodology (APK extraction, jadx decompile, the App Atlas daily pipeline) stays internal. This is a competitive moat, not a secret.
- **Quality-scale changes that ride on unstable HA core APIs.** v1.26.1 was an install regression caused by a quality-scale-driven change that hit an upstream HA bug. We are conservative on this surface now.

## Done in v2.5 to v2.7 (emergency response shipped)

The 2026-05-27 VW Azure WAF migration broke Audi and VW EU login simultaneously across every Python-based VAG integration. The response pulled forward a lot of what was originally on the v3.0 roadmap. This block records what shipped during that period so the rest of this doc does not have to relitigate it.

Auth and resilience.

- v2.5.1. Consent wall auto-skip (ported from upstream evcc PR #30277).
- v2.5.3. OLA v1 to v5 fallback chain for SEAT and CUPRA offline vehicles (#306 Mii, Tavascan, Leon FR-KL).
- v2.5.4. Emergency hotfix for the VW Azure WAF migration (#313). Audi plus VW EU HTTP 403 on token endpoint.
- v2.5.5. App Atlas Phase A.5. APK extraction now also mines auth-config secrets to defend against future WAF migrations.
- v2.5.6. APK-primary auth-config with OAuth client_id fallback chain.
- v2.5.7. 502 resilience, OIDC discovery for token URL, qmauth fallback chain. Stop misdiagnosing VW server outages as credentials failures.
- v2.5.10. VW NA polish (last_seen_at plus capability-filter retry-after-timeout).
- v2.5.11. Field-tested auth hardening. VW EU was silently impersonating the Audi app via the `x-android-package-name` token. Audi market-config dynamic discovery. evcc-derived alternate OAuth client_id for Audi.
- v2.5.12. Wire `refresh_audi_market_config` (was never called in v2.5.11) plus atlas pipeline audit.
- v2.5.13. Play Integrity wall decoded via Audi 5.5.0 APK forensics. Documents the wall, does not bypass it.
- v2.6.0. Multi-Strategy Auth resolver. OIDC hybrid flow for VW EU. DAG module (RFC 8628) for Audi, Skoda, SEAT, CUPRA. In-house EU Data Act portal as read-only fallback strategy.
- v2.7.0. DAG browser-login UI. Trip statistics endpoint, warning_messages text sensor, oilLevel plus tyrePressure plus auxiliaryHeating jobs in the selectivestatus request. Audi MY24+ outside-temp key variants and window-heating shape variants. Cross-language translation parity for all 8 languages.
- v2.7.0b2 to b11. DAG UX iteration. Progress-dialog UX, two-phase step_id split, form-based URL display, QR code, TIMESTAMP sensor ISO-string parse fix.
- v2.7.1. Scout silencing for oilLevel, tyrePressure, auxiliaryHeating branches (#366, #367).
- v2.7.2. Coordinator setup-failure log redaction. aiohttp `InvalidURL` could surface the full redirect URL including access_token, id_token, and code JWTs. Type-only at ERROR, message at DEBUG. Multi-strategy resolver also catches non-AuthenticationError exceptions and converts cleanly.
- v2.7.3. Data Act portal auth. Scan returned HTML for EU Data Act consent signals before falling back to credentials-rejected (#372).
- v2.7.4. Scout `.error.*` envelope silencing for the 6-key shape the Cariad BFF returns when oilLevel, tyrePressure, auxiliaryHeating hit a 5xx upstream (#371, #373).

Infrastructure that came along the way.

- App Atlas APK extraction pipeline matured. Phase A.3 jadx full decompile plus cross-version semantic diff. Cloudflare-bypass headers. Daily watcher refresh.
- Scout policy. T1 paths get parsed instead of silenced. Silencer sweeps batched.
- Repo-wide sweep 2026-05-27 (CNG silencer plus docs refresh).
- Repo sanitisation pass. Upstream-maintainer names scrubbed, pre-push gate installed (#350, #364).

Files retired by this consolidation.

- `docs/ROADMAP.md`. Last edited 2026-05-08, still on v1.24.0 baseline. Replaced by this file.
- `docs/research/app-atlas/_v3.0-roadmap-FINAL.md`. Internal v3.0 strategy doc from 2026-05-27. The actionable items have been folded into the v3.0 section above. The strategy and moat content stays in the research archive locally but is no longer tracked.
- Two `_private/research-archive/` roadmap docs referenced in the old top-level ROADMAP.md. These were already removed from the tracked tree during task #44 dead-weight cleanup. Local copies retained outside git.

---

Issues, PRs, releases. https://github.com/its-me-prash/vwgroup-connect-ha
