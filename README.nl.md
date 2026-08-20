<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Eén Home Assistant-integratie voor auto's van de Volkswagen Group: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW en Audi VS/Canada</strong><br>
  <em>Accu, laden, actieradius, deuren, klimaat en GPS-locatie in Home Assistant. Directe API-toegang, meerdere leeskanalen met automatische terugval, geen middleware.</em>
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

**VW Group Connect is een [Home Assistant](https://www.home-assistant.io)-integratie die je auto van de Volkswagen Group in je smart home brengt: accu- en laadstatus, actieradius, kilometerstand, klimaat, deuren en ramen, GPS-locatie en meer, voor Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley en de Noord-Amerikaanse VW-/Audi-accounts, allemaal vanuit één configuratie-item.**

Waar de backend van het merk het nog toelaat, stuurt ze ook opdrachten op afstand zoals vergrendelen/ontgrendelen, klimaat- en laadbesturing. **Dat verschilt per merk, het is niet universeel:** Audi en Škoda zijn tweeweg, Volkswagen EU via het EU Data Act-portaal is alleen-lezen, en opdrachten voor SEAT/CUPRA worden door de fabrikant geblokkeerd. De tabel hieronder zegt precies wat waar geldt.

Om door de API-wijzigingen van Volkswagen in 2026 heen te blijven werken spreekt ze **meerdere leeskanalen en valt automatisch terug** wanneer er één geblokkeerd is: de merkeigen backends, het alleen-lezen **EU Data Act**-voertuigdataportaal, een optioneel `volkswagen.de`-webkanaal (bèta), een optionele **Tibber**-aanvulling, en een duurzame **wachtwoordloze** login voor oudere Car-Net-voertuigen. Ze draait prima **naast [evcc](https://evcc.io)** (zie [docs/EVCC.md](docs/EVCC.md)) en heeft **geen add-on, broker of middleware-container** nodig. Home Assistant installeert er automatisch twee kleine Python-pakketten voor; die worden alleen gebruikt door de optionele push-kanalen.

> 🎉 **Nu rechtstreeks beschikbaar in HACS** — geen custom repository nodig.

---

## Hoogtepunten

- **9 selecteerbare merken van de Volkswagen Group** in één integratie: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW VS/Canada, Audi VS/Canada, Porsche en Bentley.
- **Tweewegbesturing waar de backend van het merk het toelaat**: vergrendelen/ontgrendelen, klimaat, laden, doel-SoC. Dit is **per merk, niet universeel**. Kijk in de tabel hieronder voordat je op een opdracht rekent.
- **Škoda's in-car-assistent "Laura" in Home Assistant (nieuw in 3.0.0)**: vraag naar actieradius, laden en ritten als service, of geef hem door aan een willekeurige conversatie-agent (de ingebouwde Assist, OpenAI, Anthropic, Google, Ollama) als tool die hij kan aanroepen en aan elkaar kan koppelen. Alleen-lezen advies waar je automatiseringen op kunnen reageren.
- **Wachtwoordloze login-optie** (browser/device-code) voor Audi, Škoda, SEAT, CUPRA en Audi VS/CA. Er wordt geen wachtwoord in Home Assistant opgeslagen.
- **Multikanaal met automatische terugval**: merkeigen, EU Data Act-portaal, optioneel vw.de-web, optioneel Tibber, duurzaam Car-Net. Valt één kanaal weg, dan gaan je data niet op zwart.
- **Companion-kanaal (experimenteel, opt-in)**: als elke backend-route dicht zit, kan de integratie je auto uitlezen door via ADB de officiële app op een reservetelefoon met Android aan te sturen. Volkswagen is tegen een echt apparaat geverifieerd; de andere merken zijn alleen-lezen totdat een schermmapping bevestigd is. Moderne telefoons hebben de [ADB Bridge add-on](https://github.com/its-me-prash/vwgroup-app-adb-bridge) nodig; er wordt niets geroot en er worden geen app-tokens uitgelezen.
- **Veerkrachtig van opzet**: bewaart de laatst bekende waarden en de laatst bekende parkeerpositie tijdens portaalstoringen, filtert onzinnige "geen meting"-sentinels, laat de kilometerstand nooit terugspringen, en vertelt je wanneer een mislukte login een storing bij de fabrikant is en niet je wachtwoord.
- **Jij bepaalt het pollritme**: een **poll-interval-schuifregelaar** per account (een Number-entiteit, in minuten) die automatiseringen kunnen aansturen, aangemaakt bij elke installatie, ook bij alleen-lezen portaalinstallaties.
- **GPS device tracker**, 100+ entiteiten over meerdere platformen, 30+ serviceaanroepen, meerdere voertuigen per account, entiteitsnamen in **12 talen**.
- **Porsche draait op zijn eigen backend**, niet op het EU Data Act-portaal. De portaalroute *sluit* Porsche structureel *uit*, dus tools die alleen het portaal gebruiken kunnen het nooit dekken. De opdrachtcode staat hier, maar de Porsche-login zelf is momenteel experimenteel (zie de tabel).
- **Vehicle Data Scout** detecteert API-drift automatisch en biedt een bugrapport met één klik — en vanaf 3.0.0 bevat de geanonimiseerde diagnostische download ook de ruwe API-responses, zodat één bijlage alles bevat wat nodig is om ondersteuning voor een nieuw veld toe te voegen. **Quality Scale: Platinum.**

---

## Merkstatus

| Merk | Bediening | Data | Opmerkingen |
|---|---|---|---|
| **Audi** (EU) | ✅ Tweeweg | ✅ Volledig | myAudi-backend (incl. start/stop verbrandingsmotor) |
| **Škoda** | ✅ Tweeweg | ✅ Volledig | native Škoda-backend |
| **VW VS/CA** | ✅ Tweeweg | ✅ Volledig | VW NA-cloud (vereist de VS/CA-landkeuze + S-PIN). Canada logt nu in op zijn eigen server met zijn eigen app-client en toont volledige data, bevestigd op een echte Canadese ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Standaard alleen-lezen · ⚠️ opdrachten = MBB **alpha** | ✅ Volledige telemetrie via het EU Data Act-portaal | Zie de eerlijke opmerking hieronder ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Opdrachten door VW geblokkeerd | ✅ EU Data Act-portaal | OLA-toegang in 2026 serverzijdig ingetrokken ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Tweeweg onder voorbehoud van livetest | ✅ Login + lezen | My Bentley, draait op de Audi/IDK-tenant |
| **Porsche** | ⚠️ Experimenteel | ⚠️ Experimenteel | Porsche Connect, eigen backend. Porsche is overgestapt op de *Porsche One*-app, dus **de login zal op huidige accounts naar verwachting mislukken**. De opdrachtcode is er, maar onbereikbaar tot de login opnieuw is gebouwd ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi VS/CA** | ⏳ Tweeweg onder voorbehoud van livetest | ✅ Volledig | myAudi NA-backend. De VS leest nu uit de regionale `na`-voertuigservice en is **bevestigd werkend op een echte VS Audi Q5** (58 entiteiten) — met dank aan @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada gebruikt de EMEA-service. Commando's erven de tweeweg-paden van Audi maar zijn nog niet apart live bevestigd op NA ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Eerlijke opmerking over VW EU-bediening.** Volkswagen EU-voertuigen zijn **standaard read-only**: je krijgt volledige telemetrie via het EU Data Act-portaal, maar geen commando's op afstand. Commando's op afstand voor VW EU bestaan **alleen als een experimentele duurzame-MBB-tweeweg-ALPHA**, en alleen voor **legacy MQB / Car-Net**-auto's — het is een opt-in-schakelaar, **geen** standaardfunctie. **MEB / ID-familie-auto's (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) hebben helemaal geen commandopad** en worden read-only aangemaakt. De MBB-alpha wordt gevolgd in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testers welkom.

> In 2026 plaatste Volkswagen delen van zijn API achter device attestation. Deze integratie omzeilt dat waar mogelijk (duurzame Car-Net-login, EU Data Act-portaal, vw.de-web) en is transparant over wat elk kanaal wel en niet kan.

---

## Bekende beperkingen

Een paar dingen zijn **structureel** — ze komen voort uit hoe Volkswagens backends in 2026 werken, niet uit de integratie, en geen enkele instelling lost ze op:

- **VW EU is standaard read-only; commando's zijn een MBB-alpha en alleen voor legacy-auto's.** Zie de merkopmerking hierboven. **MEB / ID-familie-auto's zijn read-only** — het duurzame Car-Net-commandopad herkent ze niet (het antwoordt "Unknown user"), en VW's MEB-backend biedt geen equivalent. De setup detecteert dit en maakt een **read-only entry** aan (met een reparatiemelding) in plaats van te falen, dus het is een bekende beperking, geen stille. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-commando's op afstand worden door VW geblokkeerd.** De online-services-toegang (OLA) voor deze merken is in 2026 server-side ingetrokken (HTTP 403); opnieuw inloggen of een app-versie-bump herstelt dit niet. Data blijft stromen via het EU Data Act-portaal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **De data van het EU Data Act-portaal is mager en verschilt per auto.** VW publiceert vandaag slechts een deel van de velden (vaak kilometerstand + vergrendeling + laden, soms veel meer). Het wordt na verloop van tijd ruimer naarmate VW het portaal uitbreidt richting de deadline van september 2026 — velden die vandaag `unknown` tonen, kunnen vanzelf invullen, zonder dat er iets hoeft te veranderen. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Noord-Amerika: VW én Audi lezen nu allebei — Audi-commando's zijn het laatste onbevestigde stuk.** **VW VS/CA werkt, inclusief Canada**, bevestigd tegen een echte Canadese ID.4: Canada logt in op zijn eigen server, en sinds de data-envelop-fix toont het volledige telemetrie ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi VS/CA leest nu ook**: de VS haalt data op van de regionale `na`-voertuigservice, bevestigd op een echte Amerikaanse Audi Q5 (met dank aan @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada gebruikt de EMEA-service. Commando's erven de Audi-tweeweg-paden, maar zijn nog niet apart live bevestigd op Noord-Amerikaanse accounts ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **De Porsche-login zal nu naar verwachting mislukken.** Porsche heeft de *My Porsche*-app, waartegen deze integratie zich authenticeert, uitgefaseerd ten gunste van *Porsche One*. Lezen en opdrachten zijn geïmplementeerd, maar je komt waarschijnlijk niet langs de login tot dat opnieuw is gebouwd. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-updates (vrijwel realtime) zijn een opt-in BÈTA en staan standaard uit.** De MQTT- (Škoda) en Firebase-kanalen (Audi/VW, CUPRA/SEAT) zijn bedraad maar niet live gevalideerd, en de merken schermen ze steeds vaker af met app-attestatie, waaraan buiten het apparaat niet te voldoen is. Laat ze uit tenzij je wilt helpen testen. Gewoon pollen is de ondersteunde weg.

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

- **Browser / device-code (wachtwoordloos)** voor *Audi, Škoda, SEAT, CUPRA en Audi VS/CA*. Log in op je telefoon of laptop en keur het apparaat goed; er wordt geen wachtwoord in Home Assistant opgeslagen (het bewaart een echte refresh token). Deze stap biedt ook de optionele **S-PIN** en het scaninterval.
- **Portaal, e-mail + wachtwoord** voor *Volkswagen EU, Volkswagen VS/CA, Bentley en Porsche (experimenteel)*. Vul je merklogin in. Deze stap toont een merkkiezer, e-mail, wachtwoord, optionele **S-PIN**, scaninterval en een schakelaar **"MBB-opdrachten inschakelen"** (die alleen effect heeft op Volkswagen EU, zie [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Voor **Volkswagen VS/Canada** verschijnt hier een **landkeuze (VS of CA)**; die wordt **alleen** voor dat merk getoond en door geen enkel ander gebruikt.

> Het **EU Data Act-portaal is geen derde loginknop.** Het is de alleen-lezen strategie waarop de coördinator automatisch terugvalt, en het kan daarnaast als aanvullend leeskanaal worden *toegevoegd* via **Configureren → Opties**. Hetzelfde geldt voor het `volkswagen.de`-webkanaal (opt-in bèta, alleen via de Opties, alleen-lezen) en het optionele **Tibber**-kanaal, dat gaten vult die de eerstelijnskanalen leeg lieten en nooit verse data overschrijft.

### Het S-PIN-veld — wanneer je het nodig hebt

De **S-PIN** is de beveiligings-PIN van de app van je merk. Hij is optioneel in het formulier en alleen vereist voor bepaalde acties: hij is nodig voor **VW VS/Canada-datalezingen en -commando's**, en voor beveiligingsgevoelige commando's op afstand bij merken die ze achter de S-PIN afschermen. Laat het leeg als je auto er niet om vraagt.

---

### Volkswagen EU — je data laten stromen (belangrijk)

Voor Volkswagen EU is **inloggen niet genoeg** — VW streamt voertuigdata pas zodra *jij* het delen van data aan VW's kant hebt ingeschakeld. Als je auto zonder data verschijnt (of helemaal niet verschijnt), is dit vrijwel altijd de reden, **niet** een verkeerd wachtwoord. Doe dit één keer:

1. **Voeg de integratie toe:** kies **Portaal (e-mail + wachtwoord)** en selecteer **Volkswagen EU**, en log dan in.
2. **Voltooi elke eenmalige prompt op VW's portaal.** Open het VW-dataportaal één keer in een browser of de merk-app en doorloop wat het vraagt: **accepteer voorwaarden, bevestig toestemming, voltooi onboarding / regiokeuze.** Headless-toegang komt hier niet voorbij — dit is het `portal_interaction_required`-geval ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Geef toestemming voor het delen van data.** Zet op het portaal **"Gebruik van niet-persoonsgebonden data" = Granted** (de toestemming voor het delen van data onder de EU Data Act).
4. **Ga niet op zoek naar een schakelaar voor een "continu dataverzoek" — die bestaat niet.** De integratie maakt dat verzoek voor elke auto zelf aan, en dat is **gratis**. Sinds v2.29.0 wordt het verzoek **zonder vervaldatum** aangemaakt; eerdere versies vroegen om één maand, en daardoor vielen sommige installaties na ongeveer vier weken stilletjes stil. Is je data gestopt en heb je het account vóór v2.29.0 ingesteld, verwijder het account dan uit de integratie en voeg het één keer opnieuw toe, zodat er een vers verzoek wordt aangemaakt. Zonder verzoek retourneert het portaal niets voor die VIN en verschijnt het voertuig zonder metingen.
5. **Wacht tot de auto een snapshot pusht.** Zelfs na al het bovenstaande kost propagatie tijd. De auto kan **een tijdje `offline` / `unknown` tonen — vaak tot zijn volgende rit of wake, tot ~24 u** — voordat de sensoren zich vullen. Dit is normaal.

Het portaal levert aanvankelijk slechts een **deel van de velden**, en dat deel **wordt na verloop van tijd ruimer** naarmate VW de portaaldekking uitbreidt richting de deadline van september 2026 — velden die vandaag `unknown` tonen, kunnen vanzelf invullen. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Volledige veldenlijst.** Het volledige officiële VW-Group data-dictionary (elke EU Data Act-sleutel -> veld, beschrijving en eenheid) staat in [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Een wekelijkse workflow houdt de dictionary-pagina van het portaal in de gaten en opent een pull request zodra VW een nieuwere versie publiceert, zodat de tabel niet stilletjes veroudert.

> De Opties-schakelaar **`eu_data_act_auto_kickoff`** is degene die dat Custom Data Request van 15 minuten aanmaakt, en hij staat **standaard aan** — in portaalmodus is er zonder zo'n verzoek geen data. Zet hem alleen uit als je het verzoek liever zelf beheert.

---

## Wat je krijgt

- **Sensoren:** batterij-SoC, actieradius (elektrisch / verbranding / totaal), brandstofniveau, kilometerstand, temperaturen, laadvermogen, laadsnelheid (altijd in km/u, omgerekend als je auto in mph rapporteert) en laadtype, laaddoel, geschiedenis per laadsessie (energie, duur, start, AC/DC) op Škoda en SEAT/CUPRA, ritstatistieken & levenslange totalen, service- & olieservice-intervallen, softwareversie, verbindingsstatus, laatst gezien, en — op Škoda — laatste tankbeurt, huidige betaald-parkeren-sessie, serviceherinneringen, vertrektimers en voorkeurslaadmodus, en meer.
- **Binaire sensoren:** deuren vergrendeld, deuren/ramen/kofferbak/motorkap/schuifdak open, stekker aangesloten, ladend, OTA-update beschikbaar, lichten, voertuig online, vertrektimers, alarm.
- **Bediening:** vergrendelen/ontgrendelen, klimaat starten/stoppen, laden starten/stoppen, ruitverwarming, vertrektimers, doel-SoC / temperatuur / max. laadstroom instellen, claxon-en-knipper (met keuze van de duur, en alleen lichten of ook de claxon), wake, refresh, laadstations zoeken, kampeermodus en actieve ventilatie (Škoda-interieurventilatie zonder verwarming) *(beschikbaarheid hangt af van merk & model)*.
- **Device tracker:** GPS-positie voor de Home Assistant-kaart. Een poll die zonder coördinaten terugkomt behoudt de laatst bekende parkeerpositie in plaats van die kwijt te raken.
- **Afbeeldingen:** voertuig-renders waar het merk ze levert.
- **Instellingen:** een **poll-interval**-schuifregelaar per account, in minuten, zodat een automatisering vaker kan pollen terwijl je rijdt en 's nachts gas terugneemt. Hij bestaat bij elke installatie, ook bij alleen-lezen portaalitems.
- **12 talen:** entiteitsnamen zijn volledig vertaald naar Engels, Duits, Frans, Spaans, Italiaans, Nederlands, Pools, Tsjechisch, Zweeds, Deens, Noors en Fins.

> 💡 **Energiedashboard:** de geladen-energie-sensor is `total_increasing`, dus voeg hem rechtstreeks toe aan het Home Assistant-**Energiedashboard**, of verpak hem in een `utility_meter`-helper voor dagelijkse/maandelijkse geladen-energie-totalen. Gebruik hiervoor de cumulatieve **geladen-energie (kWh)**-sensor — niet de per-100 km-efficiëntiesensoren (dat zijn gemiddelden, geen meters).

### Services

De integratie levert **30+ service calls** (`vag_connect.*`), waarvan vele merkspecifiek — *beschikbaarheid hangt af van merk & model*. Daaronder: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (hulp- / standverwarming — SEAT/CUPRA, Škoda en VW/Audi via een tweeweg-opdrachtkanaal, waar de auto ermee is uitgerust), `send_destination` (SEAT/CUPRA/Škoda) en `update_charging_settings` (SEAT/CUPRA), de Škoda `ask_assistant` (zie hieronder), `set_location_target_soc` en `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send`, en de `show_vag`-easter egg.

---

## evcc

[evcc](https://evcc.io) kan de laadtoestand, actieradius en laadstatus van je auto rechtstreeks uit Home Assistant halen, zodat laden op zonne-overschot rekent met de echte accu in plaats van met een schatting. In de integratie draait daarvoor niets extra's: evcc leest de eigen REST-API van Home Assistant. Het **lees**pad werkt bij **alle merken**, ook bij alleen-lezen VW EU-/portaalauto's. Het **schrijf**pad (`chargeEnable`) werkt alleen bij een tweeweg-auto (Audi of Škoda met een levend opdrachtkanaal) en alleen wanneer evcc de auto zelf als laadpunt behandelt. Met een echte slimme laadpaal heeft evcc genoeg aan het leespad.

Kant-en-klare `evcc.yaml`-recepten en de eenmalige inrichting staan in [docs/EVCC.md](docs/EVCC.md). Deze connector is **bèta**.

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

## Škoda AI-assistent ("Laura") — nieuw in 3.0.0

MyŠkoda's eigen in-car-assistent, **Laura**, is beschikbaar binnen Home Assistant.
Vraag haar naar actieradius, laden en ritten met de `vag_connect.ask_assistant`-service
(ze geeft een tekstantwoord terug dat je in een melding kunt tonen, kunt laten uitspreken
of waarop je kunt vertakken), of geef haar door aan een **conversatie-agent** — de
ingebouwde Assist in LLM-modus, of OpenAI / Anthropic / Google / Ollama — als tool die
hij kan aanroepen en aan elkaar kan koppelen (vraag Laura → dan `send_destination` naar
de auto). Ze is **alleen-lezen, adviserend en uitsluitend Škoda**; het is een **bèta**,
dus feedback op de antwoordkwaliteit is welkom.

De setup, de spraaktrigger ("vraag Laura …") en kant-en-klare voorbeeldautomatiseringen —
waaronder *auto komt thuis → bijladen + voorverwarmen + de actieradius uitspreken* — staan
in **[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Opties (Configureren)

Via **Instellingen → Apparaten & services → VW Group Connect → Configureren** kun je aanpassen:
scaninterval (ook live beschikbaar als poll-interval-schuifregelaar), S-PIN (plus een S-PIN per voertuig wanneer het account meer dan één auto heeft), reverse-geocoding, **read-only-modus**, force PPE climate (Audi), push-schakelaars (MQTT/FCM/Audi-VW, allemaal opt-in bèta en standaard uit), client-id-override, **`eu_data_act_auto_kickoff`** (standaard aan), lege entiteiten verbergen (standaard aan), **ABRP** (inschakelen + api_key + user token, als paar gevalideerd), plus de aanvullende leeskanalen **toevoegen / verwijderen**: `volkswagen.de` (bèta), EU Data Act-portaal, **Tibber** en het experimentele kanaal via een **companion-telefoon**.

---

## Steun dit project ❤️

Dit is een eenmansproject — en VW maakt het niet makkelijk: elke backend-wijziging betekent dagen reverse-engineering om weer een werkend pad te vinden. Die volharding is wat het in leven houdt waar gevestigde projecten het hebben opgegeven. Als het iets voor je waard is, kun je het voortgezette onderhoud steunen via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Dank je wel! 🙏

---

## Bijdragen

PR's welkom, zie [`CONTRIBUTING.md`](CONTRIBUTING.md). Veelgestelde vragen worden beantwoord in [docs/FAQ.md](docs/FAQ.md). De **Vehicle Data Scout** zet onbekende API-velden om in een vooraf ingevuld bugrapport met één klik, zodat je de dekking kunt helpen verbeteren zonder code te lezen.

## Licentie

[GNU AGPL v3.0-or-later](LICENSE) voor de integratiecode. Verplichte attributie + naam-/handelsmerkvoorwaarden bij gebruik/fork: zie [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open-source-attributies in [`NOTICE.md`](NOTICE.md).
