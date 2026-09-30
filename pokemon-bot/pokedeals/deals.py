"""Scan des annonces et calcul de la marge de revente."""
import logging
from collections import defaultdict
from dataclasses import dataclass

from .config import Config
from .ebay import EbayClient, Listing
from .grading import Grade, parse_grade
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


async def find_deals(
    queries: list[str], cfg: Config, ebay: EbayClient, pricecharting: PriceCharting | None
) -> list[Deal]:
    deals: list[Deal] = []
    for query in queries:
        graded: list[tuple[Listing, Grade, float]] = []
        seen: set[str] = set()
        for market in cfg.ebay_marketplaces:
            try:
                listings = await ebay.search_graded(query, market, cfg.min_price_eur, cfg.max_price_eur)
            except Exception as exc:  # une marketplace en panne ne bloque pas les autres
                log.warning("eBay %s « %s » : %s", market, query, exc)
                continue
            for listing in listings:
                grade = parse_grade(listing.title)
                if grade is None or listing.item_id in seen:
                    continue
                seen.add(listing.item_id)
                graded.append((listing, grade, to_eur(listing.total, listing.currency, cfg)))

        comps: dict[Grade, list[float]] = defaultdict(list)
        for _, grade, cost in graded:
            comps[grade].append(cost)

        for listing, grade, cost in graded:
            if not trusted_seller(listing, cfg):
                continue
            market, source = None, ""
            if pricecharting:
                try:
                    market, source = await pricecharting.market_price(query, grade), "PriceCharting"
                except Exception as exc:
                    log.warning("PriceCharting « %s » : %s", query, exc)
            if market is None:
                median = comps_median(comps[grade])
                if median is not None:
                    market = round(median * (1 - cfg.comps_discount_pct / 100), 2)
                    source = f"médiane de {len(comps[grade])} annonces {grade}"
            if market is None:
                continue
            net, profit, roi = resale_profit(cost, market, cfg)
            if profit >= cfg.min_profit_eur and roi >= cfg.min_roi_pct:
                deals.append(Deal(listing, query, grade, cost, market, source, net, profit, roi))

    deals.sort(key=lambda d: d.profit_eur, reverse=True)
    return deals
