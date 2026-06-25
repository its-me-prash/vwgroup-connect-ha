<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Jedna integrace pro Home Assistant pro všech sedm značek koncernu Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Kanada</strong><br>
  <em>Přímý přístup k API, více kanálů s automatickým záložním přepnutím, žádný mezičlánek.</em>
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
  🌍 <a href="README.md">English</a> · <a href="README.fr.md">Français</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Poznámka k přejmenování
> Dříve vycházelo pod názvem **`vag-connect-ha`** (VAG = Volkswagen AG, běžná zkratka v německy mluvících zemích).
> Jenže pro anglicky mluvící zní ta zkratka *dost* jinak 😅
>
> **Co funguje dál úplně stejně jako dřív**: všechny entity (např. `sensor.audi_q4_battery_soc`),
> všechna volání služeb (`vag_connect.lock`, `vag_connect.show_vag` atd.), všechny automatizace,
> instalace přes HACS — **nic se nerozbije**. Změnil se jen marketingový/zobrazovaný název, vnitřek kódu
> zůstává beze změny. Viz [`MIGRATION.md`](MIGRATION.md).
>
> Obrovský dík komunitám **Home Assistant UK** a **HA Ideas, Projects and Solutions**
> za upozornění — zvlášť **Si Gregory**, **Ben Johnson** a **Evets David**.
>
> A zvláštní pozdrav patří **Jordanu Waelesovi**, jehož komentář `show_vag()` je teď v této integraci
> oficiálně podporovaný easter egg (služba `vag_connect.show_vag`, viz CHANGELOG v2.2.3).

---

## O co jde?

