"""Photos in conversations: a seller sends more pictures of the copy when the buyer asks (or a
buyer shows a damaged parcel). Up to 5 per message; kept private to the conversation.

Revision ID: 0002_message_photos
Revises: 0001_postgres
Create Date: 2026-10-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_message_photos"
down_revision = "0001_postgres"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "message_photos",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("message_id", sa.Integer, sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("photo_key", sa.Unicode(200), nullable=False),
        sa.Column("thumb_key", sa.Unicode(200), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("utcnow()")),
    )
    op.create_index("ix_message_photos_message", "message_photos", ["message_id", "position"])


def downgrade():
    op.drop_table("message_photos")
