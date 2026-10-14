"""promotions.price_is_total: the description confirms the price is the total for N

Revision ID: l9b6f2c18e53
Revises: k8a5e1b07d42
Create Date: 2026-10-14 18:00:00

A promotion whose price for N units is not above one unit's shelf price may be a per-unit price misread
as a total. When the promotion's own text says "N ב-price" with the same N and price (e.g. "2ב18"),
the total reading is certain and the basket can use it. Existing rows stay false until their store's
next promotion file replaces them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l9b6f2c18e53"
down_revision: Union[str, None] = "k8a5e1b07d42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("price_is_total", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("promotions", "price_is_total")
