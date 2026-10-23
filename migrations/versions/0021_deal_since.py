"""Since when a wish is a good deal (user, 2026-10-22: the bell's newest first, not cheapest first):
collection_service.good_deals.

Revision ID: 0021_deal_since
Revises: 0020_contact
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_deal_since"
down_revision = "0020_contact"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_items", sa.Column("deal_key", sa.String(30)))
    op.add_column("collection_items", sa.Column("deal_since", sa.DateTime()))


def downgrade():
    op.drop_column("collection_items", "deal_since")
    op.drop_column("collection_items", "deal_key")
