"""Account deletion (GDPR): a deleted account is anonymised, not removed (user, 2026-10-07), so
the other side's purchases, ratings and conversations keep their history; deleted_at marks it.

Revision ID: 0004_deleted_users
Revises: 0003_wish_alerts
Create Date: 2026-10-07
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_deleted_users"
down_revision = "0003_wish_alerts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("deleted_at", sa.DateTime))


def downgrade():
    op.drop_column("users", "deleted_at")
