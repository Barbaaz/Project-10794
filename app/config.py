import os
import secrets
from pathlib import Path

# PostgreSQL. Override with the DB_CONNECTION_STRING environment variable on other machines.
# No password here: on a development machine it's in the user's pgpass file
# (%APPDATA%\postgresql\pgpass.conf on Windows, ~/.pgpass elsewhere); Docker puts it in the URL.
DB_CONNECTION_STRING = os.environ.get(
    "DB_CONNECTION_STRING",
    "postgresql://project10794@localhost:5432/project10794",
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
# Served through one reverse proxy (Caddy, docker-compose.hosting.yml): trust its X-Forwarded-For /
# -Proto, so the login lockout counts each visitor's address, not the proxy's. Never set it when
# the site is reachable without the proxy: anyone could then pick the address they appear from.
BEHIND_PROXY = os.environ.get("BEHIND_PROXY") == "1"
# A test copy on demo data (the teste/ launchers): its prices are a snapshot, never scraped
# again, so the pages say so and stores aren't flagged as out of date
DEMO_MODE = os.environ.get("DEMO_MODE") == "1"

# The site's own address, for links in e-mails (never taken from the request: its Host header
# could point a password-reset link at another site)
SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:5000").rstrip("/")

# E-mail (app/services/mail_service.py): sent by SMTP once SMTP_HOST is set (any provider);
# until then, e-mails are only written to the log
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
