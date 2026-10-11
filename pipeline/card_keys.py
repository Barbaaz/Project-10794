"""
Which games share a front-page card across platforms under different names (games.card_key, see
core/similar_names.card_keys): worked out again after every run, as new games and IGDB matches come in.

    python -m pipeline.card_keys
"""
import logging

from sqlalchemy import select

from app.models import Game
from core.similar_names import card_keys
from db import session

log = logging.getLogger(__name__)


def refresh():
    """Sets games.card_key; returns how many games share another name's card."""
    with session() as s:
        games = s.scalars(select(Game).where(Game.kind == "game").order_by(Game.id)).all()
        keys = card_keys([(g.id, g.platform_id, g.normalized_title, g.igdb_id, g.title) for g in games])
        for g in games:
            if g.card_key != keys.get(g.id):
                g.card_key = keys.get(g.id)
    return len(keys)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("%d games share a card with another platform's name", refresh())
