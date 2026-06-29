<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Une seule intégration Home Assistant pour les sept marques du groupe Volkswagen — Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · VW US/Canada</strong><br>
  <em>Accès direct à l'API, multi-canal avec repli automatique, sans intermédiaire.</em>
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
  🌍 <a href="README.md">English</a> · <a href="README.es.md">Español</a> · <a href="README.nl.md">Nederlands</a> · <a href="README.pl.md">Polski</a> · <a href="README.cs.md">Čeština</a> · <a href="README.sv.md">Svenska</a>
</p>

---

> ### 📛 À propos du changement de nom
> Publié auparavant sous le nom **`vag-connect-ha`** (VAG = Volkswagen AG, abréviation courante dans les pays germanophones).
> Sauf que cette abréviation se lit *un peu* différemment pour un anglophone 😅
>
> **Ce qui continue de fonctionner comme avant** : toutes les entités (par ex. `sensor.audi_q4_battery_soc`),
> tous les appels de service (`vag_connect.lock`, `vag_connect.show_vag`, etc.), toutes les automatisations,
> l'installation via HACS — **rien ne casse**. Seul le nom commercial/d'affichage change, les rouages internes
> du code restent identiques. Voir [`MIGRATION.md`](MIGRATION.md).
>
> Un grand merci aux communautés **Home Assistant UK** et **HA Ideas, Projects and Solutions**
> de m'avoir averti — en particulier **Si Gregory**, **Ben Johnson** et **Evets David**.
>
> Et un clin d'œil tout particulier à **Jordan Waeles**, dont le commentaire `show_vag()` est désormais un easter egg
> officiellement pris en charge par cette intégration (service `vag_connect.show_vag`, voir le CHANGELOG v2.2.3).

---

## C'est quoi, au juste ?

**VW Group Connect est une intégration [Home Assistant](https://www.home-assistant.io) qui fait entrer les données et le pilotage des voitures connectées dans votre maison intelligente, pour les sept marques du groupe Volkswagen — Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche et VW US/Canada — plus Bentley (lecture seule), depuis une seule entrée de configuration.**

Elle expose l'état de la batterie et de la charge, l'autonomie, le kilométrage, la climatisation, les portes et fenêtres, la localisation et bien plus, et — partout où le backend de la marque le permet encore — envoie des commandes à distance comme le verrouillage/déverrouillage, la climatisation et le pilotage de la charge. Pour continuer de fonctionner malgré les changements d'API de Volkswagen en 2026, elle parle **plusieurs canaux et bascule automatiquement** sur un autre dès que l'un est bloqué : les backends propres à chaque marque, le portail de données véhicule en lecture seule de l'**EU Data Act**, un canal web `volkswagen.de` activable à la demande, et une connexion **sans mot de passe** durable pour les anciens véhicules Car-Net. Elle cohabite sans souci **avec [evcc](https://evcc.io)** et ne réclame **aucune dépendance PyPI**.

> 🎉 **Désormais disponible directement dans HACS** — plus besoin de dépôt personnalisé.

---

## Points forts

- **Les 7 marques du groupe VW, dont Porsche et VW US/Canada** dans une seule intégration — le portail EU Data Act *exclut* structurellement Porsche, si bien que les outils basés uniquement sur le portail ne pourront jamais le couvrir.
- **Pilotage bidirectionnel** là où la marque l'autorise (verrouillage/déverrouillage, climatisation, charge, SoC cible) — pas seulement de la lecture.
- **Option de connexion sans mot de passe** (navigateur/device-code) — aucun mot de passe stocké dans Home Assistant.
- **Multi-canal avec repli automatique** — backend de la marque → portail EU Data Act → web vw.de activable → Car-Net durable. La panne d'un canal ne plonge pas vos données dans le noir.
- **Robuste par conception** — conserve les dernières valeurs connues pendant les pannes du portail, écarte les fausses valeurs sentinelles « aucune mesure », et n'autorise jamais le kilométrage à reculer.
- **Suivi de position GPS**, plus de 100 entités réparties sur 11 plateformes, plus de 20 appels de service, plusieurs véhicules par compte.
- **Vehicle Data Scout** — détecte automatiquement les dérives de l'API et propose un rapport de bug en un clic. **Quality Scale : Platinum.**

---

## État par marque

| Marque | Pilotage | Données | Remarques |
|---|---|---|---|
| **Audi** | ✅ Bidirectionnel | ✅ Complètes | backend myAudi |
| **Škoda** | ✅ Bidirectionnel | ✅ Complètes | backend Škoda natif |
| **Porsche** | ✅ Bidirectionnel | ✅ Complètes | Porsche Connect |
| **VW US/CA** | ✅ Bidirectionnel | ✅ Complètes | cloud VW NA |
| **VW EU** | ⚠️ Car-Net durable (modèles plus anciens) | ✅ EU Data Act + vw.de (bêta) | voitures ID/MEB récentes : lecture seule via le portail |
| **CUPRA / SEAT** | ⚠️ Limité | ✅ EU Data Act | backend de la marque verrouillé par VW depuis 2026 |
| **Bentley** | ⏳ En attente de test réel | ✅ Connexion + lecture | My Bentley — tourne sur la plateforme/le tenant Audi |

> En toute honnêteté : en 2026, Volkswagen a placé certaines parties de son API derrière une attestation d'appareil. Cette intégration contourne l'obstacle là où c'est possible (connexion Car-Net durable, portail EU Data Act, web vw.de) et joue la transparence sur ce que chaque canal sait faire — ou non.

---

## Limites connues

Quelques points sont **structurels** — ils tiennent au fonctionnement des backends de Volkswagen en 2026, pas à l'intégration, et aucun réglage n'y change quoi que ce soit :

- **Les voitures MEB / de la famille ID sont en lecture seule** (ID.3 / ID.4 / ID.5 / ID.7, Enyaq, Born, Q4 e-tron). Les commandes à distance — verrouillage, climatisation, charge — ne sont **pas disponibles** pour ces voitures : le chemin de commande Car-Net durable que nous utilisons ne les reconnaît pas (il répond « Unknown user »), et le backend MEB de VW n'expose aucun équivalent. Vous récupérez tout de même la télémétrie via le portail EU Data Act — mais aucun pilotage. La configuration détecte ce cas et crée une **entrée en lecture seule** au lieu d'échouer : c'est donc une limite assumée, pas un silence.
- **Les commandes à distance CUPRA / SEAT sont bloquées par VW.** L'accès aux services en ligne (OLA) de ces marques a été révoqué côté serveur en 2026 (HTTP 403) ; ni une reconnexion ni une mise à jour de la version de l'app ne le rétablira. Les données continuent toutefois de circuler via le portail EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Les données du portail EU Data Act sont maigres et varient d'une voiture à l'autre.** VW ne publie aujourd'hui qu'une partie des champs (souvent kilométrage + verrouillage + charge, parfois bien davantage). Cela s'élargit avec le temps, à mesure que VW étoffe le portail avant l'échéance de septembre 2026 — des champs qui affichent `unknown` aujourd'hui pourront se remplir d'eux-mêmes, sans rien changer. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))

