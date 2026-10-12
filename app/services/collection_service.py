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

from sqlalchemy import delete, func, select

from app.models import (
    COLLECTION_KINDS, FORMATS, NOW, PLAY_STATUSES, CollectionItem, Game, GameEdition, GameReview, Listing, Platform,
    PsnSkip, SteamSkip, User, fields,
)
from db import session

MAX_ITEMS = 2000
MAX_NOTES = 1000
MAX_HOURS = Decimal("99999.9")
# "In demand" (user, 2026-10-11): games this many users wish for, at least; one wish is never shown
# (a wishlist is private)
MIN_WISHERS = 2
# The profile's showcase (user, 2026-10-11): sections the user shows, in their order (users.profile_sections)
SHOWCASE = ("favourites", "most_played", "most_valuable", "achievements")
SHOWCASE_SIZE = 5           # games in each section but the favourites
MAX_FAVOURITES = 10
# An edition the user names (user, 2026-10-11: "Lumière Edition", which neither the stores nor IGDB list)
MIN_EDITION_NAME, MAX_EDITION_NAME = 2, 100


class CollectionError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def collection(user_id):
    """{items, stats, public, wish_alerts, profile_sections}: the user's collection with each edition's prices."""
    with session() as s:
        user = s.get(User, user_id)
        items = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id)
                          .order_by(CollectionItem.kind, CollectionItem.updated_at.desc(), CollectionItem.id.desc())).all()
        rows = [fields(i, "id", "kind", "format", "status", "hours", "notes", "achievements", "achievements_total",
                       "platinum", "psn_id", "favourite_rank", "wish_price", "edition_id", "game_id", "created_at", "updated_at") for i in items]
        public, alerts, sections = user.collection_public, user.wish_alerts, sections_of(user.profile_sections)
        # the user's review score of each game (one per game, as on the game page); a hidden one can't change
        reviews = {game_id: (score, hidden) for game_id, score, hidden in s.execute(
            select(GameReview.game_id, GameReview.score, GameReview.hidden).where(GameReview.user_id == user_id))}
        steam = dict(s.execute(select(Game.id, Game.steam_app_id).where(
            Game.id.in_({r["game_id"] for r in rows}), Game.steam_app_id > 0)).all()) if rows else {}
    for r in rows:
        r["score"], r["score_locked"] = reviews.get(r["game_id"], (None, False))
        r["steam_app_id"] = steam.get(r["game_id"])          # "Ver na Steam" (a PC game)
    rows = with_prices(rows)                       # stats() needs the prices
    return {"items": rows, "stats": stats(rows), "public": public, "wish_alerts": alerts, "profile_sections": sections}


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
        "completed": sum(r["status"] == "finished" for r in owned),
        # achievements over the games that have a total (as a share of all their achievements)
        "achievements": sum(r["achievements"] or 0 for r in owned if r["achievements_total"]),
        "achievements_total": sum(r["achievements_total"] for r in owned if r["achievements_total"]),
    }


def named_edition(s, game_id, name):
    """
    The game's edition with this name (its key: "Lumiere Edition" is "Lumière Edition"), made if
    there's none: an edition the user owns or wants that no store sells. Only shown on the game page
    once a store sells it (game_service.get_game), so a typo stays in the user's collection.
    """
    from app.services.listing_service import _edition_named
    from core.editions import is_excluded
    name = " ".join((name or "").split())
    if not MIN_EDITION_NAME <= len(name) <= MAX_EDITION_NAME or is_excluded(name):
        raise CollectionError("edition_name_invalid")
    if not s.get(Game, _int(game_id)):
        raise CollectionError("not_found", 404)
    return _edition_named(s, int(game_id), name)


