<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant Integration för Audi · VW · Škoda · SEAT · CUPRA</strong>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?style=for-the-badge"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/downloads/its-me-prash/vwgroup-connect-ha/total?style=for-the-badge&label=Downloads" alt="Downloads"></a>
  <a href="../custom_components/vag_connect/quality_scale.yaml"><img src="https://img.shields.io/badge/Quality%20Scale-Platinum%20%F0%9F%8F%86-gold?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="../README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.es.md">Español</a> ·
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


## Nytt i v2.10.0

Den största releasen av denna integration hittills. Runt 6 veckors intensivt arbete i en enda cut.

- **Fix för VW EU Auth0 SPA-login (#388)**: VW migrerade lösenordssidan till en full-SPA-mall runt 2026-05-31. JSON Content-Type retry mot `/u/login` plus skärpt consent-detektion låser upp användare på classic-auth.
- **Parser-paritet över varumärken**: VW EU Group A (10 nya fält - 12V, aktiv ventilation, bakre takfönster, cabriolet-suff, totaler per-resa), SEAT/CUPRA Group B (6 OLA-endpoints - warning-lights v3, inställbar battery-care, charging-statistics, föredragen verkstad), VW NA Group C (4 endpoints - migration till `data.exteriorStatus.*`, fixar "allt-null"-symptomet på ID.4 US 2023 #322).
- **VW kontolås-detektion** med guidad Repairs issue + auto-clear.
- **Scout Policy-tvång**: varje silenced JSON-väg måste också parsas till en entity, eller bära ett explicit T2-T5 exemption-kommentar. Stänger #384, #389.
- **Provenance canaries + veckovis watcher** + härdning (SPDX, Bruno drift-gate, mypy strict).

Resten från v2.7-v2.9 fortfarande live: Browser-Login DAG, multi-strategy auth, Data Act Portal, MFA, FCM push, Standheizung, brake-service, parser telemetry.

Full [CHANGELOG](CHANGELOG.md#2100---2026-06-02).

## Nytt i v2.7.x

**Browser-inloggning (inget lösenord lagras i HA) för Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant enligt RFC 8628. Skanna en QR-kod med telefonen eller öppna URL:en på vilken enhet som helst, bekräfta en kort kod, klar. Riktig refresh_token, ingen om-inloggning varannan timme.

**Multi-strategi auth-resolver.** Upp till tre fallback-strategier per märke (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal endast läs). En strategi dör, integrationen kör vidare på nästa.

**Data Act Portal som fallback endast läs.** Egen implementation av EU Data Act portal-login, integrerad som 3:e-tiers-strategi. Endast läs men utan attestation, alltså obrytbar när VW skärper OAuth-vägen.

**Många fler datapunkter.** Resstatistik (livstidsavstånd, sista resan), oljenivå, däcktryck per hjul, dörrar / fönster / soltak / baklucka per position, utomhustemperatur på MY24+, Webasto motorvärmare, alla tillverkarvarningar inklusive märkesspecifika som Audi STO.

Se [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Var vi leder

Status per 2026-05-31, efter VW backend-ändringen 2026-05-27 som drabbade hela HA-VAG-integrations-communityt samtidigt:

| Funktion | Status här | Status hos andra |
|---|---|---|
| OAuth Device Authorization Grant (QR-Login) för Audi/Škoda/SEAT/CUPRA | ✅ sedan v2.7.0 | Ingen |
| Multi-strategi auth-fallback-kedja (3 tiers per märke) | ✅ sedan v2.6.0 | Ingen |
| EU Data Act-portal endast läs som 3:e-tiers fallback | ✅ sedan v2.6.0 | Endast som separat integration |
| InvalidURL säkerhetsnät mot token-läckage i loggar | ✅ sedan v2.7.2 | Ingen |
| Server-side attestation gate watcher | ✅ sedan v2.7.0 | Ingen |
| Vehicle Data Scout, auto-detektion av API-drift | ✅ sedan v1.9.0 | Inget jämförbart |
| Alla 7 VAG-märken i en integration | ✅ | Andra projekt har en repo per märke |

---

## Var gränserna går (ärligt)

**VW EU är hårt Play-Integrity-låst sedan backend-ändringen 2026-05-27.** Denna mur drabbar varje Python-baserad VAG-integration (vår inräknad). Det är inte en tillfällig fördröjning från vår sida, det är VW:s backend-politik:

- Token-endpoint validerar en `X-Assertion` header som måste vara en JWS-token signerad av Google Play Integrity
- Python kan inte generera den här token, signeringsnyckeln finns endast i Googles mobile-app attestation-tjänst
- Konsekvens: VW EU-användare får ingen riktig refresh_token och tvingas in i om-inloggning var ~2:e timme

Vad vi ändå erbjuder för VW EU: OIDC Hybrid Flow som primär strategi (läs + skriv, 2h re-login), EU Data Act-portal som fallback endast läs (15-min kadens, utan attestation), veckovis watcher som automatiskt öppnar ett ärende när VW öppnar grinden.

**EU Data Act 2026-09-12 compliance-deadline.** Vid det datumet måste VW lagligen erbjuda direkt fordonsdata-åtkomst till ägare utan attestation-gating. Vår `_data_act_portal.py` är positionerad för den dagen.

## ✨ v2.0.0 Big-Bang Highlights — also available in English

> The detailed v2.0.0 highlights table + "What makes us unique" USP section
> are maintained in English on the German + English READMEs. They are
> provided here as the canonical source so non-DE/EN readers can still
> see all v2.0 features with `` markers without waiting on
> 6 parallel translations.

### Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | 3 pure-read enabled-sensors |
| **Weekly Preheat (`recurring_on`)** | Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | `vag_connect.find_charging_stations` service |
| **Vehicle Alarm sensors** | closes issue #33 |
| **heaterSource sensor** | closes issue #163 |
| **Push Manager Lifecycle Wiring** | Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | Drop-in `system_health.py` |
| **Quality Scale Platinum** | Re-introduced after v1.26.x revert |
| **DeviceInfo `configuration_url` + `suggested_area`** | Brand-aware "Open in App" button |

### What makes us unique

- **Native coverage of all 7 VAG brands** in a single integration
- **Direct manufacturer-API access** without middleware / Docker / 3rd service
- **Vehicle Data Scout** — automatic JSON-field drift detection with Repair notification + 1-click GitHub issue
- **Capability-Filter Phase 3** — phantom entities suppressed before spawn
- **Per-VIN wakeup cap + cooldown** — protects 12V battery
- **Auth Resilience One-Click Repair** — reauth flow from Repairs panel
- **System Health Panel** — at-a-glance push channel status, API quota, last poll
- **Bruno-CI Stage 2** — strict URL-drift check
- **Token persistence across HA updates** — no re-login after HACS updates since v1.19.2
- **Diagnostics anonymisation by default** — VINs, GPS, tokens stripped before export


Jag ville styra min Audi i Home Assistant — fullständigt. Så jag byggde detta.

**VW Group Connect** är en fristående Home Assistant-integration för alla VAG-märken. Inga externa beroenden, ingen Docker, inga externa tjänster.

Från v0.14.1 kommunicerar integrationen **direkt** med CARIAD API — egen async-klient, helt fristående. Cloud-polling-arkitektur, 80+ entiteter över 10 plattformar, 14 tjänster.

> ✅ **Aktivt underhållen multi-märkes-efterträdare** till [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (arkiverat 2025-10-29) och [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (deprecated 2025-03-14). En integration för Audi, VW, Škoda, SEAT, CUPRA, Porsche och VW US/CA — ingen separat plugin per märke.

## Nuvarande status och ärliga begränsningar / Current Status & Honest Limits (v1.12.3)

VW Group Connect utvecklas aktivt vidare. Så att du vet vad som fungerar och vad som kommer:

### ✅ Vad som fungerar NU (alla 7 märken)

**🛰️ 1-klick bug rapporter & feature-önskemål (LIVE sedan v1.9.0)**

Två diagnostiska sensorer med en gemensam reporter pipeline — **första riktiga live-validering av community-användare** i v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) och v1.12.3 (DnnsJp74 / Audi):

- 🔬 **Vehicle Data Scout** — upptäcker automatiskt okända JSON-fält i din bils API. Märkes-lokaliserad på 8 språk (DE: API-Beobachter, FR: Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer av de senaste 20 integrationsfelen med anonymiserad kontext (modell, firmware, stack trace).
- 🔘 **Reporter Pipeline:** båda sensorerna skapar automatiskt HA Repair-notifikationer med ett förifyllt GitHub-Issue som 1-klicks länk. Plus en diagnostics-nedladdning med allt maskerat för forum/Facebook.
- 🔒 **Integritetslöfte:** Inget lämnar din HA utan din explicita klick. VIN maskerade, GPS avrundad till 1 decimal, JWT/UUID/e-post borttagna. GDPR-compliant.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Sensor `connection_state` (online / standby / offline) för Audi, VW EU, Škoda, SEAT, CUPRA — första VAG-integration med centraliserad anslutningsstatus. Brand-agnostisk helper `compute_connection_state` med rekursiv `carCapturedTimestamp` walk.

**🔋 12V-batteri-övervakning + Smart-Wake (v1.12.0)**

- Sensor `voltage_12v` (V) + binary `warning_12v_low` vid <11.5V — förhindrar tysta API-avbrott orsakade av tomt startbatteri
- Sensor `wake_count_today` + soft-cap på 3 wakes/dag (`_WAKE_BUDGET_PER_DAY`) skyddar 12V mot wake-loops, höjer `wake_budget_exhausted` INNAN API-anrop

**💨 Optimistisk UI för Lock/Climate/Charging (v1.11.1)**

Switches växlar omedelbart vid klick (myskoda PR #832 mönster), API-roundtrip i bakgrunden. Vid misslyckande: revert + ServiceValidationError. 8 actuator-metoder migrerade.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up i v1.11.1)**

Tre explicita räckviddssensorer: `electric_range_km`, `combustion_range_km`, `total_range_km`. VW EU/Audi-parser klassificerar efter motortyp (4 källor istället för 2). Audi-diesel-fallback från `measurements.rangeStatus.value.dieselRange`. Verifierat via evcc-io/evcc#19045 + Audi Q4 sample + CarConnectivity-loggar.

**🔒 Read-only-läge Fas 1 (v1.12.0)**

Options-toggle "Read-only Mode" → hoppa över lock/switch/button(non-refresh)/climate/number-plattformar för privacy/safety-konservativa ägare. Sensors + binary_sensors + device_tracker stannar.

**⚡ Skrivbar Max-Charge-Current Number (v1.12.0)**

Slider 6-32A istället för bara en read-only-sensor. Ny `command_set_max_charge_current` POST chargingSettings.

**💡 Per-Light Binary-Sensors (v1.12.0)**

Dynamiskt per ljustyp från `lights_individual` dict + aggregat `lights_on` + `lights_count`.

**🛠️ Defensiv stabilitet (v1.8.7 + v1.10.1)**

- 504-retry, transient-network-error retry, 6h stale-cache + 3-failure tolerance
- Token-refresh-storm-skydd (max 3/h) — förhindrar IP-bans
- Helpers `safe_int` / `safe_float` / `safe_enum` — tolererar backend-quirks

**🚪 CUPRA Born 2026 Firmware-Shapes (v1.10.2 — Gerhards #53 första live-validering)**

Field-name fallback-kedja: `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Lowercase enum tolerance för `"connected"` / `"locked"`. Bakåtkompatibilitet bevarad.

**🔓 Lock + Wake för Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` skickar nu S-PIN för Audi/VW (CARIAD BFF svarade `403 spin_error`). `command_wake` använder v1→v2 fallback.

**🛡️ Capability-Filter Fas 2 (v1.9.1, #56)**

Body-sniffing `classify_command_failure` för `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error` markörer. `_cariad_cmd` skriver varje resultat till FeatureState. Command-bundna entiteter (Lock/Climate/Switch/Buttons) går automatiskt unavailable vid definitivt "nej" från backend.

### ⚠️ Fortfarande pågår / What's still in progress (planerade sessioner)

- **v1.13.0 MINOR** — Anonymized Diagnostics-Export (#62) + Capability-Filter Fas 3 (`capability.active && user-enabled` PRE-entity-creation, döljer knappar som MyCupra-appen) + Read-only Fas 2/3 (Command-Locking + cloud_refresh vs wake_vehicle service-separation).
- **v1.14.0 MINOR** — Trip Statistics från Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), Climate-Timer UI (#26).
- **v1.16.0 MINOR** — Platsspecifik laddmål-SoC + laddprofiler (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, upstream #717-mönster).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) för realtidsuppdateringar utan polling (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-tester alla märken + EU Data Act ready (pycupra `EUDAConnection` som referens, deadline september 2026) (#13, #59).

### 🚫 Medvetna begränsningar / Conscious limits

- **Image-plattform:** inget officiellt CARIAD render-image API existerar. Image-entiteten kommer i en framtida release att gå över till användar-tillhandahållna URL:er.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — ny E³ 1.2-arkitektur, ännu inte offentligt reverse-engineered (varken i upstream eller CarConnectivity). VW Group Connect upptäcker dessa fordon och gör **graceful degradation** istället för 404-fel.
- **Ford / icke-VAG-märken:** utanför scope — se [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) för Ford.

### 🔧 Integritetskrav

För att GPS-position, fordonsstatus och kupévärmare ska fungera måste **"Dela min position"** vara aktiverat i din My-VW / My-Audi / MySkoda / MyCupra-app — annars svarar backend med 403.

### 📚 Mer info / More info

- 🗺️ Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md) — komplett P0/P1/P2/P3-prioritering av alla öppna issues
- 📜 Tech Changelog: [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — per release: field-mappings + arkitekturbeslut + externa source-refs
- 🎨 Dashboards-guide + Lovelace-kort BETA: [`docs/dashboards.md`](docs/dashboards.md) — "Lägg till på instrumentpanel" felsökning + dedikerat Lovelace-kort (BETA)
- 🤝 Session Handoff (för bidragsgivare och AI-verktyg): [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Integritets- och datahanteringsregler: sektion [`CONTRIBUTING.md`](CONTRIBUTING.md) (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / `missing-capability` diagnos: FAQ-sektion i [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Stödda Märken

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA:** Båda märkena har varit tillgängliga som Beta sedan v1.0.0. Testare sökes — rapportera feedback som [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)!

---

## Funktioner

| Feature | Audi | VW EU | Škoda | SEAT/CUPRA |
|---|:---:|:---:|:---:|:---:|
| Fuel / Battery level | ✓ | ✓ | ✓ | ✓ |
| Range | ✓ | ✓ | ✓ | ✓ |
| Odometer | ✓ | ✓ | ✓ | ✓ |
| GPS position | ✓ | ✓ | ✓ | ✓ |
| Doors (total + per door) | ✓ | ✓ | ✓ | ✓ |
| Windows | ✓ | ✓ | ✓ | ✓ |
| Climate start/stop | ✓ | ✓ | ✓ | ✓ |
| Target temperature | ✓ | ✓ | ✓ | ✓ |
| Lock / Unlock | ✓ | ✓ | ✓ | ✓ |
| Flash lights | ✓ | ✓ | ✓ | ✓ |
| Wake vehicle | ✓ | ✓ | ✓ | ✓ |
| Service due km/days | ✓ | ✓ | ✓ | ✓ |
| Online status | ✓ | ✓ | ✓ | ✓ |
| Battery SoC % | ✓ | ✓ | ✓ | ✓ |
| Charge state | ✓ | ✓ | ✓ | ✓ |
| Charge power kW | ✓ | ✓ | ✓ | ✓ |
| Charge speed km/h | ✓ | ✓ | ✓ | ✓ |
| Charge ETA | ✓ | ✓ | ✓ | ✓ |
| Charge target % | ✓ | ✓ | ✓ | ✓ |
| Trunk / hood / sunroof | ✓ | ✓ | ✓ | ✓ |
| Window heating | ✓ | ✓ | ✓ | ✓ |
| Vehicle renders | ✓ | — | — | ✓ |
| Departure timers 1–3 | ✓ | ✓ | — | — |
| Battery temperature | ✓ | ✓ | — | — |
| AdBlue range | ✓ | ✓ | — | ✓ |

---

## Installation

### HACS

1. HACS → Integrationer → ⋮ → Anpassade förråd
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha` — Kategori: Integration
3. Installera **VW Group Connect** → Starta om Home Assistant
4. Inställningar → Integrationer → **+ Integration** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Starta om Home Assistant.

---

## Konfiguration

| Field | Required | Description |
|---|---|---|
| Märke | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| E-post | ✓ | Inloggnings-e-post från tillverkarens app |
| Lösenord | ✓ | Lösenord från appen |
| S-PIN | — | Krävs för låsning (under Säkerhet i appen) |
| Intervall | — | Minuter mellan uppdateringar (standard: 5) |

**Vilken app?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Kända Begränsningar

- **S-PIN** krävs för låsning
- **Intervall** minst 5 minuter
- **2FA** — bekräfta en gång manuellt i appen
- **Porsche / VW NA** — fungerar som Beta, testare sökes

---


## Licens

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** är ett oregistrerat varumärke (™, inte ®). Använd inte detta namn i forks för att undvika förvirring.

Denna integration är ett oberoende gemenskapsprojekt utan koppling till Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG eller något VAG-dotterbolag.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