**VW Group Connect je integrace pro [Home Assistant](https://www.home-assistant.io), která přináší data a ovládání připojeného auta do vaší chytré domácnosti pro všech sedm značek koncernu Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche a VW US/Kanada — plus Bentley (pouze čtení), a to z jediné konfigurační položky.**

Zobrazuje stav baterie a nabíjení, dojezd, stav tachometru, klimatizaci, dveře a okna, polohu a další — a tam, kde to backend dané značky ještě dovoluje, posílá vzdálené příkazy jako zamknutí/odemknutí, ovládání klimatizace a nabíjení. Aby fungovala i přes změny API, které Volkswagen zavedl v roce 2026, používá **několik kanálů a v případě zablokování jednoho z nich se automaticky přepne** na jiný: nativní backendy jednotlivých značek, portál s daty vozidla podle **EU Data Act** (pouze čtení), volitelný webový kanál přes `volkswagen.de` a trvalé přihlášení **bez hesla** pro starší vozy s Car-Net. Bez problémů běží **vedle [evcc](https://evcc.io)** a nepotřebuje **žádné závislosti z PyPI**.

> 🎉 **Nyní dostupné přímo v HACS** — žádný vlastní repozitář není potřeba.

---

## Hlavní přednosti

- **Všech 7 značek koncernu VW včetně Porsche a VW US/Kanada** v jediné integraci — portál EU Data Act z principu Porsche *vynechává*, takže nástroje stavějící jen na portálu ho nikdy nepokryjí.
- **Obousměrné ovládání** tam, kde to značka dovolí (zamknutí/odemknutí, klimatizace, nabíjení, cílové SoC) — nejen čtení.
- **Možnost přihlášení bez hesla** (prohlížeč / device-code) — v Home Assistantu se neukládá žádné heslo.
- **Více kanálů s automatickým záložním přepnutím** — nativní backend značky → portál EU Data Act → volitelný web vw.de → trvalý Car-Net. Výpadek jednoho kanálu vám neutne přístup k datům.
- **Odolnost už od návrhu** — udržuje poslední známé hodnoty i během výpadků portálu, odfiltruje nesmyslné zástupné hodnoty typu „žádné měření" a nikdy nedovolí, aby tachometr skočil zpět.
- **GPS sledovač polohy**, 100+ entit napříč 11 platformami, 20+ volání služeb, více vozidel na jeden účet.
- **Vehicle Data Scout** — automaticky rozpozná posun v API a nabídne hlášení chyby na jedno kliknutí. **Quality Scale: Platinum.**

---

## Stav podle značky

| Značka | Ovládání | Data | Poznámky |
|---|---|---|---|
| **Audi** | ✅ Obousměrné | ✅ Plné | backend myAudi |
| **Škoda** | ✅ Obousměrné | ✅ Plné | nativní backend Škoda |
| **Porsche** | ✅ Obousměrné | ✅ Plné | Porsche Connect |
| **VW US/CA** | ✅ Obousměrné | ✅ Plné | cloud VW NA |
| **VW EU** | ⚠️ Trvalý Car-Net (starší modely) | ✅ EU Data Act + vw.de (beta) | novější vozy ID/MEB: pouze čtení přes portál |
| **CUPRA / SEAT** | ⚠️ Omezené | ✅ EU Data Act | backend značky od roku 2026 zablokován ze strany VW |
| **Bentley** | ⏳ Čeká na živý test | ✅ Přihlášení + čtení | My Bentley — běží na platformě/tenantu Audi |

> Upřímná poznámka: v roce 2026 Volkswagen schoval části svého API za atestaci zařízení. Tato integrace to tam, kde to jde, obchází (trvalé přihlášení Car-Net, portál EU Data Act, web vw.de) a otevřeně říká, co každý kanál umí a co ne.

---

## Známá omezení

Pár věcí je **systémových** — vyplývají z toho, jak backendy Volkswagenu v roce 2026 fungují, ne z integrace, a žádné nastavení je nespraví:

- **Vozy z rodiny MEB / ID jsou pouze pro čtení** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Vzdálené příkazy — zamknutí, klimatizace, nabíjení — pro tyto vozy **nejsou k dispozici**: trvalá cesta příkazů přes Car-Net, kterou používáme, je nezná (odpovídá „Unknown user") a backend VW pro MEB nic obdobného nenabízí. Telemetrii přes portál EU Data Act stále dostanete — jen bez ovládání. Nastavení to rozpozná a místo selhání vytvoří **položku pouze pro čtení**, takže jde o známé, nikoli skryté omezení.
- **Vzdálené příkazy pro CUPRA / SEAT jsou ze strany VW zablokované.** Přístup k online službám (OLA) byl pro tyto značky v roce 2026 odebrán na straně serveru (HTTP 403); nové přihlášení ani aktualizace verze aplikace ho neobnoví. Data dál tečou přes portál EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Data z portálu EU Data Act jsou skoupá a liší se vůz od vozu.** VW dnes zveřejňuje jen výsek polí (často tachometr + zámek + nabíjení, někdy mnohem víc). Rozsah se postupně rozšiřuje, jak VW portál před termínem v září 2026 doplňuje — pole, která dnes hlásí `unknown`, se mohou sama zaplnit, bez jakéhokoli zásahu. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Instalace

**Přes HACS (doporučeno):**

1. Otevřete v Home Assistantu **HACS**.
2. Vyhledejte **„VW Group Connect"** a nainstalujte ji.
3. Restartujte Home Assistant.
4. Přejděte do **Nastavení → Zařízení a služby → Přidat integraci → VW Group Connect** a projděte přihlašovací postup.

<sup>Právě bylo sloučeno do výchozího katalogu HACS — pokud zatím nejde vyhledat, dejte indexu HACS chvilku na obnovení, nebo mezitím přidejte `its-me-prash/vwgroup-connect-ha` jako vlastní repozitář.</sup>

**Možnosti přihlášení** (vyberte podle toho, co vaše auto/značka podporuje):
- **Prohlížeč / device-code (bez hesla)** — přihlásíte se na telefonu nebo notebooku a zařízení schválíte; žádné heslo se neukládá. (Audi, Škoda, SEAT, CUPRA.)
- **E-mail + heslo** — vyžadováno pro Volkswagen EU a Porsche.
- **Portál EU Data Act** — záložní režim pouze pro čtení pro všechny značky.

---

## Co dostanete

- **Senzory:** SoC baterie, dojezd (elektrický / spalovací / celkový), stav paliva, tachometr, teploty, výkon/rychlost/typ nabíjení, cíl nabití, statistiky jízd i celkové součty za životnost, intervaly servisu a výměny oleje, verze softwaru, stav připojení, naposledy spatřeno a další.
- **Binární senzory:** zamčené dveře, otevřené dveře/okna/kufr/kapota/střešní okno, připojený konektor, nabíjení, dostupná OTA aktualizace, světla, vozidlo online, časovače odjezdu, alarm.
- **Ovládání:** zamknutí/odemknutí, spuštění/zastavení klimatizace, spuštění/zastavení nabíjení, vyhřívání oken, časovače odjezdu, nastavení cílového SoC / teploty / maximálního nabíjecího proudu, houkni a zablikej, probuzení, obnovení dat, vyhledání nabíjecích stanic *(dostupnost závisí na značce a modelu)*.
- **Sledovač polohy:** poloha GPS pro mapu v Home Assistantu.
- **Obrázky:** vyobrazení vozidla tam, kde je značka poskytuje.

> 💡 **Energetický panel:** senzor nabité energie je typu `total_increasing`, takže ho přidejte přímo do **energetického panelu** Home Assistantu, nebo ho obalte pomocníkem `utility_meter` pro denní/měsíční součty nabité energie. Použijte k tomu kumulativní senzor **nabité energie (kWh)** — ne senzory spotřeby na 100 km (to jsou průměry, ne měřiče).

---

## Podpořte tento projekt ❤️

Tohle je projekt jednoho člověka — a VW to nijak neusnadňuje: každá změna backendu znamená dny zpětného inženýrství, než se zase najde funkční cesta. Právě tahle vytrvalost ho drží při životě tam, kde to zavedené projekty vzdaly. Pokud pro vás má nějakou hodnotu, můžete pokračující údržbu podpořit přes **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Děkuji! 🙏

---

## Jak přispět

PR jsou vítány — viz [`CONTRIBUTING.md`](CONTRIBUTING.md). **Vehicle Data Scout** promění neznámá pole API ve předvyplněné hlášení chyby na jedno kliknutí, takže můžete pomoct rozšířit pokrytí, aniž byste četli kód.

## Licence

[GNU AGPL v3.0-or-later](LICENSE) pro kód integrace. Povinné uvedení autorství a podmínky k názvu/ochranné známce při použití/forku: viz [`ATTRIBUTION.md`](ATTRIBUTION.md). Uvedení autorství u použitého open-source softwaru najdete v [`NOTICE.md`](NOTICE.md).