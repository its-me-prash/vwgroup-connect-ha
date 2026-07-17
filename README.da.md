<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Én Home Assistant-integration til Volkswagen-koncernens mærker — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada · Bentley</strong><br>
  <em>Direkte API-adgang, flerkanals med automatisk fallback, ingen middleware.</em>
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

**VW Group Connect er en [Home Assistant](https://www.home-assistant.io)-integration, der bringer connected car-data og -styring for Volkswagen-koncernens mærker — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Canada og Bentley — ind i dit smarte hjem fra én enkelt konfigurationspost.**

Den viser batteri- og ladestatus, rækkevidde, kilometerstand, klima, døre og vinduer, placering og mere, og — hvor mærkets backend stadig tillader det — sender den fjernkommandoer som lås/lås op, klima- og ladestyring. For at blive ved med at virke gennem Volkswagens API-ændringer i 2026 taler den **flere kanaler og falder automatisk tilbage**, når én er blokeret: de mærkeoprindelige backends, den skrivebeskyttede **EU Data Act**-køretøjsdataportal, en valgfri `volkswagen.de`-webkanal og et vedvarende **adgangskodefrit** login til ældre Car-Net-køretøjer. Den kører gnidningsfrit **sammen med [evcc](https://evcc.io)** og kræver **nul PyPI-afhængigheder**.

> 🎉 **Nu tilgængelig direkte i HACS** — intet custom-repository nødvendigt.

---

## Højdepunkter

- **8 valgbare Volkswagen-koncernmærker** i én integration — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Porsche og Bentley.
- **Porsche-kompatibel** — Porsche kører på sit eget *Porsche Connect*-backend, **ikke** EU Data Act-portalen. Portalstien *udelukker* strukturelt Porsche, så portal-only-værktøjer kan aldrig dække det; det kan denne integration.
- **To-vejs-styring, hvor mærkets backend tillader det** — lås/lås op, klima, opladning, mål-SoC. Læs hvilke mærker, der har ægte kommandounderstøttelse, i tabellen nedenfor; VW EU er skrivebeskyttet som standard (se den ærlige bemærkning der).
- **Adgangskodefrit login-alternativ** (browser/device-code) til Audi/Škoda/SEAT/CUPRA — ingen adgangskode gemt i Home Assistant.
- **Flerkanals med auto-fallback** — mærkeoprindelig → EU Data Act-portal → valgfri vw.de-web → vedvarende Car-Net. Hvis én kanal går ned, gør det ikke dine data mørke.
- **Modstandsdygtig af design** — beholder senest kendte værdier gennem portalnedbrud, filtrerer falske "ingen aflæsning"-vagtsymboler fra, lader aldrig kilometerstanden springe baglæns.
- **GPS-device-tracker**, 100+ entiteter på tværs af flere platforme, 20+ service-calls, flere køretøjer pr. konto.
- **Vehicle Data Scout** — registrerer automatisk API-drift og tilbyder en fejlrapport med ét klik. **Quality Scale: Platinum.**

---

## Mærkestatus

| Mærke | Styring | Data | Bemærkninger |
|---|---|---|---|
| **Audi** | ✅ To-vejs | ✅ Fuld | myAudi-backend (inkl. start/stop af forbrændingsmotor) |
| **Škoda** | ✅ To-vejs | ✅ Fuld | native Škoda-backend |
| **Porsche** | ✅ To-vejs | ✅ Fuld | Porsche Connect — eget backend, ikke EU Data Act-portalen |
| **VW US/CA** | ✅ To-vejs | ✅ Fuld | VW NA-cloud (kræver US/CA-landevælgeren + S-PIN) |
| **VW EU** | 🔒 Skrivebeskyttet som standard · ⚠️ kommandoer = MBB **alfa** | ✅ Fuld telemetri via EU Data Act-portal | Se den ærlige bemærkning nedenfor — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Kommandoer blokeret af VW | ✅ EU Data Act-portal | OLA-adgang tilbagekaldt på serversiden i 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ To-vejs afventer live-test | ✅ Login + læsning | My Bentley — kører på Audi/IDK-tenanten |

> **Ærlig bemærkning om VW EU-styring.** Volkswagen EU-køretøjer er **skrivebeskyttet som standard**: du får fuld telemetri gennem EU Data Act-portalen, men ingen fjernkommandoer. Fjernkommandoer for VW EU findes **kun som en eksperimentel vedvarende MBB to-vejs-ALFA** og kun for **ældre MQB / Car-Net**-biler — det er en tilvalgs-kontakt, **ikke** en standardfunktion. **MEB / ID-familie-biler (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har slet ingen kommandosti** og oprettes skrivebeskyttet. MBB-alfaen spores i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testere velkomne.

> I 2026 lagde Volkswagen dele af sit API bag enhedsattestering. Denne integration ruter uden om det, hvor det er muligt (vedvarende Car-Net-login, EU Data Act-portal, vw.de-web), og er transparent om, hvad hver kanal kan og ikke kan.

---

## Kendte begrænsninger

Et par ting er **strukturelle** — de kommer af, hvordan Volkswagens backends fungerer i 2026, ikke af integrationen, og ingen indstilling retter dem:

- **VW EU er skrivebeskyttet som standard; kommandoer er en MBB-alfa, kun til ældre biler.** Se mærkebemærkningen ovenfor. **MEB / ID-familie-biler er skrivebeskyttet** — den vedvarende Car-Net-kommandosti genkender dem ikke (den svarer "Unknown user"), og VW's MEB-backend eksponerer ikke noget tilsvarende. Opsætningen registrerer dette og opretter en **skrivebeskyttet post** (med en reparationsmeddelelse) i stedet for at fejle, så det er en kendt begrænsning, ikke en stille en. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-fjernkommandoer er blokeret af VW.** Online-services-adgang (OLA) for disse mærker blev tilbagekaldt på serversiden i 2026 (HTTP 403); et nyt login eller en app-versionsopgradering genopretter det ikke. Data flyder stadig via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portaldata er tynde og varierer fra bil til bil.** VW udgiver kun en skive felter i dag (ofte kilometerstand + lås + opladning, nogle gange meget mere). Den udvides over tid, i takt med at VW udbygger portalen frem mod fristen i september 2026 — felter, der læser `unknown` i dag, kan fyldes ud af sig selv, uden nogen ændring. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

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

- **Browser / device-code (adgangskodefri)** — *Audi · Škoda · SEAT · CUPRA.* Log ind på din telefon eller bærbare, og godkend enheden; ingen adgangskode gemmes i Home Assistant (den beholder et ægte refresh-token). Dette trin tilbyder også de valgfrie felter **S-PIN** og scanningsinterval.
- **Portal — e-mail + adgangskode** — *Volkswagen EU · Porsche.* Indtast dit mærke-login. Dette trin viser en mærkevælger (Volkswagen EU, Porsche og de andre e-mail/adgangskode-mærker), e-mail, adgangskode, valgfri **S-PIN**, scanningsinterval og en **"aktivér MBB-kommandoer"**-kontakt (som kun har en effekt på Volkswagen EU — se [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). For **Volkswagen US/Canada** vises her en **landevælger (US vs. CA)** — den gengives **kun** for det mærke og bruges ikke af noget andet.

> **EU Data Act-portalen er ikke en tredje login-knap.** Det er den skrivebeskyttede strategi, som koordinatoren automatisk falder tilbage til, og den kan desuden *tilføjes* som en supplerende læsekanal fra **Konfigurer → Indstillinger**. Det samme gælder `volkswagen.de`-webkanalen (en valgfri, kun-via-Indstillinger, supplerende læsekanal).

### S-PIN-feltet — hvornår du har brug for det

**S-PIN** er sikkerheds-PIN'en i din mærke-app. Den er valgfri i formularen og kun påkrævet til nogle handlinger: den er nødvendig til **VW US/Canada-dataaflæsninger og -kommandoer** og til sikkerhedsfølsomme fjernkommandoer på mærker, der spærrer dem bag S-PIN'en. Lad den stå tom, hvis din bil ikke beder om en.

---

### Volkswagen EU — få dine data til at flyde (vigtigt)

For Volkswagen EU er **det ikke nok at logge ind** — VW streamer først køretøjsdata, når *du* har slået datadeling til på VW's side. Hvis din bil dukker op uden data (eller slet ikke dukker op), er dette næsten altid grunden, **ikke** en forkert adgangskode. Gør dette én gang:

1. **Tilføj integrationen:** vælg **Portal (e-mail + adgangskode)**, og vælg **Volkswagen EU**, og log derefter ind.
2. **Fuldfør enhver engangsanmodning på VW's portal.** Åbn VW-dataportalen én gang i en browser eller mærke-appen, og gennemfør, hvad end den beder om: **accepter vilkår, bekræft samtykke, fuldfør onboarding / regionsvalg.** Headless-adgang kan ikke komme forbi disse — dette er `portal_interaction_required`-tilfældet ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Giv samtykke til datadeling.** På portalen skal du sætte **"Brug af ikke-personhenførbare data" = Givet** (EU Data Act-datadelingssamtykket).
4. **Led ikke efter en kontakt til "løbende dataanmodning" — den findes ikke.** Integrationen opretter selv den anmodning for hver bil. Den registrerer et 1-måneds abonnement på din VW-konto, og det er **gratis**. Uden en anmodning returnerer portalen ingenting for det VIN, og bilen dukker op uden aflæsninger.
5. **Vent på, at bilen pusher et snapshot.** Selv efter alt det ovenstående tager udbredelsen tid. Bilen kan læse **`offline` / `unknown` et stykke tid — ofte indtil dens næste kørsel eller opvækning, op til ~24 t** — før sensorerne fyldes. Dette er normalt.

Portalen serverer indledningsvis kun en **skive felter**, og den skive **udvides over tid**, i takt med at VW udbygger portaldækningen frem mod fristen i september 2026 — felter, der læser `unknown` i dag, kan fyldes ud af sig selv. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> Indstillings-kontakten **`eu_data_act_auto_kickoff`** er den, der opretter 15-minutters Custom Data Request, og den er **slået til som standard** — i portaltilstand er der ingen data uden en. Slå den kun fra, hvis du hellere selv vil styre anmodningen.

---

## Hvad du får

- **Sensorer:** batteri-SoC, rækkevidde (elektrisk / forbrænding / total), brændstofniveau, kilometerstand, temperaturer, ladeeffekt/-hastighed/-type, lademål, turstatistik & levetidsaggregater, service- & olieservice-intervaller, softwareversion, forbindelsesstatus, sidst set og mere.
- **Binærsensorer:** døre låst, døre/vinduer/bagagerum/motorhjelm/soltag åbne, stik tilsluttet, oplader, OTA-opdatering tilgængelig, lys, køretøj online, afgangstimere, alarm.
- **Styring:** lås/lås op, klima start/stop, opladning start/stop, rudevarme, afgangstimere, sæt mål-SoC / temperatur / maks. ladestrøm, dyt-og-blink, opvækning, opdatering, find ladestationer *(tilgængelighed afhænger af mærke & model)*.
- **Device-tracker:** GPS-position til Home Assistant-kortet.
- **Billeder:** køretøjs-renderinger, hvor mærket leverer dem.

> 💡 **Energi-dashboard:** sensoren for opladet energi er `total_increasing`, så føj den direkte til Home Assistants **Energi-dashboard**, eller pak den ind i en `utility_meter`-helper til daglige/månedlige totaler for opladet energi. Brug den kumulative sensor for **opladet energi (kWh)** til dette — ikke effektivitetssensorerne pr. 100 km (de er gennemsnit, ikke målere).

### Tjenester

Integrationen leverer **20+ service-calls** (`vag_connect.*`), mange af dem mærkespecifikke — *tilgængelighed afhænger af mærke & model*. Blandt dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi forbrænding), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` og `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` og `show_vag`-easter egget.

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
scanningsinterval, S-PIN (plus en S-PIN pr. køretøj, når kontoen har mere end én bil), omvendt geokodning, **skrivebeskyttet tilstand**, gennemtving PPE-klima (Audi), push-kontakter (MQTT/FCM/Audi-VW), client-id-tilsidesættelse, **`eu_data_act_auto_kickoff`** (slået til som standard), skjul-tomme-entiteter (slået til som standard), **ABRP** (aktivér + api_key + bruger-token, valideret som et par), plus **tilføj / fjern** de supplerende læsekanaler `volkswagen.de` og EU Data Act-portalen.

---

## Støt dette projekt ❤️

Dette er et enkeltmandsprojekt — og VW gør det ikke let: hver backend-ændring betyder dages reverse engineering for at finde en fungerende sti igen. Den vedholdenhed er, hvad der holder det i live, hvor etablerede projekter har givet op. Hvis det er noget værd for dig, kan du støtte fortsat vedligeholdelse via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Tak! 🙏

---

## Bidrag

PR'er er velkomne — se [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** forvandler ukendte API-felter til en forududfyldt fejlrapport med ét klik, så du kan hjælpe med at forbedre dækningen uden at læse kode.

## Licens

[GNU AGPL v3.0-or-later](LICENSE) for integrationskoden. Obligatorisk attribution + navne-/varemærkebetingelser ved brug/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open source-attributioner i [`NOTICE.md`](NOTICE.md).
