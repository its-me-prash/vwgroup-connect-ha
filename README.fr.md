<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Intégration Home Assistant pour Audi · VW · Škoda · SEAT · CUPRA</strong>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha?style=for-the-badge"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&style=for-the-badge&label=CI" alt="CI"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/downloads/its-me-prash/vwgroup-connect-ha/total?style=for-the-badge&label=Downloads" alt="Downloads"></a>
  <a href="../custom_components/vag_connect/quality_scale.yaml"><img src="https://img.shields.io/badge/Quality%20Scale-Platinum%20%F0%9F%8F%86-gold?style=for-the-badge"></a>
</p>

<p align="center">
  <a href="../README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Previously published as **`vag-connect-ha`** (VAG = Volkswagen AG, standard DACH abbreviation).
> Turns out that abbreviation reads *quite* differently to English speakers 😅
>
> **What keeps working as before**: all entities (e.g. `sensor.audi_q4_battery_soc`),
> all service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), all automations,
> the HACS install — **nothing breaks**. Marketing/display name changes, code internals
> stay unchanged. See [`MIGRATION.md`](MIGRATION.md).
>
> Huge thanks to the **Home Assistant UK** and **HA Ideas, Projects and Solutions**
> communities for the heads-up — especially **Si Gregory**, **Ben Johnson**, and **Evets David**.
>
> And a special shoutout to **Jordan Waeles**, whose `show_vag()` comment is now an officially
> supported easter egg in this integration (`vag_connect.show_vag` service, see CHANGELOG v2.2.3).

---

## ✨ v2.0.0 Big-Bang Highlights — also available in English

> The detailed v2.0.0 highlights table + "What makes us unique" USP section
> are maintained in English on the German + English READMEs. They are
> provided here as the canonical source so non-DE/EN readers can still
> see all v2.0 features with `**[NEW v2.0]**` markers without waiting on
> 6 parallel translations.

### Latest highlights — v2.0.0 Big-Bang

| Feature | Status |
|---|---|
| **Skoda Driving-Score Sensor** | **[NEW v2.0]** Efficiency score 0-100 + class bucket for Skoda MY24+ |
| **Cross-brand Aux-Heating parity (Skoda)** | **[NEW v2.0]** SkodaClient now inherits the Webasto switch from SEAT/CUPRA |
| **Porsche TPMS sensors** | **[NEW v2.0]** 4 tire-pressure sensors + warning binary_sensor (PPA TIRE_PRESSURE) |
| **Long-Term Trip Aggregates** | **[NEW v2.0]** Lifetime distance / avg fuel / avg electric (Audi + VW EU) |
| **Departure-Timer Read-Only Binary-Sensors** | **[NEW v2.0]** 3 pure-read enabled-sensors |
| **Weekly Preheat (`recurring_on`)** | **[NEW v2.0]** Service param for weekday lists (Audi + VW EU + VW NA) |
| **Charging-Station POI Lookup** | **[NEW v2.0]** `vag_connect.find_charging_stations` service |
| **Vehicle Alarm sensors** | **[NEW v2.0]** closes issue #33 |
| **heaterSource sensor** | **[NEW v2.0]** closes issue #163 |
| **Push Manager Lifecycle Wiring** | **[NEW v2.0]** Skoda MQTT + CUPRA/SEAT FCM + Audi/VW Cariad FCM (opt-in) |
| **EU Data Act Abstraction Shim** | **[NEW v2.0]** Architectural seam for the 2026-09-12 EUDA Art. 3 deadline |
| **Auth Resilience One-Click Repair** | **[NEW v2.0]** Repair button for 4 auth reasons triggers reauth flow |
| **System Health Panel** | **[NEW v2.0]** Drop-in `system_health.py` |
| **Quality Scale Platinum** | **[NEW v2.0]** Re-introduced after v1.26.x revert |
| **DeviceInfo `configuration_url` + `suggested_area`** | **[NEW v2.0]** Brand-aware "Open in App" button |

### What makes us unique

- **Native coverage of all 7 VAG brands** in a single integration
- **Direct manufacturer-API access** without middleware / Docker / 3rd service
- **Vehicle Data Scout** — automatic JSON-field drift detection with Repair notification + 1-click GitHub issue
- **Capability-Filter Phase 3** — phantom entities suppressed before spawn
- **Per-VIN wakeup cap + cooldown** — protects 12V battery
- **Auth Resilience One-Click Repair** — reauth flow from Repairs panel
- **System Health Panel** — at-a-glance push channel status, API quota, last poll
- **Bruno-CI Stage 2** — strict URL-drift check
- **Token persistence across HA updates** — no re-login after HACS updates since v1.19.2
- **Diagnostics anonymisation by default** — VINs, GPS, tokens stripped before export


Je voulais contrôler mon Audi dans Home Assistant — complètement. Alors j'ai construit ça.

