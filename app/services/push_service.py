"""
Push notifications on phones and computers (user, 2026-10-16), also with the site closed: Web Push, through
each browser's own push service (Google's, Mozilla's, Apple's), signed with the site's VAPID key. A user
turns them on per device in Settings > Notificações (static/pages/account.js); the browser then gives an
address and keys (PushSubscription), and static/sw.js shows what arrives. The morning run sends the
wishlist's news (wish_alert_service) here as well as by e-mail.
iPhone / iPad: only when the site is added to the home screen (iOS 16.4+).

The key: VAPID_PRIVATE_KEY (servers, Docker: python -m app.services.push_service makes one); on a
development machine made once and kept in instance/vapid_private.pem. A new key means every device has
to turn them on again.
"""
import json
import logging
import os

from sqlalchemy import delete, select

from app import config
from app.models import PushSubscription, User
from db import session

log = logging.getLogger(__name__)

MAX_DEVICES = 10                 # per user: an old phone's subscription goes when an 11th comes
MAX_FIELD = {"endpoint": 1000, "p256dh": 200, "auth": 100}
TTL = 24 * 3600                  # a phone that's off for a day misses it (the e-mail and the bell still have it)
TIMEOUT = 10
# The settings page's test notification, in the user's language
TEST = {"pt": "As notificações estão ligadas neste dispositivo.", "en": "Notifications are on for this device."}
_vapid = None


class PushError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def vapid():
    """The site's VAPID key (py_vapid.Vapid01): from VAPID_PRIVATE_KEY, else instance/vapid_private.pem."""
    global _vapid
    if _vapid is None:
        from py_vapid import Vapid01
        if os.environ.get("VAPID_PRIVATE_KEY"):
            _vapid = Vapid01.from_string(os.environ["VAPID_PRIVATE_KEY"])
        elif os.environ.get("SECRET_KEY"):
            # a server (its secrets come from .env): the site and the scheduler run in containers that don't
            # share instance/, so a key made here would differ between them
            log.error("Push notifications need VAPID_PRIVATE_KEY in .env (python -m app.services.push_service)")
            raise PushError("push_unavailable", 503)
        else:
            path = config.INSTANCE_DIR / "vapid_private.pem"
            if not path.exists():
                config.INSTANCE_DIR.mkdir(exist_ok=True)
                key = Vapid01()
                key.generate_keys()
                key.save_key(str(path))
            _vapid = Vapid01.from_file(str(path))
    return _vapid


def public_key():
    """The key browsers check our messages with (applicationServerKey), base64url."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid.utils import b64urlencode
    return b64urlencode(vapid().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


def subject():
    """Who to contact about our messages (push services ask for it; Apple's refuses localhost addresses)."""
    if os.environ.get("VAPID_SUBJECT"):
        return os.environ["VAPID_SUBJECT"]
    if config.MAIL_FROM:
        return f"mailto:{config.MAIL_FROM.split('<')[-1].strip('> ')}"
    return config.SITE_URL if config.SITE_URL.startswith("https://") else "mailto:push@saveongames.invalid"


def subscribe(user_id, subscription):
    """Keep a device's subscription ({endpoint, keys: {p256dh, auth}}, as the browser gives it) for this user;
    one the device had for another user (who logged out without turning it off) moves to this one."""
    if not isinstance(subscription, dict) or not isinstance(subscription.get("keys"), dict):
        raise PushError("push_invalid")
    fields = {"endpoint": subscription.get("endpoint"), **{k: subscription["keys"].get(k) for k in ("p256dh", "auth")}}
    if any(not isinstance(v, str) or not v or len(v) > MAX_FIELD[k] for k, v in fields.items()) \
            or not fields["endpoint"].startswith("https://"):
        raise PushError("push_invalid")
    with session() as s:
        row = s.scalars(select(PushSubscription).where(PushSubscription.endpoint == fields["endpoint"])).first()
        if row is None:
            row = PushSubscription(user_id=user_id, **fields)
            s.add(row)
        else:
            row.user_id, row.p256dh, row.auth = user_id, fields["p256dh"], fields["auth"]
        s.flush()
        mine = s.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user_id)
                         .order_by(PushSubscription.id.desc())).all()
        if len(mine) > MAX_DEVICES:
            s.execute(delete(PushSubscription).where(PushSubscription.id.in_(mine[MAX_DEVICES:])))
    return {"ok": True}


def unsubscribe(user_id, endpoint):
    """This device stops getting them (turned off, or logging out)."""
    with session() as s:
        s.execute(delete(PushSubscription).where(PushSubscription.user_id == user_id,
                                                 PushSubscription.endpoint == str(endpoint or "")))
    return {"ok": True}


def devices(user_id):
    """How many devices the user gets them on."""
    with session() as s:
        return len(s.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user_id)).all())


def send(user_id, title, body, url="/", tag=None):
    """Send a notification to every device of the user; how many took it. A device the push service says is
    gone (404 / 410: the app was removed, notifications blocked) is forgotten."""
    from pywebpush import WebPushException, webpush
    with session() as s:
        if not s.scalar(select(User.is_active).where(User.id == user_id)):
            return 0
        rows = [(r.id, {"endpoint": r.endpoint, "keys": {"p256dh": r.p256dh, "auth": r.auth}}) for r in s.scalars(
            select(PushSubscription).where(PushSubscription.user_id == user_id).order_by(PushSubscription.id))]
    data = json.dumps({"title": title, "body": body, "url": url, "tag": tag})
    sent, gone = 0, []
    for row_id, info in rows:
        try:
            webpush(info, data, vapid_private_key=vapid(), vapid_claims={"sub": subject()}, ttl=TTL, timeout=TIMEOUT)
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                gone.append(row_id)
            else:
                log.warning("Push to user %s not sent: %s", user_id, e)
        except Exception as e:          # one device's network trouble mustn't stop the others
            log.warning("Push to user %s not sent: %s", user_id, e)
    if gone:
        with session() as s:
            s.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
    return sent


def send_test(user_id):
    """The settings page's "Enviar um teste": how many devices took it."""
    with session() as s:
        lang = s.scalar(select(User.lang).where(User.id == user_id))
    return send(user_id, "SaveOnGames", TEST.get(lang, TEST["pt"]), "/account#notifications", tag="test")


if __name__ == "__main__":
    # A key for a server's .env (VAPID_PRIVATE_KEY=…): python -m app.services.push_service
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    from py_vapid import Vapid01
    from py_vapid.utils import b64urlencode
    key = Vapid01()
    key.generate_keys()
    print("VAPID_PRIVATE_KEY=" + b64urlencode(key.private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())))
