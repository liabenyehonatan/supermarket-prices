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
from app.images import ImageLookupError, lookup_image_url, lookup_off_image_url, picture_matches_barcode
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

OFF_PAUSE = 1.5        # seconds each worker waits after a request
OFF_BATCH = 50
OFF_CONCURRENCY = 2    # about 20 a minute. One at a time (14 a minute) was never limited; four at a time (~60) got 429 on 7 of 10 requests
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
    """Look up pictures at Open Food Facts for up to `minutes`; returns (found, not_found).
    A few requests at a time (a request takes seconds, so one by one managed ~14 a minute); each worker pauses
    OFF_PAUSE after its request, which keeps the total well under their ~100 a minute."""
    deadline = time.monotonic() + minutes * 60
    found = missed = failures = 0
    gate = asyncio.Semaphore(OFF_CONCURRENCY)

    async def one(row) -> str:
        """'found', 'missed' or 'error'."""
        async with gate:
            if time.monotonic() >= deadline or STOP.is_set():
                return "skipped"
            try:
                url = await lookup_off_image_url(row.barcode)
            except ImageLookupError:
                await asyncio.sleep(min(60.0, OFF_PAUSE * 8))       # a rate limit or block: slow down, do not hammer
                return "error"
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    if url:
                        await session.execute(text("UPDATE products SET image_url = :u WHERE id = :i AND image_url IS NULL"),
                                              {"u": url, "i": row.id})   # never over a picture found meanwhile
                    else:
                        await session.execute(text("UPDATE products SET off_checked_at = :t WHERE id = :i"),
                                              {"t": datetime.utcnow(), "i": row.id})
            await asyncio.sleep(OFF_PAUSE)
            return "found" if url else "missed"

    while time.monotonic() < deadline and not STOP.is_set():
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(_NEXT_OFF_BATCH, {"days": OFF_RECHECK_DAYS, "batch": OFF_BATCH})).all()
        if not rows:
            break
        outcomes = await asyncio.gather(*(one(r) for r in rows))
        found += outcomes.count("found")
        missed += outcomes.count("missed")
        errors = outcomes.count("error")
        if errors * 2 > len(rows):
            failures += 1
            if failures >= MAX_FAILED_BATCHES:
                logger.warning("Open Food Facts pictures: lookups keep failing; stopping")
                break
        else:
            failures = 0
    if found or missed:
        logger.info("Open Food Facts pictures: %d found, %d not found", found, missed)
    return found, missed


# ── Checking the pictures we already hold ─────────────────────────────────────────────────────────────────────────
# Until names were matched strictly, a picture could belong to another product (a corn wearing a mayonnaise).
# A Shufersal picture whose item code is not the product's barcode was chosen by name: look it up again with the
# strict rules, replace it when the right one exists, clear it when none does, and leave it when Shufersal cannot be asked.

_AUDIT_PAGE = text(
    _DEAL_PRODUCTS + """
    SELECT p.id, p.barcode, p.name, p.image_url
      FROM products p
      LEFT JOIN dp ON dp.pid = p.id
     WHERE p.id > :after AND p.image_url LIKE '%shufersal%'
       AND ((dp.pid IS NOT NULL) = :deals)
     ORDER BY p.id
     LIMIT :page
    """
)


_AUDIT_CANARIES = text(
    """
    SELECT barcode, name FROM products
     WHERE image_url LIKE '%shufersal%' AND length(barcode) = 13
       AND substring(image_url from 'P_([0-9]+)_') = barcode
     ORDER BY id LIMIT 5
    """
)


async def audit_images(concurrency: int = 4, page: int = 400, dry_run: bool = False) -> tuple[int, int, int, int]:
    """Returns (kept, replaced, cleared, failed). Products of the promotions section first, then the rest.
    `dry_run` only counts what it would do. Before every page a product Shufersal certainly carries (its picture's
    code IS its barcode) is looked up: if Shufersal does not answer it properly (a block that still returns an empty
    200, an outage) the audit stops, so an empty answer is never taken for "no picture"."""
    import httpx

    kept = replaced = cleared = failed = 0
    async with AsyncSessionLocal() as session:
        canaries = (await session.execute(_AUDIT_CANARIES)).all()
    if not canaries:
        logger.warning("Picture audit: no known-good product to check Shufersal with; not running")
        return kept, replaced, cleared, failed
    gate = asyncio.Semaphore(concurrency)
    pages = 0

    async with httpx.AsyncClient(timeout=8) as client:
        async def one(row):
            async with gate:
                return await lookup_image_url(row.barcode, row.name, client=client)

        async def shufersal_is_answering() -> bool:
            canary = canaries[pages % len(canaries)]
            try:
                return bool(await lookup_image_url(canary.barcode, canary.name, client=client))
            except ImageLookupError:
                return False

        for deals in (True, False):
            after = 0
            while not STOP.is_set():
                async with AsyncSessionLocal() as session:
                    rows = (await session.execute(_AUDIT_PAGE, {"after": after, "page": page, "deals": deals})).all()
                if not rows:
                    break
                after = rows[-1].id
                suspects = [r for r in rows if not picture_matches_barcode(r.image_url, r.barcode)]
                if suspects:
                    if not await shufersal_is_answering():
                        logger.error("Picture audit: Shufersal did not answer the known-good check; stopping before product %d", after)
                        return kept, replaced, cleared, failed
                    pages += 1
                    results = await asyncio.gather(*(one(r) for r in suspects), return_exceptions=True)
                    errors = sum(1 for r in results if isinstance(r, ImageLookupError))
                    now = datetime.utcnow()
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            for row, result in zip(suspects, results):
                                if isinstance(result, ImageLookupError):
                                    failed += 1
                                elif isinstance(result, BaseException):
                                    raise result
                                elif result == row.image_url:
                                    kept += 1
                                elif result:
                                    replaced += 1
                                    if not dry_run:       # never over a picture that changed since it was read
                                        await session.execute(
                                            text("UPDATE products SET image_url = :u WHERE id = :i AND image_url = :old"),
                                            {"u": result, "i": row.id, "old": row.image_url})
                                else:
                                    cleared += 1
                                    if not dry_run:
                                        await session.execute(
                                            text("UPDATE products SET image_url = NULL, image_checked_at = :t "
                                                 "WHERE id = :i AND image_url = :old"),
                                            {"t": now, "i": row.id, "old": row.image_url})
                    logger.info("Picture audit%s (%s): up to product %d: %d kept, %d replaced, %d cleared, %d failed",
                                " [dry run]" if dry_run else "", "deals" if deals else "rest", after, kept, replaced, cleared, failed)
                    if errors * 2 > len(suspects):
                        logger.error("Picture audit: most lookups on this page failed; stopping")
                        return kept, replaced, cleared, failed
                await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    return kept, replaced, cleared, failed


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if len(sys.argv) > 1 and sys.argv[1] == "audit":
        print(asyncio.run(audit_images(dry_run="--dry-run" in sys.argv)))      # (kept, replaced, cleared, failed)
    else:
        asyncio.run(fill_images(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
