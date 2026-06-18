<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant Integration für Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Eine Integration für alle 7 VAG-Marken, direkter API-Zugriff, ohne Middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Lizenz"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
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

> ### 📛 Note on the rename
> Früher veröffentlicht als **`vag-connect-ha`** (VAG = Volkswagen AG, gängige DACH-Abkürzung).
> Stellte sich heraus, dass diese Abkürzung für Englisch-Sprecher *deutlich anders* klingt 😅
>
> **Was unverändert weiterläuft**: alle Entities (z. B. `sensor.audi_q4_battery_soc`),
> alle Service-Calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), alle Automatisierungen,
> die HACS-Installation - **nichts bricht**. Marketing/Anzeigename ändert sich,
> Code-Internals bleiben gleich. Details in [`MIGRATION.md`](MIGRATION.md).
>
> Riesigen Dank an die **Home Assistant UK** und **HA Ideas, Projects and Solutions**
> Communities für den Hinweis - besonders an **Si Gregory**, **Ben Johnson**, und **Evets David**.
>
> Und einen speziellen Gruß an **Jordan Waeles**, dessen `show_vag()` Kommentar jetzt ein offiziell
> unterstütztes Easter Egg in dieser Integration ist (`vag_connect.show_vag` service, siehe CHANGELOG v2.2.3).

---

## What is this? / Überblick

