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

## Was ist neu in v2.7.x

**Browser-Login (kein Passwort in HA) für Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant per RFC 8628. QR-Code mit dem Handy scannen oder URL auf irgendeinem Gerät öffnen, Code bestätigen, fertig. Echtes refresh_token vom IDP, keine 2-Stunden-Re-Logins.

**Multi-Strategy Auth Resolver.** Pro Marke bis zu 3 fallback-Strategien (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal Read-only). Eine Strategie tot, Integration läuft auf der nächsten weiter.

**Data Act Portal als Read-only Fallback.** Eigene Implementation des EU Data Act Portal-Logins, integriert als 3rd-tier Strategie. Read-only aber attestation-frei, also unkaputtbar wenn VW den OAuth-Pfad einschränkt.

**Massiv erweiterte Datenpunkte.** Trip-Statistiken (Lebensdauer-Distanz, letzte Fahrt), Ölstand, Reifendruck pro Rad, Türen / Fenster / Sonnendach / Kofferraum pro Position, Außentemperatur auch auf MY24+, Webasto Standheizung, alle Backend-Warnungen (auch markenspezifische wie Audi STO oder Anhängerkupplung).

**Sicherheits-Hardening.** Token-URLs werden im Log nicht mehr roh ausgegeben (sie enthielten JWTs die Email + Access-Token base64-dekodierbar machen). Type-only ERROR, volles Detail nur bei DEBUG.

Voll [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Wo wir vorne sind

Stand 2026-05-31 nach dem 2026-05-27 VW Auth-Wechsel, der die ganze HA-VAG-Integration-Community gleichzeitig getroffen hat:

| Feature | Status hier | Status bei anderen HA-VAG-Integrationen |
|---|---|---|
| **OAuth Device Authorization Grant (QR-Login)** für Audi/Škoda/SEAT/CUPRA | ✅ live in v2.7.0 | Niemand hat das |
| **Multi-Strategy Auth-Fallback Chain** (3 Tiers pro Marke) | ✅ live in v2.6.0 | Niemand |
| **EU Data Act Portal Read-only Tier** als 3rd-tier fallback | ✅ integriert in v2.6.0 | Nur als separate standalone-Integration verfügbar |
| **InvalidURL Safety Net** verhindert Token-Leakage im Log | ✅ live in v2.7.2 | Niemand |
| **Server-side Attestation Gate Watcher** alerted bei VW-Backend-Flag-Flips | ✅ live in v2.7.0 | Niemand |
| **Vehicle Data Scout** auto-detected API-Drift, generiert 1-Klick-Bug-Reports | ✅ live seit v1.9.0 | Niemand vergleichbares |
| **All-7-VAG-Brands in einer Integration** (Audi+VW+Škoda+SEAT+CUPRA+Porsche+VW NA) | ✅ | Andere haben pro Marke ein eigenes Repo |

---

## Wo die Grenzen liegen (ehrlich)

**VW EU ist seit dem 2026-05-27 Backend-Wechsel hart Play-Integrity-gegated.** Diese Wand trifft jede Python-basierte VAG-Integration (uns inklusive). Das ist keine vorübergehende Verzögerung von uns, das ist VW's Backend-Politik:

- Das Token-Endpoint validiert seit der Welle einen `X-Assertion` Header, der ein von Google Play Integrity signiertes JWS Token sein muss
- Python kann diesen Token nicht generieren, weil das Signing-Key nur in Google's mobile-app-attestation Service liegt
- Konsequenz: **VW EU User bekommen kein echtes refresh_token** und werden alle ~2 Stunden auf einen Re-Login zurückgezwungen

Was wir trotzdem für VW EU bieten:

1. **OIDC Hybrid Flow** als primäre Strategie (read+write, aber 2h Re-Login)
2. **EU Data Act Portal** als read-only fallback (15min Cadence, attestation-frei, unkaputtbar)
3. **Attestation-Gate Watcher** der wöchentlich pollt und automatisch ein Issue öffnet sobald VW die Gate öffnet

**EU Data Act 2026-09-12 Compliance-Deadline.** Bis zu diesem Datum muss VW per EU-Verordnung "direkten Datenzugriff für Owner ohne Attestation" anbieten. Unsere `_data_act_portal.py` Implementation ist genau für diesen Tag positioniert.

Status anderer Brands:

| Marke | Auth | refresh_token? | Bemerkung |
|---|---|---|---|
| **Audi** | DAG Browser-Login oder Email+Pwd Hybrid | ✅ ja (via DAG) | Voll funktional |
| **Škoda** | DAG Browser-Login oder Email+Pwd | ✅ ja (via DAG) | Voll funktional |
| **SEAT** | DAG Browser-Login oder OLA | ✅ ja (via DAG) | Voll funktional |
| **CUPRA** | DAG Browser-Login oder OLA | ✅ ja (via DAG) | Voll funktional |
| **VW EU** | OIDC Hybrid Flow oder Data Act Portal | ⚠️ nein, 2h Re-Login | Backend-gegated (siehe oben) |
| **Porsche** | Auth0 + PPA | ✅ ja | Stabil |
| **VW US/CA** | VW NA Cloud | ✅ ja | Beta |

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
