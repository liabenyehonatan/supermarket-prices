# app/pipeline/geocode.py
#
# Give stores a position, in the background. Online "stores" (web shops) have no place and are
# marked as such. A store that could not be found is not asked about again for RECHECK_DAYS; a
# failed request (outage, block) is never recorded as "not found" and stops the job after a few in a row.

import asyncio
import logging
import time
from datetime import datetime

import httpx
from sqlalchemy import text

from app.db.database import AsyncSessionLocal
from app.geocode import GeocodeError, geocode
from app.pipeline.shutdown import STOP

logger = logging.getLogger(__name__)

RECHECK_DAYS = 30
PAUSE = 1.1            # seconds between Nominatim requests (its policy: at most one per second)
MAX_CONSECUTIVE_ERRORS = 5

_ONLINE = r"(online|אונליין|אינטרנט|^\s*(https?://|www\.))"

_NEXT = text(
    """
    SELECT id, name, address, city FROM stores
     WHERE latitude IS NULL
       AND (geocoded_at IS NULL OR geocoded_at < now() - make_interval(days => :days))
     ORDER BY id
     LIMIT :batch
    """
)


async def fill_geocodes(minutes: float, batch: int = 50) -> tuple[int, int]:
    """Locate stores for up to `minutes`; returns (found, not_found)."""
    import re

    online = re.compile(_ONLINE, re.I)
    deadline = time.monotonic() + minutes * 60
    found = missed = errors = 0
    city_cache: dict[str, tuple | None] = {}

    async def pause():
        await asyncio.sleep(PAUSE)

    async with httpx.AsyncClient(timeout=15) as client:
        while time.monotonic() < deadline and not STOP.is_set():
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(_NEXT, {"days": RECHECK_DAYS, "batch": batch})).all()
            if not rows:
                break
            for row in rows:
                if time.monotonic() >= deadline or STOP.is_set():
                    break
                now = datetime.utcnow()
                if online.search(row.name or "") or online.search(row.address or ""):
                    result, precision = None, "none"        # a web shop: nowhere to navigate to
                else:
                    try:
                        hit = await geocode(client, row.address, row.city, pause)
                    except GeocodeError as exc:
                        errors += 1
                        logger.warning("geocode failed for store %s: %s", row.id, exc)
                        if errors >= MAX_CONSECUTIVE_ERRORS:
                            logger.warning("Geocoding keeps failing; stopping for now")
                            return found, missed
                        await pause()
                        continue
                    errors = 0
                    result, precision = (hit[:2], hit[2]) if hit else (None, "none")
                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        await session.execute(
                            text("UPDATE stores SET latitude = :lat, longitude = :lng, geo_precision = :p, geocoded_at = :t WHERE id = :i"),
                            {"lat": result[0] if result else None, "lng": result[1] if result else None,
                             "p": precision, "t": now, "i": row.id})
                if result:
                    found += 1
                else:
                    missed += 1
    if found or missed:
        logger.info("Store positions: %d found, %d not found", found, missed)
    return found, missed


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(fill_geocodes(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
