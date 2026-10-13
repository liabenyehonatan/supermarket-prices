"""Close current prices under 10 agorot

Revision ID: i6e3c9f58b20
Revises: h5d2b8e47a19
Create Date: 2026-10-13 19:00:00

About 6,000 current prices were 1-9 agorot: coupons and placeholders ("price on request"), shown as
"cheapest: 0.01". New loads reject them; this closes the existing ones (rows kept, never deleted).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "i6e3c9f58b20"
down_revision: Union[str, None] = "h5d2b8e47a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE prices SET is_current = false WHERE is_current AND price < 0.10")
    op.execute("REFRESH MATERIALIZED VIEW product_store_counts")


def downgrade() -> None:
    pass  # not reopened: those rows were never real prices
