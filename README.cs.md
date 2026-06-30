<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Jedna integrace pro Home Assistant napříč značkami koncernu Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Kanada · Bentley</strong><br>
  <em>Přímý přístup k API, více kanálů s automatickým záložním přepnutím, žádný middleware.</em>
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
> A zvláštní pozdrav patří **Jordanu Waelesovi**, jehož komentář `show_vag()` je teď oficiálně
> podporovaný easter egg v této integraci (služba `vag_connect.show_vag`, viz CHANGELOG v2.2.3).

---

## Co to je?

**VW Group Connect je integrace pro [Home Assistant](https://www.home-assistant.io), která přivádí data a ovládání propojeného vozu do vaší chytré domácnosti pro značky koncernu Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Kanada a Bentley — z jediného konfiguračního záznamu.**

Zpřístupňuje stav baterie a nabíjení, dojezd, stav tachometru, klimatizaci, dveře a okna, polohu a další — a tam, kde to backend dané značky stále umožňuje, posílá vzdálené příkazy jako zamknutí/odemknutí, ovládání klimatizace a nabíjení. Aby fungovala i přes změny API Volkswagenu v roce 2026, komunikuje přes **několik kanálů a automaticky se přepíná na záložní**, když je jeden zablokovaný: nativní backendy značek, portál vozidlových dat **EU Data Act** určený jen pro čtení, volitelný webový kanál `volkswagen.de` a trvalé **bezheslové** přihlášení pro starší vozy Car-Net. Běží spokojeně **vedle [evcc](https://evcc.io)** a nepotřebuje **žádné závislosti z PyPI**.

> 🎉 **Nyní dostupné přímo v HACS** — žádné vlastní úložiště není potřeba.

---

## Hlavní přednosti

- **8 volitelných značek koncernu Volkswagen** v jedné integraci — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Kanada, Porsche a Bentley.
- **Podpora Porsche** — Porsche jede přes vlastní backend *Porsche Connect*, **ne** přes portál EU Data Act. Cesta přes portál Porsche strukturálně *vylučuje*, takže nástroje pracující jen s portálem ho nikdy nepokryjí; tato integrace ano.
- **Obousměrné ovládání tam, kde to backend značky dovolí** — zamknutí/odemknutí, klimatizace, nabíjení, cílový SoC. Které značky mají skutečnou podporu příkazů, najdete v tabulce níže; VW EU je ve výchozím stavu jen pro čtení (viz upřímná poznámka tam).
- **Volitelné bezheslové přihlášení** (prohlížeč / device-code) pro Audi/Škoda/SEAT/CUPRA — v Home Assistant se neukládá žádné heslo.
- **Více kanálů s automatickým záložním přepnutím** — nativní backend značky → portál EU Data Act → volitelný web vw.de → trvalý Car-Net. Výpadek jednoho kanálu nezpůsobí, že vám zhasnou data.
- **Odolnost už od návrhu** — uchovává poslední známé hodnoty během výpadků portálu, filtruje falešné zástupné hodnoty „bez údaje" a nikdy nedovolí tachometru skočit zpět.
- **GPS sledovač polohy**, 100+ entit napříč více platformami, 20+ volání služeb, více vozidel na účet.
- **Vehicle Data Scout** — automaticky rozpozná posun v API a nabídne hlášení chyby na jedno kliknutí. **Quality Scale: Platinum.**

---

## Stav značek

| Značka | Ovládání | Data | Poznámky |
|---|---|---|---|
| **Audi** | ✅ Obousměrné | ✅ Plné | backend myAudi (vč. start/stop spalovacího motoru) |
| **Škoda** | ✅ Obousměrné | ✅ Plné | nativní backend Škoda |
| **Porsche** | ✅ Obousměrné | ✅ Plné | Porsche Connect — vlastní backend, ne portál EU Data Act |
| **VW US/CA** | ✅ Obousměrné | ✅ Plné | cloud VW NA (vyžaduje volič země US/CA + S-PIN) |
| **VW EU** | 🔒 Ve výchozím stavu jen pro čtení · ⚠️ příkazy = MBB **alpha** | ✅ Plná telemetrie přes portál EU Data Act | Viz upřímná poznámka níže — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Příkazy blokované VW | ✅ Portál EU Data Act | Přístup OLA zrušen na straně serveru v roce 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Obousměrné, čeká na živý test | ✅ Přihlášení + čtení | My Bentley — běží na tenantu Audi/IDK |

> **Upřímná poznámka k ovládání VW EU.** Vozy Volkswagen EU jsou **ve výchozím stavu jen pro čtení**: dostanete plnou telemetrii přes portál EU Data Act, ale žádné vzdálené příkazy. Vzdálené příkazy pro VW EU existují **pouze jako experimentální obousměrná ALPHA přes trvalý MBB**, a to jen pro **starší vozy MQB / Car-Net** — je to volitelný přepínač, **ne** výchozí funkce. **Vozy řady MEB / ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) nemají žádnou cestu pro příkazy** a jsou vytvořeny jen pro čtení. MBB alpha je sledována v **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — testeři vítáni.

> V roce 2026 Volkswagen zabezpečil části svého API attestací zařízení. Tato integrace ji obchází tam, kde je to možné (trvalé přihlášení Car-Net, portál EU Data Act, web vw.de) a je transparentní v tom, co každý kanál umí a neumí.

---

## Známá omezení

Pár věcí je **strukturálních** — vyplývají z toho, jak fungují backendy Volkswagenu v roce 2026, ne z integrace, a žádné nastavení je neopraví:

- **VW EU je ve výchozím stavu jen pro čtení; příkazy jsou MBB alpha jen pro starší vozy.** Viz poznámka ke značce výše. **Vozy řady MEB / ID jsou jen pro čtení** — cesta příkazů přes trvalý Car-Net je nerozpozná (odpovídá „Unknown user") a MEB backend Volkswagenu žádnou ekvivalentní cestu nevystavuje. Nastavení to rozpozná a místo selhání vytvoří **záznam jen pro čtení** (s opravným upozorněním), takže jde o známé omezení, ne o tiché. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Vzdálené příkazy CUPRA / SEAT jsou blokované VW.** Přístup k online službám (OLA) pro tyto značky byl v roce 2026 zrušen na straně serveru (HTTP 403); opětovné přihlášení ani aktualizace verze aplikace ho neobnoví. Data stále tečou přes portál EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Data z portálu EU Data Act jsou skoupá a liší se vozidlo od vozidla.** VW dnes publikuje jen výsek polí (často tachometr + zamčení + nabíjení, někdy mnohem víc). Postupně se to rozšiřuje, jak VW rozšiřuje portál před zářijovým termínem 2026 — pole, která dnes čtou `unknown`, se mohou sama vyplnit, bez jakékoliv změny. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

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

- **Prohlížeč / device-code (bezheslové)** — *Audi · Škoda · SEAT · CUPRA.* Přihlaste se na telefonu nebo notebooku a schvalte zařízení; v Home Assistant se neukládá žádné heslo (uchovává se skutečný obnovovací token). V tomto kroku se nabízí i volitelný **S-PIN**, interval skenování a pole pro vynucený přístup.
- **Portál — e-mail + heslo** — *Volkswagen EU · Porsche.* Zadejte přihlášení své značky. Tento krok zpřístupní výběr značky (Volkswagen EU, Porsche a ostatní značky s e-mailem/heslem), e-mail, heslo, volitelný **S-PIN**, interval skenování, vynucený přístup a přepínač **„enable MBB commands"** (který má účinek pouze na Volkswagen EU — viz [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Pro **Volkswagen US/Kanada** se zde objeví **volič země (US vs CA)** — vykreslí se **pouze** pro tuto značku a žádná jiná ho nepoužívá.

> **Portál EU Data Act není třetí přihlašovací tlačítko.** Je to strategie jen pro čtení, na kterou se koordinátor automaticky přepne jako na záložní, a navíc ji lze *přidat* jako doplňkový čtecí kanál z **Konfigurovat → Možnosti**. Totéž platí pro webový kanál `volkswagen.de` (volitelný doplňkový čtecí kanál dostupný jen v Možnostech).

### Pole S-PIN — kdy ho potřebujete

**S-PIN** je bezpečnostní PIN aplikace vaší značky. Ve formuláři je volitelný a vyžaduje se jen pro některé akce: je potřeba pro **čtení dat a příkazy VW US/Kanada** a pro bezpečnostně citlivé vzdálené příkazy u značek, které je za S-PIN zamykají. Pokud ho vaše auto nevyžaduje, nechte ho prázdný.

---

### Volkswagen EU — jak rozproudit svá data (důležité)

U Volkswagen EU **samotné přihlášení nestačí** — VW začne streamovat vozidlová data teprve poté, co *vy* na straně VW zapnete sdílení dat. Pokud se vaše auto objeví bez dat (nebo se neobjeví vůbec), je to téměř vždy z tohoto důvodu, **ne** kvůli špatnému heslu. Jednou proveďte následující:

1. **Přidejte integraci:** zvolte **Portál (e-mail + heslo)** a vyberte **Volkswagen EU**, pak se přihlaste.
2. **Dokončete jakoukoliv jednorázovou výzvu na portálu VW.** Otevřete datový portál VW jednou v prohlížeči nebo v aplikaci značky a dokončete vše, co po vás chce: **přijměte podmínky, potvrďte souhlas, dokončete onboarding / výběr regionu.** Bezobslužný přístup přes tyto kroky neprojde — jde o případ `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Udělte souhlas se sdílením dat.** Na portálu nastavte **„Use of non-personal data" = Granted** (souhlas se sdílením dat dle EU Data Act).
4. **Zapněte průběžný požadavek na data** pro konkrétní auto. Bez něj portál pro dané VIN vrátí *no data request* a vozidlo se objeví bez údajů.
5. **Počkejte, až auto odešle snímek.** I po všem výše uvedeném trvá propagace nějakou dobu. Auto může **chvíli číst `offline` / `unknown` — často až do další jízdy nebo probuzení, klidně ~24 h** — než se senzory naplní. To je normální.

Portál zpočátku poskytuje jen **výsek polí** a tento výsek se **postupně rozšiřuje**, jak VW rozšiřuje pokrytí portálu před zářijovým termínem 2026 — pole, která dnes čtou `unknown`, se mohou sama vyplnit. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Volitelné:** přepínač v Možnostech **`eu_data_act_auto_kickoff`** může za vás automaticky vytvořit 15minutový Custom Data Request. Je volitelný, protože jeho vytvoření znamená **měsíční předplatné na vašem účtu VW**, takže to integrace neudělá bez vašeho svolení.

---

## Co dostanete

- **Senzory:** SoC baterie, dojezd (elektrický / spalovací / celkový), úroveň paliva, tachometr, teploty, výkon/rychlost/typ nabíjení, cíl nabíjení, statistiky jízd a celoživotní souhrny, intervaly servisu a výměny oleje, verze softwaru, stav připojení, naposledy viděno a další.
- **Binární senzory:** zamčené dveře, otevřené dveře/okna/kufr/kapota/střešní okno, připojený konektor, nabíjení, dostupná OTA aktualizace, světla, vozidlo online, časovače odjezdu, alarm.
- **Ovládání:** zamknutí/odemknutí, start/stop klimatizace, start/stop nabíjení, vyhřívání oken, časovače odjezdu, nastavení cílového SoC / teploty / max. nabíjecího proudu, troubení a blikání, probuzení, obnovení, vyhledání nabíjecích stanic *(dostupnost závisí na značce a modelu)*.
- **Sledovač polohy:** GPS poloha pro mapu Home Assistant.
- **Obrázky:** vykreslení vozidla tam, kde je značka poskytuje.

> 💡 **Energetický panel:** senzor nabité energie je `total_increasing`, takže ho přidejte přímo do **energetického panelu** Home Assistant, nebo ho zabalte do pomocníka `utility_meter` pro denní/měsíční souhrny nabité energie. Pro tento účel použijte kumulativní senzor **nabité energie (kWh)** — ne senzory účinnosti na 100 km (ty jsou průměry, ne měřiči).

### Služby

Integrace přináší **20+ volání služeb** (`vag_connect.*`), z nichž mnohá jsou specifická pro značku — *dostupnost závisí na značce a modelu*. Mezi nimi: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi se spalovacím motorem), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` a `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` a easter egg `show_vag`.

---

## ABRP (A Better Routeplanner) živá telemetrie

Živá data svého auta můžete posílat do **[A Better Routeplanner](https://abetterrouteplanner.com/)**, aby plánoval podle vašeho skutečného stavu nabití. Je to **volitelné a ve výchozím stavu vypnuté** — z vaší sítě nic neodejde, dokud to nezapnete a dokud se skutečně nespustí nahrání.

**1. Získejte dvě přihlašovací údaje.**

- **`token`** (na vozidlo) — otevřete aplikaci ABRP → **Settings → vaše auto → Live Data → „Generic" / jiné auto** a zkopírujte token, který zobrazí.
- **`api_key`** (vývojářský klíč) — jde o partnerský/vývojářský klíč vydaný **iternio**, *ne* o něco, co vydá aplikace. Vyžádejte si ho od iternio (jejich formulář pro žádost o vývojářský/API klíč). **Záměrně žádný klíč nedodáváme** — natvrdo zadrátovat klíč, který nevlastníme, by bylo vydávání se za někoho jiného a zapeklo by nevlastněné tajemství do veřejného repozitáře. Vložte svůj vlastní.

**2. Zapněte to.** Integrace → **Konfigurovat** → přejděte na sekci **ABRP** → zaškrtněte *Enable ABRP telemetry push* a vložte obě hodnoty. Validují se jako pár (pokud nastavíte jen jednu, dostanete chybu), ukládají se maskovaně a **nikdy se nezapisují do logu**.

**3. Zautomatizujte nahrávání.** Naimportujte dodávaný blueprint **„ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), vyberte své vozidlo a jeho senzor **ABRP data changed**, a hotovo. Blueprint nahrává jen tehdy, když je k dispozici skutečně nový snímek (binární senzor *ABRP data changed* je idempotentní spouštěč — po každém úspěšném odeslání se resetuje, takže se stejný snímek nikdy neodešle dvakrát).

Můžete také volat službu **`vag_connect.abrp_send`** přímo (cíleně na zařízení nebo VIN; api_key/token se berou z možností, pokud je nepředáte inline).

> 🔒 **Soukromí:** telemetrie zahrnuje GPS. Z vaší sítě odejde jen tehdy, když se spustí `abrp_send` (tj. když ho *vy* spustíte / zapnete blueprint). Co posíláme: stav nabití, stav nabíjení, GPS, kurz, energii + kapacitu, odhadovaný dojezd, okolní + teplotu baterie, tachometr. Co záměrně **neposíláme**: cokoliv, co nedokážeme spolehlivě změřit (rychlost, napětí/proud HV baterie, stav opotřebení) — raději vynecháno než odhadnuto.

---

## Možnosti (Konfigurovat)

Z **Nastavení → Zařízení a služby → VW Group Connect → Konfigurovat** můžete upravit:
interval skenování, S-PIN, zpětné geokódování, **režim jen pro čtení**, vynucenou klimatizaci PPE (Audi), přepínače push (MQTT/FCM/Audi-VW), **záložní prohlížeč EU Data Act** (Playwright / ~100 MB Chromium, volitelné), **wake-before-poll** + prodlevu probuzení, přepsání client-id, **`eu_data_act_auto_kickoff`**, skrytí prázdných entit (výchozí zapnuto), **ABRP** (zapnutí + api_key + uživatelský token, validováno jako pár), plus **přidání / odebrání** doplňkových čtecích kanálů `volkswagen.de` a portálu EU Data Act.

---

## Podpořte tento projekt ❤️

Je to projekt jednoho člověka — a VW to neusnadňuje: každá změna backendu znamená dny reverzního inženýrství, než se najde fungující cesta. Právě tahle vytrvalost ho udržuje naživu tam, kde to zavedené projekty vzdaly. Pokud pro vás má hodnotu, můžete podpořit pokračující údržbu přes **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Děkuji! 🙏

---

## Přispívání

PR jsou vítány — viz [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** promění neznámá pole API v předvyplněné hlášení chyby na jedno kliknutí, takže můžete pomoci zlepšit pokrytí, aniž byste četli kód.

## Licence

[GNU AGPL v3.0-or-later](LICENSE) pro kód integrace. Povinné uvedení autorství + podmínky k názvu/ochranné známce při použití/forku: viz [`ATTRIBUTION.md`](ATTRIBUTION.md). Uvedení autorství upstreamového open-source v [`NOTICE.md`](NOTICE.md).
