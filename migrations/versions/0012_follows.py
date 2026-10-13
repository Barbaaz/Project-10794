"""Users following each other, to compare collections and achievements (user, 2026-10-12).

Revision ID: 0012_follows
Revises: 0011_physical_and_digital
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_follows"
down_revision = "0011_physical_and_digital"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "follows",
        sa.Column("follower_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("followed_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("utcnow()")),
    )
    op.create_index("ix_follows_followed", "follows", ["followed_id"])


def downgrade():
    op.drop_index("ix_follows_followed", table_name="follows")
    op.drop_table("follows")
