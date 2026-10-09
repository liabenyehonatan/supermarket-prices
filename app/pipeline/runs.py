# app/pipeline/runs.py
#
# ingest_runs bookkeeping and the health queries built on it.

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, select, update

from app.db.database import AsyncSessionLocal
from app.db.models import IngestRun

logger = logging.getLogger(__name__)


async def start_run(phase: str, chain: Optional[str] = None, parent_id: Optional[int] = None) -> Optional[int]:
    """Insert a 'running' row. Returns None (and logs) if the DB is unreachable."""
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                run = IngestRun(phase=phase, chain=chain, parent_id=parent_id, status="running")
                session.add(run)
                await session.flush()
                return run.id
    except Exception as exc:
        logger.error("Could not record run start (%s %s): %s", phase, chain, exc)
        return None


async def finish_run(
    run_id: Optional[int],
    status: str,
    *,
    files_ok: int = 0,
    files_failed: int = 0,
    rows_applied: int = 0,
    error: Optional[str] = None,
) -> None:
    if run_id is None:
        return
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(IngestRun).where(IngestRun.id == run_id).values(
                        status=status,
                        finished_at=func.now(),
                        files_ok=files_ok,
                        files_failed=files_failed,
                        rows_applied=rows_applied,
                        error=(error or None) and error[:4000],
                    )
                )
    except Exception as exc:
        logger.error("Could not record run finish (%s): %s", run_id, exc)


async def close_abandoned_runs() -> int:
    """
    A crash leaves rows stuck at 'running'. Called at startup, while holding the
    ingest lock (so nothing is genuinely running), to mark them failed.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                update(IngestRun)
                .where(IngestRun.status == "running")
                .values(status="failed", finished_at=func.now(), error="abandoned (process died)")
            )
            return result.rowcount or 0


async def last_success_at() -> Optional[datetime]:
    """Finish time of the newest cycle that ended ok or partial."""
    async with AsyncSessionLocal() as session:
        return (await session.execute(
            select(func.max(IngestRun.finished_at)).where(
                IngestRun.phase == "cycle", IngestRun.status.in_(("ok", "partial"))
            )
        )).scalar_one()


async def data_age_hours() -> Optional[float]:
    finished = await last_success_at()
    if finished is None:
        return None
    # finished_at is the DB server's now(); compare against the DB's clock.
    async with AsyncSessionLocal() as session:
        now = (await session.execute(select(func.now()))).scalar_one()
    now = now.replace(tzinfo=None) if now.tzinfo else now
    return max(0.0, (now - finished).total_seconds() / 3600)


async def purge_old_runs(keep_days: int = 90) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                IngestRun.__table__.delete().where(
                    IngestRun.started_at < func.now() - timedelta(days=keep_days),
                    IngestRun.parent_id.is_(None),
                )
            )


async def purge_old_ledger(keep_days: int = 120) -> int:
    """Forget ledger rows older than the portals could still list the file."""
    from app.db.models import IngestedFile

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                IngestedFile.__table__.delete().where(
                    IngestedFile.updated_at < func.now() - timedelta(days=keep_days)
                )
            )
            return result.rowcount or 0
