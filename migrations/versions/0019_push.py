"""Push notifications on phones and computers (user, 2026-10-16): the browsers / installed apps each user
gets them on (app.models.PushSubscription, push_service).

Revision ID: 0019_push
Revises: 0018_target_price
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_push"
down_revision = "0018_target_price"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.String(1000), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("utcnow()"), nullable=False),
    )
    op.create_index("ix_push_subscriptions_user", "push_subscriptions", ["user_id"])


def downgrade():
    op.drop_index("ix_push_subscriptions_user", "push_subscriptions")
    op.drop_table("push_subscriptions")
