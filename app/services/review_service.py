"""
Players' reviews of games. Any logged-in user scores a game on one platform from 1 to 10 (the
PS5 and Switch versions are separate games), with an optional title and text; one review per
user and game, which they can change or delete. Reviews a moderator hid, and those of blocked
users, aren't shown or counted. A hidden review can't be changed or deleted by its writer (as a
hidden listing: otherwise deleting and writing it again would undo the hide). When games are
merged, reviews follow (pipeline/rematch.py).
"""
from sqlalchemy import Numeric, cast, func, or_, select

from app.models import NOW, CollectionItem, Game, GameReview, User, fields
from db import session

MAX_TITLE = 120
MAX_TEXT = 4000
PER_PAGE = 20


class ReviewError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def _visible(game_id):
    """Shown and counted: this game's reviews (any game's with None), not hidden, by users who aren't
    blocked; a deleted account's stay, without the name (user, 2026-10-07: anonymised)."""
    query = select(GameReview).join(User, User.id == GameReview.user_id).where(
        ~GameReview.hidden, or_(User.is_active, User.deleted_at.is_not(None)))
    return query if game_id is None else query.where(GameReview.game_id == game_id)


def reviews(game_id, user_id=None, page=1):
    """
    {summary, mine, reviews, page, pages}: the summary (average to one decimal, count, how many
    gave each score 1–10), the user's own review (also when hidden, so they know), and a page of
    the shown reviews, newest first; `owner` marks writers who have the game in their collection.
    """
    with session() as s:
        if not s.get(Game, game_id):
            raise ReviewError("not_found", 404)
        visible = _visible(game_id).subquery()
        counts = dict(s.execute(select(visible.c.score, func.count()).group_by(visible.c.score)).all())
        count = sum(counts.values())
        average = s.scalar(select(cast(func.avg(cast(visible.c.score, Numeric(4, 2))), Numeric(3, 1))))
        summary = {"average": float(average) if count else None, "count": count,
                   "distribution": [counts.get(score, 0) for score in range(1, 11)]}

        rows = s.scalars(_visible(game_id).order_by(GameReview.created_at.desc(), GameReview.id.desc())
                         .offset((page - 1) * PER_PAGE).limit(PER_PAGE)).all()
        owners = set(s.scalars(select(CollectionItem.user_id).where(
            CollectionItem.game_id == game_id, CollectionItem.kind == "owned",
            CollectionItem.user_id.in_([r.user_id for r in rows] or [0]))))
        mine = user_id and s.scalars(select(GameReview).where(GameReview.game_id == game_id,
                                                              GameReview.user_id == user_id)).first()
        return {
            "summary": summary,
            "mine": mine and _review(mine, mine.user_id in owners) | {"hidden": mine.hidden},
            "reviews": [_review(r, r.user_id in owners, mine=r.user_id == user_id) for r in rows],
            "page": page,
            "pages": max(1, -(-count // PER_PAGE)),
        }


def _review(review, owner, **extra):
    return fields(review, "id", "score", "title", "body", "created_at", "updated_at",
                  username=review.user.username, display_name=review.user.display_name, owner=owner,
                  edited=review.updated_at > review.created_at, **extra)


def mark_review_scores(groups):
    """Set `review_score` (average to one decimal) and `review_count` on catalogue cards (dicts with game_id), in one query."""
    ids = list({g["game_id"] for g in groups if g.get("game_id")})
    scores = {}
    if ids:
        visible = _visible(None).where(GameReview.game_id.in_(ids)).subquery()
        average = cast(func.avg(cast(visible.c.score, Numeric(4, 2))), Numeric(3, 1))
        with session() as s:
            scores = {game_id: (float(avg), count) for game_id, avg, count in s.execute(
                select(visible.c.game_id, average, func.count()).group_by(visible.c.game_id))}
    for g in groups:
        g["review_score"], g["review_count"] = scores.get(g.get("game_id"), (None, 0))
    return groups


def reviews_of_user(user_id, limit=50):
    """A user's shown reviews, newest first, with the game they're about (their public profile)."""
    with session() as s:
        rows = s.scalars(select(GameReview).where(GameReview.user_id == user_id, ~GameReview.hidden)
                         .order_by(GameReview.created_at.desc(), GameReview.id.desc()).limit(limit)).all()
        return [fields(r, "id", "game_id", "score", "title", "body", "created_at",
                       game=r.game.title, platform=r.game.platform.code, platform_name=r.game.platform.name,
                       edited=r.updated_at > r.created_at) for r in rows]


def save(user_id, game_id, score, title=None, body=None):
    """Write or change the user's review of this game (the page's reviews afterwards)."""
    try:
        score = int(score)
    except (TypeError, ValueError):
        raise ReviewError("score_invalid")
    if not 1 <= score <= 10:
        raise ReviewError("score_invalid")
    title = (title or "").strip() or None
    body = (body or "").strip() or None
    if title and len(title) > MAX_TITLE:
        raise ReviewError("review_title_long")
    if body and len(body) > MAX_TEXT:
        raise ReviewError("review_text_long")

    with session() as s:
        if not s.get(Game, game_id):
            raise ReviewError("not_found", 404)
        review = s.scalars(select(GameReview).where(GameReview.user_id == user_id,
                                                    GameReview.game_id == game_id)).first()
        if review is None:
            s.add(GameReview(user_id=user_id, game_id=game_id, score=score, title=title, body=body))
        elif review.hidden:
            raise ReviewError("review_hidden", 403)
        elif (review.score, review.title, review.body) != (score, title, body):
            review.score, review.title, review.body, review.updated_at = score, title, body, NOW
    return reviews(game_id, user_id)


def set_score(user_id, game_id, score):
    """
    Only the score, from the collection page: a review's title and text stay as written on the
    game page. No score ("") takes the review away, unless it has text (deleted on the game
    page then, where the text shows). {score}
    """
    with session() as s:
        review = s.scalars(select(GameReview).where(GameReview.user_id == user_id,
                                                    GameReview.game_id == game_id)).first()
        title, body = (review.title, review.body) if review else (None, None)
    if score in (None, ""):
        if review is None:
            return {"score": None}
        if title or body:
            raise ReviewError("review_has_text")
        delete(user_id, game_id)
        return {"score": None}
    save(user_id, game_id, score, title, body)
    return {"score": int(score)}


def delete(user_id, game_id):
    with session() as s:
        review = s.scalars(select(GameReview).where(GameReview.user_id == user_id,
                                                    GameReview.game_id == game_id)).first()
        if not review:
            raise ReviewError("not_found", 404)
        if review.hidden:
            raise ReviewError("review_hidden", 403)
        s.delete(review)
    return reviews(game_id, user_id)
