"""
Re-link every store product to its game and edition with the current matching rules,
refresh game titles / edition names, then delete games and editions nothing points
to anymore. No scraping involved.
Run it after changing core/normalizer.py, core/editions.py or core/close_match.py:

    python -m pipeline.rematch --dry-run     # list what would be merged, change nothing
    python -m pipeline.rematch

A game or edition whose products all went to another one is recorded in merged_ids
(old links and favourites saved in browsers follow it), and its IGDB information is
kept when the game it went to has none.
"""
import argparse
import logging
from collections import Counter, defaultdict

from core.editions import edition_key_of, is_excluded
from db import get_connection
from pipeline.matcher import GameMatcher
from scheduler.jobs import setup_logging

log = logging.getLogger(__name__)

IGDB_COLUMNS = ["igdb_id", "igdb_checked_at", "summary", "genres", "publishers", "developers", "first_release_date",
                "rating", "pegi", "cover_image_id", "screenshot_ids", "video_ids"]


def rematch_all(dry_run=False):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        platform_ids = dict(cursor.execute("SELECT code, id FROM platforms").fetchall())
        codes = {v: k for k, v in platform_ids.items()}

        rows = cursor.execute(
            "SELECT id, external_name, platform_id, image_url, game_id, edition_id, is_active FROM store_products"
        ).fetchall()

        rekeyed = rekey_editions(cursor)
        matcher = GameMatcher(cursor, platform_ids)
        changed = 0
        game_titles = defaultdict(Counter)      # {game_id: Counter of titles from its products}
        edition_names = defaultdict(Counter)
        moves = {"game": defaultdict(Counter), "edition": defaultdict(Counter)}   # {old id: Counter(new ids)}

        for sp_id, name, platform_id, image, old_game, old_edition, is_active in rows:
            if is_excluded(name):
                if (old_game, old_edition, is_active) == (None, None, False):
                    continue
                cursor.execute(
                    "UPDATE store_products SET game_id = NULL, edition_id = NULL, is_active = 0 WHERE id = ?",
                    sp_id,
                )
                changed += 1
                continue

            product = {"external_name": name, "console": codes.get(platform_id), "image": image}
            game_id, edition_id, title, edition_name = matcher.match_details(product)

            if game_id:
                if title:
                    game_titles[game_id][title] += 1
                edition_names[edition_id][edition_name] += 1

            if (game_id, edition_id) != (old_game, old_edition):
                cursor.execute(
                    "UPDATE store_products SET game_id = ?, edition_id = ? WHERE id = ?",
                    game_id, edition_id, sp_id,
                )
                changed += 1
                if old_game and game_id and old_game != game_id:
                    moves["game"][old_game][game_id] += 1
                if old_edition and edition_id and old_edition != edition_id:
                    moves["edition"][old_edition][edition_id] += 1

        renamed = refresh_names(cursor, "games", "title", 300, game_titles)
        renamed += refresh_names(cursor, "game_editions", "name", 200, edition_names)
        merged = record_merges(cursor, moves)
        if dry_run:
            report(cursor, merged)      # before the merged rows are deleted: it shows their names
        removed = delete_orphans(cursor)

        log.info("Rematched %d products, %d changed, %d edition keys updated in place, %d names refreshed, "
                 "merged %s, removed %s", len(rows), changed, rekeyed, renamed,
                 {k: len(v) for k, v in merged.items()}, removed)
        if dry_run:
            conn.rollback()
            log.info("Dry run: nothing was changed")
        else:
            conn.commit()
        return changed, merged, removed

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def rekey_editions(cursor):
    """
    Bring stored edition keys to the current key rules in place ("limited collectors" →
    "collectors limited", "game of the year" → "goty"), so an edition keeps its id when only
    its key's spelling changed. Where the new key is already taken in that game, the
    rematch merges the two (and records it).
    """
    rows = cursor.execute("SELECT id, game_id, edition_key FROM game_editions").fetchall()
    taken = {(game_id, key) for _, game_id, key in rows}
    updated = 0
    for edition_id, game_id, key in rows:
        words, *tags = key.split("|")
        new = "|".join([edition_key_of(words)] + tags)
        if new != key and (game_id, new) not in taken:
            cursor.execute("UPDATE game_editions SET edition_key = ? WHERE id = ?", new, edition_id)
            taken.discard((game_id, key))
            taken.add((game_id, new))
            updated += 1
    return updated


