"""Game collection: games a user owns or wants (wishlist), and whether their collection is public.

Revision ID: 0004_collection
Revises: 0003_match_overrides
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "0004_collection"
down_revision = "0003_match_overrides"
branch_labels = None
depends_on = None

NOW = sa.text("SYSUTCDATETIME()")


def upgrade():
    op.add_column("users", sa.Column("collection_public", sa.Boolean, nullable=False, server_default="0"))

    op.create_table(
        "collection_items",
        sa.Column("id", sa.Integer, sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),               # owned / wishlist
        sa.Column("format", sa.String(10)),                             # physical / digital (owned)
        sa.Column("status", sa.String(10)),                             # backlog / playing / completed / platinum / abandoned
        sa.Column("hours", sa.Numeric(6, 1)),
        sa.Column("notes", sa.Unicode(1000)),
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=NOW),
        sa.Column("updated_at", mssql.DATETIME2, nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('owned', 'wishlist')", name="ck_collection_kind"),
        sa.CheckConstraint("format IS NULL OR format IN ('physical', 'digital')", name="ck_collection_format"),
        sa.CheckConstraint("status IS NULL OR status IN ('backlog', 'playing', 'completed', 'platinum', 'abandoned')",
                           name="ck_collection_status"),
    )
    op.create_index("ux_collection_items", "collection_items", ["user_id", "edition_id", "kind"], unique=True)
    op.create_index("ix_collection_items_edition", "collection_items", ["edition_id"])


def downgrade():
    op.drop_table("collection_items")
    op.drop_column("users", "collection_public", mssql_drop_default=True)
