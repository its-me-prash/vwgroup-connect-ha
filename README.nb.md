<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Én Home Assistant-integrasjon for merkene i Volkswagen-konsernet — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada · Bentley</strong><br>
  <em>Direkte API-tilgang, flerkanals med automatisk reserveløsning, ingen mellomvare.</em>
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

**VW Group Connect er en [Home Assistant](https://www.home-assistant.io)-integrasjon som bringer connected-car-data og -styring inn i smarthjemmet ditt for merkene i Volkswagen-konsernet — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Canada og Bentley — fra én enkelt konfigurasjonsoppføring.**

Den viser batteri- og ladetilstand, rekkevidde, kilometerstand, klima, dører og vinduer, plassering og mer, og sender — der merkets baksystem fortsatt tillater det — fjernkommandoer som låsing/opplåsing, klima- og ladestyring. For å fortsette å fungere gjennom Volkswagens API-endringer i 2026 snakker den **flere kanaler og faller automatisk tilbake** når én er blokkert: de merkeegne baksystemene, det skrivebeskyttede **EU Data Act**-portalet for kjøretøydata, en valgfri `volkswagen.de`-webkanal, og en varig **passordløs** pålogging for eldre Car-Net-kjøretøy. Den kjører problemfritt **side om side med [evcc](https://evcc.io)** og trenger **null PyPI-avhengigheter**.

> 🎉 **Nå tilgjengelig direkte i HACS** — ingen custom-repository nødvendig.

---

## Høydepunkter

- **8 valgbare Volkswagen-konsernmerker** i én integrasjon — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Porsche og Bentley.
- **Porsche-støtte** — Porsche kjører på sitt eget *Porsche Connect*-baksystem, **ikke** EU Data Act-portalen. Portalbanen *ekskluderer* Porsche strukturelt, så portal-baserte verktøy kan aldri dekke det; denne integrasjonen kan.
- **Toveisstyring der merkets baksystem tillater det** — låsing/opplåsing, klima, lading, mål-SoC. Les hvilke merker som har ekte kommandostøtte i tabellen nedenfor; VW EU er skrivebeskyttet som standard (se den ærlige merknaden der).
- **Passordløs påloggingsmulighet** (nettleser/enhetskode) for Audi/Škoda/SEAT/CUPRA — ingen passord lagret i Home Assistant.
- **Flerkanals med automatisk reserveløsning** — merkeegen → EU Data Act-portal → valgfri vw.de-web → varig Car-Net. Én kanal som går ned, gjør ikke dataene dine mørke.
- **Robust av design** — beholder sist kjente verdier gjennom portalfeil, filtrerer ut falske «ingen avlesning»-plassholdere, lar aldri kilometerstanden hoppe bakover.
- **GPS-enhetssporer**, 100+ entiteter på tvers av flere plattformer, 20+ service-kall, flere kjøretøy per konto.
- **Vehicle Data Scout** — oppdager API-drift automatisk og tilbyr en ett-klikks feilrapport. **Quality Scale: Platinum.**

---

## Merkestatus

| Merke | Styring | Data | Merknader |
|---|---|---|---|
| **Audi** | ✅ Toveis | ✅ Full | myAudi-baksystem (inkl. start/stopp av forbrenningsmotor) |
| **Škoda** | ✅ Toveis | ✅ Full | nativt Škoda-baksystem |
| **Porsche** | ✅ Toveis | ✅ Full | Porsche Connect — eget baksystem, ikke EU Data Act-portalen |
| **VW US/CA** | ✅ Toveis | ✅ Full | VW NA-sky (trenger US/CA-landvelgeren + S-PIN) |
| **VW EU** | 🔒 Skrivebeskyttet som standard · ⚠️ kommandoer = MBB **alfa** | ✅ Full telemetri via EU Data Act-portalen | Se den ærlige merknaden nedenfor — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Kommandoer blokkert av VW | ✅ EU Data Act-portal | OLA-tilgang trukket tilbake på serversiden i 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Toveis begrenset av live-test | ✅ Pålogging + lesing | My Bentley — kjører på Audi/IDK-tenanten |

> **Ærlig merknad om VW EU-styring.** Volkswagen EU-kjøretøy er **skrivebeskyttet som standard**: du får full telemetri gjennom EU Data Act-portalen, men ingen fjernkommandoer. Fjernkommandoer for VW EU finnes **kun som en eksperimentell varig-MBB toveis-ALFA**, og bare for **eldre MQB- / Car-Net**-biler — det er en valgfri bryter, **ikke** en standardfunksjon. **MEB- / ID-familiebiler (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har ingen kommandobane i det hele tatt** og opprettes skrivebeskyttet. MBB-alfaen spores i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testere er velkomne.

> I 2026 la Volkswagen deler av API-et sitt bak enhetsattestasjon. Denne integrasjonen ruter rundt det der det er mulig (varig Car-Net-pålogging, EU Data Act-portal, vw.de-web) og er åpen om hva hver kanal kan og ikke kan.

---

## Kjente begrensninger

Noen få ting er **strukturelle** — de kommer av hvordan Volkswagens baksystemer fungerer i 2026, ikke av integrasjonen, og ingen innstilling fikser dem:

- **VW EU er skrivebeskyttet som standard; kommandoer er en MBB-alfa kun for eldre biler.** Se merkemerknaden ovenfor. **MEB- / ID-familiebiler er skrivebeskyttet** — den varige Car-Net-kommandobanen gjenkjenner dem ikke (den svarer «Unknown user»), og VWs MEB-baksystem har ingen tilsvarende. Oppsettet oppdager dette og oppretter en **skrivebeskyttet oppføring** (med en reparasjonsmelding) i stedet for å feile, så det er en kjent grense, ikke en stille en. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA- / SEAT-fjernkommandoer er blokkert av VW.** Tilgang til nettjenester (OLA) for disse merkene ble trukket tilbake på serversiden i 2026 (HTTP 403); en ny innlogging eller en oppdatert app-versjon gjenoppretter det ikke. Data flyter fortsatt via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portaldata er tynne og varierer fra bil til bil.** VW publiserer bare et utsnitt av felter i dag (ofte kilometerstand + låsing + lading, noen ganger mye mer). Det utvides over tid etter hvert som VW bygger ut portalen frem mot fristen i september 2026 — felter som i dag viser `unknown`, kan fylle seg av seg selv, uten endring. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

> **Hvor vi står.** Under EU Data Act (Forordning (EU) 2023/2854) er bilens data *dine*. Å kjøre denne integrasjonen på din egen maskinvare er *deg* som får tilgang til *dine egne* data (Artikkel 4) — skyldig i samme kvalitet som produsenten leverer til seg selv, i sanntid der det er teknisk mulig. VWs skrivebeskyttede, timevis utdaterte portal lever ikke opp til dette i dag. Denne integrasjonen er bevisst **kanaluavhengig**: i det øyeblikket VW gir eiere et sanntids, styringsdyktig grensesnitt — slik Data Act krever, og slik noen produsenter allerede tilbyr eierne sine — vil vi støtte det her, gratis, for alle. Vi står bak din rett til sanntidstilgang til din egen bil.

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

- **Nettleser / enhetskode (passordløs)** — *Audi · Škoda · SEAT · CUPRA.* Logg inn på telefonen eller den bærbare PC-en din og godkjenn enheten; ingen passord lagres i Home Assistant (den beholder et ekte refresh-token). Dette steget tilbyr også de valgfrie feltene **S-PIN**, skanneintervall og tving-tilgang.
- **Portal — e-post + passord** — *Volkswagen EU · Porsche.* Skriv inn merkepåloggingen din. Dette steget viser en merkevelger (Volkswagen EU, Porsche og de andre e-post/passord-merkene), e-post, passord, valgfri **S-PIN**, skanneintervall, tving-tilgang, og en **«aktiver MBB-kommandoer»**-bryter (som bare har en effekt på Volkswagen EU — se [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen US/Canada** dukker en **landvelger (US vs. CA)** opp her — den vises **kun** for det merket og brukes ikke av noe annet.

> **EU Data Act-portalen er ikke en tredje påloggingsknapp.** Det er den skrivebeskyttede strategien koordinatoren automatisk faller tilbake til, og den kan i tillegg *legges til* som en supplerende lesekanal fra **Konfigurer → Alternativer**. Det samme gjelder `volkswagen.de`-webkanalen (en valgfri supplerende lesekanal kun tilgjengelig fra Alternativer).

### S-PIN-feltet — når du trenger det

**S-PIN** er sikkerhets-PIN-en til merkeappen din. Den er valgfri i skjemaet og bare påkrevd for enkelte handlinger: den trengs for **datalesing og kommandoer på VW US/Canada**, og for sikkerhetssensitive fjernkommandoer på merker som sperrer dem bak S-PIN-en. La den stå tom hvis bilen din ikke ber om en.

---

### Volkswagen EU — å få dataene dine til å flyte (viktig)

For Volkswagen EU er **det ikke nok å logge inn** — VW streamer kjøretøydata først når *du* har slått på datadeling på VWs side. Hvis bilen din dukker opp uten data (eller ikke dukker opp i det hele tatt), er det nesten alltid grunnen, **ikke** et feil passord. Gjør dette én gang:

1. **Legg til integrasjonen:** velg **Portal (e-post + passord)** og velg **Volkswagen EU**, og logg deretter inn.
2. **Fullfør enhver engangsoppgave på VWs portal.** Åpne VWs dataportal én gang i en nettleser eller merkeappen og fullfør det den ber om: **godta vilkår, bekreft samtykke, fullfør onboarding / regionvalg.** Tilgang uten nettleser kommer ikke forbi disse — dette er tilfellet `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Gi samtykke til datadeling.** I portalen setter du **«Bruk av ikke-personlige data» = Innvilget** (EU Data Act-samtykket til datadeling).
4. **Aktiver den kontinuerlige dataforespørselen** for den aktuelle bilen. Uten den returnerer portalen *ingen dataforespørsel* for den VIN-en, og kjøretøyet dukker opp uten avlesninger.
5. **Vent på at bilen pusher et øyeblikksbilde.** Selv etter alt det ovenfor tar propageringen tid. Bilen kan vise **`offline` / `unknown` en stund — ofte til neste kjøretur eller vekking, opptil ~24 t** — før sensorene fylles. Dette er normalt.

Portalen leverer i utgangspunktet bare et **utsnitt av felter**, og det utsnittet **utvides over tid** etter hvert som VW bygger ut portaldekningen frem mot fristen i september 2026 — felter som i dag viser `unknown`, kan fylle seg av seg selv. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Valgfritt:** Alternativer-bryteren **`eu_data_act_auto_kickoff`** kan opprette 15-minutters Custom Data Request automatisk for deg. Den er valgfri fordi å opprette den innebærer et **1-måneds abonnement på VW-kontoen din**, så integrasjonen gjør det ikke uten din tillatelse.

---

## Hva du får

- **Sensorer:** batteri-SoC, rekkevidde (elektrisk / forbrenning / total), drivstoffnivå, kilometerstand, temperaturer, ladeeffekt/-hastighet/-type, lademål, turstatistikk og totalaggregater, service- og oljeserviceintervaller, programvareversjon, tilkoblingstilstand, sist sett, og mer.
- **Binærsensorer:** dører låst, dører/vinduer/bagasjerom/panser/soltak åpne, plugg tilkoblet, lading, OTA-oppdatering tilgjengelig, lys, kjøretøy online, avreisetimere, alarm.
- **Styring:** låsing/opplåsing, klima start/stopp, lading start/stopp, rutevarme, avreisetimere, sette mål-SoC / temperatur / maks. ladestrøm, tut-og-blink, vekking, oppdatering, finn ladestasjoner *(tilgjengelighet avhenger av merke og modell)*.
- **Enhetssporer:** GPS-posisjon for Home Assistant-kartet.
- **Bilder:** kjøretøyrenderinger der merket leverer dem.

> 💡 **Energidashbord:** ladet-energi-sensoren er `total_increasing`, så legg den til Home Assistants **Energidashbord** direkte, eller pakk den inn i en `utility_meter`-hjelper for daglige/månedlige totaler for ladet energi. Bruk den kumulative **ladet-energi (kWh)**-sensoren til dette — ikke effektivitetssensorene per 100 km (de er gjennomsnitt, ikke målere).

### Tjenester

Integrasjonen leverer **20+ service-kall** (`vag_connect.*`), mange av dem merkespesifikke — *tilgjengelighet avhenger av merke og modell*. Blant dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi forbrenning), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` og `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, og `show_vag`-påskeegget.

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

## Alternativer (Konfigurer)

Fra **Innstillinger → Enheter og tjenester → VW Group Connect → Konfigurer** kan du justere:
skanneintervall, S-PIN, omvendt geokoding, **skrivebeskyttet modus**, tving PPE-klima (Audi), push-brytere (MQTT/FCM/Audi-VW), **EU Data Act-nettleserreserveløsning** (Playwright / ~100 MB Chromium, valgfri), **wake-before-poll** + vekkeforsinkelse, client-id-overstyring, **`eu_data_act_auto_kickoff`**, skjul-tomme-entiteter (på som standard), **ABRP** (aktiver + api_key + brukertoken, validert som et par), pluss **legg til / fjern** de supplerende lesekanalene `volkswagen.de` og EU Data Act-portal.

---

## Støtt dette prosjektet ❤️

Dette er et enmannsprosjekt — og VW gjør det ikke lett: hver baksystemendring betyr dager med reverse-engineering for å finne en fungerende bane igjen. Den utholdenheten er det som holder det i live der etablerte prosjekter har gitt opp. Hvis det er verdt noe for deg, kan du støtte fortsatt vedlikehold via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Takk! 🙏

---

## Bidra

PR-er er velkomne — se [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** gjør ukjente API-felter til en ett-klikks, forhåndsutfylt feilrapport, slik at du kan hjelpe til med å forbedre dekningen uten å lese kode.

## Lisens

[GNU AGPL v3.0-or-later](LICENSE) for integrasjonskoden. Obligatorisk attribusjon + navne-/varemerkebetingelser ved bruk/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Attribusjoner for åpen kildekode fra oppstrøms i [`NOTICE.md`](NOTICE.md).
