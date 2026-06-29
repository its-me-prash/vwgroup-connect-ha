<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Eén Home Assistant-integratie voor alle zeven merken van de Volkswagen-groep — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW VS/Canada</strong><br>
  <em>Directe API-toegang, meerdere kanalen met automatische terugval, geen tussenlaag.</em>
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
  🌍 <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Opmerking over de naamswijziging
> Eerder uitgebracht als **`vag-connect-ha`** (VAG = Volkswagen AG, de standaardafkorting in de DACH-regio).
> Blijkt dat die afkorting *nogal* anders klinkt voor Engelstaligen 😅
>
> **Wat gewoon blijft werken als voorheen**: alle entiteiten (bijv. `sensor.audi_q4_battery_soc`),
> alle serviceaanroepen (`vag_connect.lock`, `vag_connect.show_vag` enz.), alle automatiseringen,
> de HACS-installatie — **er gaat niets stuk**. Alleen de marketing-/weergavenaam verandert, de
> interne code blijft ongewijzigd. Zie [`MIGRATION.md`](MIGRATION.md).
>
> Grote dank aan de communities **Home Assistant UK** en **HA Ideas, Projects and Solutions**
> voor de tip — in het bijzonder **Si Gregory**, **Ben Johnson** en **Evets David**.
>
> En een speciale shout-out naar **Jordan Waeles**, wiens `show_vag()`-comment nu een officieel
> ondersteunde easter egg in deze integratie is (`vag_connect.show_vag`-service, zie CHANGELOG v2.2.3).

---

## Wat is dit?

