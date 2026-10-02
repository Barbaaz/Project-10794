from datetime import date

import pytest

from scrapers.base.parser_utils import absolute_url, detect_condition, parse_price, parse_release_date


@pytest.mark.parametrize("text, expected", [
    ("Lançamento: 15 Outubro 2026", date(2026, 10, 15)),
    ("2 de março de 2027", date(2027, 3, 2)),
    ("2026-12-31", date(2026, 12, 31)),
    ("31/12/2026", date(2026, 12, 31)),
    ("6/1/2027", date(2027, 1, 6)),
    ("31/02/2026", None),
    ("15 Brumário 2026", None),
    ("", None),
    (None, None),
])
def test_parse_release_date(text, expected):
    assert parse_release_date(text) == expected


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
