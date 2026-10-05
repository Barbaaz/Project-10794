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
    c.execute("DELETE FROM price_snapshots ps USING store_products sp WHERE sp.id = ps.store_product_id "
              "AND sp.url LIKE 'https://match.test/%'")
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


@pytest.mark.parametrize("path, body", [
    ("/api/mod/matches", {"product_ids": "12", "edition_id": 1}),        # a text, not a list
    ("/api/mod/matches", {"product_ids": ["x"], "edition_id": 1}),
    ("/api/mod/matches", {"product_ids": [1], "game_id": "x", "new_edition": "Gold"}),
    ("/api/mod/duplicates/merge", {"from_id": "x", "into_id": 1}),
    ("/api/mod/duplicates/dismiss", {"a": None, "b": 2}),
])
def test_ids_that_arent_numbers_are_refused(mod, path, body):
    response = mod["client"].post(path, json=body, headers=HEADERS)
    assert (response.status_code, response.get_json()["error"]) == (400, "ids_invalid")


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


def test_a_pinned_product_stays_on_its_games_platform(mod):
    """A PS4 disc the store lists on its PS5 page: the game moved to PS4, the product pinned to it."""
    client, c = mod["client"], mod["db"]
    game, by_name = editions(client)
    standard = by_name["Standard"]
    ps4 = c.execute("SELECT id FROM platforms WHERE code = 'PS4'").fetchone()[0]
    c.execute("UPDATE games SET platform_id = ? WHERE id = ?", ps4, game["id"])
    client.post("/api/mod/matches", headers=HEADERS, json={"product_ids": [standard["products"][0]["id"]],
                                                           "edition_id": standard["id"]})
    process_products("press_start", PRODUCTS, full_catalog=False)       # the store still says PS5
    assert c.execute("SELECT platform_id FROM store_products WHERE url = ?", "https://match.test/3").fetchone()[0] == ps4


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


def test_english_name_by_a_moderator(mod):
    client = mod["client"]
    game, _ = editions(client)
    put = lambda title: client.put(f"/api/mod/games/{game['id']}/title-en", headers=HEADERS, json={"title_en": title})
    assert put("Shadow Quest: Reborn").get_json() == {"title_en": "Shadow Quest: Reborn"}
    cards = client.get("/api/games/catalog?q=shadow quest").get_json()["groups"]
    assert {c["name_en"] for c in cards} == {"Shadow Quest: Reborn", "Shadow Quest: Reborn — Deluxe Edition",
                                             "Shadow Quest: Reborn — Gold Edition"}
    assert {c["name"] for c in cards} >= {"Shadow Quest"}                   # the Portuguese page keeps the store's
    assert client.get("/api/mod/log").get_json()[0]["action"] == "rename_game_en"
    assert put("x" * 301).get_json()["error"] == "title_en_invalid"
    assert put("").get_json() == {"title_en": ""}                         # back to the store's title

    sign_up(client, "not_a_mod_2")
    assert put("Nope").status_code == 403


def test_title_corrected_by_a_moderator_is_kept(mod):
    """A store's typo fixed by hand: the next scrape and a rematch keep it, IGDB looks the game up again."""
    client, c = mod["client"], mod["db"]
    game, by_name = editions(client)
    c.execute("UPDATE games SET igdb_checked_at = utcnow() WHERE id = ?", game["id"])
    put = lambda title: client.put(f"/api/mod/games/{game['id']}/title", headers=HEADERS, json={"title": title})
    assert put("Shadow Quest: Reborn").get_json() == {"title": "Shadow Quest: Reborn", "title_fixed": True}
    assert c.execute("SELECT igdb_checked_at FROM games WHERE id = ?", game["id"]).fetchone()[0] is None

    upper = [dict(p, external_name=p["external_name"].upper()) for p in PRODUCTS]
    process_products("press_start", upper, full_catalog=False)
    rematch_all()
    [after] = client.get("/api/mod/matches?q=shadow quest").get_json()
    assert (after["id"], after["title"], after["title_fixed"]) == (game["id"], "Shadow Quest: Reborn", True)
    assert where(mod, 3) == by_name["Standard"]["id"]                       # still matched by the old key
    assert client.get("/api/mod/log").get_json()[0]["action"] == "rename_game"

    assert put("x" * 301).get_json()["error"] == "title_invalid"
    assert put("").get_json() == {"title": "Shadow Quest: Reborn", "title_fixed": False}
    rematch_all()                                                           # the stores' title again
    assert client.get("/api/mod/matches?q=shadow quest").get_json()[0]["title"] == "SHADOW QUEST"

    sign_up(client, "not_a_mod_3")
    assert put("Nope").status_code == 403


