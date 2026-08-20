<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Jedna integrace pro Home Assistant pro vozy koncernu Volkswagen: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW a Audi USA/Kanada</strong><br>
  <em>Baterie, nabíjení, dojezd, dveře, klimatizace a GPS poloha v Home Assistantu. Přímý přístup k API, několik čtecích kanálů s automatickým přepnutím, bez mezivrstvy.</em>
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

> ### 📛 Poznámka k přejmenování
> Dříve publikováno jako **`vag-connect-ha`** (VAG = Volkswagen AG, běžná zkratka v regionu DACH).
> Ukázalo se, že tahle zkratka zní v angličtině *poněkud* jinak 😅
>
> **Co funguje dál jako dřív**: všechny entity (např. `sensor.audi_q4_battery_soc`),
> všechna volání služeb (`vag_connect.lock`, `vag_connect.show_vag` atd.), všechny automatizace,
> instalace přes HACS — **nic se nerozbije**. Mění se jen marketingový/zobrazovaný název, vnitřní
> kód zůstává beze změny. Viz [`MIGRATION.md`](MIGRATION.md).
>
> Obrovský dík komunitám **Home Assistant UK** a **HA Ideas, Projects and Solutions**
> za upozornění — zejména **Si Gregory**, **Ben Johnson** a **Evets David**.
>
> A zvláštní pozdrav pro **Jordan Waeles**, jehož komentář `show_vag()` je teď oficiálně
> podporovaný easter egg v této integraci (služba `vag_connect.show_vag`, viz CHANGELOG v2.2.3).

---

## Co to je?

