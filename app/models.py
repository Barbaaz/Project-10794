"""
The tables as SQLAlchemy models:
- the marketplace (users, listings and their photos, conversations and messages,
  ratings, moderation, collection, reviews): Alembic manages these tables (migrations/, MARKET_TABLES)
- the catalogue and prices (platforms, stores, games, editions, store products, price
  snapshots, merged ids): the pipeline writes them (pipeline/); their tables are made by
  database/*.sql, which these models follow

The price analysis queries (the current_offers view, windows, "latest price per product")
stay SQL: they're reports that read better as SQL.
Times are UTC, without a time zone, set by the database (utcnow(), database/schema.sql).
"""
import json

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Unicode, UnicodeText,
    UniqueConstraint, false, func, text, true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NOW = func.utcnow()      # the database's clock, in UTC (database/schema.sql)


# The tables Alembic manages (migrations/); the others belong to the price side (database/*.sql)
MARKET_TABLES = {"users", "user_listings", "listing_photos", "conversations", "messages", "message_photos",
                 "user_ratings", "reports", "moderation_log", "match_overrides",
                 "collection_items", "game_reviews", "duplicate_dismissals", "steam_skips",
                 "psn_skips", "follows", "igdb_addons", "push_subscriptions"}

# The header bell's notifications (collection_service.good_deals): on at all; which wish deals count (a real
# discount, the historical low, cheaper than when added); the smallest discount / drop, in %, that counts
NOTIFY_DEFAULTS = {"bell": True, "sale": True, "low": True, "drop": True, "min_discount": 0}
MIN_DISCOUNTS = (0, 10, 20, 30, 50)

# user: buys and sells; moderator: also handles reports; admin: also names / removes moderators
ROLES = ("user", "moderator", "admin")


class Base(DeclarativeBase):
    pass


def created_at():
    return mapped_column(DateTime, server_default=NOW, nullable=False)


# --- catalogue and prices (database/schema.sql; written by pipeline/) ----------------------

class Platform(Base):
    __tablename__ = "platforms"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(Unicode(100))


