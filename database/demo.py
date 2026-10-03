"""
Demo data: the collected games, prices and stores in one file, so someone else can try the
site without scraping the stores themselves.

    python -m database.demo export database/demo/demo.json.gz
    python -m database.demo export database/demo/demo.json.gz --without-texts
    python -m database.demo import database/demo/demo.json.gz

The file is NOT committed (database/demo/ is in .gitignore): it holds the stores' product
descriptions and IGDB summaries, which aren't ours to publish. Share it privately.
--without-texts leaves those texts out (names, prices, links and images stay).
User accounts and listings are never exported.
"""
import argparse
import gzip
import json
import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from db import connection

log = logging.getLogger(__name__)

# In foreign-key order (a table only points to tables before it)
TABLES = ("platforms", "stores", "games", "game_editions", "store_products", "price_snapshots",
          "scrape_runs", "merged_ids")
# Texts written by the stores / IGDB: left out with --without-texts
TEXT_COLUMNS = {"games": ("summary",), "store_products": ("description", "details")}


def encode(value):
    if isinstance(value, datetime):
        return {"dt": value.isoformat()}
    if isinstance(value, date):
        return {"d": value.isoformat()}
    if isinstance(value, Decimal):
        return {"n": str(value)}
    return value


def decode(value):
    if isinstance(value, dict):
        if "dt" in value:
            return datetime.fromisoformat(value["dt"])
        if "d" in value:
            return date.fromisoformat(value["d"])
        if "n" in value:
            return Decimal(value["n"])
    return value


def export_demo(path, without_texts=False):
    data = {"exported_at": datetime.utcnow().isoformat(), "tables": {}}
    with connection() as conn:
        cursor = conn.cursor()
        for table in TABLES:
            cursor.execute(f"SELECT * FROM {table}")
            columns = [c[0] for c in cursor.description]
            blank = {i for i, c in enumerate(columns) if without_texts and c in TEXT_COLUMNS.get(table, ())}
            rows = [[None if i in blank else encode(v) for i, v in enumerate(row)] for row in cursor.fetchall()]
            data["tables"][table] = {"columns": columns, "rows": rows}
            log.info("%s: %d rows", table, len(rows))

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    log.info("Demo data written to %s (%.1f MB)", path, path.stat().st_size / 1e6)


def import_demo(path, replace=False):
    """
    Load a demo file into this database (created with python -m database.setup). Refuses a
    database that already has games, unless replace=True (which deletes them first).
    """
    # A browser may have unpacked the file on download (Safari does): plain .json works too
    opener = gzip.open if Path(path).suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    with connection() as conn:
        cursor = conn.cursor()
        if cursor.execute("SELECT COUNT(*) FROM games").fetchone()[0] and not replace:
            log.info("The database already has games: demo data not loaded (use --replace to overwrite)")
            return False
        if cursor.execute("SELECT COUNT(*) FROM user_listings").fetchone()[0]:
            raise RuntimeError("This database has user listings; demo data would remove the games they point to")

        for table in reversed(TABLES):
            cursor.execute(f"DELETE FROM {table}")

        cursor.fast_executemany = True
        for table in TABLES:
            columns, rows = data["tables"][table]["columns"], data["tables"][table]["rows"]
            identity = cursor.execute(
                "SELECT COUNT(*) FROM sys.identity_columns WHERE object_id = OBJECT_ID(?)", table).fetchone()[0]
            if identity:
                cursor.execute(f"SET IDENTITY_INSERT {table} ON")
            if rows:
                cursor.executemany(
                    f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
                    [[decode(v) for v in row] for row in rows],
                )
            if identity:
                cursor.execute(f"SET IDENTITY_INSERT {table} OFF")
            log.info("%s: %d rows", table, len(rows))

    log.info("Demo data from %s loaded (exported %s)", path, data["exported_at"])
    return True


if __name__ == "__main__":
    from scheduler.jobs import setup_logging

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--without-texts", action="store_true", help="export: leave out store / IGDB texts")
    parser.add_argument("--replace", action="store_true", help="import: replace the games already there")
    args = parser.parse_args()
    setup_logging()
    if args.action == "export":
        export_demo(args.file, args.without_texts)
    else:
        import_demo(args.file, args.replace)
