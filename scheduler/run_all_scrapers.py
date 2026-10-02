"""
Scrape every active store into the database.

    python -m scheduler.run_all_scrapers

Runs daily via the Windows task set up by scheduler/register_daily_task.ps1.
A store scraped successfully less than 12 hours ago is skipped (see MIN_HOURS_BETWEEN_RUNS).
"""
import logging
import sys

from scheduler.jobs import SCRAPERS, RanRecently, active_store_slugs, run_store, setup_logging

log = logging.getLogger(__name__)


def main():
    setup_logging()
    failed = []

    for slug in active_store_slugs():
        if slug not in SCRAPERS:
            log.warning("[%s] active in the database but has no scraper, skipped", slug)
            continue

        # One store failing must not stop the others
        try:
            run_store(slug)
        except RanRecently as e:
            log.info("%s, skipped", e)
        except Exception:
            failed.append(slug)

    if failed:
        log.error("Failed stores: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
