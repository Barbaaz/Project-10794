"""
Importing a user's PlayStation games and trophies into their collection (user, 2026-10-12), through
PSN's unofficial API, the one the PlayStation app uses: Sony offers no public one and its terms
don't allow this, which the user accepted (the site's PSN account could be blocked). The site signs
in with one PSN account's NPSSO token (PSN_NPSSO, never in the code; it lasts about two months, then
the admin saves a new one). The user gives their PSN name; PSN returns their trophy lists when the
profile shows trophies to anyone, and the PS4 / PS5 games they played, with the time, when it
shares those (user, 2026-10-12: "the games and the playtime" too). Each trophy list (one game, on
one console or two: "PS3,PSVITA") or played game without one is linked to our game of that name on
that console, else to IGDB's game of that name (made for the collection only, as Steam's); those
go in as owned with the trophies earned / in total, the platinum and the hours. Games only ever
played on PS Plus (PSN says so) stay out unless the user asks for them: they don't own them.
Imported games are digital, as Steam's (user, 2026-10-12: PSN doesn't say; the user changes a disc's
format, and games added by hand are physical). A game the user took out of the collection
is never imported again (PsnSkip): borrowed, rented, or PS Plus games PSN didn't say were.
"""
import logging
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import requests
from sqlalchemy import select

from app.models import CollectionItem, Game, GameEdition, Platform, PsnSkip, User
from app.services import collection_service
from app.services.igdb_game_service import (
    GAME_TYPES, IGDBGameError, _with_standard_edition, collection_editions, query,
)
from core.normalizer import normalize_name
from db import session
from pipeline.igdb import IGDB_PLATFORMS, REMAKE

log = logging.getLogger(__name__)

# PSN's sign-in as the PlayStation app does it (the same values as the PSNAWP library)
AUTH = "https://ca.account.sony.com/api/authz/v3/oauth"
CLIENT_ID = "09515159-7237-4370-9b40-3806e67c0891"
CLIENT_AUTH = "Basic MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
REDIRECT = "com.scee.psxandroid.scecompcall://redirect"
SCOPE = "psn:mobile.v2.core psn:clientapp"
PROFILE = "https://us-prof.np.community.playstation.net/userProfile/v1/users/{}/profile2"
TROPHY_TITLES = "https://m.np.playstation.com/api/trophy/v1/users/{}/trophyTitles"
PLAYED = "https://m.np.playstation.com/api/gamelist/v2/users/{}/titles"

PLATFORMS = {"PS5": "PS5", "PS4": "PS4", "PS3": "PS3", "PSVITA": "PSVita"}    # PSN's → ours (not PSPC)
# A trophy list shared by consoles ("PSVITA,PS4": bought once, played on either) is the game on the
# console the player played it on, else the newest of them (user, 2026-10-12: PS4 games came in as Vita
# games, PSN naming the Vita first)
NEWEST_FIRST = ["PS5", "PS4", "PS3", "PSVita"]
PLAYED_PLATFORMS = {"ps5_native_game": "PS5", "ps4_game": "PS4"}             # played games: PS4 / PS5 only
PLAYED_IDS = {"PPSA": "PS5", "CUSA": "PS4"}      # the console of a game PSN files as "unknown", by its title id
WAIT_SECONDS = 10 * 60           # one import per user in this time
MAX_GAMES = 5000
PAGE = 800                       # trophy lists per PSN request
PLAYED_PAGE, MAX_PLAYED_PAGES = 200, 10
IGDB_NAMES = 100                 # names per IGDB request
MAX_SEARCHES = 200               # IGDB searches for the names it doesn't have as they are (one request each)

