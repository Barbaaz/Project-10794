"""
Favourite editions, per account. (Before accounts they lived in the browser: import_ids()
moves those into the account at the first log-in, following merged editions.)
"""
from app.services.game_service import merged_into
from db import connection, fetch_all, placeholders

MAX_FAVORITES = 200     # the favourites tab asks for all of them at once


class FavoriteError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def list_ids(user_id):
    """The user's favourite edition ids, oldest first (the order they were starred)."""
    return [r["edition_id"] for r in fetch_all(
        "SELECT edition_id FROM user_favorites WHERE user_id = ? ORDER BY created_at, edition_id", user_id)]


def add(user_id, edition_id):
    return import_ids(user_id, [edition_id], strict=True)


def remove(user_id, edition_id):
    with connection() as conn:
        conn.cursor().execute("DELETE FROM user_favorites WHERE user_id = ? AND edition_id = ?", user_id, edition_id)
    return list_ids(user_id)


def import_ids(user_id, edition_ids, strict=False):
    """
    Add these editions to the user's favourites (already there: kept once). Ids of editions
    merged into another become that one; unknown ids are skipped (strict: an error).
    """
    try:
        ids = list(dict.fromkeys(int(i) for i in edition_ids))
    except (TypeError, ValueError):
        raise FavoriteError("edition_invalid")
    merged = merged_into("edition", ids)
    ids = list(dict.fromkeys(merged.get(i, i) for i in ids))
    known = {r["id"] for r in fetch_all(f"SELECT id FROM game_editions WHERE id IN ({placeholders(ids)})", *ids)} if ids else set()
    if strict and len(known) < len(ids):
        raise FavoriteError("not_found", 404)

    current = set(list_ids(user_id))
    new = [i for i in ids if i in known and i not in current]
    if len(current) + len(new) > MAX_FAVORITES:
        raise FavoriteError("favorites_full")
    with connection() as conn:
        for edition_id in new:
            conn.cursor().execute("INSERT INTO user_favorites (user_id, edition_id) VALUES (?, ?)", user_id, edition_id)
    return list_ids(user_id)
