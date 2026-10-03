"""
Fixing wrong matches by hand (moderators, the "Correspondências" tab of /admin). A store
product moved to another edition is pinned there (match_overrides): the daily processing and
`python -m pipeline.rematch` leave it alone. An edition or game a move leaves empty is merged
into where its products went, as the rematch does (merged_ids, collection items and listings follow).
Unpinning lets the next rematch decide again.
"""
from collections import Counter, defaultdict

from sqlalchemy import delete, select

from app.models import Game, GameEdition, MatchOverride, ModerationLog, Store, StoreProduct
from app.services.common import clear_cache
from app.services.moderation_service import ModerationError
from core.editions import edition_key_of
from core.normalizer import normalize_name
from db import session

MAX_GAMES = 15
MAX_PRODUCTS = 50          # products moved in one go


def find(q):
    """Games whose title has every word of q (at most MAX_GAMES), each with its editions and their
    store products (pinned or not), for a moderator to check and fix."""
    words = normalize_name(q or "").split()
    if not words:
        return []
    with session() as s:
        games = s.scalars(select(Game).where(*[Game.normalized_title.like(f"%{w}%") for w in words])
                          .order_by(Game.title).limit(MAX_GAMES)).all()
        ids = [g.id for g in games]
        editions = s.scalars(select(GameEdition).where(GameEdition.game_id.in_(ids)).order_by(GameEdition.id)).all() if ids else []
        products = s.execute(
            select(StoreProduct, Store.name).join(Store, Store.id == StoreProduct.store_id)
            .where(StoreProduct.game_id.in_(ids)).order_by(Store.name, StoreProduct.external_name)).all() if ids else []
        pinned = set(s.scalars(select(MatchOverride.store_product_id).where(
            MatchOverride.store_product_id.in_([p.id for p, _ in products])))) if products else set()

        def product(p, store):
            return {"id": p.id, "store": store, "name": p.external_name, "url": p.url, "is_active": p.is_active,
                    "pinned": p.id in pinned}
        return [{
            "id": g.id, "title": g.title, "title_en": g.title_en or "", "platform": g.platform.name,
            "editions": [{"id": e.id, "name": e.name, "key": e.edition_key,
                          "products": [product(p, store) for p, store in products if p.edition_id == e.id]}
                         for e in editions if e.game_id == g.id],
        } for g in games]


def move(moderator_id, product_ids, edition_id=None, game_id=None, new_edition=None):
    """
    Move store products to an edition and pin them there: an existing edition (edition_id), or a
    new one of game `game_id` named `new_edition` (the game's edition with the same key if it
    already has one). Returns the target edition's id.
    """
    product_ids = list(dict.fromkeys(int(i) for i in product_ids or []))
    if not product_ids or len(product_ids) > MAX_PRODUCTS:
        raise ModerationError("products_invalid")
    from pipeline.rematch import delete_orphans, record_merges     # pipeline code, only needed here

    with session() as s:
        products = s.scalars(select(StoreProduct).where(StoreProduct.id.in_(product_ids))).all()
        if len(products) != len(product_ids):
            raise ModerationError("not_found", 404)
        target = _target_edition(s, edition_id, game_id, new_edition)

        moves = {"game": defaultdict(Counter), "edition": defaultdict(Counter)}
        for sp in products:
            if sp.game_id and sp.game_id != target.game_id:
                moves["game"][sp.game_id][target.game_id] += 1
            if sp.edition_id and sp.edition_id != target.id:
                moves["edition"][sp.edition_id][target.id] += 1
            sp.game_id, sp.edition_id = target.game_id, target.id
            s.merge(MatchOverride(store_product_id=sp.id, edition_id=target.id, created_by=moderator_id))
            s.add(ModerationLog(moderator_id=moderator_id, action="move_product", kind="product", target_id=sp.id,
                                note=f"→ #{target.id} {target.name} ({target.game.title})"[:500]))
        record_merges(s, moves)          # what's left empty goes where its products went
        delete_orphans(s)
        target_id = target.id
    clear_cache()
    return target_id


def _target_edition(s, edition_id, game_id, new_edition):
    if edition_id:
        edition = s.get(GameEdition, int(edition_id))
        if not edition:
            raise ModerationError("not_found", 404)
        return edition
    name = (new_edition or "").strip()
    game = s.get(Game, int(game_id)) if game_id else None
    if not game or not name or len(name) > 200:
        raise ModerationError("new_edition_invalid")
    key = edition_key_of(normalize_name(name))
    edition = s.scalars(select(GameEdition).where(GameEdition.game_id == game.id, GameEdition.edition_key == key)).first()
    if edition is None:
        edition = GameEdition(game_id=game.id, edition_key=key, name=name)
        s.add(edition)
        s.flush()
    return edition


def set_title_en(moderator_id, game_id, title):
    """
    A game's English name, shown when the page is in English ("" = the store's title). A
    moderator's name is kept: the IGDB fill only fills games that have none.
    """
    title = (title or "").strip()
    if len(title) > 300:
        raise ModerationError("title_en_invalid")
    with session() as s:
        game = s.get(Game, int(game_id))
        if not game:
            raise ModerationError("not_found", 404)
        game.title_en = title
        s.add(ModerationLog(moderator_id=moderator_id, action="rename_game_en", kind="game", target_id=game.id,
                            note=f"{game.title} → {title or '(store title)'}"[:500]))
    clear_cache()
    return {"title_en": title}


def unpin(moderator_id, product_id):
    """Remove a pin: the next rematch matches the product again by its name."""
    with session() as s:
        if not s.execute(delete(MatchOverride).where(MatchOverride.store_product_id == product_id)).rowcount:
            raise ModerationError("not_found", 404)
        s.add(ModerationLog(moderator_id=moderator_id, action="unpin_product", kind="product", target_id=product_id))
    return {"ok": True}


def pins():
    """Every pinned product: where it is, who pinned it."""
    with session() as s:
        rows = s.execute(
            select(MatchOverride, StoreProduct.external_name, Store.name, GameEdition.name, Game.title, Game.id)
            .join(StoreProduct, StoreProduct.id == MatchOverride.store_product_id)
            .join(Store, Store.id == StoreProduct.store_id)
            .join(GameEdition, GameEdition.id == MatchOverride.edition_id)
            .join(Game, Game.id == GameEdition.game_id)
            .order_by(MatchOverride.created_at.desc())).all()
        return [{"product_id": o.store_product_id, "name": name, "store": store, "edition": edition,
                 "edition_id": o.edition_id, "game": title, "game_id": gid}
                for o, name, store, edition, title, gid in rows]
