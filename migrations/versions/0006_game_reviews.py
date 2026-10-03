"""Players' reviews of games: a 1-10 score and optional text, one per user per game (platform).

Revision ID: 0006_game_reviews
Revises: 0005_collection_extras
Create Date: 2026-10-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "0006_game_reviews"
down_revision = "0005_collection_extras"
branch_labels = None
depends_on = None

NOW = sa.text("SYSUTCDATETIME()")


def upgrade():
    op.create_table(
        "game_reviews",
        sa.Column("id", sa.Integer, sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("game_id", sa.Integer, sa.ForeignKey("games.id"), nullable=False),
        sa.Column("score", mssql.TINYINT, nullable=False),
        sa.Column("title", sa.Unicode(120)),
        sa.Column("body", sa.Unicode(4000)),
        sa.Column("hidden", sa.Boolean, nullable=False, server_default="0"),     # by a moderator
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=NOW),
        sa.Column("updated_at", mssql.DATETIME2, nullable=False, server_default=NOW),
        sa.CheckConstraint("score BETWEEN 1 AND 10", name="ck_game_reviews_score"),
    )
    op.create_index("ux_game_reviews", "game_reviews", ["user_id", "game_id"], unique=True)
    op.create_index("ix_game_reviews_game", "game_reviews", ["game_id", "hidden"], mssql_include=["score"])

    # reviews can be reported like listings, users and ratings
    op.drop_constraint("ck_reports_kind", "reports", type_="check")
    op.create_check_constraint("ck_reports_kind", "reports", "kind IN ('listing', 'user', 'rating', 'review')")


def downgrade():
    op.execute("DELETE FROM reports WHERE kind = 'review'")
    op.drop_constraint("ck_reports_kind", "reports", type_="check")
    op.create_check_constraint("ck_reports_kind", "reports", "kind IN ('listing', 'user', 'rating')")
    op.drop_table("game_reviews")
