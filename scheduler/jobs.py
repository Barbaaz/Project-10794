import logging
import sys
from collections import Counter
from contextlib import contextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import db
from db import connection
from pipeline.process_scraped_data import process_products
from scrapers.cstech.scraper import CSTechScraper
from scrapers.gaming_replay.scraper import GamingReplayScraper
from scrapers.mega_mania.scraper import MegaManiaScraper
from scrapers.press_start.scraper import PressStartScraper
from scrapers.radio_popular.scraper import RadioPopularScraper
from scrapers.techinn.scraper import TechinnScraper

log = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# A run finding less than this share of the last successful run's products is suspicious
MIN_PRODUCT_RATIO = 0.7

# Release dates that need a product page (Press Start) are re-read after this many days
RELEASE_DATE_RECHECK_DAYS = 7

# A store isn't scraped again this soon after a successful run (unless forced), so repeated
# manual runs don't flood it with requests. The schedule (06:00 and 18:00) is above this.
MIN_HOURS_BETWEEN_RUNS = 8

# The evening run (run_all_scrapers --light): these stores again, listing pages only (prices and
# stock; no product pages), so prices are at most ~12 h old. CSTech stays once a day: it has
# answered "too many requests" before; Rádio Popular too (match-only, few of its products link).
LIGHT_STORES = ("press_start", "mega-mania", "gaming_replay")

# Stores whose consoles are read too (core/hardware.py; user, 2026-10-07: consoles only):
# a store is added once a check run's kept / left-out names were read (these three: 2026-10-07).
# Not yet: CSTech (its feed has them, product_type not "Jogos …"), Techinn, Rádio Popular (match-only)
HARDWARE_STORES = {"press_start", "mega-mania", "gaming_replay"}

# To add a store: write its scraper, register it here and add it to database/seed_stores.sql
SCRAPERS = {
    "press_start": PressStartScraper,
    "mega-mania": MegaManiaScraper,
    "cstech": CSTechScraper,
    "radio_popular": RadioPopularScraper,
    "gaming_replay": GamingReplayScraper,
    "techinn": TechinnScraper,
}


def setup_logging():
    # Scheduled runs have no console, so also keep a log file (last 30 days)
    LOG_DIR.mkdir(exist_ok=True)
    handlers = [TimedRotatingFileHandler(LOG_DIR / "scraper.log", when="midnight", backupCount=30, encoding="utf-8")]

    # sys.stdout is None under pythonw.exe (used by the scheduled task)
    if sys.stdout is not None:
        # Product names have characters the Windows console can't print
        sys.stdout.reconfigure(errors="replace")
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def active_store_slugs():
    with connection() as conn:
        rows = conn.cursor().execute("SELECT slug FROM stores WHERE is_active ORDER BY id").fetchall()
    return [r[0] for r in rows]


class RanRecently(Exception):
    """The store was scraped successfully less than MIN_HOURS_BETWEEN_RUNS ago."""


def run_store(slug, accept_drop=False, force=False, light=False):
    """
    Scrape one store's catalogue into the database, logging the run in scrape_runs.
    accept_drop=True: the store really has fewer products now; deactivate the missing ones.
    force=True: run even if the store was scraped less than MIN_HOURS_BETWEEN_RUNS ago.
    light=True: listing pages only (no product pages for descriptions / release dates).
    """
    if slug not in SCRAPERS:
        raise ValueError(f"No scraper registered for '{slug}'. Known: {', '.join(SCRAPERS)}")

    with store_lock(slug):
        return scrape_store(slug, accept_drop, force, light)


@contextmanager
def store_lock(slug):
    """
    One run of a store at a time, across processes. A PC switched on after 18:00 starts the missed
    morning task and the evening one together (10-06, 10-07): both read Gaming Replay, Mega Mania
    and Press Start at once. The second now waits here, then the MIN_HOURS_BETWEEN_RUNS check skips it.
    """
    conn = db.connect(db.DB_CONNECTION_STRING, autocommit=True)
    try:
        cursor = conn.cursor()
        key = f"scrape_store:{slug}"
        if not cursor.execute("SELECT pg_try_advisory_lock(hashtext(?))", key).fetchone()[0]:
            log.info("[%s] another run is scraping it; waiting for it to finish", slug)
            cursor.execute("SELECT pg_advisory_lock(hashtext(?))", key)
        yield
    finally:
        conn.close()        # closing the session releases the lock


