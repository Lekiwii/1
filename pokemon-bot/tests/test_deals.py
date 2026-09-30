import asyncio

from pokedeals.config import Config
from pokedeals.deals import find_deals, resale_profit
from pokedeals.ebay import Listing
from pokedeals.pricing import comps_median


def listing(item_id, title, price, feedback=99.8, score=500, currency="EUR"):
    return Listing("EBAY_FR", item_id, title, price, 0.0, currency, f"https://ebay/{item_id}", "", "s", feedback, score)


class FakeEbay:
    def __init__(self, listings):
        self.listings = listings

    async def search_graded(self, query, marketplace, min_price, max_price):
        return self.listings


def cfg(**kw):
    return Config(ebay_marketplaces=["EBAY_FR"], comps_discount_pct=0, **kw)


def test_resale_profit_includes_fees_and_shipping():
    net, profit, roi = resale_profit(100, 200, cfg(sell_fee_pct=13, sell_shipping_eur=8))
    assert net == 166.0 and profit == 66.0 and roi == 66.0


def test_comps_median_ignores_outliers_and_needs_enough_comps():
    assert comps_median([100, 110]) is None
    assert comps_median([100, 110, 120, 5000]) == 110


def test_find_deals_flags_underpriced_card_from_trusted_seller():
    ebay = FakeEbay([
        listing("1", "Umbreon VMAX 215/203 PSA 10", 700),
        listing("2", "Umbreon VMAX 215/203 PSA 10", 1400),
        listing("3", "Umbreon VMAX 215/203 PSA 10", 1450),
        listing("4", "Umbreon VMAX 215/203 PSA 10", 1500),
        listing("5", "Umbreon VMAX 215/203 PSA 10", 650, feedback=90),  # vendeur douteux
        listing("6", "Umbreon VMAX 215/203 PSA 9", 300),                 # pas assez de comparables PSA 9
    ])
    deals = asyncio.run(find_deals(["Umbreon VMAX 215/203"], cfg(), ebay, None))
    assert [d.listing.item_id for d in deals] == ["1"]
    assert deals[0].market_eur == 1400 and deals[0].profit_eur > 400
