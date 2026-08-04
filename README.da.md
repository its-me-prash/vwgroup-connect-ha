<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Én Home Assistant-integration til Volkswagen-koncernens biler: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW og Audi USA/Canada</strong><br>
  <em>Batteri, opladning, rækkevidde, døre, klima og GPS-position i Home Assistant. Direkte API-adgang, flere læsekanaler med automatisk skift, ingen mellemlag.</em>
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

> ### 📛 Bemærkning om omdøbningen
> Tidligere udgivet som **`vag-connect-ha`** (VAG = Volkswagen AG, gængs DACH-forkortelse).
> Det viser sig, at den forkortelse læses *ret* anderledes for engelsktalende 😅
>
> **Hvad der fortsat virker som før**: alle entiteter (f.eks. `sensor.audi_q4_battery_soc`),
> alle service-calls (`vag_connect.lock`, `vag_connect.show_vag` osv.), alle automatiseringer,
> HACS-installationen — **intet går i stykker**. Det er markedsførings-/visningsnavnet, der ændres,
> koden indeni forbliver uændret. Se [`MIGRATION.md`](MIGRATION.md).
>
> Kæmpe tak til **Home Assistant UK**- og **HA Ideas, Projects and Solutions**-fællesskaberne
> for advarslen — især **Si Gregory**, **Ben Johnson** og **Evets David**.
>
> Og et særligt shoutout til **Jordan Waeles**, hvis `show_vag()`-kommentar nu er et officielt
> understøttet easter egg i denne integration (`vag_connect.show_vag`-service, se CHANGELOG v2.2.3).

---

## Hvad er det?

