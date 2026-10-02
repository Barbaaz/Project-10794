import pytest

from scrapers.base.parser_utils import absolute_url, detect_condition, parse_price


@pytest.mark.parametrize("text, expected", [
    ("59,99 €", 59.99),
    ("€39.99", 39.99),
    ("1.299,99 €", 1299.99),
    ("1,299.99", 1299.99),
    ("19,99 - 29,99 €", 19.99),
    ("54.99", 54.99),
    ("2,09\xa0€", 2.09),
    ("", None),
    (None, None),
])
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize("texts, expected", [
    (("COMPRAR USADO",), "used"),
    (("Far Cry [USADO] PS3",), "used"),
    (("Semi-Novo",), "used"),
    (("Jogo seminovo",), "used"),
    (("COMPRAR NOVO", "Renovo PS5"), "new"),
    ((None, "Hogwarts Legacy PS5"), "new"),
])
def test_detect_condition(texts, expected):
    assert detect_condition(*texts) == expected


def test_absolute_url():
    assert absolute_url("https://mega-mania.com.pt", "/pt/produto/1") == "https://mega-mania.com.pt/pt/produto/1"
    assert absolute_url("https://mega-mania.com.pt", "https://x.pt/a") == "https://x.pt/a"
    assert absolute_url("https://mega-mania.com.pt", None) is None
