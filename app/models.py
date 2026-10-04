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
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Unicode, UnicodeText,
    UniqueConstraint, false, func, text, true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NOW = func.utcnow()      # the database's clock, in UTC (database/schema.sql)


# The tables Alembic manages (migrations/); the others belong to the price side (database/*.sql)
MARKET_TABLES = {"users", "user_listings", "listing_photos", "conversations", "messages", "message_photos",
                 "user_ratings", "reports", "moderation_log", "match_overrides",
                 "collection_items", "game_reviews", "duplicate_dismissals"}

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
    rating: Mapped[int | None] = mapped_column(Integer)
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
    last_login_at = mapped_column(DateTime)
    created_at = created_at()

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

COLLECTION_KINDS = ("owned", "wishlist")
FORMATS = ("physical", "digital")
PLAY_STATUSES = ("backlog", "playing", "completed", "platinum", "abandoned")


class CollectionItem(Base):
    """A game edition a user owns or wants (app/services/collection_service.py)."""
    __tablename__ = "collection_items"
    __table_args__ = (
        Index("ux_collection_items", "user_id", "edition_id", "kind", unique=True),
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
    wish_price = mapped_column(Numeric(10, 2))                         # best new price when wished (wishlist)
    # wishlist alerts: the best new price at the last check (None: none in stock), and when
    alert_price = mapped_column(Numeric(10, 2))
    alert_checked_at = mapped_column(DateTime)
    created_at = created_at()
    updated_at = mapped_column(DateTime, server_default=NOW, nullable=False)

    game: Mapped[Game] = relationship(lazy="joined")
    edition: Mapped[GameEdition] = relationship(lazy="joined")


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
