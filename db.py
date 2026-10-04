import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import namedtuple_row, tuple_row

from app.config import DB_CONNECTION_STRING


def sql_for_psycopg(sql):
    """Our SQL marks parameters with ? (DB-API's qmark style); psycopg wants %s, and a literal % doubled."""
    return sql.replace("%", "%%").replace("?", "%s")


class Cursor(psycopg.ClientCursor):
    """
    A cursor that takes ? parameters one by one:   cursor.execute("... WHERE id = ?", game_id)
    Client-side binding (values written into the SQL, as psycopg2 did): "? IS NULL" and
    parameters in a SELECT list work without saying their type.
    """
    def execute(self, query, *params):
        if len(params) == 1 and isinstance(params[0], (list, tuple)):
            params = params[0]
        return super().execute(sql_for_psycopg(query), params)


def connect(connection_string, autocommit=False):
    """Rows are named tuples: row[0] or row.url."""
    return psycopg.connect(connection_string, autocommit=autocommit, cursor_factory=Cursor, row_factory=namedtuple_row)


def get_connection():
    return connect(DB_CONNECTION_STRING)


@contextmanager
def connection():
    """
    A connection for a unit of work: committed at the end, rolled back if anything fails,
    always closed.   with connection() as conn: conn.cursor().execute(...)
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- SQLAlchemy (the marketplace's models, app/models.py) ---------------------------------
_engines = {}


def get_engine():
    """
    The SQLAlchemy engine for DB_CONNECTION_STRING (made on first use, one per connection
    string, so tests that point the app at a throwaway database get their own).
    """
    if DB_CONNECTION_STRING not in _engines:
        _engines[DB_CONNECTION_STRING] = make_engine(DB_CONNECTION_STRING)
    return _engines[DB_CONNECTION_STRING]


def make_engine(connection_string):
    """A SQLAlchemy engine for a PostgreSQL connection string (as in app/config.py)."""
    from sqlalchemy import create_engine

    return create_engine(
        "postgresql+psycopg://",
        creator=lambda: psycopg.connect(connection_string),
        pool_pre_ping=True,        # a connection dropped by the server is replaced, not used
    )


@contextmanager
def session():
    """
    A SQLAlchemy session for a unit of work: committed at the end, rolled back if anything
    fails, always closed.   with session() as s: s.add(Listing(...))
    Objects stay readable after the commit (expire_on_commit=False).
    """
    from sqlalchemy.orm import Session

    s = Session(get_engine(), expire_on_commit=False)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def json_value(value):
    """A column value as JSON sends it: Decimal → float, datetime → ISO in UTC ("…Z"), date → ISO."""
    return _json_value(value)


def placeholders(values):
    """ "?,?,?" for an IN (...) list of these values."""
    return ",".join("?" * len(values))


def json_or_none(value):
    """A dict / list for a text JSON column; None when empty."""
    return json.dumps(value, ensure_ascii=False) if value else None


_pools = {}


def get_pool():
    """
    Open connections kept for fetch_all, one pool per connection string (as get_engine).
    A new PostgreSQL connection costs ~60 ms (the password exchange), and a page runs
    several queries; SQL Server's driver pooled them without being asked, psycopg doesn't.
    """
    if DB_CONNECTION_STRING not in _pools:
        from psycopg_pool import ConnectionPool

        _pools[DB_CONNECTION_STRING] = ConnectionPool(
            DB_CONNECTION_STRING, min_size=1, max_size=10, open=True,
            check=ConnectionPool.check_connection,   # one dropped by the server is replaced, not used
        )
    return _pools[DB_CONNECTION_STRING]


def fetch_all(sql, *params):
    """Rows as dicts with JSON-friendly values (Decimal → float, datetime → ISO string)."""
    with get_pool().connection() as conn:              # committed, or rolled back on an error
        cursor = Cursor(conn, row_factory=tuple_row)   # a query may repeat a column name (the last one wins)
        cursor.execute(sql, *params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, map(_json_value, row))) for row in cursor.fetchall()]


def fetch_one(sql, *params):
    rows = fetch_all(sql, *params)
    return rows[0] if rows else None


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat() + "Z"   # every timestamp is stored in UTC (utcnow(), database/schema.sql)
    if isinstance(value, date):
        return value.isoformat()
    return value
