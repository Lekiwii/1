"""Scan des annonces et calcul de la marge de revente."""
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from .config import Config
from .ebay import EbayClient, Listing
from .grading import Grade, parse_grade, strip_grade
from .pricing import PriceCharting, comps_median

log = logging.getLogger(__name__)


@dataclass
class Deal:
    listing: Listing
    query: str
    grade: Grade
    cost_eur: float
    market_eur: float
    market_source: str
    net_resale_eur: float
    profit_eur: float
    roi_pct: float


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
    query: str, cfg: Config, ebay: EbayClient, min_price: float, max_price: float
) -> list[tuple[Listing, Grade, float]]:
    """Annonces gradées de la recherche, sur toutes les marketplaces, avec leur coût total en euros."""
    graded: list[tuple[Listing, Grade, float]] = []
    seen: set[str] = set()
    for market in cfg.ebay_marketplaces:
        try:
            listings = await ebay.search_graded(query, market, min_price, max_price)
        except Exception as exc:  # une marketplace en panne ne bloque pas les autres
            log.warning("eBay %s « %s » : %s", market, query, exc)
            continue
        for listing in listings:
            grade = parse_grade(listing.title)
            if grade is None or listing.item_id in seen:
                continue
            seen.add(listing.item_id)
            graded.append((listing, grade, to_eur(listing.total, listing.currency, cfg)))
    return graded


async def _market_price(
    query: str, grade: Grade, comps: list[float], cfg: Config, pricecharting: PriceCharting | None
) -> tuple[float | None, str]:
    if pricecharting:
        try:
            price = await pricecharting.market_price(query, grade)
            if price is not None:
                return price, "PriceCharting"
        except Exception as exc:
            log.warning("PriceCharting « %s » : %s", query, exc)
    median = comps_median(comps)
    if median is None:
        return None, ""
    return round(median * (1 - cfg.comps_discount_pct / 100), 2), f"médiane de {len(comps)} annonces eBay {grade}"


async def find_deals(
    queries: list[str], cfg: Config, ebay: EbayClient, pricecharting: PriceCharting | None
) -> list[Deal]:
    deals: list[Deal] = []
    for query in queries:
        graded = await _graded_listings(query, cfg, ebay, cfg.min_price_eur, cfg.max_price_eur)
        comps: dict[Grade, list[float]] = defaultdict(list)
        for _, grade, cost in graded:
            comps[grade].append(cost)

        for listing, grade, cost in graded:
            if not trusted_seller(listing, cfg):
                continue
            market, source = await _market_price(query, grade, comps[grade], cfg, pricecharting)
            if market is None:
                continue
            net, profit, roi = resale_profit(cost, market, cfg)
            if profit >= cfg.min_profit_eur and roi >= cfg.min_roi_pct:
                deals.append(Deal(listing, query, grade, cost, market, source, net, profit, roi))

    deals.sort(key=lambda d: d.profit_eur, reverse=True)
    return deals


@dataclass
class Estimate:
    query: str
    grade: Grade
    cost_eur: float
    market_eur: float
    market_source: str
    net_resale_eur: float
    profit_eur: float
    roi_pct: float


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
    query: str, grade: Grade, price_eur: float, cfg: Config, ebay: EbayClient, pricecharting: PriceCharting | None
) -> Estimate | None:
    """Cote et marge de revente pour une offre vue ailleurs (Vinted, Leboncoin, salon…)."""
    graded = await _graded_listings(f"{query} {grade}", cfg, ebay, 1, 100_000)
    comps = [cost for _, g, cost in graded if g == grade]
    market, source = await _market_price(query, grade, comps, cfg, pricecharting)
    if market is None:
        return None
    net, profit, roi = resale_profit(price_eur, market, cfg)
    return Estimate(query, grade, price_eur, market, source, net, profit, roi)
