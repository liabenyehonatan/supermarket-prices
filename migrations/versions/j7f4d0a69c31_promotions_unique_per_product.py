"""promotions: unique per (promotion, store, product)

Revision ID: j7f4d0a69c31
Revises: i6e3c9f58b20
Create Date: 2026-10-14 10:00:00

One promotion lists many products; the old unique index (promotion_id, store_id) allowed one.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "j7f4d0a69c31"
down_revision: Union[str, None] = "i6e3c9f58b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_promotions_unique", table_name="promotions")
    op.create_index("ix_promotions_unique", "promotions", ["promotion_id", "store_id", "product_id"], unique=True)


def downgrade() -> None:
    # The table is derived data (rebuilt from the next full promo file), and the narrower index
    # cannot hold a promotion with several products.
    op.execute("DELETE FROM promotions")
    op.drop_index("ix_promotions_unique", table_name="promotions")
    op.create_index("ix_promotions_unique", "promotions", ["promotion_id", "store_id"], unique=True)
