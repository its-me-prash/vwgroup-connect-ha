<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Jedna integracja Home Assistant dla samochodów koncernu Volkswagen: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW i Audi USA/Kanada</strong><br>
  <em>Bateria, ładowanie, zasięg, drzwi, klimatyzacja i pozycja GPS w Home Assistant. Bezpośredni dostęp do API, kilka kanałów odczytu z automatycznym przełączaniem, bez warstwy pośredniej.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Sponsor this project"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.4%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.md">English</a> · <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.it.md">Italiano</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a> · <a href="README.da.md">Dansk</a> · <a href="README.nb.md">Norsk</a> · <a href="README.fi.md">Suomi</a>
</p>

---

> ### 📛 Uwaga o zmianie nazwy
> Poprzednio publikowana jako **`vag-connect-ha`** (VAG = Volkswagen AG, standardowy skrót w regionie DACH).
> Okazało się, że ten skrót brzmi *całkiem* inaczej dla osób anglojęzycznych 😅
>
> **Co działa jak dotychczas**: wszystkie encje (np. `sensor.audi_q4_battery_soc`),
> wszystkie wywołania usług (`vag_connect.lock`, `vag_connect.show_vag` itd.), wszystkie automatyzacje,
> instalacja przez HACS — **nic się nie psuje**. Zmienia się nazwa marketingowa/wyświetlana, wnętrze kodu
> pozostaje bez zmian. Zobacz [`MIGRATION.md`](MIGRATION.md).
>
> Ogromne podziękowania dla społeczności **Home Assistant UK** oraz **HA Ideas, Projects and Solutions**
> za zwrócenie uwagi — w szczególności dla **Si Gregory**, **Ben Johnson** i **Evets David**.
>
> I szczególne wyróżnienie dla **Jordan Waeles**, którego komentarz `show_vag()` jest teraz oficjalnie
> wspieranym easter eggiem w tej integracji (usługa `vag_connect.show_vag`, zobacz CHANGELOG v2.2.3).

---

## Co to jest?

