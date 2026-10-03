"""
A user's game collection: editions they own (physical / digital, play status, hours,
achievements, notes) and a wishlist. Each item shows the edition's current prices (stores, used
copies, a real discount, the historical low); a wish also remembers the price it was added at, so
a drop shows. A wish on sale, at its historical low or cheaper than when added is a good deal
(counted on the 📚 header button). Statistics: per platform and
status, hours, and what the owned games are worth today. Private unless the user makes it
public (it then shows on their profile). When games / editions are merged, items follow
(pipeline/rematch.py).
"""
from collections import Counter
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from app.models import COLLECTION_KINDS, FORMATS, NOW, PLAY_STATUSES, CollectionItem, GameEdition, User, fields
from db import session

MAX_ITEMS = 2000
MAX_NOTES = 1000
MAX_HOURS = Decimal("99999.9")


class CollectionError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def collection(user_id):
    """{items, stats, public}: the user's collection with each edition's prices."""
    with session() as s:
        user = s.get(User, user_id)
        items = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id)
                          .order_by(CollectionItem.kind, CollectionItem.updated_at.desc())).all()
        rows = [fields(i, "id", "kind", "format", "status", "hours", "notes", "achievements", "achievements_total",
                       "wish_price", "edition_id", "game_id", "created_at", "updated_at") for i in items]
        public = user.collection_public
    rows = with_prices(rows)                       # stats() needs the prices
    return {"items": rows, "stats": stats(rows), "public": public}


def with_prices(rows):
    """Add each item's edition (name, platform, cover) and current prices; for wishes, whether it's a good deal."""
    from app.services.game_service import editions_with_offers     # game_service → listing_service → …
    prices = {g["edition_id"]: g for g in editions_with_offers(list({r["edition_id"] for r in rows}))}
    for r in rows:
        g = prices.get(r["edition_id"], {})
        offers = [o for o in g.get("offers", []) if o["in_stock"] and o["condition"] == "new"]
        best = min(offers, key=lambda o: o["price"]) if offers else None
        r.update(name=g.get("name"), name_en=g.get("name_en"), platform=g.get("console"),
                 platform_name=g.get("platform_name"), image=g.get("image"),
                 best_price=best["price"] if best else None, best_store=best["store_name"] if best else None,
                 on_sale=any(o["is_discount"] for o in offers),
                 at_historical_low=g.get("at_historical_low", False), used=g.get("used"))
        wished = r.get("wish_price")
        r["price_drop"] = round(wished - r["best_price"], 2) if wished and best and best["price"] < wished else None
        r["good_deal"] = r["kind"] == "wishlist" and bool(r["on_sale"] or r["at_historical_low"] or r["price_drop"])
    return rows


def good_deals(user_id):
    """{count, items}: the wishes that are a good deal now (on sale, at the historical low, cheaper than
    when added), for the 📚 header button."""
    with session() as s:
        rows = [fields(i, "id", "kind", "edition_id", "game_id", "wish_price") for i in s.scalars(
            select(CollectionItem).where(CollectionItem.user_id == user_id, CollectionItem.kind == "wishlist"))]
    deals = [r for r in with_prices(rows) if r["good_deal"]] if rows else []
    return {"count": len(deals), "items": [{k: r[k] for k in ("id", "name", "best_price", "price_drop")} for r in deals]}


def item_ids(user_id):
    """{edition_id: {kind: item id}}: what the user has, for the game page's Tenho / Quero buttons."""
    with session() as s:
        rows = s.execute(select(CollectionItem.edition_id, CollectionItem.kind, CollectionItem.id)
                         .where(CollectionItem.user_id == user_id)).all()
    result = {}
    for edition_id, kind, item_id in rows:
        result.setdefault(edition_id, {})[kind] = item_id
    return result


def stats(rows):
    """Per platform / status counts, total hours, and what the owned games are worth today:
    new (the best store price in stock) and used (the cheapest copy users sell), where known."""
    owned = [r for r in rows if r["kind"] == "owned"]
    new_prices = [r["best_price"] for r in owned if r["best_price"] is not None]
    used_prices = [r["used"]["price"] for r in owned if r.get("used")]
    return {
        "owned": len(owned),
        "wishlist": len(rows) - len(owned),
        "platforms": Counter(r["platform_name"] for r in owned if r["platform_name"]).most_common(),
        "statuses": dict(Counter(r["status"] for r in owned if r["status"])),
        "hours": float(sum(r["hours"] or 0 for r in owned)),
        "worth_new": round(sum(new_prices), 2), "priced_new": len(new_prices),
        "worth_used": round(sum(used_prices), 2), "priced_used": len(used_prices),
        "completed": sum(r["status"] in ("completed", "platinum") for r in owned),
        # achievements over the games that have a total (as a share of all their achievements)
        "achievements": sum(r["achievements"] or 0 for r in owned if r["achievements_total"]),
        "achievements_total": sum(r["achievements_total"] for r in owned if r["achievements_total"]),
    }


