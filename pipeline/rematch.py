"""
Re-link every store product to its game and edition with the current matching rules,
refresh game titles / edition names, then delete games and editions nothing points
to anymore. No scraping involved.
Run it after changing core/normalizer.py or core/editions.py:

    python -m pipeline.rematch
"""
import logging
from collections import Counter, defaultdict

from core.editions import is_excluded, parse_title
from db import get_connection
from pipeline.matcher import GameMatcher
from scheduler.jobs import setup_logging

log = logging.getLogger(__name__)


def rematch_all():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        platform_ids = dict(cursor.execute("SELECT code, id FROM platforms").fetchall())
        codes = {v: k for k, v in platform_ids.items()}

        rows = cursor.execute(
            "SELECT id, external_name, platform_id, image_url, game_id, edition_id, is_active FROM store_products"
        ).fetchall()

        matcher = GameMatcher(cursor, platform_ids)
        changed = 0
        game_titles = defaultdict(Counter)      # {game_id: Counter of titles from its products}
        edition_names = defaultdict(Counter)

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
            game_id, edition_id = matcher.match(product)

            if game_id:
                parsed = parse_title(name, matcher.known_phrases)
                game_titles[game_id][parsed.game_title] += 1
                edition_names[edition_id][parsed.edition_name] += 1

            if (game_id, edition_id) != (old_game, old_edition):
                cursor.execute(
                    "UPDATE store_products SET game_id = ?, edition_id = ? WHERE id = ?",
                    game_id, edition_id, sp_id,
                )
                changed += 1

        renamed = refresh_names(cursor, "games", "title", 300, game_titles)
        renamed += refresh_names(cursor, "game_editions", "name", 200, edition_names)
        removed = delete_orphans(cursor)
        conn.commit()

        log.info("Rematched %d products, %d changed, %d names refreshed, removed %s",
                 len(rows), changed, renamed, removed)
        return changed, removed

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


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
    setup_logging()
    rematch_all()
