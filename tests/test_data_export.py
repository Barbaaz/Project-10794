"""Downloading one's own data (GDPR); on a throwaway database."""
import json

from helpers import HEADERS, completed_purchase, log_in


def test_the_file_has_the_users_data_and_nobody_elses_secrets(market):
    client = market["client"]
    conversation_id = completed_purchase(market)             # "seller" sold to "buyer"; buyer logged in
    client.post(f"/api/conversations/{conversation_id}/messages", json={"body": "Chegou bem"}, headers=HEADERS)
    client.post(f"/api/conversations/{conversation_id}/rating", json={"stars": 4, "comment": "Ok"}, headers=HEADERS)
    client.post("/api/collection", json={"edition_id": market["edition"], "kind": "wishlist"}, headers=HEADERS)
    client.put(f"/api/games/{market['game']}/reviews/mine", json={"score": 7, "body": "Giro"}, headers=HEADERS)
    listing_id = client.get(f"/api/conversations/{conversation_id}").get_json()["listing_id"]
    assert client.post("/api/reports", json={"kind": "listing", "target_id": listing_id, "reason": "other"},
                       headers=HEADERS).status_code == 201

    response = client.get("/api/auth/export")
    assert response.status_code == 200
    assert response.headers["Content-Disposition"].startswith('attachment; filename="project10794-')
    data = json.loads(response.data)

    assert data["account"]["username"] == "buyer" and data["account"]["email"] == "buyer@example.pt"
    assert "password_hash" not in data["account"] and "segredo" not in response.get_data(as_text=True)
    assert data["listings"] == []
    [conversation] = data["conversations"]
    assert (conversation["role"], conversation["other_user"], conversation["deal_status"]) == \
        ("buyer", "seller", "completed")
    assert {"sender": "me", "body": "Chegou bem"}.items() <= conversation["messages"][-1].items()
    assert [(r["stars"], r["rated"]) for r in data["ratings_given"]] == [(4, "seller")]
    assert data["ratings_received"] == []
    assert [(i["kind"], i["game_id"]) for i in data["collection"]] == [("wishlist", market["game"])]
    assert [(r["score"], r["body"]) for r in data["game_reviews"]] == [(7, "Giro")]
    assert [r["kind"] for r in data["reports_made"]] == ["listing"]

    log_in(client, "seller")
    data = client.get("/api/auth/export").get_json()
    [listing] = data["listings"]
    assert listing["status"] == "sold" and len(listing["photos"]) == 3
    assert all(url.startswith("/media/") for url in listing["photos"])
    assert [(r["stars"], r["rater"]) for r in data["ratings_received"]] == [(4, "buyer")]
    assert data["reports_made"] == []                 # the buyer's report on their listing isn't told


def test_exporting_needs_a_login(market):
    assert market["client"].get("/api/auth/export").status_code == 401
