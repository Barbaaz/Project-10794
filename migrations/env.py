"""
Alembic: changes to the marketplace tables (app/models.py), as numbered migrations in
migrations/versions. The price side's tables are still made by database/*.sql
(python -m database.setup runs both).

    alembic upgrade head                                   # bring the database up to date
    alembic revision --autogenerate -m "what changed"      # after changing app/models.py: review it!

The database is the one in DB_CONNECTION_STRING (app/config.py); database/setup.py passes its
own connection instead (config.attributes["connection"]), e.g. for the tests' database.
"""
from alembic import context

from app.models import MARKET_TABLES, Base

config = context.config
target_metadata = Base.metadata


def include_name(name, type_, parent_names):
    """Tables in the database: only the marketplace's (the price side has its own SQL scripts)."""
    return type_ != "table" or name in MARKET_TABLES


def include_object(obj, name, type_, reflected, compare_to):
    """Tables in app/models.py: also only the marketplace's (games, editions… are only read there)."""
    table = name if type_ == "table" else getattr(getattr(obj, "table", None), "name", None)
    return table is None or table in MARKET_TABLES


def run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, include_name=include_name,
                      include_object=include_object,
                      compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return
    from db import get_engine
    with get_engine().connect() as connection:
        run_migrations(connection)


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) mode isn't set up: run against the database.")
run_migrations_online()
