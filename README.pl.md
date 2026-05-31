<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integracja Home Assistant dla Audi · VW · Škoda · SEAT · CUPRA</strong>
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

## ✨ v2.0.0 Big-Bang Highlights — also available in English

> The detailed v2.0.0 highlights table + "What makes us unique" USP section
> are maintained in English on the German + English READMEs. They are
> provided here as the canonical source so non-DE/EN readers can still
> see all v2.0 features with `**[NEW v2.0]**` markers without waiting on
> 6 parallel translations.

### Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | **[NEW v2.0]** Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | **[NEW v2.0]** SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | **[NEW v2.0]** 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | **[NEW v2.0]** Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | **[NEW v2.0]** 3 pure-read enabled-sensors |
| **Weekly Preheat (`recurring_on`)** | **[NEW v2.0]** Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | **[NEW v2.0]** `vag_connect.find_charging_stations` service |
| **Vehicle Alarm sensors** | **[NEW v2.0]** closes issue #33 |
| **heaterSource sensor** | **[NEW v2.0]** closes issue #163 |
| **Push Manager Lifecycle Wiring** | **[NEW v2.0]** Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | **[NEW v2.0]** Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | **[NEW v2.0]** Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | **[NEW v2.0]** Drop-in `system_health.py` |
| **Quality Scale Platinum** | **[NEW v2.0]** Re-introduced after v1.26.x revert |
| **DeviceInfo `configuration_url` + `suggested_area`** | **[NEW v2.0]** Brand-aware "Open in App" button |

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


Chciałem w pełni sterować moim Audi z poziomu Home Assistant. Więc to zbudowałem.

**VW Group Connect** to samodzielna integracja Home Assistant dla wszystkich marek VAG. Bez zewnętrznych zależności, bez Dockera, bez zewnętrznych usług.

Od v0.14.1 integracja **bezpośrednio** komunikuje się z API CARIAD — własny klient async, w pełni autonomiczny. Architektura cloud-polling, 80+ encji w 10 platformach, 14 usług.

