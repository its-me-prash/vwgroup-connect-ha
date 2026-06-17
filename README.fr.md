<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Intégration Home Assistant pour Audi · VW · Škoda · SEAT · CUPRA · Porsche · VW US/CA</strong><br>
  <em>Une seule intégration pour les 7 marques VAG, accès direct à l'API, sans middleware</em>
</p>

<p align="center">
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-Custom-orange.svg" alt="HACS"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/releases"><img src="https://img.shields.io/github/v/release/its-me-prash/vwgroup-connect-ha" alt="Version"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="Licence"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2025.1%2B-blue" alt="Home Assistant"></a>
  <a href="https://github.com/its-me-prash/vwgroup-connect-ha/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/its-me-prash/vwgroup-connect-ha/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="https://www.home-assistant.io/docs/quality_scale/"><img src="https://img.shields.io/badge/quality_scale-platinum-d4af37" alt="Quality Scale Platinum"></a>
</p>

<p align="center">
  <a href="README.md">Deutsch</a> ·
  <a href="README.en.md">English</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.nl.md">Nederlands</a> ·
  <a href="README.pl.md">Polski</a> ·
  <a href="README.cs.md">Čeština</a> ·
  <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 Note on the rename
> Auparavant publié sous le nom **`vag-connect-ha`** (VAG = Volkswagen AG, abréviation courante en zone DACH).
> Il s'est avéré que cette abréviation sonne *nettement différemment* pour les anglophones 😅
>
> **Ce qui continue de fonctionner à l'identique** : toutes les entités (p. ex. `sensor.audi_q4_battery_soc`),
> tous les service-calls (`vag_connect.lock`, `vag_connect.show_vag` etc.), toutes les automatisations,
> l'installation HACS — **rien ne casse**. C'est le nom marketing/affiché qui change,
> les internes du code restent identiques. Détails dans [`MIGRATION.md`](MIGRATION.md).
>
> Un grand merci aux communautés **Home Assistant UK** et **HA Ideas, Projects and Solutions**
> pour l'avoir signalé — en particulier à **Si Gregory**, **Ben Johnson** et **Evets David**.
>
> Et un clin d'œil spécial à **Jordan Waeles**, dont le commentaire `show_vag()` est désormais un easter egg
> officiellement pris en charge dans cette intégration (service `vag_connect.show_vag`, voir CHANGELOG v2.2.3).

---

## Qu'est-ce que c'est ?