**VW Group Connect is een [Home Assistant](https://www.home-assistant.io)-integratie die de gegevens en bediening van je connected car naar je smart home brengt, voor alle zeven merken van de Volkswagen-groep — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche en VW VS/Canada — plus Bentley (alleen-lezen), vanuit één enkele configuratie.**

Ze toont de accu- en laadstatus, het rijbereik, de kilometerstand, de klimaatregeling, deuren en ramen, de locatie en meer — en, waar de backend van het merk dat nog toelaat, stuurt ze opdrachten op afstand zoals vergrendelen/ontgrendelen, klimaat- en laadbediening. Om te blijven werken doorheen de API-wijzigingen van Volkswagen in 2026 spreekt ze **meerdere kanalen en valt ze automatisch terug** wanneer er één wordt geblokkeerd: de merkeigen backends, het alleen-lezen voertuigdataportaal van de **EU Data Act**, een optioneel `volkswagen.de`-webkanaal, en een duurzame **wachtwoordloze** login voor oudere Car-Net-voertuigen. Ze draait probleemloos **naast [evcc](https://evcc.io)** en heeft **nul PyPI-afhankelijkheden** nodig.

> 🎉 **Nu rechtstreeks beschikbaar in HACS** — geen custom repository meer nodig.

---

## Hoogtepunten

- **Alle 7 merken van de VW-groep incl. Porsche & VW VS/Canada** in één integratie — het EU Data Act-portaal sluit Porsche structureel *uit*, dus tools die enkel op het portaal steunen, kunnen het nooit dekken.
- **Tweerichtingsbediening** waar het merk dat toelaat (vergrendelen/ontgrendelen, klimaat, laden, doel-SoC) — niet alleen lezen.
- **Optie voor wachtwoordloze login** (browser/apparaatcode) — geen wachtwoord opgeslagen in Home Assistant.
- **Meerdere kanalen met automatische terugval** — merkeigen → EU Data Act-portaal → optioneel vw.de-web → duurzaam Car-Net. Als één kanaal uitvalt, blijven je gegevens niet in het donker.
- **Veerkrachtig van opzet** — behoudt de laatst bekende waarden bij portaalstoringen, filtert nep-"geen meting"-waarden eruit, en laat de kilometerstand nooit achteruit springen.
- **GPS-apparaattracker**, 100+ entiteiten verdeeld over 11 platforms, 20+ serviceaanroepen, meerdere voertuigen per account.
- **Vehicle Data Scout** — detecteert automatisch API-drift en biedt een bugmelding met één klik. **Quality Scale: Platinum.**

---

## Merkstatus

| Merk | Bediening | Gegevens | Opmerkingen |
|---|---|---|---|
| **Audi** | ✅ Tweerichting | ✅ Volledig | myAudi-backend |
| **Škoda** | ✅ Tweerichting | ✅ Volledig | merkeigen Škoda-backend |
| **Porsche** | ✅ Tweerichting | ✅ Volledig | Porsche Connect |
| **VW VS/CA** | ✅ Tweerichting | ✅ Volledig | VW NA-cloud |
| **VW EU** | ⚠️ Duurzaam Car-Net (oudere modellen) | ✅ EU Data Act + vw.de (bèta) | nieuwere ID/MEB-auto's: alleen-lezen via portaal |
| **CUPRA / SEAT** | ⚠️ Beperkt | ✅ EU Data Act | merkbackend door VW afgegrendeld sinds 2026 |
| **Bentley** | ⏳ Wacht op livetest | ✅ Login + lezen | My Bentley — draait op het platform/tenant van Audi |

> Eerlijk gezegd: in 2026 heeft Volkswagen delen van zijn API achter apparaatattestatie geplaatst. Deze integratie omzeilt dat waar mogelijk (duurzame Car-Net-login, EU Data Act-portaal, vw.de-web) en is transparant over wat elk kanaal wel en niet kan.

---

## Bekende beperkingen

Een paar zaken zijn **structureel** — ze komen voort uit hoe de backends van Volkswagen werken in 2026, niet uit de integratie, en geen enkele instelling lost ze op:

- **MEB-/ID-auto's zijn alleen-lezen** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Opdrachten op afstand — vergrendelen, klimaat, laden — zijn voor deze auto's **niet beschikbaar**: het duurzame Car-Net-commandopad dat we gebruiken herkent ze niet (het antwoordt "Unknown user"), en de MEB-backend van VW biedt geen equivalent. Je krijgt nog steeds telemetrie via het EU Data Act-portaal — alleen geen bediening. De installatie detecteert dit en maakt in plaats van te falen een **alleen-lezen-vermelding** aan, zodat het een bekende beperking is en geen stille.
- **Opdrachten op afstand voor CUPRA / SEAT worden door VW geblokkeerd.** De toegang tot de online diensten (OLA) voor deze merken werd in 2026 aan de serverzijde ingetrokken (HTTP 403); opnieuw inloggen of een nieuwere app-versie herstelt dat niet. Gegevens blijven binnenkomen via het EU Data Act-portaal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **De gegevens van het EU Data Act-portaal zijn mager en verschillen per auto.** VW publiceert vandaag slechts een deel van de velden (vaak kilometerstand + vergrendeling + laden, soms veel meer). Dat breidt na verloop van tijd uit naarmate VW het portaal uitbouwt richting de deadline van september 2026 — velden die vandaag `unknown` tonen, kunnen vanzelf ingevuld raken, zonder dat er iets hoeft te veranderen. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Installeren

**Via HACS (aanbevolen):**

1. Open **HACS** in Home Assistant.
2. Zoek naar **“VW Group Connect”** en installeer ze.
3. Herstart Home Assistant.
4. Ga naar **Instellingen → Apparaten & diensten → Integratie toevoegen → VW Group Connect** en volg de loginstappen.

<sup>Net samengevoegd in de HACS-standaard — als ze nog niet doorzoekbaar is, geef de HACS-index dan even tijd om te verversen, of voeg in de tussentijd `its-me-prash/vwgroup-connect-ha` toe als custom repository.</sup>

**Login-opties** (kies wat je auto/merk ondersteunt):
- **Browser / apparaatcode (wachtwoordloos)** — meld je aan op je telefoon of laptop en keur het apparaat goed; geen wachtwoord opgeslagen. (Audi, Škoda, SEAT, CUPRA.)
- **E-mail + wachtwoord** — vereist voor Volkswagen EU en Porsche.
- **EU Data Act-portaal** — alleen-lezen terugval voor alle merken.

---

## Wat je krijgt

- **Sensoren:** accu-SoC, rijbereik (elektrisch / verbranding / totaal), brandstofpeil, kilometerstand, temperaturen, laadvermogen/-snelheid/-type, laaddoel, ritstatistieken & totaaltellers, onderhouds- en olieserviceintervallen, softwareversie, verbindingsstatus, laatst gezien, en meer.
- **Binaire sensoren:** deuren vergrendeld, deuren/ramen/kofferbak/motorkap/schuifdak open, stekker aangesloten, aan het laden, OTA-update beschikbaar, verlichting, voertuig online, vertrektimers, alarm.
- **Bediening:** vergrendelen/ontgrendelen, klimaat starten/stoppen, laden starten/stoppen, ruitverwarming, vertrektimers, doel-SoC / temperatuur / max. laadstroom instellen, claxonneren en knipperen, wekken, verversen, laadstations vinden *(beschikbaarheid afhankelijk van merk & model)*.
- **Apparaattracker:** GPS-positie voor de kaart van Home Assistant.
- **Afbeeldingen:** voertuigafbeeldingen waar het merk ze aanlevert.

> 💡 **Energiedashboard:** de sensor voor geladen energie is `total_increasing`, dus voeg ze rechtstreeks toe aan het **Energiedashboard** van Home Assistant, of verpak ze in een `utility_meter`-helper voor dagelijkse/maandelijkse totalen van geladen energie. Gebruik hiervoor de cumulatieve sensor **geladen energie (kWh)** — niet de efficiëntiesensoren per 100 km (dat zijn gemiddelden, geen meters).

---

## Steun dit project ❤️

Dit is een eenmansproject — en VW maakt het me niet makkelijk: elke backend-wijziging betekent dagen reverse-engineeren om opnieuw een werkend pad te vinden. Net die volharding houdt het in leven waar gevestigde projecten het hebben opgegeven. Als het voor jou iets waard is, kun je het doorlopende onderhoud steunen via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Bedankt! 🙏

---

## Bijdragen

PR's zijn welkom — zie [`CONTRIBUTING.md`](CONTRIBUTING.md). De **Vehicle Data Scout** zet onbekende API-velden om in een vooraf ingevulde bugmelding met één klik, zodat je de dekking kunt helpen verbeteren zonder code te lezen.

## Licentie

[GNU AGPL v3.0-or-later](LICENSE) voor de integratiecode. Verplichte naamsvermelding + naam-/handelsmerkvoorwaarden bij gebruik/fork: zie [`ATTRIBUTION.md`](ATTRIBUTION.md). Naamsvermeldingen van upstream-opensource in [`NOTICE.md`](NOTICE.md).