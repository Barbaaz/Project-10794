"""The marketplace's tables on PostgreSQL, as they were when the project moved from SQL Server
(2026-10-03): users, listings and photos, conversations and messages, ratings, moderation,
match overrides, the collection, reviews and dismissed duplicates. The SQL Server history
(0001_marketplace … 0008_duplicate_dismissals) ended in this same shape.
From here on, changes to these tables are new migrations.

Revision ID: 0001_postgres
Revises:
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0001_postgres"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("utcnow()")      # database/schema.sql


def _id():
    return sa.Column("id", sa.Integer, sa.Identity(), primary_key=True)


def _time(name="created_at"):
    return sa.Column(name, sa.DateTime, nullable=False, server_default=NOW)


def _flag(name):
    return sa.Column(name, sa.Boolean, nullable=False, server_default=sa.false())


def upgrade():
    op.create_table(
        "users",
        _id(),
        sa.Column("username", sa.Unicode(30)),
        sa.Column("email", sa.Unicode(255), nullable=False, unique=True),    # stored in lower case
        sa.Column("password_hash", sa.Unicode(255)),                         # None: Google / Microsoft only
        sa.Column("display_name", sa.Unicode(100), nullable=False),
        sa.Column("location", sa.Unicode(100)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("role", sa.String(10), nullable=False, server_default="user"),
        _flag("collection_public"),
        sa.Column("last_login_at", sa.DateTime),
        _time(),
        sa.CheckConstraint("role IN ('user', 'moderator', 'admin')", name="ck_users_role"),
    )
    # unique without case ("Paulo" is taken by "paulo"); NULLs don't clash
    op.create_index("ux_users_username", "users", [sa.text("lower(username)")], unique=True)

    op.create_table(
        "user_listings",
        _id(),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id")),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("condition", sa.String(10), nullable=False),
        sa.Column("description", sa.Unicode(2000)),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        _flag("removed_by_moderator"),
        _time(),
        _time("updated_at"),
        sa.Column("sold_at", sa.DateTime),
        sa.CheckConstraint("condition IN ('new', 'like_new', 'good', 'fair', 'poor')", name="ck_user_listings_condition"),
        sa.CheckConstraint("status IN ('active', 'reserved', 'sold', 'removed')", name="ck_user_listings_status"),
        sa.CheckConstraint("price > 0", name="ck_user_listings_price"),
    )
    op.create_index("ix_user_listings_game_status", "user_listings", ["game_id", "status"],
                    postgresql_include=["price", "condition"])
    op.create_index("ix_user_listings_user", "user_listings", ["user_id"])

    op.create_table(
        "listing_photos",
        _id(),
        sa.Column("listing_id", sa.Integer, sa.ForeignKey("user_listings.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("photo_key", sa.Unicode(200), nullable=False),
        sa.Column("thumb_key", sa.Unicode(200), nullable=False),
        _time(),
    )
    op.create_index("ix_listing_photos_listing", "listing_photos", ["listing_id", "position"])

    op.create_table(
        "conversations",
        _id(),
        sa.Column("listing_id", sa.Integer, sa.ForeignKey("user_listings.id"), nullable=False),
        sa.Column("buyer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("deal_status", sa.String(12), nullable=False, server_default="none"),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("buyer_read_at", sa.DateTime),
        sa.Column("seller_read_at", sa.DateTime),
        _time("last_message_at"),
        _time(),
        sa.UniqueConstraint("listing_id", "buyer_id", name="uq_conversations_listing_buyer"),
        sa.CheckConstraint("deal_status IN ('none', 'requested', 'accepted', 'declined', 'cancelled', "
                           "'sent', 'completed', 'problem')", name="ck_conversations_deal"),
    )
    op.create_index("ix_conversations_buyer", "conversations", ["buyer_id", "last_message_at"])
    op.create_index("ix_conversations_seller", "conversations", ["seller_id", "last_message_at"])

    op.create_table(
        "messages",
        _id(),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("sender_id", sa.Integer, sa.ForeignKey("users.id")),        # None: from the site
        sa.Column("body", sa.Unicode(2000)),
        sa.Column("event", sa.String(20)),
        _time(),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "id"])

    op.create_table(
        "user_ratings",
        _id(),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("rater_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rated_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stars", sa.SmallInteger, nullable=False),
        sa.Column("comment", sa.Unicode(500)),
        sa.Column("reply", sa.Unicode(500)),
        _flag("hidden"),                                                       # by a moderator
        _time(),
        _time("updated_at"),
        sa.UniqueConstraint("conversation_id", "rater_id", name="uq_user_ratings"),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_user_ratings_stars"),
    )
    op.create_index("ix_user_ratings_rated", "user_ratings", ["rated_id"], postgresql_include=["stars"])

    op.create_table(
        "reports",
        _id(),
        sa.Column("reporter_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("details", sa.Unicode(1000)),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        _time(),
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("resolution", sa.Unicode(500)),
        sa.CheckConstraint("kind IN ('listing', 'user', 'rating', 'review')", name="ck_reports_kind"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_reports_status"),
    )
    op.create_index("ix_reports_status", "reports", ["status", "created_at"])

    op.create_table(
        "moderation_log",
        _id(),
        sa.Column("moderator_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Integer, nullable=False),
        sa.Column("note", sa.Unicode(500)),
        _time(),
    )

    op.create_table(
        "match_overrides",
        # a product that leaves the database takes its pin along
        sa.Column("store_product_id", sa.Integer, sa.ForeignKey("store_products.id", ondelete="CASCADE"),
                  primary_key=True, autoincrement=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        _time(),
    )
    op.create_index("ix_match_overrides_edition", "match_overrides", ["edition_id"])

    op.create_table(
        "collection_items",
        _id(),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),               # owned / wishlist
        sa.Column("format", sa.String(10)),                             # physical / digital (owned)
        sa.Column("status", sa.String(10)),                             # backlog / playing / completed / platinum / abandoned
        sa.Column("hours", sa.Numeric(6, 1)),
        sa.Column("notes", sa.Unicode(1000)),
        sa.Column("achievements", sa.Integer),
        sa.Column("achievements_total", sa.Integer),
        sa.Column("wish_price", sa.Numeric(10, 2)),                     # best new price when wished
        _time(),
        _time("updated_at"),
        sa.CheckConstraint("kind IN ('owned', 'wishlist')", name="ck_collection_kind"),
        sa.CheckConstraint("format IS NULL OR format IN ('physical', 'digital')", name="ck_collection_format"),
        sa.CheckConstraint("status IS NULL OR status IN ('backlog', 'playing', 'completed', 'platinum', 'abandoned')",
                           name="ck_collection_status"),
    )
    op.create_index("ux_collection_items", "collection_items", ["user_id", "edition_id", "kind"], unique=True)
    op.create_index("ix_collection_items_edition", "collection_items", ["edition_id"])

    op.create_table(
        "game_reviews",
        _id(),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("title", sa.Unicode(120)),
        sa.Column("body", sa.Unicode(4000)),
        _flag("hidden"),                                                       # by a moderator
        _time(),
        _time("updated_at"),
        sa.CheckConstraint("score BETWEEN 1 AND 10", name="ck_game_reviews_score"),
    )
    op.create_index("ux_game_reviews", "game_reviews", ["user_id", "game_id"], unique=True)
    op.create_index("ix_game_reviews_game", "game_reviews", ["game_id", "hidden"], postgresql_include=["score"])

    op.create_table(
        "duplicate_dismissals",
        sa.Column("game_a", sa.Integer, nullable=False),        # the smaller id of the pair
        sa.Column("game_b", sa.Integer, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        _time(),
        sa.PrimaryKeyConstraint("game_a", "game_b", name="pk_duplicate_dismissals"),
    )


def downgrade():
    for table in ("duplicate_dismissals", "game_reviews", "collection_items", "match_overrides", "moderation_log",
                  "reports", "user_ratings", "messages", "conversations", "listing_photos", "user_listings", "users"):
        op.drop_table(table)