**VW Group Connect est une intégration [Home Assistant](https://www.home-assistant.io) pour les données et le contrôle des véhicules connectés sur l'ensemble des sept marques du groupe Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche et VW US/Canada — depuis une seule entrée de configuration, installable via [HACS](https://hacs.xyz).**

Elle expose l'état de la batterie et de la charge, l'autonomie, le kilométrage, la climatisation, les portes/fenêtres et la localisation, et — lorsque le backend de la marque le permet encore (p. ex. Audi) — envoie des commandes comme verrouillage/déverrouillage, contrôle de la climatisation et de la charge. Pour rester fonctionnelle malgré les changements d'API de Volkswagen en 2026, elle parle plusieurs canaux et bascule automatiquement quand l'un d'eux est bloqué : les backends natifs des marques, le portail de données véhicule **EU Data Act** en lecture seule, et un canal web `volkswagen.de` en opt-in.

Contrairement aux intégrations qui reposent uniquement sur le portail, elle couvre aussi **Porsche** (que le portail EU Data Act exclut) et conserve le **contrôle bidirectionnel d'Audi**.

> Une intégration [Home Assistant](https://www.home-assistant.io) pour les données et le contrôle des véhicules connectés sur les sept marques du groupe VW (Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, VW US/CA) — une seule intégration, plusieurs canaux de données, repli automatique, installation via HACS.

---

## Situation actuelle

En 2026, VW a progressivement fermé l'accès direct au véhicule pour les outils tiers (CARIAD-BFF avec attestation d'appareil, OLA CUPRA/SEAT derrière Play Integrity depuis juin 2026). Cette intégration reste utilisable parce qu'elle parle **plusieurs canaux** et bascule automatiquement dès que l'un d'eux est bloqué :

- **Backends propres aux marques** — accès complet, contrôle inclus là où c'est disponible (Audi, Škoda, Porsche, VW US/CA).
- **Portail EU Data Act** — repli en lecture seule pour toutes les marques (sans attestation, cadence ~15 min).
- **Canal web volkswagen.de (bêta, opt-in)** — deuxième canal de lecture sans attestation pour VW.

Le travail en cours porte sur la robustesse du portail (retry sur timeout, fraîcheur des données) et la résilience à travers les canaux.

➡️ Historique complet des versions : **[CHANGELOG.md](CHANGELOG.md)**.

---

## Là où nous menons

État honnête mi-2026 : le portail EU Data Act est devenu le canal standard de facto, beaucoup d'intégrations l'utilisent. Ce qui nous distingue concrètement :

| Atout | Nous | Alternatives portail-only |
|---|---|---|
| **Les 7 marques du groupe, Porsche inclus**, dans une seule intégration | ✅ | Le portail EU Data Act **exclut structurellement Porsche** — les outils portail-only ne pourront jamais couvrir Porsche |
| **Contrôle bidirectionnel Audi** (verrouillage/climatisation/charge, réglage du SoC cible) | ✅ | Le portail est en **lecture seule** par conception |
| **Auth multi-canal avec repli automatique** (backend de la marque → portail EU Data Act → web vw.de en opt-in) | ✅ | le plus souvent à source unique — une panne du portail = panne totale |
| **Vehicle Data Scout** — détecte automatiquement la dérive de l'API, génère des rapports de bug en 1 clic | ✅ | rien d'équivalent |

---

## Là où sont les limites (en toute honnêteté)

**VW EU et l'OLA CUPRA/SEAT sont derrière une attestation d'appareil depuis 2026.** Ce mur (Google Play Integrity / Firebase App Check) touche toute intégration VAG basée sur Python — la nôtre incluse. Ce n'est pas un retard de notre côté, c'est la politique backend de VW :

- L'endpoint token/OLA exige un token d'attestation signé par l'app officielle, que Python ne peut pas générer (la clé de signature vit uniquement dans le service d'attestation Google/Firebase).
- Conséquence : **VW EU** n'obtient pas de `refresh_token` durable (le flux hybride OIDC tient ~2 h), et **CUPRA/SEAT** via OLA reçoivent depuis le ~2026-06-08 un `403 "Forbidden device detected"`.

Ce que nous offrons malgré tout :

