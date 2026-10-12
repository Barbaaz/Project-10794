"""Profile pictures (user, 2026-10-12): the key of each user's picture in the photo storage.

Revision ID: 0013_avatars
Revises: 0012_follows
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_avatars"
down_revision = "0012_follows"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("avatar_key", sa.String(80)))


def downgrade():
    op.drop_column("users", "avatar_key")
