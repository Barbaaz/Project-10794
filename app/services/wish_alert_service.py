"""
Wishlist alerts by e-mail, after the morning run (scheduler/run_all_scrapers.py): one message
per user listing the wishes that changed since the last check, each for one reason:
- back in stock: no store had a new copy in stock, now one has
- historical low / price drop: the best new price fell by at least MIN_DROP and MIN_DROP_SHARE
  (small moves aren't news; they add up until they are)
Each wish keeps the best price at the last check (alert_price), so the same change is sent once.
Users switch them off on /collection or with the link in every message. Until an e-mail
provider is set (mail_service), messages are only logged.
"""
import logging
from decimal import Decimal

from sqlalchemy import select

from app import config
from app.models import NOW, CollectionItem, User
from app.services import mail_service
from db import session

log = logging.getLogger(__name__)

MIN_DROP = Decimal("1.00")
MIN_DROP_SHARE = Decimal("0.05")
BATCH = 500           # editions priced per query

MAIL = {
    "pt": {
        "subject": {1: "Lista de desejos: 1 jogo com novidades", "n": "Lista de desejos: {n} jogos com novidades"},
        "hello": "Olá {name},\n\nHá novidades em jogos da sua lista de desejos:\n",
        "back_in_stock": "de novo em stock: {price} na {store}",
        "price_drop": "desceu de {old} para {price} na {store}",
        "historical_low": "mínimo histórico: {price} na {store} (antes {old})",
        "footer": "\nVer a lista de desejos: {wishlist}\n\nPara não receber estes emails: {off}\n",
    },
    "en": {
        "subject": {1: "Wishlist: news on 1 game", "n": "Wishlist: news on {n} games"},
        "hello": "Hello {name},\n\nThere's news on games on your wishlist:\n",
        "back_in_stock": "back in stock: {price} at {store}",
        "price_drop": "down from {old} to {price} at {store}",
        "historical_low": "historical low: {price} at {store} (was {old})",
        "footer": "\nSee your wishlist: {wishlist}\n\nTo stop these emails: {off}\n",
    },
}


def _tokens():
    from itsdangerous import URLSafeSerializer
    return URLSafeSerializer(config.SECRET_KEY, salt="wish-alerts-off")


def off_link(user_id):
    """The link in each message that switches the alerts off (no log-in needed, never expires)."""
    return f"{config.SITE_URL}/collection?alerts_off={_tokens().dumps(user_id)}"


def switch_off(token):
    """Switch a user's alerts off from the e-mailed link; False for a bad link."""
    from itsdangerous import BadSignature
    try:
        user_id = _tokens().loads(token or "")
    except BadSignature:
        return False
    with session() as s:
        user = s.get(User, user_id) if isinstance(user_id, int) else None
        if not user:
            return False
        user.wish_alerts = False
    return True


def change(old, new, checked, at_low):
    """
    (reason or None, price to remember) for one wish: old = the remembered price (None: was out
    of stock), new = the best new price now (None: out of stock), checked = whether it was
    checked before (a first check only remembers).
    """
    if new is None:
        return None, None
    if not checked:
        return None, new
    if old is None:
        return "back_in_stock", new
    if old - new >= max(MIN_DROP, old * MIN_DROP_SHARE):
        return ("historical_low" if at_low else "price_drop"), new
    if new < old:
        return None, old          # a small drop: remembered from the old price, so drops add up
    return None, new


def check_all():
    """Check every wish of users with alerts on, e-mail those with news. {users, items, sent}"""
    from app.services.collection_service import with_prices
    with session() as s:
        rows = s.execute(
            select(CollectionItem.id, CollectionItem.user_id, CollectionItem.edition_id, CollectionItem.game_id,
                   CollectionItem.alert_price, CollectionItem.alert_checked_at)
            .join(User, User.id == CollectionItem.user_id)
            .where(CollectionItem.kind == "wishlist", User.is_active, User.wish_alerts)
            .order_by(CollectionItem.user_id, CollectionItem.id)).all()
        users = {u.id: (u.email, u.display_name or u.username, u.lang) for u in s.scalars(
            select(User).where(User.id.in_({r.user_id for r in rows})))} if rows else {}

    items = [{"id": r.id, "user_id": r.user_id, "edition_id": r.edition_id, "game_id": r.game_id, "kind": "wishlist",
              "old": r.alert_price, "checked": r.alert_checked_at is not None} for r in rows]
    for start in range(0, len(items), BATCH):
        with_prices(items[start:start + BATCH])

    news, remember = {}, {}
    for item in items:
        new = Decimal(str(item["best_price"])) if item["best_price"] is not None else None
        reason, remember[item["id"]] = change(item["old"], new, item["checked"], item["at_historical_low"])
        if reason:
            news.setdefault(item["user_id"], []).append((reason, item))

    sent = 0
    for user_id, changed in news.items():
        email, name, lang = users[user_id]
        try:
            mail_service.send(email, *message(user_id, name, lang, changed))
            sent += 1
        except Exception as e:          # one bad address mustn't stop the others; its news is sent next time
            log.warning("Wishlist alert to user %s not sent: %s", user_id, e)
            for _, item in changed:
                remember[item["id"]] = item["old"]

    with session() as s:
        for item_id, price in remember.items():
            s.query(CollectionItem).filter(CollectionItem.id == item_id).update(
                {"alert_price": price, "alert_checked_at": NOW}, synchronize_session=False)
    return {"users": len(news), "items": sum(len(c) for c in news.values()), "sent": sent}


def message(user_id, name, lang, changed):
    """(subject, text) of one user's alert."""
    words = MAIL.get(lang, MAIL["pt"])
    n = len(changed)
    subject = words["subject"][1] if n == 1 else words["subject"]["n"].format(n=n)
    lines = [words["hello"].format(name=name)]
    for reason, item in changed:
        title = (item.get("name_en") or item["name"]) if lang == "en" else item["name"]
        platform = f" ({item['platform_name']})" if item.get("platform_name") else ""
        detail = words[reason].format(price=money(item["best_price"], lang), old=money(item["old"], lang),
                                      store=item["best_store"])
        lines.append(f"- {title}{platform}: {detail}\n  {config.SITE_URL}/game/{item['game_id']}")
    lines.append(words["footer"].format(wishlist=f"{config.SITE_URL}/collection?tab=wishlist", off=off_link(user_id)))
    return subject, "\n".join(lines)


def money(value, lang):
    if value is None:
        return ""
    text = f"{Decimal(str(value)):.2f}"
    return f"{text.replace('.', ',')} €" if lang == "pt" else f"€{text}"
