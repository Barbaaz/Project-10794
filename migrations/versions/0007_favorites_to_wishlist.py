"""Favourites folded into the wishlist: each favourite becomes a wish (unless the user already wishes
for or owns that edition), then user_favorites goes. The wish price stays empty: a favourite never
recorded the price it was starred at.

Revision ID: 0007_favorites_to_wishlist
Revises: 0006_game_reviews
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mssql import DATETIME2

revision = "0007_favorites_to_wishlist"
down_revision = "0006_game_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT INTO collection_items (user_id, game_id, edition_id, kind, created_at, updated_at)
        SELECT f.user_id, e.game_id, f.edition_id, 'wishlist', f.created_at, f.created_at
        FROM user_favorites f
        JOIN game_editions e ON e.id = f.edition_id
        WHERE NOT EXISTS (SELECT 1 FROM collection_items c
                          WHERE c.user_id = f.user_id AND c.edition_id = f.edition_id)
    """)
    op.drop_table("user_favorites")


def downgrade():
    # the table comes back with every wish in it (which wishes were favourites isn't known anymore)
    op.create_table(
        "user_favorites",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("edition_id", sa.Integer, sa.ForeignKey("game_editions.id"), nullable=False),
        sa.Column("created_at", DATETIME2, server_default=sa.text("SYSUTCDATETIME()"), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "edition_id", name="pk_user_favorites"),
    )
    op.execute("""
        INSERT INTO user_favorites (user_id, edition_id, created_at)
        SELECT user_id, edition_id, MIN(created_at) FROM collection_items
        WHERE kind = 'wishlist' GROUP BY user_id, edition_id
    """)