def test_portuguese_page_shows_the_better_written_name_only_when_the_words_are_the_same():
    from app.services.common import better_title
    assert better_title({"title": "ASSASSINS CREED ODYSSEY", "title_en": "Assassin's Creed Odyssey"}) \
        == "Assassin's Creed Odyssey"
    assert better_title({"title": "The Last of Us Parte II", "title_en": "The Last of Us Part II"}) \
        == "The Last of Us Parte II"                                      # a translation: English page only
    assert better_title({"title": "Some Game", "title_en": ""}) == "Some Game"


def test_edition_names_in_english():
    from app.services.common import edition_en
    assert edition_en("Edição Especial Limitada") == "Special Limited Edition"
    assert edition_en("Edição Jogo do Ano") == "Game of the Year Edition"
    assert edition_en("Edição de Colecionador") == "Collector's Edition"
    assert edition_en("Versão Europeia") == "European Version"
    assert edition_en("Deluxe Edition") == "Deluxe Edition"


def test_possible_duplicates_merged_or_dismissed(mod):
    client, c = mod["client"], mod["db"]
    # the same game under another name (another store, another language), linked to the same IGDB entry
    process_products("press_start", [product("Sombra Quest - Deluxe Edition PS5", 4), product("Sombra Quest PS5", 5)],
                     full_catalog=False)
    shadow = c.execute("SELECT game_id FROM store_products WHERE url = 'https://match.test/1'").fetchone()[0]
    sombra = c.execute("SELECT game_id FROM store_products WHERE url = 'https://match.test/4'").fetchone()[0]
    c.execute("UPDATE games SET igdb_id = 777001 WHERE id IN (?, ?)", shadow, sombra)
    try:
        [pair] = [p for p in client.get("/api/mod/duplicates").get_json() if p["a"]["id"] in (shadow, sombra)]
        assert {pair["a"]["id"], pair["b"]["id"]} == {shadow, sombra} and pair["platform"] == "PlayStation 5"

        # "not the same": the pair leaves the list
        assert client.post("/api/mod/duplicates/dismiss", headers=HEADERS, json={"a": sombra, "b": shadow}).status_code == 200
        assert not [p for p in client.get("/api/mod/duplicates").get_json() if p["a"]["id"] in (shadow, sombra)]
        c.execute("DELETE FROM duplicate_dismissals")

        # merged: each product to the edition with the same key, pinned; the other game is gone
        merged = client.post("/api/mod/duplicates/merge", headers=HEADERS, json={"from_id": sombra, "into_id": shadow})
        assert merged.get_json() == {"game_id": shadow}
        _, by_name = editions(client)
        assert len(by_name["Deluxe Edition"]["products"]) == 2 and len(by_name["Standard"]["products"]) == 2
        assert c.execute("SELECT COUNT(*) FROM games WHERE id = ?", sombra).fetchone()[0] == 0
        assert c.execute("SELECT new_id FROM merged_ids WHERE kind = 'game' AND old_id = ?", sombra).fetchone()[0] == shadow
        assert client.get("/api/mod/log").get_json()[0]["action"] == "merge_game"
    finally:
        c.execute("DELETE FROM duplicate_dismissals")


def test_move_errors_and_access(mod):
    client = mod["client"]
    post = lambda data: client.post("/api/mod/matches", headers=HEADERS, json=data)
    assert post({"product_ids": [], "edition_id": 1}).get_json()["error"] == "products_invalid"
    assert post({"product_ids": [999999], "edition_id": 1}).status_code == 404
    _, by_name = editions(client)
    some = by_name["Standard"]["products"][0]["id"]
    assert post({"product_ids": [some], "edition_id": 999999}).status_code == 404
    assert post({"product_ids": [some], "game_id": 999999, "new_edition": "X"}).get_json()["error"] == "new_edition_invalid"
    assert client.delete("/api/mod/pins/999999", headers=HEADERS).status_code == 404

    sign_up(client, "not_a_mod")
    assert client.get("/api/mod/matches?q=shadow").status_code == 403
    assert post({"product_ids": [some], "edition_id": 1}).status_code == 403
