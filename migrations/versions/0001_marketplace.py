"""The marketplace's tables (before Alembic they were made by database/schema.sql).

A database that already has them (made by schema.sql) keeps them as they are: each table is
only created where it's missing. From here on, changes to these tables are new migrations.

Revision ID: 0001_marketplace
Revises:
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mssql import DATETIME2, TINYINT

revision = "0001_marketplace"
down_revision = None
branch_labels = None
depends_on = None

NOW = sa.text("SYSUTCDATETIME()")


def _id():
    return sa.Column("id", sa.Integer, sa.Identity(start=1, increment=1), primary_key=True)


def _created_at(name="created_at"):
    return sa.Column(name, DATETIME2, nullable=False, server_default=NOW)


def _missing(name):
    return not sa.inspect(op.get_bind()).has_table(name)


def _columns(table):
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _bring_old_tables_up_to_date():
    """
    Databases made by schema.sql before accounts existed have older users / user_listings
    tables (what schema.sql's upgrade blocks used to fix): bring them to the shape below.
    """
    if not _missing("users"):
        columns = _columns("users")
        if "username" not in columns:
            op.add_column("users", sa.Column("username", sa.Unicode(30)))
            op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")))
            op.add_column("users", sa.Column("last_login_at", DATETIME2))
        indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("users")}
        if "ux_users_username" not in indexes:
            op.create_index("ux_users_username", "users", ["username"], unique=True,
                            mssql_where=sa.text("username IS NOT NULL"))
        op.alter_column("users", "password_hash", existing_type=sa.Unicode(255), nullable=True)
    if not _missing("user_listings"):
        if "edition_id" not in _columns("user_listings"):
            op.add_column("user_listings", sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id")))
        # condition may also be "new" (sealed)
        definition = op.get_bind().scalar(sa.text(
            "SELECT definition FROM sys.check_constraints WHERE name = 'ck_user_listings_condition'"))
        if definition and "'new'" not in definition:
            op.drop_constraint("ck_user_listings_condition", "user_listings", type_="check")
            op.create_check_constraint("ck_user_listings_condition", "user_listings",
                                       "condition IN ('new', 'like_new', 'good', 'fair', 'poor')")


def upgrade():
    _bring_old_tables_up_to_date()
    if _missing("users"):
        op.create_table(
            "users",
            _id(),
            sa.Column("email", sa.Unicode(255), nullable=False, unique=True),
            sa.Column("password_hash", sa.Unicode(255)),                 # None: Google / Microsoft only
            sa.Column("display_name", sa.Unicode(100), nullable=False),
            sa.Column("location", sa.Unicode(100)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
            _created_at(),
            sa.Column("username", sa.Unicode(30)),
            sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")),
            sa.Column("last_login_at", DATETIME2),
        )
        op.create_index("ux_users_username", "users", ["username"], unique=True,
                        mssql_where=sa.text("username IS NOT NULL"))

    if _missing("user_listings"):
        op.create_table(
            "user_listings",
            _id(),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
            sa.Column("price", sa.Numeric(10, 2), nullable=False),
            sa.Column("condition", sa.String(10), nullable=False),
            sa.Column("description", sa.Unicode(2000)),
            sa.Column("status", sa.String(10), nullable=False, server_default="active"),
            _created_at(),
            _created_at("updated_at"),
            sa.Column("sold_at", DATETIME2),
            sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id")),
            sa.CheckConstraint("condition IN ('new', 'like_new', 'good', 'fair', 'poor')", name="ck_user_listings_condition"),
            sa.CheckConstraint("status IN ('active', 'reserved', 'sold', 'removed')", name="ck_user_listings_status"),
            sa.CheckConstraint("price > 0", name="ck_user_listings_price"),
        )
        op.create_index("ix_user_listings_game_status", "user_listings", ["game_id", "status"],
                        mssql_include=["price", "condition"])
        op.create_index("ix_user_listings_user", "user_listings", ["user_id"])

    if _missing("listing_photos"):
        op.create_table(
            "listing_photos",
            _id(),
            sa.Column("listing_id", sa.Integer, sa.ForeignKey("user_listings.id"), nullable=False),
            sa.Column("position", sa.Integer, nullable=False),
            sa.Column("photo_key", sa.Unicode(200), nullable=False),
            sa.Column("thumb_key", sa.Unicode(200), nullable=False),
            _created_at(),
        )
        op.create_index("ix_listing_photos_listing", "listing_photos", ["listing_id", "position"])

    if _missing("conversations"):
        op.create_table(
            "conversations",
            _id(),
            sa.Column("listing_id", sa.Integer, sa.ForeignKey("user_listings.id"), nullable=False),
            sa.Column("buyer_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("seller_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("deal_status", sa.String(12), nullable=False, server_default="none"),
            sa.Column("sent_at", DATETIME2),
            sa.Column("completed_at", DATETIME2),
            sa.Column("buyer_read_at", DATETIME2),
            sa.Column("seller_read_at", DATETIME2),
            _created_at("last_message_at"),
            _created_at(),
            sa.UniqueConstraint("listing_id", "buyer_id", name="uq_conversations_listing_buyer"),
            sa.CheckConstraint("deal_status IN ('none', 'requested', 'accepted', 'declined', 'cancelled', "
                               "'sent', 'completed', 'problem')", name="ck_conversations_deal"),
        )
        op.create_index("ix_conversations_buyer", "conversations", ["buyer_id", "last_message_at"])
        op.create_index("ix_conversations_seller", "conversations", ["seller_id", "last_message_at"])

    if _missing("messages"):
        op.create_table(
            "messages",
            _id(),
            sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("sender_id", sa.Integer, sa.ForeignKey("users.id")),        # None: from the site
            sa.Column("body", sa.Unicode(2000)),
            sa.Column("event", sa.String(20)),
            _created_at(),
        )
        op.create_index("ix_messages_conversation", "messages", ["conversation_id", "id"])

    if _missing("user_favorites"):
        op.create_table(
            "user_favorites",
            sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
            _created_at(),
            sa.PrimaryKeyConstraint("user_id", "edition_id", name="pk_user_favorites"),
        )

    if _missing("user_ratings"):
        op.create_table(
            "user_ratings",
            _id(),
            sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
            sa.Column("rater_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("rated_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("stars", TINYINT, nullable=False),
            sa.Column("comment", sa.Unicode(500)),
            sa.Column("reply", sa.Unicode(500)),
            _created_at(),
            _created_at("updated_at"),
            sa.UniqueConstraint("conversation_id", "rater_id", name="uq_user_ratings"),
            sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_user_ratings_stars"),
        )
        op.create_index("ix_user_ratings_rated", "user_ratings", ["rated_id"], mssql_include=["stars"])


def downgrade():
    for table in ("user_ratings", "user_favorites", "messages", "conversations", "listing_photos",
                  "user_listings", "users"):
        op.drop_table(table)
