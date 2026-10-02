"""Ratings between users after a purchase (on a throwaway database)."""
from helpers import HEADERS, completed_purchase, log_in, new_listing, sign_up


def rate(client, conversation_id, stars, comment=None):
    return client.post(f"/api/conversations/{conversation_id}/rating", json={"stars": stars, "comment": comment},
                       headers=HEADERS)


def test_both_sides_rate_after_a_purchase(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    assert [p["other_username"] for p in client.get("/api/ratings/pending").get_json()] == ["seller"]

    ratings = rate(client, conversation_id, 5, "Tudo perfeito, recomendo!").get_json()
    assert ratings["mine"]["stars"] == 5 and ratings["theirs"] is None
    assert client.get("/api/ratings/pending").get_json() == []
    # changing it within the window updates the same rating
    assert rate(client, conversation_id, 4).get_json()["mine"]["stars"] == 4

    log_in(client, "seller")
    assert rate(client, conversation_id, 5, "Pagou logo.").status_code == 200
    seller = client.get("/api/users/seller").get_json()
    assert (seller["rating"], seller["rating_count"]) == (4, 1)
    assert seller["ratings"][0]["rated_as"] == "seller" and seller["ratings"][0]["rater_username"] == "buyer"
    assert "email" not in seller

    # the conversation shows both ratings once completed
    view = client.get(f"/api/conversations/{conversation_id}").get_json()
    assert (view["ratings"]["mine"]["stars"], view["ratings"]["theirs"]["stars"]) == (5, 4)


def test_rating_rules(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    for stars in (0, 6, "x"):
        assert rate(client, conversation_id, stars).get_json()["error"] == "stars_invalid"
    assert rate(client, conversation_id, 3, "x" * 501).get_json()["error"] == "comment_long"
    sign_up(client, "stranger")
    assert rate(client, conversation_id, 1).status_code == 404        # not your purchase


def test_only_completed_purchases_are_rated(market):
    client = market["client"]
    sign_up(client, "seller2")
    listing = new_listing(market).get_json()
    sign_up(client, "buyer2")
    conversation_id = client.post(f"/api/listings/{listing['id']}/conversation", json={"message": "Olá"},
                                  headers=HEADERS).get_json()["id"]
    response = rate(client, conversation_id, 5)
    assert (response.status_code, response.get_json()["error"]) == (409, "not_completed")


def test_an_overdue_rating_blocks_buying_and_selling(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    # not overdue yet: still free to sell
    assert new_listing(market).status_code == 201

    market["db"].execute("UPDATE conversations SET completed_at = DATEADD(DAY, -15, SYSUTCDATETIME()) WHERE id = ?",
                         conversation_id)
    assert client.get("/api/ratings/pending").get_json()[0]["overdue"] is True
    response = new_listing(market)
    assert (response.status_code, response.get_json()["error"]) == (403, "ratings_overdue")

    # the seller hasn't rated that purchase either: blocked too
    log_in(client, "seller")
    assert new_listing(market).get_json()["error"] == "ratings_overdue"

    # buying (a third user's listing) is blocked as well; messaging isn't
    sign_up(client, "seller3")
    other = new_listing(market).get_json()
    log_in(client, "buyer")
    blocked = client.post(f"/api/listings/{other['id']}/conversation", json={"buy": True}, headers=HEADERS)
    assert (blocked.status_code, blocked.get_json()["error"]) == (403, "ratings_overdue")
    assert client.post(f"/api/listings/{other['id']}/conversation", json={"message": "Olá"}, headers=HEADERS).status_code == 200

    rate(client, conversation_id, 5)
    assert new_listing(market).status_code == 201


def test_replies_and_the_edit_window(market):
    client = market["client"]
    conversation_id = completed_purchase(market)
    rating = rate(client, conversation_id, 2, "Demorou muito a enviar.").get_json()["mine"]
    assert client.post(f"/api/ratings/{rating['id']}/reply", json={"reply": "x"}, headers=HEADERS).status_code == 404

    log_in(client, "seller")
    answer = client.post(f"/api/ratings/{rating['id']}/reply", json={"reply": "Os CTT atrasaram, desculpe."},
                         headers=HEADERS).get_json()
    assert answer["reply"] == "Os CTT atrasaram, desculpe."

    market["db"].execute("UPDATE user_ratings SET created_at = DATEADD(DAY, -15, SYSUTCDATETIME()) WHERE id = ?", rating["id"])
    log_in(client, "buyer")
    response = rate(client, conversation_id, 5)
    assert (response.status_code, response.get_json()["error"]) == (409, "rating_locked")
