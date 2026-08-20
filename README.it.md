<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Un'unica integrazione Home Assistant per le auto del gruppo Volkswagen: Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW e Audi USA/Canada</strong><br>
  <em>Batteria, ricarica, autonomia, porte, clima e posizione GPS in Home Assistant. Accesso diretto alle API, più canali di lettura con ripiego automatico, senza middleware.</em>
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

**VW Group Connect è un'integrazione [Home Assistant](https://www.home-assistant.io) che porta la tua auto del gruppo Volkswagen nella smart home: stato di batteria e ricarica, autonomia, contachilometri, clima, porte e finestrini, posizione GPS e altro, per Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley e gli account nordamericani VW / Audi, tutto da un'unica voce di configurazione.**

Dove il backend della marca lo consente ancora, invia anche comandi a distanza come blocco/sblocco, controllo del clima e della ricarica. **Questo dipende dalla marca, non è universale:** Audi e Škoda sono bidirezionali, Volkswagen EU sul portale EU Data Act è in sola lettura, e i comandi SEAT/CUPRA sono bloccati dal costruttore. La tabella qui sotto dice esattamente cosa vale dove.

Per continuare a funzionare attraverso i cambi di API di Volkswagen del 2026 parla **più canali di lettura e ripiega automaticamente** quando uno è bloccato: i backend nativi delle marche, il portale dati veicolo **EU Data Act** in sola lettura, un canale web `volkswagen.de` opzionale (beta), un riempimento opzionale via **Tibber** e un accesso **senza password** duraturo per le vetture Car-Net più vecchie. Gira tranquillamente **accanto a [evcc](https://evcc.io)** (vedi [docs/EVCC.md](docs/EVCC.md)) e non richiede **nessun add-on, broker o container intermedio**. Home Assistant installa automaticamente due piccoli pacchetti Python; sono usati solo dai canali push opzionali.

> 🎉 **Ora disponibile direttamente in HACS** — nessun repository personalizzato necessario.

---

## In evidenza

- **9 marche del gruppo Volkswagen selezionabili** in un'unica integrazione: Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW USA/Canada, Audi USA/Canada, Porsche e Bentley.
- **Controllo bidirezionale dove il backend della marca lo permette**: blocco/sblocco, clima, ricarica, SoC obiettivo. È **per marca, non universale**. Guarda la tabella qui sotto prima di contare su un comando.
- **L'assistente di bordo di Škoda «Laura» in Home Assistant (novità della 3.0.0)**: chiedile di autonomia, ricarica e viaggi come servizio, oppure affidala a un qualsiasi agente conversazionale (l'Assist integrato, OpenAI, Anthropic, Google, Ollama) come strumento che può richiamare e concatenare. Consigli in sola lettura su cui le tue automazioni possono agire.
- **Accesso senza password** (browser/device-code) per Audi, Škoda, SEAT, CUPRA e Audi USA/CA. In Home Assistant non viene salvata nessuna password.
- **Multicanale con ripiego automatico**: backend nativo della marca, portale EU Data Act, web vw.de opzionale, Tibber opzionale, Car-Net duraturo. Se un canale cade, i tuoi dati non si spengono.
- **Canale companion (sperimentale, opzionale)**: quando ogni via verso i backend è chiusa, l'integrazione può leggere la tua auto pilotando l'app ufficiale su un telefono Android di scorta tramite ADB. Volkswagen è verificata su un dispositivo reale; le altre marche restano in sola lettura finché non viene confermata una mappa delle schermate. I telefoni moderni richiedono l'[add-on ADB Bridge](https://github.com/its-me-prash/vwgroup-app-adb-bridge); non viene fatto alcun root e non viene letto nessun token dell'app.
- **Resiliente per progetto**: conserva gli ultimi valori noti e l'ultima posizione di parcheggio nota attraverso i disservizi del portale, filtra le false sentinelle «nessuna lettura», non lascia mai tornare indietro il contachilometri e ti dice quando un accesso fallito è un disservizio del costruttore e non la tua password.
- **Il ritmo di interrogazione lo decidi tu**: un **cursore dell'intervallo di interrogazione** per account (un'entità Number, in minuti) pilotabile dalle automazioni, creato in ogni installazione, comprese quelle in sola lettura via portale.
- **Device tracker GPS**, oltre 100 entità su più piattaforme, oltre 30 chiamate di servizio, più veicoli per account, nomi delle entità in **12 lingue**.
- **Porsche gira sul proprio backend**, non sul portale EU Data Act. La via del portale *esclude* strutturalmente Porsche, quindi gli strumenti basati solo sul portale non potranno mai coprirla. Il codice dei comandi è qui, ma l'accesso Porsche in sé è al momento sperimentale (vedi la tabella).
- **Vehicle Data Scout** rileva automaticamente le derive delle API e propone una segnalazione di bug con un clic — e dalla 3.0.0 il suo download diagnostico oscurato include anche le risposte grezze delle API, così un unico allegato è tutto ciò che serve per aggiungere il supporto a un nuovo campo. **Quality Scale: Platinum.**

