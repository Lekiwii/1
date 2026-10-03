# Pokémon Deals

Application PC qui repère les **cartes Pokémon gradées** (PSA, BGS, CGC, SGC, TAG…) vendues sous
leur cote, calcule la **marge de revente après frais** et donne un **indice de confiance** qui
croise plusieurs sources fiables. Les alertes arrivent aussi sur Telegram.

## L'application

`LANCER.bat` ouvre l'application dans ton navigateur (http://localhost:8765). Elle a 5 onglets :

- **Bonnes affaires** : chaque annonce rentable avec photo, prix d'achat port compris, cote,
  revente nette, bénéfice, tendance Cardmarket et indice de confiance (🟢 Fiable ≥ 70,
  🟡 À vérifier ≥ 45, 🔴 Risqué). « Pourquoi ? » détaille chaque point gagné ou perdu, et montre les
  prix de toutes les annonces comparables.
- **Estimer une carte** : pour une offre vue sur Vinted, Leboncoin, en salon… Entre la carte,
  la note, la langue et le prix : verdict, cote, marge, indice de confiance et liste des annonces
  comparables.
- **Tendances** : cartes recherchées (Illustration Rare, Alt Art, Secret…) dont le prix Cardmarket
  monte le plus. Un clic sur « Surveiller » les ajoute au scan.
- **Mes cartes** : les cartes surveillées, leur prix et leur tendance, et leurs recherches Vinted
  et Leboncoin toutes prêtes.
- **Réglages** : seuils, frais, budget, sites eBay scannés, fréquence du scan.

## D'où viennent les données

