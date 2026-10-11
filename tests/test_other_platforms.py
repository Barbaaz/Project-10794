"""The game page's "Também para …": the same game (same IGDB entry) on our other platforms; on a throwaway database."""


def test_the_same_igdb_game_on_other_platforms(market):
    client, c = market["client"], market["db"]
    xbox = c.execute("SELECT id FROM platforms WHERE code = 'XboxSeries'").fetchone()[0]
    pc = c.execute("SELECT id FROM platforms WHERE code = 'PC'").fetchone()[0]
    c.execute("UPDATE games SET igdb_id = 4242 WHERE id = ?", market["game"])
    other = c.execute("INSERT INTO games (platform_id, title, normalized_title, igdb_id) VALUES (?, 'Market Test Game', "
                      "'market test game', 4242) RETURNING id", xbox).fetchone()[0]
    product = c.execute("INSERT INTO store_products (store_id, game_id, platform_id, url, external_name) "
                        "SELECT id, ?, ?, 'https://example.test/xbox', 'Market Test Game' FROM stores ORDER BY id LIMIT 1 "
                        "RETURNING id", other, xbox).fetchone()[0]
    # only in someone's collection (a Steam import): no store or seller has it
    collected = c.execute("INSERT INTO games (platform_id, title, normalized_title, igdb_id) VALUES (?, 'Market Test Game', "
                          "'market test game', 4242) RETURNING id", pc).fetchone()[0]
    try:
        page = client.get(f"/api/games/{market['game']}").get_json()
        assert [(o["game_id"], o["platform"], o["best_price"]) for o in page["other_platforms"]] == [(other, "XboxSeries", None)]
        # a game without an IGDB entry has none
        assert client.get(f"/api/games/{market['other_game']}").get_json()["other_platforms"] == []
    finally:
        c.execute("DELETE FROM store_products WHERE id = ?", product)
        c.execute("DELETE FROM games WHERE id IN (?, ?)", other, collected)
