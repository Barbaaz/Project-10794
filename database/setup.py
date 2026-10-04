"""
Create the database if it doesn't exist and bring it up to date: the price side's tables,
indexes, views, platforms and stores (database/*.sql), then the marketplace's tables (Alembic
migrations, migrations/). Safe to re-run: every step only adds what's missing.
Uses DB_CONNECTION_STRING (app/config.py) — its database (dbname) is the one created; the login
needs the CREATEDB right for that.

    python -m database.setup
    python -m database.setup --demo database/demo/demo.json.gz   # and load demo data (see database/demo.py)
"""
import argparse
import time
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.config import DB_CONNECTION_STRING

DATABASE_DIR = Path(__file__).resolve().parent
ROOT = DATABASE_DIR.parent
SCRIPTS = ("schema.sql", "indexes.sql", "views.sql", "seed_stores.sql")

# Sorting and comparing text the Portuguese way, the same on Windows and Linux (ICU)
CREATE_DATABASE = "CREATE DATABASE {} TEMPLATE template0 ENCODING 'UTF8' LOCALE_PROVIDER icu ICU_LOCALE 'pt-PT' LOCALE 'C'"


def database_name(connection_string):
    return conninfo_to_dict(connection_string)["dbname"]


def with_database(connection_string, name):
    return make_conninfo(connection_string, dbname=name)


def run_sql_script(conn, path):
    """Run a .sql file from database/ (a whole script at once: no parameters in it)."""
    conn.execute((DATABASE_DIR / path).read_text(encoding="utf-8"))


def connect_server(connection_string, wait_seconds=0):
    """A connection to the server's postgres database; waits for a server that is still starting."""
    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            return psycopg.connect(with_database(connection_string, "postgres"), autocommit=True, connect_timeout=5)
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(3)


def setup(connection_string=DB_CONNECTION_STRING, wait_seconds=0):
    name = database_name(connection_string)
    with connect_server(connection_string, wait_seconds) as server:
        if not server.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            server.execute(sql.SQL(CREATE_DATABASE).format(sql.Identifier(name)))
            print(f"Database {name} created")

    with psycopg.connect(connection_string, autocommit=True) as conn:
        for script in SCRIPTS:
            run_sql_script(conn, script)
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
        if import_demo(args.demo):
            # platforms / stores added since the demo file was exported
            with psycopg.connect(DB_CONNECTION_STRING, autocommit=True) as conn:
                run_sql_script(conn, "seed_stores.sql")
