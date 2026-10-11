"""store.city: replace CBS locality codes with the city name, blank out junk

Revision ID: d5a2c9b81e07
Revises: c3e8a1f47d92
Create Date: 2026-10-11 21:00:00

Most chains publish <City> as the CBS locality code ('2600'); some publish '0'
or 'unknown'. The UI showed the code and the city filter could not match it.
New loads go through app.parser.city_codes.resolve_city; this fixes the rows
already stored.
"""
import json
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d5a2c9b81e07"
down_revision: Union[str, None] = "c3e8a1f47d92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODES = Path(__file__).resolve().parents[2] / "app" / "data" / "city_codes.json"


def upgrade() -> None:
    conn = op.get_bind()
    codes = json.loads(_CODES.read_text(encoding="utf-8"))
    for code, name in codes.items():
        conn.execute(
            sa.text("UPDATE stores SET city = :name WHERE city ~ '^[0-9]+$' AND ltrim(city, '0') = :code"),
            {"name": name, "code": str(int(code))},
        )
    # whatever is still numeric ('0', unknown codes) or 'unknown' is not a city
    conn.execute(sa.text("UPDATE stores SET city = NULL WHERE city ~ '^[0-9]+$' OR lower(city) = 'unknown'"))


def downgrade() -> None:
    pass  # the codes were never worth restoring
