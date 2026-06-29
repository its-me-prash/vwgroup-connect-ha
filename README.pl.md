<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Jedna integracja Home Assistant dla wszystkich siedmiu marek Grupy Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW USA/Kanada</strong><br>
  <em>Bezpośredni dostęp do API, wiele kanałów z automatycznym przełączaniem, bez warstw pośrednich.</em>
</p>

<p align="center">
  <a href="https://github.com/sponsors/its-me-prash"><img src="https://img.shields.io/badge/%E2%9D%A4%20Sponsor-ec6cb9?logo=github-sponsors&logoColor=white" alt="Sponsor this project"></a>
  <a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg" alt="HACS Default"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?include_prereleases" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-AGPL%20v3-blue.svg" alt="License"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  🌍 <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Słowo o zmianie nazwy
> Wcześniej publikowane jako **`vag-connect-ha`** (VAG = Volkswagen AG, standardowy skrót w krajach niemieckojęzycznych).
> Okazało się, że dla anglojęzycznych ten skrót brzmi *zupełnie* inaczej 😅
>
> **Co działa tak jak wcześniej**: wszystkie encje (np. `sensor.audi_q4_battery_soc`),
> wszystkie wywołania usług (`vag_connect.lock`, `vag_connect.show_vag` itd.), wszystkie automatyzacje,
> instalacja przez HACS — **nic się nie psuje**. Zmienia się nazwa marketingowa/wyświetlana, a wnętrze kodu
> pozostaje bez zmian. Zobacz [`MIGRATION.md`](MIGRATION.md).
>
> Ogromne podziękowania dla społeczności **Home Assistant UK** oraz **HA Ideas, Projects and Solutions**
> za zwrócenie uwagi — szczególnie dla **Si Gregory**, **Ben Johnson** i **Evets David**.
>
> I specjalne ukłony w stronę **Jordan Waeles**, którego komentarz `show_vag()` jest teraz oficjalnie
> wspieranym easter eggiem tej integracji (usługa `vag_connect.show_vag`, zobacz CHANGELOG v2.2.3).

---

## Co to jest?

