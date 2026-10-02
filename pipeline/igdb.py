"""
Game information from IGDB (summary, genres, publisher, developer, PEGI, rating, cover,
screenshots) for the game page. Each game is looked up once; new games each day.

    python -m pipeline.igdb                  # games not looked up yet (up to 300)
    python -m pipeline.igdb --limit 5000     # first fill

Credentials: a Twitch developer app, in the environment variables IGDB_CLIENT_ID and
IGDB_CLIENT_SECRET (never in the code). IGDB allows 4 requests per second; we stay under it.
"""
import argparse
import json
import logging
import os
import sys
import time

import requests

from core.normalizer import normalize_name
from db import get_connection

log = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
MIN_INTERVAL = 0.3          # seconds between requests (IGDB limit: 4 per second)
MIN_SCORE = 0.75            # how similar the names must be to accept a match
RETRY_UNMATCHED_DAYS = 30   # games IGDB didn't have may be added later

# Our platform codes → IGDB platform ids
IGDB_PLATFORMS = {"PS5": 167, "PS4": 48, "PS3": 9, "Switch": 130, "Switch2": 508,
                  "XboxSeries": 169, "XboxOne": 49, "PC": 6}

# IGDB game_type: 1 DLC, 2 expansion, 5 mod, 13 pack, 14 update — not the game itself
NOT_A_GAME = {1, 5, 13, 14}

FIELDS = ("name,version_parent,game_type,first_release_date,summary,genres.name,"
          "involved_companies.company.name,involved_companies.publisher,involved_companies.developer,"
          "age_ratings.rating_category.rating,age_ratings.organization.name,"
          "cover.image_id,screenshots.image_id,total_rating")


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

    def query(self, body):
        for attempt in range(3):
            wait = MIN_INTERVAL - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            response = self.session.post(GAMES_URL, data=body.encode("utf-8"), timeout=30)
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
        score = name_score(game_key, g["name"])
        if g.get("version_parent"):
            score -= 0.05        # "X: Deluxe Edition" — we want X
        if score > best_score:
            best, best_score = g, score
    return best if best_score >= MIN_SCORE else None


def game_info(g):
    """The columns we store from an IGDB game."""
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
    }


def enrich_games(limit=300):
    """Look up games never looked up (or unmatched for a while), those on sale first."""
    client = IGDBClient()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        games = cursor.execute(
            f"""
            SELECT TOP ({int(limit)}) g.id, g.title, g.normalized_title, p.code
            FROM games g JOIN platforms p ON p.id = g.platform_id
            WHERE g.igdb_checked_at IS NULL
               OR (g.igdb_id IS NULL AND g.igdb_checked_at < DATEADD(DAY, ?, SYSUTCDATETIME()))
            ORDER BY CASE WHEN EXISTS (SELECT 1 FROM store_products sp WHERE sp.game_id = g.id AND sp.is_active = 1)
                          THEN 0 ELSE 1 END, g.id DESC
            """,
            -RETRY_UNMATCHED_DAYS,
        ).fetchall()

        matched = 0
        for game_id, title, game_key, platform in games:
            try:
                g = best_match(game_key, client.search(title, platform))
            except requests.RequestException as e:
                log.warning("IGDB lookup of %s failed: %s", title, e)
                continue

            if g:
                info = game_info(g)
                cursor.execute(
                    """UPDATE games SET igdb_id = ?, summary = ?, genres = ?, publishers = ?, developers = ?,
                       first_release_date = ?, rating = ?, pegi = ?, cover_image_id = ?, screenshot_ids = ?,
                       igdb_checked_at = SYSUTCDATETIME() WHERE id = ?""",
                    *info.values(), game_id,
                )
                matched += 1
            else:
                cursor.execute("UPDATE games SET igdb_checked_at = SYSUTCDATETIME() WHERE id = ?", game_id)
            conn.commit()

        log.info("IGDB: %d games looked up, %d matched", len(games), matched)
        return len(games), matched
    finally:
        conn.close()


if __name__ == "__main__":
    from scheduler.jobs import setup_logging

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=300)
    args = parser.parse_args()
    setup_logging()
    enrich_games(args.limit)
