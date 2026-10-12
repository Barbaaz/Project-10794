"""
Importing a user's PlayStation games and trophies into their collection (user, 2026-10-12), through
PSN's unofficial API, the one the PlayStation app uses: Sony offers no public one and its terms
don't allow this, which the user accepted (the site's PSN account could be blocked). The site signs
in with one PSN account's NPSSO token (PSN_NPSSO, never in the code; it lasts about two months, then
the admin saves a new one). The user gives their PSN name; PSN returns their trophy lists when the
profile shows trophies to anyone. Each list (one game, on one console or two: "PS3,PSVITA") is
linked to our game of that name on that console, else to IGDB's game of that name (made for the
collection only, as Steam's); those go in as owned with the trophies earned / in total, the
platinum, and PS4 / PS5 play time when the player shares it. The format isn't known (a disc or a
download): left empty. A trophy list the user took out of the collection is never imported again
(PsnSkip): the lists also have games played on PS Plus, borrowed or rented.
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

from app.models import CollectionItem, Game, Platform, PsnSkip, User
from app.services import collection_service
from app.services.igdb_game_service import (
    GAME_TYPES, IGDBGameError, _with_standard_edition, collection_editions, query,
)
from core.normalizer import normalize_name
from db import session
from pipeline.igdb import IGDB_PLATFORMS

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
PLAYED_PLATFORMS = {"ps5_native_game": "PS5", "ps4_game": "PS4"}             # play time: PS4 / PS5 only
WAIT_SECONDS = 10 * 60           # one import per user in this time
MAX_GAMES = 5000
PAGE = 800                       # trophy lists per PSN request
PLAYED_PAGE, MAX_PLAYED_PAGES = 200, 10
IGDB_NAMES = 100                 # names per IGDB request
MAX_SEARCHES = 200               # IGDB searches for the names it doesn't have as they are (one request each)

ONLINE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,15}")
# a trophy list's name has marks and words a game's name doesn't: "Uncharted™: Drake's Fortune Trophies",
# "Gran Turismo® 7", "Crash Bandicoot (PS4)"
NOISE = re.compile(r"[™®©]|\s+troph(?:y set|ies)\s*$|\s*[(\[]?\b(?:PS[345]|PS ?Vita)\b[)\]]?\s*$", re.IGNORECASE)

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
            platforms = [PLATFORMS[p] for p in (t.get("trophyTitlePlatform") or "").split(",") if p in PLATFORMS]
            defined, earned = t.get("definedTrophies") or {}, t.get("earnedTrophies") or {}
            if platforms and t.get("npCommunicationId"):
                lists.append({"id": t["npCommunicationId"], "name": t.get("trophyTitleName") or t["npCommunicationId"],
                              "platforms": platforms, "earned": sum(earned.values()), "total": sum(defined.values()),
                              "platinum": bool(earned.get("platinum")) if defined.get("platinum") else None})
        offset += len(data.get("trophyTitles") or [])
        if not data.get("trophyTitles") or offset >= (data.get("totalItemCount") or 0):
            break
    return lists[:MAX_GAMES]


def play_minutes(account_id):
    """{(our platform code, name key): minutes} of the PS4 / PS5 games the player shares; {} when they don't."""
    minutes, offset = {}, 0
    for _ in range(MAX_PLAYED_PAGES):
        try:
            status, data = _get(PLAYED.format(account_id), categories="ps4_game,ps5_native_game",
                                limit=PLAYED_PAGE, offset=offset)
        except PsnError:
            break
        if status != 200:
            break
        for g in data.get("titles") or []:
            code = PLAYED_PLATFORMS.get(g.get("category"))
            found = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", g.get("playDuration") or "")
            if code and found and g.get("name"):
                key = (code, key_of(g["name"]))
                minutes[key] = minutes.get(key, 0) + int(found[1] or 0) * 60 + int(found[2] or 0)
        offset = data.get("nextOffset")
        if not offset:
            break
    return minutes


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
    found = {}

    def take(games, same):
        for g in games:
            for l in lists:
                code = next((p for p in l["platforms"] if IGDB_PLATFORMS[p] in (g.get("platforms") or [])), None)
                if code and l["id"] not in found and same(l, g.get("name") or ""):
                    found[l["id"]] = (g["id"], code)

    names = list(dict.fromkeys(clean(l["name"]).replace('"', " ").replace("\\", " ").strip() for l in lists))
    for start in range(0, len(names), IGDB_NAMES):
        either = " | ".join(f'name ~ "{n}"' for n in names[start:start + IGDB_NAMES] if n)
        if either:
            take(query(f"fields name,platforms; where ({either}) & {where}; limit 500;"),
                 lambda l, name: key_of(l["name"]) == normalize_name(name))
    left = list(dict.fromkeys(clean(l["name"]).replace('"', " ").replace("\\", " ").strip()
                              for l in lists if l["id"] not in found))
    for name in left[:MAX_SEARCHES]:
        if words(name):
            take(query(f'search "{name}"; fields name,platforms; where {where}; limit 10;'),
                 lambda l, other: clean(l["name"]).replace('"', " ").replace("\\", " ").strip() == name
                 and words(name) == words(other))
    return found


