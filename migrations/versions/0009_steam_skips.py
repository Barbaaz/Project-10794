"""Steam games a user took out of their collection: imports skip them (user, 2026-10-11: games marked
"private" on Steam must not come in; Steam still sends them when the site's key is the user's own,
and no API we can use says which are private).

Revision ID: 0009_steam_skips
Revises: 0008_profile_showcase
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_steam_skips"
down_revision = "0008_profile_showcase"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "steam_skips",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("app_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("utcnow()")),
    )


def downgrade():
    op.drop_table("steam_skips")
