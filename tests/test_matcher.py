"""Game / edition matching and the duplicate clean-up, on a throwaway database."""
import pytest

from pipeline.matcher import GameMatcher, same_with_typos


@pytest.fixture
def cursor(test_db):
    c = test_db.conn.cursor()
    for table in ("merged_ids", "moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos", "user_listings", "user_favorites",
                  "users", "price_snapshots", "store_products", "game_editions", "games"):
        c.execute(f"DELETE FROM {table}")
    return c


def matcher(cursor):
    return GameMatcher(cursor, dict(cursor.execute("SELECT code, id FROM platforms").fetchall()))


def match(m, name, console="PS5"):
    return m.match({"external_name": name, "console": console})


def game_title(cursor, game_id):
    return cursor.execute("SELECT title FROM games WHERE id = ?", game_id).fetchone()[0]


def edition(cursor, edition_id):
    return cursor.execute("SELECT edition_key, name FROM game_editions WHERE id = ?", edition_id).fetchone()


def test_shortened_name_goes_to_the_fuller_known_game(cursor):
    full, _ = match(matcher(cursor), "Doom: The Dark Ages PS5")
    m = matcher(cursor)                                  # a later run knows "doom the dark ages"
    assert match(m, "DOOM DARK AGES PS5")[0] == full
    assert match(m, "God of War PS5")[0] != match(m, "God of War Ragnarök PS5")[0]
    assert game_title(cursor, full) == "Doom: The Dark Ages"   # not renamed after the short form


def test_title_cut_in_the_wrong_place_is_mended(cursor):
    game, _ = match(matcher(cursor), "Star Wars: Galactic Racer PS5")
    m = matcher(cursor)
    game_id, edition_id = match(m, "Star Wars - Galactic Racer Deluxe Edition PS5")
    assert game_id == game
    assert tuple(edition(cursor, edition_id)) == ("deluxe", "Deluxe Edition")


def test_edition_words_are_not_moved_into_the_title(cursor):
    match(matcher(cursor), "Dead Island Definitive PS5")      # a store that wrote the edition in the title
    m = matcher(cursor)
    game_id, edition_id = match(m, "Dead Island - Definitive Edition PS5")
    assert game_title(cursor, game_id) == "Dead Island"
    assert edition(cursor, edition_id)[0] == "definitive"


def test_edition_typos_within_a_game(cursor):
    m = matcher(cursor)
    _, deluxe = match(m, "Game X - Deluxe Edition PS5")
    assert match(m, "Game X - Delixe Edition PS5")[1] == deluxe
    assert match(m, "Game X - Steelbook Day One Edition PS5")[1] == match(m, "GAME X - DAY 1 STEELBOOK EDITION PS5")[1]
    assert match(m, "Game X - Gold Edition PS5")[1] != match(m, "Game X - Bold Edition PS5")[1]   # too short to tell


def test_same_with_typos():
    assert same_with_typos("enrolment", "enrollment")
    assert same_with_typos("steeelbook", "steelbook")
    assert not same_with_typos("deluxe", "deluxe")                 # identical isn't a typo
    assert not same_with_typos("collectors", "collectors limited")
    assert not same_with_typos("deluxe|Game Key Card", "delixe")   # tags must match
    assert not same_with_typos("zeno", "zero")


def test_rematch_merges_duplicates_and_records_redirects(cursor, app_on_test_db):
    from pipeline.rematch import rematch_all
    from app.services.game_service import merged_into

    store = cursor.execute("SELECT id FROM stores WHERE slug = 'press_start'").fetchone()[0]
    ps5 = cursor.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]

    def product(name, url):
        game_id, edition_id = match(matcher(cursor), name)
        cursor.execute(
            "INSERT INTO store_products (store_id, game_id, edition_id, platform_id, external_name, url) "
            "VALUES (?, ?, ?, ?, ?, ?)", store, game_id, edition_id, ps5, name, url)
        return game_id, edition_id

    # Created before the rules knew they're the same game (the short one first, so it got its own game)
    short_game, short_edition = product("DOOM DARK AGES PS5", "https://x/1")
    full_game, full_edition = product("Doom: The Dark Ages PS5", "https://x/2")
    cursor.execute("UPDATE games SET igdb_id = 77, summary = 'Fight.' WHERE id = ?", short_game)
    assert short_game != full_game
    # a user's favourite and listing on the copy that will be merged
    user = cursor.execute("INSERT INTO users (username, email, display_name) OUTPUT INSERTED.id "
                          "VALUES ('fan', 'fan@x.pt', 'Fan')").fetchone()[0]
    cursor.execute("INSERT INTO user_favorites (user_id, edition_id) VALUES (?, ?)", user, short_edition)
    cursor.execute("INSERT INTO user_listings (user_id, game_id, edition_id, price, condition) VALUES (?, ?, ?, 20, 'good')",
                   user, short_game, short_edition)

    rematch_all()

    assert cursor.execute("SELECT edition_id FROM user_favorites WHERE user_id = ?", user).fetchone()[0] == full_edition
    assert tuple(cursor.execute("SELECT game_id, edition_id FROM user_listings WHERE user_id = ?", user).fetchone())         == (full_game, full_edition)

    rows = cursor.execute("SELECT DISTINCT game_id FROM store_products").fetchall()
    assert [r[0] for r in rows] == [full_game]
    assert merged_into("game", [short_game]) == {short_game: full_game}
    assert merged_into("edition", [short_edition]) == {short_edition: full_edition}
    # the merged copy's IGDB information is kept
    assert cursor.execute("SELECT igdb_id FROM games WHERE id = ?", full_game).fetchone()[0] == 77


def test_old_links_and_favourites_follow_a_merge(cursor, web_client):
    client = web_client

    full_game, full_edition = match(matcher(cursor), "Doom: The Dark Ages PS5")
    cursor.execute("INSERT INTO merged_ids (kind, old_id, new_id) VALUES ('game', 999001, ?), ('edition', 999002, ?)",
                   full_game, full_edition)

    response = client.get("/game/999001")
    assert response.status_code == 301 and response.headers["Location"].endswith(f"/game/{full_game}")
    assert client.get(f"/game/{full_game}").status_code == 200

    # a favourite saved with the old edition id gets the edition now, marked as replacing it
    groups = client.get("/api/games/editions?ids=999002").get_json()
    assert [(g["edition_id"], g["merged_from"]) for g in groups] == [(full_edition, [999002])]
