"""Collection play statuses as the user wants them (2026-10-11): Finished, Playing, Backlog, Paused,
Dropped, Owned. completed and platinum become finished (the achievements show a 100%), abandoned
becomes dropped, and an owned game without one is "owned".

Revision ID: 0006_play_statuses
Revises: 0005_steam_profile
Create Date: 2026-10-11
"""
from alembic import op

revision = "0006_play_statuses"
down_revision = "0005_steam_profile"
branch_labels = None
depends_on = None


OLD = "status IS NULL OR status IN ('backlog', 'playing', 'completed', 'platinum', 'abandoned')"
NEW = "status IS NULL OR status IN ('finished', 'playing', 'backlog', 'paused', 'dropped', 'owned')"


def upgrade():
    op.drop_constraint("ck_collection_status", "collection_items", type_="check")
    op.execute("UPDATE collection_items SET status = 'finished' WHERE status IN ('completed', 'platinum')")
    op.execute("UPDATE collection_items SET status = 'dropped' WHERE status = 'abandoned'")
    op.execute("UPDATE collection_items SET status = 'owned' WHERE kind = 'owned' AND status IS NULL")
    op.create_check_constraint("ck_collection_status", "collection_items", NEW)


def downgrade():
    op.drop_constraint("ck_collection_status", "collection_items", type_="check")
    op.execute("UPDATE collection_items SET status = NULL WHERE status = 'owned'")
    op.execute("UPDATE collection_items SET status = 'playing' WHERE status = 'paused'")
    op.execute("UPDATE collection_items SET status = 'abandoned' WHERE status = 'dropped'")
    op.execute("UPDATE collection_items SET status = 'completed' WHERE status = 'finished'")
    op.create_check_constraint("ck_collection_status", "collection_items", OLD)
