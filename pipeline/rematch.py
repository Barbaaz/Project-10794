"""
Re-link every store product to its game and edition with the current matching rules,
refresh game titles / edition names, then delete games and editions nothing points
to anymore. No scraping involved.
Run it after changing core/normalizer.py, core/editions.py or core/close_match.py:

    python -m pipeline.rematch --dry-run     # list what would be merged, change nothing
    python -m pipeline.rematch

A game or edition whose products all went to another one is recorded in merged_ids
(old links and favourites saved in browsers follow it), and its IGDB information is
kept when the game it went to has none.
"""
import argparse
import logging
from collections import Counter, defaultdict

from sqlalchemy import delete, exists, insert, literal, select, update
from sqlalchemy.orm import aliased

from app.models import (
    CollectionItem, Favorite, Game, GameEdition, GameReview, Listing, MergedId, Platform, Store, StoreProduct,
)
from core.editions import edition_key_of, is_excluded
from db import session
from pipeline.igdb import IGDB_COLUMNS
from pipeline.matcher import MATCH_ONLY_STORES, GameMatcher
from pipeline.process_scraped_data import pinned_editions

log = logging.getLogger(__name__)

# A merged game / edition: its model, and the column store products and listings point to it with
KINDS = {"game": (Game, "game_id"), "edition": (GameEdition, "edition_id")}


def rematch_all(dry_run=False):
    with session() as s:
        platform_ids = dict(s.execute(select(Platform.code, Platform.id)).all())
        codes = {v: k for k, v in platform_ids.items()}
        match_only = set(s.scalars(select(Store.id).where(Store.slug.in_(MATCH_ONLY_STORES))))
        products = s.scalars(select(StoreProduct).order_by(StoreProduct.id)).all()
        pinned = pinned_editions(s)       # moderators' pins: these products stay where they are

        rekeyed = rekey_editions(s)
        matcher = GameMatcher(s, platform_ids)
        changed = 0
        game_titles = defaultdict(Counter)      # {game_id: Counter of titles from its products}
        edition_names = defaultdict(Counter)
        moves = {"game": defaultdict(Counter), "edition": defaultdict(Counter)}   # {old id: Counter(new ids)}

        for sp in products:
            old_game, old_edition = sp.game_id, sp.edition_id
            if is_excluded(sp.external_name):
                if (old_game, old_edition, sp.is_active) == (None, None, False):
                    continue
                sp.game_id, sp.edition_id, sp.is_active = None, None, False
                changed += 1
                continue

            if sp.id in pinned:
                (game_id, edition_id), title, edition_name = pinned[sp.id], None, None    # names: as they are
            else:
                product = {"external_name": sp.external_name, "console": codes.get(sp.platform_id), "image": sp.image_url}
                game_id, edition_id, title, edition_name = matcher.match_details(product, sp.store_id not in match_only)

            if game_id:
                if title:
                    game_titles[game_id][title] += 1
                if edition_name:
                    edition_names[edition_id][edition_name] += 1

            if (game_id, edition_id) != (old_game, old_edition):
                sp.game_id, sp.edition_id = game_id, edition_id
                changed += 1
                if old_game and game_id and old_game != game_id:
                    moves["game"][old_game][game_id] += 1
                if old_edition and edition_id and old_edition != edition_id:
                    moves["edition"][old_edition][edition_id] += 1

        renamed = refresh_names(s, Game, "title", 300, game_titles)
        renamed += refresh_names(s, GameEdition, "name", 200, edition_names)
        merged = record_merges(s, moves)
        if dry_run:
            report(s, merged)      # before the merged rows are deleted: it shows their names
        removed = delete_orphans(s)

        log.info("Rematched %d products, %d changed, %d edition keys updated in place, %d names refreshed, "
                 "merged %s, removed %s", len(products), changed, rekeyed, renamed,
                 {k: len(v) for k, v in merged.items()}, removed)
        if dry_run:
            s.rollback()     # session() commits what's left at the end: nothing
            log.info("Dry run: nothing was changed")
    return changed, merged, removed


def rekey_editions(s):
    """
    Bring stored edition keys to the current key rules in place ("limited collectors" →
    "collectors limited", "game of the year" → "goty"), so an edition keeps its id when only
    its key's spelling changed. Where the new key is already taken in that game, the
    rematch merges the two (and records it).
    """
    editions = s.scalars(select(GameEdition).order_by(GameEdition.id)).all()
    taken = {(e.game_id, e.edition_key) for e in editions}
    updated = 0
    for e in editions:
        words, *tags = e.edition_key.split("|")
        new = "|".join([edition_key_of(words)] + tags)
        if new != e.edition_key and (e.game_id, new) not in taken:
            taken.discard((e.game_id, e.edition_key))
            taken.add((e.game_id, new))
            e.edition_key = new
            updated += 1
    s.flush()
    return updated


def no_store_product(model, column):
    """Condition: no store product points to this row of `model` (by store_products.`column`)."""
    return ~exists().where(getattr(StoreProduct, column) == model.id)


