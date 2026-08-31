<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>En enda Home Assistant-integration för Volkswagen-koncernens bilar: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW och Audi USA/Kanada</strong><br>
  <em>Batteri, laddning, räckvidd, dörrar, klimat och GPS-position i Home Assistant. Direkt API-åtkomst, flera läskanaler med automatisk växling, ingen mellanprogramvara.</em>
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

**VW Group Connect är en [Home Assistant](https://www.home-assistant.io)-integration som tar in din bil från Volkswagen-koncernen i det smarta hemmet: batteri- och laddstatus, räckvidd, vägmätare, klimat, dörrar och fönster, GPS-position och mer, för Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley och de nordamerikanska VW-/Audi-kontona, allt från en enda konfigurationspost.**

Där märkets backend fortfarande tillåter det skickar den även fjärrkommandon som lås/lås upp, klimat- och laddstyrning. **Det beror på märket, det är inte universellt:** Audi och Škoda är tvåväg, Volkswagen EU via EU Data Act-portalen är skrivskyddad, och kommandon för SEAT/CUPRA blockeras av tillverkaren. Tabellen nedan säger exakt vad som gäller var.

För att fortsätta fungera genom Volkswagens API-förändringar 2026 talar den **flera läskanaler och växlar automatiskt** när en är blockerad: märkenas egna backends, den skrivskyddade fordonsdataportalen **EU Data Act**, en valfri `volkswagen.de`-webbkanal (beta), en valfri **Tibber**-utfyllnad och en varaktig **lösenordsfri** inloggning för äldre Car-Net-bilar. Den samsas utmärkt **med [evcc](https://evcc.io)** (se [docs/EVCC.md](docs/EVCC.md)) och behöver **inget tillägg, ingen broker och ingen mellanliggande container**. Home Assistant installerar automatiskt tre små Python-paket åt den; de används bara av de valfria push- och companion-kanalerna (ADB).

> 🎉 **Nu tillgänglig direkt i HACS** — inget anpassat repository behövs.

---

## Höjdpunkter

- **10 valbara varumärken/källor från Volkswagen-koncernen** i en enda integration: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Kanada, Audi USA/Kanada, Porsche, Bentley och **Audi plug&play (OBD-dongel)** för äldre Audis utan uppkoppling.
- **Äldre Audis utan inbyggd uppkoppling, via en OBD-dongel (nytt i 4.3.0)**: bilar som är osynliga för CARIAD-backenden och EU Data Act-portalen (A4/A5 utan uppkoppling, Touareg, e-up!, …) kan läsas av via molnögonblicksbilden från en TEXA plug&play-dongel — vägmätare, 12 V-batterispänning, varningslampor, senaste parkeringsposition, plus fabriksstamdata (motoreffekt, cylindervolym, färger, modellbeteckning). Skrivskyddad, i sin egen token-silo.
- **Tvåvägsstyrning där märkets backend tillåter det**: lås/lås upp, klimat, laddning, mål-SoC. Det är **per märke, inte universellt**. Titta i tabellen nedan innan du räknar med ett kommando.
- **Škodas inbyggda assistent "Laura" i Home Assistant (nytt i 3.0.0)**: fråga om räckvidd, laddning och resor som en tjänst, eller lämna över den till valfri konversationsagent (den inbyggda Assist, OpenAI, Anthropic, Google, Ollama) som ett verktyg den kan anropa och kedja. Skrivskyddade råd som dina automationer kan agera på.
- **Loggbokshändelser, firmware- & kalenderkort (nytt i 3.1.0)**: tillverkarens push-notiser blir en `event`-entitet per fordon (loggbok + automationer, inget YAML-bussfilter), en skrivskyddad `update`-entitet för firmware visar OTA-status (Škoda i dag, ingen installationsknapp), och två `calendar`-entiteter lägger ut laddschemat + servicens förfallodatum.
- **Lösenordsfri inloggning** (webbläsare/enhetskod) för Audi, SEAT, CUPRA och Audi USA/CA. Inget lösenord lagras i Home Assistant. Škoda gick över till e-post + lösenord i 3.0.1 när VW drog in dess device-code-grant.
- **Flerkanal med automatisk växling**: märkets egen backend, EU Data Act-portalen, valfri vw.de-webb, valfri Tibber, varaktig Car-Net och en OBD-dongel-molnläsare för Audis utan uppkoppling. Faller en kanal bort slocknar inte dina data.
- **Companion-kanal (experimentell, frivillig)**: när alla vägar till backend är stängda kan integrationen läsa av din bil genom att fjärrstyra den officiella appen på en extra Android-telefon. Tre transporter: **ADB över TCP**, [**ADB Bridge-tillägget**](https://github.com/its-me-prash/vwgroup-app-adb-bridge) för moderna telefoner, och — nytt i 4.4.0-betan — en **companion-agentapp** som telefonen kör och som *anropar Home Assistant* via en utgående long-poll så att NAT, växlande IP-adresser och Wi-Fi-klientisolering slutar spela roll (agentappen är en separat artefakt som ännu inte levereras; protokollet finns i [docs/COMPANION_AGENT.md](docs/COMPANION_AGENT.md)). Volkswagen är verifierat mot en riktig enhet; övriga märken är skrivskyddade tills en skärmkarta har bekräftats. Ingenting rotas och inga app-tokens läses ut.
- **Motståndskraftig från grunden**: behåller senast kända värden och senast kända parkeringsposition genom portalavbrott, filtrerar bort falska "ingen avläsning"-vakter, låter aldrig vägmätaren hoppa bakåt, och talar om när en misslyckad inloggning är ett avbrott hos tillverkaren snarare än ditt lösenord.
- **Du styr avfrågningstakten**: ett **avfrågningsintervall-reglage** per konto (en Number-entitet, i minuter) som automationer kan styra, skapat för varje installation, även skrivskyddade portalinstallationer.
- **GPS-enhetsspårning**, 100+ entiteter över flera plattformar, 30+ tjänsteanrop, flera fordon per konto, entitetsnamn på **12 språk**.
- **Porsche går på sin egen backend**, inte på EU Data Act-portalen. Portalvägen *utesluter* Porsche strukturellt, så verktyg som bara bygger på portalen kan aldrig täcka det. Kommandokoden finns här, men själva Porsche-inloggningen är experimentell just nu (se tabellen).
- **Vehicle Data Scout** upptäcker API-drift automatiskt och erbjuder en buggrapport med ett klick — och från 3.0.0 innehåller dess maskerade diagnostiknedladdning även de råa API-svaren, så en enda bilaga är allt som behövs för att lägga till stöd för ett nytt fält. **Quality Scale: Platinum.**

---

## Varumärkesstatus

| Varumärke | Styrning | Data | Anmärkningar |
|---|---|---|---|
| **Audi** (EU) | ✅ Tvåväg | ✅ Fullständig | myAudi-backend (inkl. start/stopp av förbränningsmotor). Äldre Car-Net-Audis kan aktivera en **varaktig MBB-kommandokanal** som överlever omstarter och Play-Integrity-väggen — nytt i 4.4.0, av som standard; nyare ID/MEB-Audis är inte behöriga ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **Škoda** | ✅ Tvåväg | ✅ Fullständig | Škodas egen backend |
| **VW USA/CA** | 🇨🇦 ✅ Tvåväg · 🇺🇸 ⛔ blockerad av VW | 🇨🇦 ✅ Fullständig · 🇺🇸 ⛔ | Kanada loggar in på sin egen server + app-klient och visar fullständiga data, bekräftat mot en riktig kanadensisk ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **USA: sedan 2026-08-13 kräver VW enhetsattestering (Play Integrity) på Nordamerika-planet, så inloggning / token-utbyte i USA misslyckas hårt (401) — en vägg på VW:s sida som en öppen källkodsklient inte kan uppfylla utanför enheten ([#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)).** |
| **VW EU** | 🔒 Skrivskyddad som standard · ⚠️ kommandon = Car-Net **beta** | ✅ Fullständig telemetri via EU Data Act-portalen | Se den ärliga noteringen nedan ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Kommandon blockerade av VW | ✅ EU Data Act-portalen | OLA-åtkomsten drogs in på serversidan 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Tvåväg i väntan på livetest | ✅ Inloggning + läsning | My Bentley, körs på Audi/IDK-tenanten |
| **Porsche** | ⚠️ Experimentell | ⚠️ Experimentell | Porsche Connect, egen backend. Porsche har gått över till appen *Porsche One*, så **inloggningen väntas misslyckas på dagens konton**. Kommandokoden finns men går inte att nå förrän inloggningen byggts om ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⏳ Tvåväg i väntan på livetest | ✅ Fullständig | myAudi NA-backend. USA läser nu från den regionala fordonstjänsten `na` och är **bekräftat fungerande på en riktig USA-Audi Q5** (58 entiteter) — tack @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada använder EMEA-tjänsten. Kommandon ärver Audis tvåvägsvägar men är ännu inte separat livebekräftade på NA ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |
| **Audi plug&play** (OBD-dongel) | ⛔ Skrivskyddad | ✅ Läser via dongelns moln | TEXA OBD-dongel för Audis utan uppkoppling; vägmätare, 12 V, lampor, parkeringsposition + fabriksstamdata. Skrivskyddad, egen token-silo (nytt i 4.3.0) |

> **Ärlig notering om VW EU-styrning.** Volkswagen EU-fordon är **skrivskyddade som standard**: du får fullständig telemetri via EU Data Act-portalen, men inga fjärrkommandon. Den **2026-08-18 stängde VW av den inloggning** som den moderna (CARIAD) tvåvägen använde, så den kanalen går inte längre att sätta upp. Fjärrkommandon för VW EU finns nu **endast som en varaktig Car-Net (MBB) tvåvägs-BETA**, och bara för **äldre MQB / Car-Net**-bilar — det är en valbar inställning, **inte** en standardfunktion. **MEB- / ID-familjens bilar (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) har ingen kommandoväg alls** och skapas skrivskyddade. Car-Net-betan följs i **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testare välkomnas.

> År 2026 lade Volkswagen delar av sitt API bakom enhetsattestering, och har skärpt det under årets gång: **Volkswagen USA slutade fungera 2026-08-13** (Play-Integrity-attestering på Nordamerika-planet, [#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)) och den **moderna VW EU-tvåvägsinloggningen drogs in 2026-08-18**. Den här integrationen tar sig runt attestering där det går (varaktig Car-Net-inloggning, EU Data Act-portal, vw.de-webb) och är transparent med vad varje kanal kan och inte kan göra. **Tips: kör bara en tvåvägsintegration per bil — VW hastighetsbegränsar konton som flera appar hamrar på samtidigt, och ett låst konto slår även ut den officiella appen.**

---

## Kända begränsningar

Några saker är **strukturella** — de kommer från hur Volkswagens backendar fungerar 2026, inte från integrationen, och ingen inställning åtgärdar dem:

- **VW EU är skrivskyddad som standard; kommandon är en MBB-alfa enbart för äldre bilar.** Se varumärkesnoteringen ovan. **MEB- / ID-familjens bilar är skrivskyddade** — den beständiga Car-Net-kommandovägen känner inte igen dem (den svarar "Unknown user"), och VW:s MEB-backend exponerar inget motsvarande. Installationen upptäcker detta och skapar en **skrivskyddad post** (med ett reparationsmeddelande) istället för att misslyckas, så det är en känd gräns, inte en tyst sådan. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT-fjärrkommandon är blockerade av VW.** Åtkomsten till online-tjänster (OLA) för dessa varumärken återkallades på serversidan 2026 (HTTP 403); en ny inloggning eller en uppdaterad app-version återställer den inte. Data flödar fortfarande via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act-portalens data är tunn och varierar mellan bilar.** VW publicerar i dag bara en del av fälten (ofta vägmätare + lås + laddning, ibland mycket mer). Den breddas över tid när VW utökar portalen inför deadline i september 2026 — fält som i dag visar `unknown` kan fyllas i av sig själva, utan att något behöver ändras. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **VW EU-bilar har ingen GPS-position i realtid via EU Data Act-portalen.** Volkswagen Group Info Services har [bekräftat skriftligen](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13#issuecomment-5359744122) att portalens Data Dictionary för kontinuerlig export listar ett kluster med namnet *Spårning av fordonets position* men **ingen definierad datapunkt för bilens aktuella koordinater** (latitud / longitud) — så en VW EU-bil som bara läses via portalen visar sin position som `unknown`. Det här är en gräns i VW:s datauppsättning, inte i integrationen, och tillverkarappens positionsändpunkt har stängts för tredje part. Nordamerikanska VW / Audi och andra märken med en fungerande positionsändpunkt påverkas inte. ([#923](https://github.com/its-me-prash/vwgroup-connect-ha/issues/923))
- **Nordamerika: både VW och Audi läser nu — Audi-kommandon är den sista obekräftade biten.** **VW USA/CA fungerar, inklusive Kanada**, bekräftat mot en riktig kanadensisk ID.4: Kanada loggar in på sin egen server, och sedan rättningen av datahöljet visar den fullständig telemetri ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi USA/CA läser nu också**: USA hämtar från den regionala fordonstjänsten `na`, bekräftat på en riktig USA-Audi Q5 (tack @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada använder EMEA-tjänsten. Kommandon ärver Audis tvåvägsvägar men är ännu inte separat livebekräftade på nordamerikanska konton ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Porsche-inloggningen väntas misslyckas just nu.** Porsche har lagt ned appen *My Porsche*, som den här integrationen autentiserar mot, till förmån för *Porsche One*. Läsning och kommandon är implementerade, men du tar dig troligen inte förbi inloggningen förrän den byggts om. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-uppdateringar (nära realtid) är en frivillig BETA som är av som standard.** MQTT- (Škoda) och Firebase-kanalerna (Audi/VW, CUPRA/SEAT) är kopplade men inte livevaliderade, och märkena skyddar dem i allt högre grad med app-attestering som inte går att uppfylla utanför enheten. Låt dem vara avstängda om du inte vill hjälpa till att testa. Vanlig avfrågning är den väg som stöds.

> **Så här ligger det till.** Enligt EU Data Act (Förordning (EU) 2023/2854) är din bils data *din*. Att köra den här integrationen på din egen hårdvara är *du* som kommer åt *dina egna* data (Artikel 4) — som du har rätt till i samma kvalitet som tillverkaren själv får, i realtid där det är tekniskt möjligt. VW:s skrivskyddade, timmar-gamla portal når inte upp till det i dag. Den här integrationen är medvetet **kanaloberoende**: i samma stund som VW ger ägarna ett gränssnitt i realtid med styrmöjligheter — som Data Act kräver, och som vissa tillverkare redan erbjuder sina ägare — stödjer vi det här, gratis, för alla. Vi står bakom din rätt till realtidsåtkomst till din egen bil.

---

## Installation

**Via HACS (rekommenderas):**

1. Öppna **HACS** i Home Assistant.
2. Sök efter **"VW Group Connect"** och installera den.
3. Starta om Home Assistant.
4. Gå till **Inställningar → Enheter och tjänster → Lägg till integration → VW Group Connect** och följ inloggningsflödet.

<sup>Nyligen upptagen i HACS standard — om den inte går att söka fram än, ge HACS-indexet lite tid att uppdatera, eller lägg till `its-me-prash/vwgroup-connect-ha` som ett anpassat repository under tiden.</sup>

**Lägsta Home Assistant: `2024.4.0`.**

### Inloggningsalternativ (installationsguiden har två vägar)

Integrationens första skärm erbjuder **två** inloggningsmetoder. Välj den som ditt varumärke stöder:

- **Webbläsare / enhetskod (lösenordsfri)** för *Audi, SEAT, CUPRA och Audi USA/CA*. Logga in på mobilen eller datorn och godkänn enheten; inget lösenord lagras i Home Assistant (den behåller en riktig refresh token). Det här steget erbjuder också den valfria **S-PIN** och skanningsintervallet.
- **Portal, e-post + lösenord** för *Volkswagen EU, Škoda, Volkswagen USA/CA, Bentley och Porsche (experimentellt)*. Ange märkets inloggningsuppgifter. Det här steget visar en märkesväljare, e-post, lösenord, valfri **S-PIN**, skanningsintervall och en växel för **"aktivera MBB-kommandon"** — den varaktiga Car-Net-kommandokanalen — för Volkswagen EU och, **nu livevaliderad, för äldre Car-Net-Audi** (av som standard, [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)); lösenordsfria (device-code) Audi-inloggningar erbjuds samma varaktiga-MBB-tillval som ett eget uppsättningssteg. För **Volkswagen USA/Kanada** dyker en **landsväljare (USA eller CA)** upp här; den visas **bara** för det märket och används inte av något annat. **Audi plug&play (OBD-dongel)** är ett eget val — fordon upptäcks automatiskt från dongelns molnkonto.

> **EU Data Act-portalen är inte en tredje inloggningsknapp.** Det är den skrivskyddade strategi som koordinatorn automatiskt faller tillbaka på, och den kan dessutom *läggas till* som en kompletterande läskanal via **Konfigurera → Alternativ**. Detsamma gäller webbkanalen `volkswagen.de` (frivillig beta, bara via Alternativ, skrivskyddad) och den valfria **Tibber**-kanalen, som fyller i fält som förstahandskanalerna lämnat tomma och aldrig skriver över färskare data.

### S-PIN-fältet — när du behöver det

**S-PIN** är säkerhets-PIN-koden i din varumärkesapp. Den är valfri i formuläret och krävs bara för vissa åtgärder: den behövs för **dataavläsningar och kommandon för VW US/Kanada**, och för säkerhetskänsliga fjärrkommandon på varumärken som spärrar dem bakom S-PIN. Lämna den tom om din bil inte frågar efter någon.

---

### Volkswagen EU — få dina data att flöda (viktigt)

För Volkswagen EU är **det inte nog att logga in** — VW strömmar bara fordonsdata när *du* har slagit på datadelning på VW:s sida. Om din bil dyker upp utan data (eller inte dyker upp alls) är det nästan alltid orsaken, **inte** ett felaktigt lösenord. Gör det här en gång:

1. **Lägg till integrationen:** välj **Portal (e-post + lösenord)** och välj **Volkswagen EU**, logga sedan in.
2. **Slutför eventuell engångsuppmaning i VW:s portal.** Öppna VW-dataportalen en gång i en webbläsare eller varumärkesappen och slutför det den ber om: **acceptera villkor, bekräfta samtycke, slutför onboarding / regionval.** Headless-åtkomst kan inte ta sig förbi dessa — detta är fallet `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Bevilja samtycke till datadelning.** I portalen, ställ in **"Use of non-personal data" = Granted** (EU Data Acts samtycke till datadelning).
4. **Leta inte efter någon växel för "kontinuerlig databegäran" — det finns ingen.** Integrationen skapar den begäran åt varje bil själv, och den är **gratis**. Sedan v2.29.0 skapas begäran **utan slutdatum**; tidigare versioner bad om en månad, och det är därför en del installationer tyst slutade leverera data efter ungefär fyra veckor. Om dina data har slutat komma in och du satte upp kontot före v2.29.0, ta bort kontot från integrationen och lägg till det en gång till, så skapas en ny begäran. Utan en begäran returnerar portalen ingenting för det VIN-numret och bilen dyker upp utan avläsningar.
5. **Vänta på att bilen skickar en ögonblicksbild.** Även efter allt ovanstående tar spridningen tid. Bilen kan visa **`offline` / `unknown` ett tag — ofta tills nästa körning eller väckning, upp till ~24 h** — innan sensorerna fylls i. Detta är normalt.

Portalen levererar inledningsvis bara en **del av fälten**, och den delen **breddas över tid** när VW utökar portaltäckningen inför deadline i september 2026 — fält som i dag visar `unknown` kan fyllas i av sig själva. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Fullständig fältlista.** VW-koncernens kompletta officiella dataordbok (varje EU Data Act-nyckel -> fält, beskrivning och enhet) finns i [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Ett veckovis arbetsflöde bevakar portalens ordlistesida och öppnar en pull request när VW publicerar en nyare version, så att tabellen inte tyst blir inaktuell.

> Det är växeln **`eu_data_act_auto_kickoff`** i Alternativ som skapar den där 15-minuters Custom Data Request, och den är **på som standard** — i portalläge finns det inga data utan en. Stäng bara av den om du hellre vill hantera begäran själv.

---

## Vad du får

- **Sensorer:** batteri-SoC, räckvidd (elektrisk / förbränning / total), bränslenivå, vägmätare, temperaturer, laddeffekt, laddhastighet (alltid i km/h, omräknat om bilen rapporterar i mph) och laddtyp, laddmål, historik per laddsession (energi · varaktighet · start · AC/DC, på Škoda och SEAT/CUPRA), resestatistik & livstidsaggregat, service- & oljeserviceintervall, programvaruversion, anslutningsstatus, senast sedd, och — på Škoda — senaste tankning, pågående betalparkeringssession, servicepåminnelser, avgångstimrar och föredraget laddläge, med mera.
- **Binära sensorer:** dörrar låsta, dörrar/fönster/baklucka/motorhuv/soltak öppna, kontakt ansluten, laddar, OTA-uppdatering tillgänglig, lampor, fordon online, avgångstimrar, larm.
- **Styrning:** lås/lås upp, klimat start/stopp, laddning start/stopp, fönstervärme, avgångstimrar, ställ in mål-SoC / temperatur / max laddström, tut-och-blink (med valbar varaktighet, och enbart lampor eller signalhorn också), väck, uppdatera, hitta laddstationer, campingläge och aktiv ventilation (Škoda-kupéventilation utan uppvärmning) *(tillgänglighet beror på varumärke & modell)*.
- **Enhetsspårning:** GPS-position för Home Assistant-kartan. En avfrågning som kommer tillbaka utan koordinater behåller den senast kända parkeringspositionen i stället för att tappa den.
- **Bilder:** fordonsrenderingar där varumärket tillhandahåller dem.
- **Händelser, uppdateringar & kalendrar (nytt i 3.1.0):** en push-`event`-entitet per fordon (tillverkarnotiser i loggboken + automationer), en skrivskyddad **update**-entitet för firmware (Škoda OTA-status — ingen installationsknapp, bilen flashar sig själv), och **kalendrar för laddschema + service** som lägger ut timrar och förfallodatum på en tidslinje.
- **Inställningar:** ett **avfrågningsintervall**-reglage per konto, i minuter, så att en automation kan fråga oftare medan du kör och dra ner på natten. Det finns i varje installation, även skrivskyddade portalposter.
- **12 språk:** entitetsnamnen är fullt översatta till engelska, tyska, franska, spanska, italienska, nederländska, polska, tjeckiska, svenska, danska, norska och finska.

> 💡 **Energipanel:** sensorn för laddad energi är `total_increasing`, så lägg till den i Home Assistant-**energipanelen** direkt, eller linda in den i en `utility_meter`-hjälpare för dagliga/månatliga summor av laddad energi. Använd den ackumulerade sensorn för **laddad energi (kWh)** till detta — inte sensorerna för effektivitet per 100 km (de är medelvärden, inte mätare).

### Tjänster

Integrationen levererar **30+ service-anrop** (`vag_connect.*`), många av dem varumärkesspecifika — *tillgänglighet beror på varumärke & modell*. Bland dem: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi ICE), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (extra-/parkeringsvärmare — SEAT/CUPRA, Škoda och VW/Audi via en tvåvägs-kommandokanal, där bilen är utrustad), `send_destination` (SEAT/CUPRA/Škoda) och `update_charging_settings` (SEAT/CUPRA), Škodas `ask_assistant` (se nedan), `set_location_target_soc` och `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send`, och påskägget `show_vag`.

---

## evcc

[evcc](https://evcc.io) kan hämta bilens laddnivå, räckvidd och laddstatus direkt från Home Assistant, så att solöverskottsladdningen planerar utifrån det verkliga batteriet i stället för en gissning. Inget extra körs inuti integrationen: evcc läser Home Assistants eget REST-API. **Läs**vägen fungerar för **alla märken**, även skrivskyddade VW EU-/portalbilar. **Skriv**vägen (`chargeEnable`) fungerar bara på en tvåvägsbil (Audi eller Škoda med en levande kommandokanal) och bara när evcc behandlar själva bilen som laddaren. Med en riktig smart laddbox räcker läsvägen för evcc.

Färdiga `evcc.yaml`-recept och engångsinställningen finns i [docs/EVCC.md](docs/EVCC.md). Den här kopplingen är **beta**.

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

## iOS Live Activity — laddningsnedräkning på låsskärmen

En inbyggd **Live Activity** (låsskärm + Dynamic Island) som räknar ner till att bilen är färdigladdad, med en förloppsindikator för laddningsnivå. Integrationen exponerar redan en **absolut** tidsstämpel för när laddningen är klar (`sensor.*_charge_complete_eta` på varje elbil), så att iOS kan ticka ner nedräkningen på egen hand — ingen push varje sekund.

**Importera den medföljande blueprinten** *"Live Activity — EV charging countdown (iOS)"* (`blueprints/automation/vag_connect/live_activity_charging_countdown.yaml`), välj bilens sensorer för laddning / SoC / laddningsklar och telefonens `notify.mobile_app_*`-tjänst. Den startar när laddningen börjar, uppdateras när ETA och SoC ändras, och rensas när laddningen stoppar.

> 📱 **Krav:** Home Assistant Companion-appen med **Live Activities** aktiverat (iOS 17.2+, HA Core 2026.7+). Live Activities är just nu en **Labs**-funktion i appens **TestFlight**-bygge — aktivera dem under Labs. En Live Activity kräver en token-handskakning mellan appen och Home Assistant, så telefonen måste kunna nå HA (lokalt eller via en fjärranslutning) när laddningen startar. Detta levereras nu så att du är redo den dag den lämnar TestFlight. **iOS 2026.8 lägger till stöd för iPad och en omdesignad Live Activity — samma blueprint driver båda.**

---

## Škoda AI-assistent ("Laura") — nytt i 3.0.0

MyŠkodas egen inbyggda assistent, **Laura**, finns tillgänglig inuti Home Assistant.
Fråga henne om räckvidd, laddning och resor med tjänsten `vag_connect.ask_assistant`
(hon svarar med ett textsvar som du kan notifiera, läsa upp eller förgrena på), eller lämna
över henne till en **konversationsagent** — den inbyggda Assist i LLM-läge, eller OpenAI /
Anthropic / Google / Ollama — som ett verktyg den kan anropa och kedja (fråga Laura → sedan
`send_destination` till bilen). Hon är **skrivskyddad, rådgivande och endast för Škoda**;
det är en **beta**, så återkoppling på svarens kvalitet välkomnas.

Uppsättning, röstutlösaren ("fråga Laura …"), och färdiga exempel-automationer —
inklusive *bilen kommer hem → fyll på + förvärm + läs upp räckvidden* — finns i
**[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Alternativ (Konfigurera)

Från **Inställningar → Enheter och tjänster → VW Group Connect → Konfigurera** kan du justera:
skanningsintervall (finns också live som avfrågningsintervall-reglaget), S-PIN (plus en S-PIN per fordon när kontot har mer än en bil), omvänd geokodning, **skrivskyddat läge**, tvinga PPE-klimat (Audi), push-växlar (MQTT/FCM/Audi-VW, alla frivillig beta och avstängda som standard), åsidosättning av client-id, **`eu_data_act_auto_kickoff`** (på som standard), dölj-tomma-entiteter (på som standard), **ABRP** (aktivera + api_key + användartoken, valideras som ett par), plus **lägg till / ta bort** de kompletterande läskanalerna: `volkswagen.de` (beta), EU Data Act-portalen, **Tibber** och den experimentella kanalen via en **companion-telefon**.

---

## Stöd det här projektet ❤️

Det här är ett enmansprojekt — och VW gör det inte lätt: varje backend-ändring innebär dagar av reverse engineering för att hitta en fungerande väg igen. Den envisheten är det som håller det vid liv där etablerade projekt har gett upp. Om det är värt något för dig kan du stödja fortsatt underhåll via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Tack! 🙏

### Våra sponsorer

<!-- SPONSORS:START -->
Be the first public sponsor to show up here, and thank you either way!
<!-- SPONSORS:END -->

_Den här listan uppdateras varje vecka och visar bara sponsorer som valt att vara offentliga på GitHub Sponsors. Privata sponsorer namnges aldrig här, bara räknas, och vi tackar dem lika mycket._

---

## Community & Support

Vart du ska vända dig beror på vad du behöver:

- **Frågor, hjälp med installation, dashboard-exempel, "är det här normalt?"** → [GitHub Discussions](https://github.com/its-me-prash/vwgroup-connect-ha/discussions). Allmänna Home Assistant-frågor som inte är specifika för den här integrationen passar bättre på [HA Community Forum](https://community.home-assistant.io).
- **En bugg, ett fel eller ett okänt API-fält** → öppna ett ärende via [New issue → choose a template](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new/choose). **Vehicle Data Scout** förifyller större delen av rapporten åt dig. En användbar rapport anger ditt varumärke, region, Home Assistant- + integrationsversion, och om samma åtgärd fungerar i tillverkarens officiella app — den korta checklistan finns i [`CONTRIBUTING.md`](CONTRIBUTING.md); hur en rapport färdas från inlämning till fix finns i [`docs/TRIAGE.md`](docs/TRIAGE.md).
- **En säkerhetssårbarhet** → **öppna inte** ett publikt ärende. Rapportera den privat via [GitHub Security Advisories](https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new); processen finns i [`SECURITY.md`](SECURITY.md).

### Vad du kan förvänta dig

Det här är ett enmansprojekt som underhålls på fritiden. Svar ges **efter bästa förmåga** — ibland samma dag, ibland långsammare när VW har sönder något och en fix går före i kön. Det finns ingen SLA, och det kommer inte att finnas någon. Ju mer specifik din rapport är (sanerade loggar, maskerad diagnostik, exakta steg), desto snabbare blir den löst. Husregeln, kortversionen: **var hövlig, var specifik, klistra inte in hemligheter — patchar och tålamod når längre än krav.**

### Sätt att hjälpa till

Du behöver inte skriva kod för att föra det här framåt:

- **Skriv bra buggrapporter** och bifoga maskerad diagnostik — en Scout-nedladdning är ofta allt som behövs för att kartlägga ett nytt fält.
- **Testa på en riktig bil.** Flera märken är implementerade men väntar på första livebekräftelsen — se [listan över livetestare](CONTRIBUTING.md#live-testers-wanted).
- **Förbättra översättningar.** Entitetsnamn levereras på 12 språk; rättelser och hjälp med ett nytt språk välkomnas.
- **Skicka en patch.** En PR, en sak — se [`CONTRIBUTING.md`](CONTRIBUTING.md).

Alla som hjälper till krediteras i [`CONTRIBUTORS.md`](CONTRIBUTORS.md) och tackas vid namn i release-anteckningarna. Hur beslut fattas — och vem som har sista ordet i ett enmansunderhållet projekt — står nedskrivet i [`GOVERNANCE.md`](GOVERNANCE.md); grundreglerna för att delta finns i [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Bidra

PR:er välkomnas, se [`CONTRIBUTING.md`](CONTRIBUTING.md). Vanliga frågor besvaras i [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** förvandlar okända API-fält till en förifylld buggrapport med ett klick, så du kan hjälpa till att förbättra täckningen utan att läsa kod.

## Licens

[GNU AGPL v3.0-or-later](LICENSE) för integrationskoden. Obligatorisk attribution + namn-/varumärkesvillkor vid användning/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream open source-attributioner i [`NOTICE.md`](NOTICE.md).
