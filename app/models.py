"""
The marketplace's tables as SQLAlchemy models (users, listings and their photos,
conversations and messages, favourites, ratings), plus the catalogue tables they refer to
(games, editions, platforms), mapped for reading.

The price side (scrapers, price history, the current_offers view) still uses SQL directly:
its queries are reports (windows, "latest price per product") that read better as SQL.
Times are UTC, set by the database (SYSUTCDATETIME()) when a row is created.
"""
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Unicode, func, text,
)
from sqlalchemy.dialects.mssql import DATETIME2, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NOW = func.sysutcdatetime()      # the database's clock, in UTC


# The tables Alembic manages (migrations/); the others belong to the price side (database/*.sql)
MARKET_TABLES = {"users", "user_listings", "listing_photos", "conversations", "messages",
                 "user_favorites", "user_ratings"}


class Base(DeclarativeBase):
    type_annotation_map = {DateTime: DATETIME2}


def created_at():
    return mapped_column(DATETIME2, server_default=NOW, nullable=False)


# --- catalogue (read by the marketplace) --------------------------------------------------

class Platform(Base):
    __tablename__ = "platforms"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(Unicode(100))


class Game(Base):
    __tablename__ = "games"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    title: Mapped[str] = mapped_column(Unicode(300))
    image_url: Mapped[str | None] = mapped_column(Unicode(1000))
    platform: Mapped[Platform] = relationship(lazy="joined")


class GameEdition(Base):
    __tablename__ = "game_editions"
    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"))
    edition_key: Mapped[str] = mapped_column(Unicode(200))
    name: Mapped[str] = mapped_column(Unicode(200))
    game: Mapped[Game] = relationship(lazy="joined")


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
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="1")
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default="0")
    last_login_at = mapped_column(DATETIME2)
    created_at = created_at()


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
    created_at = created_at()
    updated_at = mapped_column(DATETIME2, server_default=NOW, nullable=False)

    rater: Mapped[User] = relationship(foreign_keys=[rater_id], lazy="joined")
    conversation: Mapped[Conversation] = relationship(lazy="joined")


def fields(obj, *names, **extra):
    """{name: value} of these attributes, JSON-ready (as the API sends them), plus `extra`."""
    from db import json_value
    return {**{name: json_value(getattr(obj, name)) for name in names}, **extra}
