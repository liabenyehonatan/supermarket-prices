# app/pipeline/maintenance.py

import logging

from sqlalchemy import text

from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def prune_history(days: int, batch: int = 20000) -> int:
    """
    Delete NON-current price rows older than `days`. Opt-in only (see
    HISTORY_RETENTION_DAYS): by default the project keeps every price row.
    Current rows are never touched.
    """
    total = 0
    while True:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await session.execute(
                    text(
                        """
                        DELETE FROM prices WHERE id IN (
                            SELECT id FROM prices
                             WHERE NOT is_current
                               AND price_updated_at < now() - make_interval(days => :days)
                             LIMIT :batch
                        )
                        """
                    ),
                    {"days": days, "batch": batch},
                )
                deleted = result.rowcount or 0
        total += deleted
        if deleted < batch:
            break
    if total:
        logger.info("Pruned %d history rows older than %d days", total, days)
    return total