def record_merges(s, moves):
    """
    {kind: {old_id: new_id}} for games / editions left with no product, whose products went
    to another one. Saved in merged_ids (older redirects to them follow along); a merged game's
    IGDB information goes to the game that replaced it if that one has none.
    """
    s.flush()
    merged = {}
    for kind, (model, column) in KINDS.items():
        # left without store products: merged, whatever users point to (that moves along below)
        orphans = set(s.scalars(select(model.id).where(no_store_product(model, column))))
        merged[kind] = {old: targets.most_common(1)[0][0] for old, targets in moves[kind].items() if old in orphans}

        for old, new in merged[kind].items():
            s.execute(update(MergedId).where(MergedId.kind == kind, MergedId.new_id == old).values(new_id=new))
            s.execute(delete(MergedId).where(MergedId.kind == kind, MergedId.old_id == old))
            s.execute(insert(MergedId).values(kind=kind, old_id=old, new_id=new))
            # what users point to moves to the one that replaced it: listings, favourites
            s.execute(update(Listing).where(getattr(Listing, column) == old).values({column: new}))
            if kind == "edition":
                other = aliased(Favorite)
                s.execute(insert(Favorite).from_select(
                    ["user_id", "edition_id"],
                    select(Favorite.user_id, literal(new)).where(
                        Favorite.edition_id == old,
                        ~exists().where(other.user_id == Favorite.user_id, other.edition_id == new))))
                s.execute(delete(Favorite).where(Favorite.edition_id == old))
                # collection items too (one per user and kind: a copy they already have there wins),
                # with the game of the edition they now point to
                mine = aliased(CollectionItem)
                s.execute(delete(CollectionItem).where(CollectionItem.edition_id == old, exists().where(
                    mine.user_id == CollectionItem.user_id, mine.kind == CollectionItem.kind, mine.edition_id == new)))
                s.execute(update(CollectionItem).where(CollectionItem.edition_id == old).values(
                    edition_id=new,
                    game_id=select(GameEdition.game_id).where(GameEdition.id == new).scalar_subquery()))
            else:
                s.execute(update(CollectionItem).where(CollectionItem.game_id == old).values(game_id=new))
                # players' reviews too (one per user and game: a review they already wrote there wins)
                theirs = aliased(GameReview)
                s.execute(delete(GameReview).where(GameReview.game_id == old, exists().where(
                    theirs.user_id == GameReview.user_id, theirs.game_id == new)))
                s.execute(update(GameReview).where(GameReview.game_id == old).values(game_id=new))

    for old, new in merged["game"].items():
        replaced, replacement = s.get(Game, old), s.get(Game, new)
        if replacement.igdb_id is None and replaced.igdb_id is not None:
            for c in (*IGDB_COLUMNS, "igdb_checked_at"):
                setattr(replacement, c, getattr(replaced, c))
    s.flush()
    return merged


def report(s, merged):
    """Print the merges of a dry run, for a person to check."""
    titles = dict(s.execute(select(Game.id, Game.title)).all())
    for old, new in sorted(merged["game"].items(), key=lambda m: titles.get(m[1], "")):
        print(f"GAME     {titles.get(old, old)!s:55} → {titles.get(new)}")
    names = {r.id: (r.title, r.name) for r in s.execute(
        select(GameEdition.id, Game.title, GameEdition.name).join(Game, Game.id == GameEdition.game_id))}
    for old, new in sorted(merged["edition"].items(), key=lambda m: names.get(m[1], ("", ""))):
        game, name = names.get(new, ("?", "?"))
        print(f"EDITION  {game[:40]:40} {names.get(old, (None, old))[1]!s:35} → {name}")


def refresh_names(s, model, column, max_len, candidates):
    """
    Set each row's display name to the most common one among its products,
    preferring mixed case ("Silent Hill: Townfall" over "SILENT HILL TOWNFALL").
    """
    rows = {row.id: row for row in s.scalars(select(model))}
    renamed = 0

    for row_id, names in candidates.items():
        best = max(names, key=lambda n: (not n.isupper(), names[n], n))[:max_len]
        row = rows.get(row_id)
        if row is not None and getattr(row, column) != best:
            setattr(row, column, best)
            renamed += 1

    return renamed


def delete_orphans(s):
    """Editions and games that no store product, listing, favourite or collection uses."""
    s.flush()
    editions = s.execute(
        delete(GameEdition).where(
            no_store_product(GameEdition, "edition_id"),
            ~exists().where(Listing.edition_id == GameEdition.id),
            ~exists().where(Favorite.edition_id == GameEdition.id),
            ~exists().where(CollectionItem.edition_id == GameEdition.id),
        ).execution_options(synchronize_session=False)
    ).rowcount

    games = s.execute(
        delete(Game).where(
            no_store_product(Game, "game_id"),
            ~exists().where(Listing.game_id == Game.id),
            ~exists().where(GameEdition.game_id == Game.id),
            ~exists().where(CollectionItem.game_id == Game.id),
            ~exists().where(GameReview.game_id == Game.id),
        ).execution_options(synchronize_session=False)
    ).rowcount

    return {"editions": editions, "games": games}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list the merges, change nothing")
    args = parser.parse_args()
    from scheduler.jobs import setup_logging
    setup_logging()
    rematch_all(dry_run=args.dry_run)
