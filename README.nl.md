<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Eén Home Assistant-integratie voor de merken van de Volkswagen Group — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW VS/Canada · Bentley</strong><br>
  <em>Directe API-toegang, multi-channel met automatische fallback, geen middleware.</em>
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
  🌍 <a href="README.de.md">Deutsch</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Opmerking over de naamswijziging
> Eerder gepubliceerd als **`vag-connect-ha`** (VAG = Volkswagen AG, de standaard DACH-afkorting).
> Blijkt dat die afkorting *behoorlijk* anders overkomt bij Engelstaligen 😅
>
> **Wat blijft werken zoals voorheen**: alle entiteiten (bijv. `sensor.audi_q4_battery_soc`),
> alle service-calls (`vag_connect.lock`, `vag_connect.show_vag` enz.), alle automatiseringen,
> de HACS-installatie — **er gaat niets stuk**. De marketing-/weergavenaam verandert, de
> code-internals blijven ongewijzigd. Zie [`MIGRATION.md`](MIGRATION.md).
>
> Grote dank aan de communities **Home Assistant UK** en **HA Ideas, Projects and Solutions**
> voor de tip — in het bijzonder **Si Gregory**, **Ben Johnson** en **Evets David**.
>
> En een speciale shoutout naar **Jordan Waeles**, wiens `show_vag()`-commentaar nu een officieel
> ondersteunde easter egg in deze integratie is (`vag_connect.show_vag`-service, zie CHANGELOG v2.2.3).

---

## Wat is dit?

