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
| `GET /api/deals?limit=12&min_percent=15` | Editions clearly cheaper at one store than at the next cheapest (15–60% gap, a comparison, not a discount); shown while there are no real discounts |
| `GET /api/preorders?platform=` | Games on pre-order, one group per edition, soonest release first |
| `GET /api/releases?platform=` | Games coming out from today on, by release date (`date_is_estimate` for "31/12" dates) |
| `GET /api/games/catalog?platform=&sort=name\|price_asc\|price_desc&page=&per_page=48&editions=special` | The whole catalogue: every edition with an offer in stock, paged; `editions=special` = only editions above Standard |
| `GET /api/games/editions?ids=12,34` | Favourites: these editions with all offers, historical low and `restocked_at` (back in stock in the last 14 days) |
| `GET /api/stores` | Active stores with `last_updated`, `last_status` / `last_error` of the latest run and `is_stale` (no update in 36 h) |
| `GET /api/platforms` | Platforms with games on sale (`PS5`, `Switch2`, `XboxSeries`, `XboxOne`, `PC`...) for the `platform` filter |

An offer has `price`, `in_stock`, `condition` (`new`/`used`), `url`, and — only when the
discount is real — `was_price` and `discount_percent`. Errors are `{"error": "..."}`
with status 400 or 404. `per_page` is at most 100.

## Front page

Tabs, the visitor's choice remembered in the browser (or opened with `/?tab=…`):
`discounts` (featured real discounts, or best prices between stores until there are some),
`preorders`, `releases` (calendar by month / day), `catalog` (everything in stock, by platform,
sortable, 48 at a time), `special` (only editions above Standard) and `favorites` (starred
editions with their offers and historical low). The game page's back button returns to the
search or tab the game was opened from. Favourites that came
back in stock show as a banner. Favourites are stored in the browser for now.

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
it runs as soon as it is on again.

When a store fails or looks half-broken, the daily run shows a **Windows notification**, and
the front page footer shows ⚠ next to that store (also when a store hasn't updated for 36 h). A full run takes about 8 minutes. A new price row is
only stored when a price or stock status changes.

## Tests

```powershell
python -m pytest
```

- Parsers run against saved store pages in `tests/fixtures`. When a store changes its site,
  refresh the fixture from the live page and see which tests break.
- Edition splitting, platform detection, price parsing, the "código na caixa" exclusion and the
  half-broken-scraper safeguard are plain unit tests.
- The discount rule runs against a throwaway SQL Server database created and dropped by the
  tests (skipped when SQL Server isn't available).

## Game information

- **Store descriptions** (Portuguese; what each special edition includes): read from each
  product page once, at most 100 pages per store per daily run, special editions first.
  CSTech's come with its catalogue. Speed up the first fill with
  `python -m pipeline.fill_descriptions <store> --limit 100`.
- **Store photos**: the product's photos besides the cover (on special editions, what's in the
  box), read with the description: Press Start's gallery, pictures inside Mega Mania's
  description, CSTech's catalogue images. Shown under each special edition's "What's included".
- **IGDB** (summary, genres, publisher, developer, PEGI, rating, cover, screenshots, YouTube
  trailers): looked up once per game, new games after each daily run. Needs a Twitch developer
  app in the environment variables `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` (never in the code).
  First fill: `python -m pipeline.igdb --limit 6000`; trailers for games matched before they were
  kept: `python -m pipeline.igdb --videos`. The game page shows thumbnails and loads the
  YouTube player (youtube-nocookie) only when a video is clicked.

## Not getting blocked by the stores

All scraper requests go through `scrapers/base/http_client.py`:

- one request at a time, at least 3 s (+ 0–2 s random) between requests to the same store;
  a larger `Crawl-delay` in the store's robots.txt wins
- URLs disallowed by robots.txt are never fetched
- a 403 / 429 answer stops that store's run immediately (no retrying into a block)
- at most 600 requests per store per run; at most 50 product pages for release dates per run
- a store isn't scraped again within 12 hours of a successful run:
  `python -m scheduler.run_single_store <store> --force` overrides it

A daily run makes about 150 requests to Press Start, 60 to Mega Mania, 16 to CSTech and 24 to Darty.
Shopify stores (CSTech, Darty) answer 429 after many requests in a short time: avoid extra manual runs.

## Safeguard against a half-broken scraper

If a store returns less than 70% of its last successful run's products (e.g. the site changed
and prices are no longer found), prices are still saved but missing products are **not**
deactivated, and the run is marked `warning` in `scrape_runs`. If the store really shrank:

```powershell
python -m scheduler.run_single_store <store> --accept-drop
```

## Stores

| Store       | Source                                   |
|-------------|------------------------------------------|
| Press Start | HTML, game category pages                |
| Mega Mania  | HTML, game category pages                |
| CSTech      | Shopify JSON feed (`/products.json`)     |
| Darty       | Shopify JSON feed, games collection only (`/collections/videojogos/products.json`); pre-orders = the `pre-vendas-gaming` collection |

| Rádio Popular | JSON from its "load more" request (POST `/ajax`, 12 games per page); **switched off** until a first manual run is checked |

Rádio Popular shortens names ("TALES OF ETERNIA REMAS", "FF VII REVELATION"): its products are
also matched to a known game they're a short form of (`core/close_match.py`: same numbers, same
first and last word, only linking words may be missing, exactly one candidate).

Checked and not added (2026-10-02): Fnac and Worten block plain requests (captcha / Cloudflare
challenge), Amazon's Conditions of Use forbid scraping, El Corte Inglés only has prices on product
pages (one request per game). Details in the project plan.

### Adding a store

1. Create `scrapers/<store>/scraper.py` with a class extending `BaseScraper`
   (HTML stores: set `catalog_urls`, implement `build_page_url` and `parse_listing`)
   or `ShopifyScraper` (Shopify stores: only `store_slug` and `base_url`; stores selling more
   than games also set `collections`, see `scrapers/darty/scraper.py`).
2. Register it in `SCRAPERS` in `scheduler/jobs.py`.
3. Add a row to `database/seed_stores.sql` with the same slug and re-run it.
