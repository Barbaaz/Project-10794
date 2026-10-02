"""
Scrape every active store into the database.

    python -m scheduler.run_all_scrapers

Runs daily via the Windows task set up by scheduler/register_daily_task.ps1.
A store scraped successfully less than 12 hours ago is skipped (see MIN_HOURS_BETWEEN_RUNS).
"""
import logging
import sys

from scheduler.jobs import SCRAPERS, RanRecently, active_store_slugs, run_store, setup_logging
from scheduler.notify import notify, run_summary
from pipeline.igdb import enrich_games, fill_videos

log = logging.getLogger(__name__)


def main():
    setup_logging()
    failed, warnings = [], []

    for slug in active_store_slugs():
        if slug not in SCRAPERS:
            log.warning("[%s] active in the database but has no scraper, skipped", slug)
            continue

        # One store failing must not stop the others
        try:
            stats = run_store(slug)
            if stats.get("status") == "warning":
                warnings.append(slug)
        except RanRecently as e:
            log.info("%s, skipped", e)
        except Exception:
            failed.append(slug)

    # Game information for games added today (IGDB); never blocks the run
    try:
        enrich_games(limit=300)
        fill_videos()
    except Exception as e:
        log.warning("IGDB lookup skipped: %s", e)

    # Tell the user on their desktop, so a broken store doesn't go unnoticed
    summary = run_summary(failed, warnings)
    if summary:
        notify(*summary)

    if failed:
        log.error("Failed stores: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