ONLINE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,15}")
# a trophy list's name has marks and words a game's name doesn't: "Uncharted™: Drake's Fortune Trophies",
# "Gran Turismo® 7", "Crash Bandicoot (PS4)"
NOISE = re.compile(r"[™®©]|\s+troph(?:y set|ies|y)\s*$"
                   r"|\s*[(\[]?\b(?:PS4 & PS5|PS[345]|PS ?Vita|PlayStation ?[345])\b[)\]]?\s*$", re.IGNORECASE)

QUOTES = str.maketrans("‘’“”", "''\"\"")
# "Control Ultimate Edition", "God of War III Remastered", "Darksiders Warmastered Edition": IGDB's game is "Control"…
EDITION_WORDS = {"the", "edition", "remastered", "remaster", "definitive", "special", "complete", "ultimate",
                 "deluxe", "goty", "hd", "deathinitive", "warmastered", "trophy", "trophies"}

_last = {}                       # user id → when they last imported
_last_lock = threading.Lock()
_token = {"access": None, "expires": 0.0, "refresh": None, "refresh_expires": 0.0}
_token_lock = threading.Lock()


class PsnError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def npsso():
    """From the environment; on Windows also from the user's saved variables (as STEAM_API_KEY)."""
    value = os.environ.get("PSN_NPSSO")
    if not value and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                value = winreg.QueryValueEx(k, "PSN_NPSSO")[0]
        except OSError:
            pass
    if not value:
        raise PsnError("psn_unavailable", 503)
    return value.strip()


def _sign_in(**form):
    response = requests.post(f"{AUTH}/token", data={**form, "scope": SCOPE, "token_format": "jwt"},
                             headers={"Authorization": CLIENT_AUTH}, timeout=20)
    response.raise_for_status()
    data = response.json()
    now = time.time()
    _token.update(access=data["access_token"], expires=now + int(data.get("expires_in", 3600)),
                  refresh=data.get("refresh_token"), refresh_expires=now + int(data.get("refresh_token_expires_in", 0)))


def access_token():
    """PSN's access token: kept for its hour, renewed with the refresh token, else made from the NPSSO."""
    with _token_lock:
        now = time.time()
        if _token["access"] and now < _token["expires"] - 60:
            return _token["access"]
        try:
            if _token["refresh"] and now < _token["refresh_expires"] - 60:
                _sign_in(grant_type="refresh_token", refresh_token=_token["refresh"])
                return _token["access"]
            answer = requests.get(f"{AUTH}/authorize", cookies={"npsso": npsso()}, allow_redirects=False, timeout=20,
                                  params={"access_type": "offline", "client_id": CLIENT_ID, "redirect_uri": REDIRECT,
                                          "response_type": "code", "scope": SCOPE})
            code = parse_qs(urlparse(answer.headers.get("location", "")).query).get("code")
            if not code:
                log.warning("PSN refused the NPSSO token (PSN_NPSSO): expired or wrong, save a new one")
                raise PsnError("psn_unavailable", 503)
            _sign_in(grant_type="authorization_code", code=code[0], redirect_uri=REDIRECT)
            return _token["access"]
        except (requests.RequestException, ValueError, KeyError):
            _token.update(access=None, refresh=None)
            raise PsnError("psn_unavailable", 503)


def _get(url, **params):
    """(status, JSON) of a PSN request; a refused token is made again once."""
    for attempt in range(2):
        try:
            response = requests.get(url, params=params, timeout=20,
                                    headers={"Authorization": f"Bearer {access_token()}", "Accept-Language": "en-US"})
        except requests.RequestException:
            raise PsnError("psn_unavailable", 503)
        if response.status_code == 401 and attempt == 0:
            with _token_lock:
                _token["access"] = None
            continue
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {}
    return response.status_code, {}


def online_id(name):
    """A PSN name, alone or at the end of a profile link (profile.playstation.com/ana, psnprofiles.com/ana)."""
    name = (name or "").strip().split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not ONLINE_ID.fullmatch(name):
        raise PsnError("psn_profile_invalid")
    return name


