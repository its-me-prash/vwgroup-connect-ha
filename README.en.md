<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant integration for Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>One integration for all 7 VAG brands — direct manufacturer-API access, no middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue" alt="Home Assistant"></a>
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
> the HACS install — **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up — especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## 🚗 What it does

Connects Home Assistant **directly** to your vehicle cloud account (myAudi, We Connect ID, MyŠkoda, MyCupra, MySeat, My Porsche, MyVW). **No middleware, no Docker, no extra service** — log in with your app credentials, done.

- **100+ entities** across **11 HA platforms** (Sensor, Binary-Sensor, Device-Tracker, Switch, Button, Climate, Number, Lock, Image, Select, Time)
- **20+ services** (Lock, Climate, Charging, Departure-Timer with Weekly-Preheat, Charging-Station-Lookup, etc.)
- **Vehicle render as device picture** + custom Lovelace card support
- **GPS position on the HA map** as TrackerEntity
- **Multi-vehicle support** per account
- **Read-only mode** for safe automation use
- **Quality scale: Platinum** ⭐

---

## ⭐ What makes us unique

| Feature | Status |
|---|---|
| **Native coverage of all 7 VAG brands in a single integration** | No other project covers Audi + VW EU + Škoda + SEAT + CUPRA + Porsche + VW NA simultaneously |
| **Direct manufacturer-API access** without middleware / Docker / 3rd service | Sign in with your app credentials, everything runs in the HA container |
| **Vehicle Data Scout** — automatic JSON-field drift detection with Repair notification + 1-click GitHub issue | Live since v1.9.0 |
| **Capability-Filter Phase 3** — phantom entities suppressed before spawn when backend reports "missing capability" | Per-VIN, per-command, three phases deep |
| **Per-VIN wakeup cap + cooldown** — smart auto-wake with max 3 wakes/day per VIN, 5-min cooldown between calls | Improves battery longevity |
| **Auth Resilience One-Click Repair** — reauth flow directly from the Repairs panel | invalid credentials / 2FA / T&C / marketing-consent |
| **System Health Panel** — at-a-glance push channel status, API quota, last poll | HA Settings → System → Repairs |
| **Bruno-CI Stage 2** — strict URL-drift check, every new endpoint URL needs `.bru` coverage | Prevents silent breakage during refactors |
| **Token persistence across HA updates** | No re-login after HACS updates since v1.19.2 |
| **Diagnostics anonymisation by default** — VINs, GPS, tokens stripped before export | Privacy by default |

---

## ✨ Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | **[NEW v2.0]** Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | **[NEW v2.0]** SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | **[NEW v2.0]** 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | **[NEW v2.0]** Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | **[NEW v2.0]** 3 pure-read enabled-sensors — decouples read from write |
| **Weekly Preheat (`recurring_on`)** | **[NEW v2.0]** Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | **[NEW v2.0]** `vag_connect.find_charging_stations` service with `response_variable:` |
| **Vehicle Alarm sensors** | **[NEW v2.0]** closes issue #33 — alarm_active + siren_active + last_alarm_at |
| **heaterSource sensor** | **[NEW v2.0]** closes issue #163 — read-only heat-pump source for ID.x |
| **Push Manager Lifecycle Wiring** | **[NEW v2.0]** Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | **[NEW v2.0]** Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | **[NEW v2.0]** Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | **[NEW v2.0]** Drop-in `system_health.py` with brands / polls / quota / push |
| **Quality Scale Platinum** | **[NEW v2.0]** Re-introduced after v1.26.x revert — verified via CI Hassfest |
| **DeviceInfo `configuration_url` + `suggested_area`** | **[NEW v2.0]** Brand-aware "Open in App" button + auto-area "Garage" |

---

## 📋 Supported brands

