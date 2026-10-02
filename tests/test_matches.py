"""Fixing wrong matches by hand: moving store products, pins the pipeline respects (throwaway database)."""
import pytest

from helpers import HEADERS, sign_up
from pipeline.process_scraped_data import process_products
from pipeline.rematch import rematch_all


def product(name, n):
    return {"external_name": name, "url": f"https://match.test/{n}", "condition": "new", "console": "PS5",
            "image": None, "price": 39.99, "old_price": None, "in_stock": True}


PRODUCTS = [product("Shadow Quest - Deluxe Edition PS5", 1), product("Shadow Quest - Gold Edition PS5", 2),
            product("Shadow Quest PS5", 3)]


@pytest.fixture
def mod(market):
    """A moderator logged in on the market fixture's client, and a game with three editions from a store."""
    c = market["db"]
    process_products("press_start", PRODUCTS, full_catalog=False)
    sign_up(market["client"], "matcher_mod")
    c.execute("UPDATE users SET role = 'moderator' WHERE username = 'matcher_mod'")
    yield market
    c.execute("DELETE FROM match_overrides")
    c.execute("DELETE ps FROM price_snapshots ps JOIN store_products sp ON sp.id = ps.store_product_id "
              "WHERE sp.url LIKE 'https://match.test/%'")
    games = [r[0] for r in c.execute("SELECT DISTINCT game_id FROM store_products WHERE url LIKE 'https://match.test/%'")]
    c.execute("DELETE FROM store_products WHERE url LIKE 'https://match.test/%'")
    for game in games:
        c.execute("DELETE FROM game_editions WHERE game_id = ?", game)
        c.execute("DELETE FROM games WHERE id = ?", game)
    c.execute("DELETE FROM merged_ids WHERE old_id >= 0")


def editions(client):
    [game] = client.get("/api/mod/matches?q=shadow quest").get_json()
    return game, {e["name"]: e for e in game["editions"]}


def where(m, n):
    return m["db"].execute("SELECT edition_id FROM store_products WHERE url = ?", f"https://match.test/{n}").fetchone()[0]


def test_merge_an_edition_by_moving_its_product(mod):
    client = mod["client"]
    game, by_name = editions(client)
    assert set(by_name) == {"Deluxe Edition", "Gold Edition", "Standard"}
    gold, deluxe = by_name["Gold Edition"], by_name["Deluxe Edition"]

    moved = client.post("/api/mod/matches", headers=HEADERS,
                        json={"product_ids": [gold["products"][0]["id"]], "edition_id": deluxe["id"]})
    assert moved.get_json() == {"edition_id": deluxe["id"]}
    _, after = editions(client)
    assert "Gold Edition" not in after                                  # left empty: merged and removed
    assert sorted(p["pinned"] for p in after["Deluxe Edition"]["products"]) == [False, True]   # the moved one
    assert mod["db"].execute("SELECT new_id FROM merged_ids WHERE kind = 'edition' AND old_id = ?",
                             gold["id"]).fetchone()[0] == deluxe["id"]

    # the next scrape and a rematch leave the pinned product where the moderator put it
    process_products("press_start", PRODUCTS, full_catalog=False)
    rematch_all()
    assert where(mod, 2) == deluxe["id"]

    # unpinned: the rematch goes by the name again
    assert [p["product_id"] for p in client.get("/api/mod/pins").get_json()] == [gold["products"][0]["id"]]
    assert client.delete(f"/api/mod/pins/{gold['products'][0]['id']}", headers=HEADERS).status_code == 200
    rematch_all()
    assert where(mod, 2) != deluxe["id"]
    assert client.get("/api/mod/log").get_json()[0]["action"] == "unpin_product"


def test_move_to_a_new_edition(mod):
    client = mod["client"]
    game, by_name = editions(client)
    standard = by_name["Standard"]["products"][0]["id"]
    new = client.post("/api/mod/matches", headers=HEADERS,
                      json={"product_ids": [standard], "game_id": game["id"], "new_edition": "Steelbook Edition"}).get_json()
    _, after = editions(client)
    assert after["Steelbook Edition"]["id"] == new["edition_id"]
    assert "Standard" not in after                                      # its only product moved
    # the same name again goes to that edition, not a second one
    again = client.post("/api/mod/matches", headers=HEADERS,
                        json={"product_ids": [standard], "game_id": game["id"], "new_edition": "steelbook"}).get_json()
    assert again == new


def test_move_errors_and_access(mod):
    client = mod["client"]
    post = lambda data: client.post("/api/mod/matches", headers=HEADERS, json=data)
    assert post({"product_ids": [], "edition_id": 1}).get_json()["error"] == "products_invalid"
    assert post({"product_ids": [999999], "edition_id": 1}).status_code == 404
    _, by_name = editions(client)
    some = by_name["Standard"]["products"][0]["id"]
    assert post({"product_ids": [some], "edition_id": 999999}).status_code == 404
    assert post({"product_ids": [some], "game_id": 999999, "new_edition": "X"}).get_json()["error"] == "edition_invalid"
    assert client.delete("/api/mod/pins/999999", headers=HEADERS).status_code == 404

    sign_up(client, "not_a_mod")
    assert client.get("/api/mod/matches?q=shadow").status_code == 403
    assert post({"product_ids": [some], "edition_id": 1}).status_code == 403