---

## Stato delle marche

| Marca | Controllo | Dati | Note |
|---|---|---|---|
| **Audi** (EU) | ✅ Bidirezionale | ✅ Completo | backend myAudi (incl. avvio/arresto motore termico) |
| **Škoda** | ✅ Bidirezionale | ✅ Completo | backend nativo Škoda |
| **VW USA/CA** | ✅ Bidirezionale | ✅ Completo | cloud VW NA (richiede il selettore di paese USA/CA + S-PIN). Ora il Canada accede sul proprio server con il proprio client dell'app e mostra dati completi, confermato su una ID.4 canadese reale ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)) |
| **VW EU** | 🔒 Sola lettura per impostazione predefinita · ⚠️ comandi = MBB **alpha** | ✅ Telemetria completa via portale EU Data Act | Vedi la nota onesta qui sotto ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Comandi bloccati da VW | ✅ Portale EU Data Act | Accesso OLA revocato lato server nel 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Bidirezionale in attesa di test dal vivo | ✅ Accesso + lettura | My Bentley, gira sul tenant Audi/IDK |
| **Porsche** | ⚠️ Sperimentale | ⚠️ Sperimentale | Porsche Connect, backend proprio. Porsche è passata all'app *Porsche One*, quindi **è previsto che l'accesso fallisca sugli account attuali**. Il codice dei comandi c'è ma è irraggiungibile finché l'accesso non viene ricostruito ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi USA/CA** | ⏳ Bidirezionale in attesa di test dal vivo | ✅ Completo | backend myAudi NA. Ora gli USA leggono dal servizio veicolo regionale `na` e sono **confermati funzionanti su un'Audi Q5 statunitense reale** (58 entità) — grazie @pouwerkerk ([#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); il Canada usa il servizio EMEA. I comandi ereditano i percorsi bidirezionali Audi ma non sono ancora confermati dal vivo separatamente su NA ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Nota onesta sul controllo VW EU.** I veicoli Volkswagen EU sono **in sola lettura per impostazione predefinita**: ottieni la telemetria completa attraverso il portale EU Data Act, ma nessun comando remoto. I comandi remoti per VW EU esistono **solo come ALPHA bidirezionale sperimentale con MBB duraturo**, e solo per le auto **legacy MQB / Car-Net** — è un'opzione opt-in, **non** una funzione predefinita. **Le auto della famiglia MEB / ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) non hanno alcun percorso per i comandi** e vengono create in sola lettura. L'alpha MBB è tracciata in **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — tester benvenuti.

> Nel 2026 Volkswagen ha messo parti delle sue API dietro l'attestazione del dispositivo. Questa integrazione le aggira dove possibile (login Car-Net duraturo, portale EU Data Act, web vw.de) ed è trasparente su ciò che ogni canale può e non può fare.

---

## Limitazioni note

Alcune cose sono **strutturali** — derivano da come funzionano i backend di Volkswagen nel 2026, non dall'integrazione, e nessuna impostazione le risolve:

