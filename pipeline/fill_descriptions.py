"""
Read product pages for products that don't have a description yet, without a full scrape.
Special editions first. Uses the same polite HTTP client as the scrapers (throttled,
robots.txt, stops on 403/429). The daily run also does this, 100 pages per store.

    python -m pipeline.fill_descriptions press_start --limit 40
"""
import argparse
import logging

from core.editions import parse_title
from db import connection, json_or_none
from scheduler.jobs import SCRAPERS, setup_logging
from scrapers.base.http_client import RequestBudgetExceeded, StoreBlocked

log = logging.getLogger(__name__)


def fill_descriptions(slug, limit):
    scraper = SCRAPERS[slug]()
    if not scraper.reads_product_pages:
        log.info("[%s] descriptions come with the catalogue; nothing to do", slug)
        return 0

    with connection() as conn:
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT sp.id, sp.url, sp.external_name FROM store_products sp JOIN stores s ON s.id = sp.store_id "
            "WHERE s.slug = ? AND sp.is_active = 1 AND sp.details_checked_at IS NULL",
            slug,
        ).fetchall()
        rows.sort(key=lambda r: parse_title(r[2]).phrase == "")   # special editions first
        filled = 0

        for sp_id, url, name in rows[:limit]:
            try:
                page = scraper.fetch_product_page(url) or {}
            except (StoreBlocked, RequestBudgetExceeded):
                raise
            except Exception as e:
                log.warning("[%s] %s: %s", slug, url, e)
                continue
            cursor.execute(
                "UPDATE store_products SET description = ?, details = ?, image_urls = ?, "
                "details_checked_at = SYSUTCDATETIME() WHERE id = ?",
                page.get("description"), json_or_none(page.get("details")), json_or_none(page.get("images")), sp_id,
            )
            conn.commit()   # each page as it's read: a block halfway keeps what was read
            filled += 1
            log.info("[%s] %s: %s", slug, name[:60], "ok" if page.get("description") else "no description")

    log.info("[%s] %d product pages read, %d still without description", slug, filled, len(rows) - filled)
    return filled


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("store", choices=list(SCRAPERS))
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    setup_logging()
    fill_descriptions(args.store, args.limit)
