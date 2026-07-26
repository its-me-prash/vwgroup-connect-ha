<p align="center">
  <img src="https://raw.githubusercontent.com/its-me-prash/vwgroup-connect-ha/main/custom_components/vag_connect/logo.png" alt="VW Group Connect" width="180">
</p>

<h1 align="center">VW Group Connect</h1>

<p align="center">
  <strong>Une seule intégration Home Assistant pour les voitures du groupe Volkswagen : Audi · Volkswagen · Škoda · SEAT · CUPRA · Porsche · Bentley · VW et Audi US/Canada</strong><br>
  <em>Batterie, charge, autonomie, portes, climatisation et position GPS dans Home Assistant. Accès direct à l'API, plusieurs canaux de lecture avec bascule automatique, sans middleware.</em>
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

> ### 📛 Note sur le renommage
> Auparavant publié sous le nom **`vag-connect-ha`** (VAG = Volkswagen AG, abréviation standard dans l'espace DACH).
> Il s'avère que cette abréviation se lit *assez* différemment pour les anglophones 😅
>
> **Ce qui continue de fonctionner comme avant** : toutes les entités (p. ex. `sensor.audi_q4_battery_soc`),
> tous les appels de service (`vag_connect.lock`, `vag_connect.show_vag`, etc.), toutes les automatisations,
> l'installation via HACS — **rien ne casse**. C'est le nom marketing/d'affichage qui change, les rouages internes
> du code restent inchangés. Voir [`MIGRATION.md`](MIGRATION.md).
>
> Un grand merci aux communautés **Home Assistant UK** et **HA Ideas, Projects and Solutions**
> pour l'avoir signalé — en particulier **Si Gregory**, **Ben Johnson** et **Evets David**.
>
> Et un clin d'œil tout particulier à **Jordan Waeles**, dont le commentaire `show_vag()` est désormais un easter egg
> officiellement pris en charge dans cette intégration (service `vag_connect.show_vag`, voir CHANGELOG v2.2.3).

---

## Qu'est-ce que c'est ?

**VW Group Connect est une intégration [Home Assistant](https://www.home-assistant.io) qui amène votre voiture du groupe Volkswagen dans votre maison intelligente : état de la batterie et de la charge, autonomie, compteur kilométrique, climatisation, portes et vitres, position GPS et bien plus, pour Volkswagen, Audi, Škoda, SEAT, CUPRA, Porsche, Bentley et les comptes VW / Audi nord-américains, le tout à partir d'une seule entrée de configuration.**

Là où le backend de la marque le permet encore, elle envoie aussi des commandes à distance telles que le verrouillage/déverrouillage, le contrôle de la climatisation et de la charge. **Cela dépend de la marque, ce n'est pas universel :** Audi et Škoda sont bidirectionnels, Volkswagen EU via le portail EU Data Act est en lecture seule, et les commandes SEAT/CUPRA sont bloquées par le constructeur. Le tableau ci-dessous indique précisément ce qu'il en est.

Pour continuer à fonctionner malgré les changements d'API de Volkswagen en 2026, elle parle **plusieurs canaux de lecture et bascule automatiquement** lorsque l'un d'eux est bloqué : les backends natifs des marques, le portail de données véhicule **EU Data Act** en lecture seule, un canal web `volkswagen.de` activable à la demande (bêta), un complément **Tibber** facultatif, et une connexion **sans mot de passe** durable pour les véhicules Car-Net plus anciens. Elle tourne sans souci **aux côtés d'[evcc](https://evcc.io)** (voir [docs/EVCC.md](docs/EVCC.md)) et ne nécessite **ni add-on, ni broker, ni conteneur intermédiaire**. Home Assistant installe automatiquement deux petits paquets Python ; ils ne servent qu'aux canaux push facultatifs.

> 🎉 **Désormais disponible directement dans HACS** — aucun dépôt personnalisé requis.

---

## Points forts

- **9 marques sélectionnables du groupe Volkswagen** dans une seule intégration : Audi, Volkswagen EU, Škoda, SEAT, CUPRA, VW US/Canada, Audi US/Canada, Porsche et Bentley.
- **Contrôle bidirectionnel là où le backend de la marque le permet** : verrouillage/déverrouillage, climatisation, charge, SoC cible. Cela dépend **de la marque, ce n'est pas universel**. Consultez le tableau ci-dessous avant de compter sur une commande.
- **Option de connexion sans mot de passe** (navigateur/code d'appareil) pour Audi, Škoda, SEAT, CUPRA et Audi US/CA. Aucun mot de passe n'est stocké dans Home Assistant.
- **Multicanal avec bascule automatique** : backend natif de la marque, portail EU Data Act, web vw.de activable à la demande, Tibber en option, Car-Net durable. Si un canal tombe, vos données ne s'éteignent pas pour autant.
- **Résilient par conception** : conserve les dernières valeurs connues et la dernière position de stationnement pendant les pannes du portail, filtre les fausses sentinelles « aucune lecture », ne laisse jamais le compteur kilométrique reculer, et vous dit quand un échec de connexion vient d'une panne chez le constructeur plutôt que de votre mot de passe.
- **Vous maîtrisez la fréquence d'interrogation** : un **curseur d'intervalle d'interrogation** par compte (une entité Number, en minutes) pilotable par une automatisation, créé pour toutes les installations, y compris celles en lecture seule via le portail.
- **Traqueur GPS**, plus de 100 entités réparties sur plusieurs plateformes, plus de 20 appels de service, plusieurs véhicules par compte, noms d'entités en **12 langues**.
- **Porsche tourne sur son propre backend**, pas sur le portail EU Data Act. Le chemin par le portail *exclut* structurellement Porsche, si bien que les outils qui ne reposent que sur le portail ne pourront jamais le couvrir. Le code des commandes est ici, mais la connexion Porsche elle-même est actuellement expérimentale (voir le tableau).
- **Vehicle Data Scout** détecte automatiquement les dérives d'API et propose un rapport de bug en un clic. **Quality Scale : Platinum.**

---

## État des marques

| Marque | Contrôle | Données | Remarques |
|---|---|---|---|
| **Audi** (EU) | ✅ Bidirectionnel | ✅ Complet | backend myAudi (incl. démarrage/arrêt moteur thermique) |
| **Škoda** | ✅ Bidirectionnel | ✅ Complet | backend Škoda natif |
| **VW US/CA** | ✅ Bidirectionnel | ✅ Complet | cloud VW NA (nécessite le sélecteur de pays US/CA + S-PIN). ⚠️ Le service de connexion de VW répond actuellement par une erreur serveur à certaines connexions canadiennes : c'est une panne côté VW, pas un mauvais mot de passe ([#915](https://github.com/its-me-prash/vwgroup-connect-ha/issues/915)) |
| **VW EU** | 🔒 Lecture seule par défaut · ⚠️ commandes = MBB **alpha** | ✅ Télémétrie complète via le portail EU Data Act | Voir la note honnête ci-dessous ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)) |
| **CUPRA / SEAT** | ⛔ Commandes bloquées par VW | ✅ Portail EU Data Act | Accès OLA révoqué côté serveur en 2026 ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464)) |
| **Bentley** | ⏳ Bidirectionnel sous réserve de test en conditions réelles | ✅ Connexion + lecture | My Bentley, tourne sur le tenant Audi/IDK |
| **Porsche** | ⚠️ Expérimental | ⚠️ Expérimental | Porsche Connect, backend propre. Porsche est passé à l'application *Porsche One*, la **connexion échouera donc probablement sur les comptes actuels**. Le code des commandes est présent mais inaccessible tant que la connexion n'est pas reconstruite ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666)) |
| **Audi US/CA** | ⚠️ Expérimental | ⚠️ Expérimental | La connexion est câblée sur le fournisseur d'identité nord-américain mais **pas encore confirmée** sur un compte US/CA réel. Testeurs bienvenus ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)) |

