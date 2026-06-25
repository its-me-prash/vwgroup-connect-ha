<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>En enda Home Assistant-integration för alla sju Volkswagen Group-märken — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW USA/Kanada</strong><br>
  <em>Direkt API-åtkomst, flera kanaler med automatisk reservväg, ingen mellanprogramvara.</em>
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
  🌍 <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a>
</p>

---

> ### 📛 Om namnbytet
> Hette tidigare **`vag-connect-ha`** (VAG = Volkswagen AG, en helt vanlig förkortning i DACH-länderna).
> Visade sig att den förkortningen läses *ganska* annorlunda av engelsktalande 😅
>
> **Det som fungerar precis som förut**: alla entiteter (t.ex. `sensor.audi_q4_battery_soc`),
> alla tjänsteanrop (`vag_connect.lock`, `vag_connect.show_vag` osv.), alla automationer,
> HACS-installationen – **inget går sönder**. Det är marknads-/visningsnamnet som ändras, koden
> internt förblir oförändrad. Se [`MIGRATION.md`](MIGRATION.md).
>
> Ett stort tack till communityt på **Home Assistant UK** och **HA Ideas, Projects and Solutions**
> för tipset – särskilt **Si Gregory**, **Ben Johnson** och **Evets David**.
>
> Och en extra eloge till **Jordan Waeles**, vars `show_vag()`-kommentar nu är ett officiellt
> stött påskägg i den här integrationen (tjänsten `vag_connect.show_vag`, se CHANGELOG v2.2.3).

---

## Vad är det här?

