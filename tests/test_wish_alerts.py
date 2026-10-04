"""Wishlist alerts by e-mail after the morning run (on a throwaway database)."""
from decimal import Decimal

import pytest

from helpers import HEADERS, log_in, sign_up
from app.services import wish_alert_service
from app.services.wish_alert_service import change


@pytest.fixture
def store(monkeypatch):
    """A store selling the editions new: {edition id: price, or None for out of stock}; the e-mails sent."""
    import app.services.game_service as games
    real = games.editions_with_offers
    prices, sent = {}, []

    def with_a_store(ids):
        groups = real(ids)
        for g in groups:
            price = prices.get(g["edition_id"])
            g["offers"] = [{"price": price, "in_stock": True, "condition": "new", "store_name": "Loja",
                            "is_discount": False}] if price is not None else []
        return groups
    monkeypatch.setattr(games, "editions_with_offers", with_a_store)
    monkeypatch.setattr(wish_alert_service.mail_service, "send", lambda *args: sent.append(args) or False)
    return prices, sent


def wish(client, edition_id):
    return client.post("/api/collection", json={"edition_id": edition_id, "kind": "wishlist"}, headers=HEADERS)


def test_change_rules():
    d = Decimal
    assert change(None, d("50"), checked=False, at_low=False) == (None, d("50"))        # first check: remembered
    assert change(None, d("50"), checked=True, at_low=False) == ("back_in_stock", d("50"))
    assert change(d("50"), None, checked=True, at_low=False) == (None, None)             # sold out: nothing to say
    assert change(d("50"), d("45"), checked=True, at_low=False) == ("price_drop", d("45"))
    assert change(d("50"), d("45"), checked=True, at_low=True) == ("historical_low", d("45"))
    assert change(d("50"), d("49"), checked=True, at_low=False) == (None, d("50"))       # small: drops add up
    assert change(d("10"), d("9.50"), checked=True, at_low=False) == (None, d("10"))     # less than 1 €
    assert change(d("50"), d("55"), checked=True, at_low=False) == (None, d("55"))


def test_drop_and_back_in_stock_once(market, store):
    prices, sent = store
    client = market["client"]
    prices[market["edition"]] = 59.99
    sign_up(client, "wisher")
    wish(client, market["edition"])
    wish(client, market["other_edition"])                       # out of stock when wished

    assert wish_alert_service.check_all() == {"users": 0, "items": 0, "sent": 0}
    prices[market["edition"]] = 44.99
    prices[market["other_edition"]] = 20.00
    assert wish_alert_service.check_all() == {"users": 1, "items": 2, "sent": 1}
    to, subject, text = sent[0]
    assert to == "wisher@example.pt" and subject == "Lista de desejos: 2 jogos com novidades"
    assert "desceu de 59,99 € para 44,99 € na Loja" in text and "de novo em stock: 20,00 € na Loja" in text
    assert f"/game/{market['game']}" in text and "/collection?alerts_off=" in text

    assert wish_alert_service.check_all()["sent"] == 0           # the same news isn't sent twice


def test_english_and_switched_off(market, store):
    prices, sent = store
    client = market["client"]
    prices[market["edition"]] = 30.00
    client.post("/api/auth/register", headers=HEADERS, json={"username": "english", "email": "en@example.pt",
                                                             "password": "segredo123", "lang": "en"})
    wish(client, market["edition"])
    sign_up(client, "quiet")
    wish(client, market["edition"])
    assert client.put("/api/collection/settings", json={"wish_alerts": False}, headers=HEADERS).get_json() == \
        {"public": False, "wish_alerts": False}
    assert client.get("/api/collection").get_json()["wish_alerts"] is False

    prices[market["edition"]] = 20.00
    wish_alert_service.check_all()
    assert [(to, subject) for to, subject, _ in sent] == [("en@example.pt", "Wishlist: news on 1 game")]
    assert "down from €30.00 to €20.00 at Loja" in sent[0][2]


def test_link_switches_them_off_without_logging_in(market, store):
    client = market["client"]
    user = sign_up(client, "leaver")
    client.post("/api/auth/logout", headers=HEADERS)
    token = wish_alert_service.off_link(user["id"]).split("alerts_off=")[1]
    off = lambda t: client.post("/api/collection/alerts-off", json={"token": t}, headers=HEADERS)
    assert off(token + "x").get_json() == {"error": "link_invalid"}
    assert off(token).get_json() == {"ok": True}
    log_in(client, "leaver")
    assert client.get("/api/collection").get_json()["wish_alerts"] is False


def test_login_keeps_the_language(market):
    client = market["client"]
    sign_up(client, "speaker")
    client.post("/api/auth/logout", headers=HEADERS)
    client.post("/api/auth/login", headers=HEADERS, json={"login": "speaker", "password": "segredo123", "lang": "en"})
    assert market["db"].execute("SELECT lang FROM users WHERE username = 'speaker'").fetchone()[0] == "en"
