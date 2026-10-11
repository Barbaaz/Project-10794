"""
Importing a user's Steam games into their collection (Steam Web API, our key in STEAM_API_KEY, never
in the code). The user gives their profile (link, custom name or 17-digit id); Steam returns their
games only when the profile's game details are public. Each game is linked to our PC game through
IGDB's Steam ids (external_games, source 1), else by its name; those go in as owned, digital, with
Steam's hours and achievements. Games we don't have are made from IGDB for the collection only (user,
2026-10-11): they stay out of the catalogue until a store or a seller offers them. The profile is
remembered, so the import can be refreshed with one button.
"""
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import requests
from sqlalchemy import select

from app.models import CollectionItem, Game, Platform, User
from app.services import collection_service
from app.services.igdb_game_service import IGDBGameError, _with_standard_edition, collection_editions, query
from core.normalizer import normalize_name
from db import session

API = "https://api.steampowered.com"
STEAM_SOURCE = 1                 # IGDB external_game_source: Steam
BATCH = 500                      # Steam ids per IGDB request
WAIT_SECONDS = 10 * 60           # one import per user in this time (each asks Steam and IGDB)
MAX_GAMES = 5000
MAX_ACHIEVEMENT_LOOKUPS = 500    # Steam requests for achievements in one import
ACHIEVEMENT_WORKERS = 4

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
    """[{appid, name, minutes, stats (it has achievements)}]; SteamError("steam_private") when the profile hides its games."""
    data = _get("IPlayerService/GetOwnedGames/v1/", steamid=steamid, include_appinfo=1)
    if "games" not in data:
        raise SteamError("steam_private")
    return [{"appid": g["appid"], "name": g.get("name") or str(g["appid"]), "minutes": g.get("playtime_forever") or 0,
             "stats": bool(g.get("has_community_visible_stats"))} for g in data["games"][:MAX_GAMES]]


def achievements(steamid, appid):
    """(done, total) of one game's Steam achievements, or None (it has none, or Steam didn't say)."""
    try:
        response = requests.get(f"{API}/ISteamUserStats/GetPlayerAchievements/v1/",
                                params={"key": api_key(), "steamid": steamid, "appid": appid}, timeout=20)
        found = (response.json().get("playerstats") or {}).get("achievements") if response.ok else None
    except (requests.RequestException, ValueError):
        return None
    if not found:
        return None
    return sum(1 for a in found if a.get("achieved")), len(found)


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


def saved_profile(user_id):
    """{steam_id, imported_at} of the user's last import, for the refresh button; None: never imported."""
    with session() as s:
        user = s.get(User, user_id)
        if not user or not user.steam_id:
            return None
        return {"steam_id": user.steam_id,
                "imported_at": user.steam_imported_at.isoformat() + "Z" if user.steam_imported_at else None}


def _editions(games, linked):
    """{Steam app id: edition id}: our PC games (by IGDB, else by name), then the rest made from IGDB."""
    editions = {}
    with session() as s:
        pc = s.scalars(select(Platform.id).where(Platform.code == "PC")).first()
        ours = s.execute(select(Game.id, Game.igdb_id, Game.normalized_title)
                         .where(Game.platform_id == pc, Game.kind == "game").order_by(Game.id)).all()
        by_igdb, by_name = {}, {}
        for game_id, igdb_id, key in ours:
            if igdb_id:
                by_igdb.setdefault(igdb_id, game_id)
            by_name.setdefault(key, game_id)
        for g in games:
            game_id = by_igdb.get(linked.get(g["appid"])) or by_name.get(normalize_name(g["name"]))
            if game_id:
                editions[g["appid"]] = _with_standard_edition(s, s.get(Game, game_id))["edition_id"]
    unknown = sorted({linked[g["appid"]] for g in games if g["appid"] not in editions and g["appid"] in linked})
    if unknown:
        try:
            made = collection_editions(unknown, "PC")
        except IGDBGameError:
            made = {}
        editions.update({g["appid"]: made[linked[g["appid"]]] for g in games
                         if g["appid"] not in editions and linked.get(g["appid"]) in made})
    return editions


def import_games(user_id, profile=None):
    """
    The user's Steam games into their collection; without a profile, the one imported last (the
    refresh button). {added, updated, total, missing: [{name, hours}]}: added = new owned items,
    updated = owned ones whose hours or achievements changed; missing = games IGDB doesn't
    know. Achievements are asked for the played games that have some, when new or played since
    (one Steam request each, at most MAX_ACHIEVEMENT_LOOKUPS).
    """
    with _last_lock:
        if time.monotonic() - _last.get(user_id, -WAIT_SECONDS) < WAIT_SECONDS:
            raise SteamError("steam_wait", 429)
    if (profile or "").strip():
        steamid = steam_id(profile)
    else:
        steamid = (saved_profile(user_id) or {}).get("steam_id")
        if not steamid:
            raise SteamError("steam_profile_invalid")
    games = owned_games(steamid)
    with _last_lock:               # only a read library counts: a private profile made public can try again at once
        _last[user_id] = time.monotonic()
    try:
        linked = igdb_ids([g["appid"] for g in games])
    except IGDBGameError:
        linked = {}                    # IGDB down: names alone
    editions = _editions(games, linked)

    targets = {}                       # edition id → its Steam app played most (two apps on one game)
    for g in games:
        edition_id = editions.get(g["appid"])
        if edition_id and g["minutes"] >= targets.get(edition_id, {"minutes": -1})["minutes"]:
            targets[edition_id] = g
    with session() as s:
        owned = {i.edition_id: (i.id, i.hours, i.achievements_total) for i in s.scalars(select(CollectionItem).where(
            CollectionItem.user_id == user_id, CollectionItem.kind == "owned"))}

    changes = {}                       # edition id → what to set (new items: maybe nothing)
    for edition_id, g in targets.items():
        hours = min((Decimal(g["minutes"]) / 60).quantize(Decimal("0.1")), collection_service.MAX_HOURS) \
            if g["minutes"] else None
        item_id, had, total = owned.get(edition_id, (None, None, None))
        raised = hours and (had is None or had < hours)
        if item_id is None or raised or (hours and g["stats"] and total is None):     # achievements never read
            changes[edition_id] = {"hours": str(hours)} if raised or item_id is None and hours else {}
    asked = [(e, targets[e]["appid"]) for e in changes if targets[e]["minutes"] and targets[e]["stats"]]
    asked = asked[:MAX_ACHIEVEMENT_LOOKUPS]
    with ThreadPoolExecutor(ACHIEVEMENT_WORKERS) as pool:
        for (edition_id, _), count in zip(asked, pool.map(lambda pair: achievements(steamid, pair[1]), asked)):
            if count:
                changes[edition_id].update(achievements=count[0], achievements_total=count[1])

    added = updated = 0
    for edition_id, change in changes.items():
        item_id = owned.get(edition_id, (None,))[0]
        if item_id is None:
            try:
                collection_service.add(user_id, edition_id, "owned", format="digital", **change)
            except collection_service.CollectionError:      # the collection is full
                break
            added += 1
        elif change:
            collection_service.update(user_id, item_id, change)
            updated += 1
    with session() as s:
        user = s.get(User, user_id)
        user.steam_id, user.steam_imported_at = steamid, datetime.now(timezone.utc).replace(tzinfo=None)

    missing = [{"name": g["name"], "hours": round(g["minutes"] / 60, 1) if g["minutes"] else None}
               for g in games if g["appid"] not in editions]
    missing.sort(key=lambda m: m["name"].lower())
    return {"added": added, "updated": updated, "total": len(games), "missing": missing}
