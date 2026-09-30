import pytest

from pokedeals.grading import Grade, parse_grade


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Pokemon Charizard Base Set 4/102 PSA 9 Mint", Grade("PSA", 9)),
        ("Umbreon VMAX 215/203 PSA 10 GEM MINT Evolving Skies", Grade("PSA", 10)),
        ("Lugia V Alt Art BGS 9.5 Gem Mint", Grade("BGS", 9.5)),
        ("Dracaufeu ex 199/165 CGC 9,5 FR", Grade("CGC", 9.5)),
        ("Pikachu Beckett 10 Pristine", Grade("BGS", 10)),
        ("Mew ex 232/091 PSA GEM MT 10", Grade("PSA", 10)),
    ],
)
def test_graded_titles(title, expected):
    assert parse_grade(title) == expected


@pytest.mark.parametrize(
    "title",
    [
        "Charizard 4/102 Base Set near mint",          # pas de note
        "Charizard 4/102 PSA ready, grade it yourself",  # non gradée
        "Lot PSA 10 Pikachu + PSA 9 Eevee",             # lot
        "Empty PSA 10 slab case only",                  # boîtier vide
        "Custom Charizard PSA 10 proxy",                # faux
        "Umbreon VMAX PSA 10 and PSA 9 set",            # plusieurs notes
    ],
)
def test_rejected_titles(title):
    assert parse_grade(title) is None


def test_card_number_is_not_a_grade():
    assert parse_grade("Charizard 4/102 PSA 8") == Grade("PSA", 8)
