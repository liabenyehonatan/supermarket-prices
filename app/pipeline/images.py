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
from app.images import ImageLookupError, lookup_image_url, lookup_off_image_url
from app.pipeline.shutdown import STOP

logger = logging.getLogger(__name__)

IMAGE_RECHECK_DAYS = 14
PAUSE_BETWEEN_BATCHES = 1.0   # seconds; be polite to Shufersal's site
MAX_FAILED_BATCHES = 3        # consecutive batches that were mostly errors -> give up for now

# The products of the promotions section, as one set (a hashed join): `p.id = ANY(array_column)` per product cannot
# use an index and would rescan the whole view for each of ~240k products.
_DEAL_PRODUCTS = "WITH dp AS MATERIALIZED (SELECT DISTINCT unnest(product_ids) AS pid FROM promo_deals)"

_NEXT_BATCH = text(
    _DEAL_PRODUCTS + """
    SELECT p.id, p.barcode, p.name
      FROM products p
      LEFT JOIN dp ON dp.pid = p.id
      LEFT JOIN product_store_counts c ON c.product_id = p.id
     WHERE p.image_url IS NULL
       AND (p.image_checked_at IS NULL
            OR p.image_checked_at < now() - make_interval(days => :days))
     ORDER BY (dp.pid IS NOT NULL) DESC, coalesce(c.store_count, 0) DESC, p.id
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


# ── Second source: Open Food Facts ────────────────────────────────────────────────────────────────
# Asked only about products that still have no picture AFTER Shufersal was asked (it did not carry them), the
# products of the promotions section first. Open Food Facts allows about 100 product reads a minute, so one at a time.

OFF_PAUSE = 0.7        # seconds between requests: ~85 a minute
OFF_BATCH = 50
OFF_RECHECK_DAYS = 30

_NEXT_OFF_BATCH = text(
    _DEAL_PRODUCTS + """
    SELECT p.id, p.barcode
      FROM products p
      LEFT JOIN dp ON dp.pid = p.id
      LEFT JOIN product_store_counts c ON c.product_id = p.id
     WHERE p.image_url IS NULL
       AND p.image_checked_at IS NOT NULL                -- Shufersal was asked first and had nothing
       AND length(p.barcode) >= 8
       AND (p.off_checked_at IS NULL OR p.off_checked_at < now() - make_interval(days => :days))
     ORDER BY (dp.pid IS NOT NULL) DESC, coalesce(c.store_count, 0) DESC, p.id
     LIMIT :batch
    """
)


async def fill_images_off(minutes: float) -> tuple[int, int]:
    """Look up pictures at Open Food Facts for up to `minutes`; returns (found, not_found)."""
    deadline = time.monotonic() + minutes * 60
    found = missed = failures = 0
    while time.monotonic() < deadline and not STOP.is_set():
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(_NEXT_OFF_BATCH, {"days": OFF_RECHECK_DAYS, "batch": OFF_BATCH})).all()
        if not rows:
            break
        batch_errors = 0
        for row in rows:
            if time.monotonic() >= deadline or STOP.is_set():
                break
            try:
                url = await lookup_off_image_url(row.barcode)
            except ImageLookupError:
                batch_errors += 1          # could not ask: leave the product untouched, try again later
                backoff = min(60.0, OFF_PAUSE * 2 ** batch_errors)         # a rate limit or block: slow down, do not hammer
                await asyncio.sleep(backoff)
                continue
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    if url:
                        await session.execute(text("UPDATE products SET image_url = :u WHERE id = :i AND image_url IS NULL"),
                                              {"u": url, "i": row.id})   # never over a picture found meanwhile
                        found += 1
                    else:
                        await session.execute(text("UPDATE products SET off_checked_at = :t WHERE id = :i"),
                                              {"t": datetime.utcnow(), "i": row.id})
                        missed += 1
            await asyncio.sleep(OFF_PAUSE)
        if batch_errors * 2 > len(rows):
            failures += 1
            if failures >= MAX_FAILED_BATCHES:
                logger.warning("Open Food Facts pictures: lookups keep failing; stopping")
                break
        else:
            failures = 0
    if found or missed:
        logger.info("Open Food Facts pictures: %d found, %d not found", found, missed)
    return found, missed


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(fill_images(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
