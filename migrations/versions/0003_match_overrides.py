"""Match overrides: a moderator pins a store product to an edition; the pipeline respects it.

Revision ID: 0003_match_overrides
Revises: 0002_moderation
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "0003_match_overrides"
down_revision = "0002_moderation"
branch_labels = None
depends_on = None

NOW = sa.text("SYSUTCDATETIME()")


def upgrade():
    op.create_table(
        "match_overrides",
        # a product that leaves the database takes its pin along
        sa.Column("store_product_id", sa.Integer, sa.ForeignKey("store_products.id", ondelete="CASCADE"),
                  primary_key=True, autoincrement=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=NOW),
    )
    op.create_index("ix_match_overrides_edition", "match_overrides", ["edition_id"])


def downgrade():
    op.drop_table("match_overrides")
