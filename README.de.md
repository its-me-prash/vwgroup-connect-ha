<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Eine Home-Assistant-Integration für die Marken des Volkswagen-Konzerns — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Kanada · Bentley</strong><br>
  <em>Direkter API-Zugriff, mehrkanalig mit automatischem Fallback, keine Middleware.</em>
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

**VW Group Connect ist eine [Home Assistant](https://www.home-assistant.io)-Integration, die Connected-Car-Daten und -Steuerung der Volkswagen-Konzernmarken — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Kanada und Bentley — aus einem einzigen Konfigurationseintrag in dein Smart Home bringt.**

Sie zeigt Batterie- & Ladezustand, Reichweite, Kilometerstand, Klima, Türen & Fenster, Standort und mehr — und sendet, wo das Backend der Marke es noch erlaubt, Fernbefehle wie Ver-/Entriegeln, Klima- und Ladesteuerung. Um durch Volkswagens API-Änderungen von 2026 hindurch weiter zu funktionieren, spricht sie **mehrere Kanäle und fällt automatisch zurück**, wenn einer blockiert ist: die markeneigenen Backends, das schreibgeschützte **EU Data Act**-Fahrzeugdaten-Portal, einen optionalen `volkswagen.de`-Webkanal und ein dauerhaftes **passwortloses** Login für ältere Car-Net-Fahrzeuge. Sie läuft problemlos **parallel zu [evcc](https://evcc.io)** und braucht **null PyPI-Abhängigkeiten**.

> 🎉 **Jetzt direkt in HACS verfügbar** — kein Custom-Repository nötig.

---

## Highlights

- **8 wählbare Volkswagen-Konzernmarken** in einer Integration — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Kanada, Porsche und Bentley.
- **Porsche-fähig** — Porsche läuft über sein eigenes *Porsche Connect*-Backend, **nicht** über das EU-Data-Act-Portal. Der Portal-Pfad schliesst Porsche strukturell *aus*, also können Portal-only-Tools es niemals abdecken; diese Integration schon.
- **Zwei-Wege-Steuerung, wo das Backend der Marke es zulässt** — Ver-/Entriegeln, Klima, Laden, Ziel-SoC. Welche Marken echte Befehlsunterstützung haben, steht in der Tabelle unten; VW EU ist standardmässig schreibgeschützt (siehe den ehrlichen Hinweis dort).
- **Passwortlose Login-Option** (Browser/Device-Code) für Audi/Škoda/SEAT/CUPRA — kein Passwort in Home Assistant gespeichert.
- **Mehrkanalig mit Auto-Fallback** — markeneigen → EU-Data-Act-Portal → optionales vw.de-Web → dauerhaftes Car-Net. Fällt ein Kanal aus, gehen deine Daten nicht dunkel.
- **Resilient by Design** — behält letzte bekannte Werte durch Portal-Ausfälle hindurch, filtert falsche „keine Messung"-Platzhalter, lässt den Kilometerstand nie rückwärts springen.
- **GPS-Device-Tracker**, 100+ Entitäten über mehrere Plattformen, 20+ Service-Calls, mehrere Fahrzeuge pro Konto.
- **Vehicle Data Scout** — erkennt API-Drift automatisch und bietet einen Ein-Klick-Bug-Report an. **Quality Scale: Platinum.**

---

## Markenstatus

| Marke | Steuerung | Daten | Hinweise |
|---|---|---|---|
| **Audi** | ✅ Zwei-Wege | ✅ Voll | myAudi-Backend (inkl. Verbrenner-Motorstart/-stopp) |
| **Škoda** | ✅ Zwei-Wege | ✅ Voll | natives Škoda-Backend |
| **Porsche** | ✅ Zwei-Wege | ✅ Voll | Porsche Connect — eigenes Backend, nicht das EU-Data-Act-Portal |
| **VW US/CA** | ✅ Zwei-Wege | ✅ Voll | VW-NA-Cloud (braucht den US/CA-Länderwähler + S-PIN) |
| **VW EU** | 🔒 Standardmässig schreibgeschützt · ⚠️ Befehle = MBB **Alpha** | ✅ Volle Telemetrie via EU-Data-Act-Portal | Siehe den ehrlichen Hinweis unten — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Befehle von VW blockiert | ✅ EU-Data-Act-Portal | OLA-Zugriff 2026 serverseitig entzogen — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Zwei-Wege durch Live-Test gegated | ✅ Login + Lesen | My Bentley — läuft auf dem Audi/IDK-Tenant |

> **Ehrlicher Hinweis zur VW-EU-Steuerung.** Volkswagen-EU-Fahrzeuge sind **standardmässig schreibgeschützt**: Du bekommst volle Telemetrie über das EU-Data-Act-Portal, aber keine Fernbefehle. Fernbefehle für VW EU existieren **nur als experimentelle dauerhafte MBB-Zwei-Wege-ALPHA** und nur für **Legacy-MQB-/Car-Net**-Autos — es ist ein Opt-in-Schalter, **kein** Standardfeature. **MEB-/ID-Familien-Autos (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) haben gar keinen Befehlspfad** und werden schreibgeschützt angelegt. Die MBB-Alpha wird in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** verfolgt — Tester:innen willkommen.

> 2026 hat Volkswagen Teile seiner API hinter Device-Attestation gestellt. Diese Integration umgeht das, wo möglich (dauerhaftes Car-Net-Login, EU-Data-Act-Portal, vw.de-Web), und ist transparent darüber, was jeder Kanal kann und nicht kann.

---

## Bekannte Einschränkungen

Ein paar Dinge sind **strukturell** — sie kommen daher, wie Volkswagens Backends 2026 funktionieren, nicht von der Integration, und keine Einstellung behebt sie:

- **VW EU ist standardmässig schreibgeschützt; Befehle sind eine MBB-Alpha, nur für Legacy-Autos.** Siehe den Markenhinweis oben. **MEB-/ID-Familien-Autos sind schreibgeschützt** — der dauerhafte Car-Net-Befehlspfad erkennt sie nicht (er antwortet „Unknown user"), und VWs MEB-Backend bietet kein Äquivalent. Das Setup erkennt das und legt einen **schreibgeschützten Eintrag** an (mit Reparatur-Hinweis), statt zu scheitern — es ist also eine bekannte Grenze, keine stille. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **CUPRA-/SEAT-Fernbefehle werden von VW blockiert.** Der Online-Services-Zugriff (OLA) für diese Marken wurde 2026 serverseitig entzogen (HTTP 403); ein erneutes Login oder ein App-Versions-Bump stellt ihn nicht wieder her. Daten fliessen weiterhin über das EU-Data-Act-Portal. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Die EU-Data-Act-Portaldaten sind dünn und variieren je nach Auto.** VW veröffentlicht heute nur einen Ausschnitt der Felder (oft Kilometerstand + Verriegelung + Laden, manchmal deutlich mehr). Er weitet sich mit der Zeit, während VW das Portal vor der Frist im September 2026 ausbaut — Felder, die heute `unknown` zeigen, füllen sich womöglich von selbst, ohne Änderung. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

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

- **Browser / Device-Code (passwortlos)** — *Audi · Škoda · SEAT · CUPRA.* Melde dich auf deinem Handy oder Laptop an und bestätige das Gerät; kein Passwort wird in Home Assistant gespeichert (es behält ein echtes Refresh-Token). Dieser Schritt bietet zusätzlich die optionale **S-PIN** und das Scan-Intervall.
- **Portal — E-Mail + Passwort** — *Volkswagen EU · Porsche.* Gib dein Marken-Login ein. Dieser Schritt zeigt einen Markenwähler (Volkswagen EU, Porsche und die anderen E-Mail/Passwort-Marken), E-Mail, Passwort, optionale **S-PIN**, Scan-Intervall und einen **„MBB-Befehle aktivieren"**-Schalter (der nur bei Volkswagen EU wirkt — siehe [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Für **Volkswagen US/Kanada** erscheint hier ein **Länderwähler (US vs. CA)** — er wird **nur** für diese Marke angezeigt und von keiner anderen genutzt.

> Das **EU-Data-Act-Portal ist kein dritter Login-Button.** Es ist die schreibgeschützte Strategie, auf die der Koordinator automatisch zurückfällt, und es kann zusätzlich als ergänzender Lesekanal über **Konfigurieren → Optionen** *hinzugefügt* werden. Dasselbe gilt für den `volkswagen.de`-Webkanal (ein optionaler, nur über die Optionen verfügbarer ergänzender Lesekanal).

### Das S-PIN-Feld — wann du es brauchst

Die **S-PIN** ist die Sicherheits-PIN deiner Marken-App. Sie ist im Formular optional und nur für manche Aktionen nötig: gebraucht wird sie für **Datenlesungen und Befehle bei VW US/Kanada** und für sicherheitskritische Fernbefehle bei Marken, die sie hinter der S-PIN absichern. Lass sie leer, wenn dein Auto keine verlangt.

---

### Volkswagen EU — deine Daten zum Fliessen bringen (wichtig)

Bei Volkswagen EU reicht **Einloggen nicht** — VW streamt Fahrzeugdaten erst, wenn *du* auf VWs Seite die Datenfreigabe eingeschaltet hast. Falls dein Auto ohne Daten auftaucht (oder gar nicht erscheint), ist das fast immer der Grund, **nicht** ein falsches Passwort. Mach das einmal:

1. **Integration hinzufügen:** Wähle **Portal (E-Mail + Passwort)** und **Volkswagen EU**, dann einloggen.
2. **Erledige eine etwaige einmalige Abfrage auf VWs Portal.** Öffne das VW-Datenportal einmal im Browser oder in der Marken-App und schliess ab, was es verlangt: **Bedingungen akzeptieren, Einwilligung bestätigen, Onboarding / Regionsauswahl abschliessen.** Headless-Zugriff kommt an diesen nicht vorbei — das ist der Fall `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Datenfreigabe-Einwilligung erteilen.** Setze im Portal **„Nutzung nicht-personenbezogener Daten" = Erteilt** (die EU-Data-Act-Datenfreigabe-Einwilligung).
4. **Such nicht nach einem Schalter für die „kontinuierliche Datenanfrage" — den gibt es nicht.** Die Integration legt diese Anfrage für jedes Auto selbst an. Sie registriert dafür ein 1-Monats-Abo auf deinem VW-Konto, das **kostenlos** ist. Ohne Anfrage liefert das Portal für diese VIN nichts, und das Fahrzeug erscheint ohne Messwerte.
5. **Warte, bis das Auto einen Snapshot pusht.** Selbst nach all dem braucht die Propagierung Zeit. Das Auto kann **eine Weile `offline` / `unknown` anzeigen — oft bis zur nächsten Fahrt oder zum nächsten Aufwachen, bis zu ~24 h** — bevor sich die Sensoren füllen. Das ist normal.

Das Portal liefert anfangs nur einen **Ausschnitt der Felder**, und dieser Ausschnitt **weitet sich mit der Zeit**, während VW die Portalabdeckung vor der Frist im September 2026 ausbaut — Felder, die heute `unknown` zeigen, füllen sich womöglich von selbst. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> Der Optionen-Schalter **`eu_data_act_auto_kickoff`** ist das, was die 15-Minuten-Custom-Data-Request anlegt, und er ist **standardmässig an** — im Portal-Modus gibt es ohne sie keine Daten. Schalte ihn nur aus, wenn du die Anfrage lieber selbst verwalten willst.

---

## Was du bekommst

- **Sensoren:** Batterie-SoC, Reichweite (elektrisch / Verbrenner / gesamt), Tankfüllstand, Kilometerstand, Temperaturen, Ladeleistung/-rate/-typ, Ladeziel, Trip-Statistiken & Lebensdauer-Aggregate, Service- & Ölservice-Intervalle, Softwareversion, Verbindungszustand, zuletzt gesehen und mehr.
- **Binärsensoren:** Türen verriegelt, Türen/Fenster/Kofferraum/Haube/Schiebedach offen, Stecker verbunden, Laden, OTA-Update verfügbar, Lichter, Fahrzeug online, Abfahrtszeiten, Alarm.
- **Steuerung:** Ver-/Entriegeln, Klima Start/Stopp, Laden Start/Stopp, Scheibenheizung, Abfahrtszeiten, Ziel-SoC / Temperatur / max. Ladestrom setzen, Hupen-und-Blinken, Aufwecken, Aktualisieren, Ladestationen finden *(Verfügbarkeit hängt von Marke & Modell ab)*.
- **Device-Tracker:** GPS-Position für die Home-Assistant-Karte.
- **Bilder:** Fahrzeug-Renderings, wo die Marke sie bereitstellt.

> 💡 **Energie-Dashboard:** Der Sensor für geladene Energie ist `total_increasing`, also füge ihn direkt zum Home-Assistant-**Energie-Dashboard** hinzu, oder pack ihn in einen `utility_meter`-Helper für tägliche/monatliche Summen der geladenen Energie. Verwende dafür den kumulativen Sensor **geladene Energie (kWh)** — nicht die Effizienz-Sensoren pro 100 km (das sind Durchschnitte, keine Zähler).

### Services

Die Integration liefert **20+ Service-Calls** (`vag_connect.*`), viele davon markenspezifisch — *Verfügbarkeit hängt von Marke & Modell ab*. Darunter: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi Verbrenner), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` und `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` und das `show_vag`-Easter-Egg.

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

## Optionen (Konfigurieren)

Unter **Einstellungen → Geräte & Dienste → VW Group Connect → Konfigurieren** kannst du anpassen:
Scan-Intervall, S-PIN (plus eine S-PIN pro Fahrzeug, wenn im Konto mehr als ein Auto hängt), Reverse-Geocoding, **Schreibgeschützter-Modus**, PPE-Klima erzwingen (Audi), Push-Schalter (MQTT/FCM/Audi-VW), Client-ID-Override, **`eu_data_act_auto_kickoff`** (standardmässig an), leere Entitäten ausblenden (standardmässig an), **ABRP** (aktivieren + api_key + User-Token, als Paar validiert), sowie die ergänzenden Lesekanäle `volkswagen.de` und EU-Data-Act-Portal **hinzufügen / entfernen**.

---

## Dieses Projekt unterstützen ❤️

Das ist ein Ein-Personen-Projekt — und VW macht es einem nicht leicht: Jede Backend-Änderung bedeutet Tage Reverse-Engineering, um wieder einen funktionierenden Pfad zu finden. Diese Hartnäckigkeit hält es dort am Leben, wo etablierte Projekte aufgegeben haben. Wenn es dir etwas wert ist, kannst du die laufende Wartung über **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)** unterstützen. Danke! 🙏

---

## Mitwirken

PRs willkommen — siehe [`CONTRIBUTING.md`](CONTRIBUTING.md). Der **Vehicle Data Scout** verwandelt unbekannte API-Felder in einen Ein-Klick-, vorausgefüllten Bug-Report, sodass du die Abdeckung verbessern helfen kannst, ohne Code zu lesen.

## Lizenz

[GNU AGPL v3.0-or-later](LICENSE) für den Integrationscode. Verpflichtende Attribution + Namens-/Marken-Bedingungen bei Nutzung/Fork: siehe [`ATTRIBUTION.md`](ATTRIBUTION.md). Upstream-Open-Source-Attributionen in [`NOTICE.md`](NOTICE.md).