> ✅ **Aktywnie utrzymywany wieloprodukcyjny następca** projektów [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (zarchiwizowany 2025-10-29) i [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (deprecated 2025-03-14). Jedna integracja dla Audi, VW, Škoda, SEAT, CUPRA, Porsche i VW US/CA — bez osobnej wtyczki dla każdej marki.

## Bieżący stan i uczciwe ograniczenia / Current Status & Honest Limits (v1.12.3)

VW Group Connect aktywnie się rozwija. Abyś wiedział, co działa i co nadchodzi:

### ✅ Co działa TERAZ (wszystkie 7 marek)

**🛰️ Bug reporty i prośby o funkcje 1-kliknięciem (LIVE od v1.9.0)**

Dwa sensory diagnostyczne ze wspólną pipeline reportera — **pierwsza prawdziwa walidacja live przez użytkowników społeczności** w v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) i v1.12.3 (DnnsJp74 / Audi):

- 🔬 **Vehicle Data Scout** — wykrywa automatycznie nieznane pola JSON w API twojego auta. Lokalizowany per marka w 8 językach (DE: API-Beobachter, FR: Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer ostatnich 20 błędów integracji z anonimizowanym kontekstem (model, firmware, stack trace).
- 🔘 **Reporter Pipeline:** oba sensory tworzą automatycznie powiadomienia HA Repair z prefilled GitHub-Issue jako linkiem 1-kliknięciem. Plus pobranie diagnostics ze wszystkim zamaskowanym dla forum/Facebooka.
- 🔒 **Obietnica prywatności:** Nic nie opuszcza twojego HA bez twojego wyraźnego kliknięcia. VIN-y zamaskowane, GPS zaokrąglone do 1 miejsca po przecinku, JWT/UUID/e-maile usunięte. Zgodne z RODO/GDPR.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Sensor `connection_state` (online / standby / offline) dla Audi, VW EU, Škoda, SEAT, CUPRA — pierwsza integracja VAG ze scentralizowanym statusem połączenia. Brand-agnostyczny helper `compute_connection_state` z rekursywnym przejściem `carCapturedTimestamp`.

**🔋 Monitoring akumulatora 12V + Smart-Wake (v1.12.0)**

- Sensor `voltage_12v` (V) + binary `warning_12v_low` przy <11.5V — zapobiega cichym awariom API spowodowanym pustym akumulatorem rozruchowym
- Sensor `wake_count_today` + soft-cap na 3 wakes/dzień (`_WAKE_BUDGET_PER_DAY`) chroni 12V przed wake-loops, podnosi `wake_budget_exhausted` PRZED wywołaniem API

**💨 Optymistyczne UI dla Lock/Climate/Charging (v1.11.1)**

Switche przełączają się natychmiast po kliknięciu (wzorzec myskoda PR #832), roundtrip API w tle. Przy niepowodzeniu: revert + ServiceValidationError. 8 metod actuator przeniesionych.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up w v1.11.1)**

Trzy jawne sensory zasięgu: `electric_range_km`, `combustion_range_km`, `total_range_km`. Parser VW EU/Audi klasyfikuje wg typu silnika (4 źródła zamiast 2). Fallback diesel Audi z `measurements.rangeStatus.value.dieselRange`. Zweryfikowany przez evcc-io/evcc#19045 + sample Audi Q4 + logi CarConnectivity.

**🔒 Tryb Read-only Faza 1 (v1.12.0)**

Toggle opcji "Read-only Mode" → pomija platformy lock/switch/button(non-refresh)/climate/number dla właścicieli ostrożnych w kwestii prywatności/bezpieczeństwa. Sensors + binary_sensors + device_tracker pozostają.

**⚡ Zapisywalny Number Max-Charge-Current (v1.12.0)**

Slider 6-32A zamiast tylko sensora read-only. Nowy `command_set_max_charge_current` POST chargingSettings.

**💡 Per-Light Binary-Sensors (v1.12.0)**

Dynamicznie per typ światła z dict `lights_individual` + agregaty `lights_on` + `lights_count`.

**🛠️ Defensywna stabilność (v1.8.7 + v1.10.1)**

- Retry 504, retry przejściowych błędów sieci, cache 6h + tolerancja 3 błędów
- Ochrona przed token-refresh-storm (max 3/h) — zapobiega banom IP
- Helpery `safe_int` / `safe_float` / `safe_enum` — tolerują dziwactwa backendu

**🚪 CUPRA Born 2026 Firmware-Shapes (v1.10.2 — pierwsza walidacja live Gerharda #53)**

Łańcuch fallback nazw pól: `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Tolerancja enum lowercase dla `"connected"` / `"locked"`. Wsteczna kompatybilność zachowana.

**🔓 Lock + Wake dla Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` wysyła teraz S-PIN dla Audi/VW (CARIAD BFF odpowiadał `403 spin_error`). `command_wake` używa fallback v1→v2.

**🛡️ Capability-Filter Faza 2 (v1.9.1, #56)**

Body-sniffing `classify_command_failure` dla markerów `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error`. `_cariad_cmd` zapisuje każdy wynik do FeatureState. Encje powiązane z komendami (Lock/Climate/Switch/Buttons) automatycznie stają się unavailable przy ostatecznym "nie" backendu.

### ⚠️ Jeszcze w toku / What's still in progress (zaplanowane sesje)

- **v1.13.0 MINOR** — Anonymized Diagnostics-Export (#62) + Capability-Filter Faza 3 (`capability.active && user-enabled` PRE-tworzenie-encji, ukrywa przyciski jak aplikacja MyCupra) + Read-only Faza 2/3 (Command-Locking + rozdzielenie usług cloud_refresh vs wake_vehicle).
- **v1.14.0 MINOR** — Trip Statistics z Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), UI timera Climate (#26).
- **v1.16.0 MINOR** — Specyficzne dla lokalizacji SoC docelowy ładowania + profile ładowania (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, wzorzec upstream #717).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) dla aktualizacji w czasie rzeczywistym bez pollingu (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-Tests wszystkich marek + EU Data Act ready (pycupra `EUDAConnection` jako referencja, deadline wrzesień 2026) (#13, #59).

### 🚫 Świadome ograniczenia / Conscious limits

- **Platforma image:** nie istnieje oficjalne API CARIAD render-image. Encja image przejdzie na URL-e dostarczone przez użytkownika w przyszłej release.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — nowa architektura E³ 1.2, jeszcze nie zreverse-engineered publicznie (nawet w upstream ani CarConnectivity). VW Group Connect wykrywa te pojazdy i robi **graceful degradation** zamiast błędów 404.
- **Ford / marki spoza VAG:** poza zakresem — patrz [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) dla Forda.

### 🔧 Wymóg prywatności

Aby pozycja GPS, status pojazdu i ogrzewanie postojowe działały, **"Udostępnij moją lokalizację"** musi być włączone w twojej aplikacji My-VW / My-Audi / MySkoda / MyCupra — inaczej backend odpowiada 403.

### 📚 Więcej informacji / More info

- 🗺️ Roadmap: [`docs/ROADMAP.md`](docs/ROADMAP.md) — pełna priorytyzacja P0/P1/P2/P3 wszystkich otwartych issues
- 📜 Tech Changelog: [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — per release: mapowania pól + decyzje architektoniczne + refy do zewnętrznych źródeł
- 🎨 Przewodnik Dashboards + karta Lovelace BETA: [`docs/dashboards.md`](docs/dashboards.md) — rozwiązywanie problemów "Dodaj do panelu" + dedykowana karta Lovelace (BETA)
- 🤝 Session Handoff (dla współtwórców i narzędzi AI): [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Zasady prywatności i obsługi danych: sekcja [`CONTRIBUTING.md`](CONTRIBUTING.md) (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / diagnoza `missing-capability`: sekcja FAQ w [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Obsługiwane Marki

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA:** Obie marki są dostępne jako Beta od v1.0.0. Szukamy testerów — zgłoś opinię jako [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues)!

---

## Funkcje

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

## Instalacja

### HACS

1. HACS → Integracje → ⋮ → Niestandardowe repozytoria
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha` — Kategoria: Integracja
3. Zainstaluj **VW Group Connect** → Uruchom ponownie Home Assistant
4. Ustawienia → Integracje → **+ Integracja** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Uruchom ponownie Home Assistant.

---

## Konfiguracja

| Field | Required | Description |
|---|---|---|
| Marka | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| E-mail | ✓ | E-mail logowania z aplikacji producenta |
| Hasło | ✓ | Hasło z aplikacji |
| S-PIN | — | Wymagany do blokowania (w Bezpieczeństwo w aplikacji) |
| Interwał | — | Minuty między aktualizacjami (domyślnie: 5) |

**Która aplikacja?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Znane Ograniczenia

- **S-PIN** wymagany do blokowania
- **Interwał** minimum 5 minut
- **2FA** — potwierdzić raz ręcznie w aplikacji
- **Porsche / VW NA** — działające jako Beta, szukamy testerów

---


## Licencja

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** jest niezastrzeżonym znakiem towarowym (™, nie ®). Prosimy nie używać tej nazwy w forkach, aby uniknąć nieporozumień.

Ta integracja jest niezależnym projektem społecznościowym bez powiązania z Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG ani żadną filią Grupy Volkswagen.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
