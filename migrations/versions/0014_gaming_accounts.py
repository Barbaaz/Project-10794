"""Gamer names and channels on the profile (user, 2026-10-13): PSN, Xbox, Steam, Nintendo, Epic, YouTube,
Twitch, as JSON {kind: name} (app/services/gaming_accounts.py).

Revision ID: 0014_gaming_accounts
Revises: 0013_avatars
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_gaming_accounts"
down_revision = "0013_avatars"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("accounts_json", sa.UnicodeText()))


def downgrade():
    op.drop_column("users", "accounts_json")