def add(user_id, edition_id, kind, game_id=None, new_edition=None, **changes):
    """
    Add an edition to the collection or the wishlist (the item, or the existing one); new_edition:
    the name of the game_id's edition the user has, when it isn't one we know (named_edition). An
    owned edition is one item per format (physical unless said): a disc and a download are two.
    """
    if kind not in COLLECTION_KINDS:
        raise CollectionError("kind_invalid")
    with session() as s:
        if new_edition:
            edition_id = named_edition(s, game_id, new_edition)
        edition = s.get(GameEdition, _int(edition_id))
        if not edition:
            raise CollectionError("not_found", 404)
        if kind == "owned" and changes.get("format") not in (*FORMATS, None):
            raise CollectionError("format_invalid")
        format = (changes.get("format") or "physical") if kind == "owned" else None
        item = s.scalars(select(CollectionItem).where(CollectionItem.user_id == user_id, CollectionItem.kind == kind,
                                                      CollectionItem.edition_id == edition.id,
                                                      CollectionItem.format.is_not_distinct_from(format))).first()
        if item is None:
            if s.query(CollectionItem).filter(CollectionItem.user_id == user_id).count() >= MAX_ITEMS:
                raise CollectionError("collection_full")
            item = CollectionItem(user_id=user_id, game_id=edition.game_id, edition_id=edition.id, kind=kind,
                                  format=format, status="owned" if kind == "owned" else None,
                                  wish_price=best_new_price(edition.id) if kind == "wishlist" else None)
            if kind == "wishlist":    # alerts from the price it was wished at (wish_alert_service)
                item.alert_price, item.alert_checked_at = item.wish_price, NOW
            s.add(item)
        _apply(item, changes)
        s.flush()
        if kind == "owned" and edition.game.steam_app_id:      # added by hand: Steam imports take it again
            s.execute(delete(SteamSkip).where(SteamSkip.user_id == user_id, SteamSkip.app_id == edition.game.steam_app_id))
        if kind == "owned":       # the same for the PSN import
            s.execute(delete(PsnSkip).where(PsnSkip.user_id == user_id, PsnSkip.edition_id == edition.id))
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
        if changes.get("edition_id") or changes.get("new_edition"):         # the edition they really have
            _move_to_edition(s, item, changes.get("edition_id"), changes.get("new_edition"))
        if changes.get("kind") == "owned" and item.kind == "wishlist":    # "I bought it"
            if _other(s, item, "owned", "physical"):
                s.delete(item)                   # already owned: the wish is just done
                return None
            item.kind, item.format, item.status, item.wish_price = "owned", "physical", "owned", None
        if item.kind == "owned" and changes.get("format") in FORMATS and _other(s, item, "owned", changes["format"]):
            raise CollectionError("already_in_collection", 409)     # that copy is there already
        _apply(item, changes)
        item.updated_at = NOW
        return item.id


def _move_to_edition(s, item, edition_id, new_edition):
    """Another edition of the item's game (one we know, or one the user names)."""
    if new_edition:
        edition_id = named_edition(s, item.game_id, new_edition)
    edition = s.get(GameEdition, _int(edition_id))
    if not edition or edition.game_id != item.game_id:
        raise CollectionError("edition_invalid")
    if edition.id != item.edition_id and _other(s, item, item.kind, item.format, edition.id):
        raise CollectionError("already_in_collection", 409)
    item.edition_id = edition.id


def _other(s, item, kind, format, edition_id=None):
    """The user's other item of this kind and format on the item's edition (or that one), if any."""
    return s.scalars(select(CollectionItem.id).where(
        CollectionItem.user_id == item.user_id, CollectionItem.kind == kind, CollectionItem.id != item.id,
        CollectionItem.edition_id == (edition_id or item.edition_id),
        CollectionItem.format.is_not_distinct_from(format))).first()


def best_new_price(edition_id):
    """The edition's cheapest new copy in stock at a store now, or None."""
    from app.services.game_service import editions_with_offers
    groups = editions_with_offers([edition_id])
    prices = [o["price"] for g in groups for o in g["offers"] if o["in_stock"] and o["condition"] == "new"]
    return Decimal(str(min(prices))) if prices else None


