from datetime import date, datetime
from decimal import Decimal

import pyodbc

from app.config import DB_CONNECTION_STRING

def get_connection():
    return pyodbc.connect(DB_CONNECTION_STRING)


def fetch_all(sql, *params):
    """Rows as dicts with JSON-friendly values (Decimal → float, datetime → ISO string)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, *params)
        columns = [c[0] for c in cursor.description]
        return [dict(zip(columns, map(_json_value, row))) for row in cursor.fetchall()]
    finally:
        conn.close()


def fetch_one(sql, *params):
    rows = fetch_all(sql, *params)
    return rows[0] if rows else None


def _json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat() + "Z"   # every timestamp is stored in UTC (SYSUTCDATETIME)
    if isinstance(value, date):
        return value.isoformat()
    return value