- **VW EU è in sola lettura per impostazione predefinita; i comandi sono un'alpha MBB solo per le auto legacy.** Vedi la nota sulla marca qui sopra. **Le auto della famiglia MEB / ID sono in sola lettura** — il percorso duraturo dei comandi Car-Net non le riconosce (risponde "Unknown user") e il backend MEB di VW non espone alcun equivalente. La configurazione lo rileva e crea una **voce in sola lettura** (con un avviso di riparazione) invece di fallire, quindi è un limite noto, non silenzioso. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **I comandi remoti CUPRA / SEAT sono bloccati da VW.** L'accesso ai servizi online (OLA) per queste marche è stato revocato lato server nel 2026 (HTTP 403); un nuovo login o un aggiornamento della versione dell'app non lo ripristina. I dati continuano a fluire tramite il portale EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **I dati del portale EU Data Act sono scarni e variano da auto ad auto.** VW pubblica oggi solo una fetta dei campi (spesso contachilometri + chiusura + ricarica, a volte molto di più). Si amplia nel tempo man mano che VW espande il portale in vista della scadenza di settembre 2026 — i campi che oggi leggono `unknown` potrebbero riempirsi da soli, senza alcuna modifica. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **Il Nord America ora legge sia VW che Audi — i comandi Audi sono l'ultimo tassello non confermato.** **VW USA/CA funziona, Canada incluso**, confermato su una ID.4 canadese reale: il Canada accede sul proprio server e, dalla correzione dell'involucro dati, mostra la telemetria completa ([#990](https://github.com/its-me-prash/vwgroup-connect-ha/issues/990)). **Ora anche Audi USA/CA legge**: gli USA attingono dal servizio veicoli regionale `na`, confermato su un'Audi Q5 statunitense reale (grazie @pouwerkerk, [#1092](https://github.com/its-me-prash/vwgroup-connect-ha/pull/1092)); il Canada usa il servizio EMEA. I comandi ereditano i percorsi bidirezionali Audi ma non sono ancora confermati dal vivo separatamente sugli account nordamericani ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)).
- **È previsto che l'accesso Porsche fallisca in questo momento.** Porsche ha dismesso l'app *My Porsche*, verso cui questa integrazione si autentica, a favore di *Porsche One*. Letture e comandi sono implementati, ma probabilmente non supererai l'accesso finché non verrà ricostruito. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Gli aggiornamenti push (quasi in tempo reale) sono una BETA opzionale, disattivata per impostazione predefinita.** I canali MQTT (Škoda) e Firebase (Audi/VW, CUPRA/SEAT) sono cablati ma non validati dal vivo, e le marche li proteggono sempre più con l'attestazione dell'app, che fuori dal dispositivo non è soddisfacibile. Lasciali disattivati a meno che tu non voglia aiutare a testarli. L'interrogazione normale è la via supportata.

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

- **Browser / device-code (senza password)** per *Audi, Škoda, SEAT, CUPRA e Audi USA/CA*. Accedi dal telefono o dal portatile e approva il dispositivo; in Home Assistant non viene salvata nessuna password (conserva un vero refresh token). Questo passaggio offre anche il **S-PIN** facoltativo e l'intervallo di scansione.
- **Portale, e-mail + password** per *Volkswagen EU, Volkswagen USA/CA, Bentley e Porsche (sperimentale)*. Inserisci le credenziali della tua marca. Questo passaggio mostra un selettore di marca, e-mail, password, **S-PIN** facoltativo, intervallo di scansione e un interruttore **«abilita comandi MBB»** (che ha effetto solo su Volkswagen EU, vedi [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Per **Volkswagen USA/Canada** compare qui un **selettore di paese (USA o CA)**; si mostra **solo** per quella marca e nessun'altra lo usa.

> Il **portale EU Data Act non è un terzo pulsante di accesso.** È la strategia in sola lettura su cui il coordinatore ripiega automaticamente, e può inoltre essere *aggiunto* come canale di lettura supplementare da **Configura → Opzioni**. Lo stesso vale per il canale web `volkswagen.de` (beta opzionale, solo dalle Opzioni, in sola lettura) e per il canale **Tibber** opzionale, che riempie i campi lasciati vuoti dai canali di prima parte e non sovrascrive mai dati più freschi.

### Il campo S-PIN — quando serve

L'**S-PIN** è il PIN di sicurezza dell'app della tua marca. È opzionale nel modulo e richiesto solo per alcune azioni: serve per le **letture dei dati e i comandi di VW US/Canada**, e per i comandi remoti sensibili dal punto di vista della sicurezza sulle marche che li proteggono dietro l'S-PIN. Lascialo vuoto se la tua auto non ne richiede uno.

---

### Volkswagen EU — far fluire i tuoi dati (importante)

Per Volkswagen EU, **accedere non basta** — VW trasmette i dati del veicolo solo dopo che *tu* hai attivato la condivisione dei dati sul lato VW. Se la tua auto compare senza dati (o non compare affatto), questo è quasi sempre il motivo, **non** una password errata. Fai questo una volta:

1. **Aggiungi l'integrazione:** scegli **Portale (email + password)** e seleziona **Volkswagen EU**, poi accedi.
2. **Completa qualsiasi richiesta una tantum sul portale di VW.** Apri il portale dati di VW una volta in un browser o nell'app della marca e completa ciò che chiede: **accetta i termini, conferma il consenso, completa l'onboarding / la selezione della regione.** L'accesso headless non può superare questi passaggi — è il caso `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Concedi il consenso alla condivisione dei dati.** Sul portale, imposta **"Uso di dati non personali" = Concesso** (il consenso alla condivisione dei dati dell'EU Data Act).
4. **Non cercare un interruttore per la "richiesta dati continua" — non esiste.** È l'integrazione stessa a creare quella richiesta per ogni auto, ed è **gratuita**. Dalla v2.29.0 la richiesta viene creata **senza data di scadenza**; le versioni precedenti chiedevano una scadenza a un mese, ed è per questo che alcune installazioni smettevano di aggiornarsi in silenzio dopo circa quattro settimane. Se i tuoi dati si sono fermati e hai configurato l'account prima della v2.29.0, rimuovi l'account dall'integrazione e riaggiungilo una volta, così viene creata una richiesta nuova. Senza una richiesta, il portale non restituisce nulla per quel VIN e il veicolo compare senza letture.
5. **Attendi che l'auto invii uno snapshot.** Anche dopo tutto quanto sopra, la propagazione richiede tempo. L'auto può leggere **`offline` / `unknown` per un po' — spesso fino alla sua prossima guida o al prossimo risveglio, fino a ~24 h** — prima che i sensori si popolino. È normale.

Il portale inizialmente serve solo una **fetta di campi**, e quella fetta **si amplia nel tempo** man mano che VW espande la copertura del portale in vista della scadenza di settembre 2026 — i campi che oggi leggono `unknown` potrebbero riempirsi da soli. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Elenco completo dei campi.** Il dizionario dati ufficiale del gruppo VW (ogni chiave EU Data Act -> campo, descrizione e unità) si trova in [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Un workflow settimanale sorveglia la pagina del dizionario del portale e apre una pull request quando VW pubblica una versione più recente, così la tabella non invecchia in silenzio.

> È l'opzione **`eu_data_act_auto_kickoff`** a creare quella Custom Data Request a 15 minuti, ed è **attiva per impostazione predefinita** — in modalità portale senza di essa non ci sono dati. Disattivala solo se preferisci gestire la richiesta per conto tuo.

---

## Cosa ottieni

- **Sensori:** SoC batteria, autonomia (elettrica / termica / totale), livello carburante, contachilometri, temperature, potenza di ricarica, velocità di ricarica (sempre in km/h, convertito se la tua auto riporta in mph) e tipo di ricarica, obiettivo di ricarica, cronologia per sessione di ricarica (energia · durata · inizio · AC/DC, su Škoda e SEAT/CUPRA), statistiche di viaggio e aggregati sull'intera vita del veicolo, intervalli di tagliando e cambio olio, versione software, stato della connessione, ultima rilevazione e — su Škoda — ultimo rifornimento, sessione di parcheggio a pagamento in corso, promemoria dei tagliandi, timer di partenza e modalità di ricarica preferita, e altro.
- **Sensori binari:** porte chiuse, porte/finestrini/bagagliaio/cofano/tetto apribile aperti, spina collegata, in ricarica, aggiornamento OTA disponibile, luci, veicolo online, timer di partenza, allarme.
- **Controllo:** chiusura/apertura, avvio/arresto clima, avvio/arresto ricarica, riscaldamento vetri, timer di partenza, impostazione di SoC obiettivo / temperatura / corrente di ricarica max, clacson-e-lampeggio (con durata a scelta e la possibilità di usare solo le luci oppure anche il clacson), risveglio, aggiornamento, ricerca stazioni di ricarica, modalità campeggio e ventilazione attiva (aerazione dell'abitacolo Škoda senza riscaldamento) *(la disponibilità dipende da marca e modello)*.
- **Device tracker:** posizione GPS per la mappa di Home Assistant. Un'interrogazione che torna senza coordinate conserva l'ultima posizione di parcheggio nota invece di perderla.
- **Immagini:** render del veicolo dove la marca li fornisce.
- **Impostazioni:** un cursore dell'**intervallo di interrogazione** per account, in minuti, così un'automazione può interrogare più spesso mentre guidi e rallentare di notte. Esiste in ogni installazione, comprese le voci portale in sola lettura.
- **12 lingue:** i nomi delle entità sono tradotti integralmente in inglese, tedesco, francese, spagnolo, italiano, olandese, polacco, ceco, svedese, danese, norvegese e finlandese.

> 💡 **Dashboard energia:** il sensore dell'energia caricata è `total_increasing`, quindi aggiungilo direttamente alla **dashboard Energia** di Home Assistant, oppure avvolgilo in un helper `utility_meter` per i totali giornalieri/mensili di energia caricata. Usa a questo scopo il sensore cumulativo **energia caricata (kWh)** — non i sensori di efficienza per 100 km (quelli sono medie, non contatori).

### Servizi

L'integrazione include **oltre 30 service-call** (`vag_connect.*`), molti specifici per marca — *la disponibilità dipende da marca e modello*. Tra questi: `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi termico), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (riscaldatore ausiliario / di stazionamento — SEAT/CUPRA, Škoda e VW/Audi su un canale comandi bidirezionale, dove l'auto ne è equipaggiata), `send_destination` (SEAT/CUPRA/Škoda) e `update_charging_settings` (SEAT/CUPRA), la `ask_assistant` di Škoda (vedi sotto), `set_location_target_soc` e `set_seat_heating`, `open_app`, `execute_vehicle_action`, `abrp_send` e l'easter egg `show_vag`.

---

## evcc

[evcc](https://evcc.io) può prendere stato di carica, autonomia e stato della ricarica della tua auto direttamente da Home Assistant, così la ricarica da surplus solare pianifica sulla batteria reale invece che su una stima. Dentro l'integrazione non gira nulla in più: evcc legge l'API REST di Home Assistant. La via di **lettura** funziona su **tutte le marche**, comprese le auto VW EU / portale in sola lettura. La via di **scrittura** (`chargeEnable`) funziona solo su un'auto bidirezionale (Audi o Škoda con un canale comandi vivo) e solo quando evcc tratta l'auto stessa come punto di ricarica. Con una vera wallbox intelligente a evcc basta la via di lettura.

Le ricette `evcc.yaml` già pronte e la configurazione iniziale sono in [docs/EVCC.md](docs/EVCC.md). Questo connettore è in **beta**.

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

## Assistente AI di Škoda («Laura») — novità della 3.0.0

L'assistente di bordo di MyŠkoda, **Laura**, è disponibile dentro Home Assistant.
Chiedile di autonomia, ricarica e viaggi con il servizio `vag_connect.ask_assistant`
(restituisce una risposta testuale che puoi inviare come notifica, far pronunciare o
usare per ramificare la logica), oppure affidala a un **agente conversazionale** —
l'Assist integrato in modalità LLM, oppure OpenAI / Anthropic / Google / Ollama — come
strumento che può richiamare e concatenare (chiedi a Laura → poi `send_destination`
all'auto). È **in sola lettura, di natura consultiva e solo per Škoda**;
è una **beta**, quindi il feedback sulla qualità delle risposte è benvenuto.

Configurazione, il trigger vocale («chiedi a Laura …») e automazioni di esempio già
pronte — inclusa *l'auto arriva a casa → rabbocca la carica + preriscalda + pronuncia
l'autonomia* — sono in **[docs/AI_ASSISTANT.md](docs/AI_ASSISTANT.md)**.

---

## Opzioni (Configura)

Da **Impostazioni → Dispositivi e servizi → VW Group Connect → Configura** puoi regolare:
intervallo di scansione (disponibile anche dal vivo come cursore dell'intervallo di interrogazione), S-PIN (più un S-PIN per veicolo quando l'account ha più di un'auto), geocodifica inversa, **modalità sola lettura**, forza clima PPE (Audi), opzioni push (MQTT/FCM/Audi-VW, tutte beta opzionali e disattivate per impostazione predefinita), override client-id, **`eu_data_act_auto_kickoff`** (attivo per impostazione predefinita), nascondi entità vuote (attivo per impostazione predefinita), **ABRP** (abilita + api_key + token utente, validati come coppia), oltre ad **aggiungere / rimuovere** i canali di lettura supplementari: `volkswagen.de` (beta), portale EU Data Act, **Tibber** e il canale sperimentale **telefono companion**.

---

## Sostieni questo progetto ❤️

Questo è un progetto di una sola persona — e VW non lo rende facile: ogni modifica al backend significa giorni di reverse engineering per trovare di nuovo un percorso funzionante. È questa tenacia a tenerlo in vita là dove progetti affermati hanno rinunciato. Se per te vale qualcosa, puoi sostenere la manutenzione continua tramite **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Grazie! 🙏

---

## Contribuire

PR benvenute, vedi [`CONTRIBUTING.md`](CONTRIBUTING.md). Le domande frequenti trovano risposta in [docs/FAQ.md](docs/FAQ.md). Il **Vehicle Data Scout** trasforma i campi API sconosciuti in una segnalazione di bug precompilata e con un clic, così puoi contribuire a migliorare la copertura senza leggere il codice.

## Licenza

[GNU AGPL v3.0-or-later](LICENSE) per il codice dell'integrazione. Attribuzione obbligatoria + termini su nome/marchio in caso di uso/fork: vedi [`ATTRIBUTION.md`](ATTRIBUTION.md). Attribuzioni open source upstream in [`NOTICE.md`](NOTICE.md).
