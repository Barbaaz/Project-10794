"""
Game information from IGDB (summary, genres, publisher, developer, PEGI, rating, cover,
screenshots, YouTube trailers, game modes, themes, time to beat) for the game page and the filters. Each game is looked up once; new games each day.

    python -m pipeline.igdb                  # games not looked up yet (up to 300)
    python -m pipeline.igdb --limit 5000     # first fill
    python -m pipeline.igdb --videos         # trailers for games matched before videos were kept
    python -m pipeline.igdb --tags           # game modes / themes for games matched before they were kept
    python -m pipeline.igdb --time-to-beat   # time to beat (rushed / normal / 100%) of matched games
    python -m pipeline.igdb --names          # English names of games matched before they were kept

Credentials: a Twitch developer app, in the environment variables IGDB_CLIENT_ID and
IGDB_CLIENT_SECRET (never in the code). IGDB allows 4 requests per second; we stay under it.
"""
import argparse
import json
from collections import Counter
import logging
import os
import re
import sys
import time

import requests

from core.normalizer import normalize_name
from db import connection

log = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.igdb.com/v4/"
MIN_INTERVAL = 0.3          # seconds between requests (IGDB limit: 4 per second)
MIN_SCORE = 0.75            # how similar the names must be to accept a match
RETRY_UNMATCHED_DAYS = 30   # games IGDB didn't have may be added later (also: time to beat not known yet)

# Our platform codes → IGDB platform ids
IGDB_PLATFORMS = {"PS5": 167, "PS4": 48, "PS3": 9, "Switch": 130, "Switch2": 508,
                  "XboxSeries": 169, "XboxOne": 49, "PC": 6,
                  # older platforms (checked against IGDB's platforms, 2026-10-03)
                  "Xbox360": 12, "WiiU": 41, "Wii": 5, "3DS": 37, "DS": 20, "PSVita": 46, "PSP": 38, "PS2": 8,
                  "PS1": 7, "Xbox": 11, "GameCube": 21, "N64": 4, "GBA": 24, "GBC": 22, "GB": 33, "SNES": 19,
                  "NES": 18, "Dreamcast": 23, "Saturn": 32, "MegaDrive": 29, "MasterSystem": 64}

# IGDB game_type: 1 DLC, 5 mod, 13 pack, 14 update — not the game itself
NOT_A_GAME = {1, 5, 13, 14}
# 2 expansion, 6 episode, 7 season, and a bundle joining games ("The Witcher 3: Wild Hunt + Dark Souls III"):
# stores do sell these on a disc ("The Elder Scrolls Online: Elsweyr", "Dragon Quest I & II HD-2D
# Remake"), but they're only our game when every word of their name is in our title — not "Dark Souls
# III" → that bundle, "The Division 2" → "The Division 2: Mutiny", "Syberia 2" → "Syberia 1 & 2".
# (IGDB also files compilations like "Rayman: 30th Anniversary Edition" as bundles: scored as usual.)
PARTS = {2, 6, 7}
BUNDLE = 3
JOINED_GAMES = re.compile(r"[+&/]|\bvs\b", re.IGNORECASE)
NOT_THE_GAMES_NAME = NOT_A_GAME | PARTS | {BUNDLE}
# Words about the packaging, not another game: allowed in such a name besides ours ("Class of Heroes
# 1 & 2 Complete Edition", "Far Cry 4 + Far Cry: Primal Bundle", "Kingdom Hearts HD 1.5 + 2.5 Remix")
PACKAGING_WORDS = {"edition", "complete", "deluxe", "digital", "bundle", "pack", "double", "twin", "collection",
                   "legacy", "hd", "the", "remastered"}


def is_all_ours(game_key, igdb_name):
    """Every word of IGDB's name is in our title (as often as it is there), besides packaging words:
    "Blasphemous + Blasphemous 2 Bundle" isn't "blasphemous 2" (one Blasphemous too many)."""
    extra = Counter(normalize_name(igdb_name).split()) - Counter(game_key.split())
    return all(word in PACKAGING_WORDS for word in extra)
# A store title in Portuguese: letters / words English titles don't have (after normalize_name)
PORTUGUESE = re.compile(r"[ãõç]", re.IGNORECASE)
PORTUGUESE_WORDS = {"parte", "edicao", "versao", "colecao", "fim", "ladrao", "remasterizado", "remasterizada", "um",
                    "uma", "dos", "das", "jogo", "aventura", "aventuras", "lenda", "expansao"}

FIELDS = ("name,version_parent.name,game_type,first_release_date,summary,genres.name,"
          "involved_companies.company.name,involved_companies.publisher,involved_companies.developer,"
          "age_ratings.rating_category.rating,age_ratings.organization.name,"
          "cover.image_id,screenshots.image_id,videos.video_id,videos.name,total_rating,game_modes.name,themes.name")
