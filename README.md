# Project-10794
Small project for a Python course

Price comparison for video games across Portuguese stores. Scrapers fill a PostgreSQL
database on a schedule; an API reads from it. Users will also be able to sell used games.

```
scheduler → scrapers → pipeline (normalise / match / dedupe) → PostgreSQL ← API
```

## Try it with Docker

The easiest way to run it on any computer (Windows, macOS, Linux): only
[Docker Desktop](https://www.docker.com/products/docker-desktop/) is needed. It starts PostgreSQL
and the site in containers and creates the database by itself.

1. Get the code and go into its folder:
   ```
   git clone https://github.com/Barbaaz/Project-10794.git
   cd Project-10794
   ```
2. Copy `.env.example` to `.env` and set your own `DB_PASSWORD` in it (letters and numbers only)
   and a long random `SECRET_KEY` (the file says how to make one).
3. **Demo data** (recommended): if you were given a `demo.json.gz` file, put it in `database/demo/`.
   It holds the games and prices collected so far, so you don't have to scrape the stores. It isn't
   in the repository (it contains the stores' descriptions), so ask for it.
4. Start:
   ```
   docker compose up --build
   ```
   The first start downloads PostgreSQL and Python (a few hundred MB) and takes a few minutes. When the log says
   `Serving on http://0.0.0.0:5000`, open **http://localhost:5000**.

Stop with `Ctrl+C` (or `docker compose down`); the data is kept for the next start
(`docker compose down -v` deletes it).

**Without demo data** the site starts empty. Fill it by scraping, one store at a time, gently (each
store takes a few minutes; please don't repeat runs, the stores rate-limit):
```
docker compose run --rm web python -m scheduler.run_single_store cstech
```
Other stores: `press_start`, `mega-mania`, `gaming_replay`, `radio_popular`. Run the tests with
`docker compose run --rm web python -m pytest -q`.

## Setup on Windows without Docker

Needs [PostgreSQL](https://www.postgresql.org/download/) 15 or newer (built with ICU, as the
standard installers are; developed on 18). Make a login for the project that may create
databases, once, as the `postgres` superuser:

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -c "CREATE ROLE project10794 LOGIN CREATEDB PASSWORD 'choose-one'"
```

and put its password in your pgpass file, `%APPDATA%\postgresql\pgpass.conf` (`~/.pgpass` on
macOS / Linux), so it never has to be in the code:

```
localhost:5432:*:project10794:choose-one
```

The connection is in `app/config.py` (`postgresql://project10794@localhost:5432/project10794`), or
the `DB_CONNECTION_STRING` environment variable.

```powershell
pip install -r requirements.txt
python -m database.setup                                        # creates / updates the database
python -m database.setup --demo database\demo\demo.json.gz      # ... and loads demo data, if you have it
```

**Coming from SQL Server** (the project's database until October 2026): `pip install pyodbc`, then
`python -m database.from_sqlserver` copies every table of the old `localhost\SQLEXPRESS` /
`Project10794` database into the new one, ids included, and compares the two row by row
(`--source` for another SQL Server, `--replace` to copy again).

**Demo marketplace**: `python -m database.demo_market` adds 5 made-up users (`demo_ana`, `demo_bruno`…,
password `demo12345`) with 15 listings (generated photos marked DEMO) and conversations at every
purchase step; `python -m database.demo_market --remove` takes them all out again.

Sharing the collected data: `python -m database.demo export database\demo\demo.json.gz`
(`--without-texts` leaves out the stores' descriptions and IGDB summaries). Never commit it.

## API

```powershell
python app.py      # development server: http://127.0.0.1:5000 (web page) and /api/...
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
| `GET /api/games/catalog?platform=&sort=name\|price_asc\|price_desc&page=&per_page=48&editions=special&q=&store=&genre=&tags=&pegi=` | The whole catalogue (and the search): every edition with an offer in stock, paged; `editions=special` = only editions above Standard; `q` = words in the title; `store` = only what that store has in stock; `genre` = only games in that category; `tags=coop,horror` = only games with all those tags; `pegi=12` = PEGI up to 12 |
| `GET /api/genres` | Categories with games in stock (`{genre, count}`), from the IGDB genres; close genres share one (TBS / RTS / Tactical → `strategy`) |
| `GET /api/tags` | Tags for the filter: game modes and themes from IGDB (with counts), price tags `on_sale`, `historical_low` (dropped to the lowest price ever), `used` |
| `GET /api/games/editions?ids=12,34` | The wishlist tab (up to 200): these editions with all offers, historical low and `restocked_at` (back in stock in the last 14 days) |
| `GET /api/stores` | Active stores with `last_updated`, `last_status` / `last_error` of the latest run and `is_stale` (no update in 36 h) |
| `GET /api/platforms` | Platforms with games on sale (`PS5`, `Switch2`, `XboxSeries`, `XboxOne`, `PC`...) for the `platform` filter |
| `POST /api/auth/register` `{username, email, password, display_name?}` | Create an account and log in (the session cookie) |
| `POST /api/auth/login` `{login, password}` | Log in with username or email; locked for 15 min after 5 wrong passwords |
| `POST /api/auth/logout` · `GET /api/auth/me` | Log out · the logged-in user (or `null`) |
| `GET /api/listings?game_id=` · `GET /api/listings/<id>` | Pre-owned copies people sell (active / reserved), with photos; never the seller's email |
| `GET /api/listings?platform=&sort=newest\|price_asc\|price_desc&page=` | The "Used" tab: one group per game edition with its sellers' active listings, paged |
| `GET /api/listings/mine` | The logged-in seller's listings |
| `POST /api/listings` (multipart: `game_id, edition_id, price, condition, description` + 3–10 `photos`) | Put a game up for sale; photos are re-saved without EXIF (no GPS location), 1600 px + thumbnail |
| `PATCH /api/listings/<id>` `{price?, condition?, description?, status?}` | The seller changes it (status: active / reserved / sold / removed) |
| `POST /api/listings/<id>/photos` · `DELETE /api/listings/<id>/photos/<photo_id>` | Add / remove photos (always 3–10) |
| `POST /api/listings/<id>/conversation` `{message?, buy?}` | Message / Buy: open (or reopen) the conversation with the seller → `{id}` |
| `GET /api/conversations` · `GET /api/conversations/unread` | The user's conversations (unread count, last message) · the total unread |
| `GET /api/conversations/<id>?after=` · `POST …/messages` `{body}` | One conversation (only messages after `after`, for refreshing) · send a message |
| `POST /api/conversations/<id>/steps` `{action}` | Purchase step: `request`, `accept` (reserves), `decline`, `sent`, `received` (sold), `problem`, `cancel`; 7 days after `sent` it completes by itself |
| `GET /api/igdb/games?q=` · `POST /api/igdb/games` `{igdb_id, platform}` | The sell form, for games the catalogue doesn't have (older platforms): IGDB games on our platforms · the game on that platform, created from IGDB if needed (20 per user per day) → `{game_id, edition_id}` |
| `PUT /api/mod/games/<id>/title-en` `{title_en}` | Moderators: a game's English name, shown when the page is in English (`""` = the store's title) |
| `POST /api/collection/import` `{ids}` | Favourites an old browser kept (before accounts; favourites are now the wishlist), put on the wishlist (merged editions followed) → `{added}` |
| `GET /api/ratings/pending` | Completed purchases the user still has to rate (`overdue` after 14 days: buying and selling blocked until rated) |
| `POST /api/conversations/<id>/rating` `{stars, comment?}` | Rate the other side of a completed purchase (changeable for 14 days) |
| `POST /api/ratings/<id>/reply` `{reply}` | The rated user answers a rating |
| `GET /api/users/<username>` | Public profile: average rating, ratings received, listings, game reviews (never the email) |
| `GET /api/collection` · `GET /api/collection/editions` | The user's collection and wishlist with current prices and statistics (per platform / status, hours, worth new / used) · which editions they have (for the game page's Tenho / Quero) |
| `POST /api/collection` `{edition_id, kind: owned\|wishlist, format?, status?, hours?, notes?}` · `PATCH` / `DELETE /api/collection/<id>` | Add (owning one takes it off the wishlist) · edit (`kind: owned` = bought it) / remove |
| `PUT /api/collection/settings` `{public}` · `GET /api/users/<username>/collection` | Show the collection on the profile (private by default; notes and hours never shown) · a public collection |
| `GET /api/games/<id>/reviews?page=` | Players' reviews of a game on that platform: average, count and how many gave each score 1–10, the user's own review, 20 shown reviews per page (newest first; hidden ones and blocked users' left out; `owner` = has the game in their collection). Catalogue / deals / wishlist cards carry `review_score` and `review_count` |
| `PUT /api/games/<id>/reviews/mine` `{score: 1–10, title?, body?}` · `DELETE` | Write or change one's review (one per user and game) · delete it (not once a moderator hid it) |
| `POST /api/reports` `{kind: listing\|user\|rating\|review, target_id, reason, details?}` | Report something to the moderators (not your own; once while open; 20 a day) |
| `GET /api/mod/reports` · `GET /api/mod/problems` · `GET /api/mod/log` | Moderators: open reports grouped by what was reported · purchases with a problem · past actions |
| `POST /api/mod/actions` `{action, target_id, note?}` | Moderators: `hide_listing` / `restore_listing`, `hide_rating` / `restore_rating`, `hide_review` / `restore_review`, `block_user` / `unblock_user`, `dismiss` (target = the report) |
| `GET /api/mod/conversations/<id>` | Moderators: a purchase's messages, read-only |
| `GET` / `POST /api/mod/staff` `{username, role: moderator\|user}` | Admins: the moderators and admins · name or remove a moderator |
| `GET /api/mod/matches?q=` · `POST /api/mod/matches` `{product_ids, edition_id \| game_id + new_edition}` | Moderators: a game's editions with their store products · move products to an edition and pin them there (the daily update and `pipeline.rematch` leave pinned products alone; an edition left empty is merged) |
| `GET /api/mod/pins` · `DELETE /api/mod/pins/<product_id>` | Moderators: pinned products · unpin (the next rematch goes by the name) |

**Moderation.** Users have a role: `user`, `moderator` or `admin`. Moderators and admins get a 🛡️
button in the header that opens `/admin` (reports, problem purchases, the log; admins also the
staff list). Admins are only made from the command line:

    python -m database.users role <username> admin     # or moderator / user
    python -m database.users list                      # who has which role

Requests that change something (POST / PUT / DELETE) must send the header `X-Requested-With: fetch`
(the pages' `api()` helper in `static/common.js` does): another site can't add it, so it can't act
as a logged-in visitor.

An offer has `price`, `in_stock`, `condition` (`new`/`used`), `url`, and — only when the
discount is real — `was_price` and `discount_percent`. Errors are `{"error": "..."}`
with status 400 or 404. `per_page` is at most 100.

## Front page

Tabs, the visitor's choice remembered in the browser (or opened with `/?tab=…`):
`discounts` (featured real discounts, or best prices between stores until there are some),
`preorders`, `releases` (calendar by month / day), `catalog` (everything in stock, by platform,
sortable, 48 at a time), `special` (only editions above Standard) and `wishlist` (the logged-in user's wished
editions with their offers and historical low; `?tab=favorites` still opens it). Search uses the
catalogue too: 48 editions per page, sort by name / price, and a store filter (also on the
catalogue tabs); the address keeps them (`/?q=zelda&page=2&store=cstech`). The game page's back
button returns to the search or tab the game was opened from. Wished editions that came back in
stock show as a banner. Each card's ☆ opens a menu: ⭐ Quero (wishlist; ★ on the card) and
📚 Tenho (collection; a small 📚 on the card). Favourites were folded into the wishlist
(migration 0007).

## The app on a phone

The site can be installed on a phone's home screen (and on a computer, from Chrome / Edge):
`static/manifest.webmanifest` (name, icons in `static/icons/`, colours) and a service worker,
`static/sw.js`, served as `/sw.js`. Android / desktop show a "📲 Instalar app" button in the header
when the browser offers it; on an iPhone it's Safari's Share → Add to Home Screen. Installing
needs HTTPS, except on `localhost`.

Without a connection (or one too slow to answer in 6 s), pages visited before open from what was
saved on the last visit; a page never visited shows `static/offline.html`. Only public reads are
saved (catalogue, game pages and price history, discounts, pre-orders, releases, lists, used
copies): whenever a page shows saved prices, a notice says so, with when they were saved.
Anything personal (account, messages, collection, moderation, reviews) or that changes something
always goes to the network. After changing what `sw.js` saves, raise its `VERSION`.

## Games and editions

Products are grouped as **game → edition → store offers**: "Silent Hill: Townfall" (PS5)
has a Standard and a Day One Edition, each with its own prices per store. The rules that
split a store's name into game + edition are in `core/editions.py`; `pipeline/matcher.py`
links each product, also when stores write a name differently:

- a shortened name goes to the one fuller known game it fits ("Doom Dark Ages" → "Doom: The
  Dark Ages"; `core/close_match.py`: same numbers, same first and last word, only linking words
  missing, exactly one candidate — so "F1 23" never joins "F1 Manager 23");
- a title cut in the wrong place is mended ("Star Wars" + "Galactic Racer Deluxe" → "Star Wars:
  Galactic Racer" + "Deluxe"), but edition words never move into a title;
- edition keys ignore word order, filler and synonyms ("Day 1 Steelbook" = "Steelbook Day One",
  "Game of the Year" = "GOTY"), and an edition differing by a typo from one the game already has
  is that edition ("Delixe" → "Deluxe").

Products sold as a code in a box ("Código na caixa", "Code in box", "Código de descarga")
are not tracked.

After changing the matching rules, re-link what is already stored (no scraping). Check the list of
merges first:

```powershell
python -m pipeline.rematch --dry-run
python -m pipeline.rematch
```

Games and editions merged into another are recorded in `merged_ids`: old `/game/<id>` links
redirect, and listings, collection items and reviews move to the game / edition that replaced theirs.

## Discounts

The stores' crossed-out prices are not trusted (many show one permanently). The
`current_offers` view decides `is_discount` from our own price history, like the EU
Omnibus rule: the current price must be lower than the lowest price recorded in the
30 days before it dropped. A product needs 30 days of history before it can show a
discount, so keep the scheduler running.

The connection string defaults to `project10794` on `localhost:5432`; set the
`DB_CONNECTION_STRING` environment variable to use another server.

## Filling the database

```powershell
python -m scheduler.run_all_scrapers            # every active store
python -m scheduler.run_single_store cstech     # one store
```

Each run is logged in the `scrape_runs` table and in `logs\scraper.log`.

### Daily update

Live prices and stock are re-checked twice a day by two Windows scheduled tasks:

- **06:00** `python -m scheduler.run_all_scrapers`: every store (including product pages for
  descriptions / release dates), then the IGDB lookups (new games, videos, tags, time to beat)
- **18:00** `python -m scheduler.run_all_scrapers --light`: Press Start, Mega Mania and Gaming Replay
  again, listing pages only (~250 requests), so their prices are at most ~12 h old. CSTech
  (has answered "too many requests" before) and Rádio Popular stay once a day

A store isn't run again within 8 hours of a successful run (`MIN_HOURS_BETWEEN_RUNS`).

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1                   # 06:00 and 18:00
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -Time 03:30 -EveningTime 17:00
powershell -ExecutionPolicy Bypass -File scheduler\register_daily_task.ps1 -EveningTime ""   # morning only
Start-ScheduledTask -TaskName Project10794-Scrapers                                          # run now
Unregister-ScheduledTask -TaskName Project10794-Scrapers* -Confirm:$false                    # remove both
```

The task runs while you are logged on; if the computer was off at the scheduled time,
it runs as soon as it is on again.

When a store fails or looks half-broken, the daily run shows a **Windows notification**, and
the front page footer shows ⚠ next to that store (also when a store hasn't updated for 36 h). A full run takes about 8 minutes. A new price row is
only stored when a price or stock status changes.

## Database code

- **Marketplace** (users, listings, photos, conversations, messages, ratings, collection, reviews):
  SQLAlchemy models in `app/models.py`, used by `app/services/{auth,listing,chat,rating,collection,review}_service.py`
  through `db.session()` — no SQL text there. Their tables are made and changed by **Alembic**
  migrations (`migrations/versions/`).
- **Pipeline** (`pipeline/process_scraped_data.py`, `matcher.py`, `rematch.py`): writes games,
  editions, store products, price snapshots and merges through the same models and `db.session()`.
  Their tables are made by `database/schema.sql` (not Alembic), which the models follow.
- **Price analysis** (the `current_offers` discount view, the catalogue / discount / history
  queries in `app/services/`): SQL in `database/*.sql` and `db.fetch_all`, being reports (latest
  price per product, 30-day windows) that read better as SQL. Parameters are written `?`
  (`db.fetch_all("... WHERE id = ?", game_id)`); `db.py` passes them to psycopg.
- **Times** are UTC without a time zone (`timestamp`), set by the database's `utcnow()`
  (`database/schema.sql`); the API sends them with a `Z`.
- **Names** that are sorted (game titles, edition, store and platform names) use the `pt_ci`
  collation: Portuguese order, case ignored, as SQL Server sorted them. Usernames are unique
  without case (an index on `lower(username)`; look users up with `User.named(name)`).

`python -m database.setup` runs both. To change a marketplace table:

```powershell
# 1. change the model in app/models.py, then:
alembic revision --autogenerate -m "listings: add a shipping cost"   # writes migrations/versions/…
# 2. read the generated file (autogenerate isn't perfect), then:
alembic upgrade head
alembic check            # "No new upgrade operations detected" = models and database agree
```

## Tests

```powershell
python -m pytest
```

- Parsers run against saved store pages in `tests/fixtures`. When a store changes its site,
  refresh the fixture from the live page and see which tests break.
- Edition splitting, platform detection, price parsing, the "código na caixa" exclusion and the
  half-broken-scraper safeguard are plain unit tests.
- The discount rule, the services and the pipeline run against a throwaway PostgreSQL database
  created and dropped by the tests (skipped when PostgreSQL isn't available).

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

A daily run makes about 150 requests to Press Start, 60 to Mega Mania, 16 to CSTech, ~110 to
Gaming Replay and ~72 to Rádio Popular. Shopify stores (CSTech) answer 429 after many requests in a
short time: avoid extra manual runs.

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
| Gaming Replay | HTML (PrestaShop), per platform the "Jogos" and "Seminovos" (pre-owned) category pages, 12 games per page (~110 requests a run); "(COIB)" = code in box, excluded; "(Edição Americana / Asiática / Japonesa)" = import editions |
| Rádio Popular | JSON from its "load more" request (POST `/ajax`, 12 games per page); match-only (see below) |

Rádio Popular shortens names ("TALES OF ETERNIA REMAS", "LUIGI MANS 3"): its products are also
matched to a known game they're a short form of (`core/close_match.py`: same numbers, same first
and last word, only linking words may be missing, exactly one candidate). Its names are too cut
down to start games from (a first run made 340 games like "INSP GADGET MAD TIME P"), so it's a
match-only store (`MATCH_ONLY_STORES` in `pipeline/matcher.py`): a product links only to a game and
edition that already exist, otherwise it stays unlinked and isn't shown.

Checked and not added (2026-10-02 / 03): Fnac, Worten and shop4nerds block plain requests (captcha /
Cloudflare challenge), Darty answered 429 to every run's first request (dropped), Amazon's
Conditions of Use forbid scraping, El Corte Inglés only has prices on
product pages (one request per game). Details in the project plan.

### Adding a store

1. Create `scrapers/<store>/scraper.py` with a class extending `BaseScraper`
   (HTML stores: set `catalog_urls`, `listing_parser` — the `parse_products` of the store's
   `parser.py` — and, if its product pages are useful, `product_page_parser`; implement
   `build_page_url`) or `scrapers.base.shopify.ShopifyScraper` (Shopify stores: `store_slug`,
   `base_url`; stores selling more than games also set `collections` / `game_type_prefix`, see
   `scrapers/base/shopify.py`).
2. Register it in `SCRAPERS` in `scheduler/jobs.py`.
3. Add a row to `database/seed_stores.sql` with the same slug and re-run it.
