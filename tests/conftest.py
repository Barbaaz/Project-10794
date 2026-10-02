import json
import re
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


def run_sql_script(cursor, path, database):
    """Run a .sql file from database/ against `database` (scripts are split on GO lines)."""
    sql = (ROOT / "database" / path).read_text(encoding="utf-8").replace("USE Project10794;", f"USE {database};")
    for batch in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE):
        if batch.strip():
            cursor.execute(batch)


@pytest.fixture(scope="session")
def test_db():
    """
    A throwaway database with the real schema, indexes and views; dropped at the end.
    Yields .conn (autocommit connection) and .url (its connection string).
    Tests using it are skipped when SQL Server isn't reachable.
    """
    pyodbc = pytest.importorskip("pyodbc")
    from app.config import DB_CONNECTION_STRING

    master = re.sub(r"DATABASE=[^;]*;", "DATABASE=master;", DB_CONNECTION_STRING)
    name = f"Project10794_Test_{uuid.uuid4().hex[:8]}"

    try:
        admin = pyodbc.connect(master, autocommit=True, timeout=5)
    except pyodbc.Error as e:
        pytest.skip(f"SQL Server not available: {e}")

    admin.cursor().execute(f"CREATE DATABASE {name}")
    url = re.sub(r"DATABASE=[^;]*;", f"DATABASE={name};", DB_CONNECTION_STRING)
    conn = pyodbc.connect(url, autocommit=True)
    try:
        for script in ("schema.sql", "indexes.sql", "views.sql", "seed_stores.sql"):
            run_sql_script(conn.cursor(), script, name)
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
