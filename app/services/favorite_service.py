"""
Favourite editions, per account. (Before accounts they lived in the browser: import_ids()
moves those into the account at the first log-in, following merged editions.)
"""
from sqlalchemy import select

from app.models import Favorite, GameEdition
from app.services.game_service import merged_into
from db import session

MAX_FAVORITES = 200     # the favourites tab asks for all of them at once


class FavoriteError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def list_ids(user_id):
    """The user's favourite edition ids, oldest first (the order they were starred)."""
    with session() as s:
        return list(s.scalars(select(Favorite.edition_id).where(Favorite.user_id == user_id)
                              .order_by(Favorite.created_at, Favorite.edition_id)))


def add(user_id, edition_id):
    return import_ids(user_id, [edition_id], strict=True)


def remove(user_id, edition_id):
    with session() as s:
        favorite = s.get(Favorite, (user_id, edition_id))
        if favorite:
            s.delete(favorite)
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

    with session() as s:
        known = set(s.scalars(select(GameEdition.id).where(GameEdition.id.in_(ids)))) if ids else set()
        if strict and len(known) < len(ids):
            raise FavoriteError("not_found", 404)
        current = set(s.scalars(select(Favorite.edition_id).where(Favorite.user_id == user_id)))
        new = [i for i in ids if i in known and i not in current]
        if len(current) + len(new) > MAX_FAVORITES:
            raise FavoriteError("favorites_full")
        s.add_all(Favorite(user_id=user_id, edition_id=i) for i in new)
    return list_ids(user_id)
