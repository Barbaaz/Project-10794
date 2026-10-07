"""Deleting an account: anonymised, not removed (user, 2026-10-07); on a throwaway database."""
from helpers import HEADERS, completed_purchase, log_in, new_listing, sign_up


def delete(client, password="segredo123"):
    return client.post("/api/auth/delete", json={"password": password}, headers=HEADERS)


def test_a_deleted_account_is_anonymised_and_the_others_keep_their_history(market):
    client, db = market["client"], market["db"]
    conversation_id = completed_purchase(market)             # "seller" sold to "buyer"; buyer logged in, hasn't rated

    log_in(client, "seller")
    assert client.post(f"/api/conversations/{conversation_id}/rating", json={"stars": 5, "comment": "Rápido"},
                       headers=HEADERS).status_code == 200
    on_sale = new_listing(market).get_json()
    client.post("/api/collection", json={"edition_id": market["edition"], "kind": "owned"}, headers=HEADERS)
    client.put(f"/api/games/{market['game']}/reviews/mine", json={"score": 8, "body": "Bom"}, headers=HEADERS)
    sign_up(client, "asker")                                  # asks to buy the copy on sale, not accepted yet
    asked = client.post(f"/api/listings/{on_sale['id']}/conversation", json={"buy": True}, headers=HEADERS).get_json()["id"]

    log_in(client, "seller")
    seller_id = client.get("/api/auth/me").get_json()["id"]
    assert delete(client).status_code == 200
    assert client.get("/api/auth/me").get_json() is None      # logged out
    assert client.post("/api/auth/login", json={"login": "seller", "password": "segredo123"},
                       headers=HEADERS).status_code == 400

    user = db.execute("SELECT username, email, password_hash, display_name, location, is_active, role, deleted_at "
                      "FROM users WHERE id = ?", seller_id).fetchone()
    assert user[:7] == (None, f"deleted-{seller_id}@deleted.invalid", None, "", None, False, "user")
    assert user.deleted_at is not None
    assert db.execute("SELECT COUNT(*) FROM collection_items WHERE user_id = ?", seller_id).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM listing_photos p JOIN user_listings l ON l.id = p.listing_id "
                      "WHERE l.user_id = ?", seller_id).fetchone()[0] == 0
    assert not list((market["dir"] / "listings").rglob("*.*"))          # the photo files too
    assert db.execute("SELECT status FROM user_listings WHERE id = ?", on_sale["id"]).fetchone()[0] == "removed"
    assert client.get("/api/users/seller").status_code == 404

    # the asker's request was declined and says why; nothing more can be sent
    log_in(client, "asker")
    view = client.get(f"/api/conversations/{asked}").get_json()
    assert (view["deal_status"], view["other_username"], view["other_deleted"], view["steps"]) == \
        ("declined", None, True, [])
    assert view["messages"][-1]["event"] == "account_deleted"
    assert client.post(f"/api/conversations/{asked}/messages", json={"body": "Olá?"},
                       headers=HEADERS).get_json()["error"] == "user_deleted"

    # the buyer keeps the purchase, the listing and the rating they got; nothing left to rate
    log_in(client, "buyer")
    view = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert (view["deal_status"], view["other_username"]) == ("completed", None)
    assert client.get(f"/api/listings/{view['listing_id']}").get_json()["seller_username"] is None
    assert client.get("/api/ratings/pending").get_json() == []
    assert client.post(f"/api/conversations/{conversation_id}/rating", json={"stars": 1},
                       headers=HEADERS).get_json()["error"] == "user_deleted"
    ratings = client.get("/api/users/buyer").get_json()["ratings"]
    assert [(r["stars"], r["comment"], r["rater_username"]) for r in ratings] == [(5, "Rápido", None)]

    # the review stays, without a name
    reviews = client.get(f"/api/games/{market['game']}/reviews").get_json()
    assert [(r["score"], r["username"]) for r in reviews["reviews"]] == [(8, None)]


def test_not_while_a_purchase_is_under_way(market):
    client = market["client"]
    sign_up(client, "seller")
    listing = new_listing(market).get_json()
    sign_up(client, "buyer")
    conversation_id = client.post(f"/api/listings/{listing['id']}/conversation", json={"buy": True},
                                  headers=HEADERS).get_json()["id"]
    log_in(client, "seller")
    client.post(f"/api/conversations/{conversation_id}/steps", json={"action": "accept"}, headers=HEADERS)
    for who in ("seller", "buyer"):
        log_in(client, who)
        assert delete(client).get_json()["error"] == "account_in_deal"
        assert client.get("/api/auth/me").get_json()["username"] == who


def test_the_password_is_needed_and_admins_cant(market):
    client, db = market["client"], market["db"]
    sign_up(client, "someone")
    assert delete(client, "wrong-password").get_json()["error"] == "password_wrong"
    assert delete(client, "").get_json()["error"] == "password_wrong"
    db.execute("UPDATE users SET role = 'admin' WHERE username = 'someone'")
    assert delete(client).get_json()["error"] == "admin_cannot_delete"
    assert client.get("/api/auth/me").get_json()["username"] == "someone"


def test_deleting_needs_a_login(market):
    assert market["client"].post("/api/auth/delete", json={"password": "x"}, headers=HEADERS).status_code == 401