> **Note honnête sur le contrôle VW EU.** Les véhicules Volkswagen EU sont **en lecture seule par défaut** : vous obtenez une télémétrie complète via le portail EU Data Act, mais aucune commande à distance. Les commandes à distance pour VW EU n'existent **que sous forme d'ALPHA bidirectionnelle durable expérimentale via MBB**, et uniquement pour les voitures **MQB / Car-Net héritées** — c'est une bascule activable à la demande, **pas** une fonctionnalité par défaut. **Les voitures MEB / famille ID (ID.3/4/5/7, Enyaq, Born, Q4 e-tron) n'ont aucun chemin de commande** et sont créées en lecture seule. L'alpha MBB est suivie dans **[#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)** — les testeurs sont les bienvenus.

> En 2026, Volkswagen a placé certaines parties de son API derrière une attestation d'appareil. Cette intégration contourne cela lorsque c'est possible (connexion Car-Net durable, portail EU Data Act, web vw.de) et reste transparente sur ce que chaque canal peut et ne peut pas faire.

---

## Limites connues

Quelques aspects sont **structurels** — ils découlent du fonctionnement des backends de Volkswagen en 2026, pas de l'intégration, et aucun réglage ne les corrige :

- **VW EU est en lecture seule par défaut ; les commandes sont une alpha MBB réservée aux voitures héritées.** Voir la note sur la marque ci-dessus. **Les voitures MEB / famille ID sont en lecture seule** — le chemin de commande Car-Net durable ne les reconnaît pas (il répond « Unknown user »), et le backend MEB de VW n'expose aucun équivalent. La configuration détecte cela et crée une **entrée en lecture seule** (avec un avis de réparation) au lieu d'échouer, ce qui en fait une limite connue, pas silencieuse. ([#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584))
- **Les commandes à distance CUPRA / SEAT sont bloquées par VW.** L'accès aux services en ligne (OLA) pour ces marques a été révoqué côté serveur en 2026 (HTTP 403) ; une reconnexion ou une mise à jour de la version de l'app ne le restaurera pas. Les données circulent toujours via le portail EU Data Act. ([#464](https://github.com/its-me-prash/vwgroup-connect-ha/issues/464))
- **Les données du portail EU Data Act sont parcellaires et varient d'une voiture à l'autre.** VW ne publie aujourd'hui qu'une partie des champs (souvent compteur kilométrique + verrouillage + charge, parfois bien plus). Cette part s'élargit avec le temps à mesure que VW étend le portail avant l'échéance de septembre 2026 — des champs affichant `unknown` aujourd'hui pourront se remplir d'eux-mêmes, sans aucune modification. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465))
- **L'Amérique du Nord est expérimentale.** La connexion **Audi US/CA** est câblée mais n'a jamais été confirmée sur un compte réel ([#13](https://github.com/its-me-prash/vwgroup-connect-ha/issues/13)). **VW US/CA** fonctionne, mais le service de connexion de VW renvoie actuellement des erreurs serveur pour certains comptes canadiens ([#915](https://github.com/its-me-prash/vwgroup-connect-ha/issues/915)). Ne choisissez pas cette intégration pour une voiture nord-américaine en vous attendant à ce qu'elle fonctionne d'emblée.
- **La connexion Porsche échouera probablement pour l'instant.** Porsche a retiré l'application *My Porsche*, auprès de laquelle cette intégration s'authentifie, au profit de *Porsche One*. La lecture et les commandes sont implémentées, mais vous ne passerez probablement pas la connexion tant que celle-ci n'aura pas été reconstruite. ([#666](https://github.com/its-me-prash/vwgroup-connect-ha/issues/666))
- **Les mises à jour push (quasi temps réel) sont une BÊTA facultative, désactivée par défaut.** Les canaux MQTT (Škoda) et Firebase (Audi/VW, CUPRA/SEAT) sont câblés mais pas validés en conditions réelles, et les marques les protègent de plus en plus par une attestation d'application impossible à satisfaire hors de l'appareil. Laissez-les désactivés sauf si vous voulez aider à les tester. L'interrogation classique reste le chemin pris en charge.

> **Où nous en sommes.** En vertu de l'EU Data Act (Règlement (UE) 2023/2854), les données de votre voiture vous *appartiennent*. Faire tourner cette intégration sur votre propre matériel, c'est *vous* qui accédez à *vos propres* données (Article 4) — dues à la même qualité que celle dont le constructeur se sert lui-même, en temps réel lorsque cela est techniquement possible. Le portail de VW, en lecture seule et vieux de plusieurs heures, n'est pas à la hauteur aujourd'hui. Cette intégration est délibérément **agnostique quant au canal** : dès l'instant où VW offrira aux propriétaires une interface en temps réel et capable de commande — comme l'exige le Data Act, et comme certains constructeurs le proposent déjà à leurs propriétaires — nous la prendrons en charge ici, gratuitement, pour tout le monde. Nous défendons votre droit à un accès en temps réel à votre propre voiture.

---

## Installation

**Via HACS (recommandé) :**

1. Ouvrez **HACS** dans Home Assistant.
2. Recherchez **« VW Group Connect »** et installez-le.
3. Redémarrez Home Assistant.
4. Allez dans **Paramètres → Appareils et services → Ajouter une intégration → VW Group Connect** et suivez le flux de connexion.

<sup>Tout juste intégré à HACS par défaut — s'il n'apparaît pas encore dans la recherche, laissez un peu de temps à l'index HACS pour se rafraîchir, ou ajoutez `its-me-prash/vwgroup-connect-ha` comme dépôt personnalisé en attendant.</sup>

**Home Assistant minimum : `2024.4.0`.**

### Options de connexion (l'assistant de configuration propose deux chemins)

Le premier écran de l'intégration propose **deux** méthodes de connexion. Choisissez celle que votre marque prend en charge :

- **Navigateur / code d'appareil (sans mot de passe)** pour *Audi, Škoda, SEAT, CUPRA et Audi US/CA (expérimental)*. Connectez-vous sur votre téléphone ou votre ordinateur portable et approuvez l'appareil ; aucun mot de passe n'est stocké dans Home Assistant (il conserve un vrai jeton de rafraîchissement). Cette étape propose aussi le **S-PIN** facultatif et l'intervalle de scan.
- **Portail, e-mail + mot de passe** pour *Volkswagen EU, Volkswagen US/CA, Bentley et Porsche (expérimental)*. Saisissez les identifiants de votre marque. Cette étape expose un sélecteur de marque, e-mail, mot de passe, **S-PIN** facultatif, intervalle de scan et une bascule **« activer les commandes MBB »** (qui n'a d'effet que sur Volkswagen EU, voir [#584](https://github.com/its-me-prash/vwgroup-connect-ha/issues/584)). Pour **Volkswagen US/Canada**, un **sélecteur de pays (US ou CA)** apparaît ici ; il ne s'affiche **que** pour cette marque et n'est utilisé par aucune autre.

> Le **portail EU Data Act n'est pas un troisième bouton de connexion.** C'est la stratégie en lecture seule vers laquelle le coordinateur bascule automatiquement, et qui peut en outre être *ajoutée* comme canal de lecture supplémentaire depuis **Configurer → Options**. Il en va de même du canal web `volkswagen.de` (bêta activable à la demande, disponible uniquement via les Options, en lecture seule) et du canal **Tibber** facultatif, qui comble les champs laissés vides par les canaux de première partie et n'écrase jamais une donnée plus récente.

### Le champ S-PIN — quand vous en avez besoin

Le **S-PIN** est le code de sécurité de l'application de votre marque. Il est facultatif dans le formulaire et n'est requis que pour certaines actions : il est nécessaire pour **les lectures de données et les commandes de VW US/Canada**, ainsi que pour les commandes à distance sensibles sur le plan de la sécurité, sur les marques qui les protègent par S-PIN. Laissez-le vide si votre voiture n'en demande pas.

---

### Volkswagen EU — faire circuler vos données (important)

Pour Volkswagen EU, **se connecter ne suffit pas** — VW ne diffuse les données du véhicule qu'une fois que *vous* avez activé le partage des données du côté de VW. Si votre voiture apparaît sans données (ou n'apparaît pas du tout), c'est presque toujours la raison, **pas** un mot de passe erroné. Faites ceci une fois :

1. **Ajoutez l'intégration :** choisissez **Portail (e-mail + mot de passe)**, sélectionnez **Volkswagen EU**, puis connectez-vous.
2. **Effectuez toute invite unique sur le portail de VW.** Ouvrez une fois le portail de données VW dans un navigateur ou l'application de la marque et terminez tout ce qu'il demande : **accepter les conditions, confirmer le consentement, finaliser l'inscription / la sélection de région.** Un accès sans interface ne peut pas franchir ces étapes — c'est le cas `portal_interaction_required` ([#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527)).
3. **Accordez le consentement au partage des données.** Sur le portail, réglez **« Utilisation des données non personnelles » = Accordé** (le consentement de partage des données EU Data Act).
4. **N'allez pas chercher une bascule « demande de données continue » — elle n'existe pas.** L'intégration crée elle-même cette demande pour chaque voiture. Elle enregistre un abonnement d'un mois sur votre compte VW, qui est **gratuit**. Sans demande, le portail ne renvoie rien pour ce VIN et le véhicule apparaît sans aucune lecture.
5. **Attendez que la voiture pousse un instantané.** Même après tout ce qui précède, la propagation prend du temps. La voiture peut afficher **`offline` / `unknown` pendant un certain temps — souvent jusqu'à son prochain trajet ou réveil, jusqu'à environ 24 h** — avant que les capteurs ne se remplissent. C'est normal.

Le portail ne sert au départ qu'une **partie des champs**, et cette part **s'élargit avec le temps** à mesure que VW étend la couverture du portail avant l'échéance de septembre 2026 — des champs affichant `unknown` aujourd'hui pourront se remplir d'eux-mêmes. ([#465](https://github.com/its-me-prash/vwgroup-connect-ha/issues/465) · [#527](https://github.com/its-me-prash/vwgroup-connect-ha/issues/527) · [#567](https://github.com/its-me-prash/vwgroup-connect-ha/issues/567))

> **Liste complète des champs.** Le dictionnaire de données officiel du groupe VW (chaque clé EU Data Act -> champ, description et unité) se trouve dans [docs/EU_DATA_ACT_DATA_DICTIONARY.md](docs/EU_DATA_ACT_DATA_DICTIONARY.md). Un workflow hebdomadaire surveille la page du dictionnaire du portail et ouvre une pull request dès que VW publie une version plus récente, pour que le tableau ne devienne pas silencieusement obsolète.

> C'est la bascule des Options **`eu_data_act_auto_kickoff`** qui crée cette demande de données personnalisée de 15 minutes, et elle est **activée par défaut** — en mode portail, sans elle, il n'y a pas de données. Ne la désactivez que si vous préférez gérer la demande vous-même.

---

## Ce que vous obtenez

- **Capteurs :** SoC de la batterie, autonomie (électrique / thermique / totale), niveau de carburant, compteur kilométrique, températures, puissance de charge, débit de charge (toujours en km/h, converti si votre voiture rapporte en mph) et type de charge, cible de charge, statistiques de trajet et cumuls sur la durée de vie, intervalles d'entretien et de vidange, version logicielle, état de connexion, dernière vue, et plus encore.
- **Capteurs binaires :** portes verrouillées, portes/vitres/coffre/capot/toit ouvrant ouverts, prise branchée, en charge, mise à jour OTA disponible, feux, véhicule en ligne, minuteries de départ, alarme.
- **Contrôle :** verrouillage/déverrouillage, démarrage/arrêt de la climatisation, démarrage/arrêt de la charge, chauffage des vitres, minuteries de départ, réglage du SoC cible / de la température / du courant de charge maximal, klaxon-et-appel de phares, réveil, rafraîchissement, recherche de bornes de recharge *(la disponibilité dépend de la marque et du modèle)*.
- **Traqueur d'appareil :** position GPS pour la carte de Home Assistant. Une interrogation qui revient sans coordonnées conserve la dernière position de stationnement connue au lieu de la perdre.
- **Images :** rendus du véhicule lorsque la marque les fournit.
- **Réglages :** un curseur d'**intervalle d'interrogation** par compte, en minutes, pour qu'une automatisation interroge plus souvent pendant que vous roulez et lève le pied la nuit. Il existe dans toutes les installations, y compris les entrées portail en lecture seule.
- **12 langues :** les noms d'entités sont entièrement traduits en anglais, allemand, français, espagnol, italien, néerlandais, polonais, tchèque, suédois, danois, norvégien et finnois.

> 💡 **Tableau de bord Énergie :** le capteur d'énergie chargée est `total_increasing`, vous pouvez donc l'ajouter directement au **tableau de bord Énergie** de Home Assistant, ou l'envelopper dans un assistant `utility_meter` pour obtenir des totaux d'énergie chargée quotidiens/mensuels. Utilisez pour cela le capteur cumulatif **d'énergie chargée (kWh)** — pas les capteurs d'efficacité aux 100 km (ce sont des moyennes, pas des compteurs).

### Services

L'intégration fournit **plus de 20 appels de service** (`vag_connect.*`), dont beaucoup sont spécifiques à une marque — *la disponibilité dépend de la marque et du modèle*. Parmi eux : `lock` / `unlock`, `start_climatisation` / `stop_climatisation`, `start_charging` / `stop_charging`, `set_target_soc`, `set_climatisation_temperature`, `set_departure_timer`, `start_window_heating` / `stop_window_heating`, `flash_lights`, `wake_vehicle`, `refresh_vehicle`, `refresh_cloud_cache`, `find_charging_stations`, `start_climate_control`, `engine_start` / `engine_stop` (Audi thermique), `start_ventilation` / `stop_ventilation`, `start_aux_heating` / `stop_aux_heating` (Webasto SEAT/CUPRA), `send_destination` et `update_charging_settings` (SEAT/CUPRA), `open_app`, `execute_vehicle_action`, `abrp_send`, et l'easter egg `show_vag`.

---

## evcc

[evcc](https://evcc.io) peut récupérer l'état de charge, l'autonomie et le statut de charge de votre voiture directement depuis Home Assistant, pour que la charge sur surplus solaire se base sur la batterie réelle plutôt que sur une estimation. Rien de plus ne tourne dans l'intégration : evcc lit l'API REST de Home Assistant. Le chemin de **lecture** fonctionne sur **toutes les marques**, y compris les voitures VW EU / portail en lecture seule. Le chemin d'**écriture** (`chargeEnable`) ne fonctionne que sur une voiture bidirectionnelle (Audi ou Škoda avec un canal de commande actif) et uniquement si evcc traite la voiture elle-même comme le point de charge. Avec une vraie borne intelligente, le chemin de lecture suffit à evcc.

Des recettes `evcc.yaml` prêtes à l'emploi et la configuration initiale sont dans [docs/EVCC.md](docs/EVCC.md). Ce connecteur est en **bêta**.

---

## Télémétrie en direct ABRP (A Better Routeplanner)

Vous pouvez envoyer les données en direct de votre voiture vers **[A Better Routeplanner](https://abetterrouteplanner.com/)** afin qu'il planifie en fonction de votre état de charge réel. C'est **activable à la demande et désactivé par défaut** — rien ne quitte votre réseau tant que vous ne l'avez pas activé et qu'un envoi ne s'est pas réellement exécuté.

**1. Obtenez les deux identifiants.**

- **`token`** (par véhicule) — ouvrez l'application ABRP → **Settings → votre voiture → Live Data → « Generic » / autre voiture** et copiez le token affiché.
- **`api_key`** (clé développeur) — il s'agit d'une clé partenaire/développeur délivrée par **iternio**, *pas* de quelque chose que l'application fournit. Demandez-la à iternio (leur formulaire de demande de clé développeur/API). **Nous ne fournissons délibérément aucune clé** — en coder une en dur que nous ne possédons pas constituerait une usurpation et inscrirait un secret non possédé dans un dépôt public. Collez la vôtre.

**2. Activez-la.** Intégration → **Configurer** → faites défiler jusqu'à la section **ABRP** → cochez *Enable ABRP telemetry push* et collez les deux valeurs. Elles sont validées par paire (vous obtiendrez une erreur si une seule est renseignée), stockées masquées et **jamais écrites dans le journal**.

**3. Automatisez l'envoi.** Importez le blueprint fourni **« ABRP — upload telemetry on data change »** (`blueprints/automation/vag_connect/abrp_upload_on_data_change.yaml`), choisissez votre véhicule et son capteur **ABRP data changed**, et c'est terminé. Le blueprint n'envoie que lorsqu'il y a un instantané réellement nouveau (le capteur binaire *ABRP data changed* est le déclencheur idempotent — il se réinitialise après chaque envoi réussi, si bien que le même instantané n'est jamais envoyé deux fois).

Vous pouvez aussi appeler directement le service **`vag_connect.abrp_send`** (ciblez un appareil ou un VIN ; l'api_key/token proviennent des options sauf si vous les passez en ligne).

> 🔒 **Confidentialité :** la télémétrie inclut le GPS. Elle ne quitte votre réseau que lorsque `abrp_send` s'exécute (c.-à-d. lorsque *vous* le déclenchez / activez le blueprint). Ce que nous envoyons : état de charge, état de la charge, GPS, cap, énergie + capacité, autonomie estimée, température ambiante + batterie, compteur kilométrique. Ce que nous **n'envoyons** délibérément pas : tout ce que nous ne pouvons pas mesurer de façon fiable (vitesse, tension/courant du pack HT, état de santé) — omis plutôt que deviné.

---

## Options (Configurer)

Depuis **Paramètres → Appareils et services → VW Group Connect → Configurer**, vous pouvez ajuster :
intervalle de scan (également disponible en direct via le curseur d'intervalle d'interrogation), S-PIN (ainsi qu'un S-PIN par véhicule lorsque le compte comporte plusieurs voitures), géocodage inverse, **mode lecture seule**, forçage de la climatisation PPE (Audi), bascules de push (MQTT/FCM/Audi-VW, toutes en bêta facultative et désactivées par défaut), surcharge du client-id, **`eu_data_act_auto_kickoff`** (activé par défaut), masquer les entités vides (activé par défaut), **ABRP** (activation + api_key + jeton utilisateur, validés par paire), ainsi que l'**ajout / la suppression** des canaux de lecture supplémentaires : `volkswagen.de` (bêta), portail EU Data Act et **Tibber**.

---

## Soutenez ce projet ❤️

C'est un projet mené par une seule personne — et VW ne facilite pas la tâche : chaque changement de backend signifie des jours de rétro-ingénierie pour retrouver un chemin fonctionnel. C'est cette persévérance qui maintient le projet en vie là où des projets établis ont abandonné. Si cela a de la valeur à vos yeux, vous pouvez soutenir la maintenance continue via **[GitHub Sponsors](https://github.com/sponsors/its-me-prash)**. Merci ! 🙏

---

## Contribuer

Les PR sont les bienvenues, voir [`CONTRIBUTING.md`](CONTRIBUTING.md). Les questions fréquentes sont traitées dans [docs/FAQ.md](docs/FAQ.md). Le **Vehicle Data Scout** transforme les champs d'API inconnus en un rapport de bug pré-rempli, en un clic, pour que vous puissiez aider à améliorer la couverture sans lire de code.

## Licence

[GNU AGPL v3.0-or-later](LICENSE) pour le code de l'intégration. Conditions obligatoires d'attribution + nom/marque en cas d'utilisation/fork : voir [`ATTRIBUTION.md`](ATTRIBUTION.md). Attributions open-source amont dans [`NOTICE.md`](NOTICE.md).
