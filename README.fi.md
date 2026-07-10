<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Yksi Home Assistant -integraatio Volkswagen-konsernin merkeille — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Kanada · Bentley</strong><br>
  <em>Suora API-pääsy, monikanavainen automaattisella varajärjestelmällä, ei väliohjelmistoa.</em>
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

> ### 📛 Huomautus nimenmuutoksesta
> Aiemmin julkaistu nimellä **`vag-connect-ha`** (VAG = Volkswagen AG, vakiintunut DACH-lyhenne).
> Kävi ilmi, että kyseinen lyhenne luetaan *aika* eri tavalla englanninpuhujien korvaan 😅
>
> **Mikä toimii kuten ennenkin**: kaikki entiteetit (esim. `sensor.audi_q4_battery_soc`),
> kaikki palvelukutsut (`vag_connect.lock`, `vag_connect.show_vag` jne.), kaikki automaatiot,
> HACS-asennus — **mikään ei mene rikki**. Markkinointi-/näyttönimi muuttuu, koodin
> sisäinen rakenne pysyy ennallaan. Katso [`MIGRATION.md`](MIGRATION.md).
>
> Valtava kiitos yhteisöille **Home Assistant UK** ja **HA Ideas, Projects and Solutions**
> vinkistä — erityisesti henkilöille **Si Gregory**, **Ben Johnson** ja **Evets David**.
>
> Ja erityismaininta henkilölle **Jordan Waeles**, jonka `show_vag()`-kommentti on nyt virallisesti
> tuettu pääsiäismuna tässä integraatiossa (`vag_connect.show_vag`-palvelu, katso CHANGELOG v2.2.3).

---

## Mikä tämä on?

