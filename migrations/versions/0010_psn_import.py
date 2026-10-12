"""PlayStation trophies (user, 2026-10-12): the PSN import's profile on the user, each item's PSN
trophy list and platinum, and the trophy lists a user took out of their collection (imports skip
them: a PSN trophy list also has games played on PS Plus, not owned).

Revision ID: 0010_psn_import
Revises: 0009_steam_skips
Create Date: 2026-10-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_psn_import"
down_revision = "0009_steam_skips"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("psn_account_id", sa.String(20)))
    op.add_column("users", sa.Column("psn_online_id", sa.Unicode(16)))
    op.add_column("users", sa.Column("psn_imported_at", sa.DateTime))
    op.add_column("collection_items", sa.Column("psn_id", sa.String(20)))
    op.add_column("collection_items", sa.Column("platinum", sa.Boolean))
    op.create_table(
        "psn_skips",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("psn_id", sa.String(20), primary_key=True),
        sa.Column("edition_id", sa.Integer),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("utcnow()")),
    )


def downgrade():
    op.drop_table("psn_skips")
    op.drop_column("collection_items", "platinum")
    op.drop_column("collection_items", "psn_id")
    op.drop_column("users", "psn_imported_at")
    op.drop_column("users", "psn_online_id")
    op.drop_column("users", "psn_account_id")
