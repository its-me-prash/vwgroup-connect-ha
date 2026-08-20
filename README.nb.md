<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Én Home Assistant-integrasjon for biler fra Volkswagen-konsernet: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW og Audi USA/Canada</strong><br>
  <em>Batteri, lading, rekkevidde, dører, klima og GPS-posisjon i Home Assistant. Direkte API-tilgang, flere lesekanaler med automatisk omkobling, ingen mellomvare.</em>
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

> ### 📛 Merknad om navnebyttet
> Tidligere publisert som **`vag-connect-ha`** (VAG = Volkswagen AG, vanlig DACH-forkortelse).
> Det viser seg at den forkortelsen leses *ganske* annerledes for engelsktalende 😅
>
> **Det som fortsetter å fungere som før**: alle entiteter (f.eks. `sensor.audi_q4_battery_soc`),
> alle service-kall (`vag_connect.lock`, `vag_connect.show_vag` osv.), alle automatiseringer,
> HACS-installasjonen — **ingenting går i stykker**. Markedsførings-/visningsnavnet endres,
> kodens indre struktur forblir uendret. Se [`MIGRATION.md`](MIGRATION.md).
>
> Stor takk til fellesskapene **Home Assistant UK** og **HA Ideas, Projects and Solutions**
> for tipset — spesielt **Si Gregory**, **Ben Johnson** og **Evets David**.
>
> Og et spesielt shoutout til **Jordan Waeles**, hvis `show_vag()`-kommentar nå er et offisielt
> støttet påskeegg i denne integrasjonen (`vag_connect.show_vag`-tjenesten, se CHANGELOG v2.2.3).

---

## Hva er dette?

