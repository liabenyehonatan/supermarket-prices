"""stores.last_full_at: confirm prices per store, not per price row

Revision ID: e4a1c7d95b83
Revises: d2b7a4e69c31
Create Date: 2026-10-13 09:00:00

Until now every unchanged price was rewritten (scraped_at) once a day: ~11.5 million UPDATEs per
daily cycle, which kept the 2-core database saturated for hours and bloated the prices table. A
store's full file confirms all the prices it lists, so that moment is now kept once per store.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4a1c7d95b83"
down_revision: Union[str, None] = "d2b7a4e69c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("last_full_at", sa.DateTime(), nullable=True))
    # Start from what we know: the newest confirmation of any current price of the store.
    op.execute("""
        UPDATE stores s SET last_full_at = x.newest
          FROM (SELECT store_id, max(scraped_at) AS newest FROM prices WHERE is_current GROUP BY store_id) x
         WHERE x.store_id = s.id
    """)


def downgrade() -> None:
    op.drop_column("stores", "last_full_at")