def account(name):
    """(account id, PSN name as written there) of a PSN name."""
    status, data = _get(PROFILE.format(online_id(name)), fields="accountId,onlineId,currentOnlineId")
    profile = data.get("profile") or {}
    if status == 404 or (status == 200 and not profile.get("accountId")):
        raise PsnError("psn_profile_not_found", 404)
    if status != 200:
        raise PsnError("psn_unavailable", 503)
    return str(profile["accountId"]), profile.get("currentOnlineId") or profile.get("onlineId") or name


def trophy_lists(account_id):
    """[{id, name, platforms: [our codes], earned, total, platinum}]; PsnError("psn_private") when the
    profile hides its trophies. platinum: None for a game without one."""
    lists, offset = [], 0
    while len(lists) < MAX_GAMES:
        status, data = _get(TROPHY_TITLES.format(account_id), limit=PAGE, offset=offset)
        if status in (403, 404):
            raise PsnError("psn_private")
        if status != 200:
            raise PsnError("psn_unavailable", 503)
        for t in data.get("trophyTitles") or []:
            platforms = sorted({PLATFORMS[p] for p in (t.get("trophyTitlePlatform") or "").split(",") if p in PLATFORMS},
                               key=NEWEST_FIRST.index)
            defined, earned = t.get("definedTrophies") or {}, t.get("earnedTrophies") or {}
            if platforms and t.get("npCommunicationId"):
                lists.append({"id": t["npCommunicationId"], "name": t.get("trophyTitleName") or t["npCommunicationId"],
                              "platforms": platforms, "earned": sum(earned.values()), "total": sum(defined.values()),
                              "platinum": bool(earned.get("platinum")) if defined.get("platinum") else None})
        offset += len(data.get("trophyTitles") or [])
        if not data.get("trophyTitles") or offset >= (data.get("totalItemCount") or 0):
            break
    return lists[:MAX_GAMES]


def played_games(account_id):
    """[{id (title id), name, platforms: [our code], minutes, plus}] of the PS4 / PS5 games the player
    played; [] when they don't share them. plus: played on PS Plus (not bought)."""
    games, offset = [], 0
    for _ in range(MAX_PLAYED_PAGES):
        try:
            status, data = _get(PLAYED.format(account_id), categories="ps4_game,ps5_native_game",
                                limit=PLAYED_PAGE, offset=offset)
        except PsnError:
            break
        if status != 200:
            break
        for g in data.get("titles") or []:
            code = PLAYED_PLATFORMS.get(g.get("category")) or PLAYED_IDS.get((g.get("titleId") or "")[:4])
            found = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", g.get("playDuration") or "")
            if code and g.get("name") and g.get("titleId"):
                games.append({"id": g["titleId"][:20], "name": g["name"], "platforms": [code],
                              "minutes": int(found[1] or 0) * 60 + int(found[2] or 0) if found else 0,
                              "plus": g.get("service") == "ps_plus"})
        offset = data.get("nextOffset")
        if not offset:
            break
    return games


def games_of(lists, played):
    """
    The trophy lists, each with the minutes and PS Plus marks of the played games of its name and
    console, and the played games with no trophy list (one per name and console, their minutes
    added: the same game from two regions, or bought after PS Plus). Each: {id, name, platforms,
    earned, total, platinum (None: no trophy list), minutes, plus: [played on PS Plus?]}
    """
    games = [{**l, "minutes": 0, "plus": []} for l in lists]
    by_key = {(code, key_of(g["name"])): g for g in games for code in g["platforms"]}
    by_words = {}
    for g in games:
        for code in g["platforms"]:
            by_words.setdefault((code, frozenset(words(clean(g["name"])))), []).append(g)
    for p in played:
        key = (p["platforms"][0], key_of(p["name"]))
        game = by_key.get(key)
        if game is None:               # "Hitman World of Assassination Deluxe": that list, when only one has the words
            same = by_words.get((key[0], frozenset(words(clean(p["name"])))), [])
            game = same[0] if len(same) == 1 else None
        if game is None:
            game = by_key[key] = {"id": p["id"], "name": p["name"], "platforms": p["platforms"],
                                  "earned": None, "total": None, "platinum": None, "minutes": 0, "plus": []}
            games.append(game)
        game["minutes"] += p["minutes"]
        game["plus"].append(p["plus"])
        if p["minutes"] and game["platforms"][0] != key[0]:      # played there: that console first
            game["platforms"] = [key[0], *(c for c in game["platforms"] if c != key[0])]
    return games


