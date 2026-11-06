---
status: accepted
---

# A run with under 70% of the last run's products deactivates nothing

A store's run normally marks every product it didn't see as gone. When a run finds fewer than 70% of the products of the store's last successful run (`MIN_PRODUCT_RATIO` in `scheduler/jobs.py`), the prices it found are saved, nothing is marked gone, and the run ends as a warning. A run that finds no products fails. (Since 2026-10-02.)

A change to a store's HTML usually breaks a scraper partly, so it still returns some products. Marking the rest as gone would take those games off the site, and out of their price history, until someone noticed.

## Consequences

- When a store really did shrink, someone accepts it by hand: `python -m scheduler.run_single_store <store> --accept-drop`. See [When a store's run fails or warns](../how-to/store-run-problems.md).
- Techinn is read in part on each run, so it marks gone only the products that left its sitemap.
