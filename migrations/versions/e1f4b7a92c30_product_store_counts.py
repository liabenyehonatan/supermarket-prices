"""product_store_counts: precomputed popularity for search ranking

Revision ID: e1f4b7a92c30
Revises: d5a2c9b81e07
Create Date: 2026-10-12 12:00:00

Search ranked products by how many stores carry them with a GROUP BY over every
current price (about 10 million rows): ~9 s per search. This materialized view holds
the same counts; the worker refreshes it after every cycle.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e1f4b7a92c30"
down_revision: Union[str, None] = "d5a2c9b81e07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW product_store_counts AS
        SELECT product_id, count(*)::int AS store_count
          FROM prices
         WHERE is_current
         GROUP BY product_id
        """
    )
    # Required for REFRESH ... CONCURRENTLY (readers are not blocked while it refreshes).
    op.execute("CREATE UNIQUE INDEX ix_product_store_counts_product ON product_store_counts (product_id)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS product_store_counts")
