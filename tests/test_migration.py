# The ingestion migration must be reversible and must repair duplicate data.

import asyncpg
import pytest
from alembic import command

from tests.conftest import TEST_DB_URL


def _dsn():
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")


async def test_duplicate_current_rows_are_repaired_on_upgrade(_database):
    cfg = _database
    # Go back to before the migration, create duplicates the old code could make.
    import asyncio
    await asyncio.get_running_loop().run_in_executor(None, command.downgrade, cfg, "5532a7085020")
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('1', 'c')")
        await conn.execute("INSERT INTO stores (chain_id, store_id) VALUES (1, 's')")
        await conn.execute("INSERT INTO products (barcode, name) VALUES ('b', 'n')")
        await conn.execute(
            "INSERT INTO prices (product_id, store_id, price, price_updated_at, is_current) VALUES "
            "(1, 1, 5, '2026-05-01', true), (1, 1, 6, '2026-05-03', true), (1, 1, 7, '2026-05-02', true)"
        )
        await asyncio.get_running_loop().run_in_executor(None, command.upgrade, cfg, "head")
        rows = await conn.fetch("SELECT price, is_current FROM prices ORDER BY price_updated_at")
        # newest price date (6) stays current, the other two are closed
        assert [(int(r["price"]), r["is_current"]) for r in rows] == [(5, False), (7, False), (6, True)]
    finally:
        await conn.close()


async def test_downgrade_then_upgrade_roundtrip(_database):
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, command.downgrade, _database, "-1")
    await loop.run_in_executor(None, command.upgrade, _database, "head")
