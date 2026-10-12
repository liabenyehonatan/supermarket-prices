"""products.image_checked_at: remember that no picture was found

Revision ID: f2c8d6e14b71
Revises: e1f4b7a92c30
Create Date: 2026-10-12 13:00:00

Without it every view of a product with no picture asked Shufersal's site again.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2c8d6e14b71"
down_revision: Union[str, None] = "e1f4b7a92c30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_checked_at", sa.DateTime(), nullable=True))
    # The API (read-only role) records a miss when a picture is requested lazily.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
            GRANT UPDATE (image_checked_at) ON public.products TO api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.drop_column("products", "image_checked_at")
