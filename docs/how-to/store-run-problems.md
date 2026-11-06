# When a store's run fails or warns

You hear about it from a Windows notification (PC), an e-mail to `ALERT_EMAIL` (server), or ⚠ beside the store in the site's footer. On the server, run the commands below inside the containers: `docker compose exec scheduler …` for Python, `docker compose exec db psql -U project10794` for SQL.

## 1. See what happened

The last runs:

```sql
SELECT s.slug, r.status, r.products_found, r.error_message, r.started_at
FROM scrape_runs r JOIN stores s ON s.id = r.store_id
ORDER BY r.started_at DESC LIMIT 10;
```

The day's log, `logs/scraper-<date>.log`, has the details: look for `WARNING`, `ERROR`, `403`, `429` and each store's `done:` line. Then follow the case that matches.

## 2a. Blocked: `failed`, and the message starts with "Blocked: "

The store answered 403 or 429. Wait: the daily run leaves it alone for 24 hours by itself. Don't force a run, and don't work around the block ([ADR 0004](../adr/0004-polite-scraping.md)). If it keeps happening, switch the store off and decide what to do next:

```sql
UPDATE stores SET is_active = false WHERE slug = '<store>';
```

**It worked when** the store's next run ends `success`.

## 2b. No products: `failed`, "Scraper returned 0 products"

The store's pages changed and the scraper no longer finds anything.

1. Save what the store now sends for the page the scraper reads (the page's source, not the page as the browser shows it) over the store's file in `tests/fixtures/`.
2. Fix the store's `selectors.py` or `parser.py` in `scrapers/` until its test in `tests/test_parsers.py` passes again.
3. Run the store once: `python -m scheduler.run_single_store <store>`.

**It worked when** the run ends `success` with about as many products as the last good run.

## 2c. Too few products: `warning`, "Only N products, last successful run had M"

The run found under 70% of the last good run's products, so it saved the prices and marked nothing gone ([ADR 0006](../adr/0006-half-broken-scraper-safeguard.md)). Open the store's site and compare.

- **The store really sells fewer games now**: accept it with `python -m scheduler.run_single_store <store> --accept-drop`.
- **The store looks the same**: the scraper is partly broken. Follow 2b.

**It worked when** the next run ends `success`. After `--accept-drop`, the products the store no longer sells stop showing on the site.

## 2d. Any other failure

The traceback is in the day's log. After fixing the cause, run the store once as in 2b. A store read successfully less than 8 hours ago is skipped; `--force` overrides that, so use it sparingly.
