"""Owned DLC in the collection (user, 2026-10-13): the DLC / expansions a user owns per collection item,
and each IGDB game's add-on list as IGDB gives it (app/services/dlc_service.py).

Revision ID: 0015_dlc
Revises: 0014_gaming_accounts
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_dlc"
down_revision = "0014_gaming_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection_items", sa.Column("dlc_owned", sa.UnicodeText()))
    op.create_table(
        "igdb_addons",
        sa.Column("igdb_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("addons", sa.UnicodeText(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.text("utcnow()"), nullable=False),
    )


def downgrade():
    op.drop_table("igdb_addons")
    op.drop_column("collection_items", "dlc_owned")
