"""
Demo data: the collected games, prices and stores in one file, so someone else can try the
site without scraping the stores themselves.

    python -m database.demo export database/demo/demo.json.gz
    python -m database.demo export database/demo/demo.json.gz --without-texts
    python -m database.demo import database/demo/demo.json.gz

The file is NOT committed (database/demo/ is in .gitignore): it holds the stores' product
descriptions and IGDB summaries, which aren't ours to publish. Share it privately.
--without-texts leaves those texts out (names, prices, links and images stay).
User accounts and listings are never exported, except --profile NAME: that user's public side (name,
location, gaming accounts, showcase, collection, picture) so testers see a full profile (user,
2026-10-13). Never their e-mail, password or Steam / PSN ids: loaded, it's an account nobody can log in to.
"""
import argparse
import base64
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
# --profile: what of the user is copied (what their public profile shows)
PROFILE_COLUMNS = ("username", "display_name", "location", "accounts_json", "collection_public", "profile_sections",
                   "lang", "created_at")
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


def export_demo(path, without_texts=False, profiles=()):
    data = {"exported_at": datetime.utcnow().isoformat(), "tables": {}, "profiles": []}
    with connection() as conn:
        cursor = conn.cursor()
        for name in profiles:
            data["profiles"].append(export_profile(cursor, name))
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


def export_profile(cursor, name):
    """A user's public side: PROFILE_COLUMNS, their collection (the same games' ids: the file's catalogue)
    and their picture's bytes."""
    from app.services.photo_storage import storage
    row = cursor.execute(f"SELECT id, avatar_key, {', '.join(PROFILE_COLUMNS)} FROM users "
                         "WHERE lower(username) = lower(?) AND is_active", name).fetchone()
    if row is None:
        raise SystemExit(f"No active user {name!r}")
    user_id, avatar_key, *values = row
    cursor.execute("SELECT * FROM collection_items WHERE user_id = ? ORDER BY id", user_id)
    columns = [c[0] for c in cursor.description]
    keep = [i for i, c in enumerate(columns) if c not in ("id", "user_id")]
    items = {"columns": [columns[i] for i in keep],
             "rows": [[encode(r[i]) for i in keep] for r in cursor.fetchall()]}
    avatar = storage.root / avatar_key if avatar_key else None
    log.info("Profile %s: %d collection items%s", name, len(items["rows"]), ", picture" if avatar else "")
    return {"user": dict(zip(PROFILE_COLUMNS, map(encode, values))), "items": items,
            "avatar": base64.b64encode(avatar.read_bytes()).decode() if avatar and avatar.exists() else None}


def import_profile(cursor, profile):
    """The profile as an account with no password and a made-up e-mail (nobody logs in to it), no alerts."""
    from app.services.photo_storage import storage
    user = {k: decode(v) for k, v in profile["user"].items()}
    if cursor.execute("SELECT 1 FROM users WHERE lower(username) = lower(?)", user["username"]).fetchone():
        log.info("Profile %s: already there", user["username"])
        return
    columns = [*user, "email", "wish_alerts"]
    user_id = cursor.execute(f"INSERT INTO users ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))}) RETURNING id",
                             *user.values(), f"{user['username'].lower()}@profile.invalid", False).fetchone()[0]
    items = profile["items"]
    insert_rows(cursor, "collection_items", ["user_id", *items["columns"]],
                [[user_id, *map(decode, row)] for row in items["rows"]])
    if profile["avatar"]:
        key = storage.save(f"avatars/{user_id}", base64.b64decode(profile["avatar"]))
        cursor.execute("UPDATE users SET avatar_key = ? WHERE id = ?", key, user_id)
    log.info("Profile %s: %d collection items", user["username"], len(items["rows"]))


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

        for table in TABLES:
            columns, rows = data["tables"][table]["columns"], data["tables"][table]["rows"]
            insert_rows(cursor, table, columns, [[decode(v) for v in row] for row in rows])
            log.info("%s: %d rows", table, len(rows))
        for profile in data.get("profiles", []):
            import_profile(cursor, profile)

    log.info("Demo data from %s loaded (exported %s)", path, data["exported_at"])
    return True


def insert_rows(cursor, table, columns, rows):
    """Insert rows with their own ids, then make the table's next new id follow the highest one."""
    if rows:
        with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
    if "id" in columns:
        sequence = cursor.execute("SELECT pg_get_serial_sequence(?, 'id')", table).fetchone()[0]
        cursor.execute(f"SELECT setval(?, COALESCE(MAX(id), 0) + 1, false) FROM {table}", sequence)


if __name__ == "__main__":
    from scheduler.jobs import setup_logging

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--without-texts", action="store_true", help="export: leave out store / IGDB texts")
    parser.add_argument("--replace", action="store_true", help="import: replace the games already there")
    parser.add_argument("--profile", action="append", default=[], metavar="USERNAME",
                        help="export: also this user's public profile and collection (no e-mail / password)")
    args = parser.parse_args()
    setup_logging()
    if args.action == "export":
        export_demo(args.file, args.without_texts, args.profile)
    else:
        import_demo(args.file, args.replace)