def clean(name):
    """A trophy list's name as the game's ("Uncharted™: Drake's Fortune Trophies" → "Uncharted: Drake's Fortune",
    "ASTRO’s PLAYROOM" → "ASTRO's PLAYROOM", "DARK SOULS Ⅱ" → "DARK SOULS II")."""
    name = NOISE.sub("", NOISE.sub("", name.translate(QUOTES)))
    return unicodedata.normalize("NFKC", name).strip()           # after the marks: NFKC makes "™" "TM"


def words(name):
    """A name's words, but the ones editions add: "Devil May Cry 4 Special Edition" = "Devil May Cry 4"."""
    return set(normalize_name(name).split()) - EDITION_WORDS


def key_of(name):
    return normalize_name(clean(name))


def saved_profile(user_id):
    """{online_id, imported_at} of the user's last import, for the refresh button; None: never imported."""
    with session() as s:
        user = s.get(User, user_id)
        if not user or not user.psn_account_id:
            return None
        return {"online_id": user.psn_online_id,
                "imported_at": user.psn_imported_at.isoformat() + "Z" if user.psn_imported_at else None}


def igdb_games(lists):
    """
    {trophy list id: (IGDB id, our platform code)} for lists named as an IGDB game on one of their
    consoles: first by the name as it is (100 a request), then IGDB's search for the others, taken
    only when the words are the same but for editions' ("Killzone Shadow Fall" = "Killzone: Shadow
    Fall", "Control Ultimate Edition" = "Control"; "Overcooked" is not "Overcooked! 2").
    """
    platforms = ",".join(str(IGDB_PLATFORMS[p]) for p in PLATFORMS.values())
    where = (f"platforms = ({platforms}) & game_type = ({','.join(map(str, GAME_TYPES))}) & version_parent = null")
    fields = "fields name,platforms,first_release_date,game_type;"
    found, released = {}, {}

    def take(games, same):
        """Of the games of the same name on its console, a game or a remake before a remaster or a port,
        then the newest: on a PS4, "DOOM" is 2016's, not 1993's re-released in 2019 and 2024 (IGDB's
        remasters), as for the stores' remakes (pipeline/igdb.py)"""
        for g in games:
            for l in lists:
                code = next((p for p in l["platforms"] if IGDB_PLATFORMS[p] in (g.get("platforms") or [])), None)
                rank = (g.get("game_type") in (0, REMAKE), g.get("first_release_date") or 0)
                if code and same(l, g.get("name") or "") and (l["id"] not in found or rank > released[l["id"]]):
                    found[l["id"]], released[l["id"]] = (g["id"], code), rank

    names = list(dict.fromkeys(clean(l["name"]).replace('"', " ").replace("\\", " ").strip() for l in lists))
    for start in range(0, len(names), IGDB_NAMES):
        either = " | ".join(f'name ~ "{n}"' for n in names[start:start + IGDB_NAMES] if n)
        if either:
            take(query(f"{fields} where ({either}) & {where}; limit 500;"),
                 lambda l, name: key_of(l["name"]) == normalize_name(name))
    left = list(dict.fromkeys(clean(l["name"]).replace('"', " ").replace("\\", " ").strip()
                              for l in lists if l["id"] not in found))
    for name in left[:MAX_SEARCHES]:
        if words(name):
            take(query(f'search "{name}"; {fields} where {where}; limit 10;'),
                 lambda l, other: clean(l["name"]).replace('"', " ").replace("\\", " ").strip() == name
                 and words(name) == words(other))
    return found


