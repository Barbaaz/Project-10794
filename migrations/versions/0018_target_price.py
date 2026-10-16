"""A target price per wish (user, 2026-10-16: custom alerts): the bell and an e-mail when the best new
or used price gets to it (collection_service.deal_reason, wish_alert_service).

Revision ID: 0018_target_price
Revises: 0017_no_negatives
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_target_price"
down_revision = "0017_no_negatives"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_items", sa.Column("target_price", sa.Numeric(10, 2)))
    op.add_column("collection_items", sa.Column("target_met", sa.Boolean()))
    op.create_check_constraint("ck_collection_items_target", "collection_items", "target_price > 0")


def downgrade():
    op.drop_constraint("ck_collection_items_target", "collection_items", type_="check")
    op.drop_column("collection_items", "target_met")
    op.drop_column("collection_items", "target_price")
