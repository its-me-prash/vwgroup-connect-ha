<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant Integration für Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Eine Integration für alle 7 VAG-Marken — direkter API-Zugriff, ohne Middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Lizenz"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename / Hinweis zur Umbenennung
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **Was läuft weiter wie bisher**: alle Entitäten (z.B. `sensor.audi_q4_battery_soc`),
> alle Service-Calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), alle Automations,
> die HACS-Installation — **nichts bricht**. Marketing/Anzeigename ändern sich,
> Code-Internals bleiben unverändert. Siehe [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up — especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## 🚗 Was es kann

Verbindet Home Assistant **direkt** mit deinem Fahrzeug-Cloud-Account (myAudi, We Connect ID, MyŠkoda, MyCupra, MySeat, My Porsche, MyVW). **Keine Middleware, kein Docker, kein extra Dienst** — Anmeldung mit deinen App-Zugangsdaten, fertig.

- **100+ Entitäten** über **11 HA Plattformen** (Sensor, Binary-Sensor, Device-Tracker, Switch, Button, Climate, Number, Lock, Image, Select, Time)
- **20+ Services** (Lock, Climate, Charging, Departure-Timer mit Weekly-Preheat, Charging-Station-Lookup, etc.)
- **Vehicle-Bild als Device-Picture** + Custom-Lovelace-Card-Support
- **GPS-Position auf der HA-Map** als TrackerEntity
- **Multi-Vehicle-Support** pro Account
- **Read-only Modus** für sichere Anwendung in Automationen
- **Quality-Scale: Platinum** ⭐

---

## ⭐ Was uns einzigartig macht

| Feature | Status |
|---|---|
| **Native Coverage aller 7 VAG-Marken in einer einzigen Integration** | Kein anderes Projekt deckt Audi + VW EU + Škoda + SEAT + CUPRA + Porsche + VW NA gleichzeitig ab |
| **Direkter Hersteller-API-Zugriff** ohne Middleware / Docker / Drittservice | Login mit deinen App-Credentials, alles läuft im HA-Container |
| **Vehicle Data Scout** — automatische Drift-Erkennung neuer JSON-Felder mit Repair-Notification + 1-Klick-GitHub-Issue | Live seit v1.9.0 |
| **Capability-Filter Phase 3** — Phantom-Entitäten werden vor Spawn unterdrückt wenn Backend "Capability fehlt" zurückgibt | Pro VIN, pro Command, drei Phasen tief |
| **Per-VIN Wakeup-Cap + Cooldown** — Smart Auto-Wake mit max 3 Wakes/Tag pro VIN, 5min Cooldown zwischen Calls | Verbessert Akku-Langlebigkeit |
| **Auth-Resilience One-Click Repair** — Reauth-Flow direkt aus dem Repairs-Panel | invalid credentials / 2FA / T&C / marketing-consent |
| **System Health Panel** — at-a-glance Push-Channel-Status, API-Quota, Last-Poll | HA Settings → System → Repairs |
| **Bruno-CI Stufe-2** — strict URL-drift-check, jede neue Endpoint-URL braucht .bru-Coverage | Verhindert silent breakage bei Refactors |
| **Token-Persistence über HA-Updates** | Kein Re-Login nach HACS-Updates seit v1.19.2 |
| **Diagnostics-Anonymisierung by default** — VINs, GPS, Tokens werden vor Export gestrippt | Privacy-by-default |

---

## ✨ Aktuelle Highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | **[NEW v2.0]** Effizienz-Score 0-100 + Class-Bucket für Skoda MY24+ |
| **Cross-brand Aux-Heating Parität (Skoda)** | **[NEW v2.0]** SkodaClient erbt jetzt Standheizung-Switch von SEAT/CUPRA |
| **Porsche TPMS Sensors** | **[NEW v2.0]** 4 Reifen-Druck-Sensoren + Warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | **[NEW v2.0]** Lifetime Distance / Avg Fuel / Avg Electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | **[NEW v2.0]** 3 pure-read enabled-Sensoren — entkoppelt Read von Write |
| **Weekly Preheat (`recurring_on`)** | **[NEW v2.0]** Service-Param für Wochentag-Listen (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | **[NEW v2.0]** `vag_connect.find_charging_stations` Service mit `response_variable:` |
| **Vehicle Alarm / Diebstahl-Sensoren** | **[NEW v2.0]** schließt Issue #33 — alarm_active + siren_active + last_alarm_at |
| **heaterSource Sensor** | **[NEW v2.0]** schließt Issue #163 — read-only Heat-Pump-Quelle für ID.x |
| **Push-Manager Lifecycle-Wiring** | **[NEW v2.0]** Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | **[NEW v2.0]** Architektonischer Seam für 2026-09-12 EUDA Art.3 Deadline |
| **Auth Resilience One-Click Repair** | **[NEW v2.0]** Repair-Button für 4 auth-reasons triggert Reauth-Flow |
| **System Health Panel** | **[NEW v2.0]** Drop-in `system_health.py` mit Brands / Polls / Quota / Push |
| **Quality Scale Platinum** | **[NEW v2.0]** Re-introduced nach v1.26.x revert — verifiziert via CI Hassfest |
| **DeviceInfo `configuration_url` + `suggested_area`** | **[NEW v2.0]** Brand-aware "Open in App" Button + Auto-Area "Garage" |

---

## 📋 Unterstützte Marken

| Marke | Backend | Status | Besonderheit |
|---|---|---|---|
| **Audi** (myAudi) | Cariad-BFF + MBB Legacy | ✅ Stable | PPC/PPE Klima, ICE Engine Start, Long-Term Trip Aggregates **[NEW v2.0]** |
| **Volkswagen EU** (We Connect ID) | Cariad-BFF + MBB Legacy | ✅ Stable | PHEV Range-Triple, Tank-Level via MBB für Golf 7 GTE, Charging-Station Lookup **[NEW v2.0]** |
| **Škoda** (MyŠkoda mysmob) | Skoda mysmob | ✅ Stable | Driving-Score **[NEW v2.0]**, Aux-Heating **[NEW v2.0]**, Charging-Profiles, OTA, Multi-Angle Renders |
| **SEAT** (MySEAT OLA) | OLA | ✅ Stable | OLA viewPoint Renders (4-7 Ansichten), Battery-Care |
| **CUPRA** (MyCupra OLA) | OLA | ✅ Stable | OLA viewPoint Renders, Born MY26 firmware shapes, defensive `command_flash` **[NEW v2.0]** |
| **Porsche** (My Porsche) | PPA + Auth0 | ✅ Stable | TPMS Sensors **[NEW v2.0]**, eigene HTTP-Hardening (retry/quota/storm-protection) |
| **VW US/CA** (myVW NA) | VW NA Cloud | 🟡 Beta | Charge ETA, Climate, Lock, Doors, Weekly Preheat **[NEW v2.0]** |

---

## 🚀 Installation (HACS)

### Option 1: One-Click Install (empfohlen)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Option 2: HACS Custom Repository (manuell)

1. **HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories**
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Kategorie: **Integration**
4. **VW Group Connect** suchen + installieren
5. **Home Assistant neu starten**

### Option 3: Manuelle Installation

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
# HA neu starten
```

---

## ⚙️ Konfiguration

**Settings → Devices & Services → Integration hinzufügen → "VW Group Connect"**

| Feld | Beispiel | Beschreibung |
|---|---|---|
| Marke | `Audi`, `Volkswagen EU`, etc. | Welche Brand-App verwendest du? |
| E-Mail | `du@example.com` | Deine VAG-Account-Email |
| Passwort | `••••••••` | Dein Account-Passwort |
| S-PIN | `1234` *(optional)* | 4-stellige PIN für Lock/Unlock auf manchen Brands |

**Optionen** (Settings → Devices & Services → VW Group Connect → ⋮ → Konfigurieren):

- **Polling-Intervall** (5-60 min) — Default 10 min. Niedriger = aktueller, frisst aber API-Quota schneller.
- **Read-only Modus** — wenn aktiv: nur Status-Sensoren, keine Schalter/Buttons die Befehle senden würden.
- **Reverse-Geocoding** (opt-in) — sendet GPS an OpenStreetMap für Adress-Auflösung.
- **Push-Toggles** (Skoda MQTT / CUPRA-SEAT FCM / Audi-VW FCM) — Lifecycle-Wiring **[NEW v2.0]**, Live-Activation pending Tester.

---

## 🎨 Was du bekommst

### Standard Entitäten pro Vehicle (alle Brands)

**Sensoren**: Battery SoC, Range (electric/combustion/total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power/Rate/Type, Last Trip Stats, **Lifetime Trip Stats [NEW v2.0]**, Charging History, Plug State, Lights Count, Equipment Count, Software Version, Quota Remaining, Connection State, Last Seen, **Driving Score (Skoda) [NEW v2.0]**, **TPMS 4 Corners (Porsche) [NEW v2.0]**, **Last Alarm Timestamp [NEW v2.0]**, **Heater Source (ID.x) [NEW v2.0]**.

**Binary Sensors**: Doors Locked, Doors Open (per door), Windows Open (per window), Trunk/Hood/Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On (per light), Vehicle Online, **Departure-Timer Enabled (3) [NEW v2.0]**, **Alarm Active + Siren Active [NEW v2.0]**, **TPMS Warning (Porsche) [NEW v2.0]**.

**Steuerung**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Window Heating Combined, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto, **Skoda + CUPRA/SEAT [NEW v2.0]**), Departure Timer (1-3 mit `time` platform + **Weekly Preheat [NEW v2.0]**), Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, **Find Charging Stations [NEW v2.0]**.

**Image Platform**: 1-7 Vehicle-Renders pro VIN (Audi/VW: GraphQL MediaService; CUPRA/SEAT: OLA viewPoints; Skoda: Widget + Multi-Angle Composites).

**Device Tracker**: GPS-Position als TrackerEntity (`source_type: gps`) für die HA Lovelace Map.

### Automatisches Vehicle-Bild

Das Auto erscheint als **Device-Picture** in HA, plus als `entity_picture` auf jedem Entity. Custom Lovelace Cards ([Ultra-Vehicle-Card](https://github.com/WJDDesigns/Ultra-Vehicle-Card), [vehicle-info-card](https://github.com/ngocjohn/vehicle-info-card), [Mushroom](https://github.com/piitaya/lovelace-mushroom) Templates) lesen `extra_state_attributes.image_url` automatisch.

---

## 🗺️ Lovelace-Beispiele

### Map Card

```yaml
type: map
title: Fuhrpark
default_zoom: 12
hours_to_show: 24
entities:
  - device_tracker.audi_a4_b9_position
  - device_tracker.vw_golf_7_gte_position
  - zone.home
```

### Picture-Entity Card mit Vehicle-Render

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Charging-Station-Lookup [NEW v2.0]

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

Mehr Beispiele in [`docs/FAQ.md#lovelace-examples`](docs/FAQ.md).

---

## 🔧 Häufige Fragen

| Frage | Antwort |
|---|---|
| **Wann wird mein Auto geweckt?** | Nur bei Service-Calls (Lock/Climate/Wake), niemals bei Status-Polls. Smart-Wake-Cap: max 3 Wakes/Tag pro Auto (Default), 5min Cooldown zwischen Wakes. |
| **Wie viel API-Quota?** | MyCupra/MySeat: ~1500 Calls/Tag. Bei 10min default Polling: ~144 Calls/Tag = 10% Budget. Sensor `requests_remaining_today` zeigt aktuellen Stand. |
| **Was wenn Tank-% bei Golf 7 GTE fehlt?** | v1.25.0 hat MBB VSR Phase 2 read-side fallback. Siehe [Golf 7 GTE Tank-Guide](docs/GOLF_7_GTE_TANK_GUIDE.md). |
| **Token bleibt nach HACS-Update?** | ✅ ja, seit v1.19.2 — Token-Persistence via HA `Store` (kein Re-Login mehr nach Updates). |
| **Wie melde ich Bugs?** | HA → Integration → 🔧 Reparieren → Bug-Report. Diagnostics werden anonymisiert (VINs gemaskt, GPS gerundet, Tokens gestrippt). |
| **„Zu Dashboard hinzufügen" zeigt mein Dashboard / meine Ansicht nicht?** | Häufigste Ursache: dein Dashboard ist im **YAML-Modus** (nur Storage-Mode-Dashboards erscheinen im Picker). Oder die Ansicht existiert noch nicht. Full guide + dedizierte VAG-Connect Lovelace-Karte (BETA): [`docs/dashboards.md`](docs/dashboards.md). |

Vollständige FAQ in [`docs/FAQ.md`](docs/FAQ.md). Dashboard-Troubleshooting + dedizierte Lovelace-Karte (BETA): [`docs/dashboards.md`](docs/dashboards.md).

---

## 🛡️ Privacy & Sicherheit

- **Keine externen Dienste** — alles geht direkt zwischen HA und Manufacturer-API
- **Token-Cache** lokal in HA's `.storage/` (per-config-entry, JSON, automatisch entfernt bei Integration-Removal)
- **Diagnostics anonymisiert**: VINs gemaskt (`***ABC123`), GPS auf 1 Decimal gerundet, Tokens/Passwörter komplett gestrippt
- **Reverse-Geocoding opt-in** — Default deaktiviert
- **VIN-Masking** durchgängig in allen Logs

Details in [`PRIVACY.md`](PRIVACY.md) und [`SECURITY.md`](SECURITY.md).

---

## 🤝 Contributing

PRs willkommen — siehe [`CONTRIBUTING.md`](CONTRIBUTING.md).

**Vehicle Data Scout** (live seit v1.9.0): Wenn deine Integration unbekannte JSON-Felder erkennt, erstellt sie automatisch eine HA Repair-Notification mit pre-filled GitHub-Issue-Link. **1-Klick Bug-Report ohne dass du Code anschauen musst.**

Live-Tester gesucht für die external-blocked Tracks — Comment unter dem entsprechenden Issue mit `Brand + Modell + Jahr + Subscription-Status`.

---

## 📜 Lizenz

[Apache License 2.0](LICENSE) für den Integration-Code; [CC BY-NC-ND 4.0](LICENSE-RESEARCH) für `docs/research/` Inhalte. Siehe auch [`NOTICE.md`](NOTICE.md) für Attributions an Upstream-Projekte ([myskoda](https://github.com/skodaconnect/myskoda), [pycupra](https://github.com/upstream/homeassistant-pycupra), [upstream](https://github.com/upstream/upstream), [volkswagencarnet](https://github.com/Trekky12/volkswagencarnet), [evcc](https://github.com/evcc-io/evcc)).