**VW Group Connect er en [Home Assistant](https://www.home-assistant.io)-integration, der henter din bil fra Volkswagen-koncernen ind i det smarte hjem: batteri- og opladningsstatus, rækkevidde, kilometerstand, klima, døre og ruder, GPS-position og mere, for Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley og de nordamerikanske VW-/Audi-konti, alt sammen fra én konfigurationspost.**

Hvor mærkets backend stadig tillader det, sender den også fjernkommandoer som lås/lås op, klima- og opladningsstyring. **Det afhænger af mærket, det er ikke universelt:** Audi og Škoda er to-vejs, Volkswagen EU via EU Data Act-portalen er skrivebeskyttet, og kommandoer til SEAT/CUPRA er blokeret af producenten. Tabellen nedenfor siger præcis, hvad der gælder hvor.

For at blive ved med at virke gennem Volkswagens API-ændringer i 2026 taler den **flere læsekanaler og skifter automatisk**, når én er blokeret: mærkernes egne backends, den skrivebeskyttede køretøjsdataportal **EU Data Act**, en valgfri `volkswagen.de`-webkanal (beta), en valgfri **Tibber**-udfyldning og et varigt **adgangskodefrit** login til ældre Car-Net-biler. Den kører fint **side om side med [evcc](https://evcc.io)** (se [docs/EVCC.md](docs/EVCC.md)) og kræver **hverken add-on, broker eller mellemliggende container**. Home Assistant installerer automatisk to små Python-pakker til den; de bruges kun af de valgfri push-kanaler.

> 🎉 **Nu tilgængelig direkte i HACS** — intet custom-repository nødvendigt.

---

## Højdepunkter

- **9 valgbare Volkswagen-koncernmærker** i én integration: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Canada, Audi USA/Canada, Porsche og Bentley.
- **To-vejs styring, hvor mærkets backend tillader det**: lås/lås op, klima, opladning, mål-SoC. Det er **pr. mærke, ikke universelt**. Kig i tabellen nedenfor, før du regner med en kommando.
- **Adgangskodefrit login** (browser/device-code) til Audi, Škoda, SEAT, CUPRA og Audi USA/CA. Der gemmes ingen adgangskode i Home Assistant.
- **Flere kanaler med automatisk skift**: mærkets egen backend, EU Data Act-portalen, valgfri vw.de-web, valgfri Tibber, varigt Car-Net. Falder én kanal ud, går dine data ikke i sort.
- **Companion-kanal (eksperimentel, tilvalg)**: når alle backend-veje er lukkede, kan integrationen læse din bil ved at fjernstyre den officielle app på en ekstra Android-telefon via ADB. Volkswagen er verificeret mod en rigtig enhed; de øvrige mærker er skrivebeskyttede, indtil en skærm-mapping er bekræftet. Moderne telefoner kræver [ADB Bridge-add-on'et](https://github.com/its-me-prash/vwgroup-app-adb-bridge); der rootes ingenting, og der læses ingen app-tokens.
- **Robust af design**: beholder de senest kendte værdier og den senest kendte parkeringsposition gennem portalnedbrud, filtrerer falske "ingen måling"-vagter fra, lader aldrig kilometerstanden springe baglæns, og fortæller dig, når et mislykket login er et nedbrud hos producenten og ikke din adgangskode.
- **Du bestemmer opslagsfrekvensen**: en **opslagsinterval-skyder** pr. konto (en Number-entitet, i minutter), som automatiseringer kan styre, oprettet i enhver opsætning, også skrivebeskyttede portalopsætninger.
- **GPS-device-tracker**, 100+ entiteter på tværs af flere platforme, 30+ servicekald, flere køretøjer pr. konto, entitetsnavne på **12 sprog**.
- **Porsche kører på sin egen backend**, ikke på EU Data Act-portalen. Portalvejen *udelukker* Porsche strukturelt, så værktøjer der kun bruger portalen kan aldrig dække det. Kommandokoden ligger her, men selve Porsche-loginet er eksperimentelt lige nu (se tabellen).
- **Vehicle Data Scout** opdager API-drift automatisk og tilbyder en fejlrapport med ét klik. **Quality Scale: Platinum.**

---

## Mærkestatus

| Mærke | Styring | Data | Bemærkninger |
|---|---|---|---|
| **Audi** (EU) | ✅ To-vejs | ✅ Fuld | myAudi-backend (inkl. start/stop af forbrændingsmotor) |
| **Škoda** | ✅ To-vejs | ✅ Fuld | Škodas egen backend |
| **VW USA/CA** | ✅ To-vejs | ✅ Fuld | VW NA-skyen (kræver landevælgeren USA/CA + S-PIN). ⚠️ Canadiske logins blev sendt videre til en host uden et fungerende authorize-endpoint; rettet i v2.26.1 og afventer bekræftelse fra en rigtig canadisk konto ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Skrivebeskyttet som standard · ⚠️ kommandoer = MBB **alpha** | ✅ Fuld telemetri via EU Data Act-portalen | Se den ærlige bemærkning nedenfor ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Kommandoer blokeret af VW | ✅ EU Data Act-portalen | OLA-adgangen blev trukket tilbage på serversiden i 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ To-vejs afventer livetest | ✅ Login + læsning | My Bentley, kører på Audi/IDK-tenanten |
| **Porsche** | ⚠️ Eksperimentel | ⚠️ Eksperimentel | Porsche Connect, egen backend. Porsche er gået over til *Porsche One*-appen, så **loginet forventes at fejle på nuværende konti**. Kommandokoden er der, men er uden for rækkevidde, indtil loginet er bygget om ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⚠️ Eksperimentel | ⚠️ Eksperimentel | Loginet er koblet op mod den nordamerikanske identitetsudbyder, men er **endnu ikke bekræftet** på en rigtig USA-/CA-konto. Testere er velkomne ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Ærlig bemærkning om VW EU-styring.** Volkswagen EU-køretøjer er **skrivebeskyttet som standard**: du får fuld telemetri gennem EU Data Act-portalen, men ingen fjernkommandoer. Fjernkommandoer for VW EU findes **kun som en eksperimentel vedvarende MBB to-vejs-ALFA** og kun for **ældre MQB / Car-Net**-biler — det er en tilvalgs-kontakt, **ikke** en standardfunktion. **MEB / ID-familie-biler (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har slet ingen kommandosti** og oprettes skrivebeskyttet. MBB-alfaen spores i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testere velkomne.

> I 2026 lagde Volkswagen dele af sit API bag enhedsattestering. Denne integration ruter uden om det, hvor det er muligt (vedvarende Car-Net-login, EU Data Act-portal, vw.de-web), og er transparent om, hvad hver kanal kan og ikke kan.

---

## Kendte begrænsninger

Et par ting er **strukturelle** — de kommer af, hvordan Volkswagens backends fungerer i 2026, ikke af integrationen, og ingen indstilling retter dem:

- **VW EU er skrivebeskyttet som standard; kommandoer er en MBB-alfa, kun til ældre biler.** Se mærkebemærkningen ovenfor. **MEB / ID-familie-biler er skrivebeskyttet** — den vedvarende Car-Net-kommandosti genkender dem ikke (den svarer "Unknown user"), og VW's MEB-backend eksponerer ikke noget tilsvarende. Opsætningen registrerer dette og opretter en **skrivebeskyttet post** (med en reparationsmeddelelse) i stedet for at fejle, så det er en kendt begrænsning, ikke en stille en. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-fjernkommandoer er blokeret af VW.** Online-services-adgang (OLA) for disse mærker blev tilbagekaldt på serversiden i 2026 (HTTP 403); et nyt login eller en app-versionsopgradering genopretter det ikke. Data flyder stadig via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portaldata er tynde og varierer fra bil til bil.** VW udgiver kun en skive felter i dag (ofte kilometerstand + lås + opladning, nogle gange meget mere). Den udvides over tid, i takt med at VW udbygger portalen frem mod fristen i september 2026 — felter, der læser `unknown` i dag, kan fyldes ud af sig selv, uden nogen ændring. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Nordamerika er eksperimentelt.** Loginet til **Audi USA/CA** er koblet op, men er aldrig blevet bekræftet mod en rigtig konto ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)). **VW USA/CA** virker, og en routing-fejl, der ødelagde en del canadiske logins, blev rettet i v2.26.1, men ingen har endnu bekræftet det mod en rigtig canadisk konto ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). Vælg ikke denne integration til en nordamerikansk bil i forventning om, at den bare virker.
- **Porsche-loginet forventes at fejle lige nu.** Porsche har udfaset *My Porsche*-appen, som denne integration godkender sig mod, til fordel for *Porsche One*. Læsning og kommandoer er implementeret, men du kommer sandsynligvis ikke forbi loginet, før det er bygget om. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-opdateringer (næsten i realtid) er en frivillig BETA, som er slået fra som standard.** MQTT- (Škoda) og Firebase-kanalerne (Audi/VW, CUPRA/SEAT) er koblet op, men ikke validerede live, og mærkerne skærmer dem i stigende grad af med app-attestering, som ikke kan opfyldes uden for enheden. Lad dem være slået fra, medmindre du vil hjælpe med at teste. Almindelig polling er den understøttede vej.

> **Hvor vi står.** Under EU Data Act (forordning (EU) 2023/2854) er din bils data *dine*. At køre denne integration på din egen hardware er *dig*, der tilgår *dine egne* data (artikel 4) — skyldt i samme kvalitet, som producenten leverer til sig selv, i realtid hvor det er teknisk muligt. VW's skrivebeskyttede, timer-forældede portal lever ikke op til det i dag. Denne integration er bevidst **kanaluafhængig**: i det øjeblik VW giver ejere en realtidskapabel, styrbar grænseflade — som Data Act kræver, og som nogle producenter allerede tilbyder deres ejere — understøtter vi den her, gratis, for alle. Vi støtter din ret til realtidsadgang til din egen bil.

---

## Installation

**Via HACS (anbefalet):**

1. Åbn **HACS** i Home Assistant.
2. Søg efter **"VW Group Connect"**, og installer den.
3. Genstart Home Assistant.
4. Gå til **Indstillinger → Enheder & tjenester → Tilføj integration → VW Group Connect**, og følg login-flowet.

<sup>Netop merget ind i HACS default — hvis den ikke er søgbar endnu, så giv HACS-indekset lidt tid til at opdatere, eller tilføj `its-me-prash/vwgroup-connect-ha` som custom-repository i mellemtiden.</sup>

**Minimum Home Assistant: `2024.4.0`.**

### Login-muligheder (opsætningsguiden har to stier)

Integrationens første skærm tilbyder **to** login-metoder. Vælg den, dit mærke understøtter:

- **Browser / device-code (adgangskodefri)** til *Audi, Škoda, SEAT, CUPRA og Audi USA/CA (eksperimentelt)*. Log ind på din telefon eller bærbare og godkend enheden; der gemmes ingen adgangskode i Home Assistant (den beholder et rigtigt refresh-token). Dette trin tilbyder også den valgfri **S-PIN** og scanningsintervallet.
- **Portal, e-mail + adgangskode** til *Volkswagen EU, Volkswagen USA/CA, Bentley og Porsche (eksperimentelt)*. Indtast dit mærkelogin. Dette trin viser en mærkevælger, e-mail, adgangskode, valgfri **S-PIN**, scanningsinterval og en kontakt til **"aktivér MBB-kommandoer"** (som kun har effekt på Volkswagen EU, se [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen USA/Canada** dukker en **landevælger (USA eller CA)** op her; den vises **kun** for det mærke og bruges ikke af noget andet.

> **EU Data Act-portalen er ikke en tredje login-knap.** Det er den skrivebeskyttede strategi, koordinatoren automatisk falder tilbage på, og den kan derudover *tilføjes* som en supplerende læsekanal via **Konfigurér → Indstillinger**. Det samme gælder webkanalen `volkswagen.de` (frivillig beta, kun via Indstillinger, skrivebeskyttet) og den valgfri **Tibber**-kanal, der udfylder felter, som førstepartskanalerne har efterladt tomme, og aldrig overskriver friskere data.

### S-PIN-feltet — hvornår du har brug for det

**S-PIN** er sikkerheds-PIN'en i din mærke-app. Den er valgfri i formularen og kun påkrævet til nogle handlinger: den er nødvendig til **VW US/Canada-dataaflæsninger og -kommandoer** og til sikkerhedsfølsomme fjernkommandoer på mærker, der spærrer dem bag S-PIN'en. Lad den stå tom, hvis din bil ikke beder om en.

---

### Volkswagen EU — få dine data til at flyde (vigtigt)

For Volkswagen EU er **det ikke nok at logge ind** — VW streamer først køretøjsdata, når *du* har slået datadeling til på VW's side. Hvis din bil dukker op uden data (eller slet ikke dukker op), er dette næsten altid grunden, **ikke** en forkert adgangskode. Gør dette én gang:

1. **Tilføj integrationen:** vælg **Portal (e-mail + adgangskode)**, og vælg **Volkswagen EU**, og log derefter ind.
2. **Fuldfør enhver engangsanmodning på VW's portal.** Åbn VW-dataportalen én gang i en browser eller mærke-appen, og gennemfør, hvad end den beder om: **accepter vilkår, bekræft samtykke, fuldfør onboarding / regionsvalg.** Headless-adgang kan ikke komme forbi disse — dette er `portal_interaction_required`-tilfældet ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Giv samtykke til datadeling.** På portalen skal du sætte **"Brug af ikke-personhenførbare data" = Givet** (EU Data Act-datadelingssamtykket).
4. **Led ikke efter en kontakt til "løbende dataanmodning" — den findes ikke.** Integrationen opretter selv den anmodning for hver bil, og den er **gratis**. Siden v2.29.0 oprettes anmodningen **uden udløbsdato**; tidligere versioner bad om én måned, og det er derfor, at nogle opsætninger stille og roligt gik i stå efter omkring fire uger. Hvis dine data er holdt op, og du satte kontoen op før v2.29.0, så fjern kontoen fra integrationen, og tilføj den igen én gang, så der bliver oprettet en frisk anmodning. Uden en anmodning returnerer portalen ingenting for det VIN, og bilen dukker op uden aflæsninger.
5. **Vent på, at bilen pusher et snapshot.** Selv efter alt det ovenstående tager udbredelsen tid. Bilen kan læse **`offline` / `unknown` et stykke tid — ofte indtil dens næste kørsel eller opvækning, op til ~24 t** — før sensorerne fyldes. Dette er normalt.

Portalen serverer indledningsvis kun en **skive felter**, og den skive **udvides over tid**, i takt med at VW udbygger portaldækningen frem mod fristen i september 2026 — felter, der læser `unknown` i dag, kan fyldes ud af sig selv. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Fuld feltliste.** VW-koncernens komplette officielle dataordbog (hver EU Data Act-nøgle -> felt, beskrivelse og enhed) findes i [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Et ugentligt workflow holder øje med portalens ordbogsside og åbner en pull request, når VW udgiver en nyere version, så tabellen ikke stille og roligt bliver forældet.

> Indstillings-kontakten **`eu_data_act_auto_kickoff`** er den, der opretter 15-minutters Custom Data Request, og den er **slået til som standard** — i portaltilstand er der ingen data uden en. Slå den kun fra, hvis du hellere selv vil styre anmodningen.

---

## Hvad du får

- **Sensorer:** batteri-SoC, rækkevidde (elektrisk / forbrænding / total), brændstofniveau, kilometerstand, temperaturer, ladeeffekt, ladehastighed (altid i km/t, omregnet hvis bilen rapporterer i mph) og ladetype, lademål, turstatistik & levetidsaggregater, service- & olieservice-intervaller, softwareversion, forbindelsesstatus, sidst set og mere.
- **Binærsensorer:** døre låst, døre/vinduer/bagagerum/motorhjelm/soltag åbne, stik tilsluttet, oplader, OTA-opdatering tilgængelig, lys, køretøj online, afgangstimere, alarm.
- **Styring:** lås/lås op, klima start/stop, opladning start/stop, rudevarme, afgangstimere, sæt mål-SoC / temperatur / maks. ladestrøm, dyt-og-blink (med valgfri varighed og enten kun lys eller også horn), opvækning, opdatering, find ladestationer *(tilgængelighed afhænger af mærke & model)*.
- **Device-tracker:** GPS-position til Home Assistant-kortet. Et opslag, der kommer tilbage uden koordinater, beholder den senest kendte parkeringsposition i stedet for at miste den.
- **Billeder:** køretøjs-renderinger, hvor mærket leverer dem.
- **Indstillinger:** en **opslagsinterval**-skyder pr. konto, i minutter, så en automatisering kan spørge oftere, mens du kører, og skrue ned om natten. Den findes i enhver opsætning, også skrivebeskyttede portalposter.
- **12 sprog:** entitetsnavnene er fuldt oversat til engelsk, tysk, fransk, spansk, italiensk, hollandsk, polsk, tjekkisk, svensk, dansk, norsk og finsk.

> 💡 **Energi-dashboard:** sensoren for opladet energi er `total_increasing`, så føj den direkte til Home Assistants **Energi-dashboard**, eller pak den ind i en `utility_meter`-helper til daglige/månedlige totaler for opladet energi. Brug den kumulative sensor for **opladet energi (kWh)** til dette — ikke effektivitetssensorerne pr. 100 km (de er gennemsnit, ikke målere).

### Tjenester

Integrationen leverer **30+ service-calls** (`vag_connect.*`), mange af dem mærkespecifikke — *tilgængelighed afhænger af mærke & model*. Blandt dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi forbrænding), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` og `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` og `show_vag`-easter egget.

---

## evcc

[evcc](https://evcc.io) kan hente bilens ladeniveau, rækkevidde og ladestatus direkte fra Home Assistant, så opladning på soloverskud planlægger ud fra det rigtige batteri i stedet for et gæt. Der kører ikke noget ekstra inde i integrationen: evcc læser Home Assistants eget REST-API. **Læse**vejen virker for **alle mærker**, også skrivebeskyttede VW EU-/portalbiler. **Skrive**vejen (`chargeEnable`) virker kun på en to-vejs bil (Audi eller Škoda med en levende kommandokanal) og kun, når evcc behandler selve bilen som laderen. Med en rigtig smart ladeboks er læsevejen alt, evcc har brug for.

Færdige `evcc.yaml`-opskrifter og engangsopsætningen findes i [docs/EVCC.md](docs/EVCC.md). Denne konnektor er **beta**.

---

## ABRP (A Better Routeplanner) live-telemetri

Du kan pushe din bils live-data til **[A Better Routeplanner](https://abetterrouteplanner.com/)**, så den planlægger ud fra dit reelle ladeniveau. Det er **tilvalg og slået fra som standard** — intet forlader dit netværk, før du slår det til, og et upload rent faktisk kører.

**1. Hent de to loginoplysninger.**

- **`token`** (pr. køretøj) — åbn ABRP-appen → **Settings → din bil → Live Data → "Generic" / anden bil**, og kopiér det token, den viser.
- **`api_key`** (udviklernøgle) — dette er en partner-/udviklernøgle udstedt af **iternio**, *ikke* noget appen udleverer. Anmod om en fra iternio (deres formular til anmodning om udvikler-/API-nøgle). **Vi leverer bevidst ikke en nøgle** — at hardkode en, vi ikke ejer, ville være impersonation og ville bage en ikke-ejet hemmelighed ind i et offentligt repo. Indsæt din egen.

**2. Aktivér det.** Integration → **Konfigurer** → rul til **ABRP**-sektionen → sæt flueben ved *Aktivér ABRP-telemetri-push*, og indsæt begge værdier. De valideres som et par (du får en fejl, hvis kun én er sat), gemmes maskeret og **skrives aldrig til loggen**.

**3. Automatisér uploadet.** Importér det medfølgende blueprint **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), vælg dit køretøj og dets **ABRP data changed**-sensor, og så er du klar. Blueprintet uploader kun, når der er et reelt nyt snapshot (*ABRP data changed*-binærsensoren er den idempotente trigger — den nulstilles efter hver vellykket afsendelse, så det samme snapshot sendes aldrig to gange).

Du kan også kalde tjenesten **`vag_connect.abrp_send`** direkte (målret en enhed eller et VIN; api_key/token kommer fra indstillingerne, medmindre du sender dem inline).

> 🔒 **Privatliv:** telemetrien indeholder GPS. Den forlader kun dit netværk, når `abrp_send` kører (dvs. når *du* udløser den / aktiverer blueprintet). Hvad vi sender: ladeniveau, ladestatus, GPS, kurs, energi + kapacitet, estimeret rækkevidde, omgivelses- + batteritemperatur, kilometerstand. Hvad vi bevidst **ikke** sender: alt, hvad vi ikke kan måle pålideligt (hastighed, HV-pakke-spænding/-strøm, state-of-health) — udeladt frem for gættet.

---

## Indstillinger (Konfigurer)

Under **Indstillinger → Enheder & tjenester → VW Group Connect → Konfigurer** kan du justere:
scanningsinterval (findes også live som opslagsinterval-skyderen), S-PIN (plus en S-PIN pr. køretøj, når kontoen har mere end én bil), omvendt geokodning, **skrivebeskyttet tilstand**, gennemtving PPE-klima (Audi), push-kontakter (MQTT/FCM/Audi-VW, alle frivillig beta og slået fra som standard), client-id-tilsidesættelse, **`eu_data_act_auto_kickoff`** (slået til som standard), skjul-tomme-entiteter (slået til som standard), **ABRP** (aktivér + api_key + bruger-token, valideret som et par), plus **tilføj / fjern** de supplerende læsekanaler: `volkswagen.de` (beta), EU Data Act-portalen, **Tibber** og den eksperimentelle **companion-telefon**-kanal.

---

## Støt dette projekt ❤️

Dette er et enkeltmandsprojekt — og VW gør det ikke let: hver backend-ændring betyder dages reverse engineering for at finde en fungerende sti igen. Den vedholdenhed er, hvad der holder det i live, hvor etablerede projekter har givet op. Hvis det er noget værd for dig, kan du støtte fortsat vedligeholdelse via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Tak! 🙏

---

## Bidrag

PR'er er velkomne, se [`CONTRIBUTING.md`](CONTRIBUTING.md). Almindelige spørgsmål besvares i [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** forvandler ukendte API-felter til en forududfyldt fejlrapport med ét klik, så du kan hjælpe med at forbedre dækningen uden at læse kode.

## Licens

[GNU AGPL v3.0-or-later](LICENSE) for integrationskoden. Obligatorisk attribution + navne-/varemærkebetingelser ved brug/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open source-attributioner i [`NOTICE.md`](NOTICE.md).
