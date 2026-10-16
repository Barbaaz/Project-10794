"""Messages to the site's team from the Contactos page (user, 2026-10-16; app.models.ContactMessage,
contact_service), read in /admin.

Revision ID: 0020_contact
Revises: 0019_push
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0020_contact"
down_revision = "0019_push"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("email", sa.Unicode(255), nullable=False),
        sa.Column("topic", sa.String(20), nullable=False),
        sa.Column("body", sa.Unicode(4000), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("utcnow()"), nullable=False),
        sa.Column("handled_at", sa.DateTime()),
        sa.Column("handled_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_contact_messages_handled", "contact_messages", ["handled_at", "id"])


def downgrade():
    op.drop_index("ix_contact_messages_handled", "contact_messages")
    op.drop_table("contact_messages")
