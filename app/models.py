"""
The tables as SQLAlchemy models:
- the marketplace (users, listings and their photos, conversations and messages, favourites,
  ratings, moderation): Alembic manages these tables (migrations/, MARKET_TABLES)
- the catalogue and prices (platforms, stores, games, editions, store products, price
  snapshots, merged ids): the pipeline writes them (pipeline/); their tables are made by
  database/*.sql, which these models follow

The price analysis queries (the current_offers view, windows, "latest price per product")
stay SQL: they're reports that read better as SQL.
Times are UTC, set by the database (SYSUTCDATETIME()).
"""
from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Unicode, UnicodeText, func,
    text,
)
from sqlalchemy.dialects.mssql import DATETIME2, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NOW = func.sysutcdatetime()      # the database's clock, in UTC


# The tables Alembic manages (migrations/); the others belong to the price side (database/*.sql)
MARKET_TABLES = {"users", "user_listings", "listing_photos", "conversations", "messages",
                 "user_favorites", "user_ratings", "reports", "moderation_log", "match_overrides",
                 "collection_items"}

# user: buys and sells; moderator: also handles reports; admin: also names / removes moderators
ROLES = ("user", "moderator", "admin")


class Base(DeclarativeBase):
    type_annotation_map = {DateTime: DATETIME2}


def created_at():
    return mapped_column(DATETIME2, server_default=NOW, nullable=False)


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
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1")


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    title: Mapped[str] = mapped_column(Unicode(300))
    normalized_title: Mapped[str] = mapped_column(Unicode(300))     # the game key (core/editions.py)
    image_url: Mapped[str | None] = mapped_column(Unicode(1000))
    created_at = created_at()
    # From IGDB (pipeline/igdb.py, IGDB_COLUMNS)
    igdb_id: Mapped[int | None] = mapped_column(Integer)
    igdb_checked_at = mapped_column(DATETIME2)
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
    first_seen_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)
    last_seen_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1")
    is_preorder: Mapped[bool] = mapped_column(Boolean, server_default="0")
    release_date = mapped_column(Date)
    release_date_checked_at = mapped_column(DATETIME2)
    description: Mapped[str | None] = mapped_column(UnicodeText)
    details: Mapped[str | None] = mapped_column(UnicodeText)        # JSON
    image_urls: Mapped[str | None] = mapped_column(UnicodeText)     # JSON list
    details_checked_at = mapped_column(DATETIME2)


class PriceSnapshot(Base):
    """A product's price and stock, recorded only when one of them changed."""
    __tablename__ = "price_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_product_id: Mapped[int] = mapped_column(ForeignKey("store_products.id"))
    price = mapped_column(Numeric(10, 2), nullable=False)
    old_price = mapped_column(Numeric(10, 2))
    in_stock: Mapped[bool] = mapped_column(Boolean)
    scraped_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)


class MergedId(Base):
    """A game / edition merged into another (old links and favourites follow it)."""
    __tablename__ = "merged_ids"
    kind: Mapped[str] = mapped_column(String(10), primary_key=True)      # game / edition
    old_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    new_id: Mapped[int] = mapped_column(Integer)
    merged_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)


# --- marketplace -------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # unique, but only among those who have one (Google / Microsoft accounts may not)
        Index("ux_users_username", "username", unique=True, mssql_where=text("username IS NOT NULL")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str | None] = mapped_column(Unicode(30))
    email: Mapped[str] = mapped_column(Unicode(255))
    password_hash: Mapped[str | None] = mapped_column(Unicode(255))      # None: Google / Microsoft only
    display_name: Mapped[str] = mapped_column(Unicode(100))
    location: Mapped[str | None] = mapped_column(Unicode(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1")      # False: blocked
    role: Mapped[str] = mapped_column(String(10), server_default="user")
    collection_public: Mapped[bool] = mapped_column(Boolean, server_default="0")   # shown on their profile
    last_login_at = mapped_column(DATETIME2)
    created_at = created_at()

    @property
    def is_moderator(self):
        return self.role in ("moderator", "admin")


class Listing(Base):
    __tablename__ = "user_listings"
    __table_args__ = (
        Index("ix_user_listings_game_status", "game_id", "status", mssql_include=["price", "condition"]),
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
    removed_by_moderator: Mapped[bool] = mapped_column(Boolean, server_default="0")   # the seller can't undo it
    created_at = created_at()
    updated_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)
    sold_at = mapped_column(DATETIME2)

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
        Index("ix_conversations_buyer", "buyer_id", "last_message_at"),
        Index("ix_conversations_seller", "seller_id", "last_message_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("user_listings.id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    deal_status: Mapped[str] = mapped_column(String(12), server_default="none")
    sent_at = mapped_column(DATETIME2)
    completed_at = mapped_column(DATETIME2)
    buyer_read_at = mapped_column(DATETIME2)
    seller_read_at = mapped_column(DATETIME2)
    last_message_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)
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


class Favorite(Base):
    __tablename__ = "user_favorites"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    edition_id: Mapped[int] = mapped_column(ForeignKey("game_editions.id"), primary_key=True)
    created_at = created_at()


class Rating(Base):
    __tablename__ = "user_ratings"
    __table_args__ = (Index("ix_user_ratings_rated", "rated_id", mssql_include=["stars"]),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    rated_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(TINYINT)
    comment: Mapped[str | None] = mapped_column(Unicode(500))
    reply: Mapped[str | None] = mapped_column(Unicode(500))
    hidden: Mapped[bool] = mapped_column(Boolean, server_default="0")   # by a moderator: not shown, not counted
    created_at = created_at()
    updated_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)

    rater: Mapped[User] = relationship(foreign_keys=[rater_id], lazy="joined")
    conversation: Mapped[Conversation] = relationship(lazy="joined")



# --- moderation --------------------------------------------------------------------------

REPORT_KINDS = ("listing", "user", "rating")
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
    resolved_at = mapped_column(DATETIME2)
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
    created_at = created_at()
    updated_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)

    game: Mapped[Game] = relationship(lazy="joined")
    edition: Mapped[GameEdition] = relationship(lazy="joined")


def fields(obj, *names, **extra):
    """{name: value} of these attributes, JSON-ready (as the API sends them), plus `extra`."""
    from db import json_value
    return {**{name: json_value(getattr(obj, name)) for name in names}, **extra}
