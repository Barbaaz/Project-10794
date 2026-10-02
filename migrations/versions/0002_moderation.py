"""Moderation: roles instead of is_admin, reports, the moderation log, hidden listings / ratings.

Revision ID: 0002_moderation
Revises: 0001_marketplace
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision = "0002_moderation"
down_revision = "0001_marketplace"
branch_labels = None
depends_on = None

NOW = sa.text("SYSUTCDATETIME()")


def upgrade():
    # Roles: user / moderator / admin. Whoever had is_admin becomes an admin (no one loses it)
    op.add_column("users", sa.Column("role", sa.String(10), nullable=False, server_default="user"))
    op.create_check_constraint("ck_users_role", "users", "role IN ('user', 'moderator', 'admin')")
    op.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")
    op.drop_column("users", "is_admin", mssql_drop_default=True)   # SQL Server: its default goes first

    op.add_column("user_listings", sa.Column("removed_by_moderator", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("user_ratings", sa.Column("hidden", sa.Boolean, nullable=False, server_default="0"))

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer, sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("reporter_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("details", sa.Unicode(1000)),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=NOW),
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("resolved_at", mssql.DATETIME2),
        sa.Column("resolution", sa.Unicode(500)),
        sa.CheckConstraint("kind IN ('listing', 'user', 'rating')", name="ck_reports_kind"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_reports_status"),
    )
    op.create_index("ix_reports_status", "reports", ["status", "created_at"])

    op.create_table(
        "moderation_log",
        sa.Column("id", sa.Integer, sa.Identity(start=1, increment=1), primary_key=True),
        sa.Column("moderator_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("target_id", sa.Integer, nullable=False),
        sa.Column("note", sa.Unicode(500)),
        sa.Column("created_at", mssql.DATETIME2, nullable=False, server_default=NOW),
    )


def downgrade():
    op.drop_table("moderation_log")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_table("reports")
    op.drop_column("user_ratings", "hidden", mssql_drop_default=True)
    op.drop_column("user_listings", "removed_by_moderator", mssql_drop_default=True)
    op.add_column("users", sa.Column("is_admin", sa.Boolean, nullable=False, server_default="0"))
    op.execute("UPDATE users SET is_admin = 1 WHERE role IN ('moderator', 'admin')")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role", mssql_drop_default=True)
