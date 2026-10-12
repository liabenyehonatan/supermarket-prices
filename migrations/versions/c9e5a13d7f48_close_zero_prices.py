"""Close current prices of 0 or less

Revision ID: c9e5a13d7f48
Revises: b8d4f02a6c15
Create Date: 2026-10-12 16:00:00

A price of 0 means "no price" (City Market's generic item, unavailable products); the app showed
it as the cheapest. New loads reject them; this closes the ones already stored (rows are kept,
never deleted) and refreshes the popularity counts.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c9e5a13d7f48"
down_revision: Union[str, None] = "b8d4f02a6c15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE prices SET is_current = false WHERE is_current AND price <= 0")
    op.execute("REFRESH MATERIALIZED VIEW product_store_counts")


def downgrade() -> None:
    pass  # not reopened: those rows were never real prices
