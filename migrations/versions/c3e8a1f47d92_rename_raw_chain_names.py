"""give chains created from the *NewSource folders their Hebrew display name

Revision ID: c3e8a1f47d92
Revises: b7d41c9e5a20
Create Date: 2026-10-11 20:00:00

CHAIN_DISPLAY_NAMES had no entry for these folders, so the chain rows were
created with the raw folder name (e.g. 'MahsaniAShukNewSource'), which showed
in the UI and matched no logo or chain filter.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e8a1f47d92"
down_revision: Union[str, None] = "b7d41c9e5a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAMES = {
    "MahsaniAShukNewSource": "מחסני השוק",
    "HetCohenNewSource": "ח. כהן",
    "Mega": "מגה",
    "CityMarketGivatayim": "סיטי מרקט גבעתיים",
    "CityMarketKiryatOno": "סיטי מרקט קרית אונו",
}


def upgrade() -> None:
    conn = op.get_bind()
    for old, new in RENAMES.items():
        conn.execute(sa.text("UPDATE chains SET name = :new WHERE name = :old"), {"new": new, "old": old})


def downgrade() -> None:
    pass  # the raw folder names were a bug, not state worth restoring
