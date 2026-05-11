# MyTurboSelf for Home Assistant

Cette base contient :

- une integration Home Assistant `custom_components/myturboself`

Le principe est simple :

1. l'integration se connecte directement au site web TurboSelf
2. elle recupere le solde et les informations utiles
3. elle calcule les capteurs Home Assistant

Il n'y a aucune dependance a la librairie non officielle `turboself`.

## Architecture

### Integration `myturboself`

L'integration Home Assistant se connecte directement au portail TurboSelf et calcule :

- `Balance`
- `Meal price`
- `Meals left`
- `Service days left`
- `Estimated empty date`

## Parametres de calcul

Dans les options de l'integration, tu peux definir :

- un prix manuel du repas
- le nombre de repas par jour pour chaque jour de la semaine

Le calcul suit cette logique :

- si un prix manuel est defini, il est prioritaire
- sinon le prix renvoye par TurboSelf est utilise
- `Meals left = floor(balance / prix_du_repas)` si un prix est connu
- sinon `meals_left` renvoye par TurboSelf est utilise
- `Service days left` et `Estimated empty date` suivent le planning hebdomadaire configure

## Installation

1. Copier `custom_components/myturboself` dans le dossier de configuration Home Assistant.
2. Redemarrer Home Assistant.
3. Aller dans `Settings > Devices & Services > Add Integration`.
4. Rechercher `MyTurboSelf`.
5. Entrer ton identifiant et ton mot de passe TurboSelf.

## Notes

- Intervalle de mise a jour Home Assistant : 15 minutes.
- Il n'y a aucune logique de reservation.
- Le scraping est fait directement par le custom component.
- Le depot contient la structure HACS minimale pour un repository de type `integration`.