**VW Group Connect** est une intégration Home Assistant autonome pour toutes les marques VAG. Aucune dépendance externe, aucun Docker, aucun service externe. Installez l'intégration, entrez vos identifiants, c'est prêt.

Depuis v0.14.1, l'intégration parle **directement** à l'API CARIAD — client async propre, entièrement autonome. Architecture cloud-polling, 80+ entités sur 10 plateformes, 14 services.

> ✅ **Successeur multi-marque activement maintenu** de [`mitch-dc/volkswagen_we_connect_id`](https://github.com/mitch-dc/volkswagen_we_connect_id) (archivé le 2025-10-29) et [`skodaconnect/homeassistant-skodaconnect`](https://github.com/skodaconnect/homeassistant-skodaconnect) (déprécié le 2025-03-14). Une intégration pour Audi, VW, Škoda, SEAT, CUPRA, Porsche et VW US/CA — pas de plugin séparé par marque.

## État actuel et limites honnêtes / Current Status & Honest Limits (v1.12.3)

VW Group Connect évolue activement. Pour que tu saches ce qui fonctionne et ce qui arrive :

### ✅ Ce qui FONCTIONNE maintenant (toutes les 7 marques)

**🛰️ Rapports de bugs & demandes de fonctionnalités en 1-clic (LIVE depuis v1.9.0)**

Deux capteurs de diagnostic avec une pipeline reporter commune — **première vraie validation live par des utilisateurs de la communauté** en v1.10.2 (Gerhard / CUPRA Born), v1.12.2 (tritanium73 / Skoda) et v1.12.3 (DnnsJp74 / Audi) :

- 🔬 **Vehicle Data Scout** — détecte automatiquement les champs JSON inconnus dans l'API de ta voiture. Localisé par marque dans 8 langues (DE : API-Beobachter, FR : Observateur d'API, etc.).
- 🚨 **Error Reporter** — Ring-buffer des 20 dernières erreurs d'intégration avec contexte anonymisé (modèle, firmware, stack trace).
- 🔘 **Reporter Pipeline :** les deux capteurs créent automatiquement des notifications HA Repair avec un GitHub-Issue pré-rempli en lien 1-clic. Plus un téléchargement de diagnostics avec tout masqué pour le forum/Facebook.
- 🔒 **Promesse confidentialité :** Rien ne quitte ton HA sans ton clic explicite. VIN masqués, GPS arrondi à 1 décimale, JWT/UUID/emails supprimés. Conforme RGPD.

**🟢🟡⚫ Multi-Brand Connection-State (v1.8.12)**

Capteur `connection_state` (online / standby / offline) pour Audi, VW EU, Škoda, SEAT, CUPRA — première intégration VAG avec statut de connexion centralisé. Helper brand-agnostic `compute_connection_state` avec parcours récursif `carCapturedTimestamp`.

**🔋 Surveillance batterie 12V + Smart-Wake (v1.12.0)**

- Capteur `voltage_12v` (V) + binary `warning_12v_low` à <11.5V — empêche les pannes silencieuses de l'API dues à une batterie de démarrage vide
- Capteur `wake_count_today` + soft-cap à 3 wakes/jour (`_WAKE_BUDGET_PER_DAY`) protège la 12V des wake-loops, lève `wake_budget_exhausted` AVANT l'appel API

**💨 UI optimiste pour Lock/Climate/Charging (v1.11.1)**

