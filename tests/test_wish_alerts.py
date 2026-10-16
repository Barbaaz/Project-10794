"""Wishlist alerts by e-mail after the morning run (on a throwaway database)."""
from decimal import Decimal

import pytest

from helpers import HEADERS, log_in, new_listing, sign_up
from app.services import wish_alert_service
from app.services.wish_alert_service import change, used_change


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

    assert wish_alert_service.check_all() == {"users": 0, "items": 0, "sent": 0, "pushed": 0}
    prices[market["edition"]] = 44.99
    prices[market["other_edition"]] = 20.00
    assert wish_alert_service.check_all() == {"users": 1, "items": 2, "sent": 1, "pushed": 0}
    to, subject, text = sent[0]
    assert to == "wisher@example.pt" and subject == "Lista de desejos: 2 jogos com novidades"
    assert "desceu de 59,99 € para 44,99 € na Loja" in text and "à venda: 20,00 € na Loja" in text
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
    bell = {"bell": True, "sale": True, "low": True, "drop": True, "min_discount": 0}      # the header bell's, untouched
    assert client.put("/api/collection/settings", json={"wish_alerts": False}, headers=HEADERS).get_json() == \
        {"public": False, "wish_alerts": False, "lang": "pt", "notify": bell}
    assert client.get("/api/collection").get_json()["wish_alerts"] is False
    assert client.get("/api/collection/settings").get_json() == {"public": False, "wish_alerts": False, "lang": "pt", "notify": bell}

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


def test_used_change_rules():
    assert used_change(None, True) == (None, True)              # first check: remembered
    assert used_change(False, True) == ("used_for_sale", True)
    assert used_change(True, True) == (None, True)              # still for sale: said already
    assert used_change(True, False) == (None, False)


def test_a_user_selling_a_wished_game(market, store):
    prices, sent = store
    client = market["client"]
    sign_up(client, "looker")
    wish(client, market["edition"])                              # looking for it: nobody sells it
    assert wish_alert_service.check_all()["sent"] == 0
    sign_up(client, "seller_of_it")
    assert new_listing(market, price="25").status_code == 201
    assert wish_alert_service.check_all() == {"users": 1, "items": 1, "sent": 1, "pushed": 0}
    assert "à venda em segunda mão por um utilizador: 25,00 €" in sent[0][2]
    assert wish_alert_service.check_all()["sent"] == 0           # once


def test_target_change_rules():
    from app.services.wish_alert_service import target_change
    assert target_change(None, None, True) == (None, None)                 # no target
    assert target_change(Decimal("20"), None, True) == ("target_reached", True)
    assert target_change(Decimal("20"), True, True) == (None, True)         # said already
    assert target_change(Decimal("20"), True, False) == (None, False)       # above it again: may be sent again


def test_a_target_price(market, store):
    """User, 2026-10-16: tell me when it costs this much (new or used), in the bell and by e-mail, once."""
    prices, sent = store
    client = market["client"]
    prices[market["edition"]] = 39.99
    sign_up(client, "target")
    item = wish(client, market["edition"]).get_json()["id"]
    target = lambda value: client.patch(f"/api/collection/{item}", json={"target_price": value}, headers=HEADERS)
    for wrong in ("abc", "0", "-5", "0,49", "10000.01", "NaN"):
        assert target(wrong).get_json() == {"error": "target_invalid"}, wrong
    assert target("30,00").status_code == 200
    wish_alert_service.check_all()
    assert client.get("/api/collection/deals").get_json()["count"] == 0 and not sent

    prices[market["edition"]] = 29.99                       # at the target: the bell (always) and an e-mail
    deals = client.get("/api/collection/deals").get_json()
    assert [(d["reason"], d["target_price"]) for d in deals["items"]] == [("target", 30.0)]
    assert wish_alert_service.check_all()["sent"] == 1
    assert "chegou ao seu preço-alvo de 30,00 €: 29,99 € na Loja" in sent[0][2]
    assert "desceu" not in sent[0][2]                       # the target says it all
    assert wish_alert_service.check_all()["sent"] == 0       # once

    assert target("25").status_code == 200                  # a new target: sent again once it's there
    prices[market["edition"]] = None
    assert wish_alert_service.check_all()["sent"] == 0
    sign_up(client, "cheap_seller")
    assert new_listing(market, price="22").status_code == 201      # a used copy under it counts too
    wish_alert_service.check_all()
    assert "chegou ao seu preço-alvo de 25,00 €: 22,00 € em segunda mão" in sent[-1][2]

    log_in(client, "target")
    assert target("").status_code == 200                    # cleared
    assert client.get("/api/collection/deals").get_json()["count"] == 0
    assert client.patch(f"/api/collection/{item}", json={"kind": "owned"}, headers=HEADERS).status_code == 200
