# app/pipeline/watchdog.py
#
# Catch silent ingestion failures. A chain can be "ok" every cycle while loading nothing (it
# happened: 9 chains' files had no .xml name, so the loader found no files and reported success).
# Two independent signals:
#   * stale chain: none of its stores had a full price file loaded for STALE_CHAIN_DAYS
#   * files left on disk after a cycle: downloaded but never loaded (and not quarantined)
# Both are logged, listed in /health/data (stale chains) and, if HEALTHCHECK_CHAINS_URL is set,
# sent to a healthchecks.io check (a /fail ping with the details, or a success ping when clean).

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import text

from app import settings
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

_STALE = text(
    """
    SELECT c.name, max(s.last_full_at) AS newest
      FROM chains c LEFT JOIN stores s ON s.chain_id = c.id
     GROUP BY c.id, c.name
    HAVING count(s.id) > 0
       AND (max(s.last_full_at) IS NULL
            OR max(s.last_full_at) < now() - make_interval(days => :days))
     ORDER BY c.name
    """
)


async def stale_chains(days: Optional[float] = None) -> list[tuple[str, Optional[datetime]]]:
    """(chain name, newest full file or None) for chains whose data stopped arriving."""
    days = settings.STALE_CHAIN_DAYS if days is None else days
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(_STALE, {"days": days})).all()
    return [(r.name, r.newest) for r in rows]


def leftover_files(root: Path) -> dict[str, int]:
    """Files still in dumps/<chain>/ (not the status db, not the quarantine): downloaded, never loaded."""
    found: dict[str, int] = {}
    if not root.exists():
        return found
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name.startswith((".", "_")) or folder.name == "status":
            continue
        n = sum(1 for f in folder.iterdir() if f.is_file() and f.suffix != ".json")
        if n:
            found[folder.name] = n
    return found


async def _ping(suffix: str, body: str = "") -> None:
    url = settings.HEALTHCHECK_CHAINS_URL
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url + suffix, content=body.encode("utf-8"))
    except Exception as exc:
        logger.warning("chains healthcheck ping failed: %s", exc)


async def check_and_alert(dumps_root: Optional[Path] = None) -> list[str]:
    """Run both checks after a cycle; returns the problems found (empty = clean)."""
    problems: list[str] = []
    for name, newest in await stale_chains():
        problems.append(f"{name}: no full price file loaded since {newest:%Y-%m-%d %H:%M}" if newest
                        else f"{name}: no full price file has ever been loaded")
    for folder, count in leftover_files(dumps_root or settings.DUMPS_DIR).items():
        problems.append(f"{folder}: {count} downloaded file(s) were not loaded")
    for problem in problems:
        logger.warning("WATCHDOG %s", problem)
    await _ping("/fail" if problems else "", "\n".join(problems))
    return problems