| Source | Rôle | Fiabilité |
|---|---|---|
| eBay (API officielle) | annonces à acheter, prix des annonces comparables | prix demandés, pas vendus : la médiane est minorée de 10 % |
| Cardmarket et TCGplayer, via [pokemontcg.io](https://pokemontcg.io) | identification de la carte, prix non gradé, tendance 1, 7 et 30 jours | prix de vente réels, cartes non gradées |
| PriceCharting (optionnel, payant) | cote gradée par note | ventes réelles, la plus fiable pour les cartes gradées |
| Reddit (optionnel, gratuit) | volume de discussions de la semaine par rapport au mois | signal d'intérêt du public, faible poids |

**Vinted et Leboncoin** n'ont pas d'accès officiel et interdisent les robots : l'application ne
lit pas leurs annonces. Elle prépare tes recherches (à sauvegarder dans leurs applis avec les
notifications), et l'onglet « Estimer une carte » te dit si une offre est rentable.

### L'indice de confiance

Il part de 20 et gagne ou perd des points selon :
- le nombre d'annonces comparables et l'homogénéité de leurs prix ;
- l'accord avec PriceCharting (si configuré) ;
- la cohérence avec le prix non gradé Cardmarket (une PSA 10 qui coterait moins que la carte non
  gradée est suspecte) ;
- la tendance du prix Cardmarket (une forte baisse rend la revente plus dure) ;
- le buzz Reddit (si configuré) ;
- l'ancienneté du vendeur et la langue indiquée dans le titre.

Seules les affaires au-dessus de `MIN_CONFIDENCE` (50 par défaut) déclenchent une alerte Telegram.
Les prix ne sont comparés qu'entre cartes **de même note, même langue et même édition**
(1st Edition ou non).

**Aucun indice ne garantit une revente.** Avant d'acheter, vérifie toujours le numéro de
certification sur le site de l'organisme, les photos du boîtier, la langue et l'édition, et
regarde les prix réellement vendus (eBay, filtre « Objets vendus »).

## Installation sur Windows (le plus simple)

1. Installe Python depuis [python.org](https://www.python.org/downloads/) en cochant
   **« Add python.exe to PATH »** (inutile si Python est déjà installé).
2. Dézippe `pokemon-bot.zip`, ouvre le dossier et double-clique sur **`LANCER.bat`**.
3. La première fois, un assistant te demande :
   - le token de ton bot Telegram : sur Telegram, ouvre [@BotFather](https://t.me/BotFather),
     envoie `/newbot` et suis les étapes ;
   - tes clés eBay **Production** (App ID et Cert ID), à créer gratuitement sur
     [developer.ebay.com](https://developer.ebay.com) ;
   - d'envoyer `/start` à ton bot : il reconnaît ton compte tout seul.

   Il vérifie chaque clé, puis enregistre tout dans `.env`. Ensuite, un double-clic sur
   `LANCER.bat` suffit. L'application s'ouvre dans ton navigateur, et les scans tournent tant
   que la fenêtre noire reste ouverte.

## Installation sur Mac ou Linux

```bash
cd pokemon-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py   # l'assistant de configuration se lance au premier démarrage
```

Pour qu'il tourne en permanence, lance-le sur un serveur ou un VPS (un service systemd ou un
conteneur, par exemple).

## Commandes Telegram

| Commande | Rôle |
|---|---|
| `/scan` | lancer un scan tout de suite ; s'il n'y a rien de nouveau, il renvoie les 5 meilleures affaires encore en ligne |
| `/statut` | vérifier que le bot tourne : heure du dernier scan et du prochain |
| `/liste` | cartes surveillées (10 cartes phares au départ) |
| `/ajouter Charizard ex 199/165` | surveiller une carte : mets le nom **et le numéro** pour éviter les mélanges |
| `/retirer Charizard ex 199/165` | ne plus la surveiller |
| `/regles` | seuils et frais utilisés |
| `/estimer Umbreon VMAX 215/203 PSA 10 650` | dit si une offre vue ailleurs (Vinted, Leboncoin, salon…) est rentable |
| `/liens` | recherches Vinted et Leboncoin prêtes pour y activer les alertes de l'appli |

## Réglages (`.env`)

La plupart se changent aussi dans l'onglet Réglages de l'application, qui a la priorité.


| Variable | Défaut | Rôle |
|---|---|---|
| `EBAY_MARKETPLACES` | `EBAY_FR,EBAY_DE` | sites eBay scannés |
| `MIN_PROFIT_EUR` / `MIN_ROI_PCT` | 30 / 15 | seuils d'alerte |
| `MIN_CONFIDENCE` | 50 | indice de confiance minimal pour une alerte |
| `POKEMONTCG_API_KEY` | vide | clé gratuite pokemontcg.io (plus de requêtes) |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | vide | buzz Reddit (clés gratuites, type « script ») |
| `WEB_PORT` | 8765 | port de l'application |
| `SELL_FEE_PCT` / `SELL_SHIPPING_EUR` | 13 / 8 | frais de ta revente |
| `MIN_SELLER_FEEDBACK_PCT` / `MIN_SELLER_FEEDBACK_SCORE` | 98 / 50 | fiabilité des vendeurs |
| `MIN_PRICE_EUR` / `MAX_PRICE_EUR` | 20 / 2000 | budget d'achat |
| `PRICECHARTING_TOKEN` | vide | cotes gradées fiables (payant) |
| `COMPS_DISCOUNT_PCT` | 10 | décote de la médiane des annonces |
| `USD_TO_EUR` / `GBP_TO_EUR` | 0.92 / 1.17 | conversion des annonces US / UK |

## Limites à connaître

- Une alerte n'est pas un achat garanti rentable. Avant d'acheter, vérifie toujours :
  - le numéro de certification sur le site de l'organisme (PSA :
    [psacard.com/cert](https://www.psacard.com/cert)) ;
  - que les photos montrent bien le boîtier annoncé ;
  - la langue et l'édition de la carte : une carte japonaise ou non 1st Edition vaut
    beaucoup moins.
- Sans PriceCharting, la cote gradée vient des prix demandés sur eBay, pas des prix vendus.
  L'indice de confiance le prend en compte, mais reste une estimation.
- La langue est lue dans le titre de l'annonce : sans mention, la carte est supposée anglaise.
- Avec PriceCharting, la carte est trouvée d'après ta recherche. Une recherche précise (nom,
  numéro, extension) évite de comparer avec la mauvaise carte.
- La fiscalité de la revente régulière (auto-entrepreneur, déclaration des plateformes) reste
  à ta charge.

## Tests

```bash
pip install pytest
python -m pytest
```