| Brand | Backend | Status | Highlights |
|---|---|---|---|
| **Audi** (myAudi) | Cariad-BFF + MBB Legacy | ✅ Stable | PPC/PPE Climate, ICE Engine Start, Long-Term Trip Aggregates **[NEW v2.0]** |
| **Volkswagen EU** (We Connect ID) | Cariad-BFF + MBB Legacy | ✅ Stable | PHEV range triple, Tank-Level via MBB for Golf 7 GTE, Charging-Station Lookup **[NEW v2.0]** |
| **Škoda** (MyŠkoda mysmob) | Skoda mysmob | ✅ Stable | Driving-Score **[NEW v2.0]**, Aux-Heating **[NEW v2.0]**, Charging-Profiles, OTA, multi-angle renders |
| **SEAT** (MySEAT OLA) | OLA | ✅ Stable | OLA viewPoint renders (4-7 views), Battery-Care |
| **CUPRA** (MyCupra OLA) | OLA | ✅ Stable | OLA viewPoint renders, Born MY26 firmware shapes, defensive `command_flash` **[NEW v2.0]** |
| **Porsche** (My Porsche) | PPA + Auth0 | ✅ Stable | TPMS sensors **[NEW v2.0]**, dedicated HTTP hardening (retry/quota/storm-protection) |
| **VW US/CA** (myVW NA) | VW NA Cloud | 🟡 Beta | Charge ETA, Climate, Lock, Doors, Weekly Preheat **[NEW v2.0]** |

---

## 🚀 Installation (HACS)

### Option 1: One-click install (recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Option 2: HACS custom repository (manual)

1. **HACS → Integrations → ⋮ → Custom repositories**
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Category: **Integration**
4. Search **VW Group Connect** + install
5. **Restart Home Assistant**

### Option 3: Manual install

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
# Restart HA
```

---

## ⚙️ Configuration

**Settings → Devices & Services → Add Integration → "VW Group Connect"**

| Field | Example | Description |
|---|---|---|
| Brand | `Audi`, `Volkswagen EU`, etc. | Which brand app do you use? |
| Email | `you@example.com` | Your VAG account email |
| Password | `••••••••` | Your account password |
| S-PIN | `1234` *(optional)* | 4-digit PIN for Lock/Unlock on some brands |

**Options** (Settings → Devices & Services → VW Group Connect → ⋮ → Configure):

- **Polling interval** (5-60 min) — Default 10 min. Lower = fresher, but burns API quota faster.
- **Read-only mode** — when enabled, only status sensors are spawned; no switches/buttons that send commands.
- **Reverse geocoding** (opt-in) — sends GPS to OpenStreetMap for address resolution.
- **Push toggles** (Skoda MQTT / CUPRA-SEAT FCM / Audi-VW FCM) — Lifecycle wiring **[NEW v2.0]**, live activation pending tester.

---

## 🎨 What you get

### Standard entities per vehicle (all brands)

**Sensors**: Battery SoC, Range (electric/combustion/total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power/Rate/Type, Last Trip Stats, **Lifetime Trip Stats [NEW v2.0]**, Charging History, Plug State, Lights Count, Equipment Count, Software Version, Quota Remaining, Connection State, Last Seen, **Driving Score (Skoda) [NEW v2.0]**, **TPMS 4 corners (Porsche) [NEW v2.0]**, **Last Alarm Timestamp [NEW v2.0]**, **Heater Source (ID.x) [NEW v2.0]**.

**Binary Sensors**: Doors Locked, Doors Open (per door), Windows Open (per window), Trunk/Hood/Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On (per light), Vehicle Online, **Departure-Timer Enabled (3) [NEW v2.0]**, **Alarm Active + Siren Active [NEW v2.0]**, **TPMS Warning (Porsche) [NEW v2.0]**.

**Controls**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Window Heating Combined, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto, **Skoda + CUPRA/SEAT [NEW v2.0]**), Departure Timer (1-3 with `time` platform + **Weekly Preheat [NEW v2.0]**), Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, **Find Charging Stations [NEW v2.0]**.

**Image Platform**: 1-7 vehicle renders per VIN (Audi/VW: GraphQL MediaService; CUPRA/SEAT: OLA viewPoints; Skoda: widget + multi-angle composites).

**Device Tracker**: GPS position as TrackerEntity (`source_type: gps`) for the HA Lovelace map.

### Automatic vehicle picture

The car appears as **Device Picture** in HA, plus as `entity_picture` on every entity. Custom Lovelace cards ([Ultra-Vehicle-Card](https://github.com/WJDDesigns/Ultra-Vehicle-Card), [vehicle-info-card](https://github.com/ngocjohn/vehicle-info-card), [Mushroom](https://github.com/piitaya/lovelace-mushroom) Templates) read `extra_state_attributes.image_url` automatically.

---

## 🗺️ Lovelace examples

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

### Charging-Station Lookup [NEW v2.0]

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

More examples in [`docs/FAQ.md#lovelace-examples`](docs/FAQ.md). Dashboard troubleshooting + dedicated VW Group Connect Lovelace card (BETA): [`docs/dashboards.md`](docs/dashboards.md).

