"""
The DLC a user owns for a game in their collection (user, 2026-10-13). IGDB lists each game's DLC,
expansions and standalone expansions; the list is kept in igdb_addons for KEEP_DAYS (the daily run
fills it for the games in collections, the edit window for one it hasn't). A remaster or another
version IGDB lists without add-ons takes its original's (Horizon Zero Dawn Remastered: The Frozen Wilds).
Steam and PSN don't say which DLC someone owns: the user ticks them.
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import CollectionItem, Game, IgdbAddons
from app.services.collection_service import CollectionError, _own
from app.services.igdb_game_service import query
from db import session

KEEP_DAYS = 30
BATCH = 500
KINDS = {"dlcs": "dlc", "expansions": "expansion", "standalone_expansions": "standalone"}
ADDON_FIELDS = "name,cover.image_id,first_release_date"
FIELDS = ("name,game_type,parent_game,version_parent,"
          + ",".join(f"{kind}.{field}" for kind in KINDS for field in ADDON_FIELDS.split(",")))
COVER_URL = "https://images.igdb.com/igdb/image/upload/t_cover_small/{}.jpg"


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _short(name, game_name):
    """An add-on's name without its game's in front ("The Witcher 3: Wild Hunt - Blood and Wine" → "Blood and Wine")."""
    if game_name and name.lower().startswith(game_name.lower()):
        rest = name[len(game_name):].lstrip(" -–—:")
        if rest:
            return rest
    return name


def _addons_of(game):
    """[{igdb_id, name, type, cover, year}] from an IGDB game, in release order (undated last)."""
    found, released = {}, {}
    for kind, label in KINDS.items():
        for a in game.get(kind, []):
            when = a.get("first_release_date")
            released[a["id"]] = when
            found.setdefault(a["id"], {"igdb_id": a["id"], "name": _short(a["name"], game.get("name")), "type": label,
                                       "cover": (a.get("cover") or {}).get("image_id"),
                                       "year": datetime.fromtimestamp(when, timezone.utc).year if when else None})
    return sorted(found.values(), key=lambda a: (released[a["igdb_id"]] is None, released[a["igdb_id"]] or 0,
                                                 a["name"].lower(), a["igdb_id"]))


def _ask(igdb_ids):
    """{igdb_id: IGDB game} for these ids, BATCH at a time."""
    ids, games = sorted(set(igdb_ids)), {}
    for i in range(0, len(ids), BATCH):
        part = ids[i:i + BATCH]
        for g in query(f"fields {FIELDS}; where id = ({','.join(map(str, part))}); limit {len(part)};"):
            games[g["id"]] = g
    return games


def refresh(igdb_ids):
    """Fetch and keep the add-on lists of these IGDB games; an empty one borrows its original's."""
    games = _ask(igdb_ids)
    lists = {gid: _addons_of(g) for gid, g in games.items()}
    originals = {gid: g.get("version_parent") or g.get("parent_game") for gid, g in games.items()
                 if not lists[gid] and (g.get("version_parent") or g.get("parent_game"))}
    if originals:
        parents = _ask(originals.values())
        for gid, parent in originals.items():
            if parent in parents:
                lists[gid] = _addons_of(parents[parent])
    now = _now()
    with session() as s:
        for gid in igdb_ids:
            if gid not in lists:
                continue               # IGDB didn't answer for it: asked again next time
            row = s.get(IgdbAddons, gid) or IgdbAddons(igdb_id=gid)
            row.addons, row.fetched_at = json.dumps(lists[gid], ensure_ascii=False), now
            s.add(row)
    return lists


def kept(igdb_ids, fresh_only=False):
    """{igdb_id: add-on list} already kept (fresh_only: younger than KEEP_DAYS)."""
    if not igdb_ids:
        return {}
    with session() as s:
        rows = s.scalars(select(IgdbAddons).where(IgdbAddons.igdb_id.in_(set(igdb_ids)))).all()
        old = _now() - timedelta(days=KEEP_DAYS)
        return {r.igdb_id: json.loads(r.addons) for r in rows if not fresh_only or r.fetched_at > old}


def addons(igdb_id):
    """One game's add-on list: kept, else fetched now."""
    found = kept([igdb_id], fresh_only=True)
    if igdb_id in found:
        return found[igdb_id]
    return refresh([igdb_id]).get(igdb_id, [])


def owned_ids(item):
    return json.loads(item.dlc_owned) if item.dlc_owned else []


def item_dlc(user_id, item_id):
    """{addons: [{igdb_id, name, type, cover, year}], owned: [igdb ids]} for an owned item's game."""
    with session() as s:
        item = _own(s, user_id, item_id)
        if item.kind != "owned":
            raise CollectionError("dlc_owned_only")
        igdb_id, owned = item.game.igdb_id, owned_ids(item)
    if not igdb_id:
        return {"addons": [], "owned": [], "no_igdb": True}
    found = addons(igdb_id)
    for a in found:
        a["cover"] = COVER_URL.format(a["cover"]) if a["cover"] else None
    listed = {a["igdb_id"] for a in found}
    return {"addons": found, "owned": [i for i in owned if i in listed]}


def set_owned(user_id, item_id, owned):
    """The add-ons the user owns, from the game's list → {owned, total}."""
    if not isinstance(owned, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in owned):
        raise CollectionError("dlc_invalid")
    with session() as s:
        item = _own(s, user_id, item_id)
        if item.kind != "owned" or not item.game.igdb_id:
            raise CollectionError("dlc_owned_only")
        igdb_id = item.game.igdb_id
    listed = [a["igdb_id"] for a in addons(igdb_id)]
    chosen = [i for i in listed if i in set(owned)]
    if len(chosen) != len(set(owned)):
        raise CollectionError("dlc_invalid")
    with session() as s:
        item = _own(s, user_id, item_id)
        item.dlc_owned = json.dumps(chosen) if chosen else None
    return {"owned": len(chosen), "total": len(listed)}


def counts(rows):
    """Adds `dlc` {owned, total} to collection rows (owned items whose game has add-ons kept), else None."""
    with session() as s:
        games = dict(s.execute(select(Game.id, Game.igdb_id).where(
            Game.id.in_({r["game_id"] for r in rows}), Game.igdb_id.is_not(None))).all()) if rows else {}
    lists = kept(set(games.values()))
    for r in rows:
        listed = {a["igdb_id"] for a in lists.get(games.get(r["game_id"]), [])}
        owned = [i for i in (json.loads(r.pop("dlc_owned")) if r.get("dlc_owned") else []) if i in listed]
        r["dlc"] = {"owned": len(owned), "total": len(listed)} if r["kind"] == "owned" and listed else None
    return rows


def refresh_collection_games(limit=2000):
    """The daily run: fetch the add-on lists of owned games in collections that have none kept, or an old one."""
    with session() as s:
        ids = set(s.scalars(select(Game.igdb_id).join(CollectionItem, CollectionItem.game_id == Game.id)
                            .where(CollectionItem.kind == "owned", Game.igdb_id.is_not(None))).all())
    fresh = kept(ids, fresh_only=True)
    todo = sorted(ids - set(fresh))[:limit]
    return len(refresh(todo)) if todo else 0
