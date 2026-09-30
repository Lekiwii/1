# Bot deals Pokémon

Bot Telegram qui surveille les annonces eBay de **cartes Pokémon gradées** (PSA, BGS, CGC, SGC, TAG…),
compare leur prix à la cote du marché et t'envoie celles qui laissent une marge de revente
**après frais**.

## Ce qu'il fait

1. Toutes les `SCAN_INTERVAL_MIN` minutes, pour chaque carte de ta liste, il cherche sur eBay
   (FR, DE, UK, US… au choix) les annonces en achat immédiat, à l'état « Gradée ».
2. Il garde uniquement les cartes vérifiées : une note d'un organisme de gradation reconnu dans le
   titre, et aucun mot suspect (proxy, custom, lot, boîtier vide, « PSA ready », non gradée…).
3. Il écarte les vendeurs peu fiables (moins de 98 % d'avis positifs ou moins de 50 avis, réglable).
4. Il calcule la cote de la carte **pour la même note** :
   - avec [PriceCharting](https://www.pricecharting.com/api-documentation) si tu as un token
     (prix réellement vendus pour PSA 10, BGS 9.5, CGC 10…) ;
   - sinon, avec la médiane des annonces comparables (même carte, même organisme, même note),
     sans les valeurs aberrantes et minorée de 10 %, parce qu'un prix demandé est plus haut
     qu'un prix vendu.
5. Il calcule le bénéfice : `cote × (1 − commission) − envoi − prix d'achat port compris`.
   Si le bénéfice dépasse `MIN_PROFIT_EUR` **et** que le ROI dépasse `MIN_ROI_PCT`, tu reçois l'alerte.
   Une annonce n'est signalée qu'une fois, ou de nouveau si son prix baisse.

Exemple d'alerte :

```
🔥 Umbreon VMAX 215/203 Evolving Skies PSA 10 GEM MINT
🏷 PSA 10 · EBAY_DE · vendeur cardshop (99.9 %, 2140 avis)
💶 Achat : 890.00 € port compris
📈 Cote : 1260.00 € (médiane de 14 annonces PSA 10)
💰 Revente nette : 1088.20 € → +198.20 € (+22 %)
```

## Installation

Il faut Python 3.10 ou plus récent.

```bash
cd pokemon-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Puis remplis `.env` :

1. **Telegram** : parle à [@BotFather](https://t.me/BotFather), `/newbot`, et copie le token dans
   `TELEGRAM_TOKEN`.
2. **eBay** : crée un compte sur [developer.ebay.com](https://developer.ebay.com), puis un jeu de clés
   **Production**. Copie l'App ID dans `EBAY_CLIENT_ID` et le Cert ID dans `EBAY_CLIENT_SECRET`.
   L'API Browse est gratuite (5 000 appels par jour).
3. Lance `python bot.py` et envoie `/start` au bot sur Telegram. Il répond avec ton identifiant :
   mets-le dans `TELEGRAM_CHAT_ID`, puis relance le bot. Seul ce compte peut utiliser le bot et
   recevoir les alertes.

Pour qu'il tourne en permanence, lance-le sur un serveur ou un VPS (`nohup python bot.py &`,
un service systemd, ou un conteneur).

## Commandes

| Commande | Rôle |
|---|---|
| `/scan` | lancer un scan tout de suite |
| `/liste` | cartes surveillées (10 cartes phares au départ) |
| `/ajouter Charizard ex 199/165` | surveiller une carte : mets le nom **et le numéro** pour éviter les mélanges |
| `/retirer Charizard ex 199/165` | ne plus la surveiller |
| `/regles` | seuils et frais utilisés |

## Réglages (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `EBAY_MARKETPLACES` | `EBAY_FR,EBAY_DE` | sites eBay scannés |
| `MIN_PROFIT_EUR` / `MIN_ROI_PCT` | 30 / 15 | seuils d'alerte |
| `SELL_FEE_PCT` / `SELL_SHIPPING_EUR` | 13 / 8 | frais de ta revente |
| `MIN_SELLER_FEEDBACK_PCT` / `MIN_SELLER_FEEDBACK_SCORE` | 98 / 50 | fiabilité des vendeurs |
| `MIN_PRICE_EUR` / `MAX_PRICE_EUR` | 20 / 2000 | budget d'achat |
| `PRICECHARTING_TOKEN` | vide | cotes gradées fiables (payant) |
| `COMPS_DISCOUNT_PCT` | 10 | décote de la médiane des annonces |
| `USD_TO_EUR` / `GBP_TO_EUR` | 0.92 / 1.17 | conversion des annonces US / UK |

## Sources de vente

- **eBay** : branché, via l'API officielle.
- **Cardmarket** : son API est réservée aux vendeurs professionnels approuvés. Si tu obtiens un
  accès, il suffit d'ajouter un client qui renvoie des `Listing` comme `pokedeals/ebay.py`.
- **TCGplayer** : l'API n'accepte plus de nouveaux développeurs.
- **Vinted, Leboncoin, Facebook Marketplace** : pas d'API publique, et leurs conditions
  d'utilisation interdisent le scraping. Le bot ne les scrape donc pas.

## Limites à connaître

- Une alerte n'est pas un achat garanti rentable. Avant d'acheter, vérifie toujours :
  - le numéro de certification sur le site de l'organisme (PSA :
    [psacard.com/cert](https://www.psacard.com/cert)) ;
  - que les photos montrent bien le boîtier annoncé ;
  - la langue et l'édition de la carte : une carte japonaise ou non 1st Edition vaut
    beaucoup moins.
- Sans PriceCharting, la cote vient des prix demandés, pas des prix vendus. Plus il y a
  d'annonces comparables, plus elle est fiable, et l'alerte indique combien il y en avait.
- Avec PriceCharting, la carte est trouvée d'après ta recherche. Une recherche précise (nom,
  numéro, extension) évite de comparer avec la mauvaise carte.
- La fiscalité de la revente régulière (auto-entrepreneur, déclaration des plateformes) reste
  à ta charge.

## Tests

```bash
pip install pytest
python -m pytest
```
