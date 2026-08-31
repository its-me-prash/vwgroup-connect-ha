<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Eine Home-Assistant-Integration für Fahrzeuge des Volkswagen-Konzerns: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW und Audi US/Kanada</strong><br>
  <em>Batterie, Laden, Reichweite, Türen, Klima und GPS-Standort in Home Assistant. Direkter API-Zugriff, mehrere Lesekanäle mit automatischem Fallback, keine Middleware.</em>
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

> ### 📛 Hinweis zur Umbenennung
> Früher veröffentlicht als **`vag-connect-ha`** (VAG = Volkswagen AG, gängige DACH-Abkürzung).
> Wie sich herausstellt, liest sich diese Abkürzung für Englischsprachige *ziemlich* anders 😅
>
> **Was wie bisher funktioniert**: alle Entitäten (z. B. `sensor.audi_q4_battery_soc`),
> alle Service-Calls (`vag_connect.lock`, `vag_connect.show_vag` usw.), alle Automationen,
> die HACS-Installation — **nichts geht kaputt**. Es ändert sich der Marketing-/Anzeigename,
> der Code-Innenbau bleibt unverändert. Siehe [`MIGRATION.md`](MIGRATION.md).
>
> Riesen-Dank an die Communities **Home Assistant UK** und **HA Ideas, Projects and Solutions**
> für den Hinweis — besonders an **Si Gregory**, **Ben Johnson** und **Evets David**.
>
> Und ein spezieller Shoutout an **Jordan Waeles**, dessen `show_vag()`-Kommentar jetzt ein offiziell
> unterstütztes Easter-Egg in dieser Integration ist (`vag_connect.show_vag`-Service, siehe CHANGELOG v2.2.3).

---

## Was ist das?

