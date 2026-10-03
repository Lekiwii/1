"""Scan des annonces, cote de marché, marge de revente et indice de confiance."""
import asyncio
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

from .cardinfo import CardInfo, PokemonTCG
from .config import Config
from .ebay import EbayClient, Listing
from .grading import Grade, Variant, explicit_language, parse_grade, parse_variant, strip_grade
from .pricing import PriceCharting, comps_median
from .scoring import Confidence, confidence
from .social import Buzz, Reddit

log = logging.getLogger(__name__)


@dataclass
class Sources:
    ebay: EbayClient
    pricecharting: PriceCharting | None = None
    pokemontcg: PokemonTCG | None = None
    reddit: Reddit | None = None


@dataclass
class Valuation:
    """Cote d'une carte pour une variante donnée, avec tout ce qui la justifie."""

    market_eur: float
    source: str
    comps: list[float]
    pricecharting_eur: float | None
    card: CardInfo | None
    buzz: Buzz | None


@dataclass
class Deal:
    listing: Listing
    query: str
    variant: Variant
    cost_eur: float
    valuation: Valuation
    net_resale_eur: float
    profit_eur: float
    roi_pct: float
    confidence: Confidence

    @property
    def grade(self) -> Grade:
        return self.variant.grade

    @property
    def market_eur(self) -> float:
        return self.valuation.market_eur

    @property
    def market_source(self) -> str:
        return self.valuation.source


@dataclass
class Estimate:
    query: str
    grade: Grade
    cost_eur: float
    valuation: Valuation
    net_resale_eur: float
    profit_eur: float
    roi_pct: float
    confidence: Confidence
    listings: list[dict] = field(default_factory=list)

    @property
    def market_eur(self) -> float:
        return self.valuation.market_eur

    @property
    def market_source(self) -> str:
        return self.valuation.source


def to_eur(amount: float, currency: str, cfg: Config) -> float:
    rates = {"EUR": 1.0, "USD": cfg.usd_to_eur, "GBP": cfg.gbp_to_eur}
    return round(amount * rates.get(currency, 1.0), 2)


def resale_profit(cost_eur: float, market_eur: float, cfg: Config) -> tuple[float, float, float]:
    """(revenu net de revente, bénéfice, ROI %) si on revend au prix du marché."""
    net = market_eur * (1 - cfg.sell_fee_pct / 100) - cfg.sell_shipping_eur
    profit = net - cost_eur
    roi = profit / cost_eur * 100 if cost_eur else 0.0
    return round(net, 2), round(profit, 2), round(roi, 1)


def trusted_seller(listing: Listing, cfg: Config) -> bool:
    return (
        listing.seller_feedback_pct >= cfg.min_seller_feedback_pct
        and listing.seller_feedback_score >= cfg.min_seller_feedback_score
    )


async def _graded_listings(
    query: str, cfg: Config, ebay: EbayClient, min_price: float, max_price: float,
    errors: list[str] | None = None,
) -> list[tuple[Listing, Variant, float]]:
    """Annonces gradées de la recherche, sur toutes les marketplaces, avec leur coût total en euros."""

    async def one(market: str) -> list[Listing]:
        try:
            return await ebay.search_graded(query, market, min_price, max_price)
        except Exception as exc:  # une marketplace en panne ne bloque pas les autres
            log.warning("eBay %s « %s » : %s", market, query, exc)
            if errors is not None:
                errors.append(str(exc))
            return []

    results = await asyncio.gather(*(one(m) for m in cfg.ebay_marketplaces))
    graded: list[tuple[Listing, Variant, float]] = []
    seen: set[str] = set()
    for listings in results:
        for listing in listings:
            variant = parse_variant(listing.title)
            if variant is None or listing.item_id in seen:
                continue
            seen.add(listing.item_id)
            graded.append((listing, variant, to_eur(listing.total, listing.currency, cfg)))
    return graded


async def _card_context(query: str, sources: Sources) -> tuple[CardInfo | None, Buzz | None]:
    card = buzz = None
    if sources.pokemontcg:
        try:
            card = await sources.pokemontcg.lookup(query)
        except Exception as exc:
            log.warning("pokemontcg.io « %s » : %s", query, exc)
    if sources.reddit:
        try:
            buzz = await sources.reddit.buzz(card.name if card else query)
        except Exception as exc:
            log.warning("Reddit « %s » : %s", query, exc)
    return card, buzz


