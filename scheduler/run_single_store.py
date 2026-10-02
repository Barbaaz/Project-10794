"""
Scrape one store into the database (useful while writing a new scraper).

    python -m scheduler.run_single_store press_start
    python -m scheduler.run_single_store press_start --force
    python -m scheduler.run_single_store press_start --accept-drop

--force: run even if the store was scraped successfully less than 12 hours ago
         (the limit exists so repeated runs don't flood the store with requests).
--accept-drop: the store really has far fewer products than last time (not a broken
               scraper), so deactivate the products that are gone. See MIN_PRODUCT_RATIO in jobs.py.
"""
import sys

from scheduler.jobs import SCRAPERS, RanRecently, run_store, setup_logging

FLAGS = {"--force", "--accept-drop"}


def main():
    args = sys.argv[1:]
    stores = [a for a in args if a not in FLAGS]

    if len(stores) != 1 or stores[0] not in SCRAPERS:
        print(f"Usage: python -m scheduler.run_single_store <{'|'.join(SCRAPERS)}> [--force] [--accept-drop]")
        sys.exit(2)

    setup_logging()

    try:
        run_store(stores[0], accept_drop="--accept-drop" in args, force="--force" in args)
    except RanRecently as e:
        print(e)
        sys.exit(3)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
