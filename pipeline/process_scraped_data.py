import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, update

from app.models import NOW, Game, GameEdition, MatchOverride, Platform, PriceSnapshot, Store, StoreProduct
from core.editions import is_excluded
from db import json_or_none, session
from pipeline.deduplicator import deduplicate
from pipeline.matcher import MATCH_ONLY_STORES, GameMatcher

log = logging.getLogger(__name__)

CENT = Decimal("0.01")


def process_products(store_slug, products, full_catalog=True):
    """
    Save one store's scraped products: link each to a game, add or update it in
    store_products and record its price. Everything is one transaction.

    full_catalog=True means `products` is the store's whole catalogue, so
    products not seen in this run are marked inactive (removed from the store).
    "Código na caixa" products are skipped (core.editions.is_excluded). A MATCH_ONLY_STORES
    store's products only link to games and editions that already exist.
    """
    scraped = deduplicate(products)
    products = [p for p in scraped if not is_excluded(p["external_name"])]
    stats = {
        "products": len(products), "excluded": len(scraped) - len(products),
        "new_products": 0, "price_changes": 0, "deactivated": 0,
    }

    with session() as s:
        store = s.scalars(select(Store).where(Store.slug == store_slug)).first()
        if not store:
            raise ValueError(f"Store '{store_slug}' is not in the stores table (see database/seed_stores.sql)")

        run_started_at = s.scalar(select(NOW))
        platform_ids = dict(s.execute(select(Platform.code, Platform.id)).all())
        matcher = GameMatcher(s, platform_ids)
        create = store_slug not in MATCH_ONLY_STORES
        if create:
            matcher.learn(p["external_name"] for p in products)

        # The store's products and their latest prices, loaded once
        known = {product_key(sp.url, sp.condition): sp
                 for sp in s.scalars(select(StoreProduct).where(StoreProduct.store_id == store.id))}
        latest = latest_prices(s, store.id)
        pinned = pinned_editions(s, StoreProduct.store_id == store.id)

        for p in products:
            if len(p["url"]) > 800:
                log.warning("[%s] URL too long, skipped: %s", store_slug, p["url"][:100])
                continue

            sp = known.get(product_key(p["url"], p["condition"]))
            # a product a moderator pinned to an edition stays there (app/services/match_service.py),
            # on its game's platform (the store may list it on another platform's page)
            if sp is not None and sp.id in pinned:
                game_id, edition_id = pinned[sp.id]
                platform_id = s.get(Game, game_id).platform_id
            else:
                game_id, edition_id = matcher.match(p, create)
                platform_id = platform_ids.get(p["console"])
            if sp is None:
                sp = StoreProduct(store_id=store.id, url=p["url"], condition=p["condition"])
                s.add(sp)
                known[product_key(p["url"], p["condition"])] = sp
                stats["new_products"] += 1
            update_product(sp, p, game_id, edition_id, platform_id)
            if sp.id is None:
                s.flush()       # its id, for the price snapshot

            # Only a row when price or stock changed since the last snapshot, so the table holds
            # the price history without a copy per scrape
            price = (to_cents(p["price"]), to_cents(p["old_price"]), bool(p["in_stock"]))
            if latest.get(sp.id) != price:
                s.add(PriceSnapshot(store_product_id=sp.id, price=price[0], old_price=price[1], in_stock=price[2]))
                latest[sp.id] = price
                stats["price_changes"] += 1

        if full_catalog and products:
            s.flush()
            stats["deactivated"] = s.execute(
                update(StoreProduct)
                .where(StoreProduct.store_id == store.id, StoreProduct.is_active, StoreProduct.last_seen_at < run_started_at)
                .values(is_active=False)
                .execution_options(synchronize_session=False)
            ).rowcount

    return stats


def update_product(sp, p, game_id, edition_id, platform_id):
    """Set a store product from what the scraper read now (`p`)."""
    sp.game_id, sp.edition_id, sp.platform_id = game_id, edition_id, platform_id
    sp.external_name = p["external_name"][:300]
    sp.image_url = (p.get("image") or "")[:1000] or None
    sp.is_preorder = bool(p.get("is_preorder", False))
    # keep the known date when this run didn't read one (e.g. the game came out and the store hid it)
    release_date = as_date(p.get("release_date"))
    if release_date is not None or sp.id is None:
        sp.release_date = release_date
    if p.get("release_date_checked", False):
        sp.release_date_checked_at = NOW
    # descriptions are only sent when the product page was read: keep the stored one otherwise
    checked = p.get("details_checked", False)
    if checked or sp.id is None:
        sp.description = p.get("description")
        sp.details = json_or_none(p.get("details"))
        sp.image_urls = json_or_none(p.get("images"))
    if checked:
        sp.details_checked_at = NOW
    sp.last_seen_at = NOW
    sp.is_active = True


def pinned_editions(s, *where):
    """{store_product_id: (game_id, edition_id)} of the products pinned by a moderator (match_overrides)."""
    rows = s.execute(select(MatchOverride.store_product_id, GameEdition.game_id, GameEdition.id)
                     .join(GameEdition, GameEdition.id == MatchOverride.edition_id)
                     .join(StoreProduct, StoreProduct.id == MatchOverride.store_product_id).where(*where))
    return {sp_id: (game_id, edition_id) for sp_id, game_id, edition_id in rows}


def latest_prices(s, store_id):
    """{store_product_id: (price, old_price, in_stock)}: the latest snapshot of each of the store's products."""
    ranked = (select(PriceSnapshot.store_product_id, PriceSnapshot.price, PriceSnapshot.old_price, PriceSnapshot.in_stock,
                     func.row_number().over(partition_by=PriceSnapshot.store_product_id,
                                            order_by=(PriceSnapshot.scraped_at.desc(), PriceSnapshot.id.desc())).label("n"))
              .join(StoreProduct, StoreProduct.id == PriceSnapshot.store_product_id)
              .where(StoreProduct.store_id == store_id).subquery())
    return {r.store_product_id: (r.price, r.old_price, bool(r.in_stock))
            for r in s.execute(select(ranked).where(ranked.c.n == 1))}


def product_key(url, condition):
    """How the database tells store products apart: URL and condition, ignoring case and trailing spaces."""
    return url.rstrip(" ").lower(), condition.rstrip(" ").lower()


def to_cents(price):
    """A price in cents, as the numeric(10,2) column keeps it: the float's exact value rounded half up
    (1.005 as a float is 1.00499…, so 1.00), as SQL Server stored prices before the move to PostgreSQL."""
    return None if price is None else Decimal(price).quantize(CENT, ROUND_HALF_UP)


def as_date(value):
    """A release date from a scraper ("2026-11-12" or a date), or None."""
    return date.fromisoformat(value[:10]) if isinstance(value, str) and value else value or None
