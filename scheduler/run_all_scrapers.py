"""
Scrape every active store into the database.

    python -m scheduler.run_all_scrapers

Schedule it with Windows Task Scheduler (e.g. every 6 hours), with the
project folder as "Start in".
"""
import logging
import sys

from scheduler.jobs import SCRAPERS, active_store_slugs, run_store, setup_logging

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
        except Exception:
            failed.append(slug)

    if failed:
        log.error("Failed stores: %s", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
