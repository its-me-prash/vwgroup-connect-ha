<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integrace Home Assistant pro Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Jedna integrace pro všech 7 značek VAG, přímý přístup k API, bez middleware</em>
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
  <a href="README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Dříve publikováno jako **`vag-connect-ha`** (VAG = Volkswagen AG, běžná DACH zkratka).
> Ukázalo se, že tahle zkratka zní pro anglicky mluvící *výrazně jinak* 😅
>
> **Co funguje beze změny**: všechny entity (např. `sensor.audi_q4_battery_soc`),
> všechny service-cally (`vag_connect.lock`, `vag_connect.show_vag` atd.), všechny automatizace,
> instalace přes HACS — **nic se nerozbije**. Mění se marketingový/zobrazovaný název,
> vnitřnosti kódu zůstávají stejné. Detaily v [`MIGRATION.md`](MIGRATION.md).
>
> Obrovský dík komunitám **Home Assistant UK** a **HA Ideas, Projects and Solutions**
> za upozornění — zvlášť **Si Gregory**, **Ben Johnson** a **Evets David**.
>
> A speciální pozdrav pro **Jordan Waeles**, jehož komentář `show_vag()` je dnes oficiálně
> podporovaný easter egg v této integraci (service `vag_connect.show_vag`, viz CHANGELOG v2.2.3).

---

## Co to je?

