# Project-10794
Small project for a Python course

Price comparison for video games across Portuguese stores. Scrapers fill a SQL Server
database on a schedule; an API reads from it. Users will also be able to sell used games.

```
scheduler → scrapers → pipeline (normalise / match / dedupe) → SQL Server ← API
```

## Setup

```powershell
pip install -r requirements.txt
sqlcmd -S "localhost\SQLEXPRESS" -E -b -i database\schema.sql -i database\indexes.sql -i database\views.sql -i database\seed_stores.sql
```

## API

```powershell
python app.py      # http://127.0.0.1:5000 (web page) and /api/...
```

Read-only JSON, served from the database (nothing is scraped on request):

| Endpoint | What it returns |
|----------|-----------------|
| `GET /api/games?q=&platform=&page=&per_page=` | Games matching every word of `q`, with `best_price` (in stock), number of `stores` / `editions`, `has_discount` |
| `GET /api/games/<id>` | The game with its `editions`, each with its store `offers` (in stock first, cheapest first) |
| `GET /api/games/<id>/prices?days=90` | Price history per offer |
| `GET /api/discounts?platform=&min_percent=&page=` | Offers that are really on sale, biggest discount first |
| `GET /api/discounts/featured?limit=12&min_percent=10` | Front page: biggest real discounts, one per game edition (new, in stock) |
| `GET /api/stores` | Active stores and when each was last updated |
| `GET /api/platforms` | Platforms with games on sale (`PS5`, `Switch2`, `XboxSeries`, `XboxOne`, `PC`...) for the `platform` filter |

An offer has `price`, `in_stock`, `condition` (`new`/`used`), `url`, and — only when the
discount is real — `was_price` and `discount_percent`. Errors are `{"error": "..."}`
with status 400 or 404. `per_page` is at most 100.

## Games and editions

Products are grouped as **game → edition → store offers**: "Silent Hill: Townfall" (PS5)
has a Standard and a Day One Edition, each with its own prices per store. The rules that
split a store's name into game + edition are in `core/editions.py`.

Products sold as a code in a box ("Código na caixa", "Code in box", "Código de descarga")
are not tracked.

After changing the matching rules, re-link what is already stored (no scraping):

```powershell
python -m pipeline.rematch
```

## Discounts

The stores' crossed-out prices are not trusted (many show one permanently). The
`current_offers` view decides `is_discount` from our own price history, like the EU
Omnibus rule: the current price must be lower than the lowest price recorded in the
30 days before it dropped. A product needs 30 days of history before it can show a
discount, so keep the scheduler running.

The connection string defaults to `localhost\SQLEXPRESS` / `Project10794`; set the
`DB_CONNECTION_STRING` environment variable to use another server.

## Filling the database

```powershell
python -m scheduler.run_all_scrapers            # every active store
python -m scheduler.run_single_store cstech     # one store
```

Each run is logged in the `scrape_runs` table and in `logs\scraper.log`.

### Daily update

Live prices and stock are re-checked once per day by a Windows scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1              # daily at 06:00
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -Time 03:30  # other time
Start-ScheduledTask -TaskName Project10794-Scrapers                                     # run now
Unregister-ScheduledTask -TaskName Project10794-Scrapers -Confirm:$false                # remove
```

The task runs while you are logged on; if the computer was off at the scheduled time,
it runs as soon as it is on again. A full run takes about 8 minutes. A new price row is
only stored when a price or stock status changes.

## Stores

| Store       | Source                                   |
|-------------|------------------------------------------|
| Press Start | HTML, game category pages                |
| Mega Mania  | HTML, game category pages                |
| CSTech      | Shopify JSON feed (`/products.json`)     |

### Adding a store

1. Create `scrapers/<store>/scraper.py` with a class extending `BaseScraper`
   (HTML stores: set `catalog_urls`, implement `build_page_url` and `parse_listing`)
   or `ShopifyScraper` (Shopify stores: only `store_slug` and `base_url`).
2. Register it in `SCRAPERS` in `scheduler/jobs.py`.
3. Add a row to `database/seed_stores.sql` with the same slug and re-run it.
