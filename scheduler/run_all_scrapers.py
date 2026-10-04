"""
Scrape every active store into the database.

    python -m scheduler.run_all_scrapers            # the morning run: every store, then IGDB
    python -m scheduler.run_all_scrapers --light    # the evening run: LIGHT_STORES, listing pages only

Runs daily via the Windows task set up by scheduler/register_daily_task.ps1.
A store scraped successfully less than 12 hours ago is skipped (see MIN_HOURS_BETWEEN_RUNS).
"""
import logging
import sys

from scheduler.jobs import LIGHT_STORES, SCRAPERS, RanRecently, active_store_slugs, run_store, setup_logging
from scheduler.notify import notify, run_summary
from pipeline.igdb import enrich_games, fill_names, fill_tags, fill_time_to_beat, fill_videos
from app.services.chat_service import complete_overdue
from app.services.wish_alert_service import check_all as wish_alerts

log = logging.getLogger(__name__)


def main(light=False):
    setup_logging()
    failed, warnings = [], []

    for slug in active_store_slugs():
        if light and slug not in LIGHT_STORES:
            continue
        if slug not in SCRAPERS:
            log.warning("[%s] active in the database but has no scraper, skipped", slug)
            continue

        # One store failing must not stop the others
        try:
            stats = run_store(slug, light=light)
            if stats.get("status") == "warning":
                warnings.append(slug)
        except RanRecently as e:
            log.info("%s, skipped", e)
        except Exception:
            failed.append(slug)

    # Game information for games added today (IGDB); never blocks the run. Morning run only
    if not light:
        try:
            enrich_games(limit=300)
            fill_videos()
            fill_tags()
            fill_names()
            fill_time_to_beat()
        except Exception as e:
            log.warning("IGDB lookup skipped: %s", e)

    # Marketplace: purchases sent 7 days ago without a problem reported are completed
    # (also done whenever someone opens their messages; this covers quiet days)
    try:
        completed = complete_overdue()
        if completed:
            log.info("Marketplace: %d purchases completed after 7 days", completed)
    except Exception as e:
        log.warning("Marketplace auto-complete skipped: %s", e)

    # Wishlist alerts by e-mail (back in stock, price drops), after the morning run's new prices:
    # at most one message a day per user
    if not light:
        try:
            log.info("Wishlist alerts: %s", wish_alerts())
        except Exception as e:
            log.warning("Wishlist alerts skipped: %s", e)

    # Tell the user on their desktop, so a broken store doesn't go unnoticed
    summary = run_summary(failed, warnings)
    if summary:
        notify(*summary)

    if failed:
        log.error("Failed stores: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main(light="--light" in sys.argv[1:])