def scrape_store(slug, accept_drop, force, light):
    """run_store's work, with the store's lock held."""
    hours = hours_since_last_success(slug)
    if not force and hours is not None and hours < MIN_HOURS_BETWEEN_RUNS:
        raise RanRecently(f"[{slug}] last successful run {hours:.1f} h ago (minimum {MIN_HOURS_BETWEEN_RUNS} h); "
                          f"use --force to run anyway")

    run_id = start_run(slug)

    try:
        scraper = SCRAPERS[slug](fresh_release_urls=fresh_release_urls(slug), known_detail_urls=known_detail_urls(slug),
                                 last_seen=last_seen(slug))
        if light:
            scraper.max_product_pages = 0
        scraper.read_hardware = slug in HARDWARE_STORES
        products = scraper.scrape_catalog()
        log.info("[%s] %d requests", slug, scraper.http.request_count)
        if scraper.read_hardware:
            kinds = Counter(p.get("kind", "game") for p in products)
            log.info("[%s] hardware: %s; %d left out", slug, dict(kinds), len(scraper.hardware_left_out))
        elif getattr(scraper, "hardware_preview", None) is not None:
            write_hardware_check(slug, scraper.hardware_preview, scraper.hardware_left_out)
        if not products:
            raise RuntimeError("Scraper returned 0 products, the site's HTML may have changed")

        previous = previous_product_count(slug)
        suspicious = not accept_drop and is_suspicious_drop(len(products), previous)

        # A half-broken scraper (e.g. prices no longer found) returns only part of the
        # catalogue. Prices are still saved, but nothing is deactivated until someone checks.
        # A store read in part each run (Techinn) says which products it still lists
        stats = process_products(slug, products, full_catalog=not suspicious,
                                   still_listed=getattr(scraper, "still_listed", None))

        if suspicious:
            message = (
                f"Only {len(products)} products, last successful run had {previous}. "
                f"Missing products were NOT deactivated; the site may have changed. "
                f"If the store really shrank: python -m scheduler.run_single_store {slug} --accept-drop"
            )
            finish_run(run_id, "warning", products_found=len(products), error_message=message)
            log.warning("[%s] %s", slug, message)
        else:
            finish_run(run_id, "success", products_found=len(products))

        stats["status"] = "warning" if suspicious else "success"
        log.info("[%s] done: %s", slug, stats)
        return stats

    except Exception as e:
        log.exception("[%s] failed", slug)
        finish_run(run_id, "failed", error_message=str(e))
        raise


def write_hardware_check(slug, kept, left_out):
    """What a store not in HARDWARE_STORES would keep and leave out, to read before switching it on."""
    path = LOG_DIR / f"hardware_check_{slug}.txt"
    lines = [f"{p['kind']:10} {p['console']:10} {p['condition']:4} {p['price']} | {p['external_name']}"
             for p in sorted(kept, key=lambda p: (p["kind"], p["console"], p["external_name"]))]
    path.write_text("\n".join([f"KEPT ({len(kept)})", *lines, "", f"LEFT OUT ({len(left_out)})", *sorted(set(left_out))]),
                    encoding="utf-8")
    log.info("[%s] hardware check (not saved): %d kept, %d left out → %s", slug, len(kept), len(left_out), path.name)


def is_suspicious_drop(found, previous, min_ratio=MIN_PRODUCT_RATIO):
    """True when a run found much less than the last successful one (no history = not suspicious)."""
    return bool(previous) and found < previous * min_ratio


def previous_product_count(slug):
    """products_found of the store's last successful run ('warning' runs don't count)."""
    with connection() as conn:
        row = conn.cursor().execute(
            "SELECT r.products_found FROM scrape_runs r JOIN stores s ON s.id = r.store_id "
            "WHERE s.slug = ? AND r.status = 'success' ORDER BY r.id DESC LIMIT 1",
            slug,
        ).fetchone()
    return row[0] if row else None


def hours_since_last_success(slug):
    with connection() as conn:
        row = conn.cursor().execute(
            "SELECT EXTRACT(EPOCH FROM utcnow() - MAX(r.finished_at)) / 3600 "
            "FROM scrape_runs r JOIN stores s ON s.id = r.store_id "
            "WHERE s.slug = ? AND r.status IN ('success', 'warning')",
            slug,
        ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def fresh_release_urls(slug):
    """Pre-orders whose release date was read in the last RELEASE_DATE_RECHECK_DAYS days."""
    return store_urls(slug, "sp.release_date_checked_at > utcnow() + make_interval(days => ?)",
                      -RELEASE_DATE_RECHECK_DAYS)


def last_seen(slug):
    """{url: when a run last saw it}: a store reading part of its catalogue per run (Techinn) reads the oldest first."""
    with connection() as conn:
        rows = conn.cursor().execute(
            "SELECT sp.url, MAX(sp.last_seen_at) FROM store_products sp JOIN stores s ON s.id = sp.store_id "
            "WHERE s.slug = ? GROUP BY sp.url", slug).fetchall()
    return {url: seen for url, seen in rows}


def known_detail_urls(slug):
    """Products whose product page (description) was already read; read once."""
    return store_urls(slug, "sp.details_checked_at IS NOT NULL")


def store_urls(slug, condition, *params):
    """The URLs of a store's products matching `condition` (SQL on store_products sp)."""
    with connection() as conn:
        rows = conn.cursor().execute(
            "SELECT sp.url FROM store_products sp JOIN stores s ON s.id = sp.store_id "
            f"WHERE s.slug = ? AND {condition}",
            slug, *params,
        ).fetchall()
    return {r[0] for r in rows}


def start_run(slug):
    with connection() as conn:
        run_id = conn.cursor().execute(
            "INSERT INTO scrape_runs (store_id) SELECT id FROM stores WHERE slug = ? RETURNING id",
            slug,
        ).fetchone()
    if not run_id:
        raise ValueError(f"Store '{slug}' is not in the stores table (see database/seed_stores.sql)")
    return run_id[0]


def finish_run(run_id, status, products_found=None, error_message=None):
    with connection() as conn:
        conn.cursor().execute(
            "UPDATE scrape_runs SET finished_at = utcnow(), status = ?, "
            "products_found = ?, error_message = ? WHERE id = ?",
            status, products_found, error_message, run_id,
        )
