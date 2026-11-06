# Change a table

First find the table's side ([ADR 0002](../adr/0002-postgresql-two-schemas.md)). Marketplace tables are listed in `MARKET_TABLES` in `app/models.py`; every other table is on the price side.

## A price-side table

1. In `database/schema.sql`, after the table's `CREATE TABLE`, add `ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type>;`. Leave the `CREATE TABLE` as it is: on an existing database it changes nothing.
2. If Python reads or writes the column through a model, add it to the model in `app/models.py`.
3. If a view should show it, change `database/views.sql`, which drops and re-creates its views.
4. Run `python -m database.setup`.

**It worked when** `python -m pytest` passes. The tests build a new database from the scripts, so a broken script fails them.

## A marketplace table

1. Change the model in `app/models.py`.
2. Write the revision with `alembic revision --autogenerate -m "<what changed>"`, then read the file it made: autogenerate misses things.
3. Number it like the others. The file name and its `revision` are the next number plus a short name (`0021_deal_since`), and `down_revision` is the previous one.
4. Run `alembic upgrade head`.

**It worked when** `alembic check` says "No new upgrade operations detected" and `python -m pytest` passes.

## On the server

Nothing by hand. The web container runs `database.setup` when it starts, so the update steps in [DEPLOY.md](../../DEPLOY.md#updating-to-newer-code) apply the change.
