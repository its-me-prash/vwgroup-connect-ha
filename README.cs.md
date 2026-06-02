<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integrace Home Assistant pro Audi · VW · Škoda · SEAT · CUPRA</strong>
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


## Co je nového ve v2.10.0

Největší release této integrace doposud. Cca 6 týdnů intenzivní práce v jednom cut.

- **Oprava loginu VW EU Auth0 SPA (#388)**: VW kolem 2026-05-31 migroval stránku hesla na full-SPA template. Retry JSON Content-Type na `/u/login` plus zpřísněná detekce consent odblokuje uživatele na classic-auth.
- **Cross-brand parser parita**: VW EU Group A (10 nových polí - 12V, aktivní ventilace, zadní střešní okno, kabriolet střecha, součty per-jízda), SEAT/CUPRA Group B (6 OLA endpointů - warning-lights v3, nastavitelný battery-care, charging-statistics, preferovaný servis), VW NA Group C (4 endpointy - migrace na `data.exteriorStatus.*`, opravuje symptom "všechno null" na ID.4 US 2023 #322).
- **Detekce uzamčení účtu VW** s vedeným Repairs issue + auto-clear.
- **Vynucování Scout Policy**: každá silenced JSON cesta musí být také parsována do entity, nebo nést explicitní T2-T5 exemption komentář. Uzavírá #384, #389.
- **Provenance canaries + weekly watcher** + hardening (SPDX, Bruno drift-gate, mypy strict).

Zbytek z v2.7-v2.9 stále běží: Browser-Login DAG, multi-strategy auth, Data Act Portal, MFA, FCM push, Standheizung, brake-service, parser telemetry.

Plný [CHANGELOG](CHANGELOG.md#2100---2026-06-02).

## Co je nového v v2.7.x

**Přihlášení přes prohlížeč (žádné heslo v HA) pro Audi, Škoda, SEAT, CUPRA.** OAuth Device Authorization Grant podle RFC 8628. Naskenuj QR kód telefonem nebo otevři URL na libovolném zařízení, potvrď krátký kód, hotovo. Skutečný refresh_token, žádné opakované přihlašování každé dvě hodiny.

**Multi-strategie auth resolver.** Až tři záložní strategie na značku (Browser-Login, OIDC Hybrid Flow, EU Data Act Portal pouze pro čtení). Jedna strategie umírá, integrace běží dál na další.

**Data Act Portal jako fallback pouze pro čtení.** Vlastní implementace přihlášení do EU Data Act portálu, integrovaná jako strategie 3. úrovně. Pouze pro čtení ale bez attestation, takže nerozbitná když VW utáhne OAuth cestu.

**Mnohem více datových bodů.** Statistiky jízdy (životnostní vzdálenost, poslední jízda), hladina oleje, tlak v každé pneumatice, dveře / okna / střecha / kufr per pozice, venkovní teplota na MY24+, Webasto přídavné topení, všechna upozornění výrobce včetně značkově specifických jako Audi STO.

Viz [CHANGELOG](CHANGELOG.md#270---2026-05-31).

---

## Kde vedeme

Stav k 2026-05-31, po backendové změně VW z 2026-05-27 která zasáhla celou komunitu integrací HA-VAG současně:

| Funkce | Status zde | Status u ostatních |
|---|---|---|
| OAuth Device Authorization Grant (QR-Login) pro Audi/Škoda/SEAT/CUPRA | ✅ od v2.7.0 | Nikdo |
| Multi-strategie auth fallback řetězec (3 úrovně na značku) | ✅ od v2.6.0 | Nikdo |
| Portál EU Data Act jako 3. úroveň pouze pro čtení | ✅ od v2.6.0 | Pouze jako samostatná integrace |
| Bezpečnostní síť InvalidURL proti úniku tokenů | ✅ od v2.7.2 | Nikdo |
| Watcher attestation gate na straně serveru | ✅ od v2.7.0 | Nikdo |
| Vehicle Data Scout, auto-detekce API driftu | ✅ od v1.9.0 | Nic srovnatelného |
| Všech 7 značek VAG v jedné integraci | ✅ | Ostatní projekty mají jeden repo na značku |

---

## Kde jsou hranice (poctivě)

**VW EU je tvrdě zablokované Play Integrity od backendové změny 2026-05-27.** Tato zeď zasahuje každou Python-based VAG integraci (naši včetně). Není to dočasné zpoždění z naší strany, je to backendová politika VW:

- Token endpoint validuje hlavičku `X-Assertion` která musí být JWS podepsaný Google Play Integrity
- Python nemůže tento token vygenerovat, podpisový klíč žije pouze v Google attestation service
- Důsledek: VW EU uživatelé nedostávají skutečný refresh_token a musí se znovu přihlašovat každé ~2h

Co nabízíme pro VW EU: OIDC Hybrid Flow jako primární strategie (čtení + zápis, 2h re-login), EU Data Act portál jako fallback pouze pro čtení (cadence 15 min, bez attestation), týdenní watcher který automaticky otevírá issue jakmile VW otevře bránu.

**Termín EU Data Act 2026-09-12.** Do tohoto data musí VW legálně poskytnout přímý přístup k datům vozidla majitelům bez attestation gatingu. Naše `_data_act_portal.py` je připraveno na tento den.

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


Chtěl jsem plně ovládat své Audi v Home Assistant. Tak jsem to postavil.

**VW Group Connect** je samostatná integrace Home Assistant pro všechny značky VAG. Bez externích závislostí, bez Dockeru, bez externích služeb.

Od v0.14.1 integrace **přímo** komunikuje s CARIAD API — vlastní async klient, plně autonomní. Architektura cloud-polling, 80+ entit napříč 10 platformami, 14 služeb.

> ✅ **Aktivně udržovaný multi-značkový nástupce** projektů [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (archivováno 2025-10-29) a [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (deprecated 2025-03-14). Jedna integrace pro Audi, VW, Škoda, SEAT, CUPRA, Porsche a VW US/CA — bez samostatného pluginu pro každou značku.

## Aktuální stav a upřímné limity / Current Status & Honest Limits (v1.12.3)

VW Group Connect se aktivně vyvíjí. Abys věděl, co funguje a co přijde:

### ✅ Co funguje TEĎ (všech 7 značek)

**🛰️ Bug reporty a žádosti o funkce 1 kliknutím (LIVE od v1.9.0)**

Dva diagnostické sensory se sdílenou reporter pipeline — **první skutečná live-validace komunitními uživateli** v v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) a v1.12.3 (DnnsJp74 / Audi):

- 🔬 **Vehicle Data Scout** — automaticky detekuje neznámá JSON pole v API tvého auta. Lokalizovaný per značku v 8 jazycích (DE: API-Beobachter, FR: Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer posledních 20 chyb integrace s anonymizovaným kontextem (model, firmware, stack trace).
- 🔘 **Reporter Pipeline:** oba sensory automaticky vytvářejí HA Repair notifikace s předvyplněným GitHub-Issue jako 1-klik linkem. Plus diagnostics-download se vším maskovaným pro fórum/Facebook.
- 🔒 **Slib soukromí:** Nic neopustí tvou HA bez tvého explicitního kliknutí. VINy maskovány, GPS zaokrouhlené na 1 desetinné místo, JWT/UUID/e-maily odstraněny. GDPR-compliant.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Sensor `connection_state` (online / standby / offline) pro Audi, VW EU, Škoda, SEAT, CUPRA — první VAG integrace s centralizovaným stavem připojení. Brand-agnostický helper `compute_connection_state` s rekurzivním procházením `carCapturedTimestamp`.

**🔋 Monitoring 12V baterie + Smart-Wake (v1.12.0)**

- Sensor `voltage_12v` (V) + binary `warning_12v_low` při <11.5V — zabraňuje tichým výpadkům API kvůli vybité startovací baterii
- Sensor `wake_count_today` + soft-cap na 3 wakes/den (`_WAKE_BUDGET_PER_DAY`) chrání 12V před wake-loops, vyvolá `wake_budget_exhausted` PŘED API voláním

**💨 Optimistické UI pro Lock/Climate/Charging (v1.11.1)**

Switche se přepínají okamžitě po kliknutí (vzor myskoda PR #832), API roundtrip na pozadí. Při selhání: revert + ServiceValidationError. 8 actuator metod převedeno.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up v v1.11.1)**

Tři explicitní range sensory: `electric_range_km`, `combustion_range_km`, `total_range_km`. Parser VW EU/Audi klasifikuje podle typu motoru (4 zdroje místo 2). Audi-diesel-fallback z `measurements.rangeStatus.value.dieselRange`. Ověřeno přes evcc-io/evcc#19045 + Audi Q4 sample + CarConnectivity logy.

**🔒 Read-only režim Fáze 1 (v1.12.0)**

Toggle možností "Read-only Mode" → přeskočí lock/switch/button(non-refresh)/climate/number platformy pro privacy/safety-konzervativní vlastníky. Sensors + binary_sensors + device_tracker zůstávají.

**⚡ Zapisovatelné Max-Charge-Current Number (v1.12.0)**

Slider 6-32A místo pouze read-only sensoru. Nový `command_set_max_charge_current` POST chargingSettings.

**💡 Per-Light Binary-Sensors (v1.12.0)**

Dynamicky per typ světla z dict `lights_individual` + agregáty `lights_on` + `lights_count`.

**🛠️ Defenzivní stabilita (v1.8.7 + v1.10.1)**

- 504-retry, transient-network-error retry, 6h stale-cache + tolerance 3 selhání
- Ochrana před token-refresh-storm (max 3/h) — zabraňuje IP banům
- Helpery `safe_int` / `safe_float` / `safe_enum` — tolerují backend quirks

**🚪 CUPRA Born 2026 Firmware-Shapes (v1.10.2 — Gerhardova #53 první live-validace)**

Field-name fallback řetězec: `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Lowercase enum tolerance pro `"connected"` / `"locked"`. Zpětná kompatibilita zachována.

**🔓 Lock + Wake pro Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` posílá nyní S-PIN pro Audi/VW (CARIAD BFF odpovídal `403 spin_error`). `command_wake` používá v1→v2 fallback.

**🛡️ Capability-Filter Fáze 2 (v1.9.1, #56)**

Body-sniffing `classify_command_failure` pro `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error` markery. `_cariad_cmd` zapisuje každý výsledek do FeatureState. Command-bound entity (Lock/Climate/Switch/Buttons) jdou automaticky unavailable při definitivním "ne" backendu.

### ⚠️ Ještě v procesu / What's still in progress (plánované sessions)

- **v1.13.0 MINOR** — Anonymized Diagnostics-Export (#62) + Capability-Filter Fáze 3 (`capability.active && user-enabled` PRE-vytvoření-entity, skrývá tlačítka jako MyCupra aplikace) + Read-only Fáze 2/3 (Command-Locking + oddělení služeb cloud_refresh vs wake_vehicle).
- **v1.14.0 MINOR** — Trip Statistics z Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), Climate-Timer UI (#26).
- **v1.16.0 MINOR** — Lokalitně-specifický Cíl SoC nabíjení + nabíjecí profily (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, vzor upstream #717).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) pro real-time updaty bez pollingu (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-Tests všech značek + EU Data Act ready (pycupra `EUDAConnection` jako reference, deadline září 2026) (#13, #59).

### 🚫 Vědomé limity / Conscious limits

- **Image platforma:** neexistuje oficiální CARIAD render-image API. Image entita přejde v budoucí release na URL dodávané uživatelem.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — nová architektura E³ 1.2, ještě veřejně reverse-engineered (ani v upstream ani v CarConnectivity). VW Group Connect tato vozidla detekuje a dělá **graceful degradation** místo 404 chyb.
- **Ford / značky mimo VAG:** mimo rozsah — viz [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) pro Ford.

### 🔧 Předpoklad ochrany soukromí

Aby GPS poloha, stav vozidla a topení fungovaly, musí být **"Sdílet mou polohu"** aktivní v tvé aplikaci My-VW / My-Audi / MySkoda / MyCupra — jinak backend odpovídá 403.

### 📚 Více informací / More info

- 🗺️ Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md) — kompletní P0/P1/P2/P3 priorizace všech otevřených issues
- 📜 Tech Changelog: [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — per release: field-mappings + architektonické rozhodnutí + externí source-refs
- 🎨 Průvodce Dashboards + Lovelace karta BETA: [`docs/dashboards.md`](docs/dashboards.md) — řešení problémů s „Přidat na panel" + dedikovaná Lovelace karta (BETA)
- 🤝 Session Handoff (pro přispěvatele a AI nástroje): [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Pravidla soukromí a zacházení s daty: sekce [`CONTRIBUTING.md`](CONTRIBUTING.md) (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / diagnóza `missing-capability`: FAQ sekce v [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Podporované Značky

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA:** Obě značky jsou od v1.0.0 k dispozici jako Beta. Hledáme testery — zpětnou vazbu hlaste jako [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)!

---

## Funkce

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

## Instalace

### HACS

1. HACS → Integrace → ⋮ → Vlastní repozitáře
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha` — Kategorie: Integrace
3. Nainstalovat **VW Group Connect** → Restartovat Home Assistant
4. Nastavení → Integrace → **+ Integrace** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Restartujte Home Assistant.

---

## Konfigurace

| Field | Required | Description |
|---|---|---|
| Značka | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| E-mail | ✓ | Přihlašovací e-mail z aplikace výrobce |
| Heslo | ✓ | Heslo z aplikace |
| S-PIN | — | Vyžadováno pro zamykání (v Zabezpečení v aplikaci) |
| Interval | — | Minuty mezi aktualizacemi (výchozí: 5) |

**Která aplikace?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Známá Omezení

- **S-PIN** vyžadováno pro zamykání
- **Interval** minimum 5 minut
- **2FA** — jednou ručně potvrdit v aplikaci
- **Porsche / VW NA** — funkční jako Beta, hledáme testery

---


## Licence

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** je neregistrovaná ochranná známka (™, ne ®). Prosíme, nepoužívejte tento název ve forkách, abyste předešli záměně.

Tato integrace je nezávislý komunitní projekt bez jakéhokoliv spojení s Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG nebo jakoukoliv pobočkou Volkswagen Group.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
