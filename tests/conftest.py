import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture_json():
    return lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def test_db():
    """
    A throwaway database with the real schema, indexes and views; dropped at the end.
    Yields .conn (autocommit connection) and .url (its connection string).
    Tests using it are skipped when SQL Server isn't reachable.
    """
    pyodbc = pytest.importorskip("pyodbc")
    from app.config import DB_CONNECTION_STRING
    from database.setup import connect_master, setup, with_database

    name = f"Project10794_Test_{uuid.uuid4().hex[:8]}"
    url = with_database(DB_CONNECTION_STRING, name)
    try:
        admin = connect_master(DB_CONNECTION_STRING)
    except pyodbc.Error as e:
        pytest.skip(f"SQL Server not available: {e}")

    setup(url)     # creates the database and runs the real scripts, like on a new machine
    conn = pyodbc.connect(url, autocommit=True)
    try:
        yield SimpleNamespace(conn=conn, url=url)
    finally:
        conn.close()
        admin.cursor().execute(f"ALTER DATABASE {name} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {name}")
        admin.close()


@pytest.fixture
def app_on_test_db(test_db, monkeypatch):
    """Point the app's own queries (db.get_connection) at the throwaway database."""
    import db
    monkeypatch.setattr(db, "DB_CONNECTION_STRING", test_db.url)
    return test_db


@pytest.fixture
def web_client(app_on_test_db):
    """The web app (app/web.py) on the throwaway database, for requests in tests."""
    from app.web import app
    return app.test_client()


MARKET_TABLES = ("moderation_log", "reports", "user_ratings", "messages", "conversations", "listing_photos", "user_listings", "user_favorites", "users")


@pytest.fixture
def market(web_client, test_db, tmp_path, monkeypatch):
    """
    For marketplace tests: a game with an edition (and another game's edition), no users or
    listings yet, uploaded photos stored in tmp_path.
    """
    from app.services import auth_service, photo_storage

    monkeypatch.setattr(photo_storage.storage, "root", tmp_path)
    c = test_db.conn.cursor()
    for table in MARKET_TABLES:
        c.execute(f"DELETE FROM {table}")
    auth_service._failures.clear()
    ps5 = c.execute("SELECT id FROM platforms WHERE code = 'PS5'").fetchone()[0]

    def game(title):
        game_id = c.execute("INSERT INTO games (platform_id, title, normalized_title) OUTPUT INSERTED.id "
                            "VALUES (?, ?, ?)", ps5, title, title.lower()).fetchone()[0]
        edition_id = c.execute("INSERT INTO game_editions (game_id, edition_key, name) OUTPUT INSERTED.id "
                               "VALUES (?, '', 'Standard')", game_id).fetchone()[0]
        return game_id, edition_id

    game_id, edition_id = game("Market Test Game")
    other_game, other_edition = game("Other Game")
    yield {"client": web_client, "game": game_id, "edition": edition_id, "other_edition": other_edition,
           "dir": tmp_path, "db": c}
    for table in MARKET_TABLES:
        c.execute(f"DELETE FROM {table}")
    c.execute("DELETE FROM game_editions WHERE game_id IN (?, ?)", game_id, other_game)
    c.execute("DELETE FROM games WHERE id IN (?, ?)", game_id, other_game)