**VW Group Connect je integrace [Home Assistant](https://www.home-assistant.io) pro data a ovládání propojených aut napříč všemi sedmi značkami koncernu Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche a VW US/Canada — z jediného config entry, instalovatelná přes [HACS](https://hacs.xyz).**

Zpřístupňuje stav baterie a nabíjení, dojezd, stav tachometru, klimatizaci, dveře/okna a polohu a — kde to backend dané značky ještě dovoluje (např. Audi) — posílá příkazy jako zamknout/odemknout, ovládání klimatizace a nabíjení. Aby zůstala funkční i přes změny VW API v roce 2026, mluví několika kanály a automaticky se přepne, když je jeden zablokovaný: backendy nativní pro značku, read-only portál pro data vozidel podle **EU Data Act** a opt-in webový kanál `volkswagen.de`.

Na rozdíl od integrací využívajících jen portál pokrývá i **Porsche** (které portál EU Data Act vylučuje) a zachovává **obousměrné ovládání Audi**.

> Integrace [Home Assistant](https://www.home-assistant.io) pro data a ovládání propojených vozidel napříč všemi sedmi značkami koncernu VW (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — jedna integrace, více datových kanálů, automatický fallback, instalace přes HACS.

---

## Aktuální stav

VW v roce 2026 postupně uzavřel přímý přístup k vozidlům pro nástroje třetích stran (CARIAD-BFF s atestací zařízení, CUPRA/SEAT-OLA za Play Integrity od června 2026). Tato integrace zůstává použitelná, protože mluví **více kanály** a automaticky se přepne, jakmile je jeden zablokovaný:

- **Backendy nativní pro značku** — plný přístup včetně ovládání, kde je dostupný (Audi, Škoda, Porsche, VW US/CA).
- **Portál EU Data Act** — read-only fallback pro všechny značky (bez atestace, cadence ~15 min).
- **Webový kanál volkswagen.de (Beta, opt-in)** — druhý čtecí kanál pro VW bez atestace.

Probíhající práce se točí kolem robustnosti portálu (retry při timeoutu, čerstvost dat) a odolnosti napříč kanály.

➡️ Kompletní historie verzí: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Kde vedeme

Poctivý stav v polovině roku 2026: portál EU Data Act se mezitím stal de-facto standardním kanálem a používá ho mnoho integrací. Co nás konkrétně odlišuje:

| Síla | My | Alternativy jen s portálem |
|---|---|---|
| **Všech 7 značek koncernu včetně Porsche** v jedné integraci | ✅ | Portál EU Data Act **strukturálně vylučuje Porsche** — nástroje jen s portálem nemůžou Porsche nikdy pokrýt |
| **Obousměrné ovládání Audi** (zámek/klima/nabíjení, nastavení target SoC) | ✅ | Portál je by-design **read-only** |
| **Multi-channel auth s auto-fallbackem** (backend značky → portál EU Data Act → opt-in vw.de web) | ✅ | většinou single-source — výpadek portálu = totální výpadek |
| **Vehicle Data Scout** — automaticky detekuje drift API, generuje bug-reporty na 1 klik | ✅ | nic srovnatelného |

---

## Kde jsou hranice (poctivě)

**VW EU a CUPRA/SEAT-OLA jsou od roku 2026 za atestací zařízení.** Tahle zeď (Google Play Integrity / Firebase App Check) zasahuje každou VAG integraci postavenou na Pythonu — naši včetně. Není to zpoždění z naší strany, je to politika backendu VW:

- Token/OLA endpoint vyžaduje atestační token podepsaný oficiální aplikací, který Python nedokáže vygenerovat (podpisový klíč žije pouze v atestační službě Google/Firebase).
- Důsledek: **VW EU** nedostane trvalý `refresh_token` (OIDC hybrid flow vydrží ~2 h) a **CUPRA/SEAT** přes OLA dostávají od ~2026-06-08 `403 "Forbidden device detected"`.

Co i přesto nabízíme:

1. **Portál EU Data Act** jako read-only fallback pro všechny značky (bez atestace, cadence ~15 min) — automaticky převezme štafetu, když nativní backend zablokuje.
2. **Webový kanál volkswagen.de (Beta, opt-in)** jako druhý čtecí kanál pro VW bez atestace.
3. **OIDC hybrid flow** pro VW EU jako read+write strategie (cenou je 2h re-login).

**Termín EU Data Act 2026-09-12.** Do tohoto data musí VW podle nařízení EU nabídnout přímý přístup k datům majitele bez atestace — pokrytí polí v portálu do té doby pravděpodobně dál poroste.

Status podle značky:

| Značka | Ovládání | Data | Poznámka |
|---|---|---|---|
| **Audi** | ✅ obousměrné | ✅ plné | myAudi backend, bez atestační zdi |
| **Škoda** | ✅ obousměrné | ✅ plné | vlastní Škoda backend |
| **Porsche** | ✅ obousměrné | ✅ plné | Auth0 + PPA, stabilní |
| **VW US/CA** | ✅ obousměrné | ✅ plné | VW NA cloud (Beta) |
| **VW EU** | ⚠️ přes OIDC hybrid (~2h re-login) | ✅ read-only portál / vw.de Beta | gated atestací backendu |
| **CUPRA / SEAT** | ❌ OLA blokováno (App Check) | ✅ read-only portál | od ~2026-06-08, neopravitelné přes hlavičku |

---

## Co dostaneš

100+ entit napříč 11 HA platformami, 20+ service-callů, nativní podpora více vozidel na účet. Quality Scale Platinum.

**Senzory** (na vozidlo): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source pro ID.x, Oil Level Warning, varování vozidla (textový senzor se všemi backend warningy).

**Binární senzory**: Doors Locked, Doors Open na každé dveře, Windows Open na každé okno, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On na každé světlo, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Ovládání**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 s týdenním předtopením, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image platforma**: 1-7 renderů vozidla na VIN (Audi/VW přes GraphQL MediaService, CUPRA/SEAT přes OLA viewPoints, Škoda přes Widget + multi-angle kompozity).

**Device Tracker**: GPS poloha jako TrackerEntity pro mapu HA Lovelace.

---

## Instalace

### Možnost 1: One-Click (doporučeno)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Možnost 2: HACS Custom Repository

1. HACS → Integrace → ⋮ → Vlastní repozitáře
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Kategorie: Integration
4. Nainstalovat **VW Group Connect**
5. Restartovat Home Assistant

### Možnost 3: Manuálně

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Poté restartuj HA.

---

## Konfigurace

Nastavení → Zařízení a služby → Přidat integraci → "VW Group Connect"

**Při prvním nastavení si vybereš:**

- **Přihlášení přes prohlížeč** (doporučeno pro Audi/Škoda/SEAT/CUPRA): naskenuj QR kód nebo otevři URL, žádné heslo uložené v HA
- **E-mail + heslo** (pro VW EU, Porsche, VW US/CA): klasicky s přihlašovacími údaji Brand-ID

**Možnosti** (dostupné po nastavení):
- Interval pollingu (5-60 min, výchozí 10 min)
- Read-only režim pro bezpečné automatizace bez nechtěných příkazů
- Reverzní geokódování opt-in (posílá GPS na OpenStreetMap pro rozlišení adresy)
- Push-toggly (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) jako základ, live aktivace čeká na zprovoznění

---

## Příklady Lovelace

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

### Picture-Entity Card s renderem vozidla

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Vyhledání nabíjecí stanice

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

Více příkladů v [`docs/FAQ.md`](docs/FAQ.md). Vlastní Lovelace karty se integrují automaticky přes `extra_state_attributes.image_url`.

---

## Časté dotazy

| Otázka | Odpověď |
|---|---|
| Kdy se moje auto probudí? | Jen při service-callech (Lock/Climate/Wake), nikdy při status pollech. Smart-Wake-Cap: max 3 probuzení/den na auto, 5min cooldown. |
| Kolik API quota? | MyCupra/MySeat: ~1500 callů/den. Při 10min pollingu: ~144 callů/den = 10 % budgetu. Senzor `requests_remaining_today` ukazuje stav. |
| Proč se u VW EU musím každé 2h znovu přihlašovat? | VW od 2026-05-27 postavil token endpoint za Google Play Integrity. To zasahuje každou VAG integraci postavenou na Pythonu. EU Data Act 2026-09-12 by to měl vyřešit. |
| Zůstane token po HACS updatu? | Ano, od v1.19.2 přes Store persistenci HA. |
| Jak nahlásím bugy? | HA → Integrace → 🔧 Opravit → Bug-Report. Diagnostika je anonymizovaná (VINy maskované, GPS zaokrouhlené, tokeny odstraněné). |
| Popisky polí ukazují raw klíče (`brand`, `spin`) po updatu? | Tvrdý refresh prohlížeče (Ctrl+Shift+R). HA cachuje překlady na straně klienta. |

Kompletní FAQ v [`docs/FAQ.md`](docs/FAQ.md). Řešení problémů s dashboardy v [`docs/dashboards.md`](docs/dashboards.md).

---

## Soukromí a bezpečnost

- Žádné externí služby, vše přímo mezi HA a API výrobce
- Token-cache lokálně v `.storage/` HA (per config entry, JSON, automaticky odstraněný při odebrání integrace)
- Diagnostika anonymizovaná: VINy maskované, GPS zaokrouhlené na 1 desetinné místo, tokeny a hesla kompletně odstraněné
- Reverzní geokódování opt-in, ve výchozím stavu vypnuté
- Maskování VIN průběžně ve všech logách
- Token-URL jsou v ERROR-logu redigované (v2.7.2+)

Detaily v [`PRIVACY.md`](PRIVACY.md) a [`SECURITY.md`](SECURITY.md).

---

## Contributing

PRs vítány, viz [`CONTRIBUTING.md`](CONTRIBUTING.md). Pravidla stylu v [`STYLE.md`](STYLE.md) (privátně v `_private/STYLE.md` pro maintainery).

**Vehicle Data Scout** (live od v1.9.0): Když tvoje integrace detekuje neznámá JSON pole, automaticky vytvoří HA Repair notifikaci s předvyplněným odkazem na GitHub issue. Bug-report na 1 klik bez studia kódu.

---

## Licence

[Apache License 2.0](LICENSE) pro kód integrace. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) pro obsah `docs/research/`. Atribuce upstream open-source projektům viz [`NOTICE.md`](NOTICE.md).
