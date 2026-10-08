# app/pipeline/lock.py
#
# One ingest run at a time, across processes and hosts.
#
# A Postgres advisory lock is held on a dedicated connection for the whole run.
# If the process dies the connection drops and the lock frees itself, so there
# is no stale lock file to clean up. A background ping keeps the idle
# connection alive through firewalls and proxies during long scrapes.

import asyncio
import contextlib
import logging

from sqlalchemy import text

from app.db.database import engine

logger = logging.getLogger(__name__)

# Arbitrary constant shared by every ingest entry point ("sup" "prices").
INGEST_LOCK_KEY = 0x5355_5052


class AlreadyRunning(RuntimeError):
    """Another process holds the ingest lock."""


async def _keepalive(conn, interval: float = 60.0) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await conn.execute(text("SELECT 1"))
            await conn.commit()  # never sit "idle in transaction": it blocks vacuum
        except Exception as exc:  # the lock is gone if this connection is
            logger.error("Lock connection lost: %s", exc)
            return


@contextlib.asynccontextmanager
async def ingest_lock():
    async with engine.connect() as conn:
        got = (await conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": INGEST_LOCK_KEY}
        )).scalar_one()
        await conn.commit()
        if not got:
            raise AlreadyRunning("ingest lock is held by another run")
        pinger = asyncio.create_task(_keepalive(conn))
        try:
            yield
        finally:
            pinger.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pinger
            with contextlib.suppress(Exception):
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": INGEST_LOCK_KEY})
                await conn.commit()
