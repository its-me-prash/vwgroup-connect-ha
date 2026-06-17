<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant-integratie voor Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Eén integratie voor alle 7 VAG-merken, directe API-toegang, zonder middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Licentie"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Eerder gepubliceerd als **`vag-connect-ha`** (VAG = Volkswagen AG, gangbare DACH-afkorting).
> Bleek dat die afkorting voor Engelstaligen *behoorlijk anders* klinkt 😅
>
> **Wat ongewijzigd blijft werken**: alle entities (bijv. `sensor.audi_q4_battery_soc`),
> alle service-calls (`vag_connect.lock`, `vag_connect.show_vag` enz.), alle automatiseringen,
> de HACS-installatie — **er breekt niets**. Marketing-/weergavenaam verandert,
> code-internals blijven gelijk. Details in [`MIGRATION.md`](MIGRATION.md).
>
> Enorme dank aan de **Home Assistant UK**- en **HA Ideas, Projects and Solutions**-
> communities voor de tip — in het bijzonder **Si Gregory**, **Ben Johnson** en **Evets David**.
>
> En een speciale shoutout naar **Jordan Waeles**, wiens `show_vag()`-comment nu een officieel
> ondersteund easter egg in deze integratie is (`vag_connect.show_vag`-service, zie CHANGELOG v2.2.3).

---

## Wat is dit? / Overzicht

