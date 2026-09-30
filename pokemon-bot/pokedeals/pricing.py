"""Cote de marché d'une carte gradée.

Deux sources :
- PriceCharting (si un token est configuré) : prix de vente constatés par note (PSA 10, BGS 9.5, CGC 10…).
- À défaut, la médiane des annonces comparables (même recherche, même organisme, même note)
  trouvées pendant le scan, sur toutes les marketplaces.
"""
import statistics

import httpx

from .grading import Grade

PRICECHARTING_URL = "https://www.pricecharting.com/api"

# Champs PriceCharting (en cents USD) par note ; les notes 10 dépendent de l'organisme.
_PC_FIELDS = {
    7.0: "cib-price",
    8.0: "new-price",
    9.0: "graded-price",
    9.5: "box-only-price",
}
_PC_TENS = {"PSA": "manual-only-price", "BGS": "bgs-10-price", "CGC": "condition-17-price", "SGC": "condition-18-price"}

MIN_COMPS = 3  # nombre minimal d'annonces comparables pour faire une médiane fiable


class PriceCharting:
    def __init__(self, token: str, usd_to_eur: float, http: httpx.AsyncClient):
        self._token = token
        self._rate = usd_to_eur
        self._http = http
        self._cache: dict[str, dict | None] = {}

    async def _product(self, query: str) -> dict | None:
        if query not in self._cache:
            resp = await self._http.get(f"{PRICECHARTING_URL}/product", params={"t": self._token, "q": f"pokemon {query}"})
            self._cache[query] = resp.json() if resp.status_code == 200 and resp.json().get("status") == "success" else None
        return self._cache[query]

    async def market_price(self, query: str, grade: Grade) -> float | None:
        field = _PC_TENS.get(grade.grader) if grade.grade == 10 else _PC_FIELDS.get(grade.grade)
        if not field:
            return None
        product = await self._product(query)
        cents = product.get(field) if product else None
        return round(cents / 100 * self._rate, 2) if cents else None


def comps_median(prices: list[float]) -> float | None:
    """Médiane robuste : on retire les valeurs aberrantes (> 3x ou < 1/3 de la médiane brute)."""
    if len(prices) < MIN_COMPS:
        return None
    raw = statistics.median(prices)
    kept = [p for p in prices if raw / 3 <= p <= raw * 3]
    return statistics.median(kept) if len(kept) >= MIN_COMPS else None