MAX_VIDEOS = 6
BATCH = 500                 # games per request when filling columns by IGDB id (IGDB's maximum)


def credentials():
    """From the environment; on Windows also from the user's saved variables (new shells pick them up)."""
    cid, secret = os.environ.get("IGDB_CLIENT_ID"), os.environ.get("IGDB_CLIENT_SECRET")
    if (not cid or not secret) and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                cid = cid or winreg.QueryValueEx(key, "IGDB_CLIENT_ID")[0]
                secret = secret or winreg.QueryValueEx(key, "IGDB_CLIENT_SECRET")[0]
        except OSError:
            pass
    if not cid or not secret:
        raise RuntimeError("IGDB_CLIENT_ID / IGDB_CLIENT_SECRET are not set")
    return cid, secret


class IGDBClient:
    def __init__(self):
        self.client_id, secret = credentials()
        response = requests.post(TOKEN_URL, params={
            "client_id": self.client_id, "client_secret": secret, "grant_type": "client_credentials"}, timeout=30)
        response.raise_for_status()
        self.token = response.json()["access_token"]
        self.session = requests.Session()
        self.session.headers.update({"Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"})
        self._last = 0.0

    def query(self, body, endpoint="games"):
        for attempt in range(3):
            wait = MIN_INTERVAL - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            response = self.session.post(API_URL + endpoint, data=body.encode("utf-8"), timeout=30)
            if response.status_code == 429:      # too fast: back off and try again
                time.sleep(2 ** attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("IGDB kept answering 429")

    def search(self, title, platform_code):
        """
        IGDB results for a game, trying a few versions of the title until one finds something:
        "Fallout 4 GOTY: 25th Anniversary" → also "Fallout 4 GOTY"; "Formula One - F1 23" → also "F1 23".
        """
        platform = IGDB_PLATFORMS.get(platform_code)
        where = f" where platforms = ({platform});" if platform else ""
        for query in title_variants(title):
            results = self.query(f'search "{query}"; fields {FIELDS};{where} limit 10;')
            if results:
                return results
        return []


def title_variants(title):
    title = title.replace('"', "").strip()
    variants = [title]
    if ":" in title:
        variants.append(title.split(":")[0])
    if " - " in title:
        variants += [title.split(" - ")[-1], title.split(" - ")[0]]
    variants.append(" ".join(normalize_name(title).split()))
    return [v.strip() for v in dict.fromkeys(variants) if len(v.strip()) >= 3]


def name_score(game_key, candidate_name):
    """
    How similar two names are (0-1), on the same normalized words we match stores with.
    One name fully inside the other also counts ("rayman 30 th" in "rayman 30 th anniversary
    edition"), if the shorter one is specific enough: 3+ words, or 2 with a number ("fallout 4").
    """
    a, b = set(game_key.split()), set(normalize_name(candidate_name).split())
    if not a or not b:
        return 0.0
    score = len(a & b) / len(a | b)
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    specific = len(shorter) >= 3 or (len(shorter) == 2 and any(w.isdigit() for w in shorter))
    if specific and shorter <= longer:
        score = max(score, 0.8)
    return score


def best_match(game_key, results):
    """The IGDB game for our game, or None. Prefers the main game over its editions and DLC."""
    best, best_score = None, 0.0
    for g in results:
        if g.get("game_type") in NOT_A_GAME:
            continue
        part = g.get("game_type") in PARTS or (g.get("game_type") == BUNDLE and JOINED_GAMES.search(g["name"]))
        if part and not is_all_ours(game_key, g["name"]):
            continue
        score = name_score(game_key, g["name"])
        if g.get("version_parent"):
            score -= 0.05        # "X: Deluxe Edition" — we want X
        if score > best_score:
            best, best_score = g, score
    return best if best_score >= MIN_SCORE else None


# The games columns filled from IGDB (game_info() gives a value for each)
IGDB_COLUMNS = ("igdb_id", "summary", "genres", "publishers", "developers", "first_release_date", "rating",
                "pegi", "cover_image_id", "screenshot_ids", "video_ids", "game_modes", "themes")


def game_info(g):
    """{column: value} for IGDB_COLUMNS, from an IGDB game."""
    companies = g.get("involved_companies", [])
    names = lambda role: ", ".join(dict.fromkeys(c["company"]["name"] for c in companies if c.get(role))) or None
    pegi = next((a.get("rating_category", {}).get("rating") for a in g.get("age_ratings", [])
                 if a.get("organization", {}).get("name") == "PEGI"), None)
    released = g.get("first_release_date")
    return {
        "igdb_id": g["id"],
        "summary": g.get("summary"),
        "genres": ", ".join(x["name"] for x in g.get("genres", [])) or None,
        "publishers": names("publisher"),
        "developers": names("developer"),
        "first_release_date": time.strftime("%Y-%m-%d", time.gmtime(released)) if released else None,
        "rating": round(g["total_rating"]) if g.get("total_rating") else None,
        "pegi": pegi,
        "cover_image_id": (g.get("cover") or {}).get("image_id"),
        "screenshot_ids": json.dumps([s["image_id"] for s in g.get("screenshots", [])][:12]) or None,
        "video_ids": video_list(g),
        **tag_lists(g),
    }


def english_name(g):
    """
    IGDB's name for the game, shown when the page is in English: for an edition IGDB matched
    ("Batman: Arkham Knight - Special Edition Steelbook") its main game's name; "" for a bundle,
    DLC or episode matched instead of the game (the store's title is shown then).
    """
    parent = g.get("version_parent")
    if isinstance(parent, dict) and parent.get("name"):
        return parent["name"]
    if g.get("game_type") in NOT_THE_GAMES_NAME:
        return ""
    return g.get("name") or ""


def tag_lists(g):
    """{game_modes, themes}: IGDB names, comma-separated; "" when IGDB lists none (looked up)."""
    return {key: ", ".join(x["name"] for x in g.get(key, []) if x.get("name")) for key in ("game_modes", "themes")}


def video_list(g):
    """
    YouTube videos of an IGDB game as JSON [{"id", "name"}], trailers first
    ("Announcement Trailer", "Launch Trailer"), then gameplay and the rest. "[]" when there are none.
    """
    videos = [{"id": v["video_id"], "name": v.get("name") or ""} for v in g.get("videos", []) if v.get("video_id")]
    videos.sort(key=lambda v: "trailer" not in v["name"].lower())
    return json.dumps(videos[:MAX_VIDEOS])


def enrich_games(limit=300):
    """Look up games never looked up (or unmatched for a while), those on sale first."""
    client = IGDBClient()
    with connection() as conn:
        cursor = conn.cursor()
        games = cursor.execute(
            f"""
            SELECT g.id, g.title, g.normalized_title, p.code, g.title_fixed
            FROM games g JOIN platforms p ON p.id = g.platform_id
            WHERE g.igdb_checked_at IS NULL
               OR (g.igdb_id IS NULL AND g.igdb_checked_at < utcnow() + make_interval(days => ?))
            ORDER BY CASE WHEN EXISTS (SELECT 1 FROM store_products sp WHERE sp.game_id = g.id AND sp.is_active)
                          THEN 0 ELSE 1 END, g.id DESC
            LIMIT {int(limit)}
            """,
            -RETRY_UNMATCHED_DAYS,
        ).fetchall()

        matched = 0
        for game_id, title, game_key, platform, title_fixed in games:
            if title_fixed:              # a moderator's spelling, not the store's typo in the key
                game_key = normalize_name(title)
            try:
                g = best_match(game_key, client.search(title, platform))
            except requests.RequestException as e:
                log.warning("IGDB lookup of %s failed: %s", title, e)
                continue

            if g:
                info = game_info(g)
                cursor.execute(
                    f"UPDATE games SET {', '.join(f'{c} = ?' for c in IGDB_COLUMNS)}, "
                    "igdb_checked_at = utcnow() WHERE id = ?",
                    *(info[c] for c in IGDB_COLUMNS), game_id,
                )
                matched += 1
            else:
                cursor.execute("UPDATE games SET igdb_checked_at = utcnow() WHERE id = ?", game_id)
            conn.commit()   # each game as it's looked up: an interrupted fill keeps its work

    log.info("IGDB: %d games looked up, %d matched", len(games), matched)
    return len(games), matched


def fill_missing(column, fields, values, client=None):
    """
    For games matched before `column` was kept (still NULL): ask IGDB by id, 500 games per
    request, for `fields`, and set the columns values(igdb game) gives. A game IGDB no longer
    returns gets the "none" value too, so it isn't asked again every day. Nothing to do once
    every matched game has it.
    """
    with connection() as conn:
        cursor = conn.cursor()
        ids = [r[0] for r in cursor.execute(
            f"SELECT DISTINCT igdb_id FROM games WHERE igdb_id IS NOT NULL AND {column} IS NULL").fetchall()]
        if not ids:
            return 0
        client = client or IGDBClient()
        for start in range(0, len(ids), BATCH):
            batch = ids[start:start + BATCH]
            found = {g["id"]: g for g in client.query(
                f"fields id,{fields}; where id = ({','.join(map(str, batch))}); limit {BATCH};")}
            for igdb_id in batch:
                update = values(found.get(igdb_id, {}))
                cursor.execute(f"UPDATE games SET {', '.join(f'{c} = ?' for c in update)} WHERE igdb_id = ?",
                               *update.values(), igdb_id)
            conn.commit()
    log.info("IGDB: %s filled for %d games", column, len(ids))
    return len(ids)


def fill_videos(client=None):
    """Videos for games matched before videos were kept."""
    return fill_missing("video_ids", "videos.video_id,videos.name", lambda g: {"video_ids": video_list(g)}, client)


def fill_tags(client=None):
    """Game modes and themes for games matched before they were kept."""
    return fill_missing("game_modes", "game_modes.name,themes.name", tag_lists, client)


def english_title(title, igdb_name):
    """
    The English name shown for a game: IGDB's when the store's title is Portuguese ("The Last of Us
    Parte II" → "The Last of Us Part II") or is the same words written worse ("DEADLY PREMONITION 2");
    else "" and the store's title is shown (IGDB's would often be a longer edition's name).
    """
    if not igdb_name:
        return ""
    if normalize_name(igdb_name) == normalize_name(title) or PORTUGUESE.search(title) \
            or set(normalize_name(title).split()) & PORTUGUESE_WORDS:
        return igdb_name
    return ""


def fill_names(client=None):
    """
    English names for matched games that don't have one yet (new games each day): looked up by
    IGDB id, 500 per request. "" when there's none to show; a moderator's name is never replaced.
    """
    with connection() as conn:
        cursor = conn.cursor()
        games = cursor.execute("SELECT id, title, igdb_id FROM games WHERE igdb_id IS NOT NULL AND title_en IS NULL").fetchall()
        if not games:
            return 0
        client = client or IGDBClient()
        ids = sorted({igdb_id for _, _, igdb_id in games})
        names = {}
        for start in range(0, len(ids), BATCH):
            batch = ids[start:start + BATCH]
            names.update({g["id"]: english_name(g) for g in client.query(
                f"fields id,name,game_type,version_parent.name; where id = ({','.join(map(str, batch))}); limit {BATCH};")})
        for game_id, title, igdb_id in games:
            cursor.execute("UPDATE games SET title_en = ? WHERE id = ?", english_title(title, names.get(igdb_id)), game_id)
        conn.commit()
    log.info("IGDB: English names looked up for %d games", len(games))
    return len(games)


def fill_time_to_beat(client=None):
    """
    Time to beat from IGDB's players (seconds to finish rushing / normally / 100%) for matched
    games not looked up yet, or looked up 30+ days ago without times. 500 games per request;
    a game IGDB has no times for is marked checked (ttb_checked_at) with empty times.
    """
    with connection() as conn:
        cursor = conn.cursor()
        ids = [r[0] for r in cursor.execute(
            "SELECT DISTINCT igdb_id FROM games WHERE igdb_id IS NOT NULL AND (ttb_checked_at IS NULL "
            "OR (ttb_normally IS NULL AND ttb_checked_at < utcnow() + make_interval(days => ?)))",
            -RETRY_UNMATCHED_DAYS).fetchall()]
        if not ids:
            return 0
        client = client or IGDBClient()
        found = 0
        for start in range(0, len(ids), BATCH):
            batch = ids[start:start + BATCH]
            times = {t["game_id"]: t for t in client.query(
                f"fields game_id,hastily,normally,completely,count; where game_id = ({','.join(map(str, batch))}); "
                f"limit {BATCH};", endpoint="game_time_to_beats")}
            for igdb_id in batch:
                t = times.get(igdb_id, {})
                found += bool(t)
                cursor.execute(
                    "UPDATE games SET ttb_hastily = ?, ttb_normally = ?, ttb_completely = ?, ttb_count = ?, "
                    "ttb_checked_at = utcnow() WHERE igdb_id = ?",
                    t.get("hastily"), t.get("normally"), t.get("completely"), t.get("count"), igdb_id)
            conn.commit()
    log.info("IGDB: time to beat looked up for %d games, %d have times", len(ids), found)
    return len(ids)


if __name__ == "__main__":
    from scheduler.jobs import setup_logging

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--videos", action="store_true", help="only fill videos of games already matched")
    parser.add_argument("--tags", action="store_true", help="only fill game modes / themes of games already matched")
    parser.add_argument("--time-to-beat", action="store_true", help="only fill the time to beat of matched games")
    parser.add_argument("--names", action="store_true", help="only fill the English names of matched games")
    args = parser.parse_args()
    setup_logging()
    if args.names:
        fill_names()
    elif args.videos:
        fill_videos()
    elif args.tags:
        fill_tags()
    elif args.time_to_beat:
        fill_time_to_beat()
    else:
        enrich_games(args.limit)