**VW Group Connect is een [Home Assistant](https://www.home-assistant.io)-integratie voor connected-car-data en -besturing over alle zeven merken van de Volkswagen Group — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche en VW US/Canada — vanuit één config entry, te installeren via [HACS](https://hacs.xyz).**

Ze toont accu- en laadstatus, actieradius, kilometerstand, klimaat, deuren/ramen en locatie, en — waar de backend van het merk het nog toestaat (bijv. Audi) — stuurt commando's zoals vergrendelen/ontgrendelen, klimaat- en laadbesturing. Om door de API-wijzigingen van Volkswagen in 2026 heen te blijven werken spreekt ze meerdere kanalen en valt automatisch terug zodra er één geblokkeerd wordt: de merk-eigen backends, het alleen-lezen **EU Data Act**-portaal voor voertuigdata en een opt-in `volkswagen.de`-webkanaal.

Anders dan portal-only-integraties dekt ze ook **Porsche** (dat het EU-Data-Act-portaal uitsluit) en behoudt ze **Audi tweerichtingsbesturing**.

> Een [Home Assistant](https://www.home-assistant.io)-integratie voor connected voertuigdata en -besturing over alle zeven VW-concernmerken (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — één integratie, meerdere datakanalen, automatische fallback, installatie via HACS.

---

## Actueel

VW heeft in 2026 stapsgewijs de directe voertuigtoegang voor third-party-tools dichtgezet (CARIAD-BFF met device-attestation, CUPRA/SEAT-OLA achter Play Integrity sinds juni 2026). Deze integratie blijft bruikbaar omdat ze **meerdere kanalen** spreekt en automatisch omschakelt zodra er één blokkeert:

- **Merk-eigen backends** — volledige toegang incl. besturing, waar beschikbaar (Audi, Škoda, Porsche, VW US/CA).
- **EU-Data-Act-portaal** — alleen-lezen fallback voor alle merken (attestation-vrij, ~15 min cadens).
- **volkswagen.de-webkanaal (Beta, opt-in)** — tweede attestation-vrij leeskanaal voor VW.

Het lopende werk draait om robuustheid van het portaal (timeout-retry, data-freshness) en veerkracht over de kanalen heen.

➡️ Volledige versiehistorie: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Waar wij voorop lopen

Eerlijke stand medio 2026: het EU-Data-Act-portaal is inmiddels het de-facto standaardkanaal, veel integraties gebruiken het. Wat ons concreet onderscheidt:

| Kracht | Wij | Portal-only-alternatieven |
|---|---|---|
| **Alle 7 concernmerken incl. Porsche** in één integratie | ✅ | Het EU-Data-Act-portaal **sluit Porsche structureel uit** — portal-only-tools kunnen Porsche nooit dekken |
| **Audi tweerichtingsbesturing** (vergrendelen/klimaat/laden, target-SoC instellen) | ✅ | Portaal is by-design **alleen-lezen** |
| **Multi-channel-auth met auto-fallback** (merk-backend → EU-Data-Act-portaal → opt-in vw.de-web) | ✅ | meestal single-source — één portaal-uitval = totale uitval |
| **Vehicle Data Scout** — detecteert API-drift automatisch, genereert 1-klik-bugrapporten | ✅ | niets vergelijkbaars |

---

## Waar de grenzen liggen (eerlijk)

**VW EU en CUPRA/SEAT-OLA zitten sinds 2026 achter device-attestation.** Deze muur (Google Play Integrity / Firebase App Check) raakt elke Python-gebaseerde VAG-integratie — onze inbegrepen. Het is geen vertraging aan onze kant, maar VW-backend-beleid:

- Het token-/OLA-endpoint verlangt een door de officiële app ondertekend attestation-token dat Python niet kan genereren (de signing-key ligt alleen in de Google/Firebase-attestation-service).
- Gevolg: **VW EU** krijgt geen blijvend `refresh_token` (de OIDC-hybrid-flow houdt ~2 u), en **CUPRA/SEAT** via OLA krijgen sinds ~2026-06-08 `403 "Forbidden device detected"`.

Wat we desondanks bieden:

1. **EU-Data-Act-portaal** als alleen-lezen fallback voor alle merken (attestation-vrij, ~15 min cadens) — neemt automatisch over wanneer de native backend blokkeert.
2. **volkswagen.de-webkanaal (Beta, opt-in)** als tweede attestation-vrij leeskanaal voor VW.
3. **OIDC-hybrid-flow** voor VW EU als lees+schrijf-strategie (met de 2u-herlogin als prijs).

**EU-Data-Act-deadline 2026-09-12.** Tegen die datum moet VW per EU-verordening directe, attestation-vrije eigenaars-datatoegang bieden — de veldafdekking van het portaal groeit tot dan naar verwachting verder.

Status per merk:

| Merk | Besturing | Data | Opmerking |
|---|---|---|---|
| **Audi** | ✅ Tweerichting | ✅ volledig | myAudi-backend, geen attestation-muur |
| **Škoda** | ✅ Tweerichting | ✅ volledig | eigen Škoda-backend |
| **Porsche** | ✅ Tweerichting | ✅ volledig | Auth0 + PPA, stabiel |
| **VW US/CA** | ✅ Tweerichting | ✅ volledig | VW-NA-cloud (Beta) |
| **VW EU** | ⚠️ via OIDC-hybrid (~2u herlogin) | ✅ alleen-lezen portaal / vw.de-Beta | backend-attestation-gegated |
| **CUPRA / SEAT** | ❌ OLA geblokkeerd (App Check) | ✅ alleen-lezen portaal | sinds ~2026-06-08, niet via header fixbaar |

---

## Wat je krijgt

100+ entities over 11 HA-platforms, 20+ service-calls, native multi-vehicle-support per account. Quality-Scale Platinum.

**Sensoren** (per voertuig): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source voor ID.x, Oil Level Warning, voertuigwaarschuwingen (tekst-sensor met alle backend-warnings).

**Binary Sensors**: Doors Locked, Doors Open per deur, Windows Open per raam, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On per light, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Besturing**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 met Weekly-Preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform**: 1-7 vehicle-renders per VIN (Audi/VW via GraphQL MediaService, CUPRA/SEAT via OLA viewPoints, Skoda via Widget + Multi-Angle Composites).

**Device Tracker**: GPS-positie als TrackerEntity voor de HA Lovelace-map.

---

## Installatie

### Optie 1: One-Click (aanbevolen)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Optie 2: HACS Custom Repository

1. HACS → Integraties → ⋮ → Aangepaste opslagplaatsen
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Categorie: Integratie
4. **VW Group Connect** installeren
5. Home Assistant opnieuw opstarten

### Optie 3: Handmatig

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Daarna HA opnieuw opstarten.

---

## Configuratie

Instellingen → Apparaten en diensten → Integratie toevoegen → "VW Group Connect"

**Bij de eerste setup kies je:**

- **Browser-Login** (aanbevolen voor Audi/Škoda/SEAT/CUPRA): QR-code scannen of URL openen, geen wachtwoord opgeslagen in HA
- **E-mail + wachtwoord** (voor VW EU, Porsche, VW US/CA): klassiek met Brand-ID-credentials

**Opties** (beschikbaar na setup):
- Polling-interval (5-60 min, standaard 10 min)
- Alleen-lezen modus voor veilige automatiseringen zonder ongewilde commando's
- Reverse-geocoding opt-in (stuurt GPS naar OpenStreetMap voor adres-resolutie)
- Push-toggles (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) als basis, live-activering pending

---

## Lovelace-voorbeelden

### Map Card

```yaml
type: map
title: Wagenpark
default_zoom: 12
hours_to_show: 24
entities:
  - device_tracker.audi_a4_b9_position
  - device_tracker.vw_golf_7_gte_position
  - zone.home
```

### Picture-Entity Card met vehicle-render

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

Meer voorbeelden in [`docs/FAQ.md`](docs/FAQ.md). Custom Lovelace-kaarten integreren automatisch via `extra_state_attributes.image_url`.

---

## Veelgestelde vragen

| Vraag | Antwoord |
|---|---|
| Wanneer wordt mijn auto gewekt? | Alleen bij service-calls (Lock/Climate/Wake), nooit bij status-polls. Smart-Wake-cap: max 3 wakes/dag per auto, 5min cooldown. |
| Hoeveel API-quota? | MyCupra/MySeat: ~1500 calls/dag. Bij 10min polling: ~144 calls/dag = 10% budget. Sensor `requests_remaining_today` toont de stand. |
| Waarom moet ik bij VW EU elke 2u opnieuw inloggen? | VW heeft sinds 2026-05-27 het token-endpoint achter Google Play Integrity gezet. Dat raakt elke Python-gebaseerde VAG-integratie. EU Data Act 2026-09-12 zou dit moeten oplossen. |
| Blijft het token na een HACS-update? | Ja, sinds v1.19.2 via HA Store-persistentie. |
| Hoe meld ik bugs? | HA → Integratie → 🔧 Repareren → Bug-Report. Diagnostics worden geanonimiseerd (VINs gemaskeerd, GPS afgerond, tokens gestript). |
| Veldlabels tonen raw keys (`brand`, `spin`) na een update? | Hard browser refresh (Ctrl+Shift+R). HA cachet vertalingen client-side. |

Volledige FAQ in [`docs/FAQ.md`](docs/FAQ.md). Dashboard-troubleshooting in [`docs/dashboards.md`](docs/dashboards.md).

---

## Privacy & beveiliging

- Geen externe diensten, alles rechtstreeks tussen HA en de manufacturer-API
- Token-cache lokaal in HA's `.storage/` (per-config-entry, JSON, automatisch verwijderd bij integratie-removal)
- Diagnostics geanonimiseerd: VINs gemaskeerd, GPS afgerond op 1 decimaal, tokens en wachtwoorden volledig gestript
- Reverse-geocoding opt-in, standaard uitgeschakeld
- VIN-masking doorlopend in alle logs
- Token-URLs worden in de ERROR-log geredacteerd (v2.7.2+)

Details in [`PRIVACY.md`](PRIVACY.md) en [`SECURITY.md`](SECURITY.md).

---

## Contributing

PRs welkom, zie [`CONTRIBUTING.md`](CONTRIBUTING.md). Style-regels in [`STYLE.md`](STYLE.md) (privé in `_private/STYLE.md` voor maintainers).

**Vehicle Data Scout** (live sinds v1.9.0): wanneer je integratie onbekende JSON-velden detecteert, maakt ze automatisch een HA Repair-notificatie aan met een vooringevulde GitHub-issue-link. 1-klik bug-report zonder code te bestuderen.

---

## Licentie

[Apache License 2.0](LICENSE) voor de integratie-code. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) voor de inhoud van `docs/research/`. Attributies aan upstream open-source projecten zie [`NOTICE.md`](NOTICE.md).