**VW Group Connect je integrace pro [Home Assistant](https://www.home-assistant.io), která přinese vaše auto z koncernu Volkswagen do chytré domácnosti: stav baterie a nabíjení, dojezd, tachometr, klimatizaci, dveře a okna, GPS polohu a další, pro značky Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley a severoamerické účty VW / Audi, to vše z jediné položky konfigurace.**

Tam, kde to backend značky ještě dovolí, posílá i vzdálené příkazy jako zamknout/odemknout, ovládání klimatizace a nabíjení. **To se liší podle značky, není to univerzální:** Audi a Škoda jsou obousměrné, Volkswagen EU přes portál EU Data Act je jen pro čtení a příkazy pro SEAT/CUPRA blokuje výrobce. Tabulka níže říká přesně, co kde platí.

Aby fungovala i po změnách API Volkswagenu v roce 2026, mluví **několika čtecími kanály a automaticky přepíná**, když je jeden zablokovaný: nativní backendy značek, portál dat vozidla **EU Data Act** (jen pro čtení), volitelný webový kanál `volkswagen.de` (beta), volitelné doplnění mezer přes **Tibber** a trvalé **bezheslové** přihlášení pro starší vozy Car-Net. Běží bez problémů **vedle [evcc](https://evcc.io)** (viz [docs/EVCC.md](docs/EVCC.md)) a nepotřebuje **žádný add-on, broker ani mezikontejner**. Home Assistant pro ni automaticky nainstaluje dva malé balíčky Pythonu; používají je pouze volitelné push kanály.

> 🎉 **Nyní dostupné přímo v HACS** — žádné vlastní úložiště není potřeba.

---

## Hlavní přednosti

- **9 volitelných značek koncernu Volkswagen** v jedné integraci: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Kanada, Audi USA/Kanada, Porsche a Bentley.
- **Obousměrné ovládání tam, kde to backend značky dovolí**: zamknout/odemknout, klimatizace, nabíjení, cílové SoC. Liší se to **podle značky, není to univerzální**. Než na nějaký příkaz vsadíte, mrkněte do tabulky níže.
- **Palubní asistentka Škody „Laura" v Home Assistantu (novinka ve 3.0.0)**: ptejte se na dojezd, nabíjení a jízdy jako na službu, nebo ji předejte libovolnému konverzačnímu agentovi (vestavěný Assist, OpenAI, Anthropic, Google, Ollama) jako nástroj, který může volat a řetězit. Rady jen pro čtení, na které mohou vaše automatizace reagovat.
- **Bezheslové přihlášení** (prohlížeč/device-code) pro Audi, Škodu, SEAT, CUPRA a Audi USA/CA. V Home Assistantu se neukládá žádné heslo.
- **Více kanálů s automatickým přepnutím**: nativní backend značky, portál EU Data Act, volitelný web vw.de, volitelný Tibber, trvalý Car-Net. Když jeden kanál vypadne, vaše data nezhasnou.
- **Doprovodný kanál (experimentální, volitelný)**: když jsou všechny backendové cesty zavřené, integrace dokáže vaše auto přečíst tak, že přes ADB ovládá oficiální aplikaci na náhradním telefonu s Androidem. Volkswagen je ověřený proti skutečnému zařízení, ostatní značky zůstávají jen pro čtení, dokud se nepotvrdí mapa obrazovek. Novější telefony potřebují [add-on ADB Bridge](https://github.com/its-me-prash/vwgroup-app-adb-bridge); nic se nerootuje a nečtou se žádné tokeny aplikace.
- **Odolná už z návrhu**: podrží poslední známé hodnoty i poslední známou parkovací polohu přes výpadky portálu, odfiltruje falešné hlídače „žádné měření", nikdy nenechá tachometr skočit zpět a řekne vám, když je neúspěšné přihlášení výpadek u výrobce, a ne vaše heslo.
- **Frekvenci dotazování řídíte vy**: posuvník **intervalu dotazování** na účet (entita Number, v minutách), který mohou řídit automatizace, vytvořený u každé instalace včetně těch portálových jen pro čtení.
- **GPS sledovač polohy**, přes 100 entit napříč několika platformami, přes 30 volání služeb, více vozidel na účet, názvy entit ve **12 jazycích**.
- **Porsche jede na vlastním backendu**, ne na portálu EU Data Act. Portálová cesta Porsche strukturálně *vylučuje*, takže nástroje postavené jen na portálu ho nikdy nepokryjí. Kód příkazů je tady, ale samotné přihlášení k Porsche je momentálně experimentální (viz tabulka).
- **Vehicle Data Scout** automaticky odhalí drift API a nabídne hlášení chyby na jedno kliknutí — a od verze 3.0.0 nese jeho stažení anonymizované diagnostiky i syrové odpovědi API, takže jedna příloha obsahuje vše potřebné k přidání podpory nového pole. **Quality Scale: Platinum.**

---

## Stav značek

| Značka | Ovládání | Data | Poznámky |
|---|---|---|---|
| **Audi** (EU) | ✅ Obousměrné | ✅ Plné | backend myAudi (vč. startu/vypnutí spalovacího motoru) |
| **Škoda** | ✅ Obousměrné | ✅ Plné | nativní backend Škody |
| **VW USA/CA** | ✅ Obousměrné | ✅ Plné | cloud VW NA (vyžaduje volbu země USA/CA + S-PIN). Kanada se teď přihlašuje na vlastním serveru s vlastním aplikačním klientem a zobrazuje plná data, potvrzeno na skutečném kanadském ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Ve výchozím stavu jen pro čtení · ⚠️ příkazy = MBB **alpha** | ✅ Plná telemetrie přes portál EU Data Act | Viz upřímná poznámka níže ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Příkazy blokuje VW | ✅ Portál EU Data Act | Přístup OLA v roce 2026 odebrán na straně serveru ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Obousměrné čeká na test naživo | ✅ Přihlášení + čtení | My Bentley, běží na tenantu Audi/IDK |
| **Porsche** | ⚠️ Experimentální | ⚠️ Experimentální | Porsche Connect, vlastní backend. Porsche přešlo na aplikaci *Porsche One*, takže **přihlášení na současných účtech nejspíš selže**. Kód příkazů tu je, ale je nedosažitelný, dokud se přihlášení nepostaví znovu ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⏳ Obousměrné čeká na test naživo | ✅ Plné | backend myAudi NA. USA teď čte z regionální vozidlové služby `na` a je **potvrzeno, že funguje na skutečném US Audi Q5** (58 entit) — díky @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada používá službu EMEA. Příkazy dědí obousměrné cesty Audi, ale na NA zatím nejsou samostatně potvrzené naživo ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Upřímná poznámka k ovládání VW EU.** Vozy Volkswagen EU jsou **ve výchozím stavu jen pro čtení**: dostanete plnou telemetrii přes portál EU Data Act, ale žádné vzdálené příkazy. Vzdálené příkazy pro VW EU existují **pouze jako experimentální obousměrná ALPHA přes trvalý MBB**, a to jen pro **starší vozy MQB / Car-Net** — je to volitelný přepínač, **ne** výchozí funkce. **Vozy řady MEB / ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) nemají žádnou cestu pro příkazy** a jsou vytvořeny jen pro čtení. MBB alpha je sledována v **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testeři vítáni.

> V roce 2026 Volkswagen zabezpečil části svého API attestací zařízení. Tato integrace ji obchází tam, kde je to možné (trvalé přihlášení Car-Net, portál EU Data Act, web vw.de) a je transparentní v tom, co každý kanál umí a neumí.

---

## Známá omezení

Pár věcí je **strukturálních** — vyplývají z toho, jak fungují backendy Volkswagenu v roce 2026, ne z integrace, a žádné nastavení je neopraví:

- **VW EU je ve výchozím stavu jen pro čtení; příkazy jsou MBB alpha jen pro starší vozy.** Viz poznámka ke značce výše. **Vozy řady MEB / ID jsou jen pro čtení** — cesta příkazů přes trvalý Car-Net je nerozpozná (odpovídá „Unknown user") a MEB backend Volkswagenu žádnou ekvivalentní cestu nevystavuje. Nastavení to rozpozná a místo selhání vytvoří **záznam jen pro čtení** (s opravným upozorněním), takže jde o známé omezení, ne o tiché. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Vzdálené příkazy CUPRA / SEAT jsou blokované VW.** Přístup k online službám (OLA) pro tyto značky byl v roce 2026 zrušen na straně serveru (HTTP 403); opětovné přihlášení ani aktualizace verze aplikace ho neobnoví. Data stále tečou přes portál EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Data z portálu EU Data Act jsou skoupá a liší se vozidlo od vozidla.** VW dnes publikuje jen výsek polí (často tachometr + zamčení + nabíjení, někdy mnohem víc). Postupně se to rozšiřuje, jak VW rozšiřuje portál před zářijovým termínem 2026 — pole, která dnes čtou `unknown`, se mohou sama vyplnit, bez jakékoliv změny. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Severní Amerika: VW i Audi teď obojí čtou — příkazy Audi jsou poslední nepotvrzený kousek.** **VW USA/CA funguje, včetně Kanady**, potvrzeno na skutečném kanadském ID.4: Kanada se přihlašuje na vlastním serveru a od opravy datové obálky zobrazuje plnou telemetrii ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi USA/CA teď také čte**: USA čte z regionální vozidlové služby `na`, potvrzeno na skutečném US Audi Q5 (díky @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada používá službu EMEA. Příkazy dědí obousměrné cesty Audi, ale na severoamerických účtech zatím nejsou samostatně potvrzené naživo ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Přihlášení k Porsche teď nejspíš selže.** Porsche vyřadilo aplikaci *My Porsche*, vůči které se tahle integrace ověřuje, ve prospěch *Porsche One*. Čtení i příkazy jsou naprogramované, ale přes přihlášení se nejspíš nedostanete, dokud se nepostaví znovu. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push aktualizace (téměř v reálném čase) jsou volitelná BETA a ve výchozím stavu vypnuté.** Kanály MQTT (Škoda) a Firebase (Audi/VW, CUPRA/SEAT) jsou zapojené, ale neověřené naživo, a značky je čím dál víc zamykají za atestaci aplikace, kterou mimo zařízení nelze splnit. Nechte je vypnuté, pokud nechcete pomoct s testováním. Běžné dotazování je podporovaná cesta.

> **Jak to vidíme my.** Podle EU Data Act (Regulation (EU) 2023/2854) jsou data vašeho auta *vaše*. Provozovat tuto integraci na vlastním hardwaru znamená, že *vy* přistupujete ke *svým vlastním* datům (Článek 4) — a náleží vám ve stejné kvalitě, v jaké je výrobce poskytuje sám sobě, v reálném čase tam, kde je to technicky proveditelné. Portál VW, dnes jen pro čtení a zpožděný o hodiny, tomu zatím nestačí. Tato integrace je záměrně **nezávislá na kanálu**: v okamžiku, kdy VW dá majitelům skutečné rozhraní v reálném čase, schopné ovládání — jak Data Act vyžaduje a jak někteří výrobci svým majitelům už nabízejí — podpoříme ho i tady, zdarma, pro všechny. Stojíme za vaším právem na přístup k datům vlastního auta v reálném čase.

---

## Instalace

**Přes HACS (doporučeno):**

1. Otevřete **HACS** v Home Assistant.
2. Vyhledejte **„VW Group Connect"** a nainstalujte ji.
3. Restartujte Home Assistant.
4. Přejděte na **Nastavení → Zařízení a služby → Přidat integraci → VW Group Connect** a projděte přihlašovacím procesem.

<sup>Právě sloučeno do výchozího HACS — pokud zatím není vyhledatelná, dejte indexu HACS chvíli na obnovení, nebo mezitím přidejte `its-me-prash/vwgroup-connect-ha` jako vlastní úložiště.</sup>

**Minimální Home Assistant: `2024.4.0`.**

### Možnosti přihlášení (průvodce nastavením má dvě cesty)

První obrazovka integrace nabízí **dvě** metody přihlášení. Vyberte tu, kterou vaše značka podporuje:

- **Prohlížeč / device-code (bezheslové)** pro *Audi, Škodu, SEAT, CUPRA a Audi USA/CA*. Přihlaste se na telefonu nebo notebooku a schvalte zařízení; v Home Assistantu se neukládá žádné heslo (drží skutečný refresh token). Tento krok navíc nabízí volitelný **S-PIN** a interval skenování.
- **Portál, e-mail + heslo** pro *Volkswagen EU, Volkswagen USA/CA, Bentley a Porsche (experimentálně)*. Zadejte přihlašovací údaje své značky. Tento krok ukáže výběr značky, e-mail, heslo, volitelný **S-PIN**, interval skenování a přepínač **„povolit příkazy MBB"** (který má vliv jen u Volkswagenu EU, viz [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Pro **Volkswagen USA/Kanada** se tu objeví **volba země (USA nebo CA)**; zobrazuje se **pouze** u této značky a žádná jiná ji nepoužívá.

> **Portál EU Data Act není třetí přihlašovací tlačítko.** Je to strategie jen pro čtení, na kterou koordinátor automaticky přepíná, a lze ji navíc *přidat* jako doplňkový čtecí kanál přes **Konfigurovat → Možnosti**. Totéž platí pro webový kanál `volkswagen.de` (volitelná beta, jen přes Možnosti, jen pro čtení) a pro volitelný kanál **Tibber**, který doplňuje pole, jež první kanály nechaly prázdná, a nikdy nepřepíše čerstvější data.

### Pole S-PIN — kdy ho potřebujete

**S-PIN** je bezpečnostní PIN aplikace vaší značky. Ve formuláři je volitelný a vyžaduje se jen pro některé akce: je potřeba pro **čtení dat a příkazy VW US/Kanada** a pro bezpečnostně citlivé vzdálené příkazy u značek, které je za S-PIN zamykají. Pokud ho vaše auto nevyžaduje, nechte ho prázdný.

---

### Volkswagen EU — jak rozproudit svá data (důležité)

U Volkswagen EU **samotné přihlášení nestačí** — VW začne streamovat vozidlová data teprve poté, co *vy* na straně VW zapnete sdílení dat. Pokud se vaše auto objeví bez dat (nebo se neobjeví vůbec), je to téměř vždy z tohoto důvodu, **ne** kvůli špatnému heslu. Jednou proveďte následující:

1. **Přidejte integraci:** zvolte **Portál (e-mail + heslo)** a vyberte **Volkswagen EU**, pak se přihlaste.
2. **Dokončete jakoukoliv jednorázovou výzvu na portálu VW.** Otevřete datový portál VW jednou v prohlížeči nebo v aplikaci značky a dokončete vše, co po vás chce: **přijměte podmínky, potvrďte souhlas, dokončete onboarding / výběr regionu.** Bezobslužný přístup přes tyto kroky neprojde — jde o případ `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Udělte souhlas se sdílením dat.** Na portálu nastavte **„Use of non-personal data" = Granted** (souhlas se sdílením dat dle EU Data Act).
4. **Nehledejte přepínač „průběžný požadavek na data" — žádný tam není.** Integrace si tento požadavek pro každé auto vytvoří sama a je **zdarma**. Od verze v2.29.0 se požadavek vytváří **bez data vypršení**; starší verze žádaly o jeden měsíc, a proto některé instalace po zhruba čtyřech týdnech tiše ztichly. Pokud vám data přestala chodit a účet jste zakládali před v2.29.0, odeberte účet z integrace a jednou ho přidejte znovu, aby se vytvořil nový požadavek. Bez požadavku portál pro dané VIN nevrátí nic a vozidlo se objeví bez údajů.
5. **Počkejte, až auto odešle snímek.** I po všem výše uvedeném trvá propagace nějakou dobu. Auto může **chvíli číst `offline` / `unknown` — často až do další jízdy nebo probuzení, klidně ~24 h** — než se senzory naplní. To je normální.

Portál zpočátku poskytuje jen **výsek polí** a tento výsek se **postupně rozšiřuje**, jak VW rozšiřuje pokrytí portálu před zářijovým termínem 2026 — pole, která dnes čtou `unknown`, se mohou sama vyplnit. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Úplný seznam polí.** Kompletní oficiální datový slovník skupiny VW (každý klíč EU Data Act -> pole, popis a jednotka) najdete v [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Týdenní workflow sleduje stránku se slovníkem na portálu a otevře pull request, jakmile VW zveřejní novější verzi, aby tabulka tiše nezastarala.

> Ten 15minutový Custom Data Request vytváří přepínač v Možnostech **`eu_data_act_auto_kickoff`** a je **ve výchozím stavu zapnutý** — v režimu portálu bez něj žádná data nejsou. Vypněte ho jen tehdy, pokud si chcete požadavek spravovat sami.

---

## Co dostanete

- **Senzory:** SoC baterie, dojezd (elektrický / spalovací / celkový), úroveň paliva, tachometr, teploty, nabíjecí výkon, rychlost nabíjení (vždy v km/h, přepočteno pokud vaše auto hlásí v mph) a typ nabíjení, cíl nabíjení, historie jednotlivých nabíjecích relací (energie / trvání / začátek / AC/DC) u Škody a SEAT/CUPRA, statistiky jízd a celoživotní souhrny, intervaly servisu a výměny oleje, verze softwaru, stav připojení, naposledy viděno a — u Škody — poslední tankování, aktuální relace placeného parkování, servisní připomínky, časovače odjezdu a preferovaný režim nabíjení a další.
- **Binární senzory:** zamčené dveře, otevřené dveře/okna/kufr/kapota/střešní okno, připojený konektor, nabíjení, dostupná OTA aktualizace, světla, vozidlo online, časovače odjezdu, alarm.
- **Ovládání:** zamknutí/odemknutí, start/stop klimatizace, start/stop nabíjení, vyhřívání oken, časovače odjezdu, nastavení cílového SoC / teploty / max. nabíjecího proudu, troubení a blikání (s volbou délky trvání a možností jen světla, nebo i klakson), probuzení, obnovení, vyhledání nabíjecích stanic, režim kempování a aktivní větrání (větrání kabiny Škoda bez topení) *(dostupnost závisí na značce a modelu)*.
- **Sledovač polohy:** GPS poloha pro mapu Home Assistant. Dotaz, který se vrátí bez souřadnic, podrží poslední známou parkovací polohu místo toho, aby ji ztratil.
- **Obrázky:** vykreslení vozidla tam, kde je značka poskytuje.
- **Nastavení:** posuvník **intervalu dotazování** na účet, v minutách, aby automatizace mohla během jízdy dotazovat častěji a v noci polevit. Je v každé instalaci, i u portálových položek jen pro čtení.
- **12 jazyků:** názvy entit jsou plně přeložené do angličtiny, němčiny, francouzštiny, španělštiny, italštiny, nizozemštiny, polštiny, češtiny, švédštiny, dánštiny, norštiny a finštiny.

> 💡 **Energetický panel:** senzor nabité energie je `total_increasing`, takže ho přidejte přímo do **energetického panelu** Home Assistant, nebo ho zabalte do pomocníka `utility_meter` pro denní/měsíční souhrny nabité energie. Pro tento účel použijte kumulativní senzor **nabité energie (kWh)** — ne senzory účinnosti na 100 km (ty jsou průměry, ne měřiči).

### Služby

Integrace přináší **30+ volání služeb** (`vag_connect.*`), z nichž mnohá jsou specifická pro značku — *dostupnost závisí na značce a modelu*. Mezi nimi: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi se spalovacím motorem), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (přídavné / nezávislé topení — SEAT/CUPRA, Škoda a VW/Audi přes obousměrný příkazový kanál, pokud je jím auto vybaveno), `send_destination` (SEAT/CUPRA/Škoda) a `update_charging_settings` (SEAT/CUPRA), `ask_assistant` pro Škodu (viz níže), `set_location_target_soc` a `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send` a easter egg `show_vag`.

---

## evcc

[evcc](https://evcc.io) si může stav nabití, dojezd a stav nabíjení vašeho auta brát rovnou z Home Assistantu, takže nabíjení z přebytků plánuje podle skutečné baterie, a ne podle odhadu. Uvnitř integrace kvůli tomu neběží nic navíc: evcc čte REST API Home Assistantu. Cesta pro **čtení** funguje u **všech značek**, i u vozů VW EU / portálových jen pro čtení. Cesta pro **zápis** (`chargeEnable`) funguje jen u obousměrného auta (Audi nebo Škoda s živým příkazovým kanálem) a jen tehdy, když evcc bere jako nabíječku samotné auto. U opravdové chytré wallboxu si evcc vystačí s čtecí cestou.

Hotové recepty pro `evcc.yaml` i jednorázové nastavení najdete v [docs/EVCC.md](docs/EVCC.md). Tenhle konektor je **beta**.

---

## ABRP (A Better Routeplanner) živá telemetrie

Živá data svého auta můžete posílat do **[A Better Routeplanner](https://abetterrouteplanner.com/)**, aby plánoval podle vašeho skutečného stavu nabití. Je to **volitelné a ve výchozím stavu vypnuté** — z vaší sítě nic neodejde, dokud to nezapnete a dokud se skutečně nespustí nahrání.

**1. Získejte dva přihlašovací údaje.**

- **`token`** (na vozidlo) — otevřete aplikaci ABRP → **Settings → vaše auto → Live Data → „Generic" / jiné auto** a zkopírujte token, který zobrazí.
- **`api_key`** (vývojářský klíč) — jde o partnerský/vývojářský klíč vydaný **iternio**, *ne* o něco, co vydá aplikace. Vyžádejte si ho od iternio (jejich formulář pro žádost o vývojářský/API klíč). **Záměrně žádný klíč nedodáváme** — natvrdo zadrátovat klíč, který nevlastníme, by bylo vydávání se za někoho jiného a zapeklo by nevlastněné tajemství do veřejného repozitáře. Vložte svůj vlastní.

**2. Zapněte to.** Integrace → **Konfigurovat** → přejděte na sekci **ABRP** → zaškrtněte *Enable ABRP telemetry push* a vložte obě hodnoty. Validují se jako pár (pokud nastavíte jen jednu, dostanete chybu), ukládají se maskovaně a **nikdy se nezapisují do logu**.

**3. Zautomatizujte nahrávání.** Naimportujte dodávaný blueprint **„ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), vyberte své vozidlo a jeho senzor **ABRP data changed**, a hotovo. Blueprint nahrává jen tehdy, když je k dispozici skutečně nový snímek (binární senzor *ABRP data changed* je idempotentní spouštěč — po každém úspěšném odeslání se resetuje, takže se stejný snímek nikdy neodešle dvakrát).

Můžete také volat službu **`vag_connect.abrp_send`** přímo (cíleně na zařízení nebo VIN; api_key/token se berou z možností, pokud je nepředáte inline).

> 🔒 **Soukromí:** telemetrie zahrnuje GPS. Z vaší sítě odejde jen tehdy, když se spustí `abrp_send` (tj. když ho *vy* spustíte / zapnete blueprint). Co posíláme: stav nabití, stav nabíjení, GPS, kurz, energii + kapacitu, odhadovaný dojezd, okolní + teplotu baterie, tachometr. Co záměrně **neposíláme**: cokoliv, co nedokážeme spolehlivě změřit (rychlost, napětí/proud HV baterie, stav opotřebení) — raději vynecháno než odhadnuto.

---

## Asistent AI Škoda („Laura") — novinka ve 3.0.0

Vlastní palubní asistentka MyŠkoda, **Laura**, je dostupná přímo v Home Assistantu.
Ptejte se jí na dojezd, nabíjení a jízdy pomocí služby `vag_connect.ask_assistant`
(vrátí textovou odpověď, kterou můžete zobrazit v notifikaci, přečíst nahlas nebo
podle ní větvit), nebo ji předejte **konverzačnímu agentovi** — vestavěnému Assistu
v režimu LLM, nebo OpenAI / Anthropic / Google / Ollama — jako nástroj, který může
volat a řetězit (zeptat se Laury → pak poslat `send_destination` do auta). Je
**jen pro čtení, poradní a pouze pro Škodu**; jde o **betu**, takže zpětná vazba
ke kvalitě odpovědí je vítána.

Nastavení, hlasový spouštěč („ask Laura …") a hotové ukázkové automatizace —
včetně *auto přijede domů → dobít + předehřát + přečíst dojezd* — najdete v
**[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Možnosti (Konfigurovat)

Z **Nastavení → Zařízení a služby → VW Group Connect → Konfigurovat** můžete upravit:
interval skenování (dostupný i živě jako posuvník intervalu dotazování), S-PIN (a k tomu S-PIN pro jednotlivá vozidla, pokud je na účtu víc než jedno auto), zpětné geokódování, **režim jen pro čtení**, vynucenou klimatizaci PPE (Audi), přepínače push (MQTT/FCM/Audi-VW, všechny volitelné, v betě a ve výchozím stavu vypnuté), přepsání client-id, **`eu_data_act_auto_kickoff`** (výchozí zapnuto), skrytí prázdných entit (výchozí zapnuto), **ABRP** (zapnutí + api_key + uživatelský token, validováno jako pár), plus **přidání / odebrání** doplňkových čtecích kanálů: `volkswagen.de` (beta), portál EU Data Act, **Tibber** a experimentální kanál **doprovodného telefonu**.

---

## Podpořte tento projekt ❤️

Je to projekt jednoho člověka — a VW to neusnadňuje: každá změna backendu znamená dny reverzního inženýrství, než se najde fungující cesta. Právě tahle vytrvalost ho udržuje naživu tam, kde to zavedené projekty vzdaly. Pokud pro vás má hodnotu, můžete podpořit pokračující údržbu přes **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Děkuji! 🙏

---

## Přispívání

PR jsou vítány, viz [`CONTRIBUTING.md`](CONTRIBUTING.md). Časté dotazy jsou zodpovězené v [docs/FAQ.md](docs/FAQ.md). **Vehicle Data Scout** promění neznámá pole API v předvyplněné hlášení chyby na jedno kliknutí, takže můžete pomoci zlepšit pokrytí, aniž byste četli kód.

## Licence

[GNU AGPL v3.0-or-later](LICENSE) pro kód integrace. Povinné uvedení autorství + podmínky k názvu/ochranné známce při použití/forku: viz [`ATTRIBUTION.md`](ATTRIBUTION.md). Uvedení autorství upstreamového open-source v [`NOTICE.md`](NOTICE.md).
