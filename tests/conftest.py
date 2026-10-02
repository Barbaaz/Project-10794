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
