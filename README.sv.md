<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>En enda Home Assistant-integration för Volkswagen-koncernens varumärken — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Kanada · Bentley</strong><br>
  <em>Direkt API-åtkomst, flerkanalig med automatisk reserv, ingen mellanprogramvara.</em>
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

> ### 📛 Om namnbytet
> Tidigare publicerad som **`vag-connect-ha`** (VAG = Volkswagen AG, vedertagen DACH-förkortning).
> Det visade sig att den förkortningen läses *ganska* annorlunda av engelsktalande 😅
>
> **Det här fungerar precis som förut**: alla entiteter (t.ex. `sensor.audi_q4_battery_soc`),
> alla service-anrop (`vag_connect.lock`, `vag_connect.show_vag` osv.), alla automationer,
> HACS-installationen — **inget går sönder**. Marknadsförings-/visningsnamnet ändras, koden internt
> förblir oförändrad. Se [`MIGRATION.md`](MIGRATION.md).
>
> Ett stort tack till communityna **Home Assistant UK** och **HA Ideas, Projects and Solutions**
> för tipset — särskilt **Si Gregory**, **Ben Johnson** och **Evets David**.
>
> Och en särskild hälsning till **Jordan Waeles**, vars `show_vag()`-kommentar nu är ett officiellt
> stött påskägg i den här integrationen (tjänsten `vag_connect.show_vag`, se CHANGELOG v2.2.3).

---

## Vad är det här?