**VW Group Connect is a [Home Assistant](https://www.home-assistant.io) integration for connected-car data and control across all seven Volkswagen Group brands — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche and VW US/Canada — from a single config entry, installable through [HACS](https://hacs.xyz).**

It surfaces battery and charging state, range, odometer, climate, doors/windows and location, and — where the brand's backend still allows it (e.g. Audi) — sends commands such as lock/unlock, climate and charge control. To stay working through Volkswagen's 2026 API changes it speaks several channels and falls back automatically when one is blocked: the brand-native backends, the read-only **EU Data Act** vehicle-data portal, and an opt-in `volkswagen.de` web channel.

Unlike portal-only integrations it also covers **Porsche** (which the EU Data Act portal excludes) and keeps **Audi two-way control**.

> Eine [Home Assistant](https://www.home-assistant.io)-Integration für vernetzte Fahrzeugdaten und -steuerung über alle sieben VW-Konzernmarken (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — eine Integration, mehrere Datenkanäle, automatischer Fallback, Installation über HACS.

---

## Aktuell

VW hat 2026 den direkten Fahrzeug-Zugriff für Dritt-Tools schrittweise dichtgemacht (CARIAD-BFF mit Geräte-Attestation, CUPRA/SEAT-OLA hinter Play Integrity seit Juni 2026). Diese Integration bleibt nutzbar, weil sie **mehrere Kanäle** spricht und automatisch umschaltet, sobald einer blockiert:

- **Marken-eigene Backends** — voller Zugriff inkl. Steuerung, wo verfügbar (Audi, Škoda, Porsche, VW US/CA).
- **EU-Data-Act-Portal** — read-only Fallback für alle Marken (attestation-frei, ~15 min Cadence).
- **volkswagen.de-Web-Kanal (Beta, opt-in)** — zweiter attestation-freier Lesekanal für VW.

Die laufende Arbeit dreht sich um Portal-Robustheit (Timeout-Retry, Daten-Freshness) und Resilienz über die Kanäle.

➡️ Vollständige Versionshistorie: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Wo wir vorne sind

Ehrlicher Stand Mitte 2026: das EU-Data-Act-Portal ist inzwischen der De-facto-Standard-Kanal, viele Integrationen nutzen ihn. Was uns konkret unterscheidet:

| Stärke | Wir | Portal-only-Alternativen |
|---|---|---|
| **Alle 7 Konzernmarken inkl. Porsche** in einer Integration | ✅ | Das EU-Data-Act-Portal **schließt Porsche strukturell aus** — portal-only-Tools können Porsche nie abdecken |
| **Audi Zwei-Wege-Steuerung** (Lock/Klima/Laden, Target-SoC setzen) | ✅ | Portal ist by-design **read-only** |
| **Multi-Channel-Auth mit Auto-Fallback** (Marken-Backend → EU-Data-Act-Portal → opt-in vw.de-Web) | ✅ | meist single-source — ein Portal-Ausfall = Totalausfall |
| **Vehicle Data Scout** — erkennt API-Drift automatisch, generiert 1-Klick-Bug-Reports | ✅ | nichts Vergleichbares |

---

## Wo die Grenzen liegen (ehrlich)

**VW EU und CUPRA/SEAT-OLA sind seit 2026 hinter Geräte-Attestation.** Diese Wand (Google Play Integrity / Firebase App Check) trifft jede Python-basierte VAG-Integration — uns inklusive. Sie ist keine Verzögerung unsererseits, sondern VW-Backend-Politik:

- Das Token-/OLA-Endpoint verlangt ein von der offiziellen App signiertes Attestation-Token, das Python nicht erzeugen kann (das Signing-Key liegt nur im Google/Firebase-Attestation-Service).
- Konsequenz: **VW EU** bekommt kein dauerhaftes `refresh_token` (der OIDC-Hybrid-Flow hält ~2 h), und **CUPRA/SEAT** über OLA bekommen seit ~2026-06-08 `403 "Forbidden device detected"`.

Was wir trotzdem bieten:

1. **EU-Data-Act-Portal** als read-only Fallback für alle Marken (attestation-frei, ~15 min Cadence) — übernimmt automatisch, wenn das native Backend blockt.
2. **volkswagen.de-Web-Kanal (Beta, opt-in)** als zweiter attestation-freier Lesekanal für VW.
3. **OIDC-Hybrid-Flow** für VW EU als read+write-Strategie (mit dem 2h-Re-Login als Preis).

**EU-Data-Act-Deadline 2026-09-12.** Bis dahin muss VW per EU-Verordnung direkten, attestation-freien Owner-Datenzugriff anbieten — die Portal-Feldabdeckung wächst bis dahin voraussichtlich weiter.

Status pro Marke:

| Marke | Steuerung | Daten | Bemerkung |
|---|---|---|---|
| **Audi** | ✅ Zwei-Wege | ✅ voll | myAudi-Backend, keine Attestation-Wand |
| **Škoda** | ✅ Zwei-Wege | ✅ voll | eigenes Škoda-Backend |
| **Porsche** | ✅ Zwei-Wege | ✅ voll | Auth0 + PPA, stabil |
| **VW US/CA** | ✅ Zwei-Wege | ✅ voll | VW-NA-Cloud (Beta) |
| **VW EU** | ⚠️ via OIDC-Hybrid (~2h Re-Login) | ✅ read-only Portal / vw.de-Beta | Backend-attestation-gegated |
| **CUPRA / SEAT** | ❌ OLA blockiert (App Check) | ✅ read-only Portal | seit ~2026-06-08, nicht per Header fixbar |

---

## Was du bekommst

100+ Entitäten über 11 HA-Plattformen, 20+ Service-Calls, native Multi-Vehicle-Support pro Account. Quality-Scale Platinum.

**Sensoren** (pro Vehicle): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source für ID.x, Oil Level Warning, Fahrzeug-Warnungen (Text-Sensor mit allen Backend-Warnings).

**Binary Sensors**: Doors Locked, Doors Open pro Tür, Windows Open pro Fenster, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On pro Light, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Steuerung**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 mit Weekly-Preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform**: 1-7 Vehicle-Renders pro VIN (Audi/VW über GraphQL MediaService, CUPRA/SEAT über OLA viewPoints, Skoda über Widget + Multi-Angle Composites).

**Device Tracker**: GPS-Position als TrackerEntity für die HA Lovelace Map.

---

## Installation

### Option 1: One-Click (empfohlen)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Option 2: HACS Custom Repository

1. HACS → Integrationen → ⋮ → Benutzerdefinierte Repositories
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Kategorie: Integration
4. **VW Group Connect** installieren
5. Home Assistant neu starten

### Option 3: Manuell

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Danach HA neu starten.

---

## Konfiguration

Settings → Devices & Services → Integration hinzufügen → "VW Group Connect"

**Beim ersten Setup wählst du:**

- **Browser-Login** (empfohlen für Audi/Škoda/SEAT/CUPRA): QR-Code scannen oder URL öffnen, kein Passwort in HA gespeichert
- **E-Mail + Passwort** (für VW EU, Porsche, VW US/CA): klassisch mit Brand-ID Credentials

**Optionen** (nach Setup verfügbar):
- Polling-Intervall (5-60 min, Default 10 min)
- Read-only Modus für sichere Automationen ohne versehentliche Befehle
- Reverse-Geocoding opt-in (sendet GPS an OpenStreetMap für Adress-Auflösung)
- Push-Toggles (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) als Foundation, Live-Activation pending

---

## Lovelace-Beispiele

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

### Charging-Station-Lookup

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

Mehr Beispiele in [`docs/FAQ.md`](docs/FAQ.md). Custom Lovelace Cards integrieren automatisch via `extra_state_attributes.image_url`.

---

## Häufige Fragen

| Frage | Antwort |
|---|---|
| Wann wird mein Auto geweckt? | Nur bei Service-Calls (Lock/Climate/Wake), niemals bei Status-Polls. Smart-Wake-Cap: max 3 Wakes/Tag pro Auto, 5min Cooldown. |
| Wie viel API-Quota? | MyCupra/MySeat: ~1500 Calls/Tag. Bei 10min Polling: ~144 Calls/Tag = 10% Budget. Sensor `requests_remaining_today` zeigt Stand. |
| Warum muss ich bei VW EU alle 2h neu einloggen? | VW hat seit 2026-05-27 das Token-Endpoint hinter Google Play Integrity gestellt. Das trifft jede Python-basierte VAG-Integration. EU Data Act 2026-09-12 sollte das beheben. |
| Token bleibt nach HACS-Update? | Ja, seit v1.19.2 via HA Store-Persistenz. |
| Wie melde ich Bugs? | HA → Integration → 🔧 Reparieren → Bug-Report. Diagnostics werden anonymisiert (VINs gemaskt, GPS gerundet, Tokens gestrippt). |
| Feldlabel zeigen Raw-Keys (`brand`, `spin`) nach Update? | Hard browser refresh (Ctrl+Shift+R). HA cached translations client-side. |

Vollständige FAQ in [`docs/FAQ.md`](docs/FAQ.md). Dashboard-Troubleshooting in [`docs/dashboards.md`](docs/dashboards.md).

---

## Privacy & Sicherheit

- Keine externen Dienste, alles direkt zwischen HA und Manufacturer-API
- Token-Cache lokal in HA's `.storage/` (per-config-entry, JSON, automatisch entfernt bei Integration-Removal)
- Diagnostics anonymisiert: VINs gemaskt, GPS auf 1 Decimal gerundet, Tokens und Passwörter komplett gestrippt
- Reverse-Geocoding opt-in, Default deaktiviert
- VIN-Masking durchgängig in allen Logs
- Token-URLs werden im ERROR-Log redacted (v2.7.2+)

Details in [`PRIVACY.md`](PRIVACY.md) und [`SECURITY.md`](SECURITY.md).

---

## Contributing

PRs willkommen, siehe [`CONTRIBUTING.md`](CONTRIBUTING.md). Style-Regeln in [`STYLE.md`](STYLE.md) (Privat in `_private/STYLE.md` für maintainer).

**Vehicle Data Scout** (live seit v1.9.0): Wenn deine Integration unbekannte JSON-Felder erkennt, erstellt sie automatisch eine HA Repair-Notification mit pre-filled GitHub-Issue-Link. 1-Klick Bug-Report ohne Code-Studium.

---

## Lizenz

[Apache License 2.0](LICENSE) für den Integration-Code. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) für `docs/research/` Inhalte. Attributions an upstream open-source Projekte siehe [`NOTICE.md`](NOTICE.md).