def remove(user_id, item_id):
    """Take an item out; an owned game on Steam isn't imported from Steam again (SteamSkip: user
    2026-10-11, games marked private on Steam), nor one imported from PSN (PsnSkip: played on PS Plus).
    User, 2026-10-12: a removed imported game never comes back, also after changing its format: a
    digital one, or any once the user imports from Steam."""
    with session() as s:
        item = _own(s, user_id, item_id)
        on_steam = item.format == "digital" or bool(s.get(User, user_id).steam_id)
        app_id = item.game.steam_app_id if item.kind == "owned" and on_steam else None
        if app_id and not s.get(SteamSkip, (user_id, app_id)):
            s.add(SteamSkip(user_id=user_id, app_id=app_id))
        psn_id = item.psn_id if item.kind == "owned" else None
        if psn_id and not s.get(PsnSkip, (user_id, psn_id)):
            s.add(PsnSkip(user_id=user_id, psn_id=psn_id, edition_id=item.edition_id))
        s.delete(item)
    return {"ok": True, "steam_skipped": bool(app_id), "psn_skipped": bool(psn_id)}


def set_settings(user_id, changes):
    """{public?, wish_alerts?, lang?}: show the collection on the profile; wishlist e-mails, in this language."""
    from app.services.auth_service import LANGS
    with session() as s:
        user = s.get(User, user_id)
        if "public" in changes:
            user.collection_public = bool(changes["public"])
        if "wish_alerts" in changes:
            user.wish_alerts = bool(changes["wish_alerts"])
        if changes.get("lang") in LANGS:
            user.lang = changes["lang"]
        return {"public": user.collection_public, "wish_alerts": user.wish_alerts}


def public_collection(username):
    """A user's collection as their profile shows it, or None when it's private (or no such user)."""
    with session() as s:
        user = s.scalars(select(User).where(User.named(username), User.is_active)).first()
        if not user or not user.collection_public:
            return None
        user_id = user.id
    data = collection(user_id)
    keep = ("kind", "status", "format", "edition_id", "game_id", "name", "name_en", "platform", "platform_name", "image",
            "best_price", "used", "hours", "achievements", "achievements_total", "platinum")
    return {"items": [{k: r[k] for k in keep} for r in data["items"]], "stats": data["stats"],
            "showcase": showcase(data["items"], data["profile_sections"])}


def sections_of(value):
    """The showcase sections a user chose, in order (None: never chose: all of them)."""
    if value is None:
        return list(SHOWCASE)
    return [s for s in value.split(",") if s in SHOWCASE]


def showcase(rows, sections):
    """
    The profile's sections from the owned items, in the user's order, empty ones left out:
    [{section, items: [{game_id, name, name_en, platform_name, image, hours, value, achievements, achievements_total}]}]
    value = what it's worth now (best new store price, else the cheapest used copy).
    """
    owned = [r for r in rows if r["kind"] == "owned"]
    for r in owned:
        r["value"] = r["best_price"] if r["best_price"] is not None else (r["used"] or {}).get("price")
    share = lambda r: r["achievements"] / r["achievements_total"]
    picks = {
        "favourites": sorted((r for r in owned if r["favourite_rank"]), key=lambda r: r["favourite_rank"])[:MAX_FAVOURITES],
        "most_played": sorted((r for r in owned if r["hours"]), key=lambda r: (-r["hours"], r["id"]))[:SHOWCASE_SIZE],
        "most_valuable": sorted((r for r in owned if r["value"]), key=lambda r: (-r["value"], r["id"]))[:SHOWCASE_SIZE],
        "achievements": sorted((r for r in owned if r["achievements_total"] and r["achievements"]),
                               key=lambda r: (-share(r), -r["achievements"], r["id"]))[:SHOWCASE_SIZE],
    }
    keep = ("game_id", "name", "name_en", "platform_name", "image", "hours", "value", "achievements", "achievements_total")
    return [{"section": s, "items": [{k: r[k] for k in keep} for r in picks[s]]} for s in sections if picks[s]]


