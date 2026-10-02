"""Favourites per account (on a throwaway database)."""
from helpers import HEADERS, log_in, sign_up


def favorites(client):
    return client.get("/api/favorites")


def test_favorites_need_an_account(market):
    client = market["client"]
    assert favorites(client).status_code == 401
    assert client.put(f"/api/favorites/{market['edition']}", headers=HEADERS).status_code == 401


def test_each_user_sees_only_their_own(market):
    client = market["client"]
    sign_up(client, "fan_one")
    assert client.put(f"/api/favorites/{market['edition']}", headers=HEADERS).get_json() == [market["edition"]]
    # starring twice keeps it once
    assert client.put(f"/api/favorites/{market['edition']}", headers=HEADERS).get_json() == [market["edition"]]

    sign_up(client, "fan_two")
    assert favorites(client).get_json() == []
    client.put(f"/api/favorites/{market['other_edition']}", headers=HEADERS)
    assert favorites(client).get_json() == [market["other_edition"]]

    log_in(client, "fan_one")
    assert favorites(client).get_json() == [market["edition"]]
    assert client.delete(f"/api/favorites/{market['edition']}", headers=HEADERS).get_json() == []


def test_unknown_edition(market):
    client = market["client"]
    sign_up(client, "fan_three")
    assert client.put("/api/favorites/999999", headers=HEADERS).status_code == 404


def test_browser_favorites_move_into_the_account(market):
    client = market["client"]
    sign_up(client, "fan_four")
    # an old id from before a duplicate clean-up follows the merge; unknown ids are skipped
    market["db"].execute("INSERT INTO merged_ids (kind, old_id, new_id) VALUES ('edition', 888001, ?)", market["edition"])
    try:
        imported = client.post("/api/favorites/import", json={"ids": [888001, market["other_edition"], 999999]},
                               headers=HEADERS).get_json()
        assert sorted(imported) == sorted([market["edition"], market["other_edition"]])
    finally:
        market["db"].execute("DELETE FROM merged_ids WHERE old_id = 888001")