def add(user_id, edition_id, kind, **changes):
    """Add an edition to the collection or the wishlist (the item, or the existing one)."""
    if kind not in COLLECTION_KINDS:
        raise CollectionError("kind_invalid")
    with session() as s:
        edition = s.get(GameEdition, _int(edition_id))
        if not edition:
            raise CollectionError("not_found", 404)
        item = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id, CollectionItem.kind == kind,
                                                      CollectionItem.edition_id == edition.id)).first()
        if item is None:
            if s.query(CollectionItem).filter(CollectionItem.user_id == user_id).count() >= MAX_ITEMS:
                raise CollectionError("collection_full")
            item = CollectionItem(user_id=user_id, game_id=edition.game_id, edition_id=edition.id, kind=kind,
                                  format="physical" if kind == "owned" else None,
                                  wish_price=best_new_price(edition.id) if kind == "wishlist" else None)
            s.add(item)
        _apply(item, changes)
        s.flush()
        if kind == "owned":       # bought it: off the wishlist
            for wanted in s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id,
                                                                 CollectionItem.kind == "wishlist",
                                                                 CollectionItem.edition_id == edition.id)):
                s.delete(wanted)
        return item.id


def add_wishes(user_id, edition_ids):
    """
    Put these editions on the wishlist: the favourites browsers kept before accounts (they were
    folded into the wishlist). Merged editions become the one that replaced them; unknown ones,
    and editions already wished or owned, are skipped. {added}
    """
    from app.services.game_service import merged_into
    try:
        ids = list(dict.fromkeys(int(i) for i in edition_ids))[:MAX_ITEMS]
    except (TypeError, ValueError):
        raise CollectionError("edition_invalid")
    merged = merged_into("edition", ids)
    ids = list(dict.fromkeys(merged.get(i, i) for i in ids))
    with session() as s:
        known = set(s.scalars(select(GameEdition.id).where(GameEdition.id.in_(ids)))) if ids else set()
        have = set(s.scalars(select(CollectionItem.edition_id).where(CollectionItem.user_id == user_id)))
    added = 0
    for edition_id in ids:
        if edition_id in known and edition_id not in have:
            add(user_id, edition_id, "wishlist")
            added += 1
    return {"added": added}


def update(user_id, item_id, changes):
    with session() as s:
        item = _own(s, user_id, item_id)
        if changes.get("kind") == "owned" and item.kind == "wishlist":    # "I bought it"
            if s.scalars(select(CollectionItem.id).where(CollectionItem.user_id == user_id, CollectionItem.kind == "owned",
                                                         CollectionItem.edition_id == item.edition_id)).first():
                s.delete(item)                   # already owned: the wish is just done
                return None
            item.kind, item.format, item.wish_price = "owned", "physical", None
        _apply(item, changes)
        item.updated_at = NOW
        return item.id


def best_new_price(edition_id):
    """The edition's cheapest new copy in stock at a store now, or None."""
    from app.services.game_service import editions_with_offers
    groups = editions_with_offers([edition_id])
    prices = [o["price"] for g in groups for o in g["offers"] if o["in_stock"] and o["condition"] == "new"]
    return Decimal(str(min(prices))) if prices else None


def remove(user_id, item_id):
    with session() as s:
        s.delete(_own(s, user_id, item_id))
    return {"ok": True}


def set_public(user_id, public):
    with session() as s:
        s.get(User, user_id).collection_public = bool(public)
    return {"public": bool(public)}


def public_collection(username):
    """A user's collection as their profile shows it, or None when it's private (or no such user)."""
    with session() as s:
        user = s.scalars(select(User).where(User.username == username, User.is_active)).first()
        if not user or not user.collection_public:
            return None
        user_id = user.id
    data = collection(user_id)
    keep = ("kind", "status", "format", "edition_id", "game_id", "name", "name_en", "platform", "platform_name", "image",
            "best_price", "used")
    return {"items": [{k: r[k] for k in keep} for r in data["items"]], "stats": data["stats"]}


def _own(s, user_id, item_id):
    item = s.get(CollectionItem, _int(item_id))
    if not item or item.user_id != user_id:
        raise CollectionError("not_found", 404)
    return item


def _apply(item, changes):
    """Set the editable fields that are in `changes`, checked."""
    if "format" in changes:
        if changes["format"] not in (*FORMATS, None):
            raise CollectionError("format_invalid")
        item.format = changes["format"] if item.kind == "owned" else None
    if "status" in changes:
        if changes["status"] not in (*PLAY_STATUSES, None, ""):
            raise CollectionError("play_status_invalid")
        item.status = (changes["status"] or None) if item.kind == "owned" else None
    if "hours" in changes:
        item.hours = _hours(changes["hours"])
    if "achievements" in changes or "achievements_total" in changes:
        done = _count(changes.get("achievements", item.achievements))
        total = _count(changes.get("achievements_total", item.achievements_total))
        if done is not None and total is not None and done > total:
            raise CollectionError("achievements_invalid")
        item.achievements, item.achievements_total = (done, total) if item.kind == "owned" else (None, None)
    if "notes" in changes:
        notes = (changes["notes"] or "").strip() or None
        if notes and len(notes) > MAX_NOTES:
            raise CollectionError("notes_long")
        item.notes = notes


def _hours(value):
    if value in (None, ""):
        return None
    try:
        hours = Decimal(str(value).replace(",", ".")).quantize(Decimal("0.1"))
    except InvalidOperation:
        raise CollectionError("hours_invalid")
    if not 0 <= hours <= MAX_HOURS:
        raise CollectionError("hours_invalid")
    return hours


def _count(value):
    """A number of achievements: a whole number from 0 to 99999, or None when empty."""
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise CollectionError("achievements_invalid")
    if not 0 <= number <= 99999:
        raise CollectionError("achievements_invalid")
    return number


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise CollectionError("not_found", 404)
