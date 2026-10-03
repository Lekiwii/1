"""Buzz sur Reddit (optionnel) : nombre de discussions récentes sur une carte.

Utilise l'API officielle de Reddit (clés gratuites sur https://www.reddit.com/prefs/apps,
type « script »). Ce n'est pas une source de prix : un signal d'intérêt du public, à faible poids.
"""
import time
from dataclasses import dataclass

import httpx

SUBREDDITS = "PokemonTCG+pkmntcgcollections+PokeInvesting+pokemoncardcollectors+PokemonTCGDeals"
CACHE_SECONDS = 6 * 3600


@dataclass
class Buzz:
    week: int
    month: int

    @property
    def ratio(self) -> float | None:
        """Mentions de la semaine par rapport à une semaine moyenne du mois (1 = normal)."""
        return round(self.week / (self.month / 4.3), 2) if self.month else None

    @property
    def label(self) -> str:
        r = self.ratio
        if r is None or self.month < 4:
            return "peu discutée"
        if r >= 1.8:
            return "buzz en hausse"
        if r <= 0.5:
            return "intérêt en baisse"
        return "intérêt stable"


class Reddit:
    def __init__(self, client_id: str, client_secret: str, http: httpx.AsyncClient):
        self._auth = (client_id, client_secret)
        self._http = http
        self._token = ""
        self._expiry = 0.0
        self._cache: dict[str, tuple[float, Buzz]] = {}
        self._headers = {"User-Agent": "pokedeals/1.0 (personal price tracker)"}

    async def _bearer(self) -> str:
        if not self._token or time.time() > self._expiry - 60:
            resp = await self._http.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=self._auth, data={"grant_type": "client_credentials"}, headers=self._headers,
            )
            resp.raise_for_status()
            body = resp.json()
            self._token, self._expiry = body["access_token"], time.time() + body.get("expires_in", 3600)
        return self._token

    async def _count(self, query: str, period: str) -> int:
        resp = await self._http.get(
            f"https://oauth.reddit.com/r/{SUBREDDITS}/search",
            params={"q": f'"{query}"', "restrict_sr": "1", "t": period, "limit": "100", "sort": "new"},
            headers={**self._headers, "Authorization": f"Bearer {await self._bearer()}"},
        )
        resp.raise_for_status()
        return len(resp.json().get("data", {}).get("children", []))

    async def buzz(self, card_name: str) -> Buzz:
        cached = self._cache.get(card_name)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1]
        result = Buzz(await self._count(card_name, "week"), await self._count(card_name, "month"))
        self._cache[card_name] = (time.time(), result)
        return result