**VW Group Connect er en [Home Assistant](https://www.home-assistant.io)-integrasjon som henter bilen din fra Volkswagen-konsernet inn i smarthjemmet: batteri- og ladestatus, rekkevidde, kilometerstand, klima, dører og vinduer, GPS-posisjon og mer, for Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley og de nordamerikanske VW-/Audi-kontoene, alt fra én konfigurasjonsoppføring.**

Der merkets baksystem fortsatt tillater det, sender den også fjernkommandoer som lås/lås opp, klima- og ladestyring. **Dette avhenger av merket, det er ikke universelt:** Audi og Škoda er toveis, Volkswagen EU via EU Data Act-portalen er skrivebeskyttet, og kommandoer for SEAT/CUPRA er blokkert av produsenten. Tabellen under sier nøyaktig hva som gjelder hvor.

For å fortsette å virke gjennom Volkswagens API-endringer i 2026 snakker den **flere lesekanaler og kobler automatisk om** når én er blokkert: merkenes egne baksystemer, den skrivebeskyttede kjøretøydataportalen **EU Data Act**, en valgfri `volkswagen.de`-webkanal (beta), en valgfri **Tibber**-utfylling og en varig **passordløs** innlogging for eldre Car-Net-biler. Den går fint **side om side med [evcc](https://evcc.io)** (se [docs/EVCC.md](docs/EVCC.md)) og trenger **verken tillegg, megler eller mellomliggende container**. Home Assistant installerer automatisk to små Python-pakker til den; de brukes bare av de valgfrie push-kanalene.

> 🎉 **Nå tilgjengelig direkte i HACS** — ingen custom-repository nødvendig.

---

## Høydepunkter

- **9 valgbare Volkswagen-konsernmerker** i én integrasjon: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Canada, Audi USA/Canada, Porsche og Bentley.
- **Toveisstyring der merkets baksystem tillater det**: lås/lås opp, klima, lading, mål-SoC. Dette er **per merke, ikke universelt**. Sjekk tabellen under før du regner med en kommando.
- **Škodas innebygde bilassistent «Laura» i Home Assistant (nytt i 3.0.0)**: spør om rekkevidde, lading og turer som en tjeneste, eller overlat den til en hvilken som helst samtaleagent (den innebygde Assist, OpenAI, Anthropic, Google, Ollama) som et verktøy den kan kalle og kjede sammen. Skrivebeskyttede råd automasjonene dine kan handle ut fra.
- **Passordløs innlogging** (nettleser/enhetskode) for Audi, Škoda, SEAT, CUPRA og Audi USA/CA. Ingen passord lagres i Home Assistant.
- **Flerkanals med automatisk omkobling**: merkets eget baksystem, EU Data Act-portalen, valgfri vw.de-web, valgfri Tibber, varig Car-Net. Faller én kanal ut, går ikke dataene dine i svart.
- **Companion-kanal (eksperimentell, frivillig)**: når alle baksystembaner er stengt, kan integrasjonen lese bilen din ved å fjernstyre den offisielle appen på en ledig Android-telefon via ADB. Volkswagen er verifisert mot en ekte enhet; de andre merkene er skrivebeskyttet til et skjermkart er bekreftet. Moderne telefoner trenger [ADB Bridge-tillegget](https://github.com/its-me-prash/vwgroup-app-adb-bridge); ingenting rootes, og ingen app-tokener leses.
- **Robust av design**: beholder de sist kjente verdiene og den sist kjente parkeringsposisjonen gjennom portalutfall, filtrerer bort falske «ingen avlesning»-vakter, lar aldri kilometerstanden hoppe bakover, og sier fra når en mislykket innlogging er et utfall hos produsenten og ikke passordet ditt.
- **Du bestemmer spørretakten**: en **spørreintervall-glidebryter** per konto (en Number-entitet, i minutter) som automasjoner kan styre, opprettet i hvert oppsett, også skrivebeskyttede portaloppsett.
- **GPS-enhetssporer**, 100+ entiteter på tvers av flere plattformer, 30+ tjenestekall, flere kjøretøy per konto, entitetsnavn på **12 språk**.
- **Porsche går på sitt eget baksystem**, ikke på EU Data Act-portalen. Portalveien *utelukker* Porsche strukturelt, så verktøy som bare bygger på portalen kan aldri dekke det. Kommandokoden ligger her, men selve Porsche-innloggingen er eksperimentell akkurat nå (se tabellen).
- **Vehicle Data Scout** oppdager API-drift automatisk og tilbyr en feilrapport med ett klikk — og fra 3.0.0 inneholder den sladdede diagnostikknedlastingen også de rå API-svarene, slik at ett enkelt vedlegg er alt som trengs for å legge til støtte for et nytt felt. **Quality Scale: Platinum.**

---

## Merkestatus

| Merke | Styring | Data | Merknader |
|---|---|---|---|
| **Audi** (EU) | ✅ Toveis | ✅ Full | myAudi-baksystem (inkl. start/stopp av forbrenningsmotor) |
| **Škoda** | ✅ Toveis | ✅ Full | Škodas eget baksystem |
| **VW USA/CA** | ✅ Toveis | ✅ Full | VW NA-skyen (krever landvelgeren USA/CA + S-PIN). Canada logger nå inn på sin egen tjener med sin egen app-klient og viser alle data, bekreftet på en ekte kanadisk ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Skrivebeskyttet som standard · ⚠️ kommandoer = MBB **alpha** | ✅ Full telemetri via EU Data Act-portalen | Se den ærlige merknaden under ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Kommandoer blokkert av VW | ✅ EU Data Act-portalen | OLA-tilgangen ble trukket tilbake på tjenersiden i 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Toveis avventer livetest | ✅ Innlogging + lesing | My Bentley, kjører på Audi/IDK-tenanten |
| **Porsche** | ⚠️ Eksperimentell | ⚠️ Eksperimentell | Porsche Connect, eget baksystem. Porsche har gått over til *Porsche One*-appen, så **innloggingen forventes å feile på dagens kontoer**. Kommandokoden finnes, men er utilgjengelig til innloggingen er bygget om ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⏳ Toveis avventer livetest | ✅ Full | myAudi NA-baksystem. USA leser nå fra den regionale `na`-kjøretøytjenesten og er **bekreftet fungerende på en ekte USA Audi Q5** (58 entiteter) — takk @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada bruker EMEA-tjenesten. Kommandoer arver Audis toveisbaner, men er ennå ikke separat live-bekreftet på NA ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Ærlig merknad om VW EU-styring.** Volkswagen EU-kjøretøy er **skrivebeskyttet som standard**: du får full telemetri gjennom EU Data Act-portalen, men ingen fjernkommandoer. Fjernkommandoer for VW EU finnes **kun som en eksperimentell varig-MBB toveis-ALFA**, og bare for **eldre MQB- / Car-Net**-biler — det er en valgfri bryter, **ikke** en standardfunksjon. **MEB- / ID-familiebiler (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har ingen kommandobane i det hele tatt** og opprettes skrivebeskyttet. MBB-alfaen spores i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testere er velkomne.

> I 2026 la Volkswagen deler av API-et sitt bak enhetsattestasjon. Denne integrasjonen ruter rundt det der det er mulig (varig Car-Net-pålogging, EU Data Act-portal, vw.de-web) og er åpen om hva hver kanal kan og ikke kan.

---

## Kjente begrensninger

Noen få ting er **strukturelle** — de kommer av hvordan Volkswagens baksystemer fungerer i 2026, ikke av integrasjonen, og ingen innstilling fikser dem:

- **VW EU er skrivebeskyttet som standard; kommandoer er en MBB-alfa kun for eldre biler.** Se merkemerknaden ovenfor. **MEB- / ID-familiebiler er skrivebeskyttet** — den varige Car-Net-kommandobanen gjenkjenner dem ikke (den svarer «Unknown user»), og VWs MEB-baksystem har ingen tilsvarende. Oppsettet oppdager dette og oppretter en **skrivebeskyttet oppføring** (med en reparasjonsmelding) i stedet for å feile, så det er en kjent grense, ikke en stille en. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA- / SEAT-fjernkommandoer er blokkert av VW.** Tilgang til nettjenester (OLA) for disse merkene ble trukket tilbake på serversiden i 2026 (HTTP 403); en ny innlogging eller en oppdatert app-versjon gjenoppretter det ikke. Data flyter fortsatt via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portaldata er tynne og varierer fra bil til bil.** VW publiserer bare et utsnitt av felter i dag (ofte kilometerstand + låsing + lading, noen ganger mye mer). Det utvides over tid etter hvert som VW bygger ut portalen frem mot fristen i september 2026 — felter som i dag viser `unknown`, kan fylle seg av seg selv, uten endring. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Nord-Amerika: både VW og Audi leser nå — Audi-kommandoer er den siste ubekreftede biten.** **VW USA/CA virker, inkludert Canada**, bekreftet mot en ekte kanadisk ID.4: Canada logger inn på sin egen tjener, og etter datakonvolutt-rettelsen viser den full telemetri ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi USA/CA leser nå også**: USA henter fra den regionale `na`-kjøretøytjenesten, bekreftet på en ekte USA Audi Q5 (takk @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Canada bruker EMEA-tjenesten. Kommandoer arver Audis toveisbaner, men er ennå ikke separat live-bekreftet på nordamerikanske kontoer ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Porsche-innloggingen forventes å feile akkurat nå.** Porsche har lagt ned *My Porsche*-appen, som denne integrasjonen autentiserer seg mot, til fordel for *Porsche One*. Lesing og kommandoer er implementert, men du kommer trolig ikke forbi innloggingen før den er bygget om. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-oppdateringer (tilnærmet sanntid) er en frivillig BETA som er av som standard.** MQTT- (Škoda) og Firebase-kanalene (Audi/VW, CUPRA/SEAT) er koblet opp, men ikke validert live, og merkene skjermer dem i økende grad med app-attestering som ikke lar seg oppfylle utenfor enheten. La dem være av med mindre du vil hjelpe til med testingen. Vanlig spørring er den støttede veien.

> **Hvor vi står.** Under EU Data Act (Forordning (EU) 2023/2854) er bilens data *dine*. Å kjøre denne integrasjonen på din egen maskinvare er *deg* som får tilgang til *dine egne* data (Artikkel 4) — som du har krav på i samme kvalitet som produsenten leverer til seg selv, i sanntid der det er teknisk mulig. VWs skrivebeskyttede, timevis utdaterte portal lever ikke opp til dette i dag. Denne integrasjonen er bevisst **kanaluavhengig**: i det øyeblikket VW gir eiere et sanntids, styringsdyktig grensesnitt — slik Data Act krever, og slik noen produsenter allerede tilbyr eierne sine — vil vi støtte det her, gratis, for alle. Vi står bak din rett til sanntidstilgang til din egen bil.

---

## Installasjon

**Via HACS (anbefalt):**

1. Åpne **HACS** i Home Assistant.
2. Søk etter **«VW Group Connect»** og installer den.
3. Start Home Assistant på nytt.
4. Gå til **Innstillinger → Enheter og tjenester → Legg til integrasjon → VW Group Connect** og følg påloggingsflyten.

<sup>Nettopp slått sammen i HACS-standarden — hvis den ikke er søkbar ennå, gi HACS-indeksen litt tid til å oppdatere seg, eller legg til `its-me-prash/vwgroup-connect-ha` som et custom-repository i mellomtiden.</sup>

**Minimum Home Assistant: `2024.4.0`.**

### Påloggingsalternativer (oppsettsveiviseren har to baner)

Integrasjonens første skjermbilde tilbyr **to** påloggingsmetoder. Velg den merket ditt støtter:

- **Nettleser / enhetskode (passordløs)** for *Audi, Škoda, SEAT, CUPRA og Audi USA/CA*. Logg inn på telefonen eller den bærbare og godkjenn enheten; ingen passord lagres i Home Assistant (den beholder en ekte refresh-token). Dette trinnet tilbyr også valgfri **S-PIN** og skanneintervall.
- **Portal, e-post + passord** for *Volkswagen EU, Volkswagen USA/CA, Bentley og Porsche (eksperimentelt)*. Skriv inn merkeinnloggingen din. Dette trinnet viser en merkevelger, e-post, passord, valgfri **S-PIN**, skanneintervall og en bryter for **«aktiver MBB-kommandoer»** (som bare har effekt på Volkswagen EU, se [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen USA/Canada** dukker det opp en **landvelger (USA eller CA)** her; den vises **bare** for det merket og brukes ikke av noe annet.

> **EU Data Act-portalen er ikke en tredje innloggingsknapp.** Det er den skrivebeskyttede strategien koordinatoren automatisk faller tilbake på, og den kan i tillegg *legges til* som en supplerende lesekanal via **Konfigurer → Alternativer**. Det samme gjelder webkanalen `volkswagen.de` (frivillig beta, bare via Alternativer, skrivebeskyttet) og den valgfrie **Tibber**-kanalen, som fyller ut felter førstepartskanalene lot stå tomme og aldri overskriver ferskere data.

### S-PIN-feltet — når du trenger det

**S-PIN** er sikkerhets-PIN-en til merkeappen din. Den er valgfri i skjemaet og bare påkrevd for enkelte handlinger: den trengs for **datalesing og kommandoer på VW US/Canada**, og for sikkerhetssensitive fjernkommandoer på merker som sperrer dem bak S-PIN-en. La den stå tom hvis bilen din ikke ber om en.

---

### Volkswagen EU — å få dataene dine til å flyte (viktig)

For Volkswagen EU er **det ikke nok å logge inn** — VW streamer kjøretøydata først når *du* har slått på datadeling på VWs side. Hvis bilen din dukker opp uten data (eller ikke dukker opp i det hele tatt), er det nesten alltid grunnen, **ikke** et feil passord. Gjør dette én gang:

1. **Legg til integrasjonen:** velg **Portal (e-post + passord)** og velg **Volkswagen EU**, og logg deretter inn.
2. **Fullfør enhver engangsoppgave på VWs portal.** Åpne VWs dataportal én gang i en nettleser eller merkeappen og fullfør det den ber om: **godta vilkår, bekreft samtykke, fullfør onboarding / regionvalg.** Tilgang uten nettleser kommer ikke forbi disse — dette er tilfellet `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Gi samtykke til datadeling.** I portalen setter du **«Bruk av ikke-personlige data» = Innvilget** (EU Data Act-samtykket til datadeling).
4. **Ikke let etter en bryter for «kontinuerlig dataforespørsel» — den finnes ikke.** Integrasjonen oppretter den forespørselen for hver bil selv, og den er **gratis**. Fra og med v2.29.0 opprettes forespørselen **uten utløpsdato**; tidligere versjoner ba om én måned, og det er grunnen til at enkelte oppsett stille sluttet å levere data etter rundt fire uker. Hvis dataene dine har stoppet og du satte opp kontoen før v2.29.0, fjerner du kontoen fra integrasjonen og legger den til igjen én gang, slik at det opprettes en fersk forespørsel. Uten en forespørsel returnerer portalen ingenting for den VIN-en, og bilen dukker opp uten avlesninger.
5. **Vent på at bilen pusher et øyeblikksbilde.** Selv etter alt det ovenfor tar propageringen tid. Bilen kan vise **`offline` / `unknown` en stund — ofte til neste kjøretur eller vekking, opptil ~24 t** — før sensorene fylles. Dette er normalt.

Portalen leverer i utgangspunktet bare et **utsnitt av felter**, og det utsnittet **utvides over tid** etter hvert som VW bygger ut portaldekningen frem mot fristen i september 2026 — felter som i dag viser `unknown`, kan fylle seg av seg selv. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Fullstendig feltliste.** VW-konsernets komplette offisielle dataordbok (hver EU Data Act-nøkkel -> felt, beskrivelse og enhet) finnes i [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). En ukentlig arbeidsflyt følger med på ordlistesiden til portalen og åpner en pull request når VW publiserer en nyere versjon, slik at tabellen ikke stille blir utdatert.

> Alternativer-bryteren **`eu_data_act_auto_kickoff`** er den som oppretter denne 15-minutters Custom Data Request, og den er **på som standard** — i portalmodus finnes det ingen data uten en. Slå den av bare hvis du heller vil håndtere forespørselen selv.

---

## Hva du får

- **Sensorer:** batteri-SoC, rekkevidde (elektrisk / forbrenning / total), drivstoffnivå, kilometerstand, temperaturer, ladeeffekt, ladehastighet (alltid i km/t, konvertert hvis bilen rapporterer i mph) og ladetype, lademål, historikk per ladeøkt (energi, varighet, start, AC/DC) på Škoda og SEAT/CUPRA, turstatistikk og totalaggregater, service- og oljeserviceintervaller, programvareversjon, tilkoblingstilstand, sist sett, og — på Škoda — siste tanking, gjeldende betal-for-parkering-økt, servicepåminnelser, avreisetimere og foretrukket lademodus, og mer.
- **Binærsensorer:** dører låst, dører/vinduer/bagasjerom/panser/soltak åpne, plugg tilkoblet, lading, OTA-oppdatering tilgjengelig, lys, kjøretøy online, avreisetimere, alarm.
- **Styring:** låsing/opplåsing, klima start/stopp, lading start/stopp, rutevarme, avreisetimere, sette mål-SoC / temperatur / maks. ladestrøm, tut-og-blink (med valgbar varighet, og enten bare lys eller horn i tillegg), vekking, oppdatering, finn ladestasjoner, campingmodus og aktiv ventilasjon (Škoda-kupéventilasjon uten oppvarming) *(tilgjengelighet avhenger av merke og modell)*.
- **Enhetssporer:** GPS-posisjon for Home Assistant-kartet. En spørring som kommer tilbake uten koordinater beholder den sist kjente parkeringsposisjonen i stedet for å miste den.
- **Bilder:** kjøretøyrenderinger der merket leverer dem.
- **Innstillinger:** en **spørreintervall**-glidebryter per konto, i minutter, slik at en automasjon kan spørre oftere mens du kjører og roe ned om natten. Den finnes i hvert oppsett, også skrivebeskyttede portaloppføringer.
- **12 språk:** entitetsnavnene er fullt oversatt til engelsk, tysk, fransk, spansk, italiensk, nederlandsk, polsk, tsjekkisk, svensk, dansk, norsk og finsk.

> 💡 **Energidashbord:** ladet-energi-sensoren er `total_increasing`, så legg den til Home Assistants **Energidashbord** direkte, eller pakk den inn i en `utility_meter`-hjelper for daglige/månedlige totaler for ladet energi. Bruk den kumulative **ladet-energi (kWh)**-sensoren til dette — ikke effektivitetssensorene per 100 km (de er gjennomsnitt, ikke målere).

### Tjenester

Integrasjonen leverer **30+ service-kall** (`vag_connect.*`), mange av dem merkespesifikke — *tilgjengelighet avhenger av merke og modell*. Blant dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi forbrenning), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (tilleggs- / parkeringsvarmer — SEAT/CUPRA, Škoda og VW/Audi på en toveis-kommandokanal, der bilen er utstyrt for det), `send_destination` (SEAT/CUPRA/Škoda) og `update_charging_settings` (SEAT/CUPRA), Škodas `ask_assistant` (se under), `set_location_target_soc` og `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send`, og `show_vag`-påskeegget.

---

## evcc

[evcc](https://evcc.io) kan hente bilens ladenivå, rekkevidde og ladestatus rett fra Home Assistant, slik at lading på soloverskudd planlegger ut fra det virkelige batteriet i stedet for et anslag. Det kjører ikke noe ekstra inne i integrasjonen: evcc leser Home Assistants eget REST-API. **Lese**veien virker for **alle merker**, også skrivebeskyttede VW EU-/portalbiler. **Skrive**veien (`chargeEnable`) virker bare på en toveisbil (Audi eller Škoda med en levende kommandokanal) og bare når evcc behandler selve bilen som laderen. Med en ekte smart ladeboks er leseveien alt evcc trenger.

Ferdige `evcc.yaml`-oppskrifter og engangsoppsettet ligger i [docs/EVCC.md](docs/EVCC.md). Denne koblingen er **beta**.

---

## ABRP (A Better Routeplanner) sanntidstelemetri

Du kan pushe bilens sanntidsdata til **[A Better Routeplanner](https://abetterrouteplanner.com/)** slik at den planlegger rundt din faktiske ladetilstand. Det er **valgfritt og av som standard** — ingenting forlater nettverket ditt før du slår det på og en opplasting faktisk kjører.

**1. Skaff de to påloggingsinformasjonene.**

- **`token`** (per kjøretøy) — åpne ABRP-appen → **Innstillinger → bilen din → Live Data → «Generic» / annen bil** og kopier tokenet den viser.
- **`api_key`** (utviklernøkkel) — dette er en partner-/utviklernøkkel utstedt av **iternio**, *ikke* noe appen deler ut. Be om en fra iternio (deres skjema for utvikler-/API-nøkkelforespørsel). **Vi leverer bevisst ingen nøkkel** — å hardkode en vi ikke eier ville vært etterligning og ville bakt inn en ikke-eid hemmelighet i et offentlig repo. Lim inn din egen.

**2. Aktiver den.** Integrasjon → **Konfigurer** → bla til **ABRP**-seksjonen → kryss av *Aktiver ABRP-telemetripush* og lim inn begge verdiene. De valideres som et par (du får en feil hvis bare én er satt), lagres maskert og **skrives aldri til loggen**.

**3. Automatiser opplastingen.** Importer den medfølgende blueprinten **«ABRP — upload telemetry on data change»** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), velg kjøretøyet ditt og dets **ABRP data changed**-sensor, og du er ferdig. Blueprinten laster kun opp når det er et genuint nytt øyeblikksbilde (*ABRP data changed*-binærsensoren er den idempotente utløseren — den nullstilles etter hver vellykkede sending, slik at det samme øyeblikksbildet aldri sendes to ganger).

Du kan også kalle **`vag_connect.abrp_send`**-tjenesten direkte (rett mot en enhet eller VIN; api_key/token kommer fra alternativene med mindre du sender dem inline).

> 🔒 **Personvern:** telemetrien inneholder GPS. Den forlater bare nettverket ditt når `abrp_send` kjører (dvs. når *du* utløser den / aktiverer blueprinten). Det vi sender: ladetilstand, ladestatus, GPS, kurs, energi + kapasitet, estimert rekkevidde, omgivelses- + batteritemperatur, kilometerstand. Det vi bevisst **ikke** sender: alt vi ikke kan måle pålitelig (fart, HV-pakke-spenning/-strøm, state-of-health) — utelatt fremfor gjettet.

---

## Škoda AI-assistent («Laura») — nytt i 3.0.0

MyŠkodas egen innebygde bilassistent, **Laura**, er tilgjengelig inne i Home Assistant.
Spør henne om rekkevidde, lading og turer med tjenesten `vag_connect.ask_assistant`
(hun returnerer et tekstsvar du kan varsle, lese opp eller forgrene på), eller overlat
henne til en **samtaleagent** — den innebygde Assist i LLM-modus, eller OpenAI /
Anthropic / Google / Ollama — som et verktøy den kan kalle og kjede sammen (spør Laura →
send deretter `send_destination` til bilen). Hun er **skrivebeskyttet, rådgivende og kun
for Škoda**; dette er en **beta**, så tilbakemelding på svarkvaliteten er velkommen.

Oppsett, stemmeutløseren («spør Laura …») og ferdige eksempelautomasjoner —
inkludert *bil ankommer hjemme → topp opp + forvarm + les opp rekkevidden* — finnes i
**[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Alternativer (Konfigurer)

Fra **Innstillinger → Enheter og tjenester → VW Group Connect → Konfigurer** kan du justere:
skanneintervall (også tilgjengelig live som spørreintervall-glidebryteren), S-PIN (pluss en S-PIN per kjøretøy når kontoen har mer enn én bil), omvendt geokoding, **skrivebeskyttet modus**, tving PPE-klima (Audi), push-brytere (MQTT/FCM/Audi-VW, alle frivillig beta og av som standard), client-id-overstyring, **`eu_data_act_auto_kickoff`** (på som standard), skjul-tomme-entiteter (på som standard), **ABRP** (aktiver + api_key + brukertoken, validert som et par), pluss **legg til / fjern** de supplerende lesekanalene: `volkswagen.de` (beta), EU Data Act-portal, **Tibber** og den eksperimentelle **Companion-telefon**-kanalen.

---

## Støtt dette prosjektet ❤️

Dette er et enmannsprosjekt — og VW gjør det ikke lett: hver baksystemendring betyr dager med reverse-engineering for å finne en fungerende bane igjen. Den utholdenheten er det som holder det i live der etablerte prosjekter har gitt opp. Hvis det er verdt noe for deg, kan du støtte fortsatt vedlikehold via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Takk! 🙏

---

## Bidra

PR-er er velkomne, se [`CONTRIBUTING.md`](CONTRIBUTING.md). Vanlige spørsmål besvares i [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** gjør ukjente API-felter til en ett-klikks, forhåndsutfylt feilrapport, slik at du kan hjelpe til med å forbedre dekningen uten å lese kode.

## Lisens

[GNU AGPL v3.0-or-later](LICENSE) for integrasjonskoden. Obligatorisk attribusjon + navne-/varemerkebetingelser ved bruk/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Attribusjoner for åpen kildekode fra oppstrøms i [`NOTICE.md`](NOTICE.md).
