"""
Importing a user's Steam games into their collection (Steam Web API, our key in STEAM_API_KEY, never
in the code). The user gives their profile (link, custom name or 17-digit id); Steam returns their
games only when the profile's game details are public. Each game is linked to our PC game through
IGDB's Steam ids (external_games, source 1), else by its name; those go in as owned, digital, with
Steam's hours. The others come back with their IGDB id, so the page can offer the usual IGDB add
(igdb_game_service.create, which keeps its games-a-day limit): an import never fills the catalogue.
"""
import os
import re
import sys
import threading
import time
from decimal import Decimal

import requests
from sqlalchemy import select

from app.models import CollectionItem, Game, Platform
from app.services import collection_service
from app.services.igdb_game_service import IGDBGameError, _with_standard_edition, query
from core.normalizer import normalize_name
from db import session

API = "https://api.steampowered.com"
STEAM_SOURCE = 1                 # IGDB external_game_source: Steam
BATCH = 500                      # Steam ids per IGDB request
WAIT_SECONDS = 10 * 60           # one import per user in this time (each asks Steam and IGDB)
MAX_GAMES = 5000

PROFILE = re.compile(r"(?:steamcommunity\.com/(?:(?P<kind>id|profiles)/))?(?P<name>[A-Za-z0-9_-]{2,64})/?$")
_last = {}                       # user id → when they last imported
_last_lock = threading.Lock()


class SteamError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def api_key():
    """From the environment; on Windows also from the user's saved variables (as IGDB's credentials)."""
    key = os.environ.get("STEAM_API_KEY")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "STEAM_API_KEY")[0]
        except OSError:
            pass
    if not key:
        raise SteamError("steam_unavailable", 503)
    return key


def _get(path, **params):
    try:
        response = requests.get(f"{API}/{path}", params={"key": api_key(), **params}, timeout=20)
        response.raise_for_status()
        return response.json().get("response") or {}
    except (requests.RequestException, ValueError):
        raise SteamError("steam_unavailable", 503)


def steam_id(profile):
    """The 17-digit Steam id of a profile link, custom name or id."""
    match = PROFILE.search((profile or "").strip().split("?")[0])
    if not match:
        raise SteamError("steam_profile_invalid")
    name = match["name"]
    if re.fullmatch(r"7656\d{13}", name) and match["kind"] != "id":
        return name
    found = _get("ISteamUser/ResolveVanityURL/v1/", vanityurl=name)
    if found.get("success") != 1:
        raise SteamError("steam_profile_not_found", 404)
    return found["steamid"]


def owned_games(steamid):
    """[{appid, name, minutes}]; SteamError("steam_private") when the profile hides its games."""
    data = _get("IPlayerService/GetOwnedGames/v1/", steamid=steamid, include_appinfo=1)
    if "games" not in data:
        raise SteamError("steam_private")
    return [{"appid": g["appid"], "name": g.get("name") or str(g["appid"]), "minutes": g.get("playtime_forever") or 0}
            for g in data["games"][:MAX_GAMES]]


def igdb_ids(appids):
    """{Steam app id: IGDB game id}"""
    found = {}
    for start in range(0, len(appids), BATCH):
        uids = ",".join(f'"{a}"' for a in appids[start:start + BATCH])
        for row in query(f"fields game,uid; where external_game_source = {STEAM_SOURCE} & uid = ({uids}); "
                         f"limit {BATCH};", endpoint="external_games"):
            if row.get("game") and str(row.get("uid", "")).isdigit():
                found.setdefault(int(row["uid"]), row["game"])
    return found


def import_games(user_id, profile):
    """
    The user's Steam games into their collection. {added, updated, total, missing: [{name, igdb_id,
    hours}]}: added = new owned items, updated = owned ones whose hours Steam raised; missing = games
    we don't have on PC (igdb_id None when IGDB doesn't know the Steam game either).
    """
    with _last_lock:
        if time.monotonic() - _last.get(user_id, -WAIT_SECONDS) < WAIT_SECONDS:
            raise SteamError("steam_wait", 429)
    games = owned_games(steam_id(profile))
    with _last_lock:               # only a read library counts: a private profile made public can try again at once
        _last[user_id] = time.monotonic()
    try:
        linked = igdb_ids([g["appid"] for g in games])
    except IGDBGameError:
        linked = {}                    # IGDB down: names alone

    added = updated = 0
    missing = []
    with session() as s:
        pc = s.scalars(select(Platform.id).where(Platform.code == "PC")).first()
        ours = s.execute(select(Game.id, Game.igdb_id, Game.normalized_title)
                         .where(Game.platform_id == pc, Game.kind == "game").order_by(Game.id)).all()
        by_igdb, by_name = {}, {}
        for game_id, igdb_id, key in ours:
            if igdb_id:
                by_igdb.setdefault(igdb_id, game_id)
            by_name.setdefault(key, game_id)
        targets = {}                   # edition id → Steam hours (two Steam apps on one game: the most)
        for g in games:
            hours = min((Decimal(g["minutes"]) / 60).quantize(Decimal("0.1")), collection_service.MAX_HOURS) \
                if g["minutes"] else None
            game_id = by_igdb.get(linked.get(g["appid"])) or by_name.get(normalize_name(g["name"]))
            if game_id:
                edition_id = _with_standard_edition(s, s.get(Game, game_id))["edition_id"]
                targets[edition_id] = max(targets.get(edition_id) or 0, hours or 0) or None
            else:
                missing.append({"name": g["name"], "igdb_id": linked.get(g["appid"]), "hours": hours})
        owned = {i.edition_id: (i.id, i.hours) for i in s.scalars(select(CollectionItem).where(
            CollectionItem.user_id == user_id, CollectionItem.kind == "owned"))}

    for edition_id, hours in targets.items():
        item_id, had = owned.get(edition_id, (None, None))
        if item_id is None:
            try:
                collection_service.add(user_id, edition_id, "owned", format="digital",
                                       **({"hours": str(hours)} if hours else {}))
            except collection_service.CollectionError:      # the collection is full
                break
            added += 1
        elif hours and (had is None or had < hours):
            collection_service.update(user_id, item_id, {"hours": str(hours)})
            updated += 1
    missing.sort(key=lambda m: (m["igdb_id"] is None, m["name"].lower()))
    return {"added": added, "updated": updated, "total": len(games),
            "missing": [{**m, "hours": float(m["hours"]) if m["hours"] else None} for m in missing]}
