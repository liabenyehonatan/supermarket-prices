"""Stores only placed at their town's centre (or not found) are looked up again with the improved address search

Revision ID: q5a1e6c38da4
Revises: p4f0d5b27c93
Create Date: 2026-11-08 12:00:00
"""
from typing import Sequence, Union

from alembic import op

revision: str = "q5a1e6c38da4"
down_revision: Union[str, None] = "p4f0d5b27c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The worker's geocoding job picks up stores with no recent attempt. A town-centre position stays on the store
    # until a better one is found (the job never replaces a position with a worse one).
    op.execute("UPDATE stores SET geocoded_at = NULL WHERE geo_precision IN ('city', 'none')")


def downgrade() -> None:
    pass
