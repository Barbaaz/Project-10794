"""The bell's notification settings (user, 2026-10-13: not to be bombarded): JSON per user over
app.models.NOTIFY_DEFAULTS.

Revision ID: 0016_notify
Revises: 0015_dlc
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_notify"
down_revision = "0015_dlc"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("notify_json", sa.UnicodeText()))


def downgrade():
    op.drop_column("users", "notify_json")