def record_merges(cursor, moves):
    """
    {kind: {old_id: new_id}} for games / editions left with no product, whose products went
    to another one. Saved in merged_ids (older redirects to them follow along); a merged game's
    IGDB information goes to the game that replaced it if that one has none.
    """
    merged = {}
    for kind, table in (("game", "games"), ("edition", "game_editions")):
        orphans = {r[0] for r in cursor.execute(f"""
            SELECT t.id FROM {table} t
            WHERE NOT EXISTS (SELECT 1 FROM store_products sp WHERE sp.{kind}_id = t.id)
              AND NOT EXISTS (SELECT 1 FROM user_listings ul WHERE ul.{kind}_id = t.id)""").fetchall()}
        merged[kind] = {old: targets.most_common(1)[0][0] for old, targets in moves[kind].items() if old in orphans}

        for old, new in merged[kind].items():
            cursor.execute("UPDATE merged_ids SET new_id = ? WHERE kind = ? AND new_id = ?", new, kind, old)
            cursor.execute("DELETE FROM merged_ids WHERE kind = ? AND old_id = ?", kind, old)
            cursor.execute("INSERT INTO merged_ids (kind, old_id, new_id) VALUES (?, ?, ?)", kind, old, new)

    columns = ", ".join(f"{c} = old.{c}" for c in IGDB_COLUMNS)
    for old, new in merged["game"].items():
        cursor.execute(f"""
            UPDATE g SET {columns}
            FROM games g JOIN games old ON old.id = ?
            WHERE g.id = ? AND g.igdb_id IS NULL AND old.igdb_id IS NOT NULL""", old, new)
    return merged


def report(cursor, merged):
    """Print the merges of a dry run, for a person to check."""
    titles = dict(cursor.execute("SELECT id, title FROM games").fetchall())
    for old, new in sorted(merged["game"].items(), key=lambda m: titles.get(m[1], "")):
        old_title = cursor.execute("SELECT title FROM games WHERE id = ?", old).fetchone()
        print(f"GAME     {old_title[0] if old_title else old!s:55} → {titles.get(new)}")
    names = {r[0]: (r[1], r[2]) for r in cursor.execute(
        "SELECT e.id, g.title, e.name FROM game_editions e JOIN games g ON g.id = e.game_id").fetchall()}
    old_names = {}
    for old in merged["edition"]:
        row = cursor.execute("SELECT name FROM game_editions WHERE id = ?", old).fetchone()
        old_names[old] = row[0] if row else old
    for old, new in sorted(merged["edition"].items(), key=lambda m: names.get(m[1], ("", ""))):
        game, name = names.get(new, ("?", "?"))
        print(f"EDITION  {game[:40]:40} {old_names[old]!s:35} → {name}")


def refresh_names(cursor, table, column, max_len, candidates):
    """
    Set each row's display name to the most common one among its products,
    preferring mixed case ("Silent Hill: Townfall" over "SILENT HILL TOWNFALL").
    """
    current = dict(cursor.execute(f"SELECT id, {column} FROM {table}").fetchall())
    renamed = 0

    for row_id, names in candidates.items():
        best = max(names, key=lambda n: (not n.isupper(), names[n], n))[:max_len]
        if current.get(row_id) != best:
            cursor.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", best, row_id)
            renamed += 1

    return renamed


def delete_orphans(cursor):
    """Editions and games that no store product or user listing uses."""
    cursor.execute("""
        DELETE e FROM game_editions e
        WHERE NOT EXISTS (SELECT 1 FROM store_products sp WHERE sp.edition_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM user_listings ul WHERE ul.edition_id = e.id)
    """)
    editions = cursor.rowcount

    cursor.execute("""
        DELETE g FROM games g
        WHERE NOT EXISTS (SELECT 1 FROM store_products sp WHERE sp.game_id = g.id)
          AND NOT EXISTS (SELECT 1 FROM user_listings ul WHERE ul.game_id = g.id)
          AND NOT EXISTS (SELECT 1 FROM game_editions e WHERE e.game_id = g.id)
    """)

    return {"editions": editions, "games": cursor.rowcount}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list the merges, change nothing")
    args = parser.parse_args()
    setup_logging()
    rematch_all(dry_run=args.dry_run)
