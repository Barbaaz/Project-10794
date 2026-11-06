# Python

## Layers

- **Routes** (`app/routes/`) stay thin: read input with the `params.py` helpers or `request.get_json(silent=True)`, check access with `login_required` / `moderator_required` (`app/routes/auth.py`), call one service, return `jsonify(...)`.
- **Services** (`app/services/`) hold the rules and open the database: `with session() as s:` from `db.py` (commits at the end, rolls back on an error), or `fetch_all` / `fetch_one` for plain SQL reads.
- **Refusals**: a service raises its own exception carrying `code` and `status` (`CollectionError`, `AccountError`…), and the blueprint's `@bp.errorhandler` turns it into `{"error": code}`. The page shows `t("error_" + code)`, so a new code needs an `error_<code>` key in both languages of `static/i18n.js`.
- **Prices** are written only by the daily run (`scheduler/` → `scrapers/` → `pipeline/`, with name and edition rules in `core/`). The web app reads them and writes only what people do on the site.

## Data

- **Two schemas.** The price side (platforms, stores, games, editions, store products, price snapshots) is plain SQL in `database/*.sql`, applied by `python -m database.setup`. A new column there is an `ALTER TABLE … ADD COLUMN IF NOT EXISTS` under the table in `schema.sql`. The marketplace side (`app/models.py`, from users onward) changes through a new numbered Alembic revision, `migrations/versions/00NN_short_name.py`.
- **Money** is `Decimal` in Python and `Numeric(10, 2)` in the marketplace tables. Price snapshots store whole cents (`to_cents`).
- **Time** is UTC: `NOW` (the database clock, `app/models.py`) for stored timestamps, `datetime.now(timezone.utc)` in Python.
- **Queries** use the SQLAlchemy 2 style: `select()`, `update()`, `delete()`.

## Scrapers

- **One package per store**: `scrapers/<store>/` with `scraper.py` (and usually `parser.py` and `selectors.py`), its scraper subclassing `BaseScraper` (or `ShopifyScraper`). Every request goes through the scraper's `HttpClient`, which throttles, follows robots.txt and stops on 403 / 429.
- **A new store** is registered in `SCRAPERS` (`scheduler/jobs.py`) and given a row in `database/seed_stores.sql`.
- **Parser tests** read saved pages from `tests/fixtures/`.
- **Matching rules** in `core/` apply to stored products after `python -m pipeline.rematch`.

## Style

- **Type hints** on every function you add or whose signature you change.
- **Constants**: UPPER_CASE at the top of the module, with one name for each meaning. A second assignment to the same name silently replaces the first for the whole module.
- **Docstrings**: each module opens with what it owns and why. A choice the user made carries `(user, YYYY-MM-DD)` in the comment beside it.
- **Language**: code, comments and names in English. Text people read comes from `static/i18n.js` keys.

## Tests

- **Run** `python -m pytest`. Database tests get a throwaway PostgreSQL database (`tests/conftest.py`) and are *skipped* when PostgreSQL isn't running, so read the skip count before trusting a green run.
- **A bug fix** comes with a test that fails without the fix.
