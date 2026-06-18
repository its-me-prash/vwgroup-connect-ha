<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Integracja Home Assistant dla Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Jedna integracja dla wszystkich 7 marek VAG, bezpośredni dostęp do API, bez middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Licencja"></a>
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
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Wcześniej publikowane jako **`vag-connect-ha`** (VAG = Volkswagen AG, popularny skrót w regionie DACH).
> Okazało się, że ten skrót brzmi *znacząco inaczej* dla osób anglojęzycznych 😅
>
> **Co działa dalej bez zmian**: wszystkie encje (np. `sensor.audi_q4_battery_soc`),
> wszystkie wywołania usług (`vag_connect.lock`, `vag_connect.show_vag` itd.), wszystkie automatyzacje,
> instalacja przez HACS — **nic się nie psuje**. Zmienia się nazwa marketingowa / wyświetlana,
> wnętrze kodu pozostaje takie samo. Szczegóły w [`MIGRATION.md`](MIGRATION.md).
>
> Ogromne podziękowania dla społeczności **Home Assistant UK** oraz **HA Ideas, Projects and Solutions**
> za zwrócenie uwagi — szczególnie dla **Si Gregory**, **Ben Johnson** i **Evets David**.
>
> I specjalne pozdrowienia dla **Jordan Waeles**, którego komentarz `show_vag()` jest teraz oficjalnie
> wspieranym easter eggiem w tej integracji (usługa `vag_connect.show_vag`, patrz CHANGELOG v2.2.3).

---

## Co to jest?