**VW Group Connect ist eine [Home Assistant](https://www.home-assistant.io)-Integration, die dein Auto aus dem Volkswagen-Konzern ins Smart Home holt: Batterie- und Ladezustand, Reichweite, Kilometerstand, Klima, Türen und Fenster, GPS-Standort und mehr, für Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley und die nordamerikanischen VW-/Audi-Konten, alles aus einem einzigen Konfigurationseintrag.**

Wo das Backend der Marke es noch erlaubt, sendet sie zusätzlich Fernbefehle wie Ver-/Entriegeln, Klima- und Ladesteuerung. **Das ist markenabhängig, nicht universell:** Audi und Škoda sind Zwei-Wege, Volkswagen EU am EU-Data-Act-Portal ist schreibgeschützt, und SEAT-/CUPRA-Befehle sind vom Hersteller blockiert. Die Tabelle unten sagt genau, was wo gilt.

Um durch Volkswagens API-Änderungen von 2026 hindurch weiter zu funktionieren, spricht sie **mehrere Lesekanäle und fällt automatisch zurück**, wenn einer blockiert ist: die markeneigenen Backends, das schreibgeschützte **EU Data Act**-Fahrzeugdaten-Portal, einen optionalen `volkswagen.de`-Webkanal (Beta), eine optionale **Tibber**-Lückenfüllung und ein dauerhaftes **passwortloses** Login für ältere Car-Net-Fahrzeuge. Sie läuft problemlos **parallel zu [evcc](https://evcc.io)** (siehe [docs/EVCC.md](docs/EVCC.md)) und braucht **kein Add-on, keinen Broker und keinen Middleware-Container**. Home Assistant installiert dafür automatisch drei kleine Python-Pakete; sie werden nur von den optionalen Push- und Companion-(ADB-)Kanälen genutzt.

> 🎉 **Jetzt direkt in HACS verfügbar** — kein Custom-Repository nötig.

---

## Highlights

- **10 wählbare Volkswagen-Konzernmarken/-Quellen** in einer Integration: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Kanada, Audi US/Kanada, Porsche, Bentley und **Audi plug&play (OBD-Dongle)** für ältere Audis ohne Werkskonnektivität.
- **Ältere Audis ohne eingebaute Konnektivität, über einen OBD-Dongle (neu in 4.3.0)**: Autos, die für das CARIAD-Backend und das EU-Data-Act-Portal unsichtbar sind (A4/A5 ohne Konnektivität, Touareg, e-up!, …), lassen sich über den Cloud-Snapshot eines TEXA-Plug&Play-Dongles auslesen — Kilometerstand, 12-V-Batteriespannung, Warnleuchten, letzte Parkposition, dazu Werks-Stammdaten (Motorleistung, Hubraum, Farben, Modellbezeichnung). Schreibgeschützt, in eigenem Token-Silo.
- **Zwei-Wege-Steuerung, wo das Backend der Marke es zulässt**: Ver-/Entriegeln, Klima, Laden, Ziel-SoC. Das ist **markenabhängig, nicht universell**. Schau in die Tabelle unten, bevor du dich auf einen Befehl verlässt.
- **Škodas Bordassistentin „Laura" in Home Assistant (neu in 3.0.0)**: Frag als Service nach Reichweite, Laden und Fahrten, oder übergib sie an einen beliebigen Conversation-Agent (das eingebaute Assist, OpenAI, Anthropic, Google, Ollama) als Werkzeug, das er aufrufen und verketten kann. Schreibgeschützte Ratschläge, auf die deine Automationen reagieren können.
- **Logbuch-Events, Firmware- & Kalender-Karten (neu in 3.1.0)**: Hersteller-Push-Benachrichtigungen werden zu einer `event`-Entität pro Fahrzeug (Logbuch + Automationen, kein YAML-Bus-Filter), eine schreibgeschützte Firmware-`update`-Entität zeigt den OTA-Status (Škoda heute, kein Installieren-Button), und zwei `calendar`-Entitäten legen den Ladeplan + die Service-Fälligkeiten aus.
- **Passwortlose Login-Option** (Browser/Device-Code) für Audi, SEAT, CUPRA und Audi US/CA. Kein Passwort wird in Home Assistant gespeichert. Škoda ist in 3.0.1 auf E-Mail + Passwort umgestiegen, als VW seinen Device-Code-Grant entzogen hat.
- **Mehrkanalig mit Auto-Fallback**: markeneigen, EU-Data-Act-Portal, optionales vw.de-Web, optional Tibber, dauerhaftes Car-Net und ein OBD-Dongle-Cloud-Reader für Audis ohne Werkskonnektivität. Fällt ein Kanal aus, gehen deine Daten nicht dunkel.
- **Companion-Kanal (experimentell, Opt-in)**: Wenn alle Backend-Pfade dicht sind, kann die Integration dein Auto auslesen, indem sie die offizielle App auf einem ungenutzten Android-Handy fernsteuert. Drei Transportwege: **ADB über TCP**, das [**ADB-Bridge-Add-on**](https://github.com/its-me-prash/vwgroup-app-adb-bridge) für moderne Handys und — neu in der 4.4.0-Beta — eine **Companion-Agent-App**, die auf dem Handy läuft und ihrerseits *Home Assistant anruft* über einen ausgehenden Long-Poll, sodass NAT, wechselnde IPs und Wi-Fi-Client-Isolation keine Rolle mehr spielen (die Agent-App ist ein separates Artefakt, noch nicht ausgeliefert; das Protokoll steht in [docs/COMPANION_AGENT.md](docs/COMPANION_AGENT.md)). Volkswagen ist an einem echten Gerät verifiziert; die anderen Marken sind schreibgeschützt, bis eine Screen-Map bestätigt ist. Nichts wird gerootet und es werden keine App-Tokens ausgelesen.
- **Resilient by Design**: behält letzte bekannte Werte und die zuletzt bekannte Parkposition durch Portal-Ausfälle hindurch, filtert falsche „keine Messung"-Platzhalter, lässt den Kilometerstand nie rückwärts springen und sagt dir, wenn ein fehlgeschlagenes Login eine Störung beim Hersteller ist und nicht dein Passwort.
- **Du bestimmst das Abfrageintervall**: ein **Abfrageintervall-Regler** pro Konto (eine Number-Entität, in Minuten), den Automationen steuern können, angelegt für jedes Setup, auch für schreibgeschützte Portal-Einträge.
- **GPS-Device-Tracker**, 100+ Entitäten über mehrere Plattformen, 30+ Service-Calls, mehrere Fahrzeuge pro Konto, Entitätsnamen in **12 Sprachen**.
- **Porsche läuft über sein eigenes Backend**, nicht über das EU-Data-Act-Portal. Der Portal-Pfad schliesst Porsche strukturell *aus*, also können Portal-only-Tools es niemals abdecken. Der Befehls-Code liegt hier, aber das Porsche-Login selbst ist derzeit experimentell (siehe Tabelle).
- **Vehicle Data Scout** erkennt API-Drift automatisch und bietet einen Ein-Klick-Bug-Report an — und ab 3.0.0 enthält der geschwärzte Diagnose-Download auch die rohen API-Antworten, sodass ein einziger Anhang alles ist, was man braucht, um Unterstützung für ein neues Feld hinzuzufügen. **Quality Scale: Platinum.**

---

## Markenstatus

| Marke | Steuerung | Daten | Hinweise |
|---|---|---|---|
| **Audi** (EU) | ✅ Zwei-Wege | ✅ Voll | myAudi-Backend (inkl. Verbrenner-Motorstart/-stopp). Legacy-Car-Net-Audis können einen **dauerhaften MBB-Befehlskanal** aktivieren, der Neustarts und die Play-Integrity-Wand übersteht — neu in 4.4.0, standardmässig aus; neuere ID-/MEB-Audis sind nicht berechtigt ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **Škoda** | ✅ Zwei-Wege | ✅ Voll | natives Škoda-Backend |
| **VW US/CA** | 🇨🇦 ✅ Zwei-Wege · 🇺🇸 ⛔ von VW blockiert | 🇨🇦 ✅ Voll · 🇺🇸 ⛔ | Kanada meldet sich am eigenen Server + App-Client an und zeigt volle Daten, bestätigt an einem echten kanadischen ID.4 ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **US: seit 2026-08-13 erzwingt VW Device-Attestation (Play Integrity) auf der Nordamerika-Ebene, daher scheitert US-Login / Token-Exchange hart (401) — eine VW-seitige Wand, die ein Open-Source-Client ausserhalb des Geräts nicht erfüllen kann ([#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)).** |
| **VW EU** | 🔒 Standardmässig schreibgeschützt · ⚠️ Befehle = Car-Net **Beta** | ✅ Volle Telemetrie via EU-Data-Act-Portal | Siehe den ehrlichen Hinweis unten ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Befehle von VW blockiert | ✅ EU-Data-Act-Portal | OLA-Zugriff 2026 serverseitig entzogen ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Zwei-Wege durch Live-Test gegated | ✅ Login + Lesen | My Bentley, läuft auf dem Audi/IDK-Tenant |
| **Porsche** | ⚠️ Experimentell | ⚠️ Experimentell | Porsche Connect, eigenes Backend. Porsche ist auf die *Porsche One*-App umgestiegen, deshalb **schlägt das Login bei aktuellen Konten voraussichtlich fehl**. Der Befehls-Code ist da, aber unerreichbar, bis das Login neu gebaut ist ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi US/CA** | ⏳ Zwei-Wege durch Live-Test gegated | ✅ Voll | myAudi-NA-Backend. US liest jetzt vom regionalen `na`-Fahrzeugdienst und **funktioniert bestätigt an einem echten US-Audi Q5** (58 Entitäten) — Dank an @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada nutzt den EMEA-Dienst. Befehle erben die Audi-Zwei-Wege-Pfade, sind auf NA aber noch nicht separat live bestätigt ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |
| **Audi plug&play** (OBD-Dongle) | ⛔ Schreibgeschützt | ✅ Lesen über Dongle-Cloud | TEXA-OBD-Dongle für Audis ohne Werkskonnektivität; Kilometerstand, 12 V, Lichter, Parkposition + Werks-Stammdaten. Schreibgeschützt, eigenes Token-Silo (neu in 4.3.0) |

> **Ehrlicher Hinweis zur VW-EU-Steuerung.** Volkswagen-EU-Fahrzeuge sind **standardmässig schreibgeschützt**: Du bekommst volle Telemetrie über das EU-Data-Act-Portal, aber keine Fernbefehle. Am **2026-08-18 hat VW den Login abgeschaltet**, den die moderne (CARIAD) Zwei-Wege nutzte — dieser Kanal lässt sich nicht mehr einrichten. Fernbefehle für VW EU existieren jetzt **nur als dauerhafte Car-Net-(MBB-)Zwei-Wege-BETA** und nur für **Legacy-MQB-/Car-Net**-Autos — ein Opt-in-Schalter, **kein** Standardfeature. **MEB-/ID-Familien-Autos (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) haben gar keinen Befehlspfad** und werden schreibgeschützt angelegt. Die Car-Net-Beta wird in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** verfolgt — Tester:innen willkommen.

> 2026 hat Volkswagen Teile seiner API hinter Device-Attestation gestellt und zieht sie übers Jahr weiter an: **Volkswagen US ging am 2026-08-13 down** (Play-Integrity auf der Nordamerika-Ebene, [#1215](https://github.com/its-me-prash/vwgroup-connect-ha/issues/1215)), und der **moderne VW-EU-Zwei-Wege-Login wurde am 2026-08-18 gekappt**. Diese Integration umgeht Attestation, wo möglich (dauerhaftes Car-Net-Login, EU-Data-Act-Portal, vw.de-Web), und ist transparent darüber, was jeder Kanal kann und nicht kann. **Tipp: pro Auto nur einen Two-Way-Zugang betreiben — VW drosselt Konten, die mehrere Apps gleichzeitig bombardieren, und ein gesperrtes Konto legt auch die offizielle App lahm.**

---

## Bekannte Einschränkungen

Ein paar Dinge sind **strukturell** — sie kommen daher, wie Volkswagens Backends 2026 funktionieren, nicht von der Integration, und keine Einstellung behebt sie:

- **VW EU ist standardmässig schreibgeschützt; Befehle sind eine MBB-Alpha, nur für Legacy-Autos.** Siehe den Markenhinweis oben. **MEB-/ID-Familien-Autos sind schreibgeschützt** — der dauerhafte Car-Net-Befehlspfad erkennt sie nicht (er antwortet „Unknown user"), und VWs MEB-Backend bietet kein Äquivalent. Das Setup erkennt das und legt einen **schreibgeschützten Eintrag** an (mit Reparatur-Hinweis), statt zu scheitern — es ist also eine bekannte Grenze, keine stille. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA-/SEAT-Fernbefehle werden von VW blockiert.** Der Online-Services-Zugriff (OLA) für diese Marken wurde 2026 serverseitig entzogen (HTTP 403); ein erneutes Login oder ein App-Versions-Bump stellt ihn nicht wieder her. Daten fliessen weiterhin über das EU-Data-Act-Portal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Die EU-Data-Act-Portaldaten sind dünn und variieren je nach Auto.** VW veröffentlicht heute nur einen Ausschnitt der Felder (oft Kilometerstand + Verriegelung + Laden, manchmal deutlich mehr). Er weitet sich mit der Zeit, während VW das Portal vor der Frist im September 2026 ausbaut — Felder, die heute `unknown` zeigen, füllen sich womöglich von selbst, ohne Änderung. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **VW-EU-Autos haben über das EU-Data-Act-Portal keine Live-GPS-Position.** Volkswagen Group Info Services hat [schriftlich bestätigt](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13#issuecomment-5359744122), dass das Data-Dictionary des kontinuierlichen Portal-Exports zwar ein Cluster *Fahrzeug-Standortverfolgung* auflistet, aber **keinen definierten Datenpunkt für die aktuellen Koordinaten des Autos** (Breiten-/Längengrad) enthält — ein VW-EU-Auto, das nur über das Portal gelesen wird, zeigt seinen Standort daher als `unknown`. Das ist eine Grenze von VWs Datensatz, nicht der Integration, und der Positions-Endpunkt der Hersteller-App wurde für Dritte geschlossen. Nordamerikanische VW/Audi und andere Marken mit funktionierendem Positions-Endpunkt sind nicht betroffen. ([#923](https://github.com/its-me-prash/vwgroup-connect-ha/issues/923))
- **Nordamerika: VW und Audi lesen jetzt beide — die Audi-Befehle sind das letzte unbestätigte Stück.** **VW US/CA funktioniert, auch Kanada**, an einem echten kanadischen ID.4 bestätigt: Kanada meldet sich am eigenen Server an, und seit dem Fix an der Datenhülle zeigt es volle Telemetrie ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Audi US/CA liest jetzt auch**: US liest vom regionalen `na`-Fahrzeugdienst, bestätigt an einem echten US-Audi Q5 (Dank an @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); Kanada nutzt den EMEA-Dienst. Befehle erben die Audi-Zwei-Wege-Pfade, sind auf nordamerikanischen Konten aber noch nicht separat live bestätigt ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **Das Porsche-Login schlägt derzeit voraussichtlich fehl.** Porsche hat die *My Porsche*-App, gegen die sich diese Integration authentifiziert, zugunsten von *Porsche One* eingestellt. Lesen und Befehle sind implementiert, aber du kommst wahrscheinlich nicht am Login vorbei, bis das neu gebaut ist. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Push-Updates (nahezu in Echtzeit) sind eine Opt-in-BETA und standardmässig aus.** Die MQTT- (Škoda) und Firebase-Kanäle (Audi/VW, CUPRA/SEAT) sind verdrahtet, aber nicht live validiert, und die Marken sichern sie zunehmend mit App-Attestation ab, die sich ausserhalb des Geräts nicht erfüllen lässt. Lass sie aus, ausser du willst beim Testen helfen. Normales Polling ist der unterstützte Weg.

> **Wo wir stehen.** Nach dem EU Data Act (Verordnung (EU) 2023/2854) gehören die Daten deines Autos *dir*. Diese Integration auf deiner eigenen Hardware zu betreiben heisst, dass *du* auf *deine eigenen* Daten zugreifst (Artikel 4) — geschuldet in derselben Qualität, in der der Hersteller sie sich selbst liefert, in Echtzeit, wo technisch machbar. VWs schreibgeschütztes, stundenlang veraltetes Portal wird dem heute nicht gerecht. Diese Integration ist bewusst **kanalunabhängig**: In dem Moment, in dem VW den Besitzern eine echtzeitfähige, steuerbare Schnittstelle gibt — wie es der Data Act verlangt und wie es manche Hersteller ihren Besitzern schon heute bieten — unterstützen wir sie hier, kostenlos, für alle. Wir stehen hinter deinem Recht auf Echtzeit-Zugriff auf dein eigenes Auto.

---

## Installation

**Über HACS (empfohlen):**

1. Öffne **HACS** in Home Assistant.
2. Suche nach **„VW Group Connect"** und installiere es.
3. Starte Home Assistant neu.
4. Geh zu **Einstellungen → Geräte & Dienste → Integration hinzufügen → VW Group Connect** und folge dem Login-Ablauf.

<sup>Gerade in den HACS-Default gemergt — falls es noch nicht durchsuchbar ist, gib dem HACS-Index etwas Zeit zum Aktualisieren, oder füge in der Zwischenzeit `its-me-prash/vwgroup-connect-ha` als Custom-Repository hinzu.</sup>

**Minimum Home Assistant: `2024.4.0`.**

### Login-Optionen (der Setup-Assistent hat zwei Pfade)

Der erste Bildschirm der Integration bietet **zwei** Login-Methoden. Wähle die, die deine Marke unterstützt:

- **Browser / Device-Code (passwortlos)** für *Audi, SEAT, CUPRA und Audi US/CA*. Melde dich auf deinem Handy oder Laptop an und bestätige das Gerät; kein Passwort wird in Home Assistant gespeichert (es behält ein echtes Refresh-Token). Dieser Schritt bietet zusätzlich die optionale **S-PIN** und das Scan-Intervall.
- **Portal, E-Mail + Passwort** für *Volkswagen EU, Škoda, Volkswagen US/CA, Bentley und Porsche (experimentell)*. Gib dein Marken-Login ein. Dieser Schritt zeigt einen Markenwähler, E-Mail, Passwort, optionale **S-PIN**, Scan-Intervall und einen **„MBB-Befehle aktivieren"**-Schalter — den dauerhaften Car-Net-Befehlskanal — für Volkswagen EU und, **jetzt live validiert, für Legacy-Car-Net-Audi** (standardmässig aus, [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)); passwortlosen (Device-Code) Audi-Logins wird derselbe dauerhafte MBB-Opt-in als eigener Setup-Schritt angeboten. Für **Volkswagen US/Kanada** erscheint hier ein **Länderwähler (US vs. CA)**; er wird **nur** für diese Marke angezeigt und von keiner anderen genutzt. **Audi plug&play (OBD-Dongle)** ist eine eigene Auswahl — Fahrzeuge werden automatisch aus dem Cloud-Konto des Dongles erkannt.

> Das **EU-Data-Act-Portal ist kein dritter Login-Button.** Es ist die schreibgeschützte Strategie, auf die der Koordinator automatisch zurückfällt, und es kann zusätzlich als ergänzender Lesekanal über **Konfigurieren → Optionen** *hinzugefügt* werden. Dasselbe gilt für den `volkswagen.de`-Webkanal (Opt-in-Beta, nur über die Optionen, schreibgeschützt) und den optionalen **Tibber**-Kanal, der Lücken füllt, die die Erstanbieter-Kanäle leer gelassen haben, und nie frischere Daten überschreibt.

### Das S-PIN-Feld — wann du es brauchst

Die **S-PIN** ist die Sicherheits-PIN deiner Marken-App. Sie ist im Formular optional und nur für manche Aktionen nötig: gebraucht wird sie für **Datenlesungen und Befehle bei VW US/Kanada** und für sicherheitskritische Fernbefehle bei Marken, die sie hinter der S-PIN absichern. Lass sie leer, wenn dein Auto keine verlangt.

---

### Volkswagen EU — deine Daten zum Fliessen bringen (wichtig)

Bei Volkswagen EU reicht **Einloggen nicht** — VW streamt Fahrzeugdaten erst, wenn *du* auf VWs Seite die Datenfreigabe eingeschaltet hast. Falls dein Auto ohne Daten auftaucht (oder gar nicht erscheint), ist das fast immer der Grund, **nicht** ein falsches Passwort. Mach das einmal:

1. **Integration hinzufügen:** Wähle **Portal (E-Mail + Passwort)** und **Volkswagen EU**, dann einloggen.
2. **Erledige eine etwaige einmalige Abfrage auf VWs Portal.** Öffne das VW-Datenportal einmal im Browser oder in der Marken-App und schliess ab, was es verlangt: **Bedingungen akzeptieren, Einwilligung bestätigen, Onboarding / Regionsauswahl abschliessen.** Headless-Zugriff kommt an diesen nicht vorbei — das ist der Fall `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Datenfreigabe-Einwilligung erteilen.** Setze im Portal **„Nutzung nicht-personenbezogener Daten" = Erteilt** (die EU-Data-Act-Datenfreigabe-Einwilligung).
4. **Such nicht nach einem Schalter für die „kontinuierliche Datenanfrage" — den gibt es nicht.** Die Integration legt diese Anfrage für jedes Auto selbst an, und sie ist **kostenlos**. Seit v2.29.0 wird die Anfrage **ohne Ablaufdatum** angelegt; frühere Versionen haben einen Monat angefragt, weshalb manche Setups nach rund vier Wochen stillschweigend verstummt sind. Wenn bei dir keine Daten mehr ankommen und du das Konto vor v2.29.0 eingerichtet hast, entferne das Konto einmal aus der Integration und füge es neu hinzu, damit eine frische Anfrage angelegt wird. Ohne Anfrage liefert das Portal für diese VIN nichts, und das Fahrzeug erscheint ohne Messwerte.
5. **Warte, bis das Auto einen Snapshot pusht.** Selbst nach all dem braucht die Propagierung Zeit. Das Auto kann **eine Weile `offline` / `unknown` anzeigen — oft bis zur nächsten Fahrt oder zum nächsten Aufwachen, bis zu ~24 h** — bevor sich die Sensoren füllen. Das ist normal.

Das Portal liefert anfangs nur einen **Ausschnitt der Felder**, und dieser Ausschnitt **weitet sich mit der Zeit**, während VW die Portalabdeckung vor der Frist im September 2026 ausbaut — Felder, die heute `unknown` zeigen, füllen sich womöglich von selbst. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Vollständige Feldliste.** Das komplette offizielle VW-Group-Data-Dictionary (jeder EU-Data-Act-Key -> Feld, Beschreibung und Einheit) steht in [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Ein wöchentlicher Workflow beobachtet die Dictionary-Seite des Portals und öffnet einen Pull-Request, sobald VW eine neuere Version veröffentlicht, damit die Tabelle nicht stillschweigend veraltet.

> Der Optionen-Schalter **`eu_data_act_auto_kickoff`** ist das, was die 15-Minuten-Custom-Data-Request anlegt, und er ist **standardmässig an** — im Portal-Modus gibt es ohne sie keine Daten. Schalte ihn nur aus, wenn du die Anfrage lieber selbst verwalten willst.

---

## Was du bekommst

- **Sensoren:** Batterie-SoC, Reichweite (elektrisch / Verbrenner / gesamt), Tankfüllstand, Kilometerstand, Temperaturen, Ladeleistung, Laderate (immer in km/h, bei Fahrzeugen die in mph melden wird umgerechnet) und Ladetyp, Ladeziel, Verlauf je Ladesitzung (Energie · Dauer · Start · AC/DC) bei Škoda und SEAT/CUPRA, Trip-Statistiken & Lebensdauer-Aggregate, Service- & Ölservice-Intervalle, Softwareversion, Verbindungszustand, zuletzt gesehen und — bei Škoda — letzte Betankung, aktuelle Parkgebühren-Sitzung, Service-Erinnerungen, Abfahrtszeiten und bevorzugter Lademodus, und mehr.
- **Binärsensoren:** Türen verriegelt, Türen/Fenster/Kofferraum/Haube/Schiebedach offen, Stecker verbunden, Laden, OTA-Update verfügbar, Lichter, Fahrzeug online, Abfahrtszeiten, Alarm.
- **Steuerung:** Ver-/Entriegeln, Klima Start/Stopp, Laden Start/Stopp, Scheibenheizung, Abfahrtszeiten, Ziel-SoC / Temperatur / max. Ladestrom setzen, Hupen-und-Blinken (mit wählbarer Dauer und wahlweise nur Licht oder zusätzlich Hupe), Aufwecken, Aktualisieren, Ladestationen finden, Camping-Modus und aktive Belüftung (Škoda-Innenraumlüftung ohne Heizen) *(Verfügbarkeit hängt von Marke & Modell ab)*.
- **Device-Tracker:** GPS-Position für die Home-Assistant-Karte. Kommt eine Abfrage ohne Koordinaten zurück, bleibt die zuletzt bekannte Parkposition erhalten, statt verloren zu gehen.
- **Bilder:** Fahrzeug-Renderings, wo die Marke sie bereitstellt.
- **Events, Updates & Kalender (neu in 3.1.0):** eine Push-`event`-Entität pro Fahrzeug (Hersteller-Benachrichtigungen im Logbuch + Automationen), eine schreibgeschützte Firmware-**update**-Entität (Škoda-OTA-Status — kein Installieren-Button, das Auto flasht sich selbst) und **Ladeplan- + Service-Kalender**, die die Timer und Fälligkeiten auf einer Zeitleiste anordnen.
- **Einstellungen:** ein **Abfrageintervall**-Regler pro Konto in Minuten, damit eine Automation während der Fahrt öfter abfragen und nachts zurückfahren kann. Es gibt ihn in jedem Setup, auch bei schreibgeschützten Portal-Einträgen.
- **12 Sprachen:** Entitätsnamen sind vollständig übersetzt in Englisch, Deutsch, Französisch, Spanisch, Italienisch, Niederländisch, Polnisch, Tschechisch, Schwedisch, Dänisch, Norwegisch und Finnisch.

> 💡 **Energie-Dashboard:** Der Sensor für geladene Energie ist `total_increasing`, also füge ihn direkt zum Home-Assistant-**Energie-Dashboard** hinzu, oder pack ihn in einen `utility_meter`-Helper für tägliche/monatliche Summen der geladenen Energie. Verwende dafür den kumulativen Sensor **geladene Energie (kWh)** — nicht die Effizienz-Sensoren pro 100 km (das sind Durchschnitte, keine Zähler).

### Services

Die Integration liefert **30+ Service-Calls** (`vag_connect.*`), viele davon markenspezifisch — *Verfügbarkeit hängt von Marke & Modell ab*. Darunter: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi Verbrenner), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (Zusatz-/Standheizung — SEAT/CUPRA, Škoda und VW/Audi über einen Zwei-Wege-Befehlskanal, wo das Auto entsprechend ausgestattet ist), `send_destination` (SEAT/CUPRA/Škoda) und `update_charging_settings` (SEAT/CUPRA), das Škoda-`ask_assistant` (siehe unten), `set_location_target_soc` und `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send` und das `show_vag`-Easter-Egg.

---

## evcc

[evcc](https://evcc.io) kann Ladezustand, Reichweite und Ladestatus deines Autos direkt aus Home Assistant beziehen, damit die Überschussladung mit der echten Batterie plant statt mit einer Schätzung. In der Integration läuft dafür nichts Zusätzliches: evcc liest die REST-API von Home Assistant. Der **Lese**-Pfad funktioniert bei **allen Marken**, auch bei schreibgeschützten VW-EU-/Portal-Autos. Der **Schreib**-Pfad (`chargeEnable`) funktioniert nur bei einem Zwei-Wege-Auto (Audi oder Škoda mit lebendem Befehlskanal) und nur, wenn evcc das Auto selbst als Ladepunkt behandelt. Mit einer echten smarten Wallbox reicht evcc der Lese-Pfad.

Fertige `evcc.yaml`-Rezepte und die einmalige Einrichtung stehen in [docs/EVCC.md](docs/EVCC.md). Dieser Connector ist **Beta**.

---

## ABRP (A Better Routeplanner) Live-Telemetrie

Du kannst die Live-Daten deines Autos an **[A Better Routeplanner](https://abetterrouteplanner.com/)** pushen, damit er rund um deinen echten Ladezustand plant. Es ist **Opt-in und standardmässig aus** — nichts verlässt dein Netzwerk, bis du es einschaltest und tatsächlich ein Upload läuft.

**1. Die zwei Zugangsdaten holen.**

- **`token`** (pro Fahrzeug) — öffne die ABRP-App → **Einstellungen → dein Auto → Live Data → „Generic" / anderes Auto** und kopiere das angezeigte Token.
- **`api_key`** (Entwickler-Key) — das ist ein Partner-/Entwickler-Key, ausgestellt von **iternio**, *nicht* etwas, das die App ausgibt. Fordere einen bei iternio an (deren Entwickler-/API-Key-Anfrageformular). **Wir liefern bewusst keinen Key mit** — einen fest einzucodieren, der uns nicht gehört, wäre Impersonation und würde ein fremdes Secret in ein öffentliches Repo backen. Füge deinen eigenen ein.

**2. Aktivieren.** Integration → **Konfigurieren** → zum **ABRP**-Abschnitt scrollen → *ABRP-Telemetrie-Push aktivieren* anhaken und beide Werte einfügen. Sie werden als Paar validiert (du bekommst einen Fehler, wenn nur einer gesetzt ist), maskiert gespeichert und **nie ins Log geschrieben**.

**3. Den Upload automatisieren.** Importiere das mitgelieferte Blueprint **„ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), wähle dein Fahrzeug und seinen **ABRP data changed**-Sensor, und fertig. Das Blueprint lädt nur hoch, wenn es einen wirklich neuen Snapshot gibt (der *ABRP data changed*-Binärsensor ist der idempotente Trigger — er setzt sich nach jedem erfolgreichen Senden zurück, sodass derselbe Snapshot nie zweimal gesendet wird).

Du kannst auch den Service **`vag_connect.abrp_send`** direkt aufrufen (auf ein Gerät oder eine VIN zielen; api_key/token kommen aus den Optionen, sofern du sie nicht inline übergibst).

> 🔒 **Datenschutz:** Die Telemetrie enthält GPS. Sie verlässt dein Netzwerk nur, wenn `abrp_send` läuft (d. h. wenn *du* es auslöst / das Blueprint aktivierst). Was wir senden: Ladezustand, Ladestatus, GPS, Fahrtrichtung, Energie + Kapazität, geschätzte Reichweite, Umgebungs- + Batterietemperatur, Kilometerstand. Was wir bewusst **nicht** senden: alles, was wir nicht zuverlässig messen können (Geschwindigkeit, HV-Pack-Spannung/-Strom, State-of-Health) — weggelassen statt geraten.

---

## iOS Live Activity — Lade-Countdown auf dem Sperrbildschirm

Eine native **Live Activity** (Sperrbildschirm + Dynamic Island), die zum Ladeende deines Autos herunterzählt, mit einem Fortschrittsbalken für den Ladezustand. Die Integration stellt bereits einen **absoluten** Zeitstempel des Ladeendes bereit (`sensor.*_charge_complete_eta` bei jedem EV), sodass iOS den Countdown von selbst weiterlaufen lassen kann — kein Push im Sekundentakt.

**Importiere das mitgelieferte Blueprint** *„Live Activity — EV charging countdown (iOS)"* (`blueprints/automation/vag_connect/live_activity_charging_countdown.yaml`), wähle die Lade-/SoC-/Ladeende-Sensoren deines Fahrzeugs und den `notify.mobile_app_*`-Service deines Handys. Es startet, wenn das Laden beginnt, aktualisiert sich, während sich ETA und SoC bewegen, und wird gelöscht, wenn das Laden stoppt.

> 📱 **Voraussetzungen:** die Home-Assistant-Companion-App mit aktivierten **Live Activities** (iOS 17.2+, HA Core 2026.7+). Live Activities sind derzeit ein **Labs**-Feature im **TestFlight**-Build der App — aktiviere sie unter Labs. Eine Live Activity braucht einen Token-Handshake zwischen App und Home Assistant, dein Handy muss HA also erreichen können (lokal oder über eine Remote-Verbindung), wenn das Laden beginnt. Das wird jetzt schon ausgeliefert, damit du bereit bist, sobald es TestFlight verlässt. **iOS 2026.8 bringt iPad-Unterstützung und eine überarbeitete Live Activity — dasselbe Blueprint steuert beide.**

---

## Škoda-KI-Assistentin („Laura") — neu in 3.0.0

MyŠkodas eigene Bordassistentin **Laura** ist in Home Assistant verfügbar.
Frag sie mit dem Service `vag_connect.ask_assistant` nach Reichweite, Laden
und Fahrten (sie gibt eine Textantwort zurück, die du per Benachrichtigung
ausgeben, vorlesen oder als Verzweigung nutzen kannst), oder übergib sie an
einen **Conversation-Agent** — das eingebaute Assist im LLM-Modus, oder
OpenAI / Anthropic / Google / Ollama — als Werkzeug, das er aufrufen und
verketten kann (frag Laura → dann `send_destination` ans Auto). Sie ist
**schreibgeschützt, beratend und nur für Škoda**; es ist eine **Beta**,
Feedback zur Antwortqualität ist also willkommen.

Einrichtung, der Sprach-Trigger („frag Laura …") und fertige
Beispiel-Automationen — darunter *Auto kommt zu Hause an → nachladen +
vorheizen + Reichweite vorlesen* — stehen in
**[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Optionen (Konfigurieren)

Unter **Einstellungen → Geräte & Dienste → VW Group Connect → Konfigurieren** kannst du anpassen:
Scan-Intervall (auch live als Abfrageintervall-Regler verfügbar), S-PIN (plus eine S-PIN pro Fahrzeug, wenn im Konto mehr als ein Auto hängt), Reverse-Geocoding, **Schreibgeschützter-Modus**, PPE-Klima erzwingen (Audi), Push-Schalter (MQTT/FCM/Audi-VW, alle Opt-in-Beta und standardmässig aus), Client-ID-Override, **`eu_data_act_auto_kickoff`** (standardmässig an), leere Entitäten ausblenden (standardmässig an), **ABRP** (aktivieren + api_key + User-Token, als Paar validiert), sowie die ergänzenden Lesekanäle **hinzufügen / entfernen**: `volkswagen.de` (Beta), EU-Data-Act-Portal, **Tibber** und den experimentellen **Companion-Handy**-Kanal.

---

## Dieses Projekt unterstützen ❤️

Das ist ein Ein-Personen-Projekt — und VW macht es einem nicht leicht: Jede Backend-Änderung bedeutet Tage Reverse-Engineering, um wieder einen funktionierenden Pfad zu finden. Diese Hartnäckigkeit hält es dort am Leben, wo etablierte Projekte aufgegeben haben. Wenn es dir etwas wert ist, kannst du die laufende Wartung über **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)** unterstützen. Danke! 🙏

### Unsere Sponsoren

<!-- SPONSORS:START -->
Be the first public sponsor to show up here, and thank you either way!
<!-- SPONSORS:END -->

_Diese Liste wird wöchentlich aktualisiert und zeigt nur Sponsoren, die sich auf GitHub Sponsors für öffentlich entschieden haben. Private Sponsoren werden hier nie namentlich genannt, nur gezählt — und wir danken ihnen genauso._

---

## Community & Support

Wohin du dich wendest, hängt davon ab, was du brauchst:

- **Fragen, Einrichtungshilfe, Dashboard-Beispiele, „ist das normal?"** → [GitHub Discussions](https://github.com/its-me-prash/vwgroup-connect-ha/discussions). Allgemeine Home-Assistant-Fragen, die nicht speziell diese Integration betreffen, sind im [HA Community Forum](https://community.home-assistant.io) besser aufgehoben.
- **Ein Bug, ein Fehler oder ein unbekanntes API-Feld** → öffne ein Issue über [New issue → choose a template](https://github.com/its-me-prash/vwgroup-connect-ha/issues/new/choose). Der **Vehicle Data Scout** füllt den Grossteil des Reports für dich vor. Ein nützlicher Report nennt deine Marke, Region, Home-Assistant- + Integrations-Version und ob dieselbe Aktion in der offiziellen App des Herstellers funktioniert — die kurze Checkliste steht in [`CONTRIBUTING.md`](CONTRIBUTING.md); wie ein Report von der Meldung bis zum Fix wandert, steht in [`docs/TRIAGE.md`](docs/TRIAGE.md).
- **Eine Sicherheitslücke** → bitte **kein** öffentliches Issue öffnen. Melde sie privat über [GitHub Security Advisories](https://github.com/its-me-prash/vwgroup-connect-ha/security/advisories/new); der Ablauf steht in [`SECURITY.md`](SECURITY.md).

### Was dich erwartet

Das ist ein Ein-Personen-Projekt, in der Freizeit gepflegt. Antworten erfolgen **nach bestem Bemühen** — mal am selben Tag, mal langsamer, wenn VW etwas kaputt macht und ein Fix sich vordrängelt. Es gibt kein SLA, und es wird keines geben. Je konkreter dein Report (bereinigte Logs, geschwärzte Diagnose, genaue Schritte), desto schneller ist er erledigt. Die Hausregel, kurz gefasst: **sei höflich, sei konkret, poste keine Secrets — Patches und Geduld kommen weiter als Forderungen.**

### Wie du helfen kannst

Du musst keinen Code schreiben, um das hier voranzubringen:

- **Gute Bug-Reports einreichen** und geschwärzte Diagnose anhängen — ein Scout-Download ist oft alles, was man braucht, um ein neues Feld zu mappen.
- **An einem echten Auto testen.** Mehrere Marken sind implementiert, warten aber auf die erste Live-Bestätigung — siehe die [Live-Tester-Liste](CONTRIBUTING.md#live-testers-wanted).
- **Übersetzungen verbessern.** Entitätsnamen werden in 12 Sprachen ausgeliefert; Korrekturen und Hilfe bei einer neuen Sprache sind willkommen.
- **Einen Patch schicken.** Ein PR, ein Anliegen — siehe [`CONTRIBUTING.md`](CONTRIBUTING.md).

Alle, die helfen, werden in [`CONTRIBUTORS.md`](CONTRIBUTORS.md) genannt und in den Release-Notes namentlich gedankt. Wie Entscheidungen getroffen werden — und wer bei einem Ein-Maintainer-Projekt das letzte Wort hat — steht in [`GOVERNANCE.md`](GOVERNANCE.md); die Grundregeln fürs Mitmachen stehen in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

---

## Mitwirken

PRs willkommen, siehe [`CONTRIBUTING.md`](CONTRIBUTING.md). Häufige Fragen beantwortet [docs/FAQ.md](docs/FAQ.md). Der **Vehicle Data Scout** verwandelt unbekannte API-Felder in einen Ein-Klick-, vorausgefüllten Bug-Report, sodass du die Abdeckung verbessern helfen kannst, ohne Code zu lesen.

## Lizenz

[GNU AGPL v3.0-or-later](LICENSE) für den Integrationscode. Verpflichtende Attribution + Namens-/Marken-Bedingungen bei Nutzung/Fork: siehe [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream-Open-Source-Attributionen in [`NOTICE.md`](NOTICE.md).