---

## 🔧 FAQ

| Question | Answer |
|---|---|
| **When is my car woken up?** | Only on service calls (Lock/Climate/Wake), never on status polls. Smart wake cap: max 3 wakes/day per car (default), 5-min cooldown between wakes. |
| **How much API quota?** | MyCupra/MySeat: ~1500 calls/day. With 10-min default polling: ~144 calls/day = 10% budget. Sensor `requests_remaining_today` shows the current count. |
| **What if Tank-% is missing on Golf 7 GTE?** | v1.25.0 added MBB VSR Phase 2 read-side fallback. See [Golf 7 GTE Tank Guide](docs/GOLF_7_GTE_TANK_GUIDE.md). |
| **Token survives HACS update?** | ✅ yes, since v1.19.2 — token persistence via HA `Store` (no re-login after updates). |
| **How do I report bugs?** | HA → Integration → 🔧 Repair → Bug Report. Diagnostics are anonymised (VINs masked, GPS rounded, tokens stripped). |
| **"Add to Dashboard" doesn't show my dashboard / view?** | Most common cause: dashboard is in **YAML mode** (only Storage-mode dashboards appear in the picker). Or the view doesn't exist yet. Full guide + dedicated VW Group Connect Lovelace card (BETA): [`docs/dashboards.md`](docs/dashboards.md). |

Full FAQ in [`docs/FAQ.md`](docs/FAQ.md).

---

## 🛡️ Privacy & Security

- **No external services** — everything runs directly between HA and the manufacturer API
- **Token cache** local in HA's `.storage/` (per config entry, JSON, automatically removed on integration removal)
- **Diagnostics anonymised**: VINs masked (`***ABC123`), GPS rounded to 1 decimal, tokens/passwords fully stripped
- **Reverse geocoding opt-in** — disabled by default
- **VIN masking** consistent across all logs

Details in [`PRIVACY.md`](PRIVACY.md) and [`SECURITY.md`](SECURITY.md).

---

## 🤝 Contributing

PRs welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).

**Vehicle Data Scout** (live since v1.9.0): when your integration detects unknown JSON fields, it automatically creates an HA Repair notification with a pre-filled GitHub issue link. **One-click bug report without you having to look at code.**

Live testers wanted for the external-blocked tracks — comment on the relevant issue with `Brand + model + year + subscription status`.

---

## 📜 License

[Apache License 2.0](LICENSE) — see also [`NOTICE.md`](NOTICE.md) for attributions to upstream projects ([myskoda](https://github.com/skodaconnect/myskoda), [pycupra](https://github.com/WulfgarW/homeassistant-pycupra), [audi_connect_ha](https://github.com/audiconnect/audi_connect_ha), [volkswagencarnet](https://github.com/Trekky12/volkswagencarnet), [evcc](https://github.com/evcc-io/evcc)).
