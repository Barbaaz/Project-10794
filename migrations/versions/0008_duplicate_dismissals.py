"""Possible duplicate games a moderator said are not the same (so the review list doesn't show them again).

Revision ID: 0008_duplicate_dismissals
Revises: 0007_favorites_to_wishlist
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "0008_duplicate_dismissals"
down_revision = "0007_favorites_to_wishlist"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "duplicate_dismissals",
        sa.Column("game_a", sa.Integer, nullable=False),        # the smaller id of the pair
        sa.Column("game_b", sa.Integer, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=sa.text("SYSUTCDATETIME()")),
        sa.PrimaryKeyConstraint("game_a", "game_b", name="pk_duplicate_dismissals"),
    )


def downgrade():
    op.drop_table("duplicate_dismissals")
