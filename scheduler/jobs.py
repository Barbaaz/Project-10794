import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from db import get_connection
from pipeline.process_scraped_data import process_products
from scrapers.cstech.scraper import CSTechScraper
from scrapers.mega_mania.scraper import MegaManiaScraper
from scrapers.press_start.scraper import PressStartScraper

log = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# To add a store: write its scraper, register it here and add it to database/seed_stores.sql
SCRAPERS = {
    "press_start": PressStartScraper,
    "mega-mania": MegaManiaScraper,
    "cstech": CSTechScraper,
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
    conn = get_connection()
    try:
        rows = conn.cursor().execute("SELECT slug FROM stores WHERE is_active = 1 ORDER BY id").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def run_store(slug):
    """Scrape one store's catalogue into the database, logging the run in scrape_runs."""
    if slug not in SCRAPERS:
        raise ValueError(f"No scraper registered for '{slug}'. Known: {', '.join(SCRAPERS)}")

    run_id = start_run(slug)

    try:
        products = SCRAPERS[slug]().scrape_catalog()
        if not products:
            raise RuntimeError("Scraper returned 0 products, the site's HTML may have changed")

        stats = process_products(slug, products)
        finish_run(run_id, "success", products_found=len(products))
        log.info("[%s] done: %s", slug, stats)
        return stats

    except Exception as e:
        log.exception("[%s] failed", slug)
        finish_run(run_id, "failed", error_message=str(e))
        raise


def start_run(slug):
    conn = get_connection()
    try:
        run_id = conn.cursor().execute(
            "INSERT INTO scrape_runs (store_id) OUTPUT INSERTED.id "
            "SELECT id FROM stores WHERE slug = ?",
            slug,
        ).fetchone()
        if not run_id:
            raise ValueError(f"Store '{slug}' is not in the stores table (see database/seed_stores.sql)")
        conn.commit()
        return run_id[0]
    finally:
        conn.close()


def finish_run(run_id, status, products_found=None, error_message=None):
    conn = get_connection()
    try:
        conn.cursor().execute(
            "UPDATE scrape_runs SET finished_at = SYSUTCDATETIME(), status = ?, "
            "products_found = ?, error_message = ? WHERE id = ?",
            status, products_found, error_message, run_id,
        )
        conn.commit()
    finally:
        conn.close()