---

## Installation

**Via HACS (recommandé) :**

1. Ouvrez **HACS** dans Home Assistant.
2. Recherchez **« VW Group Connect »** et installez-la.
3. Redémarrez Home Assistant.
4. Allez dans **Paramètres → Appareils et services → Ajouter une intégration → VW Group Connect** et suivez la procédure de connexion.

<sup>Tout juste intégrée au dépôt par défaut de HACS — si elle n'apparaît pas encore dans la recherche, laissez un peu de temps à l'index HACS pour se rafraîchir, ou ajoutez `its-me-prash/vwgroup-connect-ha` comme dépôt personnalisé en attendant.</sup>

**Options de connexion** (choisissez selon ce que votre voiture/marque prend en charge) :
- **Navigateur / device-code (sans mot de passe)** — connectez-vous sur votre téléphone ou votre ordinateur, validez l'appareil ; aucun mot de passe stocké. (Audi, Škoda, SEAT, CUPRA.)
- **E-mail + mot de passe** — requis pour Volkswagen EU et Porsche.
- **Portail EU Data Act** — repli en lecture seule pour toutes les marques.

---

## Ce que vous obtenez

- **Capteurs :** SoC de la batterie, autonomie (électrique / thermique / totale), niveau de carburant, kilométrage, températures, puissance/vitesse/type de charge, cible de charge, statistiques de trajet et cumuls sur toute la durée de vie, intervalles d'entretien et de vidange, version logicielle, état de la connexion, dernière communication, et plus encore.
- **Capteurs binaires :** portes verrouillées, portes/fenêtres/coffre/capot/toit ouvrant ouverts, câble branché, charge en cours, mise à jour OTA disponible, feux, véhicule en ligne, minuteries de départ, alarme.
- **Pilotage :** verrouillage/déverrouillage, démarrage/arrêt de la climatisation, démarrage/arrêt de la charge, dégivrage des vitres, minuteries de départ, réglage du SoC cible / de la température / du courant de charge maximal, klaxon-et-appels de phares, réveil, actualisation, recherche de bornes de recharge *(la disponibilité dépend de la marque et du modèle)*.
- **Suivi d'appareil :** position GPS pour la carte de Home Assistant.
- **Images :** rendus du véhicule, lorsque la marque les fournit.

> 💡 **Tableau de bord Énergie :** le capteur d'énergie chargée est de type `total_increasing` ; ajoutez-le donc directement au **tableau de bord Énergie** de Home Assistant, ou enveloppez-le dans une aide `utility_meter` pour obtenir les totaux d'énergie chargée par jour/par mois. Utilisez pour cela le capteur cumulatif **d'énergie chargée (kWh)** — et non les capteurs d'efficacité aux 100 km (ce sont des moyennes, pas des compteurs).

---

## Soutenir ce projet ❤️

C'est un projet mené par une seule personne — et VW ne facilite pas les choses : chaque changement de backend signifie des jours de rétro-ingénierie pour retrouver un chemin qui fonctionne. C'est cette ténacité qui le maintient en vie là où des projets bien établis ont jeté l'éponge. S'il a de la valeur à vos yeux, vous pouvez soutenir sa maintenance continue via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Merci ! 🙏

---

## Contribuer

Les PR sont les bienvenues — voir [`CONTRIBUTING.md`](CONTRIBUTING.md). Le **Vehicle Data Scout** transforme les champs d'API inconnus en un rapport de bug pré-rempli, en un clic : vous pouvez ainsi aider à élargir la couverture sans lire une ligne de code.

## Licence

[GNU AGPL v3.0-or-later](LICENSE) pour le code de l'intégration. Attribution obligatoire + conditions sur le nom/la marque en cas d'utilisation ou de fork : voir [`ATTRIBUTION.md`](ATTRIBUTION.md). Attributions open source en amont dans [`NOTICE.md`](NOTICE.md).