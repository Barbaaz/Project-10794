"""The user's Steam profile, remembered by the import so it can be refreshed with one button
(user, 2026-10-11; steam_service).

Revision ID: 0005_steam_profile
Revises: 0004_deleted_users
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_steam_profile"
down_revision = "0004_deleted_users"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("steam_id", sa.String(20)))
    op.add_column("users", sa.Column("steam_imported_at", sa.DateTime))


def downgrade():
    op.drop_column("users", "steam_imported_at")
    op.drop_column("users", "steam_id")
