"""
Create the database if it doesn't exist and bring it up to date: the price side's tables,
indexes, views, platforms and stores (database/*.sql), then the marketplace's tables (Alembic
migrations, migrations/). Safe to re-run: every step only adds what's missing.
Uses DB_CONNECTION_STRING (app/config.py) — its DATABASE= is the one created.

    python -m database.setup
    python -m database.setup --demo database/demo/demo.json.gz   # and load demo data (see database/demo.py)
"""
import argparse
import re
import time
from pathlib import Path

import pyodbc

from app.config import DB_CONNECTION_STRING

DATABASE_DIR = Path(__file__).resolve().parent
ROOT = DATABASE_DIR.parent
SCRIPTS = ("schema.sql", "indexes.sql", "views.sql", "seed_stores.sql")


def database_name(connection_string):
    return re.search(r"DATABASE=([^;]*)", connection_string, re.IGNORECASE).group(1)


def with_database(connection_string, name):
    return re.sub(r"DATABASE=[^;]*", f"DATABASE={name}", connection_string, flags=re.IGNORECASE)


def run_sql_script(cursor, path, database):
    """Run a .sql file from database/ against `database` (scripts are split on GO lines)."""
    sql = (DATABASE_DIR / path).read_text(encoding="utf-8").replace("USE Project10794;", f"USE {database};")
    for batch in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE):
        if batch.strip():
            cursor.execute(batch)


def connect_master(connection_string, wait_seconds=0):
    """A connection to the server's master database; waits for a server that is still starting."""
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return pyodbc.connect(with_database(connection_string, "master"), autocommit=True, timeout=5)
        except pyodbc.Error:
            if time.monotonic() > deadline:
                raise
            time.sleep(3)


def setup(connection_string=DB_CONNECTION_STRING, wait_seconds=0):
    name = database_name(connection_string)
    master = connect_master(connection_string, wait_seconds)
    try:
        if not master.cursor().execute("SELECT 1 FROM sys.databases WHERE name = ?", name).fetchone():
            master.cursor().execute(f"CREATE DATABASE [{name}]")
            print(f"Database {name} created")
    finally:
        master.close()

    conn = pyodbc.connect(connection_string, autocommit=True)
    try:
        for script in SCRIPTS:
            run_sql_script(conn.cursor(), script, name)
    finally:
        conn.close()
    migrate(connection_string)
    print(f"Database {name} is up to date")


def migrate(connection_string):
    """The marketplace's tables: Alembic's migrations (migrations/versions) up to the latest."""
    from alembic import command
    from alembic.config import Config

    from db import make_engine

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    engine = make_engine(connection_string)
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", type=Path, help="load this demo data file when the database is empty")
    parser.add_argument("--wait", type=int, default=0, help="seconds to wait for the server to start")
    args = parser.parse_args()
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    setup(wait_seconds=args.wait)
    if args.demo:
        from database.demo import import_demo
        import_demo(args.demo)
