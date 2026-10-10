"""
Games no store sells (older platforms, mostly), created from IGDB when a user wants to sell a copy or
add it to their collection (user, 2026-10-07; never a typed name, unlike Trophium's collection):
the sell form and /collection search IGDB when the catalogue doesn't have the game, and picking a result on a
platform creates the game there with its IGDB information and a Standard edition (the game's other
IGDB editions are offered too: edition_options). The game then
works like any other (game page, collection, reviews); if a store starts selling it, the daily
processing finds it by its name. One created game nobody uses is removed by the next rematch.
"""
import re
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import func, select

from app.models import Game, GameEdition, Platform
from core.editions import key_of_edition_name
from core.normalizer import normalize_name
from db import session
from pipeline.igdb import FIELDS, IGDB_PLATFORMS, IGDBClient, game_info

MAX_PER_DAY = 20                   # games one user may create in 24 h
MAX_RESULTS = 20
# IGDB game_type: 0 main game, 4 standalone expansion, 8 remake, 9 remaster, 10 expanded game, 11 port
GAME_TYPES = (0, 4, 8, 9, 10, 11)
COVER_URL = "https://images.igdb.com/igdb/image/upload/t_cover_big/{}.jpg"


class IGDBGameError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


_client = None


def query(body, endpoint="games"):
    """IGDB's answer; the client (and its token) is kept between requests, made again if refused."""
    global _client
    for attempt in range(2):
        try:
            if _client is None:
                _client = IGDBClient()
            return _client.query(body, endpoint)
        except (requests.RequestException, RuntimeError):
            _client = None              # an expired token: a new one on the second try
    raise IGDBGameError("igdb_unavailable", 503)


def known_platforms():
    """{IGDB platform id: (our code, name)} for our platforms IGDB knows."""
    with session() as s:
        rows = s.execute(select(Platform.code, Platform.name)).all()
    return {IGDB_PLATFORMS[code]: (code, name) for code, name in rows if code in IGDB_PLATFORMS}


def search(q):
    """IGDB games whose name has q, on our platforms: [{igdb_id, name, year, cover, platforms: [{code, name}]}]."""
    # inside IGDB's search "…": no quote to close it, no backslash to escape the closing one
    q = " ".join((q or "").replace('"', " ").replace("\\", " ").split())[:100]
    if len(q) < 2:
        return []
    platforms = known_platforms()
    results = query(f'search "{q}"; fields name,first_release_date,cover.image_id,platforms; '
                    f'where platforms = ({",".join(map(str, platforms))}) & game_type = ({",".join(map(str, GAME_TYPES))}) '
                    f'& version_parent = null; limit {MAX_RESULTS};')
    games = []
    for g in results:
        ours = [{"code": platforms[p][0], "name": platforms[p][1]} for p in g.get("platforms", []) if p in platforms]
        if ours:
            released = g.get("first_release_date")
            games.append({"igdb_id": g["id"], "name": g["name"],
                          "year": datetime.fromtimestamp(released, timezone.utc).year if released else None,
                          "cover": COVER_URL.format(g["cover"]["image_id"]) if g.get("cover") else None,
                          "platforms": ours})
    return games


def create(user_id, igdb_id, platform_code):
    """
    The game for an IGDB game on one of our platforms: the one we have already (same IGDB game, or
    same name, on that platform), else created with a Standard edition. {game_id, edition_id}
    """
    try:
        igdb_id = int(igdb_id)
    except (TypeError, ValueError):
        raise IGDBGameError("not_found", 404)
    if platform_code not in IGDB_PLATFORMS:
        raise IGDBGameError("platform_invalid")

    with session() as s:
        platform = s.scalars(select(Platform).where(Platform.code == platform_code)).first()
        if not platform:
            raise IGDBGameError("platform_invalid")
        game = s.scalars(select(Game).where(Game.igdb_id == igdb_id, Game.platform_id == platform.id)).first()
        if game:
            return _with_standard_edition(s, game)

        found = query(f"fields {FIELDS},platforms; where id = {igdb_id};")
        if not found or IGDB_PLATFORMS[platform_code] not in found[0].get("platforms", []):
            raise IGDBGameError("not_found", 404)
        g = found[0]
        key = normalize_name(g["name"])
        game = s.scalars(select(Game).where(Game.normalized_title == key, Game.platform_id == platform.id)).first()
        if game:                       # the stores' copy of it: keep that one
            return _with_standard_edition(s, game)

        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        made = s.scalar(select(func.count()).select_from(Game).where(Game.created_by == user_id, Game.created_at > since))
        if made >= MAX_PER_DAY:
            raise IGDBGameError("games_per_day", 429)

        info = game_info(g)
        game = Game(platform_id=platform.id, title=g["name"][:300], normalized_title=key, created_by=user_id,
                    image_url=COVER_URL.format(info["cover_image_id"]) if info["cover_image_id"] else None,
                    igdb_checked_at=datetime.now(timezone.utc).replace(tzinfo=None), **info)
        s.add(game)
        s.flush()
        return _with_standard_edition(s, game)


# Versions only sold as downloads: not a copy anyone can sell here (physical copies only)
DIGITAL_VERSION = re.compile(r"digital|cloud|download", re.IGNORECASE)


def edition_options(game_id):
    """
    The game's editions on IGDB that we don't have yet, for the sell form: [name] ("Collector's
    Edition", "Steelbook Edition"…), physical, on the game's platform. The seller picks one instead
    of typing a name (listing_service.create_listing creates it). [] without an IGDB match.
    """
    with session() as s:
        game = s.get(Game, int(game_id))
        if not game or not game.igdb_id:
            return []
        code = s.get(Platform, game.platform_id).code
        have = set(s.scalars(select(GameEdition.edition_key).where(GameEdition.game_id == game.id)))
    platform = IGDB_PLATFORMS.get(code)
    versions = query(f"fields name,version_title,platforms; where version_parent = {int(game.igdb_id)}; limit 50;")
    names = {}
    for v in versions:
        name = (v.get("version_title") or "").strip()
        if not name or DIGITAL_VERSION.search(name) or (v.get("platforms") and platform not in v["platforms"]):
            continue
        key = key_of_edition_name(name)
        if key not in have:
            names.setdefault(key, name[:200])
    return sorted(names.values())


def _with_standard_edition(s, game):
    edition = s.scalars(select(GameEdition).where(GameEdition.game_id == game.id, GameEdition.edition_key == "")).first()
    if edition is None:
        edition = GameEdition(game_id=game.id, edition_key="", name="Standard")
        s.add(edition)
        s.flush()
    return {"game_id": game.id, "edition_id": edition.id}
