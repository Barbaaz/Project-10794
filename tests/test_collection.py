"""A user's game collection and wishlist (on a throwaway database)."""
from helpers import HEADERS, new_listing, sign_up


def add(client, edition_id, kind="owned", **fields):
    return client.post("/api/collection", json={"edition_id": edition_id, "kind": kind, **fields}, headers=HEADERS)


def mine(client):
    return client.get("/api/collection").get_json()


def test_needs_an_account(market):
    client = market["client"]
    assert client.get("/api/collection").status_code == 401
    assert add(client, market["edition"]).status_code == 401


def test_owned_games_with_status_and_stats(market):
    client = market["client"]
    sign_up(client, "collector")
    item = add(client, market["edition"], status="playing", hours="12,5", notes="Comprado em 2025.").get_json()["id"]
    assert add(client, market["edition"]).get_json()["id"] == item               # the same edition once per list
    add(client, market["other_edition"], format="digital", status="platinum")

    data = mine(client)
    assert [i["kind"] for i in data["items"]] == ["owned", "owned"] and data["public"] is False
    first = next(i for i in data["items"] if i["id"] == item)
    assert (first["status"], first["hours"], first["format"], first["name"]) == ("playing", 12.5, "physical",
                                                                                 "Market Test Game")
    stats = data["stats"]
    assert (stats["owned"], stats["hours"], stats["completed"], stats["statuses"]) == \
           (2, 12.5, 1, {"playing": 1, "platinum": 1})
    assert stats["platforms"] == [["PlayStation 5", 2]]

    assert client.patch(f"/api/collection/{item}", json={"status": "completed", "hours": 30}, headers=HEADERS).status_code == 200
    assert mine(client)["stats"]["completed"] == 2
    assert client.delete(f"/api/collection/{item}", headers=HEADERS).status_code == 200
    assert mine(client)["stats"]["owned"] == 1


def test_wishlist_becomes_owned(market):
    client = market["client"]
    sign_up(client, "wisher")
    wish = add(client, market["edition"], kind="wishlist", status="playing").get_json()["id"]
    item = next(i for i in mine(client)["items"] if i["id"] == wish)
    assert (item["kind"], item["status"], item["format"]) == ("wishlist", None, None)    # no play status on a wish

    # "I bought it": the wish becomes an owned game
    assert client.patch(f"/api/collection/{wish}", json={"kind": "owned"}, headers=HEADERS).get_json() == {"id": wish}
    assert [(i["kind"], i["format"]) for i in mine(client)["items"]] == [("owned", "physical")]

    # adding an owned game takes it off the wishlist
    add(client, market["other_edition"], kind="wishlist")
    add(client, market["other_edition"])
    assert sorted(i["kind"] for i in mine(client)["items"]) == ["owned", "owned"]


def test_checks(market):
    client = market["client"]
    sign_up(client, "careful")
    assert add(client, market["edition"], kind="stolen").get_json()["error"] == "kind_invalid"
    assert add(client, 999999).status_code == 404
    for fields, error in [({"status": "bored"}, "play_status_invalid"), ({"format": "cassette"}, "format_invalid"),
                          ({"hours": "-1"}, "hours_invalid"), ({"hours": "lots"}, "hours_invalid"),
                          ({"notes": "x" * 1001}, "notes_long")]:
        assert add(client, market["edition"], **fields).get_json()["error"] == error, fields
    item = add(client, market["edition"]).get_json()["id"]
    sign_up(client, "someone_else")
    assert client.patch(f"/api/collection/{item}", json={"hours": 1}, headers=HEADERS).status_code == 404
    assert client.delete(f"/api/collection/{item}", headers=HEADERS).status_code == 404


def test_private_unless_made_public(market):
    client = market["client"]
    sign_up(client, "shower")
    add(client, market["edition"], status="completed", notes="Só para mim.")
    assert client.get("/api/users/shower/collection").status_code == 404
    assert client.put("/api/collection/settings", json={"public": True}, headers=HEADERS).get_json() == {"public": True}

    sign_up(client, "visitor")
    public = client.get("/api/users/shower/collection").get_json()
    assert [i["status"] for i in public["items"]] == ["completed"]
    assert "notes" not in public["items"][0] and "hours" not in public["items"][0]        # notes stay private
    assert public["stats"]["owned"] == 1


def test_worth_counts_store_and_used_prices(market):
    client = market["client"]
    sign_up(client, "seller_for_worth")
    new_listing(market, price="15.00")                    # a used copy of the same edition, for the used value
    sign_up(client, "owner_for_worth")
    add(client, market["edition"])
    stats = mine(client)["stats"]
    assert (stats["worth_used"], stats["priced_used"]) == (15.0, 1)
    assert (stats["worth_new"], stats["priced_new"]) == (0, 0)          # no store sells the test game
