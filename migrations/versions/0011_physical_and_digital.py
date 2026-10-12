"""A game on a disc and as a download too (user, 2026-10-12): one owned item per edition and format,
no longer per edition; a wish has no format, and NULLS NOT DISTINCT keeps it to one per edition.

Revision ID: 0011_physical_and_digital
Revises: 0010_psn_import
Create Date: 2026-10-12
"""
from alembic import op

revision = "0011_physical_and_digital"
down_revision = "0010_psn_import"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ux_collection_items", table_name="collection_items")
    op.create_index("ux_collection_items", "collection_items", ["user_id", "edition_id", "kind", "format"],
                    unique=True, postgresql_nulls_not_distinct=True)


def downgrade():
    op.drop_index("ux_collection_items", table_name="collection_items")
    op.create_index("ux_collection_items", "collection_items", ["user_id", "edition_id", "kind"], unique=True)
