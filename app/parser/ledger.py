# app/parser/ledger.py
#
# The ingested_files ledger and the file housekeeping around it.
#
# Rule of the pipeline: a file is "loaded" when its ledger row says done, never
# because it exists (or no longer exists) on disk. The ledger row is written in
# the same transaction as the data, and the file is deleted only after commit,
# so a crash can leave a loaded file on disk (cleaned up next run) but never a
# deleted file whose data is missing.

import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import IngestedFile

logger = logging.getLogger(__name__)

DONE = "done"
FAILED = "failed"
QUARANTINED = "quarantined"
SUPERSEDED = "superseded"   # a newer full file for the same store exists; never loaded

# ...-20260512-030442.xml  or  ...-202605120201.xml
_TS_RE = re.compile(r"(\d{8})-?(\d{4,6})(?=\.\w+$)")


def file_timestamp(file_name: str) -> Optional[datetime]:
    """The publish time encoded in a dump file name, if there is one."""
    match = _TS_RE.search(file_name)
    if not match:
        return None
    date_part, time_part = match.groups()
    time_part = time_part.ljust(6, "0")[:6]
    try:
        return datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
    except ValueError:
        return None


@dataclass(frozen=True)
class LedgerEntry:
    status: str
    attempts: int
    file_type: str = ""


async def load_ledger(session: AsyncSession, source_folder: str) -> dict[str, LedgerEntry]:
    result = await session.execute(
        select(IngestedFile.file_name, IngestedFile.status, IngestedFile.attempts, IngestedFile.file_type)
        .where(IngestedFile.source_folder == source_folder)
    )
    return {name: LedgerEntry(status, attempts, ftype) for name, status, attempts, ftype in result.all()}


async def record_done(
    session: AsyncSession,
    source_folder: str,
    file_name: str,
    file_type: str,
    *,
    rows_total: int,
    rows_applied: int,
    rows_skipped: int,
) -> None:
    """Write the 'done' row. Call it inside the data transaction."""
    stmt = pg_insert(IngestedFile).values(
        source_folder=source_folder,
        file_name=file_name,
        file_type=file_type,
        status=DONE,
        attempts=1,
        rows_total=rows_total,
        rows_applied=rows_applied,
        rows_skipped=rows_skipped,
        last_error=None,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_ingested_files_source_name",
        set_={
            "status": DONE,
            "attempts": IngestedFile.attempts + 1,
            "rows_total": stmt.excluded.rows_total,
            "rows_applied": stmt.excluded.rows_applied,
            "rows_skipped": stmt.excluded.rows_skipped,
            "last_error": None,
            "updated_at": datetime.now(),
        },
    )
    await session.execute(stmt)


async def record_failure(
    session: AsyncSession,
    source_folder: str,
    file_name: str,
    file_type: str,
    error: str,
) -> str:
    """
    Count a failed attempt in its own transaction (the data transaction was
    rolled back). Returns the resulting status, 'quarantined' once the file has
    failed PARSE_MAX_ATTEMPTS times.
    """
    stmt = pg_insert(IngestedFile).values(
        source_folder=source_folder,
        file_name=file_name,
        file_type=file_type,
        status=FAILED,
        attempts=1,
        last_error=error[:2000],
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_ingested_files_source_name",
        set_={
            "attempts": IngestedFile.attempts + 1,
            "last_error": stmt.excluded.last_error,
            "updated_at": datetime.now(),
        },
    ).returning(IngestedFile.attempts)
    attempts = (await session.execute(stmt)).scalar_one()

    if attempts >= settings.PARSE_MAX_ATTEMPTS:
        await mark_quarantined(session, source_folder, file_name)
        return QUARANTINED
    return FAILED


async def record_superseded(
    session: AsyncSession, source_folder: str, file_names: list[str]
) -> None:
    """Mark full files as skipped because a newer one for their store is (or was) loaded."""
    for start in range(0, len(file_names), 500):
        stmt = pg_insert(IngestedFile).values([
            {"source_folder": source_folder, "file_name": name, "file_type": "price_full",
             "status": SUPERSEDED, "attempts": 0}
            for name in file_names[start:start + 500]
        ])
        await session.execute(stmt.on_conflict_do_nothing(constraint="uq_ingested_files_source_name"))


async def mark_quarantined(session: AsyncSession, source_folder: str, file_name: str) -> None:
    await session.execute(
        pg_insert(IngestedFile)
        .values(
            source_folder=source_folder,
            file_name=file_name,
            file_type="unknown",
            status=QUARANTINED,
            attempts=settings.PARSE_MAX_ATTEMPTS,
        )
        .on_conflict_do_update(
            constraint="uq_ingested_files_source_name",
            set_={"status": QUARANTINED, "updated_at": datetime.now()},
        )
    )


def quarantine_file(path: Path) -> None:
    """Move a poison file out of the way (kept for inspection, never re-parsed)."""
    if not path.exists():
        return
    target_dir = settings.DUMPS_DIR / "_quarantine" / path.parent.name
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target_dir / path.name))
        logger.error("Quarantined %s -> %s", path.name, target_dir)
    except OSError as exc:
        logger.error("Could not quarantine %s: %s", path, exc)


def delete_loaded_file(path: Path) -> None:
    """Remove a file whose data is committed. Never raises."""
    if not settings.DELETE_AFTER_INGEST:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete %s: %s", path, exc)
