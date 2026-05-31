<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant integration for Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>One integration for all 7 VAG brands, direct API access, no middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.md">Deutsch</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **What keeps working as before**: all entities (e.g. `sensor.audi_q4_battery_soc`),
> all service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), all automations,
> the HACS install - **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up - especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## What is new in v2.7.x

**Browser-Login (no password stored in HA) for Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant per RFC 8628. Scan a QR code with your phone or open the URL on any device, confirm a short code, done. Real refresh_token from the IDP, no two-hour re-login cycle.

**Multi-strategy auth resolver.** Up to three fallback strategies per brand (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal read-only). One strategy dies, the integration keeps running on the next.

**Data Act Portal as read-only fallback.** In-house implementation of the EU Data Act portal login, wired as a 3rd-tier strategy. Read-only but attestation-free, so unbreakable when VW tightens the OAuth path.

**Significantly more data points.** Trip statistics (lifetime distance, last trip), oil level, per-wheel tire pressure, per-position doors / windows / sunroof / trunk lock, outside temperature on MY24+ vehicles, Webasto auxiliary heating, all backend warnings including brand-specific ones like Audi STO / towing-bracket.

**Security hardening.** Token URLs are no longer printed raw in the log (they contained JWTs that base64-decode to email and access_token). Exception type only at ERROR level, full message at DEBUG.

