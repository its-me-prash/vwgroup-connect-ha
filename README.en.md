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

## What is this?

**VW Group Connect is a [Home Assistant](https://www.home-assistant.io) integration for connected-car data and control across all seven Volkswagen Group brands — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche and VW US/Canada — from a single config entry, installable through [HACS](https://hacs.xyz).**

It surfaces battery and charging state, range, odometer, climate, doors/windows and location, and — where the brand's backend still allows it (e.g. Audi) — sends commands such as lock/unlock, climate and charge control. To stay working through Volkswagen's 2026 API changes it speaks several channels and falls back automatically when one is blocked: the brand-native backends, the read-only **EU Data Act** vehicle-data portal, and an opt-in `volkswagen.de` web channel.

Unlike portal-only integrations it also covers **Porsche** (which the EU Data Act portal excludes) and keeps **Audi two-way control**.

---

## Current status

In 2026 VW progressively locked down direct vehicle access for third-party tools (CARIAD BFF with device attestation, CUPRA/SEAT OLA behind Play Integrity since June 2026). This integration stays usable because it speaks **several channels** and switches automatically the moment one is blocked:

- **Brand-native backends** — full access including control, where available (Audi, Škoda, Porsche, VW US/CA).
- **EU Data Act portal** — read-only fallback for all brands (attestation-free, ~15 min cadence).
- **volkswagen.de web channel (beta, opt-in)** — a second attestation-free read channel for VW.

Current work centres on portal robustness (timeout retry, data freshness) and resilience across the channels.

➡️ Full version history: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Where we lead

Honest picture as of mid-2026: the EU Data Act portal has by now become the de-facto standard channel, and many integrations use it. What concretely sets us apart:

| Strength | Us | Portal-only alternatives |
|---|---|---|
| **All 7 group brands incl. Porsche** in one integration | ✅ | The EU Data Act portal **structurally excludes Porsche** — portal-only tools can never cover Porsche |
| **Audi two-way control** (lock/climate/charge, set target SoC) | ✅ | The portal is by design **read-only** |
| **Multi-channel auth with auto-fallback** (brand backend → EU Data Act portal → opt-in vw.de web) | ✅ | mostly single-source — one portal outage = total outage |
| **Vehicle Data Scout** — detects API drift automatically, generates 1-click bug reports | ✅ | nothing comparable |

---

## Where the limits are (honest)

**VW EU and CUPRA/SEAT OLA have been behind device attestation since 2026.** This wall (Google Play Integrity / Firebase App Check) hits every Python-based VAG integration — ours included. It is not a delay on our side, it is VW backend policy:

- The token / OLA endpoint demands an attestation token signed by the official app, which Python cannot produce (the signing key lives only inside the Google/Firebase attestation service).
- Consequence: **VW EU** gets no durable `refresh_token` (the OIDC hybrid flow lasts ~2 h), and **CUPRA/SEAT** over OLA get `403 "Forbidden device detected"` since ~2026-06-08.

What we offer regardless:

1. **EU Data Act portal** as a read-only fallback for all brands (attestation-free, ~15 min cadence) — takes over automatically when the native backend blocks.
2. **volkswagen.de web channel (beta, opt-in)** as a second attestation-free read channel for VW.
3. **OIDC hybrid flow** for VW EU as a read+write strategy (with the 2h re-login as the price).

**EU Data Act deadline 2026-09-12.** By that date, EU regulation requires VW to offer direct, attestation-free owner-data access — portal field coverage is expected to keep growing until then.

Status per brand:

| Brand | Control | Data | Note |
|---|---|---|---|
| **Audi** | ✅ Two-way | ✅ full | myAudi backend, no attestation wall |
| **Škoda** | ✅ Two-way | ✅ full | own Škoda backend |
| **Porsche** | ✅ Two-way | ✅ full | Auth0 + PPA, stable |
| **VW US/CA** | ✅ Two-way | ✅ full | VW NA cloud (beta) |
| **VW EU** | ⚠️ via OIDC hybrid (~2h re-login) | ✅ read-only portal / vw.de beta | backend attestation-gated |
| **CUPRA / SEAT** | ❌ OLA blocked (App Check) | ✅ read-only portal | since ~2026-06-08, not fixable via headers |

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
