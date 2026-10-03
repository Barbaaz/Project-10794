"""
Move a database from SQL Server (the project's database until 2026-10-03) to PostgreSQL: every
table, with its ids, then a row-by-row comparison of the two. One-time; needs pyodbc and the ODBC
driver (pip install pyodbc), which the project no longer uses otherwise.

    python -m database.from_sqlserver
    python -m database.from_sqlserver --source "DRIVER={ODBC Driver 17 for SQL Server};SERVER=...;DATABASE=...;Trusted_Connection=yes;"

The PostgreSQL database is DB_CONNECTION_STRING's (app/config.py); it's created / brought up to
date first (database/setup.py) and must have no games yet, unless --replace (which empties it).
"""
import argparse
import logging

import psycopg

from app.config import DB_CONNECTION_STRING
from database.demo import insert_rows
from database.setup import run_sql_script, setup
from db import connect

log = logging.getLogger(__name__)

SQL_SERVER = ("DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\\SQLEXPRESS;"
              "DATABASE=Project10794;Trusted_Connection=yes;")

# In foreign-key order (a table only points to tables before it)
TABLES = ("platforms", "stores", "games", "game_editions", "store_products", "price_snapshots", "scrape_runs",
          "merged_ids", "users", "user_listings", "listing_photos", "conversations", "messages", "user_ratings",
          "reports", "moderation_log", "match_overrides", "collection_items", "game_reviews", "duplicate_dismissals")


def columns_of(cursor, table):
    cursor.execute(f"SELECT * FROM {table} WHERE 1 = 0")
    return [c[0] for c in cursor.description]


def copy_database(source, replace=False):
    import pyodbc

    setup()
    old = pyodbc.connect(source)
    with connect(DB_CONNECTION_STRING) as new:
        cursor = new.cursor()
        if cursor.execute("SELECT COUNT(*) FROM games").fetchone()[0] and not replace:
            raise SystemExit("The PostgreSQL database already has games (use --replace to empty it first)")
        cursor.execute(f"TRUNCATE {', '.join(TABLES)}")

        for table in TABLES:
            source_columns = columns_of(old.cursor(), table)
            columns = [c for c in columns_of(cursor, table) if c in source_columns]
            if left_out := set(source_columns) - set(columns):
                log.warning("%s: columns not in PostgreSQL, left out: %s", table, ", ".join(sorted(left_out)))
            rows = old.cursor().execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()
            insert_rows(cursor, table, columns, [tuple(r) for r in rows])
            if "id" in columns:
                # the next id goes on from SQL Server's counter, not from the highest id: an id that
                # was used and deleted isn't given again (it may still be in a link or merged_ids)
                last = old.cursor().execute("SELECT IDENT_CURRENT(?)", table).fetchone()[0]
                cursor.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), GREATEST(?, COALESCE(MAX(id), 0)) + 1, "
                               f"false) FROM {table}", table, int(last or 0))
            log.info("%s: %d rows", table, len(rows))

    differences = compare(old, TABLES)
    old.close()
    # platforms / stores added to seed_stores.sql since (e.g. "Xbox (original)", which SQL Server's
    # script used to delete again)
    with psycopg.connect(DB_CONNECTION_STRING, autocommit=True) as new:
        run_sql_script(new, "seed_stores.sql")
    return differences


def compare(old, tables):
    """Every table's rows in both databases, value by value: the tables that differ."""
    differences = []
    with connect(DB_CONNECTION_STRING) as new:
        for table in tables:
            columns = [c for c in columns_of(new.cursor(), table) if c in columns_of(old.cursor(), table)]
            select = f"SELECT {', '.join(columns)} FROM {table}"
            before = sorted((tuple(r) for r in old.cursor().execute(select).fetchall()), key=str)
            after = sorted((tuple(r) for r in new.cursor().execute(select).fetchall()), key=str)
            if before != after:
                differences.append(table)
                log.error("%s: %d rows in SQL Server, %d in PostgreSQL, %d differ", table, len(before), len(after),
                          len(set(before) ^ set(after)))
    log.info("Compared %d tables: %s", len(tables), "all the same" if not differences else f"{len(differences)} differ")
    return differences


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=SQL_SERVER, help="the SQL Server database's ODBC connection string")
    parser.add_argument("--replace", action="store_true", help="empty the PostgreSQL database first")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(1 if copy_database(args.source, args.replace) else 0)
