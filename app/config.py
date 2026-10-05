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

# The cookie only holds the user id: whoever knows the key can sign one for any user (an admin too).
# So never .env.example's placeholder, and long enough not to be guessed (DEPLOY.md makes 64 characters)
MIN_SECRET_KEY = 32
SECRET_KEY_PLACEHOLDERS = {"change-me-to-a-long-random-text"}


def _secret_key():
    """
    Signs the login cookie. From the SECRET_KEY environment variable (servers, Docker); on a
    development machine, made once and kept in instance/secret_key so logins survive restarts.
    """
    if os.environ.get("SECRET_KEY"):
        key = os.environ["SECRET_KEY"]
        if key in SECRET_KEY_PLACEHOLDERS or len(key) < MIN_SECRET_KEY:
            raise SystemExit(f"SECRET_KEY must be a long random text, at least {MIN_SECRET_KEY} characters "
                             '(not the example\'s): python -c "import secrets; print(secrets.token_hex(32))"')
        return key
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
# Where a daily run's problems (a store failed or half-broken) are e-mailed; on a server nobody
# sees the Windows notification. Needs SMTP_HOST too
ALERT_EMAIL = os.environ.get("ALERT_EMAIL", "")
