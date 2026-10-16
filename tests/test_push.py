"""Push notifications on phones and computers (user, 2026-10-16); on a throwaway database, nothing really sent."""
import json

import pytest

from helpers import HEADERS, log_in, sign_up
from app.services import push_service, wish_alert_service


def device(n=1):
    return {"endpoint": f"https://push.example.com/send/{n}", "keys": {"p256dh": f"key{n}", "auth": f"auth{n}"}}


@pytest.fixture
def pushes(monkeypatch):
    """What the push services were sent: [(endpoint, message)]; endpoints in `gone` answer 410."""
    import pywebpush
    sent, gone = [], set()

    def webpush(info, data, **kwargs):
        if info["endpoint"] in gone:
            raise pywebpush.WebPushException("gone", response=type("R", (), {"status_code": 410})())
        assert kwargs["vapid_claims"]["sub"].startswith(("mailto:", "https://"))
        sent.append((info["endpoint"], json.loads(data)))
    monkeypatch.setattr(pywebpush, "webpush", webpush)
    monkeypatch.setattr(wish_alert_service.mail_service, "send", lambda *args: False)
    return sent, gone


def subscribe(client, body):
    return client.post("/api/push/subscribe", json=body, headers=HEADERS)


def test_the_public_key(market):
    key = market["client"].get("/api/push/key").get_json()["key"]
    assert len(key) == 87 and "=" not in key            # 65 bytes, base64url without padding


def test_subscribing_needs_a_login_and_a_real_subscription(market):
    client = market["client"]
    assert subscribe(client, device()).status_code == 401
    sign_up(client, "pusher")
    for wrong in ({}, {"endpoint": "https://x"}, {"endpoint": "http://push.example.com/1", "keys": {"p256dh": "a", "auth": "b"}},
                  {"endpoint": "https://push.example.com/1", "keys": {"p256dh": "", "auth": "b"}},
                  {"endpoint": "https://push.example.com/" + "x" * 1000, "keys": {"p256dh": "a", "auth": "b"}}):
        assert subscribe(client, wrong).get_json() == {"error": "push_invalid"}, wrong
    assert subscribe(client, device()).get_json() == {"ok": True}
    assert subscribe(client, device()).get_json() == {"ok": True}          # the same device again: one row
    assert market["db"].execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 1


def test_a_test_notification_and_a_device_that_is_gone(market, pushes):
    sent, gone = pushes
    client = market["client"]
    sign_up(client, "tester")
    subscribe(client, device(1))
    subscribe(client, device(2))
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 2}
    assert sent[0][1] == {"title": "SaveOnGames", "body": "As notificações estão ligadas neste dispositivo.",
                          "url": "/account#notifications", "tag": "test"}
    gone.add(device(1)["endpoint"])
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 1}
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 1}    # forgotten: not tried again
    assert len(sent) == 4


def test_a_device_follows_who_is_logged_in_and_turns_off(market, pushes):
    sent, _ = pushes
    client = market["client"]
    sign_up(client, "first")
    subscribe(client, device())
    sign_up(client, "second")                    # the same browser, another user turns them on
    subscribe(client, device())
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 1}
    log_in(client, "first")
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 0}
    log_in(client, "second")
    client.post("/api/push/unsubscribe", json={"endpoint": device()["endpoint"]}, headers=HEADERS)
    assert client.post("/api/push/test", headers=HEADERS).get_json() == {"sent": 0}


def test_at_most_ten_devices(market, pushes):
    client = market["client"]
    sign_up(client, "many")
    for n in range(12):
        subscribe(client, device(n))
    endpoints = [r[0] for r in market["db"].execute("SELECT endpoint FROM push_subscriptions ORDER BY id").fetchall()]
    assert endpoints == [device(n)["endpoint"] for n in range(2, 12)]       # the oldest went


def test_wishlist_news_on_the_devices_also_with_emails_off(market, pushes):
    sent, _ = pushes
    client = market["client"]
    sign_up(client, "phone_only")
    client.put("/api/collection/settings", json={"wish_alerts": False}, headers=HEADERS)
    item = client.post("/api/collection", json={"edition_id": market["edition"], "kind": "wishlist"}, headers=HEADERS).get_json()["id"]
    subscribe(client, device())
    assert client.patch(f"/api/collection/{item}", json={"target_price": "10000"}, headers=HEADERS).status_code == 200

    sign_up(client, "seller_for_push")
    from helpers import new_listing
    assert new_listing(market, price="25").status_code == 201            # a used copy: under the target
    result = wish_alert_service.check_all()
    assert result["pushed"] == 1 and result["sent"] == 0
    message = sent[-1][1]
    assert message["title"] == "Lista de desejos" and message["tag"] == "wishlist"
    assert "chegou ao seu preço-alvo de 10000,00 €: 25,00 € em segunda mão" in message["body"]
    assert message["url"] == f"/game/{market['game']}"
    assert wish_alert_service.check_all()["pushed"] == 0                 # once


def test_more_news_in_one_notification():
    item = {"name": "Jogo", "platform_name": "PS5", "best_price": 20, "best_store": "Loja", "old": 30, "game_id": 1}
    title, text, url, tag = wish_alert_service.notification("en", [("price_drop", item), ("back_in_stock", item), ("back_in_stock", item)])
    assert (title, url, tag) == ("Wishlist", "/wishlist", "wishlist")
    assert text == "Jogo (PS5): down from €30.00 to €20.00 at Loja\nand 2 more games"


def test_a_deleted_account_leaves_no_devices(market):
    client = market["client"]
    sign_up(client, "leaving")
    subscribe(client, device())
    assert client.post("/api/auth/delete", json={"password": "segredo123"}, headers=HEADERS).status_code == 200
    assert market["db"].execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 0
