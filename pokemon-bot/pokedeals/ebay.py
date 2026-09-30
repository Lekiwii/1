"""Annonces eBay via l'API officielle Browse (https://developer.ebay.com/api-docs/buy/browse)."""
import base64
import time
from dataclasses import dataclass

import httpx

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
POKEMON_CARDS_CATEGORY = "183454"  # CCG Individual Cards
GRADED_CONDITION_ID = "2750"  # état "Gradée" des cartes à collectionner

MARKET_CURRENCY = {
    "EBAY_FR": "EUR", "EBAY_DE": "EUR", "EBAY_IT": "EUR", "EBAY_ES": "EUR",
    "EBAY_NL": "EUR", "EBAY_BE": "EUR", "EBAY_GB": "GBP", "EBAY_US": "USD",
}


@dataclass
class Listing:
    source: str
    item_id: str
    title: str
    price: float
    shipping: float
    currency: str
    url: str
    image: str
    seller: str
    seller_feedback_pct: float
    seller_feedback_score: int

    @property
    def total(self) -> float:
        return self.price + self.shipping


class EbayClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.AsyncClient):
        self._auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        self._http = http
        self._token = ""
        self._token_expiry = 0.0

    async def _access_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = await self._http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {self._auth}"},
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._token_expiry = time.time() + body.get("expires_in", 7200)
        return self._token

    async def search_graded(
        self, query: str, marketplace: str, min_price: float, max_price: float, limit: int = 200
    ) -> list[Listing]:
        currency = MARKET_CURRENCY.get(marketplace, "EUR")
        filters = [
            "buyingOptions:{FIXED_PRICE}",
            f"conditionIds:{{{GRADED_CONDITION_ID}}}",
            f"price:[{min_price:.0f}..{max_price:.0f}]",
            f"priceCurrency:{currency}",
        ]
        resp = await self._http.get(
            SEARCH_URL,
            headers={
                "Authorization": f"Bearer {await self._access_token()}",
                "X-EBAY-C-MARKETPLACE-ID": marketplace,
            },
            params={
                "q": f"pokemon {query}",
                "category_ids": POKEMON_CARDS_CATEGORY,
                "filter": ",".join(filters),
                "sort": "newlyListed",
                "limit": str(limit),
            },
        )
        resp.raise_for_status()
        return [_to_listing(item, marketplace) for item in resp.json().get("itemSummaries", [])]


def _to_listing(item: dict, marketplace: str) -> Listing:
    shipping = 0.0
    for option in item.get("shippingOptions", []):
        cost = option.get("shippingCost")
        if cost:
            shipping = float(cost["value"])
            break
    seller = item.get("seller", {})
    return Listing(
        source=marketplace,
        item_id=item["itemId"],
        title=item.get("title", ""),
        price=float(item["price"]["value"]),
        shipping=shipping,
        currency=item["price"]["currency"],
        url=item.get("itemWebUrl", ""),
        image=item.get("image", {}).get("imageUrl", ""),
        seller=seller.get("username", "?"),
        seller_feedback_pct=float(seller.get("feedbackPercentage", 0) or 0),
        seller_feedback_score=int(seller.get("feedbackScore", 0) or 0),
    )