**VW Group Connect to integracja [Home Assistant](https://www.home-assistant.io) do odczytu danych i sterowania samochodami połączonymi we wszystkich siedmiu markach Grupy Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche oraz VW US/Kanada — z jednego wpisu konfiguracyjnego, instalowana przez [HACS](https://hacs.xyz).**

Pokazuje stan akumulatora i ładowania, zasięg, przebieg, klimatyzację, drzwi/okna oraz lokalizację, a tam, gdzie backend marki nadal na to pozwala (np. Audi) — wysyła komendy takie jak zamykanie/otwieranie, sterowanie klimatyzacją i ładowaniem. Aby działać mimo zmian w API Volkswagena z 2026 roku, korzysta z kilku kanałów i automatycznie przełącza się na kolejny, gdy jeden zostanie zablokowany: natywne backendy marek, portal danych pojazdu **EU Data Act** (tylko do odczytu) oraz opcjonalny kanał webowy `volkswagen.de`.

W odróżnieniu od integracji opartych wyłącznie na portalu, obejmuje też **Porsche** (którego portal EU Data Act nie udostępnia) i zachowuje **dwukierunkowe sterowanie Audi**.

> Integracja [Home Assistant](https://www.home-assistant.io) do odczytu danych i sterowania samochodami połączonymi we wszystkich siedmiu markach koncernu VW (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — jedna integracja, wiele kanałów danych, automatyczny fallback, instalacja przez HACS.

---

## Bieżący stan

W 2026 roku VW stopniowo zamykał bezpośredni dostęp do pojazdów dla narzędzi firm trzecich (CARIAD-BFF z atestacją urządzenia, OLA dla CUPRA/SEAT za Play Integrity od czerwca 2026). Ta integracja pozostaje używalna, ponieważ obsługuje **wiele kanałów** i automatycznie przełącza się, gdy tylko jeden zostanie zablokowany:

- **Natywne backendy marek** — pełny dostęp wraz ze sterowaniem, tam gdzie jest dostępne (Audi, Škoda, Porsche, VW US/CA).
- **Portal EU Data Act** — fallback tylko do odczytu dla wszystkich marek (bez atestacji, cadence ~15 min).
- **Kanał webowy volkswagen.de (Beta, opt-in)** — drugi kanał odczytu dla VW bez atestacji.

Bieżąca praca skupia się na odporności portalu (retry przy timeoutach, świeżość danych) i odporności między kanałami.

➡️ Pełna historia wersji: **[CHANGELOG.md](CHANGELOG.md)**.

---

## Gdzie prowadzimy

Uczciwy stan na połowę 2026: portal EU Data Act stał się de facto standardowym kanałem, korzysta z niego wiele integracji. Co konkretnie nas wyróżnia:

| Mocna strona | My | Alternatywy oparte tylko na portalu |
|---|---|---|
| **Wszystkie 7 marek koncernu wraz z Porsche** w jednej integracji | ✅ | Portal EU Data Act **strukturalnie wyklucza Porsche** — narzędzia oparte tylko na portalu nigdy nie obejmą Porsche |
| **Dwukierunkowe sterowanie Audi** (Lock/Klima/Ładowanie, ustawianie docelowego SoC) | ✅ | Portal jest z założenia **tylko do odczytu** |
| **Multi-channel auth z auto-fallbackiem** (backend marki → portal EU Data Act → opcjonalny web vw.de) | ✅ | zwykle pojedyncze źródło — awaria portalu = całkowita awaria |
| **Vehicle Data Scout** — automatycznie wykrywa drift API, generuje raporty błędów jednym kliknięciem | ✅ | nic porównywalnego |

---

## Gdzie są granice (uczciwie)

**VW EU oraz OLA dla CUPRA/SEAT są od 2026 za atestacją urządzenia.** Ten mur (Google Play Integrity / Firebase App Check) uderza w każdą integrację VAG opartą o Python — w nas włącznie. To nie jest opóźnienie po naszej stronie, lecz polityka backendu VW:

- Endpoint tokenu/OLA wymaga tokenu atestacji podpisanego przez oficjalną aplikację, którego Python nie potrafi wygenerować (klucz podpisujący leży wyłącznie w usłudze atestacji Google/Firebase).
- Konsekwencja: **VW EU** nie dostaje trwałego `refresh_token` (hybrydowy flow OIDC trzyma ~2 h), a **CUPRA/SEAT** przez OLA dostają od ~2026-06-08 `403 "Forbidden device detected"`.

Co mimo to oferujemy:

1. **Portal EU Data Act** jako fallback tylko do odczytu dla wszystkich marek (bez atestacji, cadence ~15 min) — przejmuje automatycznie, gdy natywny backend blokuje.
2. **Kanał webowy volkswagen.de (Beta, opt-in)** jako drugi kanał odczytu dla VW bez atestacji.
3. **Hybrydowy flow OIDC** dla VW EU jako strategia odczyt+zapis (z ceną ponownego logowania co 2 h).

**Termin EU Data Act 2026-09-12.** Do tej daty VW musi na mocy rozporządzenia UE zapewnić bezpośredni dostęp do danych właściciela bez atestacji — pokrycie pól w portalu do tego czasu prawdopodobnie będzie rosło.

Status per marka:

| Marka | Sterowanie | Dane | Uwaga |
|---|---|---|---|
| **Audi** | ✅ Dwukierunkowe | ✅ pełne | backend myAudi, bez muru atestacji |
| **Škoda** | ✅ Dwukierunkowe | ✅ pełne | własny backend Škody |
| **Porsche** | ✅ Dwukierunkowe | ✅ pełne | Auth0 + PPA, stabilne |
| **VW US/CA** | ✅ Dwukierunkowe | ✅ pełne | VW-NA-Cloud (Beta) |
| **VW EU** | ⚠️ przez hybrydowy OIDC (~2h re-login) | ✅ portal tylko do odczytu / vw.de-Beta | backend za atestacją |
| **CUPRA / SEAT** | ❌ OLA zablokowane (App Check) | ✅ portal tylko do odczytu | od ~2026-06-08, nie do naprawienia nagłówkiem |

---

## Co dostajesz

100+ encji w 11 platformach HA, 20+ wywołań usług, natywne wsparcie wielu pojazdów na konto. Quality-Scale Platinum.

**Sensory** (per pojazd): Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source dla ID.x, Oil Level Warning, ostrzeżenia pojazdu (sensor tekstowy ze wszystkimi ostrzeżeniami backendu).

**Binary Sensors**: Doors Locked, Doors Open per drzwi, Windows Open per okno, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On per światło, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Sterowanie**: Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 z Weekly-Preheat, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform**: 1-7 renderów pojazdu per VIN (Audi/VW przez GraphQL MediaService, CUPRA/SEAT przez OLA viewPoints, Skoda przez Widget + Multi-Angle Composites).

**Device Tracker**: pozycja GPS jako TrackerEntity dla mapy HA Lovelace.

---

## Instalacja

### Opcja 1: One-Click (zalecane)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Opcja 2: HACS Custom Repository

1. HACS → Integracje → ⋮ → Niestandardowe repozytoria
2. URL: `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Kategoria: Integration
4. Zainstaluj **VW Group Connect**
5. Uruchom ponownie Home Assistant

### Opcja 3: Ręcznie

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Następnie uruchom ponownie HA.

---

## Konfiguracja

Ustawienia → Urządzenia i usługi → Dodaj integrację → "VW Group Connect"

**Przy pierwszej konfiguracji wybierasz:**

- **Logowanie przez przeglądarkę** (zalecane dla Audi/Škoda/SEAT/CUPRA): zeskanuj kod QR lub otwórz URL, hasło nie jest zapisywane w HA
- **E-mail + hasło** (dla VW EU, Porsche, VW US/CA): klasycznie z danymi Brand-ID

**Opcje** (dostępne po konfiguracji):
- Interwał odpytywania (5-60 min, domyślnie 10 min)
- Tryb read-only dla bezpiecznych automatyzacji bez przypadkowych komend
- Reverse-geocoding opt-in (wysyła GPS do OpenStreetMap w celu rozwiązania adresu)
- Push-Toggles (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) jako fundament, aktywacja live w toku

---

## Przykłady Lovelace

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

### Picture-Entity Card z renderem pojazdu

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Wyszukiwanie stacji ładowania

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

Więcej przykładów w [`docs/FAQ.md`](docs/FAQ.md). Niestandardowe karty Lovelace integrują się automatycznie przez `extra_state_attributes.image_url`.

---

## Najczęstsze pytania

| Pytanie | Odpowiedź |
|---|---|
| Kiedy moje auto jest budzone? | Tylko przy wywołaniach usług (Lock/Climate/Wake), nigdy przy odpytywaniu statusu. Smart-Wake-Cap: maks. 3 wybudzenia/dzień na auto, cooldown 5 min. |
| Ile API-Quota? | MyCupra/MySeat: ~1500 wywołań/dzień. Przy odpytywaniu co 10 min: ~144 wywołań/dzień = 10% budżetu. Sensor `requests_remaining_today` pokazuje stan. |
| Dlaczego przy VW EU muszę logować się ponownie co 2 h? | VW od 2026-05-27 umieścił endpoint tokenu za Google Play Integrity. Dotyczy to każdej integracji VAG opartej o Python. EU Data Act 2026-09-12 powinno to naprawić. |
| Czy token przetrwa aktualizację HACS? | Tak, od v1.19.2 dzięki persystencji w HA Store. |
| Jak zgłaszać błędy? | HA → Integracja → 🔧 Napraw → Bug-Report. Diagnostyka jest anonimizowana (VIN-y zamaskowane, GPS zaokrąglony, tokeny usunięte). |
| Etykiety pól pokazują surowe klucze (`brand`, `spin`) po aktualizacji? | Twarde odświeżenie przeglądarki (Ctrl+Shift+R). HA cache'uje tłumaczenia po stronie klienta. |

Pełne FAQ w [`docs/FAQ.md`](docs/FAQ.md). Rozwiązywanie problemów z dashboardami w [`docs/dashboards.md`](docs/dashboards.md).

---

## Prywatność i bezpieczeństwo

- Brak zewnętrznych usług, wszystko bezpośrednio między HA a API producenta
- Token-Cache lokalnie w `.storage/` HA (per-config-entry, JSON, automatycznie usuwany przy usunięciu integracji)
- Diagnostyka anonimizowana: VIN-y zamaskowane, GPS zaokrąglony do 1 miejsca po przecinku, tokeny i hasła całkowicie usunięte
- Reverse-geocoding opt-in, domyślnie wyłączony
- Maskowanie VIN konsekwentnie we wszystkich logach
- URL-e z tokenami są redagowane w logu ERROR (v2.7.2+)

Szczegóły w [`PRIVACY.md`](PRIVACY.md) i [`SECURITY.md`](SECURITY.md).

---

## Contributing

PR-y mile widziane, patrz [`CONTRIBUTING.md`](CONTRIBUTING.md). Reguły stylu w [`STYLE.md`](STYLE.md) (prywatne w `_private/STYLE.md` dla maintainerów).

**Vehicle Data Scout** (live od v1.9.0): gdy twoja integracja wykryje nieznane pola JSON, automatycznie tworzy powiadomienie HA Repair z gotowym linkiem do issue na GitHubie. Bug-Report jednym kliknięciem, bez studiowania kodu.

---

## Licencja

[Apache License 2.0](LICENSE) dla kodu integracji. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) dla treści `docs/research/`. Atrybucje do upstreamowych projektów open-source w [`NOTICE.md`](NOTICE.md).