**VW Group Connect is een [Home Assistant](https://www.home-assistant.io)-integratie die connected-car-data en -bediening naar je smart home brengt voor de merken van de Volkswagen Group — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW VS/Canada en Bentley — vanuit één config entry.**

Het toont de batterij- & laadstatus, actieradius, kilometerstand, klimaat, deuren & ramen, locatie en meer, en — waar de backend van het merk het nog toelaat — stuurt het commando's op afstand zoals vergrendelen/ontgrendelen, klimaat- en laadbediening. Om te blijven werken door de API-wijzigingen van Volkswagen in 2026 spreekt het **meerdere kanalen en valt automatisch terug** wanneer er een wordt geblokkeerd: de merkeigen backends, het read-only **EU Data Act**-voertuigdataportaal, een opt-in `volkswagen.de`-webkanaal en een duurzame **wachtwoordloze** login voor oudere Car-Net-voertuigen. Het draait probleemloos **naast [evcc](https://evcc.io)** en heeft **nul PyPI-dependencies** nodig.

> 🎉 **Nu rechtstreeks beschikbaar in HACS** — geen custom repository nodig.

---

## Hoogtepunten

- **8 selecteerbare merken van de Volkswagen Group** in één integratie — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW VS/Canada, Porsche en Bentley.
- **Porsche-compatibel** — Porsche draait op zijn eigen *Porsche Connect*-backend, **niet** op het EU Data Act-portaal. Het portaalpad sluit Porsche structureel *uit*, dus portaal-only tools kunnen het nooit dekken; deze integratie wel.
- **Tweewegbediening waar de backend van het merk het toelaat** — vergrendelen/ontgrendelen, klimaat, laden, doel-SoC. Lees in de tabel hieronder welke merken echte commando-ondersteuning hebben; VW EU is standaard read-only (zie de eerlijke opmerking daar).
- **Wachtwoordloze login-optie** (browser/device-code) voor Audi/Škoda/SEAT/CUPRA — geen wachtwoord opgeslagen in Home Assistant.
- **Multi-channel met auto-fallback** — merkeigen → EU Data Act-portaal → opt-in vw.de-web → duurzaam Car-Net. Eén kanaal dat uitvalt zet je data niet op zwart.
- **Veerkrachtig van opzet** — behoudt de laatst bekende waarden tijdens portaalstoringen, filtert valse "geen meting"-sentinels en laat de kilometerstand nooit achteruit springen.
- **GPS device tracker**, 100+ entiteiten over meerdere platforms, 20+ service calls, meerdere voertuigen per account.
- **Vehicle Data Scout** — detecteert automatisch API-drift en biedt een bugrapport met één klik. **Quality Scale: Platinum.**

---

## Merkstatus

| Merk | Bediening | Data | Opmerkingen |
|---|---|---|---|
| **Audi** | ✅ Tweeweg | ✅ Volledig | myAudi-backend (incl. start/stop ICE-motor) |
| **Škoda** | ✅ Tweeweg | ✅ Volledig | native Škoda-backend |
| **Porsche** | ✅ Tweeweg | ✅ Volledig | Porsche Connect — eigen backend, niet het EU Data Act-portaal |
| **VW VS/CA** | ✅ Tweeweg | ✅ Volledig | VW NA-cloud (vereist de VS/CA-landkeuze + S-PIN) |
| **VW EU** | 🔒 Standaard read-only · ⚠️ commando's = MBB **alpha** | ✅ Volledige telemetrie via EU Data Act-portaal | Zie de eerlijke opmerking hieronder — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Commando's geblokkeerd door VW | ✅ EU Data Act-portaal | OLA-toegang server-side ingetrokken in 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Tweeweg achter live-test-gate | ✅ Login + uitlezen | My Bentley — draait op de Audi/IDK-tenant |

> **Eerlijke opmerking over VW EU-bediening.** Volkswagen EU-voertuigen zijn **standaard read-only**: je krijgt volledige telemetrie via het EU Data Act-portaal, maar geen commando's op afstand. Commando's op afstand voor VW EU bestaan **alleen als een experimentele duurzame-MBB-tweeweg-ALPHA**, en alleen voor **legacy MQB / Car-Net**-auto's — het is een opt-in-schakelaar, **geen** standaardfunctie. **MEB / ID-familie-auto's (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) hebben helemaal geen commandopad** en worden read-only aangemaakt. De MBB-alpha wordt gevolgd in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testers welkom.

> In 2026 plaatste Volkswagen delen van zijn API achter device attestation. Deze integratie omzeilt dat waar mogelijk (duurzame Car-Net-login, EU Data Act-portaal, vw.de-web) en is transparant over wat elk kanaal wel en niet kan.

---

## Bekende beperkingen

Een paar dingen zijn **structureel** — ze komen voort uit hoe Volkswagens backends in 2026 werken, niet uit de integratie, en geen enkele instelling lost ze op:

- **VW EU is standaard read-only; commando's zijn een MBB-alpha en alleen voor legacy-auto's.** Zie de merkopmerking hierboven. **MEB / ID-familie-auto's zijn read-only** — het duurzame Car-Net-commandopad herkent ze niet (het antwoordt "Unknown user"), en VW's MEB-backend biedt geen equivalent. De setup detecteert dit en maakt een **read-only entry** aan (met een reparatiemelding) in plaats van te falen, dus het is een bekende beperking, geen stille. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-commando's op afstand worden door VW geblokkeerd.** De online-services-toegang (OLA) voor deze merken is in 2026 server-side ingetrokken (HTTP 403); opnieuw inloggen of een app-versie-bump herstelt dit niet. Data blijft stromen via het EU Data Act-portaal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **De data van het EU Data Act-portaal is mager en verschilt per auto.** VW publiceert vandaag slechts een deel van de velden (vaak kilometerstand + vergrendeling + laden, soms veel meer). Het wordt na verloop van tijd ruimer naarmate VW het portaal uitbreidt richting de deadline van september 2026 — velden die vandaag `unknown` tonen, kunnen vanzelf invullen, zonder dat er iets hoeft te veranderen. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

> **Waar we staan.** Onder de EU Data Act (Verordening (EU) 2023/2854) is de data van je auto *van jou*. Deze integratie op je eigen hardware draaien is *jij* die *je eigen* data raadpleegt (Artikel 4) — waar je recht op hebt in dezelfde kwaliteit als de fabrikant zichzelf bedient, in real time waar dat technisch haalbaar is. VW's alleen-lezen portaal, dat uren achterloopt, schiet daar vandaag tekort in. Deze integratie is bewust **kanaal-agnostisch**: op het moment dat VW eigenaren een real-time, bedienbare interface geeft — zoals de Data Act vereist, en zoals sommige fabrikanten hun eigenaren al bieden — ondersteunen we die hier, gratis, voor iedereen. Wij staan achter jouw recht op real-time toegang tot je eigen auto.

---

## Installeren

**Via HACS (aanbevolen):**

1. Open **HACS** in Home Assistant.
2. Zoek naar **"VW Group Connect"** en installeer het.
3. Herstart Home Assistant.
4. Ga naar **Instellingen → Apparaten & services → Integratie toevoegen → VW Group Connect** en volg de login-flow.

<sup>Net samengevoegd in de HACS-default — als het nog niet doorzoekbaar is, geef de HACS-index even tijd om te verversen, of voeg in de tussentijd `its-me-prash/vwgroup-connect-ha` toe als custom repository.</sup>

**Minimale Home Assistant: `2024.4.0`.**

### Login-opties (de setup-wizard heeft twee paden)

Het eerste scherm van de integratie biedt **twee** loginmethoden. Kies degene die jouw merk ondersteunt:

- **Browser / device-code (wachtwoordloos)** — *Audi · Škoda · SEAT · CUPRA.* Log in op je telefoon of laptop en keur het apparaat goed; er wordt geen wachtwoord opgeslagen in Home Assistant (het bewaart een echte refresh token). Deze stap biedt ook de optionele **S-PIN**, het scaninterval en force-access-velden.
- **Portaal — e-mail + wachtwoord** — *Volkswagen EU · Porsche.* Voer je merklogin in. Deze stap toont een merkkeuze (Volkswagen EU, Porsche en de andere e-mail/wachtwoord-merken), e-mail, wachtwoord, optionele **S-PIN**, scaninterval, force-access en een **"MBB-commando's inschakelen"**-schakelaar (die alleen effect heeft op Volkswagen EU — zie [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Voor **Volkswagen VS/Canada** verschijnt hier een **landkeuze (VS vs CA)** — die wordt **alleen** voor dat merk getoond en wordt door geen enkel ander merk gebruikt.

> Het **EU Data Act-portaal is geen derde login-knop.** Het is de read-only-strategie waar de coordinator automatisch op terugvalt, en het kan daarnaast als aanvullend leeskanaal worden *toegevoegd* via **Configureren → Opties**. Hetzelfde geldt voor het `volkswagen.de`-webkanaal (een opt-in, alleen via Opties beschikbaar aanvullend leeskanaal).

### Het S-PIN-veld — wanneer je het nodig hebt

De **S-PIN** is de beveiligings-PIN van de app van je merk. Hij is optioneel in het formulier en alleen vereist voor bepaalde acties: hij is nodig voor **VW VS/Canada-datalezingen en -commando's**, en voor beveiligingsgevoelige commando's op afstand bij merken die ze achter de S-PIN afschermen. Laat het leeg als je auto er niet om vraagt.

---

### Volkswagen EU — je data laten stromen (belangrijk)

Voor Volkswagen EU is **inloggen niet genoeg** — VW streamt voertuigdata pas zodra *jij* het delen van data aan VW's kant hebt ingeschakeld. Als je auto zonder data verschijnt (of helemaal niet verschijnt), is dit vrijwel altijd de reden, **niet** een verkeerd wachtwoord. Doe dit één keer:

1. **Voeg de integratie toe:** kies **Portaal (e-mail + wachtwoord)** en selecteer **Volkswagen EU**, en log dan in.
2. **Voltooi elke eenmalige prompt op VW's portaal.** Open het VW-dataportaal één keer in een browser of de merk-app en doorloop wat het vraagt: **accepteer voorwaarden, bevestig toestemming, voltooi onboarding / regiokeuze.** Headless-toegang komt hier niet voorbij — dit is het `portal_interaction_required`-geval ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Geef toestemming voor het delen van data.** Zet op het portaal **"Gebruik van niet-persoonsgebonden data" = Granted** (de toestemming voor het delen van data onder de EU Data Act).
4. **Schakel het continue dataverzoek** voor de specifieke auto in. Zonder dit retourneert het portaal *geen dataverzoek* voor die VIN en verschijnt het voertuig zonder metingen.
5. **Wacht tot de auto een snapshot pusht.** Zelfs na al het bovenstaande kost propagatie tijd. De auto kan **een tijdje `offline` / `unknown` tonen — vaak tot zijn volgende rit of wake, tot ~24 u** — voordat de sensoren zich vullen. Dit is normaal.

Het portaal levert aanvankelijk slechts een **deel van de velden**, en dat deel **wordt na verloop van tijd ruimer** naarmate VW de portaaldekking uitbreidt richting de deadline van september 2026 — velden die vandaag `unknown` tonen, kunnen vanzelf invullen. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Optioneel:** de Opties-schakelaar **`eu_data_act_auto_kickoff`** kan het Custom Data Request van 15 minuten automatisch voor je aanmaken. Het is opt-in omdat het aanmaken ervan een **abonnement van 1 maand op je VW-account** impliceert, dus de integratie doet het niet zonder jouw toestemming.

---

## Wat je krijgt

- **Sensoren:** batterij-SoC, actieradius (elektrisch / verbranding / totaal), brandstofniveau, kilometerstand, temperaturen, laadvermogen/-snelheid/-type, laaddoel, ritstatistieken & levenslange totalen, service- & olieservice-intervallen, softwareversie, verbindingsstatus, laatst gezien, en meer.
- **Binaire sensoren:** deuren vergrendeld, deuren/ramen/kofferbak/motorkap/schuifdak open, stekker aangesloten, ladend, OTA-update beschikbaar, lichten, voertuig online, vertrektimers, alarm.
- **Bediening:** vergrendelen/ontgrendelen, klimaat starten/stoppen, laden starten/stoppen, ruitverwarming, vertrektimers, doel-SoC / temperatuur / max. laadstroom instellen, claxon-en-knipper, wake, refresh, laadstations zoeken *(beschikbaarheid hangt af van merk & model)*.
- **Device tracker:** GPS-positie voor de Home Assistant-kaart.
- **Afbeeldingen:** voertuig-renders waar het merk ze levert.

> 💡 **Energiedashboard:** de geladen-energie-sensor is `total_increasing`, dus voeg hem rechtstreeks toe aan het Home Assistant-**Energiedashboard**, of verpak hem in een `utility_meter`-helper voor dagelijkse/maandelijkse geladen-energie-totalen. Gebruik hiervoor de cumulatieve **geladen-energie (kWh)**-sensor — niet de per-100 km-efficiëntiesensoren (dat zijn gemiddelden, geen meters).

### Services

De integratie levert **20+ service calls** (`vag_connect.*`), waarvan vele merkspecifiek — *beschikbaarheid hangt af van merk & model*. Daaronder: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` en `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, en de `show_vag`-easter egg.

---

## ABRP (A Better Routeplanner) live telemetrie

Je kunt de live data van je auto naar **[A Better Routeplanner](https://abetterrouteplanner.com/)** pushen, zodat het bij het plannen rekening houdt met je werkelijke laadtoestand. Het is **opt-in en standaard uit** — er verlaat niets je netwerk totdat je het inschakelt en er daadwerkelijk een upload draait.

**1. Haal de twee credentials op.**

- **`token`** (per voertuig) — open de ABRP-app → **Settings → je auto → Live Data → "Generic" / andere auto** en kopieer de token die het toont.
- **`api_key`** (developer key) — dit is een partner-/developer-key uitgegeven door **iternio**, *niet* iets wat de app uitdeelt. Vraag er een aan bij iternio (hun developer-/API-key-aanvraagformulier). **We leveren bewust geen key mee** — er een hardcoden die we niet bezitten zou impersonatie zijn en zou een niet-eigen secret in een publieke repo bakken. Plak je eigen key.

**2. Schakel het in.** Integratie → **Configureren** → scroll naar de **ABRP**-sectie → vink *ABRP-telemetrie-push inschakelen* aan en plak beide waarden. Ze worden als paar gevalideerd (je krijgt een foutmelding als er maar één is ingesteld), gemaskeerd opgeslagen en **nooit naar het log geschreven**.

**3. Automatiseer de upload.** Importeer de meegeleverde blueprint **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), kies je voertuig en de bijbehorende **ABRP data changed**-sensor, en je bent klaar. De blueprint uploadt alleen wanneer er een echt nieuwe snapshot is (de binaire sensor *ABRP data changed* is de idempotente trigger — hij reset na elke geslaagde verzending, zodat dezelfde snapshot nooit twee keer wordt verstuurd).

Je kunt ook de **`vag_connect.abrp_send`**-service rechtstreeks aanroepen (richt op een apparaat of VIN; de api_key/token komen uit de opties, tenzij je ze inline meegeeft).

> 🔒 **Privacy:** de telemetrie bevat GPS. Het verlaat je netwerk alleen wanneer `abrp_send` draait (d.w.z. wanneer *jij* het triggert / de blueprint inschakelt). Wat we versturen: laadtoestand, laadstatus, GPS, koers, energie + capaciteit, geschatte actieradius, omgevings- + batterijtemperatuur, kilometerstand. Wat we bewust **niet** versturen: alles wat we niet betrouwbaar kunnen meten (snelheid, HV-pack-spanning/-stroom, state-of-health) — weggelaten in plaats van geraden.

---

## Opties (Configureren)

Via **Instellingen → Apparaten & services → VW Group Connect → Configureren** kun je aanpassen:
scaninterval, S-PIN, reverse-geocoding, **read-only-modus**, force PPE climate (Audi), push-schakelaars (MQTT/FCM/Audi-VW), **EU Data Act browser-fallback** (Playwright / ~100 MB Chromium, opt-in), **wake-before-poll** + wake-vertraging, client-id-override, **`eu_data_act_auto_kickoff`**, lege entiteiten verbergen (standaard aan), **ABRP** (inschakelen + api_key + user token, als paar gevalideerd), plus de aanvullende leeskanalen `volkswagen.de` en EU Data Act-portaal **toevoegen / verwijderen**.

---

## Steun dit project ❤️

Dit is een eenmansproject — en VW maakt het niet makkelijk: elke backend-wijziging betekent dagen reverse-engineering om weer een werkend pad te vinden. Die volharding is wat het in leven houdt waar gevestigde projecten het hebben opgegeven. Als het iets voor je waard is, kun je het voortgezette onderhoud steunen via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Dank je wel! 🙏

---

## Bijdragen

PR's welkom — zie [`CONTRIBUTING.md`](CONTRIBUTING.md). De **Vehicle Data Scout** zet onbekende API-velden om in een vooraf ingevuld bugrapport met één klik, zodat je de dekking kunt helpen verbeteren zonder code te lezen.

## Licentie

[GNU AGPL v3.0-or-later](LICENSE) voor de integratiecode. Verplichte attributie + naam-/handelsmerkvoorwaarden bij gebruik/fork: zie [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open-source-attributies in [`NOTICE.md`](NOTICE.md).