Full [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Where we lead

State as of 2026-05-31, after the 2026-05-27 VW backend change that hit the entire HA-VAG-integration community simultaneously:

| Feature | Status here | Status in other HA-VAG integrations |
|---|---|---|
| **OAuth Device Authorization Grant (QR-Login)** for Audi/Škoda/SEAT/CUPRA | ✅ live since v2.7.0 | Nobody has it |
| **Multi-strategy auth fallback chain** (3 tiers per brand) | ✅ live since v2.6.0 | Nobody |
| **EU Data Act portal read-only tier** as 3rd-tier fallback | ✅ integrated since v2.6.0 | Only available as separate standalone integration |
| **InvalidURL safety net** prevents token leakage in logs | ✅ live since v2.7.2 | Nobody |
| **Server-side attestation gate watcher** alerts on VW backend flag flips | ✅ live since v2.7.0 | Nobody |
| **Vehicle Data Scout** auto-detects API drift, generates 1-click bug reports | ✅ live since v1.9.0 | No comparable feature |
| **All 7 VAG brands in one integration** (Audi+VW+Škoda+SEAT+CUPRA+Porsche+VW NA) | ✅ | Other projects ship one repo per brand |

---

## Where the limits are (honest)

**VW EU is hard Play-Integrity-gated since the 2026-05-27 backend change.** This wall hits every Python-based VAG integration (ours included). It is not a temporary delay on our side, it is VW's backend policy:

- The token endpoint validates an `X-Assertion` header that must be a Google Play Integrity signed JWS token
- Python cannot generate this token because the signing key lives only inside Google's mobile-app attestation service
- Consequence: **VW EU users do not get a real refresh_token** and are forced into a re-login every ~2 hours

What we still offer for VW EU:

1. **OIDC Hybrid Flow** as primary strategy (read + write, but 2h re-login)
2. **EU Data Act portal** as read-only fallback (15-min cadence, attestation-free, unbreakable)
3. **Attestation gate watcher** that polls weekly and auto-opens an issue the moment VW opens the gate

**EU Data Act 2026-09-12 compliance deadline.** By that date, VW must legally provide direct vehicle-data access to owners without attestation gating. Our `_data_act_portal.py` is positioned for that day.

Brand status:

| Brand | Auth | refresh_token? | Notes |
|---|---|---|---|
| **Audi** | DAG Browser-Login or email+pwd Hybrid | ✅ yes (via DAG) | Fully functional |
| **Škoda** | DAG Browser-Login or email+pwd | ✅ yes (via DAG) | Fully functional |
| **SEAT** | DAG Browser-Login or OLA | ✅ yes (via DAG) | Fully functional |
| **CUPRA** | DAG Browser-Login or OLA | ✅ yes (via DAG) | Fully functional |
| **VW EU** | OIDC Hybrid Flow or Data Act Portal | ⚠️ no, 2h re-login | Backend-gated (see above) |
| **Porsche** | Auth0 + PPA | ✅ yes | Stable |
| **VW US/CA** | VW NA Cloud | ✅ yes | Beta |

---

## What you get

100+ entities across 11 HA platforms, 20+ service calls, native multi-vehicle support per account. Quality Scale Platinum.

**Sensors** (per vehicle): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 corners, Last Alarm Timestamp, Heater Source for ID.x, Oil Level Warning, Vehicle Warning Messages (text sensor with all backend warnings).

**Binary sensors**: Doors Locked, Doors Open per door, Windows Open per window, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On per light, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Controls**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 with weekly preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image platform**: 1-7 vehicle renders per VIN (Audi/VW via GraphQL MediaService, CUPRA/SEAT via OLA viewPoints, Skoda via Widget + multi-angle composites).

**Device tracker**: GPS position as TrackerEntity for the HA Lovelace Map.

---

## Installation

### Option 1: One-Click (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Option 2: HACS custom repository

1. HACS → Integrations → ⋮ → Custom repositories
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Category: Integration
4. Install **VW Group Connect**
5. Restart Home Assistant

### Option 3: Manual

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Then restart HA.

---

## Configuration

Settings → Devices & Services → Add integration → "VW Group Connect"

**On first setup you choose:**

- **Browser-Login** (recommended for Audi/Škoda/SEAT/CUPRA): scan a QR code or open the URL, no password stored in HA
- **Email + password** (for VW EU, Porsche, VW US/CA): classic Brand-ID credentials

**Options** (available after setup):
- Polling interval (5-60 min, default 10 min)
- Read-only mode for safe automations without accidental commands
- Reverse geocoding opt-in (sends GPS to OpenStreetMap for address lookup)
- Push toggles (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) as foundation, live activation pending

---

## Lovelace examples

### Map Card

```yaml
type: map
title: Fleet
default_zoom: 12
hours_to_show: 24
entities:
  - device_tracker.audi_a4_b9_position
  - device_tracker.vw_golf_7_gte_position
  - zone.home
```

### Picture-Entity Card with vehicle render

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Charging-Station Lookup

```yaml
action: vag_connect.find_charging_stations
data:
  vin: WAUZZZ...
  latitude: 47.3769
  longitude: 8.5417
  radius_m: 5000
  max_results: 25
response_variable: result
```

More examples in [`docs/FAQ.md`](docs/FAQ.md). Custom Lovelace cards integrate automatically via `extra_state_attributes.image_url`.

---

## FAQ

| Question | Answer |
|---|---|
| When is my car woken up? | Only on service calls (Lock/Climate/Wake), never on status polls. Smart-wake cap: max 3 wakes/day per vehicle, 5 min cooldown. |
| How much API quota? | MyCupra/MySeat: ~1500 calls/day. At 10 min polling: ~144 calls/day = 10% budget. Sensor `requests_remaining_today` shows the count. |
| Why do I have to re-login every 2h on VW EU? | VW gated the token endpoint behind Google Play Integrity since 2026-05-27. This hits every Python-based VAG integration. EU Data Act 2026-09-12 should fix this. |
| Token persists across HACS updates? | Yes, since v1.19.2 via HA Store persistence. |
| How do I report bugs? | HA → Integration → 🔧 Repair → Bug report. Diagnostics are anonymised (VINs masked, GPS rounded, tokens stripped). |
| Field labels show raw keys (`brand`, `spin`) after upgrade? | Hard browser refresh (Ctrl+Shift+R). HA caches translations client-side. |

Full FAQ in [`docs/FAQ.md`](docs/FAQ.md). Dashboard troubleshooting in [`docs/dashboards.md`](docs/dashboards.md).

---

## Privacy & Security

- No external services, all direct between HA and manufacturer API
- Token cache local in HA's `.storage/` (per config entry, JSON, automatically removed on integration removal)
- Diagnostics anonymised: VINs masked, GPS rounded to 1 decimal, tokens and passwords fully stripped
- Reverse geocoding opt-in, default off
- VIN masking consistent across all logs
- Token URLs redacted at ERROR log level (v2.7.2+)

Details in [`PRIVACY.md`](PRIVACY.md) and [`SECURITY.md`](SECURITY.md).

---

## Contributing

PRs welcome, see [`CONTRIBUTING.md`](CONTRIBUTING.md). Style rules in [`STYLE.md`](STYLE.md) (private maintainer copy in `_private/STYLE.md`).

**Vehicle Data Scout** (live since v1.9.0): when your integration detects unknown JSON fields, it automatically creates a HA Repair notification with a pre-filled GitHub issue link. One-click bug report, no code reading required.

---

## License

[Apache License 2.0](LICENSE) for integration code. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) for `docs/research/` content. Attributions to upstream open-source projects in [`NOTICE.md`](NOTICE.md).
