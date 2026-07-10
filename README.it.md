<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Un'unica integrazione Home Assistant per le marche del gruppo Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada · Bentley</strong><br>
  <em>Accesso diretto alle API, multicanale con fallback automatico, nessun middleware.</em>
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

> ### 📛 Nota sulla rinominazione
> Precedentemente pubblicato come **`vag-connect-ha`** (VAG = Volkswagen AG, abbreviazione standard nell'area DACH).
> Si è scoperto che quell'abbreviazione si legge in modo *piuttosto* diverso per chi parla inglese 😅
>
> **Cosa continua a funzionare come prima**: tutte le entità (ad es. `sensor.audi_q4_battery_soc`),
> tutti i service-call (`vag_connect.lock`, `vag_connect.show_vag` ecc.), tutte le automazioni,
> l'installazione HACS — **niente si rompe**. Cambia il nome di marketing/visualizzazione,
> l'interno del codice resta invariato. Vedi [`MIGRATION.md`](MIGRATION.md).
>
> Un enorme grazie alle community **Home Assistant UK** e **HA Ideas, Projects and Solutions**
> per la segnalazione — in particolare a **Si Gregory**, **Ben Johnson** ed **Evets David**.
>
> E un ringraziamento speciale a **Jordan Waeles**, il cui commento `show_vag()` è ora un easter egg
> ufficialmente supportato in questa integrazione (servizio `vag_connect.show_vag`, vedi CHANGELOG v2.2.3).

---

## Che cos'è?

**VW Group Connect è un'integrazione [Home Assistant](https://www.home-assistant.io) che porta i dati e il controllo dell'auto connessa nella tua smart home per le marche del gruppo Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/Canada e Bentley — da un'unica voce di configurazione.**

Mostra stato di batteria e ricarica, autonomia, contachilometri, clima, porte e finestrini, posizione e altro ancora, e — dove il backend della marca lo consente ancora — invia comandi remoti come chiusura/apertura, controllo del clima e della ricarica. Per continuare a funzionare attraverso le modifiche alle API di Volkswagen del 2026, parla **diversi canali e ripiega automaticamente** quando uno è bloccato: i backend nativi delle marche, il portale dei dati del veicolo **EU Data Act** in sola lettura, un canale web `volkswagen.de` opt-in e un login **senza password** duraturo per i veicoli Car-Net più vecchi. Gira tranquillamente **accanto a [evcc](https://evcc.io)** e non richiede **alcuna dipendenza PyPI**.

> 🎉 **Ora disponibile direttamente in HACS** — nessun repository personalizzato necessario.

---

## In evidenza

- **8 marche del gruppo Volkswagen selezionabili** in un'unica integrazione — Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Porsche e Bentley.
- **Compatibile con Porsche** — Porsche viaggia sul proprio backend *Porsche Connect*, **non** sul portale EU Data Act. Il percorso del portale *esclude* strutturalmente Porsche, quindi gli strumenti basati solo sul portale non potranno mai coprirlo; questa integrazione sì.
- **Controllo bidirezionale dove il backend della marca lo consente** — chiusura/apertura, clima, ricarica, SoC obiettivo. Leggi quali marche hanno un vero supporto ai comandi nella tabella qui sotto; VW EU è in sola lettura per impostazione predefinita (vedi la nota onesta lì).
- **Opzione di login senza password** (browser/device-code) per Audi/Škoda/SEAT/CUPRA — nessuna password salvata in Home Assistant.
- **Multicanale con fallback automatico** — nativo della marca → portale EU Data Act → web vw.de opt-in → Car-Net duraturo. Se un canale va giù, i tuoi dati non restano al buio.
- **Resiliente per progettazione** — mantiene gli ultimi valori noti durante le interruzioni del portale, filtra i falsi segnaposto "nessuna lettura", non lascia mai che il contachilometri salti all'indietro.
- **Device tracker GPS**, oltre 100 entità su più piattaforme, oltre 20 service-call, più veicoli per account.
- **Vehicle Data Scout** — rileva automaticamente il drift delle API e offre una segnalazione di bug con un clic. **Quality Scale: Platinum.**

---

## Stato delle marche

| Marca | Controllo | Dati | Note |
|---|---|---|---|
| **Audi** | ✅ Bidirezionale | ✅ Completo | backend myAudi (incl. avvio/arresto motore termico) |
| **Škoda** | ✅ Bidirezionale | ✅ Completo | backend nativo Škoda |
| **Porsche** | ✅ Bidirezionale | ✅ Completo | Porsche Connect — backend proprio, non il portale EU Data Act |
| **VW US/CA** | ✅ Bidirezionale | ✅ Completo | cloud VW NA (richiede il selettore di paese US/CA + S-PIN) |
| **VW EU** | 🔒 In sola lettura per impostazione predefinita · ⚠️ comandi = MBB **alpha** | ✅ Telemetria completa via portale EU Data Act | Vedi la nota onesta qui sotto — [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584) |
| **CUPRA / SEAT** | ⛔ Comandi bloccati da VW | ✅ Portale EU Data Act | Accesso OLA revocato lato server nel 2026 — [#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464) |
| **Bentley** | ⏳ Bidirezionale subordinato a test dal vivo | ✅ Login + lettura | My Bentley — gira sul tenant Audi/IDK |

> **Nota onesta sul controllo VW EU.** I veicoli Volkswagen EU sono **in sola lettura per impostazione predefinita**: ottieni la telemetria completa attraverso il portale EU Data Act, ma nessun comando remoto. I comandi remoti per VW EU esistono **solo come ALPHA bidirezionale sperimentale con MBB duraturo**, e solo per le auto **legacy MQB / Car-Net** — è un'opzione opt-in, **non** una funzione predefinita. **Le auto della famiglia MEB / ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) non hanno alcun percorso per i comandi** e vengono create in sola lettura. L'alpha MBB è tracciata in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — tester benvenuti.

> Nel 2026 Volkswagen ha messo parti delle sue API dietro l'attestazione del dispositivo. Questa integrazione le aggira dove possibile (login Car-Net duraturo, portale EU Data Act, web vw.de) ed è trasparente su ciò che ogni canale può e non può fare.

---

## Limitazioni note

Alcune cose sono **strutturali** — derivano da come funzionano i backend di Volkswagen nel 2026, non dall'integrazione, e nessuna impostazione le risolve:

- **VW EU è in sola lettura per impostazione predefinita; i comandi sono un'alpha MBB solo per le auto legacy.** Vedi la nota sulla marca qui sopra. **Le auto della famiglia MEB / ID sono in sola lettura** — il percorso duraturo dei comandi Car-Net non le riconosce (risponde "Unknown user") e il backend MEB di VW non espone alcun equivalente. La configurazione lo rileva e crea una **voce in sola lettura** (con un avviso di riparazione) invece di fallire, quindi è un limite noto, non silenzioso. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **I comandi remoti CUPRA / SEAT sono bloccati da VW.** L'accesso ai servizi online (OLA) per queste marche è stato revocato lato server nel 2026 (HTTP 403); un nuovo login o un aggiornamento della versione dell'app non lo ripristina. I dati continuano a fluire tramite il portale EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **I dati del portale EU Data Act sono scarni e variano da auto ad auto.** VW pubblica oggi solo una fetta dei campi (spesso contachilometri + chiusura + ricarica, a volte molto di più). Si amplia nel tempo man mano che VW espande il portale in vista della scadenza di settembre 2026 — i campi che oggi leggono `unknown` potrebbero riempirsi da soli, senza alcuna modifica. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

> **Dove ci troviamo.** Ai sensi dell'EU Data Act (Regolamento (UE) 2023/2854), i dati della tua auto sono *tuoi*. Eseguire questa integrazione sul tuo hardware significa che *tu* accedi ai *tuoi stessi* dati (Articolo 4) — dovuti alla stessa qualità con cui il produttore li serve a se stesso, in tempo reale dove tecnicamente fattibile. Il portale di VW in sola lettura, vecchio di ore, oggi non è all'altezza. Questa integrazione è deliberatamente **agnostica rispetto al canale**: nel momento in cui VW darà ai proprietari un'interfaccia in tempo reale, capace di controllo — come richiede il Data Act, e come alcuni produttori già offrono ai loro proprietari — la supporteremo qui, gratuitamente, per tutti. Sosteniamo il tuo diritto all'accesso in tempo reale alla tua stessa auto.

---

## Installazione

**Tramite HACS (consigliato):**

1. Apri **HACS** in Home Assistant.
2. Cerca **"VW Group Connect"** e installalo.
3. Riavvia Home Assistant.
4. Vai su **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → VW Group Connect** e segui la procedura di login.

<sup>Appena inserito nel default di HACS — se non è ancora ricercabile, concedi all'indice HACS un po' di tempo per aggiornarsi, oppure nel frattempo aggiungi `its-me-prash/vwgroup-connect-ha` come repository personalizzato.</sup>

**Home Assistant minimo: `2024.4.0`.**

### Opzioni di login (la procedura di configurazione ha due percorsi)

La prima schermata dell'integrazione offre **due** metodi di login. Scegli quello che la tua marca supporta:

- **Browser / device-code (senza password)** — *Audi · Škoda · SEAT · CUPRA.* Accedi sul telefono o sul laptop e approva il dispositivo; nessuna password viene salvata in Home Assistant (mantiene un vero refresh token). Questo passaggio offre anche i campi opzionali **S-PIN**, intervallo di scansione e force-access.
- **Portale — email + password** — *Volkswagen EU · Porsche.* Inserisci il login della tua marca. Questo passaggio espone un selettore di marca (Volkswagen EU, Porsche e le altre marche email/password), email, password, **S-PIN** opzionale, intervallo di scansione, force-access e un'opzione **"abilita i comandi MBB"** (che ha effetto solo su Volkswagen EU — vedi [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Per **Volkswagen US/Canada** qui appare un **selettore di paese (US vs CA)** — viene visualizzato **solo** per quella marca e non è usato da nessun'altra.

> Il **portale EU Data Act non è un terzo pulsante di login.** È la strategia in sola lettura su cui il coordinatore ripiega automaticamente, e può inoltre essere *aggiunto* come canale di lettura supplementare da **Configura → Opzioni**. Lo stesso vale per il canale web `volkswagen.de` (un canale di lettura supplementare opt-in, disponibile solo dalle Opzioni).

### Il campo S-PIN — quando serve

L'**S-PIN** è il PIN di sicurezza dell'app della tua marca. È opzionale nel modulo e richiesto solo per alcune azioni: serve per le **letture dei dati e i comandi di VW US/Canada**, e per i comandi remoti sensibili dal punto di vista della sicurezza sulle marche che li proteggono dietro l'S-PIN. Lascialo vuoto se la tua auto non ne richiede uno.

---

### Volkswagen EU — far fluire i tuoi dati (importante)

Per Volkswagen EU, **accedere non basta** — VW trasmette i dati del veicolo solo dopo che *tu* hai attivato la condivisione dei dati sul lato VW. Se la tua auto compare senza dati (o non compare affatto), questo è quasi sempre il motivo, **non** una password errata. Fai questo una volta:

1. **Aggiungi l'integrazione:** scegli **Portale (email + password)** e seleziona **Volkswagen EU**, poi accedi.
2. **Completa qualsiasi richiesta una tantum sul portale di VW.** Apri il portale dati di VW una volta in un browser o nell'app della marca e completa ciò che chiede: **accetta i termini, conferma il consenso, completa l'onboarding / la selezione della regione.** L'accesso headless non può superare questi passaggi — è il caso `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Concedi il consenso alla condivisione dei dati.** Sul portale, imposta **"Uso di dati non personali" = Concesso** (il consenso alla condivisione dei dati dell'EU Data Act).
4. **Abilita la richiesta di dati continua** per l'auto specifica. Senza di essa, il portale restituisce *nessuna richiesta dati* per quel VIN e il veicolo compare senza letture.
5. **Attendi che l'auto invii uno snapshot.** Anche dopo tutto quanto sopra, la propagazione richiede tempo. L'auto può leggere **`offline` / `unknown` per un po' — spesso fino alla sua prossima guida o al prossimo risveglio, fino a ~24 h** — prima che i sensori si popolino. È normale.

Il portale inizialmente serve solo una **fetta di campi**, e quella fetta **si amplia nel tempo** man mano che VW espande la copertura del portale in vista della scadenza di settembre 2026 — i campi che oggi leggono `unknown` potrebbero riempirsi da soli. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Facoltativo:** l'opzione **`eu_data_act_auto_kickoff`** può creare automaticamente per te la Custom Data Request a 15 minuti. È opt-in perché crearla implica un **abbonamento di 1 mese sul tuo account VW**, quindi l'integrazione non lo farà senza il tuo consenso.

---

## Cosa ottieni

- **Sensori:** SoC batteria, autonomia (elettrica / termica / totale), livello carburante, contachilometri, temperature, potenza/velocità/tipo di ricarica, obiettivo di ricarica, statistiche di viaggio e aggregati sull'intera vita del veicolo, intervalli di tagliando e cambio olio, versione software, stato della connessione, ultima rilevazione e altro.
- **Sensori binari:** porte chiuse, porte/finestrini/bagagliaio/cofano/tetto apribile aperti, spina collegata, in ricarica, aggiornamento OTA disponibile, luci, veicolo online, timer di partenza, allarme.
- **Controllo:** chiusura/apertura, avvio/arresto clima, avvio/arresto ricarica, riscaldamento vetri, timer di partenza, impostazione di SoC obiettivo / temperatura / corrente di ricarica max, clacson-e-lampeggio, risveglio, aggiornamento, ricerca stazioni di ricarica *(la disponibilità dipende da marca e modello)*.
- **Device tracker:** posizione GPS per la mappa di Home Assistant.
- **Immagini:** render del veicolo dove la marca li fornisce.

> 💡 **Dashboard energia:** il sensore dell'energia caricata è `total_increasing`, quindi aggiungilo direttamente alla **dashboard Energia** di Home Assistant, oppure avvolgilo in un helper `utility_meter` per i totali giornalieri/mensili di energia caricata. Usa a questo scopo il sensore cumulativo **energia caricata (kWh)** — non i sensori di efficienza per 100 km (quelli sono medie, non contatori).

### Servizi

L'integrazione include **oltre 20 service-call** (`vag_connect.*`), molti specifici per marca — *la disponibilità dipende da marca e modello*. Tra questi: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi termico), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (SEAT/CUPRA Webasto), `send_destination` e `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send` e l'easter egg `show_vag`.

---

## Telemetria in tempo reale ABRP (A Better Routeplanner)

Puoi inviare i dati in tempo reale della tua auto ad **[A Better Routeplanner](https://abetterrouteplanner.com/)** così da pianificare in base al tuo reale stato di carica. È **opt-in e disattivato per impostazione predefinita** — nulla lascia la tua rete finché non lo attivi e non viene effettivamente eseguito un caricamento.

**1. Ottieni le due credenziali.**

- **`token`** (per veicolo) — apri l'app ABRP → **Impostazioni → la tua auto → Live Data → "Generic" / altra auto** e copia il token che mostra.
- **`api_key`** (chiave sviluppatore) — è una chiave partner/sviluppatore rilasciata da **iternio**, *non* qualcosa che l'app fornisce. Richiedine una a iternio (il loro modulo di richiesta chiave sviluppatore/API). **Deliberatamente non forniamo una chiave** — codificarne una che non ci appartiene sarebbe impersonificazione e incorporerebbe un segreto non nostro in un repository pubblico. Inserisci la tua.

**2. Abilitala.** Integrazione → **Configura** → scorri fino alla sezione **ABRP** → spunta *Abilita l'invio di telemetria ABRP* e inserisci entrambi i valori. Vengono validati come coppia (otterrai un errore se ne è impostato solo uno), memorizzati mascherati e **mai scritti nel log**.

**3. Automatizza il caricamento.** Importa il blueprint incluso **"ABRP — upload telemetry on data change"** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), scegli il tuo veicolo e il suo sensore **ABRP data changed**, e hai finito. Il blueprint carica solo quando c'è uno snapshot davvero nuovo (il sensore binario *ABRP data changed* è il trigger idempotente — si azzera dopo ogni invio riuscito, così lo stesso snapshot non viene mai inviato due volte).

Puoi anche chiamare direttamente il servizio **`vag_connect.abrp_send`** (punta a un dispositivo o un VIN; api_key/token provengono dalle opzioni a meno che tu non li passi inline).

> 🔒 **Privacy:** la telemetria include il GPS. Lascia la tua rete solo quando `abrp_send` viene eseguito (cioè quando *tu* lo attivi / abiliti il blueprint). Ciò che inviamo: stato di carica, stato di ricarica, GPS, direzione, energia + capacità, autonomia stimata, temperatura ambiente + batteria, contachilometri. Ciò che deliberatamente **non** inviamo: qualsiasi cosa non possiamo misurare in modo affidabile (velocità, tensione/corrente del pacco HV, state-of-health) — omesso anziché indovinato.

---

## Opzioni (Configura)

Da **Impostazioni → Dispositivi e servizi → VW Group Connect → Configura** puoi regolare:
intervallo di scansione, S-PIN, geocodifica inversa, **modalità sola lettura**, forza clima PPE (Audi), opzioni push (MQTT/FCM/Audi-VW), **fallback browser EU Data Act** (Playwright / ~100 MB Chromium, opt-in), **wake-before-poll** + ritardo di risveglio, override client-id, **`eu_data_act_auto_kickoff`**, nascondi entità vuote (attivo per impostazione predefinita), **ABRP** (abilita + api_key + token utente, validati come coppia), oltre ad **aggiungere / rimuovere** i canali di lettura supplementari `volkswagen.de` e portale EU Data Act.

---

## Sostieni questo progetto ❤️

Questo è un progetto di una sola persona — e VW non lo rende facile: ogni modifica al backend significa giorni di reverse engineering per trovare di nuovo un percorso funzionante. È questa tenacia a tenerlo in vita là dove progetti affermati hanno rinunciato. Se per te vale qualcosa, puoi sostenere la manutenzione continua tramite **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Grazie! 🙏

---

## Contribuire

PR benvenute — vedi [`CONTRIBUTING.md`](CONTRIBUTING.md). Il **Vehicle Data Scout** trasforma i campi API sconosciuti in una segnalazione di bug precompilata e con un clic, così puoi contribuire a migliorare la copertura senza leggere il codice.

## Licenza

[GNU AGPL v3.0-or-later](LICENSE) per il codice dell'integrazione. Attribuzione obbligatoria + termini su nome/marchio in caso di uso/fork: vedi [`ATTRIBUTION.md`](ATTRIBUTION.md). Attribuzioni open source upstream in [`NOTICE.md`](NOTICE.md).
