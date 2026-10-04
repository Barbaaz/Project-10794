"""Wishlist alerts by e-mail (app/services/wish_alert_service.py): a user can switch them off and
gets them in their language; each wish remembers the price at the last check, so only a change
since then (back in stock, a drop, a new historical low) is sent.

Revision ID: 0003_wish_alerts
Revises: 0002_message_photos
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_wish_alerts"
down_revision = "0002_message_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("wish_alerts", sa.Boolean, nullable=False, server_default=sa.true()))
    op.add_column("users", sa.Column("lang", sa.String(2), nullable=False, server_default="pt"))
    op.add_column("collection_items", sa.Column("alert_price", sa.Numeric(10, 2)))
    op.add_column("collection_items", sa.Column("alert_checked_at", sa.DateTime))


def downgrade():
    op.drop_column("collection_items", "alert_checked_at")
    op.drop_column("collection_items", "alert_price")
    op.drop_column("users", "lang")
    op.drop_column("users", "wish_alerts")
