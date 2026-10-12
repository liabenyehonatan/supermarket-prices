"""Merge chains created from files whose ChainId is all zeros into the real chain

Revision ID: a7c3e91f5b24
Revises: f2c8d6e14b71
Create Date: 2026-10-12 14:00:00

A few City Market price files carry ChainId 0000000000000, so the loader created a second
"סיטי מרקט" chain (3 stores that already exist under the real chain, ~73k current prices).
Folds each such chain into the same-named real chain: where both have the same store id the
prices move over and, per product, only the most recently scraped current row stays current.
The data change cannot be undone (downgrade is a no-op).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a7c3e91f5b24"
down_revision: Union[str, None] = "f2c8d6e14b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TEMP TABLE _chain_pairs ON COMMIT DROP AS
        SELECT DISTINCT ON (d.id) d.id AS dup_id, m.id AS main_id
          FROM chains d JOIN chains m ON m.name = d.name AND m.id <> d.id AND m.chain_id !~ '^0+$'
         WHERE d.chain_id ~ '^0+$'
         ORDER BY d.id, m.id
    """)
    op.execute("""
        CREATE TEMP TABLE _store_pairs ON COMMIT DROP AS
        SELECT s_dup.id AS old_id, s_main.id AS new_id
          FROM _chain_pairs cp
          JOIN stores s_dup  ON s_dup.chain_id = cp.dup_id
          JOIN stores s_main ON s_main.chain_id = cp.main_id AND s_main.store_id = s_dup.store_id
    """)
    # Two current rows for the same (store, product) once merged: keep the most recently scraped one.
    op.execute("""
        WITH cur AS (
            SELECT p.id, p.product_id, sp.new_id AS store_id, p.scraped_at
              FROM prices p JOIN _store_pairs sp ON p.store_id = sp.old_id WHERE p.is_current
            UNION ALL
            SELECT p.id, p.product_id, p.store_id, p.scraped_at
              FROM prices p JOIN _store_pairs sp ON p.store_id = sp.new_id WHERE p.is_current
        ), ranked AS (
            SELECT id, row_number() OVER (PARTITION BY store_id, product_id
                                          ORDER BY scraped_at DESC NULLS LAST, id DESC) AS rn
              FROM cur
        )
        UPDATE prices SET is_current = false WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
    """)
    op.execute("UPDATE prices p SET store_id = sp.new_id FROM _store_pairs sp WHERE p.store_id = sp.old_id")
    op.execute("UPDATE promotions p SET store_id = sp.new_id FROM _store_pairs sp WHERE p.store_id = sp.old_id")
    op.execute("DELETE FROM stores WHERE id IN (SELECT old_id FROM _store_pairs)")
    # Stores that exist only under the zero-id chain simply move to the real chain.
    op.execute("""
        UPDATE stores s SET chain_id = cp.main_id FROM _chain_pairs cp WHERE s.chain_id = cp.dup_id
    """)
    op.execute("DELETE FROM chains WHERE id IN (SELECT dup_id FROM _chain_pairs)")


def downgrade() -> None:
    pass  # merged data is not split apart again