**VW Group Connect to integracja [Home Assistant](https://www.home-assistant.io), która wprowadza twój samochód koncernu Volkswagen do inteligentnego domu: stan baterii i ładowania, zasięg, przebieg, klimatyzacja, drzwi i szyby, pozycja GPS i więcej, dla marek Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley oraz kont północnoamerykańskich VW / Audi, wszystko z jednego wpisu konfiguracyjnego.**

Tam, gdzie backend marki wciąż na to pozwala, wysyła też polecenia zdalne, takie jak zamykanie/otwieranie, sterowanie klimatyzacją i ładowaniem. **To zależy od marki, nie jest uniwersalne:** Audi i Škoda są dwukierunkowe, Volkswagen EU przez portal EU Data Act jest tylko do odczytu, a polecenia dla SEAT/CUPRA są zablokowane przez producenta. Tabela poniżej mówi dokładnie, co jest czym.

Żeby działać mimo zmian API Volkswagena z 2026 roku, integracja mówi **kilkoma kanałami odczytu i automatycznie się przełącza**, gdy jeden zostanie zablokowany: natywne backendy marek, portal danych pojazdu **EU Data Act** (tylko do odczytu), opcjonalny kanał webowy `volkswagen.de` (beta), opcjonalne uzupełnianie luk przez **Tibber** oraz trwałe logowanie **bez hasła** dla starszych aut Car-Net. Działa bez problemu **obok [evcc](https://evcc.io)** (zobacz [docs/EVCC.md](docs/EVCC.md)) i nie wymaga **żadnego dodatku, brokera ani kontenera pośredniego**. Home Assistant instaluje dla niej automatycznie dwa małe pakiety Pythona; używają ich wyłącznie opcjonalne kanały push.

> 🎉 **Teraz dostępna bezpośrednio w HACS** — bez potrzeby dodawania repozytorium niestandardowego.

---

## Najważniejsze cechy

- **9 wybieralnych marek koncernu Volkswagen** w jednej integracji: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Kanada, Audi USA/Kanada, Porsche i Bentley.
- **Sterowanie dwukierunkowe tam, gdzie backend marki na to pozwala**: zamykanie/otwieranie, klimatyzacja, ładowanie, docelowy SoC. To zależy **od marki, nie jest uniwersalne**. Zajrzyj do tabeli poniżej, zanim zaczniesz liczyć na jakieś polecenie.
- **Logowanie bez hasła** (przeglądarka/device-code) dla Audi, Škody, SEAT-a, CUPR-y i Audi USA/CA. W Home Assistant nie jest przechowywane żadne hasło.
- **Wiele kanałów z automatycznym przełączaniem**: natywny backend marki, portal EU Data Act, opcjonalny web vw.de, opcjonalny Tibber, trwały Car-Net. Awaria jednego kanału nie gasi twoich danych.
- **Odporność z założenia**: zachowuje ostatnie znane wartości i ostatnią znaną pozycję parkowania podczas awarii portalu, odfiltrowuje fałszywe wartości „brak odczytu", nigdy nie pozwala przebiegowi cofnąć się i mówi ci, kiedy nieudane logowanie to awaria po stronie producenta, a nie twoje hasło.
- **To ty ustalasz częstotliwość odpytywania**: suwak **interwału odpytywania** na konto (encja Number, w minutach), którym mogą sterować automatyzacje, tworzony w każdej instalacji, także w tych tylko do odczytu przez portal.
- **Tracker GPS**, ponad 100 encji na kilku platformach, ponad 20 wywołań usług, wiele pojazdów na koncie, nazwy encji w **12 językach**.
- **Porsche działa na własnym backendzie**, nie na portalu EU Data Act. Ścieżka portalowa strukturalnie *wyklucza* Porsche, więc narzędzia oparte wyłącznie na portalu nigdy go nie obsłużą. Kod poleceń jest tutaj, ale samo logowanie do Porsche jest obecnie eksperymentalne (zobacz tabelę).
- **Vehicle Data Scout** automatycznie wykrywa dryf API i proponuje zgłoszenie błędu jednym kliknięciem. **Quality Scale: Platinum.**

---

## Status marek

| Marka | Sterowanie | Dane | Uwagi |
|---|---|---|---|
| **Audi** (EU) | ✅ Dwukierunkowe | ✅ Pełne | backend myAudi (w tym start/stop silnika spalinowego) |
| **Škoda** | ✅ Dwukierunkowe | ✅ Pełne | natywny backend Škody |
| **VW USA/CA** | ✅ Dwukierunkowe | ✅ Pełne | chmura VW NA (wymaga wyboru kraju USA/CA + S-PIN). ⚠️ Własna usługa logowania VW odpowiada obecnie błędem serwera na część kanadyjskich logowań: to awaria po stronie VW, a nie złe hasło ([#915](https://github.com/its-me-prash/vwgroup-connect-ha/issues/915)) |
| **VW EU** | 🔒 Domyślnie tylko do odczytu · ⚠️ polecenia = MBB **alpha** | ✅ Pełna telemetria przez portal EU Data Act | Zobacz uczciwą uwagę poniżej ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Polecenia zablokowane przez VW | ✅ Portal EU Data Act | Dostęp OLA odebrany po stronie serwera w 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Dwukierunkowe zależne od testu na żywo | ✅ Logowanie + odczyt | My Bentley, działa na tenancie Audi/IDK |
| **Porsche** | ⚠️ Eksperymentalne | ⚠️ Eksperymentalne | Porsche Connect, własny backend. Porsche przeszło na aplikację *Porsche One*, więc **logowanie na obecnych kontach najprawdopodobniej się nie powiedzie**. Kod poleceń jest, ale pozostaje nieosiągalny do czasu przebudowania logowania ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⚠️ Eksperymentalne | ⚠️ Eksperymentalne | Logowanie jest podpięte do północnoamerykańskiego dostawcy tożsamości, ale **nie zostało jeszcze potwierdzone** na prawdziwym koncie USA/CA. Testerzy mile widziani ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Szczera uwaga o sterowaniu VW EU.** Pojazdy Volkswagen EU są **domyślnie tylko do odczytu**: otrzymujesz pełną telemetrię przez portal EU Data Act, ale bez zdalnych poleceń. Zdalne polecenia dla VW EU istnieją **wyłącznie jako eksperymentalna, trwała dwukierunkowa MBB w wersji ALPHA**, i tylko dla samochodów **starszych MQB / Car-Net** — to opcjonalny przełącznik, **a nie** funkcja domyślna. **Samochody MEB / z rodziny ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) nie mają żadnej ścieżki poleceń** i są tworzone jako tylko do odczytu. Alpha MBB jest śledzona w **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testerzy mile widziani.

> W 2026 roku Volkswagen ukrył część swojego API za atestacją urządzeń. Ta integracja omija to, gdzie to możliwe (trwałe logowanie Car-Net, portal EU Data Act, web vw.de) i jest transparentna co do tego, co każdy kanał potrafi, a czego nie.

---

## Znane ograniczenia

Kilka rzeczy jest **strukturalnych** — wynikają one z działania backendów Volkswagena w 2026 roku, a nie z samej integracji, i żadne ustawienie ich nie naprawi:

- **VW EU jest domyślnie tylko do odczytu; polecenia to alpha MBB tylko dla starszych samochodów.** Zobacz uwagę o marce powyżej. **Samochody MEB / z rodziny ID są tylko do odczytu** — trwała ścieżka poleceń Car-Net ich nie rozpoznaje (odpowiada „Unknown user"), a backend MEB Volkswagena nie udostępnia odpowiednika. Konfiguracja wykrywa to i tworzy **wpis tylko do odczytu** (z powiadomieniem naprawczym), zamiast się nie powieść, więc jest to znane ograniczenie, a nie ciche. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Zdalne polecenia CUPRA / SEAT są zablokowane przez VW.** Dostęp do usług online (OLA) dla tych marek został cofnięty po stronie serwera w 2026 (HTTP 403); ponowne logowanie ani aktualizacja wersji aplikacji go nie przywróci. Dane nadal płyną przez portal EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Dane z portalu EU Data Act są skąpe i różnią się w zależności od samochodu.** VW publikuje dziś tylko wycinek pól (często przebieg + blokada + ładowanie, czasem znacznie więcej). Z czasem się to rozszerza, gdy VW poszerza zakres portalu przed terminem we wrześniu 2026 — pola, które dziś pokazują `unknown`, mogą wypełnić się same, bez żadnych zmian. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Ameryka Północna jest eksperymentalna.** Logowanie **Audi USA/CA** jest podpięte, ale nigdy nie zostało potwierdzone na prawdziwym koncie ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)). **VW USA/CA** działa, ale własna usługa logowania VW zwraca obecnie błędy serwera na części kont kanadyjskich ([#915](https://github.com/its-me-prash/vwgroup-connect-ha/issues/915)). Nie wybieraj tej integracji do auta z Ameryki Północnej w oczekiwaniu, że po prostu zadziała.
- **Logowanie do Porsche najprawdopodobniej teraz zawiedzie.** Porsche wycofało aplikację *My Porsche*, wobec której ta integracja się uwierzytelnia, na rzecz *Porsche One*. Odczyty i polecenia są zaimplementowane, ale prawdopodobnie nie przejdziesz logowania, dopóki nie zostanie ono przebudowane. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Aktualizacje push (niemal w czasie rzeczywistym) to opcjonalna BETA, domyślnie wyłączona.** Kanały MQTT (Škoda) i Firebase (Audi/VW, CUPRA/SEAT) są podpięte, ale niesprawdzone na żywo, a marki coraz częściej zabezpieczają je atestacją aplikacji, której nie da się spełnić poza urządzeniem. Zostaw je wyłączone, chyba że chcesz pomóc w testach. Zwykłe odpytywanie to wspierana droga.

> **Jak się sprawy mają.** Zgodnie z EU Data Act (Rozporządzenie (UE) 2023/2854) dane Twojego samochodu należą *do Ciebie*. Uruchomienie tej integracji na własnym sprzęcie to *Ty* uzyskujący dostęp *do własnych* danych (Artykuł 4) — należnych w tej samej jakości, w jakiej producent udostępnia je sobie samemu, w czasie rzeczywistym tam, gdzie jest to technicznie wykonalne. Dzisiejszy portal VW — tylko do odczytu i przestarzały o godziny — nie spełnia tego wymogu. Ta integracja jest celowo **niezależna od kanału**: w chwili, gdy VW da właścicielom interfejs działający w czasie rzeczywistym i umożliwiający sterowanie — czego wymaga Data Act i co część producentów już oferuje swoim właścicielom — będziemy go tu wspierać, za darmo, dla wszystkich. Popieramy Twoje prawo do dostępu do własnego samochodu w czasie rzeczywistym.

---

## Instalacja

**Przez HACS (zalecane):**

1. Otwórz **HACS** w Home Assistant.
2. Wyszukaj **„VW Group Connect"** i zainstaluj.
3. Uruchom ponownie Home Assistant.
4. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację → VW Group Connect** i postępuj zgodnie z procesem logowania.

<sup>Właśnie scalono do domyślnego HACS — jeśli jeszcze nie da się jej wyszukać, daj indeksowi HACS chwilę na odświeżenie lub w międzyczasie dodaj `its-me-prash/vwgroup-connect-ha` jako repozytorium niestandardowe.</sup>

**Minimalna wersja Home Assistant: `2024.4.0`.**

### Opcje logowania (kreator konfiguracji ma dwie ścieżki)

Pierwszy ekran integracji oferuje **dwie** metody logowania. Wybierz tę, którą obsługuje Twoja marka:

- **Przeglądarka / device-code (bez hasła)** dla *Audi, Škody, SEAT-a, CUPR-y i Audi USA/CA (eksperymentalnie)*. Zaloguj się na telefonie lub laptopie i zatwierdź urządzenie; w Home Assistant nie jest przechowywane żadne hasło (trzyma prawdziwy refresh token). Ten krok oferuje też opcjonalny **S-PIN** i interwał skanowania.
- **Portal, e-mail + hasło** dla *Volkswagena EU, Volkswagena USA/CA, Bentleya i Porsche (eksperymentalnie)*. Podaj dane logowania swojej marki. Ten krok pokazuje wybór marki, e-mail, hasło, opcjonalny **S-PIN**, interwał skanowania oraz przełącznik **„włącz polecenia MBB"** (który działa tylko przy Volkswagenie EU, zobacz [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Dla **Volkswagena USA/Kanada** pojawia się tu **wybór kraju (USA lub CA)**; wyświetla się **tylko** dla tej marki i żadna inna go nie używa.

> **Portal EU Data Act nie jest trzecim przyciskiem logowania.** To strategia tylko do odczytu, na którą koordynator przełącza się automatycznie, i którą można dodatkowo *dodać* jako uzupełniający kanał odczytu przez **Konfiguruj → Opcje**. To samo dotyczy kanału webowego `volkswagen.de` (opcjonalna beta, tylko przez Opcje, tylko do odczytu) oraz opcjonalnego kanału **Tibber**, który uzupełnia pola pozostawione puste przez kanały własne i nigdy nie nadpisuje świeższych danych.

### Pole S-PIN — kiedy jest potrzebne

**S-PIN** to PIN bezpieczeństwa aplikacji Twojej marki. Jest opcjonalny w formularzu i wymagany tylko dla niektórych działań: jest potrzebny do **odczytów danych i poleceń VW US/Kanada** oraz do wrażliwych pod względem bezpieczeństwa zdalnych poleceń w markach, które zabezpieczają je S-PIN-em. Zostaw puste, jeśli Twój samochód o niego nie prosi.

---

### Volkswagen EU — uruchamianie przepływu danych (ważne)

Dla Volkswagen EU **samo zalogowanie nie wystarczy** — VW przesyła dane pojazdu dopiero wtedy, gdy *Ty* włączysz udostępnianie danych po stronie VW. Jeśli Twój samochód pojawia się bez danych (lub w ogóle się nie pojawia), to prawie zawsze jest tego przyczyną, a **nie** błędne hasło. Zrób to jednorazowo:

1. **Dodaj integrację:** wybierz **Portal (e-mail + hasło)** i wskaż **Volkswagen EU**, następnie zaloguj się.
2. **Wykonaj jednorazowe monity na portalu VW.** Otwórz portal danych VW raz w przeglądarce lub aplikacji marki i dokończ to, o co prosi: **zaakceptuj warunki, potwierdź zgodę, zakończ onboarding / wybór regionu.** Dostęp bezgłowy nie przejdzie przez te kroki — to przypadek `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Udziel zgody na udostępnianie danych.** Na portalu ustaw **„Use of non-personal data" = Granted** (zgoda na udostępnianie danych w ramach EU Data Act).
4. **Nie szukaj przełącznika „ciągłego żądania danych" — takiego nie ma.** Integracja sama tworzy takie żądanie dla każdego samochodu. Rejestruje przy tym miesięczną subskrypcję na Twoim koncie VW, która jest **bezpłatna**. Bez żądania portal nie zwraca nic dla danego VIN, a pojazd pojawia się bez odczytów.
5. **Poczekaj, aż samochód wyśle migawkę.** Nawet po wykonaniu wszystkich powyższych kroków propagacja zajmuje czas. Samochód może przez jakiś czas pokazywać **`offline` / `unknown` — często aż do następnej jazdy lub wybudzenia, do ~24 godz.** — zanim sensory się wypełnią. To normalne.

Portal początkowo udostępnia tylko **wycinek pól**, a ten wycinek **z czasem się poszerza**, gdy VW rozszerza zakres portalu przed terminem we wrześniu 2026 — pola, które dziś pokazują `unknown`, mogą wypełnić się same. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Pełna lista pól.** Kompletny oficjalny słownik danych grupy VW (każdy klucz EU Data Act -> pole, opis i jednostka) znajduje się w [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Cotygodniowy workflow obserwuje stronę słownika portalu i otwiera pull request, gdy VW opublikuje nowszą wersję, żeby tabela po cichu się nie zestarzała.

> To właśnie przełącznik Opcji **`eu_data_act_auto_kickoff`** tworzy owo 15-minutowe Custom Data Request i jest **domyślnie włączony** — w trybie portalowym bez niego nie ma danych. Wyłącz go tylko wtedy, gdy wolisz zarządzać żądaniem samodzielnie.

---

## Co otrzymujesz

- **Sensory:** SoC baterii, zasięg (elektryczny / spalinowy / łączny), poziom paliwa, przebieg, temperatury, moc ładowania, szybkość ładowania (zawsze w km/h, przeliczane jeśli auto raportuje w mph) i typ ładowania, cel ładowania, statystyki podróży i agregaty z całego okresu eksploatacji, interwały serwisowe i przeglądu oleju, wersja oprogramowania, stan połączenia, ostatnio widziany i więcej.
- **Sensory binarne:** drzwi zablokowane, drzwi/okna/bagażnik/maska/szyberdach otwarte, wtyczka podłączona, ładowanie, dostępna aktualizacja OTA, światła, pojazd online, timery odjazdu, alarm.
- **Sterowanie:** blokada/odblokowanie, start/stop klimatyzacji, start/stop ładowania, ogrzewanie okien, timery odjazdu, ustawienie docelowego SoC / temperatury / maksymalnego prądu ładowania, klakson-i-światła, wybudzenie, odświeżenie, wyszukiwanie stacji ładowania *(dostępność zależy od marki i modelu)*.
- **Tracker urządzeń:** pozycja GPS dla mapy Home Assistant. Odpytanie, które wróci bez współrzędnych, zachowuje ostatnią znaną pozycję parkowania, zamiast ją tracić.
- **Obrazy:** rendery pojazdu tam, gdzie marka je udostępnia.
- **Ustawienia:** suwak **interwału odpytywania** na konto, w minutach, żeby automatyzacja mogła odpytywać częściej w czasie jazdy i zwalniać na noc. Istnieje w każdej instalacji, także we wpisach portalowych tylko do odczytu.
- **12 języków:** nazwy encji są w pełni przetłumaczone na angielski, niemiecki, francuski, hiszpański, włoski, niderlandzki, polski, czeski, szwedzki, duński, norweski i fiński.

> 💡 **Panel energii:** sensor naładowanej energii jest typu `total_increasing`, więc dodaj go do **panelu Energii** Home Assistant bezpośrednio lub opakuj w helper `utility_meter`, aby uzyskać dzienne/miesięczne sumy naładowanej energii. Użyj do tego kumulacyjnego sensora **naładowanej energii (kWh)** — a nie sensorów wydajności na 100 km (te są średnimi, a nie licznikami).

### Usługi

Integracja dostarcza **ponad 20 wywołań usług** (`vag_connect.*`), wiele z nich specyficznych dla marki — *dostępność zależy od marki i modelu*. Wśród nich: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` i `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` oraz easter egg `show_vag`.

---

## evcc

[evcc](https://evcc.io) może pobierać stan naładowania, zasięg i status ładowania twojego auta prosto z Home Assistant, dzięki czemu ładowanie z nadwyżki fotowoltaicznej planuje się na podstawie prawdziwej baterii, a nie zgadywanki. W samej integracji nie działa nic dodatkowego: evcc czyta REST API Home Assistant. Ścieżka **odczytu** działa dla **wszystkich marek**, także dla aut VW EU / portalowych tylko do odczytu. Ścieżka **zapisu** (`chargeEnable`) działa tylko dla auta dwukierunkowego (Audi lub Škoda z żywym kanałem poleceń) i tylko wtedy, gdy evcc traktuje samo auto jako punkt ładowania. Przy prawdziwej inteligentnej ładowarce evcc potrzebuje wyłącznie ścieżki odczytu.

Gotowe przepisy `evcc.yaml` i jednorazowa konfiguracja są w [docs/EVCC.md](docs/EVCC.md). Ten konektor jest w wersji **beta**.

---

## ABRP (A Better Routeplanner) telemetria na żywo

Możesz przesyłać dane na żywo ze swojego samochodu do **[A Better Routeplanner](https://abetterrouteplanner.com/)**, aby planował trasy w oparciu o Twój rzeczywisty stan naładowania. Jest to **opcjonalne i domyślnie wyłączone** — nic nie opuszcza Twojej sieci, dopóki tego nie włączysz i faktycznie nie nastąpi wysyłka.

**1. Zdobądź dwa poświadczenia.**

- **`token`** (na pojazd) — otwórz aplikację ABRP → **Settings → your car → Live Data → „Generic" / other car** i skopiuj pokazany token.
- **`api_key`** (klucz deweloperski) — to klucz partnerski/deweloperski wydawany przez **iternio**, a *nie* coś, co przekazuje aplikacja. Poproś o niego iternio (ich formularz wniosku o klucz deweloperski/API). **Celowo nie dostarczamy klucza** — wpisanie na stałe klucza, którego nie jesteśmy właścicielem, byłoby podszywaniem się i osadziłoby cudzy sekret w publicznym repozytorium. Wklej swój własny.

**2. Włącz to.** Integracja → **Konfiguruj** → przewiń do sekcji **ABRP** → zaznacz *Enable ABRP telemetry push* i wklej obie wartości. Są walidowane jako para (otrzymasz błąd, jeśli ustawiona jest tylko jedna), przechowywane zamaskowane i **nigdy niezapisywane w logu**.

**3. Zautomatyzuj wysyłkę.** Zaimportuj dostarczony blueprint **„ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), wybierz swój pojazd i jego sensor **ABRP data changed** i gotowe. Blueprint wysyła tylko wtedy, gdy istnieje rzeczywiście nowa migawka (sensor binarny *ABRP data changed* jest idempotentnym wyzwalaczem — resetuje się po każdej udanej wysyłce, więc ta sama migawka nigdy nie jest wysyłana dwukrotnie).

Możesz też wywołać usługę **`vag_connect.abrp_send`** bezpośrednio (skieruj na urządzenie lub VIN; api_key/token pochodzą z opcji, chyba że przekażesz je w wywołaniu).

> 🔒 **Prywatność:** telemetria zawiera GPS. Opuszcza Twoją sieć tylko wtedy, gdy uruchamia się `abrp_send` (czyli gdy *Ty* to wyzwolisz / włączysz blueprint). Co wysyłamy: stan naładowania, stan ładowania, GPS, kurs, energia + pojemność, szacowany zasięg, temperatura otoczenia i baterii, przebieg. Czego celowo **nie** wysyłamy: niczego, czego nie potrafimy wiarygodnie zmierzyć (prędkość, napięcie/prąd pakietu HV, stan techniczny baterii) — pomijamy zamiast zgadywać.

---

## Opcje (Konfiguruj)

W **Ustawienia → Urządzenia i usługi → VW Group Connect → Konfiguruj** możesz dostosować:
interwał skanowania (dostępny też na żywo jako suwak interwału odpytywania), S-PIN (a także osobny S-PIN dla każdego pojazdu, gdy na koncie jest więcej niż jeden samochód), geokodowanie odwrotne, **tryb tylko do odczytu**, wymuszenie klimatyzacji PPE (Audi), przełączniki push (MQTT/FCM/Audi-VW, wszystkie opcjonalne, w wersji beta i domyślnie wyłączone), nadpisanie client-id, **`eu_data_act_auto_kickoff`** (domyślnie włączone), ukrywanie pustych encji (domyślnie włączone), **ABRP** (włączenie + api_key + token użytkownika, walidowane jako para), a także **dodawanie / usuwanie** uzupełniających kanałów odczytu: `volkswagen.de` (beta), portal EU Data Act i **Tibber**.

---

## Wesprzyj ten projekt ❤️

To projekt jednoosobowy — a VW nie ułatwia sprawy: każda zmiana backendu oznacza dni inżynierii wstecznej, aby ponownie znaleźć działającą ścieżkę. Ta wytrwałość jest tym, co utrzymuje go przy życiu tam, gdzie uznane projekty się poddały. Jeśli ma to dla Ciebie wartość, możesz wesprzeć dalsze utrzymanie przez **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Dziękuję! 🙏

---

## Współtworzenie

PR-y mile widziane, zobacz [`CONTRIBUTING.md`](CONTRIBUTING.md). Najczęstsze pytania są omówione w [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** zamienia nieznane pola API w gotowy, wstępnie wypełniony raport błędu jednym kliknięciem, więc możesz pomóc poprawić pokrycie bez czytania kodu.

## Licencja

[GNU AGPL v3.0-or-later](LICENSE) dla kodu integracji. Obowiązkowe warunki atrybucji + nazwy/znaku towarowego przy używaniu/forkowaniu: zobacz [`ATTRIBUTION.md`](ATTRIBUTION.md). Atrybucje open-source wobec projektów zewnętrznych w [`NOTICE.md`](NOTICE.md).
