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
    add(client, market["other_edition"], format="digital", status="finished")

    data = mine(client)
    assert [i["kind"] for i in data["items"]] == ["owned", "owned"] and data["public"] is False
    first = next(i for i in data["items"] if i["id"] == item)
    assert (first["status"], first["hours"], first["format"], first["name"]) == ("playing", 12.5, "physical",
                                                                                 "Market Test Game")
    stats = data["stats"]
    assert (stats["owned"], stats["hours"], stats["completed"], stats["statuses"]) == \
           (2, 12.5, 1, {"playing": 1, "finished": 1})
    assert stats["platforms"] == [["PlayStation 5", 2]]

    assert client.patch(f"/api/collection/{item}", json={"status": "finished", "hours": 30}, headers=HEADERS).status_code == 200
    assert mine(client)["stats"]["completed"] == 2
    # no status chosen: "owned" (what an owned game starts as)
    assert client.patch(f"/api/collection/{item}", json={"status": ""}, headers=HEADERS).status_code == 200
    assert next(i for i in mine(client)["items"] if i["id"] == item)["status"] == "owned"
    assert client.delete(f"/api/collection/{item}", headers=HEADERS).status_code == 200
    assert mine(client)["stats"]["owned"] == 1


def test_hours_that_arent_numbers_are_refused(market):
    client = market["client"]
    sign_up(client, "collector_nan")
    for hours in ("NaN", "sNaN", "Infinity"):
        response = add(client, market["edition"], hours=hours)
        assert (response.status_code, response.get_json()["error"]) == (400, "hours_invalid"), hours


def test_wishlist_becomes_owned(market):
    client = market["client"]
    sign_up(client, "wisher")
    wish = add(client, market["edition"], kind="wishlist", status="playing").get_json()["id"]
    item = next(i for i in mine(client)["items"] if i["id"] == wish)
    assert (item["kind"], item["status"], item["format"]) == ("wishlist", None, None)    # no play status on a wish

    # "I bought it": the wish becomes an owned game
    assert client.patch(f"/api/collection/{wish}", json={"kind": "owned"}, headers=HEADERS).get_json() == {"id": wish}
    assert [(i["kind"], i["format"], i["status"]) for i in mine(client)["items"]] == [("owned", "physical", "owned")]

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
    add(client, market["edition"], status="paused", notes="Só para mim.")
    assert client.get("/api/users/shower/collection").status_code == 404
    assert client.put("/api/collection/settings", json={"public": True}, headers=HEADERS).get_json()["public"] is True

    sign_up(client, "visitor")
    public = client.get("/api/users/shower/collection").get_json()
    assert [i["status"] for i in public["items"]] == ["paused"]
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


def test_achievements(market):
    client = market["client"]
    sign_up(client, "achiever")
    item = add(client, market["edition"], achievements=10, achievements_total=40).get_json()["id"]
    add(client, market["other_edition"], achievements=5)                       # no total: not counted
    stats = mine(client)["stats"]
    assert (stats["achievements"], stats["achievements_total"]) == (10, 40)
    patch = lambda data: client.patch(f"/api/collection/{item}", json=data, headers=HEADERS)
    assert patch({"achievements": 41}).get_json()["error"] == "achievements_invalid"     # more than the total
    assert patch({"achievements_total": "x"}).get_json()["error"] == "achievements_invalid"
    assert patch({"achievements": 40}).status_code == 200
    assert mine(client)["stats"]["achievements"] == 40


def test_a_wish_remembers_its_price(market, monkeypatch):
    """A wish keeps the best price it was added at; a lower price later is a drop, and a good deal."""
    import app.services.game_service as games
    real = games.editions_with_offers
    store_price = {"now": 59.99}

    def with_a_store(ids):           # as if a store sold the edition new, in stock, at store_price
        groups = real(ids)
        for g in groups:
            g["offers"] = [{"price": store_price["now"], "in_stock": True, "condition": "new", "store_name": "Loja",
                            "is_discount": False}]
        return groups
    monkeypatch.setattr(games, "editions_with_offers", with_a_store)

    client = market["client"]
    sign_up(client, "bargain_hunter")
    wish = add(client, market["edition"], kind="wishlist").get_json()["id"]
    item = mine(client)["items"][0]
    assert (item["wish_price"], item["best_price"], item["price_drop"], item["good_deal"]) == (59.99, 59.99, None, False)
    assert client.get("/api/collection/deals").get_json() == {"count": 0, "items": []}

    store_price["now"] = 44.99
    deals = client.get("/api/collection/deals").get_json()
    assert deals["count"] == 1 and deals["items"][0]["price_drop"] == 15.0

    # bought: no longer a wish, no wish price
    client.patch(f"/api/collection/{wish}", json={"kind": "owned"}, headers=HEADERS)
    assert market["db"].execute("SELECT wish_price FROM collection_items WHERE id = ?", wish).fetchone()[0] is None