**VW Group Connect är en integration för [Home Assistant](https://www.home-assistant.io) som tar in data och styrning från uppkopplade bilar i ditt smarta hem – för alla sju Volkswagen Group-märken: Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche och VW USA/Kanada – plus Bentley (skrivskyddat), från en enda konfigurationspost.**

Den visar batteri- och laddningsstatus, räckvidd, vägmätare, klimat, dörrar och fönster, position med mera, och – där märkets backend fortfarande tillåter det – skickar fjärrkommandon som lås/lås upp, klimat- och laddstyrning. För att fortsätta fungera genom Volkswagens API-förändringar 2026 talar den **flera kanaler och växlar automatiskt till en reservväg** när en blockeras: märkenas egna backendar, den skrivskyddade fordonsdataportalen enligt **EU Data Act**, en valfri webbkanal via `volkswagen.de` och en hållbar **lösenordsfri** inloggning för äldre Car-Net-bilar. Den samsas utan problem **med [evcc](https://evcc.io)** och kräver **noll PyPI-beroenden**.

> 🎉 **Nu tillgänglig direkt i HACS** – inget eget repository behövs.

---

## Höjdpunkter

- **Alla 7 VW Group-märken inkl. Porsche och VW USA/Kanada** i en enda integration – EU Data Act-portalen *utesluter* Porsche rent strukturellt, så verktyg som bara bygger på portalen kan aldrig täcka det.
- **Tvåvägsstyrning** där märket tillåter det (lås/lås upp, klimat, laddning, mål-SoC) – inte bara avläsningar.
- **Lösenordsfritt inloggningsalternativ** (webbläsare/enhetskod) – inget lösenord sparas i Home Assistant.
- **Flera kanaler med automatisk reservväg** – märkets egen backend → EU Data Act-portalen → valfri webb via vw.de → hållbar Car-Net. Att en kanal faller släcker inte din data.
- **Robust i grunden** – behåller senast kända värden genom portalavbrott, filtrerar bort falska "ingen avläsning"-markörer och låter aldrig vägmätaren hoppa bakåt.
- **GPS-positionsspårare**, 100+ entiteter över 11 plattformar, 20+ tjänsteanrop, flera fordon per konto.
- **Vehicle Data Scout** – upptäcker automatiskt API-avvikelser och erbjuder en felrapport med ett klick. **Quality Scale: Platinum.**

---

## Status per märke

| Märke | Styrning | Data | Anmärkningar |
|---|---|---|---|
| **Audi** | ✅ Tvåvägs | ✅ Full | myAudi-backend |
| **Škoda** | ✅ Tvåvägs | ✅ Full | Škodas egen backend |
| **Porsche** | ✅ Tvåvägs | ✅ Full | Porsche Connect |
| **VW USA/CA** | ✅ Tvåvägs | ✅ Full | VW NA-molnet |
| **VW EU** | ⚠️ Hållbar Car-Net (äldre modeller) | ✅ EU Data Act + vw.de (beta) | nyare ID/MEB-bilar: skrivskyddat via portalen |
| **CUPRA / SEAT** | ⚠️ Begränsad | ✅ EU Data Act | märkets backend spärrad av VW sedan 2026 |
| **Bentley** | ⏳ Inväntar livetest | ✅ Inloggning + avläsning | My Bentley — kör på Audis plattform/tenant |

> Ärlig anmärkning: under 2026 lade Volkswagen delar av sitt API bakom enhetsattestering. Den här integrationen tar sig runt det där det går (hållbar Car-Net-inloggning, EU Data Act-portalen, vw.de-webben) och är öppen med vad varje kanal kan och inte kan göra.

---

## Kända begränsningar

Några saker är **strukturella** – de beror på hur Volkswagens backendar fungerar 2026, inte på integrationen, och ingen inställning åtgärdar dem:

- **MEB-/ID-bilar är skrivskyddade** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Fjärrkommandon – lås, klimat, laddning – är **inte tillgängliga** för dessa bilar: den hållbara Car-Net-kommandovägen vi använder känner inte igen dem (den svarar "Unknown user"), och VW:s MEB-backend erbjuder ingen motsvarighet. Du får fortfarande telemetri via EU Data Act-portalen – bara ingen styrning. Vid uppsättning upptäcks detta och en **skrivskyddad post** skapas istället för att misslyckas, så det är en känd gräns, inte en tyst sådan.
- **Fjärrkommandon för CUPRA / SEAT blockeras av VW.** Åtkomsten till onlinetjänster (OLA) för dessa märken drogs in på serversidan under 2026 (HTTP 403); varken en ny inloggning eller en uppgraderad app-version återställer den. Data flödar fortfarande via EU Data Act-portalen. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Datan i EU Data Act-portalen är mager och varierar mellan bilar.** VW publicerar i dag bara en bråkdel av fälten (ofta vägmätare + lås + laddning, ibland mycket mer). Det vidgas över tid i takt med att VW bygger ut portalen inför deadline i september 2026 – fält som i dag visar `unknown` kan fylla i sig själva, utan att något behöver ändras. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Installation

**Via HACS (rekommenderas):**

1. Öppna **HACS** i Home Assistant.
2. Sök efter **”VW Group Connect”** och installera den.
3. Starta om Home Assistant.
4. Gå till **Inställningar → Enheter och tjänster → Lägg till integration → VW Group Connect** och följ inloggningsflödet.

<sup>Precis mergad in i HACS default – om den inte går att söka fram än, ge HACS-indexet lite tid att uppdateras, eller lägg till `its-me-prash/vwgroup-connect-ha` som ett eget repository under tiden.</sup>

**Inloggningsalternativ** (välj det din bil/märke stöder):
- **Webbläsare / enhetskod (lösenordsfritt)** – logga in på telefonen eller datorn, godkänn enheten; inget lösenord sparas. (Audi, Škoda, SEAT, CUPRA.)
- **E-post + lösenord** – krävs för Volkswagen EU och Porsche.
- **EU Data Act-portalen** – skrivskyddad reservväg för alla märken.

---

## Vad du får

- **Sensorer:** batteri-SoC, räckvidd (el / förbränning / totalt), bränslenivå, vägmätare, temperaturer, laddeffekt/-hastighet/-typ, laddmål, resstatistik och livstidssummor, service- och oljeserviceintervall, mjukvaruversion, anslutningsstatus, senast sedd med mera.
- **Binära sensorer:** dörrar låsta, dörrar/fönster/baklucka/motorhuv/soltak öppna, kontakt ansluten, laddar, OTA-uppdatering tillgänglig, ljus, fordon online, avfärdstimer, larm.
- **Styrning:** lås/lås upp, starta/stoppa klimat, starta/stoppa laddning, fönstervärme, avfärdstimer, ställ in mål-SoC / temperatur / max laddström, tut-och-blink, väck, uppdatera, hitta laddstationer *(tillgängligheten beror på märke och modell)*.
- **Positionsspårare:** GPS-position för kartan i Home Assistant.
- **Bilder:** fordonsrenderingar där märket tillhandahåller dem.

> 💡 **Energiöversikten:** sensorn för laddad energi är `total_increasing`, så lägg in den direkt i Home Assistants **Energiöversikt**, eller paketera den i en `utility_meter`-hjälpare för dygns-/månadssummor av laddad energi. Använd den kumulativa sensorn för **laddad energi (kWh)** till detta – inte effektivitetssensorerna per 100 km (de är medelvärden, inte mätare).

---

## Stötta projektet ❤️

Det här är ett enmansprojekt – och VW gör det inte enkelt: varje backendförändring innebär dagars reverse engineering för att hitta en fungerande väg igen. Det är den ihärdigheten som håller det vid liv där etablerade projekt har gett upp. Om det är värt något för dig kan du stötta det fortsatta underhållet via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Tack! 🙏

---

## Bidra

PR:er välkomnas – se [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** förvandlar okända API-fält till en förifylld felrapport med ett klick, så du kan hjälpa till att förbättra täckningen utan att läsa kod.

## Licens

[GNU AGPL v3.0-or-later](LICENSE) för integrationskoden. Obligatorisk attribution samt namn-/varumärkesvillkor vid användning/fork: se [`ATTRIBUTION.md`](ATTRIBUTION.md). Attributioner för uppströms öppen källkod finns i [`NOTICE.md`](NOTICE.md).