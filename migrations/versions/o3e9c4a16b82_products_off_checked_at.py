"""products.off_checked_at: when Open Food Facts was last asked for a picture and had none

Revision ID: o3e9c4a16b82
Revises: n2d8b3f05a71
Create Date: 2026-10-15 14:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o3e9c4a16b82"
down_revision: Union[str, None] = "n2d8b3f05a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("off_checked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "off_checked_at")