**VW Group Connect to integracja [Home Assistant](https://www.home-assistant.io), która wnosi dane i sterowanie połączonym autem do Twojego inteligentnego domu dla wszystkich siedmiu marek Grupy Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche i VW USA/Kanada — plus Bentley (tylko odczyt), z jednego wpisu konfiguracyjnego.**

Pokazuje stan baterii i ładowania, zasięg, przebieg, klimatyzację, drzwi i okna, lokalizację i więcej, a tam, gdzie backend marki wciąż na to pozwala — wysyła zdalne polecenia, takie jak zamykanie/otwieranie, sterowanie klimatyzacją i ładowaniem. Aby działać mimo zmian w API Volkswagena z 2026 roku, korzysta z **kilku kanałów i automatycznie przełącza się**, gdy jeden zostanie zablokowany: natywnych backendów marek, portalu danych pojazdów **EU Data Act** (tylko odczyt), opcjonalnego kanału webowego `volkswagen.de` oraz trwałego logowania **bez hasła** dla starszych pojazdów Car-Net. Działa bezproblemowo **obok [evcc](https://evcc.io)** i nie wymaga **żadnych zależności z PyPI**.

> 🎉 **Teraz dostępne bezpośrednio w HACS** — bez potrzeby dodawania własnego repozytorium.

---

## Najważniejsze cechy

- **Wszystkie 7 marek Grupy VW, w tym Porsche i VW USA/Kanada** w jednej integracji — portal EU Data Act z założenia *wyklucza* Porsche, więc narzędzia oparte wyłącznie na portalu nigdy go nie obsłużą.
- **Dwukierunkowe sterowanie** tam, gdzie marka na to pozwala (zamykanie/otwieranie, klimatyzacja, ładowanie, docelowy SoC) — nie tylko odczyty.
- **Opcja logowania bez hasła** (przeglądarka / kod urządzenia) — żadne hasło nie jest przechowywane w Home Assistant.
- **Wiele kanałów z automatycznym przełączaniem** — natywny backend marki → portal EU Data Act → opcjonalny kanał webowy vw.de → trwały Car-Net. Awaria jednego kanału nie pozbawia Cię danych.
- **Odporny z założenia** — zachowuje ostatnio znane wartości podczas awarii portalu, odfiltrowuje fałszywe wartości „brak odczytu", nigdy nie pozwala, by przebieg cofnął się wstecz.
- **Lokalizator GPS**, ponad 100 encji w 11 platformach, ponad 20 wywołań usług, wiele pojazdów na koncie.
- **Vehicle Data Scout** — automatycznie wykrywa zmiany w API i oferuje zgłoszenie błędu jednym kliknięciem. **Quality Scale: Platinum.**

---

## Status marek

| Marka | Sterowanie | Dane | Uwagi |
|---|---|---|---|
| **Audi** | ✅ Dwukierunkowe | ✅ Pełne | backend myAudi |
| **Škoda** | ✅ Dwukierunkowe | ✅ Pełne | natywny backend Škoda |
| **Porsche** | ✅ Dwukierunkowe | ✅ Pełne | Porsche Connect |
| **VW USA/KA** | ✅ Dwukierunkowe | ✅ Pełne | chmura VW NA |
| **VW EU** | ⚠️ Trwały Car-Net (starsze modele) | ✅ EU Data Act + vw.de (beta) | nowsze auta ID/MEB: tylko odczyt przez portal |
| **CUPRA / SEAT** | ⚠️ Ograniczone | ✅ EU Data Act | backend marki zablokowany przez VW od 2026 |
| **Bentley** | ⏳ Czeka na testy na żywo | ✅ Logowanie + odczyt | My Bentley — działa na platformie/tenancie Audi |

> Szczerze: w 2026 roku Volkswagen schował części swojego API za atestacją urządzeń. Ta integracja obchodzi to tam, gdzie się da (trwałe logowanie Car-Net, portal EU Data Act, web vw.de) i otwarcie mówi, co każdy kanał może, a czego nie może zrobić.

---

## Znane ograniczenia

Kilka rzeczy ma charakter **strukturalny** — wynikają z tego, jak działają backendy Volkswagena w 2026 roku, a nie z samej integracji, i żadne ustawienie ich nie naprawi:

- **Auta z rodziny MEB / ID są tylko do odczytu** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Zdalne polecenia — zamykanie, klimatyzacja, ładowanie — **nie są dostępne** dla tych aut: trwała ścieżka poleceń Car-Net, której używamy, ich nie rozpoznaje (odpowiada „Unknown user"), a backend MEB Volkswagena nie udostępnia odpowiednika. Telemetrię nadal otrzymujesz przez portal EU Data Act — po prostu bez sterowania. Konfiguracja wykrywa to i tworzy **wpis tylko do odczytu** zamiast zgłaszać błąd, więc jest to ograniczenie znane, a nie ukryte.
- **Zdalne polecenia CUPRA / SEAT są zablokowane przez VW.** Dostęp do usług online (OLA) dla tych marek został cofnięty po stronie serwera w 2026 roku (HTTP 403); ponowne logowanie ani aktualizacja wersji aplikacji tego nie przywrócą. Dane wciąż płyną przez portal EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Dane z portalu EU Data Act są skąpe i różnią się w zależności od auta.** VW publikuje dziś tylko część pól (często przebieg + zamki + ładowanie, czasem znacznie więcej). Z czasem zakres się poszerza, bo VW rozbudowuje portal przed terminem we wrześniu 2026 — pola, które dziś pokazują `unknown`, mogą same się wypełnić, bez żadnej zmiany. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Instalacja

**Przez HACS (zalecane):**

1. Otwórz **HACS** w Home Assistant.
2. Wyszukaj **„VW Group Connect"** i zainstaluj.
3. Uruchom ponownie Home Assistant.
4. Przejdź do **Ustawienia → Urządzenia i usługi → Dodaj integrację → VW Group Connect** i przejdź przez proces logowania.

<sup>Dopiero co dołączone do domyślnego HACS — jeśli jeszcze nie da się tego wyszukać, daj indeksowi HACS chwilę na odświeżenie albo w międzyczasie dodaj `its-me-prash/vwgroup-connect-ha` jako własne repozytorium.</sup>

**Opcje logowania** (wybierz to, co obsługuje Twoje auto/marka):
- **Przeglądarka / kod urządzenia (bez hasła)** — zaloguj się na telefonie lub laptopie, zatwierdź urządzenie; żadne hasło nie jest przechowywane. (Audi, Škoda, SEAT, CUPRA.)
- **E-mail + hasło** — wymagane dla Volkswagena EU i Porsche.
- **Portal EU Data Act** — awaryjny tryb tylko do odczytu dla wszystkich marek.

---

## Co dostajesz

- **Czujniki:** SoC baterii, zasięg (elektryczny / spalinowy / łączny), poziom paliwa, przebieg, temperatury, moc/szybkość/typ ładowania, cel ładowania, statystyki tras i sumy z całego okresu, interwały serwisu i wymiany oleju, wersja oprogramowania, stan połączenia, ostatnio widziano i więcej.
- **Czujniki binarne:** zamknięte drzwi, otwarte drzwi/okna/bagażnik/maska/szyberdach, podłączona wtyczka, ładowanie, dostępna aktualizacja OTA, światła, pojazd online, programatory odjazdu, alarm.
- **Sterowanie:** zamykanie/otwieranie, start/stop klimatyzacji, start/stop ładowania, ogrzewanie szyb, programatory odjazdu, ustawianie docelowego SoC / temperatury / maks. prądu ładowania, sygnał i mignięcie świateł, wybudzanie, odświeżanie, wyszukiwanie stacji ładowania *(dostępność zależy od marki i modelu)*.
- **Lokalizator:** pozycja GPS na mapie Home Assistant.
- **Obrazy:** wizualizacje pojazdu tam, gdzie marka je udostępnia.

> 💡 **Panel energii:** czujnik naładowanej energii jest typu `total_increasing`, więc dodaj go bezpośrednio do **panelu energii** Home Assistant albo opakuj w pomocnika `utility_meter`, żeby uzyskać dzienne/miesięczne sumy naładowanej energii. Użyj do tego skumulowanego czujnika **naładowanej energii (kWh)** — nie czujników zużycia na 100 km (te podają średnie, a nie zliczają).

---

## Wesprzyj ten projekt ❤️

To projekt jednej osoby — a VW nie ułatwia sprawy: każda zmiana backendu oznacza dni inżynierii wstecznej, żeby znów znaleźć działającą ścieżkę. To właśnie ta wytrwałość trzyma go przy życiu tam, gdzie uznane projekty już się poddały. Jeśli coś dla Ciebie znaczy, możesz wesprzeć dalsze utrzymanie przez **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Dziękuję! 🙏

---

## Współtworzenie

PR-y mile widziane — zobacz [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** zamienia nieznane pola API w gotowe, wstępnie wypełnione zgłoszenie błędu jednym kliknięciem, więc możesz pomóc poprawić pokrycie bez czytania kodu.

## Licencja

[GNU AGPL v3.0-or-later](LICENSE) dla kodu integracji. Obowiązkowe warunki atrybucji oraz nazwy/znaku towarowego przy użyciu/forku: zobacz [`ATTRIBUTION.md`](ATTRIBUTION.md). Atrybucje open-source komponentów zewnętrznych w [`NOTICE.md`](NOTICE.md).