"""
Scrape one store into the database (useful while writing a new scraper).

    python -m scheduler.run_single_store press_start
"""
import sys

from scheduler.jobs import SCRAPERS, run_store, setup_logging


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in SCRAPERS:
        print(f"Usage: python -m scheduler.run_single_store <{'|'.join(SCRAPERS)}>")
        sys.exit(2)

    setup_logging()

    try:
        run_store(sys.argv[1])
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
