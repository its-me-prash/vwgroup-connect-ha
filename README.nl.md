<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Home Assistant Integratie voor Audi · VW · Škoda · SEAT · CUPRA</strong>
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


## Wat is nieuw in v2.10.0

De grootste release van deze integratie tot nu toe. Ongeveer 6 weken intensief werk in één cut.

- **VW EU Auth0 SPA login fix (#388)**: VW migreerde de password-pagina rond 2026-05-31 naar een full-SPA template. JSON Content-Type retry op `/u/login` plus aangescherpte consent-detectie deblokkeert gebruikers op classic-auth.
- **Cross-brand parser pariteit**: VW EU Group A (10 nieuwe velden - 12V, actieve ventilatie, achterste schuifdak, cabrio-kap, per-rit totalen), SEAT/CUPRA Group B (6 OLA endpoints - warning-lights v3, instelbare battery-care, charging-statistics, voorkeurs-werkplaats), VW NA Group C (4 endpoints - migratie naar `data.exteriorStatus.*`, lost het "alles-null" symptoom op de ID.4 US 2023 #322 op).
- **VW account-lock detectie** met geleide Repairs issue + auto-clear.
- **Scout Policy enforcement**: elk silenced JSON pad moet ook geparsed worden tot een entity, of een expliciete T2-T5 exemption-comment dragen. Sluit #384, #389.
- **Provenance canaries + weekly watcher** + hardening (SPDX, Bruno drift-gate, mypy strict).

Rest van v2.7-v2.9 nog steeds live: Browser-Login DAG, multi-strategy auth, Data Act Portal, MFA, FCM push, Standheizung, brake-service, parser telemetry.

Volledige [CHANGELOG](CHANGELOG.md#2100---2026-06-02).

## Wat is nieuw in v2.7.x

**Browser-Login (geen wachtwoord opgeslagen in HA) voor Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant per RFC 8628. Scan een QR-code met je telefoon of open de URL op een willekeurig apparaat, bevestig een korte code, klaar. Echt refresh_token, geen re-login elke twee uur.

**Multi-strategie auth resolver.** Tot drie fallback-strategieën per merk (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal alleen lezen). Een strategie stopt, de integratie loopt verder op de volgende.

**Data Act Portal als alleen-lezen fallback.** Eigen implementatie van de EU Data Act portal login, geïntegreerd als 3e-tier strategie. Alleen lezen maar attestation-vrij, dus onbreekbaar wanneer VW de OAuth-route verstrakt.

**Aanzienlijk meer datapunten.** Reisstatistieken (lifetime afstand, laatste rit), oliepeil, bandenspanning per wiel, deuren / ramen / dak / kofferbak per positie, buitentemperatuur op MY24+, Webasto extra verwarming, alle fabrikantswaarschuwingen inclusief merk-specifieke zoals Audi STO.

Zie [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Waar wij voorop lopen

Stand per 2026-05-31, na de VW backend-wijziging van 2026-05-27 die de hele HA-VAG-integratie-community tegelijk trof:

| Functie | Status hier | Status bij anderen |
|---|---|---|
| OAuth Device Authorization Grant (QR-Login) voor Audi/Škoda/SEAT/CUPRA | ✅ sinds v2.7.0 | Niemand |
| Multi-strategie auth fallback-keten (3 tiers per merk) | ✅ sinds v2.6.0 | Niemand |
| EU Data Act portal alleen-lezen tier als 3e-tier fallback | ✅ sinds v2.6.0 | Alleen als losse integratie |
| InvalidURL veiligheidsnet tegen token-lekken in logs | ✅ sinds v2.7.2 | Niemand |
| Server-side attestation gate watcher | ✅ sinds v2.7.0 | Niemand |
| Vehicle Data Scout, automatische API drift-detectie | ✅ sinds v1.9.0 | Niets vergelijkbaars |
| Alle 7 VAG-merken in één integratie | ✅ | Andere projecten hebben één repo per merk |

---

## Waar de grenzen liggen (eerlijk)

**VW EU is hard Play-Integrity-vergrendeld sinds de 2026-05-27 backend-wijziging.** Deze muur raakt elke Python-gebaseerde VAG-integratie (onze inbegrepen). Het is geen tijdelijke vertraging aan onze kant, het is het backend-beleid van VW:

- Het token-endpoint valideert een `X-Assertion` header die een door Google Play Integrity ondertekende JWS-token moet zijn
- Python kan deze token niet genereren, de signing-key zit alleen in Google's mobile-app attestation service
- Gevolg: VW EU-gebruikers krijgen geen echt refresh_token en moeten elke ~2 uur opnieuw inloggen

Wat we wel bieden voor VW EU: OIDC Hybrid Flow als primaire strategie (lezen + schrijven, 2h re-login), EU Data Act portal als alleen-lezen fallback (15-min cadens, attestation-vrij), wekelijkse watcher die automatisch een issue opent zodra VW de poort opent.

**EU Data Act 2026-09-12 compliance-deadline.** Tegen die datum moet VW wettelijk directe voertuigdata-toegang voor eigenaren bieden zonder attestation-gating. Onze `_data_act_portal.py` is gepositioneerd voor die dag.

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


Ik wilde mijn Audi volledig in Home Assistant besturen. Dus bouwde ik dit.

**VW Group Connect** is een zelfstandige Home Assistant integratie voor alle VAG-merken. Geen externe afhankelijkheden, geen Docker, geen externe diensten.

Vanaf v0.14.1 communiceert de integratie **rechtstreeks** met de CARIAD API — eigen async-client, volledig zelfstandig. Cloud-polling architectuur, 80+ entities over 10 platforms, 14 services.

> ✅ **Actief onderhouden multi-merk opvolger** van [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (gearchiveerd op 2025-10-29) en [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (deprecated op 2025-03-14). Eén integratie voor Audi, VW, Škoda, SEAT, CUPRA, Porsche en VW US/CA — geen aparte plugin per merk.

## Huidige status & eerlijke beperkingen / Current Status & Honest Limits (v1.12.3)

VW Group Connect ontwikkelt zich actief verder. Zodat je weet wat werkt en wat eraan komt:

### ✅ Wat NU werkt (alle 7 merken)

**🛰️ 1-klik bug reports & feature requests (LIVE sinds v1.9.0)**

Twee diagnose-sensoren met een gedeelde reporter-pipeline — **eerste echte live-validatie door community-gebruikers** in v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) en v1.12.3 (DnnsJp74 / Audi):

- 🔬 **Vehicle Data Scout** — detecteert automatisch onbekende JSON-velden in de API van je auto. Per merk gelokaliseerd in 8 talen (DE: API-Beobachter, FR: Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer van de laatste 20 integratie-fouten met geanonimiseerde context (model, firmware, stack trace).
- 🔘 **Reporter Pipeline:** beide sensoren maken automatisch HA Repair-notificaties met een vooringevuld GitHub-Issue als 1-klik link. Plus een diagnostics-download met alles gemaskeerd voor forum/Facebook.
- 🔒 **Privacy-belofte:** Niets verlaat je HA zonder jouw expliciete klik. VINs gemaskeerd, GPS afgerond op 1 decimaal, JWT's/UUID's/e-mails verwijderd. AVG/GDPR-compliant.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Sensor `connection_state` (online / standby / offline) voor Audi, VW EU, Škoda, SEAT, CUPRA — eerste VAG-integratie met gecentraliseerde verbindingsstatus. Brand-agnostische helper `compute_connection_state` met recursieve `carCapturedTimestamp` walk.

**🔋 12V-Accu monitoring + Smart-Wake (v1.12.0)**

- `voltage_12v` sensor (V) + `warning_12v_low` binary bij <11.5V — voorkomt stille API-uitval door lege startaccu
- `wake_count_today` sensor + soft-cap op 3 wakes/dag (`_WAKE_BUDGET_PER_DAY`) beschermt 12V tegen wake-loops, raised `wake_budget_exhausted` VOOR de API-call

**💨 Optimistische UI voor Lock/Climate/Charging (v1.11.1)**

Switches schakelen direct bij klik (myskoda PR #832 patroon), API-roundtrip op de achtergrond. Bij failure: revert + ServiceValidationError. 8 actuator-methodes overgezet.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up in v1.11.1)**

Drie expliciete range-sensoren: `electric_range_km`, `combustion_range_km`, `total_range_km`. VW EU/Audi parser classificeert op motortype (4 bronnen in plaats van 2). Audi-diesel-fallback uit `measurements.rangeStatus.value.dieselRange`. Geverifieerd via evcc-io/evcc#19045 + Audi Q4 sample + CarConnectivity logs.

**🔒 Read-only Modus Fase 1 (v1.12.0)**

Options-toggle "Read-only Mode" → skip lock/switch/button(non-refresh)/climate/number platformen voor privacy/safety-conservatieve eigenaren. Sensors + binary_sensors + device_tracker blijven.

**⚡ Schrijfbare Max-Charge-Current Number (v1.12.0)**

Slider 6-32A in plaats van alleen een read-only sensor. Nieuwe `command_set_max_charge_current` POST chargingSettings.

**💡 Per-Light Binary-Sensors (v1.12.0)**

Dynamisch per lichttype uit `lights_individual` dict + aggregaten `lights_on` + `lights_count`.

**🛠️ Defensieve stabiliteit (v1.8.7 + v1.10.1)**

- 504-retry, transient-network-error retry, 6h stale-cache + 3-failure tolerance
- Token-refresh-storm bescherming (max 3/h) — voorkomt IP-bans
- `safe_int` / `safe_float` / `safe_enum` helpers — toleranter voor backend-quirks

**🚪 CUPRA Born 2026 Firmware-Shapes (v1.10.2 — Gerhard's #53 eerste live-validatie)**

Field-name fallback-keten: `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Lowercase enum tolerantie voor `"connected"` / `"locked"`. Backwards-compat behouden.

**🔓 Lock + Wake voor Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` stuurt nu S-PIN voor Audi/VW (CARIAD BFF antwoordde `403 spin_error`). `command_wake` gebruikt v1→v2 fallback.

**🛡️ Capability-Filter Fase 2 (v1.9.1, #56)**

`classify_command_failure` body-sniffing voor `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error` markers. `_cariad_cmd` schrijft elke uitkomst naar FeatureState. Command-gebonden entities (Lock/Climate/Switch/Buttons) gaan automatisch unavailable bij definitieve backend-"nee".

### ⚠️ Nog in uitvoering / What's still in progress (geplande sessies)

- **v1.13.0 MINOR** — Anonymized Diagnostics-Export (#62) + Capability-Filter Fase 3 (`capability.active && user-enabled` PRE-entity-creation, verbergt knoppen zoals de MyCupra-app) + Read-only Fase 2/3 (Command-Locking + cloud_refresh vs wake_vehicle service-scheiding).
- **v1.14.0 MINOR** — Trip Statistics uit Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), Climate-Timer UI (#26).
- **v1.16.0 MINOR** — Locatie-specifieke laaddoel-SoC + laadprofielen (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, upstream #717 patroon).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) voor real-time updates zonder polling (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-Tests alle merken + EU Data Act ready (pycupra `EUDAConnection` als referentie, deadline september 2026) (#13, #59).

### 🚫 Bewuste beperkingen / Conscious limits

- **Image-platform:** geen officiële CARIAD render-image API. De image-entity zal in een toekomstige release overgaan naar door gebruiker geleverde URLs.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — nieuwe E³ 1.2 architectuur, nog niet publiek reverse-engineered (ook niet in upstream of CarConnectivity). VW Group Connect detecteert deze voertuigen en doet **graceful degradation** in plaats van 404-fouten.
- **Ford / niet-VAG merken:** buiten scope — zie [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) voor Ford.

### 🔧 Privacy-vereiste

Voor GPS-positie, voertuigstatus en standkachel moet **"Locatie delen"** ingeschakeld zijn in je My-VW / My-Audi / MySkoda / MyCupra app — anders antwoordt de backend met 403.

### 📚 Meer info / More info

- 🗺️ Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md) — volledige P0/P1/P2/P3 prioritisering van alle openstaande issues
- 📜 Tech Changelog: [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — per release: field-mappings + architectuur-beslissingen + externe source-refs
- 🎨 Dashboards-gids + Lovelace-kaart BETA: [`docs/dashboards.md`](docs/dashboards.md) — "Toevoegen aan dashboard" troubleshooting + dedicated Lovelace-kaart (BETA)
- 🤝 Session Handoff (voor bijdragers & AI-tools): [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Privacy & data handling regels: [`CONTRIBUTING.md`](CONTRIBUTING.md) sectie (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / `missing-capability` diagnose: [`CONTRIBUTING.md`](CONTRIBUTING.md) FAQ-sectie

---

## Ondersteunde Merken

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA:** Beide merken zijn sinds v1.0.0 beschikbaar als Beta. Testers gezocht — meld feedback als [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)!

---

## Functies

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

## Installatie

### HACS

1. HACS → Integraties → ⋮ → Aangepaste opslagplaatsen
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha` — Categorie: Integratie
3. **VW Group Connect** installeren → Home Assistant opnieuw opstarten
4. Instellingen → Integraties → **+ Integratie** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Herstart Home Assistant.

---

## Configuratie

| Field | Required | Description |
|---|---|---|
| Merk | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| E-mail | ✓ | Aanmeldings-e-mail van de fabrikants-app |
| Wachtwoord | ✓ | Wachtwoord van de app |
| S-PIN | — | Vereist voor vergrendeling (onder Beveiliging in de app) |
| Poll-interval | — | Minuten tussen updates (standaard: 5) |

**Welke app?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Bekende Beperkingen

- **S-PIN** vereist voor vergrendeling
- **Poll-interval** minimaal 5 minuten
- **2FA** — eenmalig handmatig bevestigen in de app
- **Porsche / VW NA** — functioneel als Beta, testers gezocht

---


## Licentie

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** is een niet-geregistreerd handelsmerk (™, niet ®). Gebruik deze naam niet in forks om verwarring te voorkomen.

Deze integratie is een onafhankelijk communityproject zonder enige verbinding met Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG of andere VAG-dochterondernemingen.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