def _editions(lists):
    """{trophy list id: edition id}: our game of that name on one of its consoles, else IGDB's (made)."""
    editions = {}
    with session() as s:
        codes = {code: pid for code, pid in s.execute(select(Platform.code, Platform.id)
                                                       .where(Platform.code.in_(PLATFORMS.values())))}
        ours, by_words = {}, {}
        for game_id, platform_id, key, title in s.execute(select(Game.id, Game.platform_id, Game.normalized_title, Game.title)
                .where(Game.platform_id.in_(codes.values()), Game.kind == "game").order_by(Game.id)):
            ours.setdefault((platform_id, key), game_id)
            by_words.setdefault((platform_id, frozenset(words(title))), set()).add(game_id)
        for l in lists:
            key = key_of(l["name"])
            game_id = next((ours[(codes[p], key)] for p in l["platforms"] if (codes.get(p), key) in ours), None)
            if game_id is None:        # the same words but an edition's (user, 2026-10-12: the same game, not a
                same = [by_words.get((codes[p], frozenset(words(clean(l["name"])))), set()) for p in l["platforms"]]
                game_id = next((min(ids) for ids in same if len(ids) == 1), None)   # second one beside it)
            if game_id:
                editions[l["id"]] = _with_standard_edition(s, s.get(Game, game_id))["edition_id"]
    unknown = [l for l in lists if l["id"] not in editions]
    if unknown:
        try:
            linked = igdb_games(unknown)
            for code in {c for _, c in linked.values()}:
                made = collection_editions([i for i, c in linked.values() if c == code], code)
                editions.update({lid: made[i] for lid, (i, c) in linked.items() if c == code and i in made})
        except IGDBGameError:
            pass                         # IGDB down: our games alone
    return editions


def _moved_to_console(user_id, item_id, edition_id, platforms):
    """
    An item imported on another of its trophy list's consoles than the one it's on now (a list shared
    by the Vita and the PS4, put on the Vita before 2026-10-12) goes to this edition, on the right
    console. An edition the user chose on the same console stays; so does an item whose copy is
    there already (the same edition and format). True when moved.
    """
    with session() as s:
        item, edition = s.get(CollectionItem, item_id), s.get(GameEdition, edition_id)
        now, then = item.game.platform.code, edition.game.platform.code
        if item.edition_id == edition_id or now == then or now not in PLATFORMS.values() or now not in platforms \
                or collection_service._other(s, item, item.kind, item.format, edition_id):
            return False
        item.edition_id, item.game_id = edition.id, edition.game_id
        return True


