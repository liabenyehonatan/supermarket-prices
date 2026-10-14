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
    await loop.run_in_executor(None, command.downgrade, _database, "5532a7085020")
    await loop.run_in_executor(None, command.upgrade, _database, "head")


async def test_city_codes_are_resolved_by_migration(_database):
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, command.downgrade, _database, "b7d41c9e5a20")
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('1', 'MahsaniAShukNewSource')")
        for sid, city in [("a", "2600"), ("b", "0"), ("c", "unknown"), ("d", "חיפה"), ("e", "99999"), ("f", None)]:
            await conn.execute("INSERT INTO stores (chain_id, store_id, city) VALUES (1, $1, $2)", sid, city)
        await loop.run_in_executor(None, command.upgrade, _database, "head")
        cities = {r["store_id"]: r["city"] for r in await conn.fetch("SELECT store_id, city FROM stores")}
        assert cities == {"a": "אילת", "b": None, "c": None, "d": "חיפה", "e": None, "f": None}
        assert await conn.fetchval("SELECT name FROM chains") == "מחסני השוק"
    finally:
        await conn.close()


async def test_zero_id_chain_is_merged_into_the_real_chain(_database):
    import asyncio
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, command.downgrade, _database, "f2c8d6e14b71")
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('7290000000003', 'סיטי מרקט'), ('0000000000000', 'סיטי מרקט')")
        await conn.execute("INSERT INTO stores (chain_id, store_id) VALUES (1, '003'), (2, '003'), (2, '999')")
        await conn.execute("INSERT INTO products (barcode, name) VALUES ('b1', 'n1'), ('b2', 'n2')")
        await conn.execute(
            "INSERT INTO prices (product_id, store_id, price, price_updated_at, scraped_at, is_current) VALUES "
            "(1, 1, 5, '2026-10-01', '2026-10-01', true),"     # real chain, older
            "(1, 2, 6, '2026-10-01', '2026-10-10', true),"     # zero-id chain, newer scrape: wins
            "(2, 2, 7, '2026-10-01', '2026-10-10', true),"     # only under the zero-id chain: moves over
            "(1, 3, 8, '2026-10-01', '2026-10-10', true)"      # store that exists only under the zero-id chain
        )
        await loop.run_in_executor(None, command.upgrade, _database, "head")

        assert await conn.fetchval("SELECT count(*) FROM chains") == 1
        stores = await conn.fetch("SELECT id, chain_id, store_id FROM stores ORDER BY store_id")
        assert [(s["chain_id"], s["store_id"]) for s in stores] == [(1, "003"), (1, "999")]
        main003 = stores[0]["id"]
        current = await conn.fetch(
            "SELECT product_id, store_id, price FROM prices WHERE is_current ORDER BY product_id, store_id")
        assert [(r["product_id"], int(r["price"])) for r in current if r["store_id"] == main003] == [(1, 6), (2, 7)]
        assert await conn.fetchval("SELECT count(*) FROM prices") == 4      # nothing deleted
        assert await conn.fetchval("SELECT count(*) FROM prices WHERE is_current") == 3
    finally:
        await conn.close()


async def test_one_promotion_can_cover_many_products_in_a_store(_database):
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('1', 'c')")
        await conn.execute("INSERT INTO stores (chain_id, store_id) VALUES (1, 's')")
        await conn.execute("INSERT INTO products (barcode, name) VALUES ('a', 'n'), ('b', 'n')")
        await conn.execute(
            "INSERT INTO promotions (product_id, store_id, promotion_id, is_active) VALUES (1, 1, 'p', true), (2, 1, 'p', true)"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO promotions (product_id, store_id, promotion_id, is_active) VALUES (1, 1, 'p', true)"
            )
    finally:
        await conn.close()
