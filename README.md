# MyTurboSelf for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![Version](https://img.shields.io/badge/version-v0.1.8-orange.svg)

Intégration personnalisée pour Home Assistant permettant de suivre votre compte TurboSelf (cantine/restauration scolaire).

<p align="center">
  <img src="https://raw.githubusercontent.com/kweebix/myturboself_ha/main/brand/logo.png" alt="MyTurboSelf Logo" width="200">
</p>

## Caractéristiques

- **Connexion directe** : Se connecte au portail TurboSelf sans dépendance externe.
- **Suivi précis** : Récupère le solde, le prix unitaire du repas et les informations du compte.
- **Planning intelligent** : Configurez vos repas (Petit-déjeuner, Midi, Soir) pour chaque jour de la semaine via des cases à cocher.
- **Calcul de fin prévisionnelle** : Estime la date à laquelle votre compte sera vide en prenant en compte :
  - Votre planning hebdomadaire.
  - Les **jours fériés** (France).
  - Les **vacances scolaires** (Zones A, B, C).
- **Optimisation des ressources** : Fréquence de mise à jour dynamique (toutes les 15 min en période de repas, toutes les 4h la nuit et pendant les vacances).
- **Lien de recharge direct** : Un bouton "Visiter l'appareil" dans Home Assistant vous redirige directement vers la page de recharge TurboSelf.
- **Blueprints** : Automatisation prête à l'emploi pour vous alerter quand le solde est bas.

## Capteurs disponibles

| Capteur | Description |
| --- | --- |
| **Solde** | Le montant disponible sur votre compte en €. |
| **Prix du repas** | Le prix d'un repas (détecté automatiquement ou forcé manuellement). |
| **Repas restants** | Le nombre de repas que vous pouvez encore prendre. |
| **Jours de service restants** | Le nombre de jours de cantine couverts par votre solde. |
| **Date de fin prévisionnelle** | Le premier jour où vous n'aurez plus assez de crédit pour vos repas. |

## Installation

### Via HACS (Recommandé)

1. Ouvrez **HACS** dans votre instance Home Assistant.
2. Cliquez sur les trois points en haut à droite et choisissez **Dépôts personnalisés**.
3. Ajoutez l'URL de ce dépôt, sélectionnez **Intégration** comme catégorie et cliquez sur **Ajouter**.
4. Recherchez et installez l'intégration **MyTurboSelf**.
5. Redémarrez Home Assistant.
6. Allez dans **Paramètres > Appareils et services > Ajouter une intégration**.
7. Recherchez **MyTurboSelf** et suivez les instructions.

### Manuelle

1. Copiez le dossier `custom_components/myturboself` dans votre dossier `config/custom_components/`.
2. Redémarrez Home Assistant.
3. Ajoutez l'intégration via l'interface utilisateur.

## Configuration

Lors de l'installation (ou via le bouton "Configurer"), vous pouvez :
- Choisir vos jours et types de repas (**Petit-déjeuner**, **Midi**, **Soir**).
- Activer/Désactiver l'ignorance des **jours fériés**.
- Activer/Désactiver l'ignorance des **vacances scolaires** et choisir votre **Zone (A, B, C)**.
- Définir un **prix de repas manuel** si la détection automatique échoue ou si vous souhaitez forcer un tarif spécifique.

## Blueprints (Modèles d'automatisation)

Cette intégration inclut un **Blueprint** pour vous faciliter la vie :
- **Alerte Solde TurboSelf Bas** : Recevez une notification (ou toute autre action de votre choix) quand votre solde descend sous un certain seuil.
  - Pour l'utiliser : Paramètres > Automatisations et scènes > Créer une automatisation > Utiliser un modèle > Alerte Solde TurboSelf Bas.

## Notes

- L'intervalle de mise à jour est de 15 minutes entre 06:00 et 23:00 les jours de repas.
- Il n'y a aucune logique de réservation dans cette intégration.
- Les données sont extraites directement du portail web TurboSelf.