Les switches basculent immédiatement au clic (pattern myskoda PR #832), aller-retour API en arrière-plan. En cas d'échec : revert + ServiceValidationError. 8 méthodes actuator migrées.

**🔋 PHEV-Range-Triple (v1.10.0 + #94 + #96 follow-up en v1.11.1)**

Trois capteurs d'autonomie explicites : `electric_range_km`, `combustion_range_km`, `total_range_km`. Le parser VW EU/Audi classifie par type de motorisation (4 sources au lieu de 2). Fallback diesel Audi depuis `measurements.rangeStatus.value.dieselRange`. Vérifié via evcc-io/evcc#19045 + sample Audi Q4 + logs CarConnectivity.

**🔒 Mode Read-only Phase 1 (v1.12.0)**

Toggle d'options "Read-only Mode" → ignore les plateformes lock/switch/button(non-refresh)/climate/number pour les propriétaires soucieux de confidentialité/sécurité. Sensors + binary_sensors + device_tracker restent.

**⚡ Number Max-Charge-Current modifiable (v1.12.0)**

Slider 6-32A au lieu d'un capteur read-only seul. Nouveau `command_set_max_charge_current` POST chargingSettings.

**💡 Binary-Sensors par feu (v1.12.0)**

Dynamiquement par type de feu depuis le dict `lights_individual` + agrégats `lights_on` + `lights_count`.

**🛠️ Stabilité défensive (v1.8.7 + v1.10.1)**

- Retry 504, retry erreurs réseau transitoires, cache 6h + tolérance 3 échecs
- Protection token-refresh-storm (max 3/h) — empêche les bans IP
- Helpers `safe_int` / `safe_float` / `safe_enum` — tolèrent les bizarreries du backend

**🚪 Firmware-Shapes CUPRA Born 2026 (v1.10.2 — première validation live de Gerhard #53)**

Chaîne de fallback de noms de champs : `battery.currentSocPercentage` (Born 2026) → `currentPct` (Rainer #109) → `currentSOC_pct` (legacy). Tolérance enum lowercase pour `"connected"` / `"locked"`. Compatibilité ascendante préservée.

**🔓 Lock + Wake pour Audi/VW (v1.9.1, #92 Audi S6 C8)**

`command_lock` envoie maintenant le S-PIN pour Audi/VW (CARIAD BFF répondait `403 spin_error`). `command_wake` utilise le fallback v1→v2.

**🛡️ Capability-Filter Phase 2 (v1.9.1, #56)**

Body-sniffing `classify_command_failure` pour les marqueurs `missing-capability` / `subscription_expired` / `not_entitled` / `spin_error`. `_cariad_cmd` écrit chaque résultat dans FeatureState. Les entités liées aux commandes (Lock/Climate/Switch/Buttons) deviennent automatiquement unavailable sur un "non" définitif du backend.

### ⚠️ Encore en cours / What's still in progress (sessions planifiées)

- **v1.13.0 MINOR** — Export de diagnostics anonymisés (#62) + Capability-Filter Phase 3 (`capability.active && user-enabled` PRE-création-d'entité, masque les boutons comme l'app MyCupra) + Read-only Phase 2/3 (Command-Locking + séparation des services cloud_refresh vs wake_vehicle).
- **v1.14.0 MINOR** — Statistiques de trajets depuis Audi `tripstatistics/v1` (#24, #35).
- **v1.15.0+ MINOR** — PPC Climate Body conditional shape (#29, #51), Theft/Alarm Binary (#33), UI minuteur Climate (#26).
- **v1.16.0 MINOR** — SoC cible de charge spécifique au lieu + profils de charge (#25, #31).
- **v1.17.0 MINOR** — Remote Start ICE (#28, pattern upstream #717).
- **v1.18.0 MINOR** — Push CUPRA/SEAT (Firebase FCM) + Push Skoda (mysmob MQTT) pour des mises à jour en temps réel sans polling (#57, #27).
- **v2.0.0 MAJOR** — HACS Default + Live-Tests toutes marques + EU Data Act ready (pycupra `EUDAConnection` comme référence, deadline septembre 2026) (#13, #59).

### 🚫 Limites conscientes / Conscious limits

- **Plateforme image :** aucune API CARIAD render-image officielle n'existe. L'entité image basculera vers des URL fournies par l'utilisateur dans une future release.
- **PPC/PPE Audi 2025+** (Q5, A5/S5, A6 e-tron, Q6 e-tron, RS e-tron GT Facelift) — nouvelle architecture E³ 1.2, pas encore reverse-engineerée publiquement (même pas dans upstream ou CarConnectivity). VW Group Connect détecte ces véhicules et fait du **graceful degradation** au lieu d'erreurs 404.
- **Ford / marques non-VAG :** hors périmètre — voir [`marq24/ha-fordpass`](https://github.com/marq24/ha-fordpass) pour Ford.

### 🔧 Prérequis confidentialité

Pour que la position GPS, le statut véhicule et le préchauffage fonctionnent, **"Partager ma position"** doit être activé dans ton app My-VW / My-Audi / MySkoda / MyCupra — sinon le backend répond avec 403.

### 📚 Plus d'infos / More info

- 🗺️ Roadmap : [`docs/ROADMAP.md`](docs/ROADMAP.md) — priorisation P0/P1/P2/P3 complète de tous les issues ouverts
- 📜 Tech Changelog : [`docs/CHANGELOG_TECHNICAL.md`](docs/CHANGELOG_TECHNICAL.md) — par release : mappings de champs + décisions d'architecture + refs sources externes
- 🎨 Guide Dashboards + carte Lovelace BETA : [`docs/dashboards.md`](docs/dashboards.md) — "Ajouter au tableau de bord" troubleshooting + carte Lovelace dédiée (BETA)
- 🤝 Session Handoff (pour contributeurs & outils IA) : [`docs/SESSION_HANDOFF.md`](docs/SESSION_HANDOFF.md)
- 🔒 Règles de confidentialité & gestion des données : section [`CONTRIBUTING.md`](CONTRIBUTING.md) (post-#53 third-party review)
- 📋 FAQ Subscription / Service Plus / diagnostic `missing-capability` : section FAQ de [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## Marques Supportées

| Brand | Auth | API | Status |
|---|---|---|---|
| **Volkswagen EU** | IDK | emea.bff.cariad.digital | ✅ |
| **Audi** | IDK + AZS/MBB | emea.bff.cariad.digital | ✅ |
| **Škoda** | IDK | mysmob.api.connect.skoda-auto.cz | ✅ |
| **SEAT** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| **CUPRA** | IDK | ola.prod.code.seat.cloud.vwgroup.com | ✅ |
| Porsche | Auth0 | api.ppa.porsche.com | ✅ Beta |
| VW NA (US/CA) | VW NA Auth | b-h-s.spr.*.p.con-veh.net | ✅ Beta |

> **Porsche & VW NA :** Les deux marques sont disponibles en Beta depuis v1.0.0. Testeurs recherchés — signalez vos retours via un [Issue](https://github.com/its-me-prash/vwgroup-connect-ha/issues) !

---

## Fonctionnalités

| Feature | Audi | VW EU | Škoda | SEAT/CUPRA |
|---|:---:|:---:|:---:|:---:|
| Fuel / Battery level | ✓ | ✓ | ✓ | ✓ |
| Range | ✓ | ✓ | ✓ | ✓ |
| Odometer | ✓ | ✓ | ✓ | ✓ |
| GPS position | ✓ | ✓ | ✓ | ✓ |
| Doors (total + per door) | ✓ | ✓ | ✓ | ✓ |
| Windows | ✓ | ✓ | ✓ | ✓ |
| Climate start/stop | ✓ | ✓ | ✓ | ✓ |
| Target temperature | ✓ | ✓ | ✓ | ✓ |
| Lock / Unlock | ✓ | ✓ | ✓ | ✓ |
| Flash lights | ✓ | ✓ | ✓ | ✓ |
| Wake vehicle | ✓ | ✓ | ✓ | ✓ |
| Service due km/days | ✓ | ✓ | ✓ | ✓ |
| Online status | ✓ | ✓ | ✓ | ✓ |
| Battery SoC % | ✓ | ✓ | ✓ | ✓ |
| Charge state | ✓ | ✓ | ✓ | ✓ |
| Charge power kW | ✓ | ✓ | ✓ | ✓ |
| Charge speed km/h | ✓ | ✓ | ✓ | ✓ |
| Charge ETA | ✓ | ✓ | ✓ | ✓ |
| Charge target % | ✓ | ✓ | ✓ | ✓ |
| Trunk / hood / sunroof | ✓ | ✓ | ✓ | ✓ |
| Window heating | ✓ | ✓ | ✓ | ✓ |
| Vehicle renders | ✓ | — | — | ✓ |
| Departure timers 1–3 | ✓ | ✓ | — | — |
| Battery temperature | ✓ | ✓ | — | — |
| AdBlue range | ✓ | ✓ | — | ✓ |

---

## Installation

### HACS

1. HACS → Intégrations → ⋮ → Dépôts personnalisés
2. URL : `https://github.com/its-me-prash/vwgroup-connect-ha` — Catégorie : Intégration
3. Installer **VW Group Connect** → Redémarrer Home Assistant
4. Paramètres → Intégrations → **+ Intégration** → **VW Group Connect**

### Manual

```bash
cp -r custom_components/vag_connect ~/.homeassistant/custom_components/
```

Redémarrez Home Assistant.

---

## Configuration

| Field | Required | Description |
|---|---|---|
| Marque | ✓ | Audi / Volkswagen / Škoda / SEAT / CUPRA |
| E-mail | ✓ | E-mail de connexion de l'application constructeur |
| Mot de passe | ✓ | Mot de passe de l'application |
| S-PIN | — | Requis pour le verrouillage (dans Sécurité dans l'app) |
| Intervalle | — | Minutes entre les mises à jour (défaut : 5) |

**Quelle app ?** Audi → myAudi · VW → WeConnect · Škoda → MyŠkoda · SEAT → My SEAT · CUPRA → MyCupra

---

## Limitations Connues

- **S-PIN** requis pour le verrouillage — à configurer dans l'app
- **Intervalle** minimum 5 minutes — trop court entraîne un blocage temporaire
- **2FA** — confirmer une fois manuellement dans l'app
- **Porsche / VW NA** — fonctionnel en Beta, testeurs recherchés

---


## Licence

Apache License 2.0 — [LICENSE](LICENSE)

**VW Group Connect™** est une marque non déposée (™, pas ®). Veuillez ne pas utiliser ce nom dans les forks afin d'éviter toute confusion.

Cette intégration est un projet communautaire indépendant sans affiliation avec Volkswagen AG, Audi AG, Škoda Auto, SEAT S.A., CUPRA, Porsche AG ou toute filiale VAG.

---

*Copyright 2026 [Prash Balan](https://github.com/its-me-prash) · Apache License 2.0*
