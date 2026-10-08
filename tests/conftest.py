# tests/conftest.py
#
# Tests run against a throw-away PostgreSQL database that is created, migrated
# with Alembic and dropped around the session. They never touch DATABASE_URL's
# database: the URL is swapped BEFORE any app module is imported, and a guard
# refuses to run unless the database name contains "test".

import os
import re
import sys
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

_base_url = os.environ.get("TEST_DATABASE_URL") or re.sub(
    r"/[^/?]+(\?.*)?$", r"/sm_pytest\1", os.environ.get("DATABASE_URL", "")
)
if not _base_url or "test" not in _base_url.rsplit("/", 1)[-1]:
    raise RuntimeError(
        "Refusing to run: set TEST_DATABASE_URL (or DATABASE_URL) so the test "
        "database name contains 'test'."
    )
TEST_DB_URL = _base_url
TEST_DB_NAME = TEST_DB_URL.rsplit("/", 1)[-1].split("?")[0]
os.environ["DATABASE_URL"] = TEST_DB_URL  # must precede `import app...`

# Keep tests independent of the developer's .env.
os.environ["DELETE_AFTER_INGEST"] = "false"
os.environ["HEALTHCHECK_URL"] = ""
os.environ["HISTORY_RETENTION_DAYS"] = ""


def _admin_dsn() -> str:
    dsn = TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")
    return re.sub(r"/[^/?]+(\?.*)?$", "/postgres", dsn)


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Create a fresh database, migrate it to head, drop it afterwards."""
    import asyncio

    async def recreate():
        conn = await asyncpg.connect(_admin_dsn())
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        finally:
            await conn.close()

    async def drop():
        conn = await asyncpg.connect(_admin_dsn())
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)')
        finally:
            await conn.close()

    asyncio.run(recreate())

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")
    yield cfg
    asyncio.run(drop())


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Empty every table before each test."""
    from sqlalchemy import text

    from app.db.database import engine

    async with engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE ingested_files, ingest_runs, promotions, prices, products, stores, chains "
            "RESTART IDENTITY CASCADE"
        ))
    yield


@pytest_asyncio.fixture
async def session():
    from app.db.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def store(session):
    """A chain with one store, committed."""
    from app.db.models import Chain, Store

    chain = Chain(chain_id="7290000000001", name="Test Chain")
    session.add(chain)
    await session.flush()
    st = Store(chain_id=chain.id, store_id="001", name="Test Store", city="Tel Aviv")
    session.add(st)
    await session.commit()
    return st
