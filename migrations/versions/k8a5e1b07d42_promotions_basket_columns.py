"""promotions: basket_eligible + max_qty, stores.last_promo_at

Revision ID: k8a5e1b07d42
Revises: j7f4d0a69c31
Create Date: 2026-10-14 15:00:00

Phase B1: the basket prices a line with a promotion only when the loader marked it safe
(basket_eligible), honouring the purchase limit (max_qty), and only for stores whose promotion data is
fresh (last_promo_at). Existing rows stay not eligible until the store's next promotion file replaces them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k8a5e1b07d42"
down_revision: Union[str, None] = "j7f4d0a69c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("basket_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("promotions", sa.Column("max_qty", sa.Integer(), nullable=True))
    op.add_column("stores", sa.Column("last_promo_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_promotions_basket", "promotions", ["product_id", "store_id"],
        postgresql_where=sa.text("basket_eligible"),
    )


def downgrade() -> None:
    op.drop_index("ix_promotions_basket", table_name="promotions")
    op.drop_column("stores", "last_promo_at")
    op.drop_column("promotions", "max_qty")
    op.drop_column("promotions", "basket_eligible")
