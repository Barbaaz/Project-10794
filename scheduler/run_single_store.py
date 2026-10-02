"""
Scrape one store into the database (useful while writing a new scraper).

    python -m scheduler.run_single_store press_start
    python -m scheduler.run_single_store press_start --accept-drop

--accept-drop: the store really has far fewer products than last time (not a broken
scraper), so deactivate the products that are gone. See MIN_PRODUCT_RATIO in jobs.py.
"""
import sys

from scheduler.jobs import SCRAPERS, run_store, setup_logging


def main():
    args = sys.argv[1:]
    accept_drop = "--accept-drop" in args
    stores = [a for a in args if a != "--accept-drop"]

    if len(stores) != 1 or stores[0] not in SCRAPERS:
        print(f"Usage: python -m scheduler.run_single_store <{'|'.join(SCRAPERS)}> [--accept-drop]")
        sys.exit(2)

    setup_logging()

    try:
        run_store(stores[0], accept_drop=accept_drop)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