def import_games(user_id, name=None, ps_plus=False):
    """
    The user's PlayStation games into their collection; without a name, the player imported last
    (the refresh button). ps_plus: also the games only played on PS Plus. {added, updated, total,
    skipped, ps_plus, missing: [{name, platform}]}: added = new owned items, updated = owned ones
    whose trophies or hours changed; ps_plus = PS Plus games left out; missing = games neither we
    nor IGDB know. Trophies come from PSN as they are; hours only go up (the user may have more).
    """
    with _last_lock:
        if time.monotonic() - _last.get(user_id, -WAIT_SECONDS) < WAIT_SECONDS:
            raise PsnError("psn_wait", 429)
    if (name or "").strip():
        account_id, shown = account(name)
    else:
        with session() as s:
            user = s.get(User, user_id)
            account_id, shown = user.psn_account_id, user.psn_online_id
        if not account_id:
            raise PsnError("psn_profile_invalid")
    games = games_of(trophy_lists(account_id), played_games(account_id))
    plus_only = [g for g in games if g["plus"] and all(g["plus"])]
    if not ps_plus:
        games = [g for g in games if g not in plus_only]
    with session() as s:          # taken out of the collection before (borrowed, or not wanted)
        skips = s.execute(select(PsnSkip.psn_id, PsnSkip.edition_id).where(PsnSkip.user_id == user_id)).all()
    # a game taken out stays out on the console it was taken out from (its edition; a trophy list and a
    # played game of another name or region can be the same game), not on another: a list once put on
    # the wrong console (a Vita game played on a PS4) comes back on the right one (user, 2026-10-12)
    skipped_editions = {edition_id for _, edition_id in skips if edition_id}
    games = [g for g in games if g["id"] not in {psn_id for psn_id, edition_id in skips if not edition_id}]
    with _last_lock:               # only read trophies count: a private profile made public can try again at once
        _last[user_id] = time.monotonic()
    editions = _editions(games)
    skipped = {gid for gid, e in editions.items() if e in skipped_editions}
    editions = {gid: e for gid, e in editions.items() if gid not in skipped}

    targets, minutes = {}, {}      # edition id → its trophy list with the most earned (else a played game), minutes
    rank = lambda g: (g["total"] is not None, g["earned"] or 0)
    for g in games:
        edition_id = editions.get(g["id"])
        if edition_id:
            minutes[edition_id] = minutes.get(edition_id, 0) + g["minutes"]
            if edition_id not in targets or rank(g) > rank(targets[edition_id]):
                targets[edition_id] = g
    with session() as s:
        items = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id, CollectionItem.kind == "owned")
                          .order_by(CollectionItem.format == "digital", CollectionItem.id)).all()   # the download's last: it wins
        by_list = {i.psn_id: i.id for i in items if i.psn_id}          # also after the user changed its edition
        by_edition = {i.edition_id: i.id for i in items}
        had = {i.id: (i.hours, i.achievements, i.achievements_total, i.platinum, i.psn_id) for i in items}

    added = updated = moved = 0
    for edition_id, l in targets.items():
        hours = min((Decimal(minutes[edition_id]) / 60).quantize(Decimal("0.1")), collection_service.MAX_HOURS) \
            or None                                       # a few minutes: none
        trophies = {"achievements": l["earned"], "achievements_total": l["total"] or None, "platinum": l["platinum"]} \
            if l["total"] is not None else {}             # a played game without a trophy list: none to say
        item_id = by_list.get(l["id"]) or by_edition.get(edition_id)
        if item_id is not None and _moved_to_console(user_id, item_id, edition_id, l["platforms"]):
            moved += 1
        if item_id is None:
            try:
                item_id = collection_service.add(user_id, edition_id, "owned", format="digital", **trophies,
                                                 **({"hours": str(hours)} if hours else {}))
            except collection_service.CollectionError:      # the collection is full
                break
            added += 1
        else:
            old_hours, *old_trophies, old_list = had[item_id]
            change = dict(trophies) if trophies and old_trophies != list(trophies.values()) else {}
            if hours and (old_hours is None or old_hours < hours):
                change["hours"] = str(hours)
            if change:
                collection_service.update(user_id, item_id, change)
                updated += 1
            if old_list == l["id"]:
                continue
        with session() as s:       # the item's trophy list: refreshes find it, taking it out skips it
            s.get(CollectionItem, item_id).psn_id = l["id"]
    with session() as s:
        user = s.get(User, user_id)
        user.psn_account_id, user.psn_online_id = account_id, shown
        user.psn_imported_at = datetime.now(timezone.utc).replace(tzinfo=None)

    missing = [{"name": clean(g["name"]), "platform": "/".join(g["platforms"])}
               for g in games if g["id"] not in editions]
    missing.sort(key=lambda m: m["name"].lower())
    return {"added": added, "updated": updated, "moved": moved, "total": len(games), "skipped": len(skipped),
            "ps_plus": 0 if ps_plus else len(plus_only), "missing": missing}
