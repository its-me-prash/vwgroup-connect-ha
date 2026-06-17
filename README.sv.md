<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant-integration för Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>En integration för alla 7 VAG-märken, direkt API-åtkomst, utan mellanlager</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Licens"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a>
</p>

---

> ### 📛 Note on the rename
> Tidigare publicerad som **`vag-connect-ha`** (VAG = Volkswagen AG, vanlig DACH-förkortning).
> Det visade sig att förkortningen låter *rätt så annorlunda* för engelsktalande 😅
>
> **Det som rullar vidare oförändrat**: alla entiteter (t.ex. `sensor.audi_q4_battery_soc`),
> alla service-anrop (`vag_connect.lock`, `vag_connect.show_vag` osv.), alla automationer,
> HACS-installationen — **inget går sönder**. Marknadsförings-/visningsnamnet ändras,
> kodens interna delar är desamma. Detaljer i [`MIGRATION.md`](MIGRATION.md).
>
> Stort tack till communityn **Home Assistant UK** och **HA Ideas, Projects and Solutions**
> för tipset — särskilt **Si Gregory**, **Ben Johnson** och **Evets David**.
>
> Och en särskild hälsning till **Jordan Waeles**, vars `show_vag()`-kommentar nu är ett officiellt
> stött easter egg i den här integrationen (`vag_connect.show_vag`-service, se CHANGELOG v2.2.3).

---

## Vad är det här?

