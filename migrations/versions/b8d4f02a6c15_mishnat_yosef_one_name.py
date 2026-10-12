"""Show both Mishnat Yosef feeds under one name

Revision ID: b8d4f02a6c15
Revises: a7c3e91f5b24
Create Date: 2026-10-12 15:00:00

The company publishes two feeds: the web shop (chain id 5144744100002) and the Kitty Market
branches (7290058289400, shown as "משנת יוסף 2"). Their store numbers overlap, so they stay two
chain rows, but users see one chain.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b8d4f02a6c15"
down_revision: Union[str, None] = "a7c3e91f5b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE chains SET name = 'משנת יוסף' WHERE chain_id = '7290058289400' AND name = 'משנת יוסף 2'")


def downgrade() -> None:
    op.execute("UPDATE chains SET name = 'משנת יוסף 2' WHERE chain_id = '7290058289400'")