def _editions(lists):
    """{trophy list id: edition id}: our game of that name on one of its consoles, else IGDB's (made)."""
    editions = {}
    with session() as s:
        codes = {code: pid for code, pid in s.execute(select(Platform.code, Platform.id)
                                                       .where(Platform.code.in_(PLATFORMS.values())))}
        ours = {}
        for game_id, platform_id, key in s.execute(select(Game.id, Game.platform_id, Game.normalized_title).where(
                Game.platform_id.in_(codes.values()), Game.kind == "game").order_by(Game.id)):
            ours.setdefault((platform_id, key), game_id)
        for l in lists:
            key = key_of(l["name"])
            game_id = next((ours[(codes[p], key)] for p in l["platforms"] if (codes.get(p), key) in ours), None)
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


def import_games(user_id, name=None):
    """
    The user's PlayStation games into their collection; without a name, the player imported last
    (the refresh button). {added, updated, total, skipped, missing: [{name, platform}]}: added = new
    owned items, updated = owned ones whose trophies or hours changed; missing = games neither we
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
    lists = trophy_lists(account_id)
    with session() as s:          # taken out of the collection before (played on PS Plus, or not wanted)
        skipped = set(s.scalars(select(PsnSkip.psn_id).where(PsnSkip.user_id == user_id)))
    lists = [l for l in lists if l["id"] not in skipped]
    with _last_lock:               # only read trophies count: a private profile made public can try again at once
        _last[user_id] = time.monotonic()
    editions = _editions(lists)
    minutes = play_minutes(account_id) if editions else {}

    targets = {}                   # edition id → its trophy list with the most earned (two lists on one game)
    for l in lists:
        edition_id = editions.get(l["id"])
        if edition_id and l["earned"] >= targets.get(edition_id, {"earned": -1})["earned"]:
            targets[edition_id] = l
    with session() as s:
        items = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id,
                                                       CollectionItem.kind == "owned")).all()
        by_list = {i.psn_id: i.id for i in items if i.psn_id}          # also after the user changed its edition
        by_edition = {i.edition_id: i.id for i in items}
        had = {i.id: (i.hours, i.achievements, i.achievements_total, i.platinum, i.psn_id) for i in items}

    added = updated = 0
    for edition_id, l in targets.items():
        played = sum(minutes.get((p, key_of(l["name"])), 0) for p in l["platforms"])
        hours = min((Decimal(played) / 60).quantize(Decimal("0.1")), collection_service.MAX_HOURS) or None   # a few minutes: none
        trophies = {"achievements": l["earned"], "achievements_total": l["total"] or None, "platinum": l["platinum"]}
        item_id = by_list.get(l["id"]) or by_edition.get(edition_id)
        if item_id is None:
            try:
                item_id = collection_service.add(user_id, edition_id, "owned", format=None, **trophies,
                                                 **({"hours": str(hours)} if hours else {}))
            except collection_service.CollectionError:      # the collection is full
                break
            added += 1
        else:
            old_hours, *old_trophies, old_list = had[item_id]
            change = dict(trophies) if old_trophies != list(trophies.values()) else {}
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

    missing = [{"name": clean(l["name"]), "platform": "/".join(l["platforms"])}
               for l in lists if l["id"] not in editions]
    missing.sort(key=lambda m: m["name"].lower())
    return {"added": added, "updated": updated, "total": len(lists), "skipped": len(skipped), "missing": missing}
