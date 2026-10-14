"""No negative game data in the collection (user, 2026-10-14): hours and achievements are checked by
collection_service already; these checks hold for whatever else writes them (Steam / PSN imports, later
code). Reviews' scores, ratings' stars and listings' prices have had theirs since 0001.

Revision ID: 0017_no_negatives
Revises: 0016_notify
Create Date: 2026-10-14
"""
from alembic import op

revision = "0017_no_negatives"
down_revision = "0016_notify"
branch_labels = None
depends_on = None

CHECKS = [
    ("ck_collection_items_hours", "hours >= 0"),
    ("ck_collection_items_achievements",
     "achievements >= 0 AND achievements_total >= 0 AND achievements <= achievements_total"),
    ("ck_collection_items_prices", "wish_price >= 0 AND alert_price >= 0"),
]


def upgrade():
    for name, condition in CHECKS:
        op.create_check_constraint(name, "collection_items", condition)


def downgrade():
    for name, _ in reversed(CHECKS):
        op.drop_constraint(name, "collection_items", type_="check")