def test_in_demand_from_two_wishers(market):
    """Games users look for (user, 2026-10-11), counts only: one wish alone is never shown."""
    client = market["client"]
    demand = lambda: client.get("/api/listings/in-demand").get_json()
    sign_up(client, "wants_one")
    add(client, market["edition"], kind="wishlist")
    assert demand() == [] and client.get(f"/api/games/{market['game']}").get_json()["wanted_by"] == 0
    sign_up(client, "wants_two")
    add(client, market["edition"], kind="wishlist")
    assert [(g["game_id"], g["wishers"], g["used"]) for g in demand()] == [(market["game"], 2, 0)]
    assert client.get(f"/api/games/{market['game']}").get_json()["wanted_by"] == 2


def test_profile_showcase_in_the_users_order(market):
    """The profile's sections and top 10 (user, 2026-10-11), shown with a public collection only."""
    client = market["client"]
    sign_up(client, "show_off")
    first = add(client, market["edition"], hours="40", achievements=10, achievements_total=20).get_json()["id"]
    second = add(client, market["other_edition"], hours="5").get_json()["id"]
    put = lambda body: client.put("/api/collection/showcase", json=body, headers=HEADERS)
    assert put({"sections": ["most_played", "favourites"], "favourites": [second, first]}).status_code == 200
    assert mine(client)["profile_sections"] == ["most_played", "favourites"]
    for body in ({"sections": ["most_played", "most_played"], "favourites": []},     # twice
                 {"sections": ["secrets"], "favourites": []},
                 {"sections": [], "favourites": list(range(1, 12))},                    # more than 10
                 {"sections": [], "favourites": [999999]}):                              # not theirs
        assert put(body).get_json()["error"] == "showcase_invalid", body

    assert client.get("/api/users/show_off/collection").status_code == 404           # private: nothing shown
    client.put("/api/collection/settings", json={"public": True}, headers=HEADERS)
    showcase = client.get("/api/users/show_off/collection").get_json()["showcase"]
    assert [(s["section"], [g["game_id"] for g in s["items"]]) for s in showcase] == [
        ("most_played", [market["game"], market["other_game"]]),
        ("favourites", [market["other_game"], market["game"]]),
    ]
    assert showcase[0]["items"][0]["hours"] == 40


def test_an_edition_no_store_sells(market):
    """The user's own edition (user, 2026-10-11: "Lumière Edition"): named once, the same key twice is one."""
    client = market["client"]
    sign_up(client, "lumiere")
    added = client.post("/api/collection", json={"kind": "owned", "game_id": market["game"], "new_edition": "Lumière Edition"},
                        headers=HEADERS)
    assert added.status_code == 201
    item = next(i for i in mine(client)["items"] if i["id"] == added.get_json()["id"])
    assert "Lumière Edition" in item["name"]
    editions = client.get(f"/api/games/{market['game']}/editions").get_json()
    assert [e["name"] for e in editions][-1] == "Lumière Edition"
    # the same edition written without the accent: the one already there
    again = client.post("/api/collection", json={"kind": "wishlist", "game_id": market["game"], "new_edition": "Lumiere Edition"},
                        headers=HEADERS).get_json()["id"]
    assert next(i for i in mine(client)["items"] if i["id"] == again)["edition_id"] == item["edition_id"]
    for name in ("", "x", "Código na caixa", "y" * 101):
        response = client.post("/api/collection", json={"kind": "owned", "game_id": market["game"], "new_edition": name}, headers=HEADERS)
        assert response.get_json()["error"] in ("edition_name_invalid", "not_found"), name


def test_changing_an_items_edition(market):
    client = market["client"]
    sign_up(client, "changer")
    item = add(client, market["edition"]).get_json()["id"]
    patch = lambda body: client.patch(f"/api/collection/{item}", json=body, headers=HEADERS)
    assert patch({"new_edition": "Collector's Edition"}).status_code == 200
    moved = next(i for i in mine(client)["items"] if i["id"] == item)
    assert moved["edition_id"] != market["edition"]
    assert patch({"edition_id": market["other_edition"]}).get_json()["error"] == "edition_invalid"   # another game's
    add(client, market["edition"])                                                                 # Standard again...
    assert patch({"edition_id": market["edition"]}).get_json()["error"] == "already_in_collection"  # ...so not twice
