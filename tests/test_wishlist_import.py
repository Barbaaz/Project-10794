"""Favourites an old browser kept go onto the wishlist (favourites were folded into it; throwaway database)."""
from helpers import HEADERS, sign_up


def wished(client):
    return sorted(int(e) for e, mine in client.get("/api/collection/editions").get_json().items() if "wishlist" in mine)


def test_import_needs_an_account(market):
    assert market["client"].post("/api/collection/import", json={"ids": [market["edition"]]},
                                 headers=HEADERS).status_code == 401


def test_browser_favorites_go_onto_the_wishlist(market):
    client = market["client"]
    sign_up(client, "fan_four")
    # an old id from before a duplicate clean-up follows the merge; unknown ids are skipped
    market["db"].execute("INSERT INTO merged_ids (kind, old_id, new_id) VALUES ('edition', 888001, ?)", market["edition"])
    try:
        response = client.post("/api/collection/import", json={"ids": [888001, market["other_edition"], 999999]},
                               headers=HEADERS)
        assert response.get_json() == {"added": 2}
        assert wished(client) == sorted([market["edition"], market["other_edition"]])
    finally:
        market["db"].execute("DELETE FROM merged_ids WHERE old_id = 888001")


def test_owned_or_wished_editions_are_left_as_they_are(market):
    client = market["client"]
    sign_up(client, "fan_five")
    client.post("/api/collection", json={"edition_id": market["edition"], "kind": "owned"}, headers=HEADERS)
    response = client.post("/api/collection/import", json={"ids": [market["edition"], market["edition"]]},
                           headers=HEADERS)
    assert response.get_json() == {"added": 0}
    assert wished(client) == []