**VW Group Connect on [Home Assistant](https://www.home-assistant.io) -integraatio, joka tuo verkkoon liitetyn auton tiedot ja hallinnan älykotiisi Volkswagen-konsernin merkeille — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Kanada ja Bentley — yhdestä ainoasta määrityskohteesta.**

Se näyttää akun & latauksen tilan, toimintamatkan, matkamittarin, ilmastoinnin, ovet & ikkunat, sijainnin ja paljon muuta — ja lähettää, missä merkin taustajärjestelmä sen vielä sallii, etäkomentoja kuten lukitus/avaus, ilmastoinnin ja latauksen hallinta. Toimiakseen edelleen Volkswagenin vuoden 2026 API-muutosten läpi se puhuu **useita kanavia ja palautuu automaattisesti**, kun yksi on estetty: merkkien natiivit taustajärjestelmät, vain lukemiseen tarkoitettu **EU Data Act** -ajoneuvodataportaali, valinnainen `volkswagen.de`-verkkokanava ja pysyvä **salasanaton** kirjautuminen vanhemmille Car-Net-ajoneuvoille. Se toimii ongelmitta **[evcc](https://evcc.io):n rinnalla** ja tarvitsee **nolla PyPI-riippuvuutta**.

> 🎉 **Nyt saatavilla suoraan HACS:issa** — ei mukautettua repositoriota tarvita.

---

## Kohokohdat

- **8 valittavaa Volkswagen-konsernin merkkiä** yhdessä integraatiossa — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Kanada, Porsche ja Bentley.
- **Porsche-yhteensopiva** — Porsche kulkee omalla *Porsche Connect* -taustajärjestelmällään, **ei** EU Data Act -portaalilla. Portaalipolku rakenteellisesti *sulkee pois* Porschen, joten pelkkään portaaliin nojaavat työkalut eivät voi koskaan kattaa sitä; tämä integraatio pystyy.
- **Kaksisuuntainen hallinta siellä, missä merkin taustajärjestelmä sen sallii** — lukitus/avaus, ilmastointi, lataus, tavoite-SoC. Lue alla olevasta taulukosta, millä merkeillä on aitoa komentotukea; VW EU on oletuksena vain luku (katso rehellinen huomautus siellä).
- **Salasanaton kirjautumisvaihtoehto** (selain/laitekoodi) merkeille Audi/Škoda/SEAT/CUPRA — salasanaa ei tallenneta Home Assistantiin.
- **Monikanavainen automaattisella varajärjestelmällä** — merkin natiivi → EU Data Act -portaali → valinnainen vw.de-verkko → pysyvä Car-Net. Yhden kanavan kaatuminen ei pimennä dataasi.
- **Kestävä suunnittelultaan** — säilyttää viimeksi tunnetut arvot portaalihäiriöiden läpi, suodattaa valheelliset "ei lukemaa" -merkkiarvot, ei koskaan anna matkamittarin hypätä taaksepäin.
- **GPS-laitepaikannin**, 100+ entiteettiä useilla alustoilla, 20+ palvelukutsua, useita ajoneuvoja tiliä kohti.
- **Vehicle Data Scout** — havaitsee API-ajautuman automaattisesti ja tarjoaa yhden napsautuksen virheraportin. **Quality Scale: Platinum.**

---

## Merkkien tila

| Merkki | Hallinta | Data | Huomautukset |
|---|---|---|---|
| **Audi** | ✅ Kaksisuuntainen | ✅ Täysi | myAudi-taustajärjestelmä (ml. polttomoottorin käynnistys/pysäytys) |
| **Škoda** | ✅ Kaksisuuntainen | ✅ Täysi | natiivi Škoda-taustajärjestelmä |
| **Porsche** | ✅ Kaksisuuntainen | ✅ Täysi | Porsche Connect — oma taustajärjestelmä, ei EU Data Act -portaali |
| **VW US/CA** | ✅ Kaksisuuntainen | ✅ Täysi | VW NA -pilvi (tarvitsee US/CA-maavalitsimen + S-PIN) |
| **VW EU** | 🔒 Oletuksena vain luku · ⚠️ komennot = MBB **alfa** | ✅ Täysi telemetria EU Data Act -portaalin kautta | Katso rehellinen huomautus alla — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Komennot estetty VW:n toimesta | ✅ EU Data Act -portaali | OLA-pääsy peruttu palvelinpuolella vuonna 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Kaksisuuntainen live-testauksella rajattu | ✅ Kirjautuminen + luku | My Bentley — toimii Audi/IDK-vuokralaisympäristössä |

> **Rehellinen huomautus VW EU:n hallinnasta.** Volkswagen EU -ajoneuvot ovat **oletuksena vain luku**: saat täyden telemetrian EU Data Act -portaalin kautta, mutta et etäkomentoja. Etäkomennot VW EU:lle ovat olemassa **vain kokeellisena pysyvän MBB:n kaksisuuntaisena ALFANA**, ja vain **vanhoille MQB / Car-Net** -autoille — se on valinnainen kytkin, **ei** oletusominaisuus. **MEB / ID-perheen autoilla (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) ei ole lainkaan komentopolkua** ja ne luodaan vain lukemista varten. MBB-alfaa seurataan issuessa **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testaajat tervetulleita.

> Vuonna 2026 Volkswagen laittoi osia API:staan laitetodennuksen taakse. Tämä integraatio kiertää sen missä mahdollista (pysyvä Car-Net-kirjautuminen, EU Data Act -portaali, vw.de-verkko) ja on läpinäkyvä siitä, mitä kukin kanava voi ja ei voi tehdä.

---

## Tunnetut rajoitukset

Muutamat asiat ovat **rakenteellisia** — ne johtuvat siitä, miten Volkswagenin taustajärjestelmät toimivat vuonna 2026, eivät integraatiosta, eikä mikään asetus korjaa niitä:

- **VW EU on oletuksena vain luku; komennot ovat MBB-alfa vain vanhoille autoille.** Katso merkin huomautus yllä. **MEB / ID-perheen autot ovat vain luku** — pysyvä Car-Net-komentopolku ei tunnista niitä (se vastaa "Unknown user"), eikä VW:n MEB-taustajärjestelmä tarjoa vastaavaa. Määritys havaitsee tämän ja luo **vain luku -kohteen** (korjausilmoituksen kera) epäonnistumisen sijaan, joten se on tunnettu rajoitus, ei hiljainen. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT -etäkomennot on estetty VW:n toimesta.** Näiden merkkien verkkopalveluiden (OLA) pääsy peruttiin palvelinpuolella vuonna 2026 (HTTP 403); uudelleenkirjautuminen tai sovellusversion päivitys ei palauta sitä. Data kulkee edelleen EU Data Act -portaalin kautta. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act -portaalin data on ohutta ja vaihtelee autoittain.** VW julkaisee tänään vain siivun kentistä (usein matkamittari + lukitus + lataus, joskus paljon enemmän). Se laajenee ajan myötä, kun VW laajentaa portaalia ennen syyskuun 2026 määräaikaa — kentät, jotka lukevat tänään `unknown`, saattavat täyttyä itsestään, ilman muutosta. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

> **Missä olemme.** EU Data Act -asetuksen (asetus 2023/2854) mukaan autosi data on *sinun*. Tämän integraation ajaminen omalla laitteistollasi on *sinä* pääsemässä *omaan* dataasi (4 artikla) — velvoitettuna samalla laadulla kuin valmistaja tarjoaa sen itselleen, reaaliajassa siellä missä teknisesti mahdollista. VW:n vain lukemiseen tarkoitettu, tunteja vanha portaali ei täytä tätä tänään. Tämä integraatio on tarkoituksella **kanavariippumaton**: sillä hetkellä, kun VW antaa omistajille reaaliaikaisen, hallintakelpoisen rajapinnan — kuten Data Act vaatii ja kuten jotkin valmistajat jo tarjoavat omistajilleen — tuemme sitä täällä, ilmaiseksi, kaikille. Tuemme oikeuttasi reaaliaikaiseen pääsyyn omaan autoosi.

---

## Asennus

**HACS:in kautta (suositeltu):**

1. Avaa **HACS** Home Assistantissa.
2. Etsi **"VW Group Connect"** ja asenna se.
3. Käynnistä Home Assistant uudelleen.
4. Mene kohtaan **Asetukset → Laitteet ja palvelut → Lisää integraatio → VW Group Connect** ja seuraa kirjautumisen kulkua.

<sup>Juuri yhdistetty HACS-oletukseen — jos se ei ole vielä haettavissa, anna HACS-indeksin päivittyä hetki, tai lisää sillä välin `its-me-prash/vwgroup-connect-ha` mukautettuna repositoriona.</sup>

**Vähimmäisvaatimus Home Assistant: `2024.4.0`.**

### Kirjautumisvaihtoehdot (ohjatussa määrityksessä on kaksi polkua)

Integraation ensimmäinen näyttö tarjoaa **kaksi** kirjautumistapaa. Valitse se, jota merkkisi tukee:

- **Selain / laitekoodi (salasanaton)** — *Audi · Škoda · SEAT · CUPRA.* Kirjaudu puhelimellasi tai kannettavallasi ja hyväksy laite; salasanaa ei tallenneta Home Assistantiin (se säilyttää aidon päivitystunnisteen). Tässä vaiheessa tarjotaan myös valinnaiset kentät **S-PIN**, skannausväli ja pakota-pääsy.
- **Portaali — sähköposti + salasana** — *Volkswagen EU · Porsche.* Syötä merkin kirjautumistietosi. Tämä vaihe paljastaa merkkivalitsimen (Volkswagen EU, Porsche ja muut sähköposti/salasana-merkit), sähköpostin, salasanan, valinnaisen **S-PIN**:in, skannausvälin, pakota-pääsyn ja **"ota käyttöön MBB-komennot"** -kytkimen (jolla on vaikutusta vain Volkswagen EU:hun — katso [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). **Volkswagen US/Kanadalle** tässä ilmestyy **maavalitsin (US vs. CA)** — se näkyy **vain** kyseiselle merkille eikä mikään muu käytä sitä.

> **EU Data Act -portaali ei ole kolmas kirjautumispainike.** Se on vain lukemiseen tarkoitettu strategia, johon koordinaattori automaattisesti palautuu, ja sen voi lisäksi *lisätä* täydentäväksi lukukanavaksi kohdasta **Määritä → Asetukset**. Sama pätee `volkswagen.de`-verkkokanavaan (valinnainen, vain asetuksista saatava täydentävä lukukanava).

### S-PIN-kenttä — milloin sitä tarvitset

**S-PIN** on merkkisi sovelluksen turva-PIN. Se on lomakkeessa valinnainen ja vaaditaan vain joihinkin toimintoihin: sitä tarvitaan **VW US/Kanadan datalukemiin ja komentoihin** sekä turvakriittisiin etäkomentoihin merkeillä, jotka rajaavat ne S-PIN:in taakse. Jätä se tyhjäksi, jos autosi ei sellaista kysy.

---

### Volkswagen EU — datan saaminen liikkeelle (tärkeää)

Volkswagen EU:lla **kirjautuminen ei riitä** — VW streamaa ajoneuvon dataa vasta, kun *sinä* olet kytkenyt datan jakamisen päälle VW:n puolella. Jos autosi ilmestyy ilman dataa (tai ei ilmesty lainkaan), tämä on lähes aina syy, **ei** väärä salasana. Tee tämä kerran:

1. **Lisää integraatio:** valitse **Portaali (sähköposti + salasana)** ja valitse **Volkswagen EU**, kirjaudu sitten sisään.
2. **Suorita mahdollinen kertaluonteinen kehote VW:n portaalissa.** Avaa VW:n dataportaali kerran selaimessa tai merkin sovelluksessa ja suorita loppuun, mitä se pyytää: **hyväksy ehdot, vahvista suostumus, viimeistele käyttöönotto / alueen valinta.** Selaimeton pääsy ei pääse näiden ohi — tämä on `portal_interaction_required`-tapaus ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Myönnä datan jakamisen suostumus.** Aseta portaalissa **"Ei-henkilökohtaisen datan käyttö" = Myönnetty** (EU Data Act -datan jakamisen suostumus).
4. **Ota käyttöön jatkuva datapyyntö** kyseiselle autolle. Ilman sitä portaali palauttaa *ei datapyyntöä* kyseiselle VIN:ille ja ajoneuvo ilmestyy ilman lukemia.
5. **Odota, että auto pushaa tilannekuvan.** Jopa kaiken yllä olevan jälkeen leviäminen vie aikaa. Auto voi lukea **`offline` / `unknown` jonkin aikaa — usein seuraavaan ajoon tai heräämiseen asti, jopa ~24 h** — ennen kuin anturit täyttyvät. Tämä on normaalia.

Portaali tarjoaa aluksi vain **siivun kentistä**, ja tämä siivu **laajenee ajan myötä**, kun VW laajentaa portaalin kattavuutta ennen syyskuun 2026 määräaikaa — kentät, jotka lukevat tänään `unknown`, saattavat täyttyä itsestään. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Valinnainen:** asetuskytkin **`eu_data_act_auto_kickoff`** voi luoda 15 minuutin mukautetun datapyynnön puolestasi automaattisesti. Se on valinnainen, koska sen luominen tarkoittaa **1 kuukauden tilausta VW-tililläsi**, joten integraatio ei tee sitä ilman lupaasi.

---

## Mitä saat

- **Anturit:** akun SoC, toimintamatka (sähkö / polttomoottori / kokonais), polttoainetaso, matkamittari, lämpötilat, latausteho/-nopeus/-tyyppi, lataustavoite, matkatilastot & käyttöiän kertymät, huolto- & öljyhuoltovälit, ohjelmistoversio, yhteyden tila, viimeksi nähty ja muuta.
- **Binäärianturit:** ovet lukittu, ovet/ikkunat/tavaratila/konepelti/kattoluukku auki, pistoke kytketty, latautuu, OTA-päivitys saatavilla, valot, ajoneuvo verkossa, lähtöajastimet, hälytys.
- **Hallinta:** lukitus/avaus, ilmastoinnin käynnistys/pysäytys, latauksen käynnistys/pysäytys, ikkunanlämmitys, lähtöajastimet, tavoite-SoC:n / lämpötilan / suurimman latausvirran asetus, äänimerkki-ja-vilkutus, herätys, päivitys, latausasemien haku *(saatavuus riippuu merkistä & mallista)*.
- **Laitepaikannin:** GPS-sijainti Home Assistant -karttaan.
- **Kuvat:** ajoneuvon renderöinnit, missä merkki niitä tarjoaa.

> 💡 **Energiapaneeli:** ladatun energian anturi on `total_increasing`, joten lisää se suoraan Home Assistantin **Energiapaneeliin**, tai kääri se `utility_meter`-apuriin päivittäisiä/kuukausittaisia ladatun energian summia varten. Käytä tähän kumulatiivista **ladattu energia (kWh)** -anturia — älä per-100 km hyötysuhdeantureita (ne ovat keskiarvoja, eivät mittareita).

### Palvelut

Integraatio toimittaa **20+ palvelukutsua** (`vag_connect.*`), monet niistä merkkikohtaisia — *saatavuus riippuu merkistä & mallista*. Niiden joukossa: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi polttomoottori), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` ja `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, ja `show_vag`-pääsiäismuna.

---

## ABRP (A Better Routeplanner) -live-telemetria

Voit pushata autosi live-datan **[A Better Routeplanner](https://abetterrouteplanner.com/)**iin, jotta se suunnittelee reitin todellisen latauksesi mukaan. Se on **valinnainen ja oletuksena pois päältä** — mitään ei lähde verkostasi ennen kuin kytket sen päälle ja lähetys tosiasiassa suoritetaan.

**1. Hanki kaksi kirjautumistietoa.**

- **`token`** (ajoneuvokohtainen) — avaa ABRP-sovellus → **Asetukset → autosi → Live Data → "Generic" / muu auto** ja kopioi sen näyttämä tunniste.
- **`api_key`** (kehittäjäavain) — tämä on **iternion** myöntämä kumppani-/kehittäjäavain, *ei* jotain, mitä sovellus antaa. Pyydä sellainen iterniolta (heidän kehittäjä-/API-avainpyyntölomakkeensa). **Emme tarkoituksella toimita avainta** — sellaisen kovakoodaaminen, joka ei ole meidän, olisi esiintymistä toisena ja upottaisi omistamattoman salaisuuden julkiseen repositorioon. Liitä oma.

**2. Ota se käyttöön.** Integraatio → **Määritä** → vieritä **ABRP**-osioon → rastita *Ota käyttöön ABRP-telemetrian lähetys* ja liitä molemmat arvot. Ne validoidaan parina (saat virheen, jos vain toinen on asetettu), tallennetaan peitettynä ja **niitä ei koskaan kirjoiteta lokiin**.

**3. Automatisoi lähetys.** Tuo mukana tuleva sinihahmo **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), valitse ajoneuvosi ja sen **ABRP data changed** -anturi, ja olet valmis. Sinihahmo lataa vain, kun on aidosti uusi tilannekuva (*ABRP data changed* -binäärianturi on idempotentti laukaisin — se nollautuu jokaisen onnistuneen lähetyksen jälkeen, joten samaa tilannekuvaa ei koskaan lähetetä kahdesti).

Voit myös kutsua palvelua **`vag_connect.abrp_send`** suoraan (kohdista laitteeseen tai VIN:iin; api_key/token tulevat asetuksista, ellet välitä niitä sisäisesti).

> 🔒 **Yksityisyys:** telemetria sisältää GPS:n. Se lähtee verkostasi vain, kun `abrp_send` suoritetaan (eli kun *sinä* laukaiset sen / otat sinihahmon käyttöön). Mitä lähetämme: latauksen tila, latausstatus, GPS, kulkusuunta, energia + kapasiteetti, arvioitu toimintamatka, ympäristön + akun lämpötila, matkamittari. Mitä tarkoituksella **emme** lähetä: mitään, mitä emme voi mitata luotettavasti (nopeus, HV-paketin jännite/virta, kunnon tila) — jätetty pois pikemminkin kuin arvattu.

---

## Asetukset (Määritä)

Kohdasta **Asetukset → Laitteet ja palvelut → VW Group Connect → Määritä** voit säätää:
skannausväliä, S-PIN:iä, käänteistä geokoodausta, **vain luku -tilaa**, pakota PPE-ilmastointi (Audi), push-kytkimet (MQTT/FCM/Audi-VW), **EU Data Act -selainvarajärjestelmä** (Playwright / ~100 Mt Chromium, valinnainen), **herätä-ennen-kyselyä** + herätysviive, client-id-ohitus, **`eu_data_act_auto_kickoff`**, piilota tyhjät entiteetit (oletuksena päällä), **ABRP** (käyttöönotto + api_key + käyttäjätunniste, validoitu parina), sekä `volkswagen.de`- ja EU Data Act -portaalin täydentävien lukukanavien **lisääminen / poistaminen**.

---

## Tue tätä projektia ❤️

Tämä on yhden ihmisen projekti — eikä VW tee siitä helppoa: jokainen taustajärjestelmän muutos tarkoittaa päiviä käänteistä suunnittelua, jotta toimiva polku löytyy taas. Tuo sinnikkyys on se, mikä pitää sen elossa siellä, missä vakiintuneet projektit ovat luovuttaneet. Jos se on sinulle jotain arvoista, voit tukea jatkuvaa ylläpitoa **[GitHub Sponsorsin](https://github.com/sponsors/its-me-prash)** kautta. Kiitos! 🙏

---

## Osallistuminen

PR:t tervetulleita — katso [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** muuttaa tuntemattomat API-kentät yhden napsautuksen, valmiiksi täytetyksi virheraportiksi, joten voit auttaa parantamaan kattavuutta lukematta koodia.

## Lisenssi

[GNU AGPL v3.0-or-later](LICENSE) integraatiokoodille. Pakollinen attribuutio + nimi-/tavaramerkkiehdot käytössä/forkissa: katso [`ATTRIBUTION.md`](ATTRIBUTION.md). Ylävirran avoimen lähdekoodin attribuutiot tiedostossa [`NOTICE.md`](NOTICE.md).
