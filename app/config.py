import os
import secrets
from pathlib import Path

# Override with the DB_CONNECTION_STRING environment variable on other machines
DB_CONNECTION_STRING = os.environ.get(
    "DB_CONNECTION_STRING",
    # Driver 17 returns DATETIME2 as datetime; the old "{SQL Server}" driver returns text
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost\\SQLEXPRESS;"
    "DATABASE=Project10794;"
    "Trusted_Connection=yes;"
)

INSTANCE_DIR = Path(__file__).resolve().parent.parent / "instance"   # local, never committed


def _secret_key():
    """
    Signs the login cookie. From the SECRET_KEY environment variable (servers, Docker); on a
    development machine, made once and kept in instance/secret_key so logins survive restarts.
    """
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = INSTANCE_DIR / "secret_key"
    if not path.exists():
        INSTANCE_DIR.mkdir(exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


SECRET_KEY = _secret_key()
# Only send the login cookie over HTTPS: set COOKIE_SECURE=1 once the site is served with HTTPS
COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"
# A test copy on demo data (the teste/ launchers): its prices are a snapshot, never scraped
# again, so the pages say so and stores aren't flagged as out of date
DEMO_MODE = os.environ.get("DEMO_MODE") == "1"