class Store(Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(Unicode(200))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    title: Mapped[str] = mapped_column(Unicode(300))
    normalized_title: Mapped[str] = mapped_column(Unicode(300))     # the game key (core/editions.py)
    steam_app_id: Mapped[int | None] = mapped_column(Integer)      # PC: its Steam app (0: none; pipeline/igdb.fill_steam_ids)
    card_key: Mapped[str | None] = mapped_column(Unicode(300))     # front-page card, when another platform's name (pipeline/card_keys.py)
    kind: Mapped[str] = mapped_column(String(12), server_default="game")   # game / console (core/hardware.py)
    title_en: Mapped[str | None] = mapped_column(Unicode(300))      # English name (IGDB / moderators)
    title_fixed: Mapped[bool] = mapped_column(Boolean, default=False)  # title corrected by a moderator: kept
    image_url: Mapped[str | None] = mapped_column(Unicode(1000))
    created_at = created_at()
    created_by: Mapped[int | None] = mapped_column(Integer)   # a user who created it from IGDB (no store sells it)
    # From IGDB (pipeline/igdb.py, IGDB_COLUMNS)
    igdb_id: Mapped[int | None] = mapped_column(Integer)
    igdb_checked_at = mapped_column(DateTime)
    summary: Mapped[str | None] = mapped_column(UnicodeText)
    genres: Mapped[str | None] = mapped_column(Unicode(500))
    publishers: Mapped[str | None] = mapped_column(Unicode(500))
    developers: Mapped[str | None] = mapped_column(Unicode(500))
    first_release_date = mapped_column(Date)
    rating: Mapped[int | None] = mapped_column(Integer)          # critics' score 0-100
    rating_count: Mapped[int | None] = mapped_column(Integer)    # critics' reviews it's made of
    hypes: Mapped[int | None] = mapped_column(Integer)           # IGDB users following it before release
    igdb_platform_release = mapped_column(Date)                  # IGDB's date for its platform (exact: a day)
    igdb_platform_release_exact: Mapped[bool | None] = mapped_column(Boolean)
    igdb_dates_checked_at = mapped_column(DateTime)
    pegi: Mapped[str | None] = mapped_column(Unicode(10))
    cover_image_id: Mapped[str | None] = mapped_column(Unicode(50))
    screenshot_ids: Mapped[str | None] = mapped_column(UnicodeText)
    video_ids: Mapped[str | None] = mapped_column(UnicodeText)
    game_modes: Mapped[str | None] = mapped_column(Unicode(500))
    themes: Mapped[str | None] = mapped_column(Unicode(500))
    # IGDB time to beat, in seconds (rushed / normal / 100%), and how many players gave times
    ttb_hastily: Mapped[int | None] = mapped_column(Integer)
    ttb_normally: Mapped[int | None] = mapped_column(Integer)
    ttb_completely: Mapped[int | None] = mapped_column(Integer)
    ttb_count: Mapped[int | None] = mapped_column(Integer)
    ttb_checked_at = mapped_column(DateTime)

    platform: Mapped[Platform] = relationship(lazy="joined")


class GameEdition(Base):
    __tablename__ = "game_editions"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    edition_key: Mapped[str] = mapped_column(Unicode(200))
    name: Mapped[str] = mapped_column(Unicode(200))
    created_at = created_at()
    game: Mapped[Game] = relationship(lazy="joined")


class StoreProduct(Base):
    """A product page at a store (one per store, URL and condition), linked to a game edition."""
    __tablename__ = "store_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    game_id: Mapped[int | None] = mapped_column(ForeignKey("games.id"))
    edition_id: Mapped[int | None] = mapped_column(ForeignKey("game_editions.id"))
    platform_id: Mapped[int | None] = mapped_column(ForeignKey("platforms.id"))
    external_name: Mapped[str] = mapped_column(Unicode(300))
    url: Mapped[str] = mapped_column(Unicode(800))
    image_url: Mapped[str | None] = mapped_column(Unicode(1000))
    condition: Mapped[str] = mapped_column(String(10), server_default="new")
    kind: Mapped[str] = mapped_column(String(12), server_default="game")   # as the scraper found it (Game.kind)
    first_seen_at = mapped_column(DateTime, server_default=NOW, nullable=False)
    last_seen_at = mapped_column(DateTime, server_default=NOW, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    is_preorder: Mapped[bool] = mapped_column(Boolean, server_default=false())
    release_date = mapped_column(Date)
    release_date_checked_at = mapped_column(DateTime)
    description: Mapped[str | None] = mapped_column(UnicodeText)
    details: Mapped[str | None] = mapped_column(UnicodeText)        # JSON
    image_urls: Mapped[str | None] = mapped_column(UnicodeText)     # JSON list
    details_checked_at = mapped_column(DateTime)


class PriceSnapshot(Base):
    """A product's price and stock, recorded only when one of them changed."""
    __tablename__ = "price_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_product_id: Mapped[int] = mapped_column(ForeignKey("store_products.id"))
    price = mapped_column(Numeric(10, 2), nullable=False)
    old_price = mapped_column(Numeric(10, 2))
    in_stock: Mapped[bool] = mapped_column(Boolean)
    scraped_at = mapped_column(DateTime, server_default=NOW, nullable=False)


class MergedId(Base):
    """A game / edition merged into another (old links and collection items follow it)."""
    __tablename__ = "merged_ids"
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)      # game / edition
    old_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    new_id: Mapped[int] = mapped_column(Integer)
    merged_at = mapped_column(DateTime, server_default=NOW, nullable=False)


# --- marketplace -------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # unique without case ("Paulo" is taken by "paulo"); NULLs don't clash (Google / Microsoft accounts may have none)
        Index("ux_users_username", text("lower(username)"), unique=True),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None] = mapped_column(Unicode(30))
    email: Mapped[str] = mapped_column(Unicode(255), unique=True)       # stored in lower case
    password_hash: Mapped[str | None] = mapped_column(Unicode(255))      # None: Google / Microsoft only
    display_name: Mapped[str] = mapped_column(Unicode(100))
    location: Mapped[str | None] = mapped_column(Unicode(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())      # False: blocked
    role: Mapped[str] = mapped_column(String(10), server_default="user")
    collection_public: Mapped[bool] = mapped_column(Boolean, server_default=false())   # shown on their profile
    wish_alerts: Mapped[bool] = mapped_column(Boolean, server_default=true(), nullable=False)   # wishlist e-mails
    lang: Mapped[str] = mapped_column(String(2), server_default="pt", nullable=False)   # pt / en, for e-mails
    steam_id: Mapped[str | None] = mapped_column(String(20))   # the last Steam import's profile (steam_service)
    steam_imported_at = mapped_column(DateTime)
    psn_account_id: Mapped[str | None] = mapped_column(String(20))      # the last PSN import's player (psn_service)
    psn_online_id: Mapped[str | None] = mapped_column(Unicode(16))
    psn_imported_at = mapped_column(DateTime)
    avatar_key: Mapped[str | None] = mapped_column(String(80))      # the profile picture (photo_storage)
    # the profile's showcase sections, in order, comma-separated (collection_service.SHOWCASE; None: all)
    profile_sections: Mapped[str | None] = mapped_column(String(100))
    # what the header's bell shows (user, 2026-10-13: not to be bombarded), JSON over NOTIFY_DEFAULTS
    notify_json: Mapped[str | None] = mapped_column(UnicodeText)
    # the gamer names and channels on the profile, JSON {kind: name} (gaming_accounts; None: none)
    accounts_json: Mapped[str | None] = mapped_column(UnicodeText)
    last_login_at = mapped_column(DateTime)
    created_at = created_at()
    deleted_at = mapped_column(DateTime)      # the user deleted their account: anonymised (auth_service.delete_account)

    @property
    def avatar(self):
        """The profile picture's address, or None."""
        return f"/media/{self.avatar_key}" if self.avatar_key else None

    @property
    def notify(self):
        """The bell's settings: NOTIFY_DEFAULTS with the user's choices over them."""
        return {**NOTIFY_DEFAULTS, **(json.loads(self.notify_json) if self.notify_json else {})}

    @property
    def accounts(self):
        """{kind: name}: the gamer names and channels the user shows (gaming_accounts)."""
        return json.loads(self.accounts_json) if self.accounts_json else {}

    @property
    def is_moderator(self):
        return self.role in ("moderator", "admin")

    @staticmethod
    def named(username):
        """The condition "this user's username is `username`", without case (as the unique index)."""
        return func.lower(User.username) == (username or "").lower()


class Listing(Base):
    __tablename__ = "user_listings"
    __table_args__ = (
        Index("ix_user_listings_game_status", "game_id", "status", postgresql_include=["price", "condition"]),
        Index("ix_user_listings_user", "user_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    edition_id: Mapped[int | None] = mapped_column(ForeignKey("game_editions.id"))
    price = mapped_column(Numeric(10, 2), nullable=False)
    condition: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Unicode(2000))
    status: Mapped[str] = mapped_column(String(10), server_default="active")
    removed_by_moderator: Mapped[bool] = mapped_column(Boolean, server_default=false())   # the seller can't undo it
    created_at = created_at()
    updated_at = mapped_column(DateTime, server_default=NOW, nullable=False)
    sold_at = mapped_column(DateTime)

    seller: Mapped[User] = relationship(lazy="joined")
    game: Mapped[Game] = relationship(lazy="joined")
    edition: Mapped[GameEdition | None] = relationship(lazy="joined")
    photos: Mapped[list["ListingPhoto"]] = relationship(order_by="ListingPhoto.position", lazy="selectin",
                                                        cascade="all, delete-orphan")


class ListingPhoto(Base):
    __tablename__ = "listing_photos"
    __table_args__ = (Index("ix_listing_photos_listing", "listing_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("user_listings.id"))
    position: Mapped[int] = mapped_column(Integer)
    photo_key: Mapped[str] = mapped_column(Unicode(200))
    thumb_key: Mapped[str] = mapped_column(Unicode(200))
    created_at = created_at()


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("listing_id", "buyer_id", name="uq_conversations_listing_buyer"),
        Index("ix_conversations_buyer", "buyer_id", "last_message_at"),
        Index("ix_conversations_seller", "seller_id", "last_message_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("user_listings.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deal_status: Mapped[str] = mapped_column(String(12), server_default="none")
    sent_at = mapped_column(DateTime)
    completed_at = mapped_column(DateTime)
    buyer_read_at = mapped_column(DateTime)
    seller_read_at = mapped_column(DateTime)
    last_message_at = mapped_column(DateTime, server_default=NOW, nullable=False)
    created_at = created_at()

    listing: Mapped[Listing] = relationship(lazy="joined")
    buyer: Mapped[User] = relationship(foreign_keys=[buyer_id], lazy="joined")
    seller: Mapped[User] = relationship(foreign_keys=[seller_id], lazy="joined")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation", "conversation_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))   # None: a message from the site
    body: Mapped[str | None] = mapped_column(Unicode(2000))
    event: Mapped[str | None] = mapped_column(String(20))
    created_at = created_at()

    photos: Mapped[list["MessagePhoto"]] = relationship(order_by="MessagePhoto.position", lazy="selectin",
                                                        cascade="all, delete-orphan")


class MessagePhoto(Base):
    """A photo sent in a conversation (more pictures of the copy, a damaged parcel): only the two
    sides (and moderators) see it, through /api/conversations/<id>/photos/<photo id>, never /media."""
    __tablename__ = "message_photos"
    __table_args__ = (Index("ix_message_photos_message", "message_id", "position"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    position: Mapped[int] = mapped_column(Integer)
    photo_key: Mapped[str] = mapped_column(Unicode(200))
    thumb_key: Mapped[str] = mapped_column(Unicode(200))
    created_at = created_at()


class Rating(Base):
    __tablename__ = "user_ratings"
    __table_args__ = (
        UniqueConstraint("conversation_id", "rater_id", name="uq_user_ratings"),
        Index("ix_user_ratings_rated", "rated_id", postgresql_include=["stars"]),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rated_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Unicode(500))
    reply: Mapped[str | None] = mapped_column(Unicode(500))
    hidden: Mapped[bool] = mapped_column(Boolean, server_default=false())   # by a moderator: not shown, not counted
    created_at = created_at()
    updated_at = mapped_column(DateTime, server_default=NOW, nullable=False)

    rater: Mapped[User] = relationship(foreign_keys=[rater_id], lazy="joined")
    conversation: Mapped[Conversation] = relationship(lazy="joined")



# --- moderation --------------------------------------------------------------------------

REPORT_KINDS = ("listing", "user", "rating", "review")
REPORT_REASONS = ("fake", "scam", "offensive", "wrong_game", "prohibited", "other")


class Report(Base):
    """Someone reports a listing, a user or a rating; a moderator resolves or dismisses it."""
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_status", "status", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(10))          # REPORT_KINDS
    target_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(20))        # REPORT_REASONS
    details: Mapped[str | None] = mapped_column(Unicode(1000))
    status: Mapped[str] = mapped_column(String(10), server_default="open")   # open / resolved / dismissed
    created_at = created_at()
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at = mapped_column(DateTime)
    resolution: Mapped[str | None] = mapped_column(Unicode(500))

    reporter: Mapped[User] = relationship(foreign_keys=[reporter_id], lazy="joined")


class ModerationLog(Base):
    """Every moderator action: who did what to which thing, and why."""
    __tablename__ = "moderation_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    moderator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(10))
    target_id: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Unicode(500))
    created_at = created_at()

    moderator: Mapped[User] = relationship(lazy="joined")


class MatchOverride(Base):
    """A moderator pinned this store product to this edition: matching and rematch leave it there
    (app/services/match_service.py). Removing it lets the next rematch decide again."""
    __tablename__ = "match_overrides"
    __table_args__ = (Index("ix_match_overrides_edition", "edition_id"),)
    store_product_id: Mapped[int] = mapped_column(ForeignKey("store_products.id", ondelete="CASCADE"),
                                                  primary_key=True, autoincrement=False)
    edition_id: Mapped[int] = mapped_column(ForeignKey("game_editions.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at = created_at()


class DuplicateDismissal(Base):
    """Two games sharing an IGDB entry that a moderator said are not the same (app/services/match_service.py)."""
    __tablename__ = "duplicate_dismissals"
    game_a: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)    # the smaller id
    game_b: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at = created_at()


# --- game collection ---------------------------------------------------------------------

class SteamSkip(Base):
    """A Steam game the user took out of their collection: the Steam import leaves it out (steam_service)."""
    __tablename__ = "steam_skips"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    app_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    created_at = created_at()


class PsnSkip(Base):
    """A PSN trophy list the user took out of their collection: the PSN import leaves it out (psn_service);
    edition_id: the edition it was, so adding that edition by hand brings it back (not a key: editions merge)."""
    __tablename__ = "psn_skips"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    psn_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    edition_id: Mapped[int | None] = mapped_column(Integer)
    created_at = created_at()


class Follow(Base):
    """A user following another, to compare collections (follow_service; user, 2026-10-12)."""
    __tablename__ = "follows"
    __table_args__ = (Index("ix_follows_followed", "followed_id"),)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    followed_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    created_at = created_at()


class PushSubscription(Base):
    """A browser / installed app a user gets push notifications on (push_service; user, 2026-10-16): what the
    browser's push service gave it (its address and keys). Gone with the user, or when the browser says so."""
    __tablename__ = "push_subscriptions"
    __table_args__ = (Index("ix_push_subscriptions_user", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at = created_at()


COLLECTION_KINDS = ("owned", "wishlist")
FORMATS = ("physical", "digital")
# the user's order (2026-10-11); "owned" = no other, what an owned item starts as
PLAY_STATUSES = ("finished", "playing", "backlog", "paused", "dropped", "owned")


class CollectionItem(Base):
    """A game edition a user owns or wants (app/services/collection_service.py)."""
    __tablename__ = "collection_items"
    __table_args__ = (
        # one item per edition, kind and format: a game on a disc and as a download too (user, 2026-10-12);
        # a wish has no format, and one wish per edition
        Index("ux_collection_items", "user_id", "edition_id", "kind", "format", unique=True,
              postgresql_nulls_not_distinct=True),
        Index("ix_collection_items_edition", "edition_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    edition_id: Mapped[int] = mapped_column(ForeignKey("game_editions.id"))
    kind: Mapped[str] = mapped_column(String(10))                 # COLLECTION_KINDS
    format: Mapped[str | None] = mapped_column(String(10))        # FORMATS (owned)
    status: Mapped[str | None] = mapped_column(String(10))        # PLAY_STATUSES (owned)
    hours = mapped_column(Numeric(6, 1))
    notes: Mapped[str | None] = mapped_column(Unicode(1000))
    achievements: Mapped[int | None] = mapped_column(Integer)          # done (owned)
    achievements_total: Mapped[int | None] = mapped_column(Integer)
    psn_id: Mapped[str | None] = mapped_column(String(20))             # its PSN trophy list (psn_service)
    platinum: Mapped[bool | None] = mapped_column(Boolean)             # PlayStation: the platinum trophy earned
    wish_price = mapped_column(Numeric(10, 2))                         # best new price when wished (wishlist)
    # wishlist alerts: the best new price at the last check (None: none in stock), and when
    alert_price = mapped_column(Numeric(10, 2))
    alert_checked_at = mapped_column(DateTime)
    alert_used = mapped_column(Boolean)                                # a user was selling a copy at the last check (None: not checked)
    # the price the user waits for (user, 2026-10-16): the bell and an e-mail when the best new or used
    # price gets to it; target_met: it had at the last e-mail check, so it's sent once until it's above again
    target_price = mapped_column(Numeric(10, 2))
    target_met: Mapped[bool | None] = mapped_column(Boolean)
    favourite_rank: Mapped[int | None] = mapped_column(SmallInteger)   # 1-10: the profile's top 10 (owned)
    # the game's DLC / expansions the user owns: JSON list of IGDB ids, from IgdbAddons' list (dlc_service)
    dlc_owned: Mapped[str | None] = mapped_column(UnicodeText)
    created_at = created_at()
    updated_at = mapped_column(DateTime, server_default=NOW, nullable=False)

    game: Mapped[Game] = relationship(lazy="joined")
    edition: Mapped[GameEdition] = relationship(lazy="joined")


class IgdbAddons(Base):
    """An IGDB game's DLC and expansions as IGDB lists them (dlc_service), kept for a while:
    JSON [{igdb_id, name, type: dlc | expansion | standalone, cover, year}]; [] when it has none."""
    __tablename__ = "igdb_addons"
    igdb_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    addons: Mapped[str] = mapped_column(UnicodeText)
    fetched_at = mapped_column(DateTime, server_default=NOW, nullable=False)


# --- players' reviews of games ------------------------------------------------------------

class GameReview(Base):
    """A user's score (1-10) and optional review of a game on one platform (app/services/review_service.py)."""
    __tablename__ = "game_reviews"
    __table_args__ = (
        Index("ux_game_reviews", "user_id", "game_id", unique=True),
        Index("ix_game_reviews_game", "game_id", "hidden", postgresql_include=["score"]),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    score: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str | None] = mapped_column(Unicode(120))
    body: Mapped[str | None] = mapped_column(Unicode(4000))
    hidden: Mapped[bool] = mapped_column(Boolean, server_default=false())    # by a moderator: not shown, not counted
    created_at = created_at()
    updated_at = mapped_column(DateTime, server_default=NOW, nullable=False)

    user: Mapped[User] = relationship(lazy="joined")
    game: Mapped[Game] = relationship(lazy="joined")


def fields(obj, *names, **extra):
    """{name: value} of these attributes, JSON-ready (as the API sends them), plus `extra`."""
    from db import json_value
    return {**{name: json_value(getattr(obj, name)) for name in names}, **extra}
