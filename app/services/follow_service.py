"""
Users following each other and comparing collections (user, 2026-10-12). Following is one way and
quiet (no e-mail, nothing for the one followed but a count); who a user follows is theirs to see.
A comparison sets the owned games of two users side by side: the games both have, and the ones
only one has, with hours, achievements / trophies and platinums. The other user's collection must
be public, as for their profile; wishlists are never compared.
"""
from sqlalchemy import delete, func, select

from app.models import Follow, Game, User
from app.services import collection_service
from db import session

MAX_FOLLOWING = 1000


class FollowError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def _user(s, username):
    user = s.scalars(select(User).where(User.named(username or ""), User.is_active)).first()
    if not user:
        raise FollowError("not_found", 404)
    return user


def follow(user_id, username):
    with session() as s:
        other = _user(s, username)
        if other.id == user_id:
            raise FollowError("follow_self")
        if not s.get(Follow, (user_id, other.id)):
            if s.scalar(select(func.count()).select_from(Follow).where(Follow.follower_id == user_id)) >= MAX_FOLLOWING:
                raise FollowError("following_full")
            s.add(Follow(follower_id=user_id, followed_id=other.id))
    return {"following": True}


def unfollow(user_id, username):
    with session() as s:
        other = _user(s, username)
        s.execute(delete(Follow).where(Follow.follower_id == user_id, Follow.followed_id == other.id))
    return {"following": False}


def counts(username, viewer_id=None):
    """{followers, following, followed (the viewer follows them)} for a profile."""
    with session() as s:
        user = _user(s, username)
        active = select(User.id).where(User.is_active)
        return {
            "followers": s.scalar(select(func.count()).select_from(Follow).where(
                Follow.followed_id == user.id, Follow.follower_id.in_(active))),
            "following": s.scalar(select(func.count()).select_from(Follow).where(
                Follow.follower_id == user.id, Follow.followed_id.in_(active))),
            "followed": bool(viewer_id and s.get(Follow, (viewer_id, user.id))),
        }


def following(user_id):
    """[{username, display_name, collection_public}] the user follows, by name (blocked / deleted ones left out)."""
    with session() as s:
        rows = s.execute(select(User.username, User.display_name, User.collection_public)
                         .join(Follow, Follow.followed_id == User.id)
                         .where(Follow.follower_id == user_id, User.is_active)
                         .order_by(func.lower(User.username), User.id)).all()
    return [{"username": u, "display_name": d, "collection_public": p} for u, d, p in rows]


def _side(user_id):
    """The user's owned games, one per game across platforms and copies: {key: game}."""
    items = [i for i in collection_service.collection(user_id)["items"] if i["kind"] == "owned"]
    with session() as s:
        known = {g: (igdb, key) for g, igdb, key in s.execute(
            select(Game.id, Game.igdb_id, Game.normalized_title).where(Game.id.in_({i["game_id"] for i in items})))} \
            if items else {}
    games = {}
    for i in items:
        igdb, key = known.get(i["game_id"], (None, None))
        game = games.setdefault(("igdb", igdb) if igdb else ("name", key or i["game_id"]), {
            "game_id": i["game_id"], "name": i["name"], "name_en": i["name_en"], "image": i["image"],
            "platforms": [], "hours": None, "achievements": None, "achievements_total": None, "platinum": False,
            "finished": False})
        if i["platform_name"] and i["platform_name"] not in game["platforms"]:
            game["platforms"].append(i["platform_name"])
        if i["hours"]:
            game["hours"] = round((game["hours"] or 0) + i["hours"], 1)
        # the achievements of the copy furthest along (two platforms have two lists)
        if i["achievements_total"] and (game["achievements_total"] is None or
                                        (i["achievements"] or 0) / i["achievements_total"] >
                                        (game["achievements"] or 0) / game["achievements_total"]):
            game["achievements"], game["achievements_total"] = i["achievements"] or 0, i["achievements_total"]
        game["platinum"] = game["platinum"] or bool(i["platinum"])
        game["finished"] = game["finished"] or i["status"] == "finished"
    return games


def _summary(games):
    with_total = [g for g in games.values() if g["achievements_total"]]
    return {"games": len(games), "finished": sum(g["finished"] for g in games.values()),
            "hours": round(sum(g["hours"] or 0 for g in games.values()), 1),
            "achievements": sum(g["achievements"] or 0 for g in with_total),
            "achievements_total": sum(g["achievements_total"] for g in with_total),
            "platinums": sum(g["platinum"] for g in games.values())}


def compare(viewer_id, username):
    """
    The viewer's collection beside a user's: {me, them: {username, display_name, summary}, both:
    [{name, image, game_id, me: game, them: game}], only_me: [game], only_them: [game]}; both by
    hours played together, the others by name.
    """
    with session() as s:
        other = _user(s, username)
        if other.id != viewer_id and not other.collection_public:
            raise FollowError("collection_private", 403)
        me = s.get(User, viewer_id)
        people = [(u.id, {"username": u.username, "display_name": u.display_name}) for u in (me, other)]
    (my_id, me_info), (their_id, them_info) = people
    mine, theirs = _side(my_id), _side(their_id)
    by_name = lambda g: (g["name"] or "").lower()
    both = [{"name": mine[k]["name"], "name_en": mine[k]["name_en"], "image": mine[k]["image"] or theirs[k]["image"],
             "game_id": mine[k]["game_id"], "me": mine[k], "them": theirs[k]} for k in mine.keys() & theirs.keys()]
    both.sort(key=lambda b: (-((b["me"]["hours"] or 0) + (b["them"]["hours"] or 0)), by_name(b)))
    return {"me": {**me_info, "summary": _summary(mine)}, "them": {**them_info, "summary": _summary(theirs)},
            "both": both,
            "only_me": sorted((g for k, g in mine.items() if k not in theirs), key=by_name),
            "only_them": sorted((g for k, g in theirs.items() if k not in mine), key=by_name)}
