"""stores.geo_precision / geocoded_at: remember how and when a store was located

Revision ID: d2b7a4e69c31
Revises: c9e5a13d7f48
Create Date: 2026-10-12 17:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d2b7a4e69c31"
down_revision: Union[str, None] = "c9e5a13d7f48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("geo_precision", sa.String(10), nullable=True))
    op.add_column("stores", sa.Column("geocoded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("stores", "geocoded_at")
    op.drop_column("stores", "geo_precision")