**VW Group Connect är en [Home Assistant](https://www.home-assistant.io)-integration för uppkopplad fordonsdata och styrning över alla sju märkena i Volkswagen-koncernen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche och VW US/Canada — från en enda config-entry, installerbar via [HACS](https://hacs.xyz).**

Den visar batteri- och laddningsstatus, räckvidd, vägmätare, klimat, dörrar/fönster och position, och — där märkets backend fortfarande tillåter det (t.ex. Audi) — skickar kommandon som lås/lås upp, klimat- och laddningsstyrning. För att fortsätta fungera genom Volkswagens API-ändringar 2026 talar den flera kanaler och faller automatiskt tillbaka när en blockeras: de märkesegna backendarna, den läs-bara fordonsdata-portalen enligt **EU Data Act**, och en opt-in-webbkanal via `volkswagen.de`.

Till skillnad från portal-bara integrationer täcker den dessutom **Porsche** (som EU Data Act-portalen utesluter) och behåller **tvåvägsstyrning för Audi**.

> En [Home Assistant](https://www.home-assistant.io)-integration för uppkopplad fordonsdata och -styrning över alla sju VW-koncernmärken (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — en integration, flera datakanaler, automatisk fallback, installation via HACS.

---

## Aktuellt

VW har under 2026 steg för steg stängt direktåtkomsten för tredjepartsverktyg (CARIAD-BFF med enhets-attestation, CUPRA/SEAT-OLA bakom Play Integrity sedan juni 2026). Den här integrationen förblir användbar eftersom den talar **flera kanaler** och växlar automatiskt så fort en blockeras:

- **Märkesegna backendar** — full åtkomst inkl. styrning, där det är möjligt (Audi, Škoda, Porsche, VW US/CA).
- **EU Data Act-portal** — läs-bar fallback för alla märken (attestationsfri, ~15 min kadens).
- **volkswagen.de-webbkanal (Beta, opt-in)** — andra attestationsfria läskanal för VW.

Det pågående arbetet handlar om portal-robusthet (timeout-retry, dataaktualitet) och resiliens över kanalerna.

➡️ Fullständig versionshistorik: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Var vi leder

Ärligt läge i mitten av 2026: EU Data Act-portalen har nu blivit den de facto standardkanalen, och många integrationer använder den. Det som konkret skiljer oss:

| Styrka | Vi | Portal-bara alternativ |
|---|---|---|
| **Alla 7 koncernmärken inkl. Porsche** i en integration | ✅ | EU Data Act-portalen **utesluter Porsche strukturellt** — portal-bara verktyg kan aldrig täcka Porsche |
| **Tvåvägsstyrning för Audi** (lås/klimat/laddning, sätta target-SoC) | ✅ | Portalen är by-design **läs-bar** |
| **Multi-channel-auth med auto-fallback** (märkes-backend → EU Data Act-portal → opt-in vw.de-webb) | ✅ | oftast single-source — ett portalavbrott = totalavbrott |
| **Vehicle Data Scout** — upptäcker API-drift automatiskt, genererar 1-klicks bug-rapporter | ✅ | inget jämförbart |

---

## Var gränserna går (ärligt)

**VW EU och CUPRA/SEAT-OLA ligger sedan 2026 bakom enhets-attestation.** Den här muren (Google Play Integrity / Firebase App Check) drabbar varje Python-baserad VAG-integration — vår inräknad. Det är ingen fördröjning från vår sida, utan VW:s backend-politik:

- Token-/OLA-endpointen kräver en attestation-token signerad av den officiella appen, som Python inte kan generera (signeringsnyckeln finns endast i Googles/Firebases attestation-tjänst).
- Konsekvens: **VW EU** får ingen varaktig `refresh_token` (OIDC-hybrid-flödet håller ~2 h), och **CUPRA/SEAT** via OLA får sedan ~2026-06-08 `403 "Forbidden device detected"`.

Vad vi ändå erbjuder:

1. **EU Data Act-portal** som läs-bar fallback för alla märken (attestationsfri, ~15 min kadens) — tar automatiskt över när den nativa backenden blockerar.
2. **volkswagen.de-webbkanal (Beta, opt-in)** som andra attestationsfria läskanal för VW.
3. **OIDC-hybrid-flöde** för VW EU som läs+skriv-strategi (med 2h-ominloggningen som pris).

**EU Data Act-deadline 2026-09-12.** Senast då måste VW enligt EU-förordning erbjuda direkt, attestationsfri ägardataåtkomst — portalens fälttäckning väntas växa vidare fram till dess.

Status per märke:

| Märke | Styrning | Data | Anmärkning |
|---|---|---|---|
| **Audi** | ✅ Tvåvägs | ✅ full | myAudi-backend, ingen attestation-mur |
| **Škoda** | ✅ Tvåvägs | ✅ full | egen Škoda-backend |
| **Porsche** | ✅ Tvåvägs | ✅ full | Auth0 + PPA, stabil |
| **VW US/CA** | ✅ Tvåvägs | ✅ full | VW-NA-cloud (Beta) |
| **VW EU** | ⚠️ via OIDC-hybrid (~2h ominloggning) | ✅ läs-bar portal / vw.de-beta | Backend-attestations-gateat |
| **CUPRA / SEAT** | ❌ OLA blockerad (App Check) | ✅ läs-bar portal | sedan ~2026-06-08, inte fixbart via header |

---

## Vad du får

100+ entiteter över 11 HA-plattformar, 20+ service-anrop, native multi-vehicle-stöd per konto. Quality-Scale Platinum.

**Sensorer** (per fordon): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source för ID.x, Oil Level Warning, fordonsvarningar (textsensor med alla backend-warnings).

**Binary Sensors**: Doors Locked, Doors Open per dörr, Windows Open per fönster, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On per light, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Styrning**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 med Weekly-Preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform**: 1-7 fordonsrenders per VIN (Audi/VW via GraphQL MediaService, CUPRA/SEAT via OLA viewPoints, Skoda via Widget + Multi-Angle-kompositer).

**Device Tracker**: GPS-position som TrackerEntity för HA Lovelace-kartan.

---

## Installation

### Alternativ 1: One-Click (rekommenderas)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Alternativ 2: HACS Custom Repository

1. HACS → Integrationer → ⋮ → Anpassade förråd
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Kategori: Integration
4. Installera **VW Group Connect**
5. Starta om Home Assistant

### Alternativ 3: Manuellt

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Starta sedan om HA.

---

## Konfiguration

Inställningar → Enheter & Tjänster → Lägg till integration → "VW Group Connect"

**Vid första setup väljer du:**

- **Browser-Login** (rekommenderas för Audi/Škoda/SEAT/CUPRA): skanna QR-kod eller öppna URL, inget lösenord sparas i HA
- **E-post + lösenord** (för VW EU, Porsche, VW US/CA): klassiskt med Brand-ID-credentials

**Alternativ** (tillgängliga efter setup):
- Polling-intervall (5-60 min, standard 10 min)
- Read-only-läge för säkra automationer utan oavsiktliga kommandon
- Reverse-geocoding opt-in (skickar GPS till OpenStreetMap för adressuppslag)
- Push-toggles (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) som grund, live-aktivering pending

---

## Lovelace-exempel

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

### Picture-Entity-kort med fordonsrender

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

Fler exempel i [`docs/FAQ.md`](docs/FAQ.md). Egna Lovelace-kort integreras automatiskt via `extra_state_attributes.image_url`.

---

## Vanliga frågor

| Fråga | Svar |
|---|---|
| När väcks min bil? | Bara vid service-anrop (Lock/Climate/Wake), aldrig vid status-polls. Smart-Wake-cap: max 3 wakes/dag per bil, 5 min cooldown. |
| Hur mycket API-quota? | MyCupra/MySeat: ~1500 calls/dag. Vid 10 min polling: ~144 calls/dag = 10% av budgeten. Sensorn `requests_remaining_today` visar läget. |
| Varför måste jag logga in på nytt var 2:e timme för VW EU? | VW har sedan 2026-05-27 lagt token-endpointen bakom Google Play Integrity. Det drabbar varje Python-baserad VAG-integration. EU Data Act 2026-09-12 bör åtgärda det. |
| Behålls token efter HACS-uppdatering? | Ja, sedan v1.19.2 via HA Store-persistens. |
| Hur rapporterar jag buggar? | HA → Integration → 🔧 Reparera → Bug-Report. Diagnostics anonymiseras (VIN maskeras, GPS avrundas, tokens stripas). |
| Fältetiketter visar raw-keys (`brand`, `spin`) efter uppdatering? | Hård browser-refresh (Ctrl+Shift+R). HA cachar översättningar client-side. |

Fullständig FAQ i [`docs/FAQ.md`](docs/FAQ.md). Dashboard-felsökning i [`docs/dashboards.md`](docs/dashboards.md).

---

## Integritet & säkerhet

- Inga externa tjänster, allt direkt mellan HA och tillverkar-API
- Token-cache lokalt i HA:s `.storage/` (per config-entry, JSON, tas automatiskt bort när integrationen avlägsnas)
- Diagnostics anonymiseras: VIN maskeras, GPS avrundas till 1 decimal, tokens och lösenord stripas helt
- Reverse-geocoding opt-in, avstängt som standard
- VIN-maskering genomgående i alla loggar
- Token-URL:er redactas i ERROR-loggen (v2.7.2+)

Detaljer i [`PRIVACY.md`](PRIVACY.md) och [`SECURITY.md`](SECURITY.md).

---

## Contributing

PR:er välkomnas, se [`CONTRIBUTING.md`](CONTRIBUTING.md). Style-regler i [`STYLE.md`](STYLE.md) (privat i `_private/STYLE.md` för maintainers).

**Vehicle Data Scout** (live sedan v1.9.0): När din integration upptäcker okända JSON-fält skapar den automatiskt en HA Repair-notifikation med en förifylld GitHub-issue-länk. 1-klicks bug-rapport utan att studera kod.

---

## Licens

[Apache License 2.0](LICENSE) för integrationskoden. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) för innehållet i `docs/research/`. Attributioner till upstream open source-projekt, se [`NOTICE.md`](NOTICE.md).
