import asyncio

from pokedeals.cardinfo import split_query, to_card_info
from pokedeals.config import Config
from pokedeals.deals import Sources, find_deals
from pokedeals.grading import parse_variant
from pokedeals.scoring import confidence
from tests.test_deals import FakeEbay, listing

CARD = {
    "id": "swsh7-215", "name": "Umbreon VMAX", "number": "215", "rarity": "Rare Secret",
    "set": {"name": "Evolving Skies", "releaseDate": "2021/08/27"},
    "images": {"small": "https://images.pokemontcg.io/swsh7/215.png"},
    "cardmarket": {"url": "https://prices.pokemontcg.io/cardmarket/swsh7-215",
                   "prices": {"trendPrice": 520.0, "avg1": 560.0, "avg7": 540.0, "avg30": 500.0}},
    "tcgplayer": {"prices": {"holofoil": {"market": 610.0}}},
}


class FakeTCG:
    async def lookup(self, query):
        return to_card_info(CARD)


def test_card_info_and_momentum():
    info = to_card_info(CARD)
    assert info.trend_eur == 520 and info.tcgplayer_usd == 610
    assert info.momentum_pct == 8.0 and info.trend_label == "forte hausse"


def test_split_query():
    assert split_query("Umbreon VMAX Alt Art 215/203") == ("Umbreon VMAX", "215")
    assert split_query("Charizard VMAX 074/073") == ("Charizard VMAX", "74")


def test_languages_are_never_mixed_in_comps():
    assert parse_variant("Umbreon PSA 10 Japanese") != parse_variant("Umbreon PSA 10")
    assert parse_variant("Carte de Dracaufeu PSA 9 en bon état").language == "EN"  # « de », « en » ≠ langues


def test_confidence_rewards_agreeing_sources_and_flags_falling_prices():
    card = to_card_info(CARD)
    solid = confidence(market_eur=1400, comps=[1350, 1380, 1400, 1420, 1450] * 2, pricecharting_eur=1450,
                       card=card, buzz=None, seller_feedback_score=2500, language_explicit=True)
    assert solid.score >= 70 and solid.label == "Fiable"

    falling = to_card_info({**CARD, "cardmarket": {"prices": {"trendPrice": 900, "avg7": 800, "avg30": 1000}}})
    shaky = confidence(market_eur=600, comps=[300, 600, 1500], pricecharting_eur=None,
                       card=falling, buzz=None, seller_feedback_score=60, language_explicit=False)
    assert shaky.score < 45 and shaky.label == "Risqué"
    assert any("sous le prix non gradé" in text for _, text in shaky.reasons)


def test_scan_attaches_card_trend_and_confidence():
    ebay = FakeEbay([listing(str(i), "Umbreon VMAX 215/203 PSA 10 English", p, score=1500)
                     for i, p in enumerate([700, 1400, 1420, 1450, 1500, 1380])])
    cfg = Config(ebay_marketplaces=["EBAY_FR"], comps_discount_pct=0)
    deals = asyncio.run(find_deals(["Umbreon VMAX 215/203"], cfg, Sources(ebay, pokemontcg=FakeTCG())))
    assert [d.listing.item_id for d in deals] == ["0"]
    assert deals[0].valuation.card.name == "Umbreon VMAX"
    assert deals[0].confidence.score >= 70


def test_scan_reports_when_ebay_is_down():
    import pytest

    class DownEbay:
        async def search_graded(self, *a):
            raise RuntimeError("401 Unauthorized")

    with pytest.raises(RuntimeError, match="eBay ne répond"):
        asyncio.run(find_deals(["Umbreon"], Config(ebay_marketplaces=["EBAY_FR"]), Sources(DownEbay())))