def set_showcase(user_id, sections, favourites):
    """The user's showcase: sections (in order, from SHOWCASE) and the top 10 (owned item ids, in order)."""
    if not isinstance(sections, list) or not isinstance(favourites, list) or len(set(map(str, sections))) != len(sections)             or any(s not in SHOWCASE for s in sections):
        raise CollectionError("showcase_invalid")
    try:
        ids = [_int(i) for i in favourites]
    except CollectionError:
        raise CollectionError("showcase_invalid")
    if len(ids) > MAX_FAVOURITES or len(set(ids)) != len(ids):
        raise CollectionError("showcase_invalid")
    with session() as s:
        owned = {i.id: i for i in s.scalars(select(CollectionItem).where(
            CollectionItem.user_id == user_id, CollectionItem.kind == "owned"))}
        if any(i not in owned for i in ids):
            raise CollectionError("showcase_invalid")
        for item in owned.values():
            rank = ids.index(item.id) + 1 if item.id in ids else None
            if item.favourite_rank != rank:
                item.favourite_rank = rank
        s.get(User, user_id).profile_sections = ",".join(sections)
    return {"profile_sections": sections, "favourites": ids}


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
        item.status = (changes["status"] or "owned") if item.kind == "owned" else None
    if "hours" in changes:
        item.hours = _hours(changes["hours"])
    if "achievements" in changes or "achievements_total" in changes:
        done = _count(changes.get("achievements", item.achievements))
        total = _count(changes.get("achievements_total", item.achievements_total))
        if done is not None and total is not None and done > total:
            raise CollectionError("achievements_invalid")
        item.achievements, item.achievements_total = (done, total) if item.kind == "owned" else (None, None)
    if "platinum" in changes:                  # PlayStation (None: the game has none, or not said)
        item.platinum = None if changes["platinum"] in (None, "") or item.kind != "owned" else bool(changes["platinum"])
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
    if not hours.is_finite() or not 0 <= hours <= MAX_HOURS:            # "NaN" gets past quantize()
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


def _wishers():
    """Users (active) wishing for each game, from MIN_WISHERS up: a select of (game_id, wishers)."""
    return (select(CollectionItem.game_id, func.count(func.distinct(CollectionItem.user_id)).label("wishers"))
            .join(User, User.id == CollectionItem.user_id)
            .where(CollectionItem.kind == "wishlist", User.is_active)
            .group_by(CollectionItem.game_id)
            .having(func.count(func.distinct(CollectionItem.user_id)) >= MIN_WISHERS))


def wanted_by(game_id):
    """How many users wish for this game (0 under MIN_WISHERS), for the game page's "N procuram"."""
    with session() as s:
        row = s.execute(_wishers().where(CollectionItem.game_id == game_id)).first()
    return row.wishers if row else 0


def in_demand(limit=12):
    """
    The games most users are looking for (user, 2026-10-11: a reason to sell one), for /sell:
    [{game_id, name, name_en, platform, platform_name, image, wishers, used}], used = copies for
    sale now. Most wished first, then the ones nobody sells.
    """
    from app.services.common import IGDB_COVER
    wishers = _wishers().subquery()
    used = (select(GameEdition.game_id, func.count().label("used"))
            .join(Listing, Listing.edition_id == GameEdition.id).join(User, User.id == Listing.user_id)
            .where(Listing.status == "active", User.is_active).group_by(GameEdition.game_id).subquery())
    with session() as s:
        rows = s.execute(
            select(Game, Platform.code, Platform.name, wishers.c.wishers, func.coalesce(used.c.used, 0).label("used"))
            .join(wishers, wishers.c.game_id == Game.id).join(Platform, Platform.id == Game.platform_id)
            .outerjoin(used, used.c.game_id == Game.id)
            .order_by(wishers.c.wishers.desc(), func.coalesce(used.c.used, 0), Game.title, Game.id).limit(limit)).all()
        return [{"game_id": g.id, "name": g.title, "name_en": g.title_en or None, "platform": code, "platform_name": name,
                 "image": IGDB_COVER.format(g.cover_image_id) if g.cover_image_id else g.image_url,
                 "wishers": n, "used": u} for g, code, name, n, u in rows]