1. **Portail EU Data Act** en repli lecture seule pour toutes les marques (sans attestation, cadence ~15 min) — prend le relais automatiquement quand le backend natif bloque.
2. **Canal web volkswagen.de (bêta, opt-in)** comme deuxième canal de lecture sans attestation pour VW.
3. **Flux hybride OIDC** pour VW EU comme stratégie lecture+écriture (au prix d'une reconnexion toutes les 2 h).

**Échéance EU Data Act 2026-09-12.** D'ici là, le règlement européen impose à VW de fournir un accès direct et sans attestation aux données du propriétaire — la couverture des champs du portail devrait continuer de croître d'ici cette date.

Statut par marque :

| Marque | Contrôle | Données | Remarque |
|---|---|---|---|
| **Audi** | ✅ Bidirectionnel | ✅ complet | backend myAudi, pas de mur d'attestation |
| **Škoda** | ✅ Bidirectionnel | ✅ complet | backend Škoda propre |
| **Porsche** | ✅ Bidirectionnel | ✅ complet | Auth0 + PPA, stable |
| **VW US/CA** | ✅ Bidirectionnel | ✅ complet | cloud VW-NA (bêta) |
| **VW EU** | ⚠️ via hybride OIDC (reconnexion ~2 h) | ✅ portail lecture seule / bêta vw.de | backend gated par attestation |
| **CUPRA / SEAT** | ❌ OLA bloqué (App Check) | ✅ portail lecture seule | depuis le ~2026-06-08, non corrigeable via header |

---

## Ce que tu obtiens

100+ entités sur 11 plateformes HA, 20+ service-calls, support multi-véhicule natif par compte. Quality-Scale Platinum.

**Capteurs** (par véhicule) : Battery SoC, Range (electric / combustion / total), Fuel Level, Odometer, Outside Temp, Battery Temp, 12V Voltage, Service Days, Oil Service Days, Charging Power / Rate / Type, Last Trip Stats, Lifetime Trip Aggregates, Charging History, Plug State, Lights Count, Equipment Count, Software Version, API Quota Remaining, Connection State, Last Seen, Skoda Driving Score, Porsche TPMS 4 Corners, Last Alarm Timestamp, Heater Source pour ID.x, Oil Level Warning, alertes véhicule (capteur texte avec toutes les alertes du backend).

**Binary Sensors** : Doors Locked, Doors Open par porte, Windows Open par fenêtre, Trunk / Hood / Sunroof, Plug Connected, Charging, OTA Update Available, 12V Low Warning, Lights On par feu, Vehicle Online, Departure-Timer 1-3 Enabled, Alarm Active + Siren Active, TPMS Warning.

**Contrôle** : Lock/Unlock, Climate Start/Stop, Charging Start/Stop, Window Heating, Cabin Ventilation (CUPRA/SEAT), Aux Heating (Webasto), Departure Timer 1-3 avec préchauffage hebdomadaire, Set Target SoC, Set Target Temp, Set Max Charge Current, Set Charge Mode, Honk-and-Flash, Wake Vehicle, Refresh, Find Charging Stations.

**Image Platform** : 1-7 rendus de véhicule par VIN (Audi/VW via GraphQL MediaService, CUPRA/SEAT via OLA viewPoints, Skoda via Widget + composites multi-angles).

**Device Tracker** : position GPS comme TrackerEntity pour la carte Lovelace de HA.

---

## Installation

### Option 1 : One-Click (recommandé)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=its-me-prash&repository=vwgroup-connect-ha&category=integration)

### Option 2 : HACS Custom Repository

1. HACS → Intégrations → ⋮ → Dépôts personnalisés
2. URL : `https://github.com/its-me-prash/vwgroup-connect-ha`
3. Catégorie : Integration
4. Installer **VW Group Connect**
5. Redémarrer Home Assistant

### Option 3 : Manuel

```bash
cd /config/custom_components
git clone https://github.com/its-me-prash/vwgroup-connect-ha.git
mv vwgroup-connect-ha/custom_components/vag_connect .
rm -rf vwgroup-connect-ha
```

Ensuite, redémarrer HA.

---

## Configuration

Paramètres → Appareils et services → Ajouter une intégration → « VW Group Connect »

**Lors du premier setup, tu choisis :**

- **Connexion par navigateur** (recommandé pour Audi/Škoda/SEAT/CUPRA) : scanner un QR code ou ouvrir l'URL, aucun mot de passe stocké dans HA
- **E-mail + mot de passe** (pour VW EU, Porsche, VW US/CA) : classique, avec les identifiants Brand-ID

**Options** (disponibles après le setup) :
- Intervalle de polling (5-60 min, défaut 10 min)
- Mode lecture seule pour des automatisations sûres sans commandes involontaires
- Reverse-geocoding en opt-in (envoie le GPS à OpenStreetMap pour la résolution d'adresse)
- Toggles push (Skoda MQTT, CUPRA/SEAT FCM, Audi/VW FCM) en fondation, activation live à venir

---

## Exemples Lovelace

### Map Card

```yaml
type: map
title: Fuhrpark
default_zoom: 12
hours_to_show: 24
entities:
  - device_tracker.audi_a4_b9_position
  - device_tracker.vw_golf_7_gte_position
  - zone.home
```

### Picture-Entity Card avec rendu de véhicule

```yaml
type: picture-entity
entity: image.audi_a4_b9_render_side_lg
camera_view: live
show_state: false
show_name: false
```

### Recherche de bornes de recharge

```yaml
action: vag_connect.find_charging_stations
data:
  vin: WAUZZZ...
  latitude: 47.3769
  longitude: 8.5417
  radius_m: 5000
  max_results: 25
response_variable: result
```

Plus d'exemples dans [`docs/FAQ.md`](docs/FAQ.md). Les cartes Lovelace personnalisées s'intègrent automatiquement via `extra_state_attributes.image_url`.

---

## Questions fréquentes

| Question | Réponse |
|---|---|
| Quand ma voiture est-elle réveillée ? | Uniquement lors des service-calls (Lock/Climate/Wake), jamais lors des status-polls. Plafond Smart-Wake : max 3 wakes/jour par voiture, cooldown 5 min. |
| Combien de quota API ? | MyCupra/MySeat : ~1500 calls/jour. À 10 min de polling : ~144 calls/jour = 10 % du budget. Le capteur `requests_remaining_today` indique l'état. |
| Pourquoi dois-je me reconnecter toutes les 2 h pour VW EU ? | Depuis le 2026-05-27, VW a placé l'endpoint token derrière Google Play Integrity. Cela touche toute intégration VAG basée sur Python. L'EU Data Act au 2026-09-12 devrait corriger ça. |
| Le token reste après une mise à jour HACS ? | Oui, depuis la v1.19.2 via la persistance du Store de HA. |
| Comment signaler des bugs ? | HA → Intégration → 🔧 Réparer → Bug-Report. Les diagnostics sont anonymisés (VIN masqués, GPS arrondi, tokens supprimés). |
| Les libellés de champs affichent des clés brutes (`brand`, `spin`) après une mise à jour ? | Rafraîchissement forcé du navigateur (Ctrl+Shift+R). HA met les traductions en cache côté client. |

FAQ complète dans [`docs/FAQ.md`](docs/FAQ.md). Dépannage des dashboards dans [`docs/dashboards.md`](docs/dashboards.md).

---

## Confidentialité & Sécurité

- Aucun service externe, tout passe directement entre HA et l'API constructeur
- Cache de tokens local dans le `.storage/` de HA (par config-entry, JSON, automatiquement supprimé à la suppression de l'intégration)
- Diagnostics anonymisés : VIN masqués, GPS arrondi à 1 décimale, tokens et mots de passe entièrement supprimés
- Reverse-geocoding en opt-in, désactivé par défaut
- Masquage des VIN systématique dans tous les logs
- Les URLs de token sont expurgées dans le log ERROR (v2.7.2+)

Détails dans [`PRIVACY.md`](PRIVACY.md) et [`SECURITY.md`](SECURITY.md).

---

## Contribuer

Les PR sont les bienvenues, voir [`CONTRIBUTING.md`](CONTRIBUTING.md). Règles de style dans [`STYLE.md`](STYLE.md) (en privé dans `_private/STYLE.md` pour les mainteneurs).

**Vehicle Data Scout** (live depuis la v1.9.0) : quand ton intégration détecte des champs JSON inconnus, elle crée automatiquement une notification HA Repair avec un lien d'issue GitHub pré-rempli. Rapport de bug en 1 clic, sans avoir à étudier le code.

---

## Licence

[Apache License 2.0](LICENSE) pour le code de l'intégration. [CC BY-NC-ND 4.0](LICENSE-RESEARCH) pour le contenu de `docs/research/`. Pour les attributions aux projets open-source amont, voir [`NOTICE.md`](NOTICE.md).
