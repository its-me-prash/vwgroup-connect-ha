<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Yksi Home Assistant -integraatio Volkswagen-konsernin autoille: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW ja Audi USA/Kanada</strong><br>
  <em>Akku, lataus, toimintamatka, ovet, ilmastointi ja GPS-sijainti Home Assistantissa. Suora API-yhteys, useita lukukanavia automaattisella vaihdolla, ei välikerrosta.</em>
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

**VW Group Connect on [Home Assistant](https://www.home-assistant.io) -integraatio, joka tuo Volkswagen-konsernin autosi älykotiin: akun ja latauksen tilan, toimintamatkan, matkamittarin, ilmastoinnin, ovet ja ikkunat, GPS-sijainnin ja muuta, merkeille Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley sekä pohjoisamerikkalaisille VW- / Audi-tileille, kaikki yhdestä konfiguraatiomerkinnästä.**

Siellä missä merkin taustajärjestelmä sen vielä sallii, se lähettää myös etäkomentoja, kuten lukitus/avaus sekä ilmastoinnin ja latauksen ohjaus. **Tämä riippuu merkistä, se ei ole yleispätevää:** Audi ja Škoda ovat kaksisuuntaisia, Volkswagen EU EU Data Act -portaalin kautta on vain luettava, ja SEATin/CUPRAn komennot on valmistaja estänyt. Alla oleva taulukko kertoo täsmälleen, mikä on mitäkin.

Jotta se toimisi Volkswagenin vuoden 2026 API-muutosten läpi, se puhuu **useaa lukukanavaa ja vaihtaa automaattisesti**, kun yksi on estetty: merkkien omat taustajärjestelmät, vain luettava **EU Data Act** -ajoneuvodataportaali, valinnainen `volkswagen.de`-verkkokanava (beta), valinnainen **Tibber**-täydennys ja kestävä **salasanaton** kirjautuminen vanhemmille Car-Net-autoille. Se toimii vaivatta **[evcc](https://evcc.io):n rinnalla** (katso [docs/EVCC.md](docs/EVCC.md)) eikä tarvitse **lisäosaa, brokeria eikä välikonttia**. Home Assistant asentaa sille automaattisesti kaksi pientä Python-pakettia; niitä käyttävät vain valinnaiset push-kanavat.

> 🎉 **Nyt saatavilla suoraan HACS:issa** — ei mukautettua repositoriota tarvita.

---

## Kohokohdat

- **9 valittavaa Volkswagen-konsernin merkkiä** yhdessä integraatiossa: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Kanada, Audi USA/Kanada, Porsche ja Bentley.
- **Kaksisuuntainen ohjaus siellä, missä merkin taustajärjestelmä sen sallii**: lukitus/avaus, ilmastointi, lataus, tavoite-SoC. Tämä on **merkkikohtaista, ei yleispätevää**. Katso alla oleva taulukko ennen kuin luotat johonkin komentoon.
- **Salasanaton kirjautumisvaihtoehto** (selain/laitekoodi) merkeille Audi, Škoda, SEAT, CUPRA ja Audi USA/CA. Home Assistantiin ei tallenneta salasanaa.
- **Monikanavaisuus automaattisella vaihdolla**: merkin oma taustajärjestelmä, EU Data Act -portaali, valinnainen vw.de-verkkokanava, valinnainen Tibber, kestävä Car-Net. Yhden kanavan kaatuminen ei pimennä dataasi.
- **Kumppanikanava (kokeellinen, valinnainen)**: kun kaikki taustajärjestelmäpolut ovat kiinni, integraatio voi lukea autoasi ohjaamalla virallista sovellusta ylimääräisessä Android-puhelimessa ADB:n kautta. Volkswagen on vahvistettu oikealla laitteella; muut merkit ovat vain luettavia, kunnes näyttökartta on vahvistettu. Uudemmat puhelimet tarvitsevat [ADB Bridge -lisäosan](https://github.com/its-me-prash/vwgroup-app-adb-bridge); mitään ei rootata eikä sovelluksen tunnisteita lueta.
- **Kestävä rakenteeltaan**: säilyttää viimeksi tunnetut arvot ja viimeksi tunnetun pysäköintipaikan portaalikatkojen yli, suodattaa valheelliset "ei lukemaa" -vartijat, ei koskaan päästä matkamittaria hyppäämään taaksepäin ja kertoo, kun epäonnistunut kirjautuminen johtuu valmistajan häiriöstä eikä salasanastasi.
- **Sinä päätät kyselytahdin**: tilikohtainen **kyselyvälin liukusäädin** (Number-entiteetti, minuutteina), jota automaatiot voivat ohjata, luodaan jokaiseen asennukseen, myös vain luettaviin portaaliasennuksiin.
- **GPS-laitepaikannin**, yli 100 entiteettiä useilla alustoilla, yli 30 palvelukutsua, useita ajoneuvoja tiliä kohden, entiteettien nimet **12 kielellä**.
- **Porsche toimii omalla taustajärjestelmällään**, ei EU Data Act -portaalilla. Portaalireitti *sulkee* Porschen rakenteellisesti pois, joten pelkkään portaaliin nojaavat työkalut eivät voi koskaan kattaa sitä. Komentokoodi on täällä, mutta itse Porsche-kirjautuminen on tällä hetkellä kokeellinen (katso taulukko).
- **Vehicle Data Scout** havaitsee API-muutokset automaattisesti ja tarjoaa yhden napsautuksen vikailmoituksen. **Quality Scale: Platinum.**

---

## Merkkien tila

| Merkki | Hallinta | Data | Huomautukset |
|---|---|---|---|
| **Audi** (EU) | ✅ Kaksisuuntainen | ✅ Täysi | myAudi-taustajärjestelmä (ml. polttomoottorin käynnistys/sammutus) |
| **Škoda** | ✅ Kaksisuuntainen | ✅ Täysi | Škodan oma taustajärjestelmä |
| **VW USA/CA** | ✅ Kaksisuuntainen | ✅ Täysi | VW NA -pilvi (vaatii USA/CA-maavalitsimen + S-PIN:n). Kanada kirjautuu nyt omalle palvelimelleen omalla sovellusclientillaan ja näyttää täyttä dataa, vahvistettu oikealla kanadalaisella ID.4:llä ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Oletuksena vain luettava · ⚠️ komennot = MBB **alpha** | ✅ Täysi telemetria EU Data Act -portaalin kautta | Katso rehellinen huomautus alla ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ VW estää komennot | ✅ EU Data Act -portaali | OLA-käyttöoikeus peruttiin palvelinpäässä vuonna 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Kaksisuuntaisuus odottaa live-testiä | ✅ Kirjautuminen + luku | My Bentley, toimii Audi/IDK-tenantilla |
| **Porsche** | ⚠️ Kokeellinen | ⚠️ Kokeellinen | Porsche Connect, oma taustajärjestelmä. Porsche siirtyi *Porsche One* -sovellukseen, joten **kirjautumisen odotetaan epäonnistuvan nykyisillä tileillä**. Komentokoodi on olemassa mutta saavuttamattomissa, kunnes kirjautuminen on rakennettu uudelleen ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⚠️ Kokeellinen | ⚠️ Kokeellinen | Kirjautuminen on kytketty pohjoisamerikkalaiseen identiteetintarjoajaan, mutta sitä **ei ole vielä vahvistettu** oikealla USA/CA-tilillä. Testaajat tervetulleita ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Rehellinen huomautus VW EU:n hallinnasta.** Volkswagen EU -ajoneuvot ovat **oletuksena vain luku**: saat täyden telemetrian EU Data Act -portaalin kautta, mutta et etäkomentoja. Etäkomennot VW EU:lle ovat olemassa **vain kokeellisena pysyvän MBB:n kaksisuuntaisena ALFANA**, ja vain **vanhoille MQB / Car-Net** -autoille — se on valinnainen kytkin, **ei** oletusominaisuus. **MEB / ID-perheen autoilla (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) ei ole lainkaan komentopolkua** ja ne luodaan vain lukemista varten. MBB-alfaa seurataan issuessa **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testaajat tervetulleita.

> Vuonna 2026 Volkswagen laittoi osia API:staan laitetodennuksen taakse. Tämä integraatio kiertää sen missä mahdollista (pysyvä Car-Net-kirjautuminen, EU Data Act -portaali, vw.de-verkko) ja on läpinäkyvä siitä, mitä kukin kanava voi ja ei voi tehdä.

---

## Tunnetut rajoitukset

Muutamat asiat ovat **rakenteellisia** — ne johtuvat siitä, miten Volkswagenin taustajärjestelmät toimivat vuonna 2026, eivät integraatiosta, eikä mikään asetus korjaa niitä:

- **VW EU on oletuksena vain luku; komennot ovat MBB-alfa vain vanhoille autoille.** Katso merkin huomautus yllä. **MEB / ID-perheen autot ovat vain luku** — pysyvä Car-Net-komentopolku ei tunnista niitä (se vastaa "Unknown user"), eikä VW:n MEB-taustajärjestelmä tarjoa vastaavaa. Määritys havaitsee tämän ja luo **vain luku -kohteen** (korjausilmoituksen kera) epäonnistumisen sijaan, joten se on tunnettu rajoitus, ei hiljainen. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA / SEAT -etäkomennot on estetty VW:n toimesta.** Näiden merkkien verkkopalveluiden (OLA) pääsy peruttiin palvelinpuolella vuonna 2026 (HTTP 403); uudelleenkirjautuminen tai sovellusversion päivitys ei palauta sitä. Data kulkee edelleen EU Data Act -portaalin kautta. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **EU Data Act -portaalin data on ohutta ja vaihtelee autoittain.** VW julkaisee tänään vain siivun kentistä (usein matkamittari + lukitus + lataus, joskus paljon enemmän). Se laajenee ajan myötä, kun VW laajentaa portaalia ennen syyskuun 2026 määräaikaa — kentät, jotka lukevat tänään `unknown`, saattavat täyttyä itsestään, ilman muutosta. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Pohjois-Amerikka on enimmäkseen VW:tä; Audi on yhä kokeellinen.** **VW USA/CA toimii, Kanada mukaan lukien**, nyt vahvistettu oikealla kanadalaisella ID.4:llä: Kanada kirjautuu omalle palvelimelleen, ja datakuoren korjauksen jälkeen se näyttää täyttä telemetriaa ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi USA/CA** -kirjautuminen on kytketty, mutta sitä ei ole koskaan vahvistettu oikealla tilillä ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)), joten käsittele pohjoisamerikkalaista Audia kokeellisena.
- **Porsche-kirjautumisen odotetaan epäonnistuvan juuri nyt.** Porsche poisti käytöstä *My Porsche* -sovelluksen, jota vastaan tämä integraatio tunnistautuu, ja siirtyi *Porsche Oneen*. Luku ja komennot on toteutettu, mutta et todennäköisesti pääse kirjautumisen ohi ennen kuin se on rakennettu uudelleen. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-päivitykset (lähes reaaliaikaiset) ovat valinnainen BETA ja oletuksena pois päältä.** MQTT- (Škoda) ja Firebase-kanavat (Audi/VW, CUPRA/SEAT) on kytketty mutta ei validoitu tuotannossa, ja merkit suojaavat niitä yhä useammin sovellustodennuksella, jota ei voi täyttää laitteen ulkopuolella. Jätä ne pois päältä, ellet halua auttaa testaamisessa. Tavallinen kysely on tuettu tapa.

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

- **Selain / laitekoodi (salasanaton)** merkeille *Audi, Škoda, SEAT, CUPRA ja Audi USA/CA (kokeellinen)*. Kirjaudu puhelimella tai kannettavalla ja hyväksy laite; Home Assistantiin ei tallenneta salasanaa (se säilyttää aidon refresh-tunnisteen). Tämä vaihe tarjoaa myös valinnaisen **S-PIN**:n ja skannausvälin.
- **Portaali, sähköposti + salasana** merkeille *Volkswagen EU, Volkswagen USA/CA, Bentley ja Porsche (kokeellinen)*. Syötä merkkisi kirjautumistiedot. Tämä vaihe näyttää merkkivalitsimen, sähköpostin, salasanan, valinnaisen **S-PIN**:n, skannausvälin sekä kytkimen **"ota MBB-komennot käyttöön"** (joka vaikuttaa vain Volkswagen EU:hun, katso [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). **Volkswagen USA/Kanadalle** ilmestyy tähän **maavalitsin (USA vai CA)**; se näkyy **vain** tälle merkille eikä mikään muu käytä sitä.

> **EU Data Act -portaali ei ole kolmas kirjautumispainike.** Se on vain luettava strategia, johon koordinaattori automaattisesti palaa, ja sen voi lisäksi *lisätä* täydentäväksi lukukanavaksi kohdasta **Määritä → Asetukset**. Sama koskee `volkswagen.de`-verkkokanavaa (valinnainen beta, vain Asetusten kautta, vain luettava) ja valinnaista **Tibber**-kanavaa, joka täyttää kentät, jotka ensisijaiset kanavat jättivät tyhjiksi, eikä koskaan ylikirjoita tuoreempaa dataa.

### S-PIN-kenttä — milloin sitä tarvitset

**S-PIN** on merkkisi sovelluksen turva-PIN. Se on lomakkeessa valinnainen ja vaaditaan vain joihinkin toimintoihin: sitä tarvitaan **VW US/Kanadan datalukemiin ja komentoihin** sekä turvakriittisiin etäkomentoihin merkeillä, jotka rajaavat ne S-PIN:in taakse. Jätä se tyhjäksi, jos autosi ei sellaista kysy.

---

### Volkswagen EU — datan saaminen liikkeelle (tärkeää)

Volkswagen EU:lla **kirjautuminen ei riitä** — VW streamaa ajoneuvon dataa vasta, kun *sinä* olet kytkenyt datan jakamisen päälle VW:n puolella. Jos autosi ilmestyy ilman dataa (tai ei ilmesty lainkaan), tämä on lähes aina syy, **ei** väärä salasana. Tee tämä kerran:

1. **Lisää integraatio:** valitse **Portaali (sähköposti + salasana)** ja valitse **Volkswagen EU**, kirjaudu sitten sisään.
2. **Suorita mahdollinen kertaluonteinen kehote VW:n portaalissa.** Avaa VW:n dataportaali kerran selaimessa tai merkin sovelluksessa ja suorita loppuun, mitä se pyytää: **hyväksy ehdot, vahvista suostumus, viimeistele käyttöönotto / alueen valinta.** Selaimeton pääsy ei pääse näiden ohi — tämä on `portal_interaction_required`-tapaus ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Myönnä datan jakamisen suostumus.** Aseta portaalissa **"Ei-henkilökohtaisen datan käyttö" = Myönnetty** (EU Data Act -datan jakamisen suostumus).
4. **Älä etsi "jatkuvan datapyynnön" kytkintä — sellaista ei ole.** Integraatio luo kyseisen pyynnön jokaiselle autolle itse, ja se on **ilmainen**. Versiosta v2.29.0 alkaen pyyntö luodaan **ilman päättymispäivää**; aiemmat versiot pyysivät yhtä kuukautta, minkä vuoksi osa asennuksista hiljeni huomaamatta noin neljän viikon jälkeen. Jos datasi lakkasi tulemasta ja otit tilin käyttöön ennen versiota v2.29.0, poista tili integraatiosta ja lisää se kerran uudelleen, jotta luodaan tuore pyyntö. Ilman pyyntöä portaali ei palauta kyseiselle VIN:ille mitään ja auto ilmestyy ilman lukemia.
5. **Odota, että auto pushaa tilannekuvan.** Jopa kaiken yllä olevan jälkeen leviäminen vie aikaa. Auto voi lukea **`offline` / `unknown` jonkin aikaa — usein seuraavaan ajoon tai heräämiseen asti, jopa ~24 h** — ennen kuin anturit täyttyvät. Tämä on normaalia.

Portaali tarjoaa aluksi vain **siivun kentistä**, ja tämä siivu **laajenee ajan myötä**, kun VW laajentaa portaalin kattavuutta ennen syyskuun 2026 määräaikaa — kentät, jotka lukevat tänään `unknown`, saattavat täyttyä itsestään. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Täydellinen kenttäluettelo.** VW-konsernin täydellinen virallinen tietosanakirja (jokainen EU Data Act -avain -> kenttä, kuvaus ja yksikkö) on tiedostossa [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Viikoittainen workflow tarkkailee portaalin sanastosivua ja avaa pull requestin, kun VW julkaisee uudemman version, jottei taulukko vanhene huomaamatta.

> Asetuskytkin **`eu_data_act_auto_kickoff`** on se, joka luo tuon 15 minuutin mukautetun datapyynnön, ja se on **oletuksena päällä** — portaalitilassa ilman sitä ei tule dataa. Kytke se pois vain, jos haluat mieluummin hallita pyyntöä itse.

---

## Mitä saat

- **Anturit:** akun SoC, toimintamatka (sähkö / polttomoottori / kokonais), polttoainetaso, matkamittari, lämpötilat, latausteho, latausnopeus (aina km/h, muunnetaan jos autosi ilmoittaa mph) ja lataustyyppi, lataustavoite, matkatilastot & käyttöiän kertymät, huolto- & öljyhuoltovälit, ohjelmistoversio, yhteyden tila, viimeksi nähty ja muuta.
- **Binäärianturit:** ovet lukittu, ovet/ikkunat/tavaratila/konepelti/kattoluukku auki, pistoke kytketty, latautuu, OTA-päivitys saatavilla, valot, ajoneuvo verkossa, lähtöajastimet, hälytys.
- **Hallinta:** lukitus/avaus, ilmastoinnin käynnistys/pysäytys, latauksen käynnistys/pysäytys, ikkunanlämmitys, lähtöajastimet, tavoite-SoC:n / lämpötilan / suurimman latausvirran asetus, äänimerkki-ja-vilkutus (kesto valittavissa, samoin pelkät valot tai myös äänimerkki), herätys, päivitys, latausasemien haku *(saatavuus riippuu merkistä & mallista)*.
- **Laitepaikannin:** GPS-sijainti Home Assistant -karttaan. Kysely, joka palaa ilman koordinaatteja, säilyttää viimeksi tunnetun pysäköintipaikan sen sijaan että menettäisi sen.
- **Kuvat:** ajoneuvon renderöinnit, missä merkki niitä tarjoaa.
- **Asetukset:** tilikohtainen **kyselyvälin** liukusäädin minuutteina, jotta automaatio voi kysellä useammin ajon aikana ja hidastaa yöksi. Se on jokaisessa asennuksessa, myös vain luettavissa portaalimerkinnöissä.
- **12 kieltä:** entiteettien nimet on käännetty kokonaan englanniksi, saksaksi, ranskaksi, espanjaksi, italiaksi, hollanniksi, puolaksi, tšekiksi, ruotsiksi, tanskaksi, norjaksi ja suomeksi.

> 💡 **Energiapaneeli:** ladatun energian anturi on `total_increasing`, joten lisää se suoraan Home Assistantin **Energiapaneeliin**, tai kääri se `utility_meter`-apuriin päivittäisiä/kuukausittaisia ladatun energian summia varten. Käytä tähän kumulatiivista **ladattu energia (kWh)** -anturia — älä per-100 km hyötysuhdeantureita (ne ovat keskiarvoja, eivät mittareita).

### Palvelut

Integraatio toimittaa **30+ palvelukutsua** (`vag_connect.*`), monet niistä merkkikohtaisia — *saatavuus riippuu merkistä & mallista*. Niiden joukossa: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi polttomoottori), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` ja `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, ja `show_vag`-pääsiäismuna.

---

## evcc

[evcc](https://evcc.io) voi hakea auton lataustilan, toimintamatkan ja lataustilanteen suoraan Home Assistantista, jolloin aurinkoylijäämälataus suunnitellaan todellisen akun eikä arvauksen mukaan. Integraation sisällä ei pyöri mitään ylimääräistä: evcc lukee Home Assistantin omaa REST-rajapintaa. **Luku**polku toimii **kaikilla merkeillä**, myös vain luettavilla VW EU- ja portaaliautoilla. **Kirjoitus**polku (`chargeEnable`) toimii vain kaksisuuntaisella autolla (Audi tai Škoda, jolla on elävä komentokanava) ja vain kun evcc käsittelee itse autoa latauspisteenä. Aidon älykkään latausaseman kanssa evcc tarvitsee vain lukupolun.

Valmiit `evcc.yaml`-reseptit ja kertaluonteinen käyttöönotto ovat tiedostossa [docs/EVCC.md](docs/EVCC.md). Tämä liitin on **beta**.

---

## ABRP (A Better Routeplanner) -live-telemetria

Voit pushata autosi live-datan **[A Better Routeplanner](https://abetterrouteplanner.com/)**iin, jotta se suunnittelee reitin todellisen varaustilasi mukaan. Se on **valinnainen ja oletuksena pois päältä** — mitään ei lähde verkostasi ennen kuin kytket sen päälle ja lähetys tosiasiassa suoritetaan.

**1. Hanki kaksi kirjautumistietoa.**

- **`token`** (ajoneuvokohtainen) — avaa ABRP-sovellus → **Asetukset → autosi → Live Data → "Generic" / muu auto** ja kopioi sen näyttämä tunniste.
- **`api_key`** (kehittäjäavain) — tämä on **iternion** myöntämä kumppani-/kehittäjäavain, *ei* jotain, mitä sovellus antaa. Pyydä sellainen iterniolta (heidän kehittäjä-/API-avainpyyntölomakkeensa). **Emme tarkoituksella toimita avainta** — sellaisen kovakoodaaminen, joka ei ole meidän, olisi esiintymistä toisena ja upottaisi omistamattoman salaisuuden julkiseen repositorioon. Liitä oma.

**2. Ota se käyttöön.** Integraatio → **Määritä** → vieritä **ABRP**-osioon → rastita *Ota käyttöön ABRP-telemetrian lähetys* ja liitä molemmat arvot. Ne validoidaan parina (saat virheen, jos vain toinen on asetettu), tallennetaan peitettynä ja **niitä ei koskaan kirjoiteta lokiin**.

**3. Automatisoi lähetys.** Tuo mukana tuleva sinihahmo **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), valitse ajoneuvosi ja sen **ABRP data changed** -anturi, ja olet valmis. Sinihahmo lataa vain, kun on aidosti uusi tilannekuva (*ABRP data changed* -binäärianturi on idempotentti laukaisin — se nollautuu jokaisen onnistuneen lähetyksen jälkeen, joten samaa tilannekuvaa ei koskaan lähetetä kahdesti).

Voit myös kutsua palvelua **`vag_connect.abrp_send`** suoraan (kohdista laitteeseen tai VIN:iin; api_key/token tulevat asetuksista, ellet anna niitä suoraan kutsussa).

> 🔒 **Yksityisyys:** telemetria sisältää GPS:n. Se lähtee verkostasi vain, kun `abrp_send` suoritetaan (eli kun *sinä* laukaiset sen / otat sinihahmon käyttöön). Mitä lähetämme: akun varaustila, latauksen tila, GPS, kulkusuunta, energia + kapasiteetti, arvioitu toimintamatka, ympäristön + akun lämpötila, matkamittari. Mitä tarkoituksella **emme** lähetä: mitään, mitä emme voi mitata luotettavasti (nopeus, HV-paketin jännite/virta, kunnon tila) — jätetty pois pikemminkin kuin arvattu.

---

## Asetukset (Määritä)

Kohdasta **Asetukset → Laitteet ja palvelut → VW Group Connect → Määritä** voit säätää:
skannausväliä (saatavilla myös elävänä kyselyvälin liukusäätimenä), S-PIN:iä (sekä ajoneuvokohtaista S-PIN:iä, kun tilillä on useampi kuin yksi auto), käänteistä geokoodausta, **vain luku -tilaa**, pakota PPE-ilmastointi (Audi), push-kytkimet (MQTT/FCM/Audi-VW, kaikki valinnaista betaa ja oletuksena pois päältä), client-id-ohitus, **`eu_data_act_auto_kickoff`** (oletuksena päällä), piilota tyhjät entiteetit (oletuksena päällä), **ABRP** (käyttöönotto + api_key + käyttäjätunniste, validoitu parina), sekä täydentävien lukukanavien **lisääminen / poistaminen**: `volkswagen.de` (beta), EU Data Act -portaali, **Tibber** ja kokeellinen **kumppanipuhelin**-kanava.

---

## Tue tätä projektia ❤️

Tämä on yhden ihmisen projekti — eikä VW tee siitä helppoa: jokainen taustajärjestelmän muutos tarkoittaa päiviä käänteistä suunnittelua, jotta toimiva polku löytyy taas. Tuo sinnikkyys on se, mikä pitää sen elossa siellä, missä vakiintuneet projektit ovat luovuttaneet. Jos se on sinulle jotain arvoista, voit tukea jatkuvaa ylläpitoa **[GitHub Sponsorsin](https://github.com/sponsors/its-me-prash)** kautta. Kiitos! 🙏

---

## Osallistuminen

PR:t tervetulleita, katso [`CONTRIBUTING.md`](CONTRIBUTING.md). Yleisimpiin kysymyksiin vastataan tiedostossa [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** muuttaa tuntemattomat API-kentät yhden napsautuksen, valmiiksi täytetyksi virheraportiksi, joten voit auttaa parantamaan kattavuutta lukematta koodia.

## Lisenssi

[GNU AGPL v3.0-or-later](LICENSE) integraatiokoodille. Pakollinen attribuutio + nimi-/tavaramerkkiehdot käytössä/forkissa: katso [`ATTRIBUTION.md`](ATTRIBUTION.md). Ylävirran avoimen lähdekoodin attribuutiot tiedostossa [`NOTICE.md`](NOTICE.md).
