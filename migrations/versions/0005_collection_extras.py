"""Collection extras: the price a wish was added at (to see it drop), achievements done / total.

Revision ID: 0005_collection_extras
Revises: 0004_collection
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_collection_extras"
down_revision = "0004_collection"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_items", sa.Column("wish_price", sa.Numeric(10, 2)))     # best new price when wished
    op.add_column("collection_items", sa.Column("achievements", sa.Integer))
    op.add_column("collection_items", sa.Column("achievements_total", sa.Integer))


def downgrade():
    op.drop_column("collection_items", "achievements_total")
    op.drop_column("collection_items", "achievements")
    op.drop_column("collection_items", "wish_price")
