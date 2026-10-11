"""Wishlist alerts for used copies (user, 2026-10-11: "notified when that game is being sold"): each
wish remembers whether a user was selling it at the last check, so a new listing is sent once.
NULL: not checked yet (the first check only remembers).

Revision ID: 0007_wish_used_alerts
Revises: 0006_play_statuses
Create Date: 2026-10-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_wish_used_alerts"
down_revision = "0006_play_statuses"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_items", sa.Column("alert_used", sa.Boolean))


def downgrade():
    op.drop_column("collection_items", "alert_used")
