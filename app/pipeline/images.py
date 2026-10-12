# app/pipeline/images.py
#
# Fill product pictures ahead of time, most-carried products first, so a search page does not
# wait on Shufersal's site for every row. A product with no picture is marked (image_checked_at)
# and not asked about again for IMAGE_RECHECK_DAYS. A lookup that FAILED (outage, block, rate
# limit) is never recorded as "no picture"; the job backs off and stops after repeated failures.

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import text

from app.db.database import AsyncSessionLocal
from app.images import ImageLookupError, lookup_image_url
from app.pipeline.shutdown import STOP

logger = logging.getLogger(__name__)

IMAGE_RECHECK_DAYS = 14
PAUSE_BETWEEN_BATCHES = 1.0   # seconds; be polite to Shufersal's site
MAX_FAILED_BATCHES = 3        # consecutive batches that were mostly errors -> give up for now

_NEXT_BATCH = text(
    """
    SELECT p.id, p.barcode, p.name
      FROM products p
      LEFT JOIN product_store_counts c ON c.product_id = p.id
     WHERE p.image_url IS NULL
       AND (p.image_checked_at IS NULL
            OR p.image_checked_at < now() - make_interval(days => :days))
     ORDER BY coalesce(c.store_count, 0) DESC, p.id
     LIMIT :batch
    """
)


async def fill_images(minutes: float, concurrency: int = 4, batch: int = 100) -> tuple[int, int]:
    """Look up pictures for up to `minutes`; returns (found, not_found)."""
    deadline = time.monotonic() + minutes * 60
    found = missed = 0
    failed_batches = 0
    gate = asyncio.Semaphore(concurrency)

    async def one(row):
        async with gate:
            return await lookup_image_url(row.barcode, row.name)

    while time.monotonic() < deadline and not STOP.is_set():
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(_NEXT_BATCH, {"days": IMAGE_RECHECK_DAYS, "batch": batch})).all()
        if not rows:
            break
        results = await asyncio.gather(*(one(r) for r in rows), return_exceptions=True)
        errors = sum(1 for r in results if isinstance(r, ImageLookupError))
        for r in results:
            if isinstance(r, BaseException) and not isinstance(r, ImageLookupError):
                raise r
        now = datetime.utcnow()
        async with AsyncSessionLocal() as session:
            async with session.begin():
                for row, url in zip(rows, results):
                    if isinstance(url, ImageLookupError):
                        continue   # could not ask: leave the product untouched, try again later
                    if url:
                        await session.execute(
                            text("UPDATE products SET image_url = :u WHERE id = :i"), {"u": url, "i": row.id})
                        found += 1
                    else:
                        await session.execute(
                            text("UPDATE products SET image_checked_at = :t WHERE id = :i"), {"t": now, "i": row.id})
                        missed += 1
        if errors * 2 > len(rows):
            failed_batches += 1
            if failed_batches >= MAX_FAILED_BATCHES:
                logger.warning("Product pictures: lookups keep failing (%d of %d in the last batch); stopping", errors, len(rows))
                break
        else:
            failed_batches = 0
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    if found or missed:
        logger.info("Product pictures: %d found, %d not found", found, missed)
    return found, missed


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(fill_images(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
