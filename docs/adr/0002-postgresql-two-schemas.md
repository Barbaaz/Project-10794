---
status: accepted
---

# PostgreSQL, with the price side in SQL scripts and the marketplace in Alembic

The database is PostgreSQL, since 2026-10-03 (SQL Server before). Its tables come from two places:

- **The price side** (platforms, stores, games, editions, offers, price history, scrape runs, merged ids, the `current_offers` view) is created by the scripts in `database/`: `schema.sql`, `indexes.sql`, `views.sql` and `seed_stores.sql`.
- **The marketplace side** (`MARKET_TABLES` in `app/models.py`) is described by SQLAlchemy models and changed by numbered Alembic revisions in `migrations/versions/` (since 2026-10-02).

`python -m database.setup` runs the scripts, then the revisions. The price side came first as SQL, and its views are reports (the latest price per offer, 30-day windows) that read better as SQL. The marketplace moved to models so its tables are described completely in Python and change one numbered revision at a time. The pipeline writes the price-side tables through models too, and those models follow `schema.sql`.

## Consequences

- A price-side column is an `ALTER TABLE … ADD COLUMN IF NOT EXISTS` after its table in `database/schema.sql`, plus the model when Python writes it. A marketplace column is a new revision. See [Change a table](../how-to/change-a-table.md).
- Alembic looks only at `MARKET_TABLES` (`migrations/env.py`), so `alembic check` can't notice a price-side model that drifted from `schema.sql`. The tests, which build a database from the scripts, can.
- The commit that left SQL Server (381b4b4) records how the move was checked (every table compared row by row, the pipeline run on both) but not why. `database/from_sqlserver.py` was the one-time copy.
