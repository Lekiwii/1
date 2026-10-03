"""Fiche carte et prix de référence via l'API pokemontcg.io (https://docs.pokemontcg.io).

Elle fournit, pour chaque carte, les prix Cardmarket (en euros, avec moyennes 1, 7 et 30 jours)
et TCGplayer (en dollars). Ce sont des prix de cartes NON gradées : ils servent à identifier la
carte, à mesurer la tendance du marché et à vérifier qu'une cote gradée est cohérente.
"""
import re
import time
from dataclasses import dataclass

import httpx

API_URL = "https://api.pokemontcg.io/v2/cards"
CACHE_SECONDS = 6 * 3600

# Raretés les plus recherchées par les collectionneurs (cartes modernes)
CHASE_RARITIES = [
    "Special Illustration Rare", "Illustration Rare", "Hyper Rare", "Rare Secret",
    "Rare Rainbow", "Rare Ultra", "Trainer Gallery Rare Holo", "Rare Holo VMAX", "Rare Holo V",
]

_NUMBER_RE = re.compile(r"\b0*(\d{1,3})\s*/\s*0*\d{1,3}\b|\b(?:#|n°\s*)0*(\d{1,3})\b", re.IGNORECASE)
_NOISE = re.compile(r"\b(alt(ernate)?\s*art|full\s*art|shiny|holo|base\s*set|secret|rare|promo)\b", re.IGNORECASE)


@dataclass
class CardInfo:
    id: str
    name: str
    number: str
    set_name: str
    release_date: str
    rarity: str
    image: str
    cardmarket_url: str
    trend_eur: float | None  # prix de tendance Cardmarket
    avg1_eur: float | None
    avg7_eur: float | None
    avg30_eur: float | None
    tcgplayer_usd: float | None

    @property
    def momentum_pct(self) -> float | None:
        """Évolution du prix moyen sur 7 jours par rapport à 30 jours, en %."""
        if self.avg7_eur and self.avg30_eur:
            return round((self.avg7_eur / self.avg30_eur - 1) * 100, 1)
        return None

    @property
    def trend_label(self) -> str:
        m = self.momentum_pct
        if m is None:
            return "inconnue"
        if m >= 8:
            return "forte hausse"
        if m >= 3:
            return "hausse"
        if m <= -8:
            return "forte baisse"
        if m <= -3:
            return "baisse"
        return "stable"


def split_query(query: str) -> tuple[str, str | None]:
    """« Umbreon VMAX Alt Art 215/203 » -> (« Umbreon VMAX », « 215 »)."""
    match = _NUMBER_RE.search(query)
    number = (match.group(1) or match.group(2)) if match else None
    name = _NUMBER_RE.sub(" ", query)
    name = _NOISE.sub(" ", name)
    return " ".join(name.split()), number


def _price(prices: dict, key: str) -> float | None:
    value = prices.get(key)
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def to_card_info(card: dict) -> CardInfo:
    cm = (card.get("cardmarket") or {}).get("prices") or {}
    tcg_prices = (card.get("tcgplayer") or {}).get("prices") or {}
    tcg = None
    for variant in ("holofoil", "1stEditionHolofoil", "normal", "reverseHolofoil", "unlimitedHolofoil"):
        if variant in tcg_prices and _price(tcg_prices[variant], "market"):
            tcg = _price(tcg_prices[variant], "market")
            break
    return CardInfo(
        id=card.get("id", ""),
        name=card.get("name", ""),
        number=card.get("number", ""),
        set_name=(card.get("set") or {}).get("name", ""),
        release_date=(card.get("set") or {}).get("releaseDate", ""),
        rarity=card.get("rarity", ""),
        image=(card.get("images") or {}).get("small", ""),
        cardmarket_url=(card.get("cardmarket") or {}).get("url", ""),
        trend_eur=_price(cm, "trendPrice"),
        avg1_eur=_price(cm, "avg1"),
        avg7_eur=_price(cm, "avg7"),
        avg30_eur=_price(cm, "avg30"),
        tcgplayer_usd=tcg,
    )


class PokemonTCG:
    def __init__(self, http: httpx.AsyncClient, api_key: str = ""):
        self._http = http
        self._headers = {"X-Api-Key": api_key} if api_key else {}
        self._cache: dict[str, tuple[float, object]] = {}

    async def _get(self, params: dict) -> list[dict]:
        key = repr(sorted(params.items()))
        cached = self._cache.get(key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1]  # type: ignore[return-value]
        resp = await self._http.get(API_URL, params=params, headers=self._headers, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        self._cache[key] = (time.time(), data)
        return data

    async def lookup(self, query: str) -> CardInfo | None:
        """La carte la plus probable pour une recherche « nom + numéro »."""
        name, number = split_query(query)
        if not name:
            return None
        q = f'name:"{name}*"' + (f" number:{number}" if number else "")
        cards = await self._get({"q": q, "orderBy": "-set.releaseDate", "pageSize": "20"})
        infos = [to_card_info(c) for c in cards]
        priced = [i for i in infos if i.trend_eur]
        if not priced:
            return infos[0] if infos else None
        return max(priced, key=lambda i: i.trend_eur or 0)  # la version la plus chère est souvent celle visée

    async def trending(self, min_price_eur: float = 20, limit: int = 40) -> list[CardInfo]:
        """Cartes recherchées dont le prix monte le plus (7 jours vs 30 jours)."""
        rarities = " OR ".join(f'rarity:"{r}"' for r in CHASE_RARITIES)
        cards = await self._get({"q": f"({rarities})", "orderBy": "-set.releaseDate", "pageSize": "250"})
        infos = [to_card_info(c) for c in cards]
        rising = [
            i for i in infos
            if i.trend_eur and i.trend_eur >= min_price_eur and i.momentum_pct is not None
        ]
        rising.sort(key=lambda i: i.momentum_pct or 0, reverse=True)
        return rising[:limit]
