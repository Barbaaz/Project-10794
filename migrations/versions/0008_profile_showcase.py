"""The profile's showcase (user, 2026-10-11): the sections a user shows on their profile, in their
order (favourites, most played, most valuable, achievements; NULL = all, in that order), and their
top 10 favourite games, picked by hand from the owned ones (collection_items.favourite_rank, 1-10).
Shown only when the collection is public.

Revision ID: 0008_profile_showcase
Revises: 0007_wish_used_alerts
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_profile_showcase"
down_revision = "0007_wish_used_alerts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("profile_sections", sa.String(100)))
    op.add_column("collection_items", sa.Column("favourite_rank", sa.SmallInteger))


def downgrade():
    op.drop_column("collection_items", "favourite_rank")
    op.drop_column("users", "profile_sections")