**VW Group Connect är en [Home Assistant](https://www.home-assistant.io)-integration som tar in uppkopplade fordonsdata och styrning i ditt smarta hem för Volkswagen-koncernens varumärken — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Kanada och Bentley — från en enda konfigurationspost.**

Den visar batteri- och laddningsstatus, räckvidd, vägmätare, klimat, dörrar och fönster, position med mera, och — där varumärkets backend fortfarande tillåter det — skickar fjärrkommandon som lås/lås upp, klimat- och laddningsstyrning. För att fortsätta fungera genom Volkswagens API-ändringar 2026 talar den **flera kanaler och faller automatiskt tillbaka** när en blockeras: de varumärkesegna backendarna, den skrivskyddade fordonsdataportalen **EU Data Act**, en valbar `volkswagen.de`-webbkanal och en beständig **lösenordsfri** inloggning för äldre Car-Net-fordon. Den körs gärna **vid sidan av [evcc](https://evcc.io)** och behöver **noll PyPI-beroenden**.

> 🎉 **Nu tillgänglig direkt i HACS** — inget anpassat repository behövs.

---

## Höjdpunkter

- **8 valbara varumärken från Volkswagen-koncernen** i en integration — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Kanada, Porsche och Bentley.
- **Porsche-kompatibel** — Porsche kör på sin egen *Porsche Connect*-backend, **inte** EU Data Act-portalen. Portalvägen utesluter Porsche strukturellt, så portal-bara verktyg kan aldrig täcka den; det kan den här integrationen.
- **Tvåvägsstyrning där varumärkets backend tillåter det** — lås/lås upp, klimat, laddning, mål-SoC. Läs vilka varumärken som har äkta kommandostöd i tabellen nedan; VW EU är skrivskyddad som standard (se den ärliga noteringen där).
- **Lösenordsfri inloggningsmöjlighet** (webbläsare/enhetskod) för Audi/Škoda/SEAT/CUPRA — inget lösenord lagras i Home Assistant.
- **Flerkanalig med automatisk reserv** — varumärkesegen → EU Data Act-portal → valbar vw.de-webb → beständig Car-Net. Att en kanal faller bort släcker inte dina data.
- **Motståndskraftig i grunden** — behåller senast kända värden genom portalavbrott, filtrerar bort falska "ingen avläsning"-markörer, låter aldrig vägmätaren hoppa bakåt.
- **GPS-enhetsspårning**, 100+ entiteter över flera plattformar, 20+ service-anrop, flera fordon per konto.
- **Vehicle Data Scout** — upptäcker automatiskt API-drift och erbjuder en buggrapport med ett klick. **Quality Scale: Platinum.**

---

## Varumärkesstatus

| Varumärke | Styrning | Data | Anmärkningar |
|---|---|---|---|
| **Audi** | ✅ Tvåväg | ✅ Fullständig | myAudi-backend (inkl. start/stopp av förbränningsmotor) |
| **Škoda** | ✅ Tvåväg | ✅ Fullständig | inbyggd Škoda-backend |
| **Porsche** | ✅ Tvåväg | ✅ Fullständig | Porsche Connect — egen backend, inte EU Data Act-portalen |
| **VW US/CA** | ✅ Tvåväg | ✅ Fullständig | VW NA-moln (kräver landväljaren US/CA + S-PIN) |
| **VW EU** | 🔒 Skrivskyddad som standard · ⚠️ kommandon = MBB **alfa** | ✅ Fullständig telemetri via EU Data Act-portalen | Se den ärliga noteringen nedan — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Kommandon blockerade av VW | ✅ EU Data Act-portal | OLA-åtkomst återkallad på serversidan 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Tvåväg spärrad i väntan på live-test | ✅ Inloggning + läsning | My Bentley — körs på Audi/IDK-tenanten |

> **Ärlig notering om VW EU-styrning.** Volkswagen EU-fordon är **skrivskyddade som standard**: du får fullständig telemetri via EU Data Act-portalen, men inga fjärrkommandon. Fjärrkommandon för VW EU finns **endast som en experimentell beständig-MBB tvåvägs-ALFA**, och bara för **äldre MQB / Car-Net**-bilar — det är en valbar inställning, **inte** en standardfunktion. **MEB- / ID-familjens bilar (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har ingen kommandoväg alls** och skapas skrivskyddade. MBB-alfan följs i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testare välkomnas.

> År 2026 lade Volkswagen delar av sitt API bakom enhetsattestering. Den här integrationen tar sig runt det där det går (beständig Car-Net-inloggning, EU Data Act-portal, vw.de-webb) och är transparent med vad varje kanal kan och inte kan göra.

---

## Kända begränsningar

Några saker är **strukturella** — de kommer från hur Volkswagens backendar fungerar 2026, inte från integrationen, och ingen inställning åtgärdar dem:

- **VW EU är skrivskyddad som standard; kommandon är en MBB-alfa enbart för äldre bilar.** Se varumärkesnoteringen ovan. **MEB- / ID-familjens bilar är skrivskyddade** — den beständiga Car-Net-kommandovägen känner inte igen dem (den svarar "Unknown user"), och VW:s MEB-backend exponerar inget motsvarande. Installationen upptäcker detta och skapar en **skrivskyddad post** (med ett reparationsmeddelande) istället för att misslyckas, så det är en känd gräns, inte en tyst sådan. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-fjärrkommandon är blockerade av VW.** Åtkomsten till online-tjänster (OLA) för dessa varumärken återkallades på serversidan 2026 (HTTP 403); en ny inloggning eller en uppdaterad app-version återställer den inte. Data flödar fortfarande via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portalens data är tunn och varierar mellan bilar.** VW publicerar i dag bara en del av fälten (ofta vägmätare + lås + laddning, ibland mycket mer). Den breddas över tid när VW utökar portalen inför deadline i september 2026 — fält som i dag visar `unknown` kan fyllas i av sig själva, utan att något behöver ändras. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Installation

**Via HACS (rekommenderas):**

1. Öppna **HACS** i Home Assistant.
2. Sök efter **"VW Group Connect"** och installera den.
3. Starta om Home Assistant.
4. Gå till **Inställningar → Enheter och tjänster → Lägg till integration → VW Group Connect** och följ inloggningsflödet.

<sup>Nyligen sammanfogad i HACS standard — om den inte går att söka fram än, ge HACS-indexet lite tid att uppdatera, eller lägg till `its-me-prash/vwgroup-connect-ha` som ett anpassat repository under tiden.</sup>

**Lägsta Home Assistant: `2024.4.0`.**

### Inloggningsalternativ (installationsguiden har två vägar)

Integrationens första skärm erbjuder **två** inloggningsmetoder. Välj den som ditt varumärke stöder:

- **Webbläsare / enhetskod (lösenordsfri)** — *Audi · Škoda · SEAT · CUPRA.* Logga in på din telefon eller laptop och godkänn enheten; inget lösenord lagras i Home Assistant (den behåller en riktig refresh-token). Det här steget erbjuder också de valfria fälten **S-PIN**, skanningsintervall och force-access.
- **Portal — e-post + lösenord** — *Volkswagen EU · Porsche.* Ange din varumärkesinloggning. Det här steget visar en varumärkesväljare (Volkswagen EU, Porsche och de andra e-post/lösenord-varumärkena), e-post, lösenord, valfri **S-PIN**, skanningsintervall, force-access och en växel för **"aktivera MBB-kommandon"** (som bara har effekt på Volkswagen EU — se [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). För **Volkswagen US/Kanada** dyker en **landväljare (US vs CA)** upp här — den visas **endast** för det varumärket och används inte av något annat.

> **EU Data Act-portalen är inte en tredje inloggningsknapp.** Det är den skrivskyddade strategin som koordinatorn automatiskt faller tillbaka till, och den kan dessutom *läggas till* som en kompletterande läskanal från **Konfigurera → Alternativ**. Samma gäller `volkswagen.de`-webbkanalen (en valbar, enbart i Alternativ tillgänglig, kompletterande läskanal).

### S-PIN-fältet — när du behöver det

**S-PIN** är säkerhets-PIN-koden i din varumärkesapp. Den är valfri i formuläret och krävs bara för vissa åtgärder: den behövs för **dataavläsningar och kommandon för VW US/Kanada**, och för säkerhetskänsliga fjärrkommandon på varumärken som spärrar dem bakom S-PIN. Lämna den tom om din bil inte frågar efter någon.

---

### Volkswagen EU — få dina data att flöda (viktigt)

För Volkswagen EU är **det inte nog att logga in** — VW strömmar bara fordonsdata när *du* har slagit på datadelning på VW:s sida. Om din bil dyker upp utan data (eller inte dyker upp alls) är det nästan alltid orsaken, **inte** ett felaktigt lösenord. Gör det här en gång:

1. **Lägg till integrationen:** välj **Portal (e-post + lösenord)** och välj **Volkswagen EU**, logga sedan in.
2. **Slutför eventuell engångsuppmaning i VW:s portal.** Öppna VW-dataportalen en gång i en webbläsare eller varumärkesappen och slutför det den ber om: **acceptera villkor, bekräfta samtycke, slutför onboarding / regionval.** Headless-åtkomst kan inte ta sig förbi dessa — detta är fallet `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Bevilja samtycke till datadelning.** I portalen, ställ in **"Use of non-personal data" = Granted** (EU Data Acts samtycke till datadelning).
4. **Aktivera den kontinuerliga databegäran** för den specifika bilen. Utan den returnerar portalen *no data request* för det VIN-numret och fordonet dyker upp utan avläsningar.
5. **Vänta på att bilen skickar en ögonblicksbild.** Även efter allt ovanstående tar spridningen tid. Bilen kan visa **`offline` / `unknown` ett tag — ofta tills nästa körning eller väckning, upp till ~24 h** — innan sensorerna fylls i. Detta är normalt.

Portalen levererar inledningsvis bara en **del av fälten**, och den delen **breddas över tid** när VW utökar portaltäckningen inför deadline i september 2026 — fält som i dag visar `unknown` kan fyllas i av sig själva. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Valfritt:** växeln **`eu_data_act_auto_kickoff`** i Alternativ kan automatiskt skapa den 15-minuters Custom Data Request åt dig. Den är valbar eftersom att skapa den innebär en **1-månadsprenumeration på ditt VW-konto**, så integrationen gör det inte utan ditt godkännande.

---

## Vad du får

- **Sensorer:** batteri-SoC, räckvidd (elektrisk / förbränning / total), bränslenivå, vägmätare, temperaturer, laddeffekt/laddhastighet/laddtyp, laddmål, resestatistik & livstidsaggregat, service- & oljeserviceintervall, programvaruversion, anslutningsstatus, senast sedd, med mera.
- **Binära sensorer:** dörrar låsta, dörrar/fönster/baklucka/motorhuv/soltak öppna, kontakt ansluten, laddar, OTA-uppdatering tillgänglig, lampor, fordon online, avgångstimrar, larm.
- **Styrning:** lås/lås upp, klimat start/stopp, laddning start/stopp, fönstervärme, avgångstimrar, ställ in mål-SoC / temperatur / max laddström, tut-och-blink, väck, uppdatera, hitta laddstationer *(tillgänglighet beror på varumärke & modell)*.
- **Enhetsspårning:** GPS-position för Home Assistant-kartan.
- **Bilder:** fordonsrenderingar där varumärket tillhandahåller dem.

> 💡 **Energipanel:** sensorn för laddad energi är `total_increasing`, så lägg till den i Home Assistant-**energipanelen** direkt, eller linda in den i en `utility_meter`-hjälpare för dagliga/månatliga summor av laddad energi. Använd den ackumulerade sensorn för **laddad energi (kWh)** till detta — inte sensorerna för effektivitet per 100 km (de är medelvärden, inte mätare).

### Tjänster

Integrationen levererar **20+ service-anrop** (`vag_connect.*`), många av dem varumärkesspecifika — *tillgänglighet beror på varumärke & modell*. Bland dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` och `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, och påskägget `show_vag`.

---

## ABRP (A Better Routeplanner) live-telemetri

Du kan skicka bilens livedata till **[A Better Routeplanner](https://abetterrouteplanner.com/)** så att den planerar utifrån din verkliga laddningsnivå. Det är **valbart och avstängt som standard** — inget lämnar ditt nätverk förrän du slår på det och en uppladdning faktiskt körs.

**1. Skaffa de två uppgifterna.**

- **`token`** (per fordon) — öppna ABRP-appen → **Settings → din bil → Live Data → "Generic" / annan bil** och kopiera den token som visas.
- **`api_key`** (utvecklarnyckel) — det här är en partner-/utvecklarnyckel utfärdad av **iternio**, *inte* något appen delar ut. Begär en från iternio (deras formulär för begäran om utvecklar-/API-nyckel). **Vi levererar medvetet ingen nyckel** — att hårdkoda en vi inte äger vore identitetsstöld och skulle baka in en hemlighet vi inte äger i ett publikt repo. Klistra in din egen.

**2. Aktivera det.** Integration → **Konfigurera** → bläddra till **ABRP**-avsnittet → bocka i *Enable ABRP telemetry push* och klistra in båda värdena. De valideras som ett par (du får ett fel om bara ett är ifyllt), lagras maskerade och **skrivs aldrig till loggen**.

**3. Automatisera uppladdningen.** Importera den medföljande blueprinten **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), välj ditt fordon och dess sensor **ABRP data changed**, så är du klar. Blueprinten laddar bara upp när det finns en genuint ny ögonblicksbild (den binära sensorn *ABRP data changed* är den idempotenta utlösaren — den nollställs efter varje lyckad sändning, så samma ögonblicksbild skickas aldrig två gånger).

Du kan också anropa tjänsten **`vag_connect.abrp_send`** direkt (rikta mot en enhet eller ett VIN; api_key/token hämtas från alternativen om du inte skickar dem inline).

> 🔒 **Integritet:** telemetrin innehåller GPS. Den lämnar bara ditt nätverk när `abrp_send` körs (dvs. när *du* utlöser det / aktiverar blueprinten). Vad vi skickar: laddningsnivå, laddningsstatus, GPS, kurs, energi + kapacitet, beräknad räckvidd, omgivnings- + batteritemperatur, vägmätare. Vad vi medvetet **inte** skickar: något vi inte kan mäta tillförlitligt (hastighet, HV-paketets spänning/ström, state-of-health) — utelämnat snarare än gissat.

---

## Alternativ (Konfigurera)

Från **Inställningar → Enheter och tjänster → VW Group Connect → Konfigurera** kan du justera:
skanningsintervall, S-PIN, omvänd geokodning, **skrivskyddat läge**, tvinga PPE-klimat (Audi), push-växlar (MQTT/FCM/Audi-VW), **EU Data Act-webbläsarreserv** (Playwright / ~100 MB Chromium, valbar), **wake-before-poll** + väckningsfördröjning, åsidosättning av client-id, **`eu_data_act_auto_kickoff`**, dölj-tomma-entiteter (på som standard), **ABRP** (aktivera + api_key + användartoken, valideras som ett par), plus **lägg till / ta bort** de kompletterande läskanalerna `volkswagen.de` och EU Data Act-portalen.

---

## Stöd det här projektet ❤️

Det här är ett enmansprojekt — och VW gör det inte lätt: varje backend-ändring innebär dagar av reverse engineering för att hitta en fungerande väg igen. Den envisheten är det som håller det vid liv där etablerade projekt har gett upp. Om det är värt något för dig kan du stödja fortsatt underhåll via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Tack! 🙏

---

## Bidra

PR:er välkomnas — se [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** förvandlar okända API-fält till en förifylld buggrapport med ett klick, så du kan hjälpa till att förbättra täckningen utan att läsa kod.

## Licens

[GNU AGPL v3.0-or-later](LICENSE) för integrationskoden. Obligatorisk attribution + namn-/varumärkesvillkor vid användning/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open source-attributioner i [`NOTICE.md`](NOTICE.md).