async def _valuation(
    query: str, variant: Variant, comps: list[float], cfg: Config, sources: Sources,
    card: CardInfo | None, buzz: Buzz | None,
) -> Valuation | None:
    pc_price = None
    if sources.pricecharting and variant.language == "EN":  # PriceCharting cote les cartes anglaises
        try:
            pc_price = await sources.pricecharting.market_price(query, variant.grade)
        except Exception as exc:
            log.warning("PriceCharting « %s » : %s", query, exc)
    median = comps_median(comps)
    if pc_price is not None:
        return Valuation(pc_price, "PriceCharting (ventes réelles)", comps, pc_price, card, buzz)
    if median is None:
        return None
    market = round(median * (1 - cfg.comps_discount_pct / 100), 2)
    source = f"médiane de {len(comps)} annonces eBay {variant}, −{cfg.comps_discount_pct:.0f} %"
    return Valuation(market, source, comps, None, card, buzz)


def _confidence(valuation: Valuation, listing: Listing | None) -> Confidence:
    return confidence(
        market_eur=valuation.market_eur,
        comps=valuation.comps,
        pricecharting_eur=valuation.pricecharting_eur,
        card=valuation.card,
        buzz=valuation.buzz,
        seller_feedback_score=listing.seller_feedback_score if listing else None,
        language_explicit=explicit_language(listing.title) is not None if listing else True,
    )


async def find_deals(queries: list[str], cfg: Config, sources: Sources) -> list[Deal]:
    deals: list[Deal] = []
    errors: list[str] = []
    for query in queries:
        graded = await _graded_listings(query, cfg, sources.ebay, cfg.min_price_eur, cfg.max_price_eur, errors)
        if not graded:
            continue
        card, buzz = await _card_context(query, sources)
        comps: dict[Variant, list[float]] = defaultdict(list)
        for _, variant, cost in graded:
            comps[variant].append(cost)

        valuations: dict[Variant, Valuation | None] = {}
        for listing, variant, cost in graded:
            if not trusted_seller(listing, cfg):
                continue
            if variant not in valuations:
                valuations[variant] = await _valuation(query, variant, comps[variant], cfg, sources, card, buzz)
            valuation = valuations[variant]
            if valuation is None:
                continue
            net, profit, roi = resale_profit(cost, valuation.market_eur, cfg)
            if profit >= cfg.min_profit_eur and roi >= cfg.min_roi_pct:
                conf = _confidence(valuation, listing)
                deals.append(Deal(listing, query, variant, cost, valuation, net, profit, roi, conf))

    if queries and len(errors) == len(queries) * len(cfg.ebay_marketplaces):
        raise RuntimeError(f"eBay ne répond à aucune recherche ({errors[0]}). Vérifie ta connexion et tes clés eBay.")
    deals.sort(key=lambda d: (d.confidence.score >= cfg.min_confidence, d.profit_eur), reverse=True)
    return deals


_PRICE_RE = re.compile(r"\s(\d+(?:[.,]\d{1,2})?)\s*(?:€|eur|euros?)?\s*$", re.IGNORECASE)


def parse_offer(text: str) -> tuple[str, Grade, float] | None:
    """« Umbreon VMAX 215/203 PSA 10 650 » -> (« Umbreon VMAX 215/203 », PSA 10, 650.0)."""
    match = _PRICE_RE.search(" " + text.strip())
    if not match:
        return None
    price = float(match.group(1).replace(",", "."))
    rest = (" " + text.strip())[: match.start()].strip()
    grade = parse_grade(rest)
    if grade is None:
        return None
    query = " ".join(strip_grade(rest).split())
    return (query, grade, price) if query else None


async def estimate(
    query: str, grade: Grade, price_eur: float, cfg: Config, sources: Sources,
    language: str = "EN", first_edition: bool = False,
) -> Estimate | None:
    """Cote et marge de revente pour une offre vue ailleurs (Vinted, Leboncoin, salon…)."""
    variant = Variant(grade, language, first_edition)
    graded = await _graded_listings(f"{query} {grade}", cfg, sources.ebay, 1, 100_000)
    same = [(l, c) for l, v, c in graded if v == variant]
    card, buzz = await _card_context(query, sources)
    valuation = await _valuation(query, variant, [c for _, c in same], cfg, sources, card, buzz)
    if valuation is None:
        return None
    net, profit, roi = resale_profit(price_eur, valuation.market_eur, cfg)
    conf = _confidence(valuation, None)
    listings = [
        {"title": l.title, "price_eur": c, "url": l.url, "source": l.source}
        for l, c in sorted(same, key=lambda x: x[1])
    ]
    return Estimate(query, grade, price_eur, valuation, net, profit, roi, conf, listings)
