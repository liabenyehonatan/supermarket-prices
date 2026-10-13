"""product_store_counts: add min_price / max_price so the home-page examples need no scan

Revision ID: h5d2b8e47a19
Revises: e4a1c7d95b83
Create Date: 2026-10-13 18:00:00

GET /products/examples aggregated every current price (11.6M rows) per request: 10-20 s, statement
timeouts (HTTP 500) under load. The same aggregate now lives in the materialized view the worker
already refreshes after each cycle.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "h5d2b8e47a19"
down_revision: Union[str, None] = "e4a1c7d95b83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS product_store_counts")
    op.execute(
        """
        CREATE MATERIALIZED VIEW product_store_counts AS
        SELECT product_id, count(*)::int AS store_count,
               min(price) AS min_price, max(price) AS max_price
          FROM prices
         WHERE is_current AND price > 0
         GROUP BY product_id
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_product_store_counts_product ON product_store_counts (product_id)")
    op.execute("CREATE INDEX ix_product_store_counts_popular ON product_store_counts (store_count DESC)")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
            GRANT SELECT ON product_store_counts TO api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS product_store_counts")
    op.execute(
        """
        CREATE MATERIALIZED VIEW product_store_counts AS
        SELECT product_id, count(*)::int AS store_count FROM prices WHERE is_current GROUP BY product_id
        """
    )
    op.execute("CREATE UNIQUE INDEX ix_product_store_counts_product ON product_store_counts (product_id)")
