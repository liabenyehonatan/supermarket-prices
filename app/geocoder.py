"""
Geocode store locations using Nominatim (OpenStreetMap) — free, 1 req/sec rate limit.

Usage:
    python -m app.geocoder              # geocode all stores missing coords
    python -m app.geocoder --dry-run    # preview what would be geocoded
"""

import asyncio
import logging
import re
import time
from urllib.parse import quote

import httpx
from sqlalchemy import select, func

from app.db.database import AsyncSessionLocal
from app.db.models import Store, Chain

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "Machirista/1.0 (supermarket price comparison)"
RATE_LIMIT_SECONDS = 1.1


def build_search_query(store_name: str, chain_name: str) -> str:
    """
    Extract location hints from the store name for geocoding.
    Store names follow patterns like:
      "80 - שלי ראשל"צ- נווה הדרים"  → "ראשון לציון נווה הדרים"
      "133 - יש חסד ביתר עילית- הר״ן" → "ביתר עילית"
      "244 - יוניברס גלילות רמתהשרון" → "גלילות רמת השרון"
    """
    name = store_name.strip()

    # Strip leading store number like "80 - " or "133 - "
    name = re.sub(r"^\d+\s*[-–־]\s*", "", name)

    # Remove common chain sub-brand prefixes that aren't location info
    prefixes = [
        "שופרסל", "דיל", "יש חסד", "יש", "יוניברס", "שלי", "אקספרס",
        "be", "big", "BIG", "Be", "סופר", "מיני", "אקסטרא", "online",
    ]
    for p in prefixes:
        if name.startswith(p):
            name = name[len(p):].strip()
            break

    # Split on common delimiters
    name = name.replace("-", " ").replace("–", " ").replace("־", " ")

    # Expand common Hebrew city abbreviations
    abbreviations = {
        'ראשל"צ': "ראשון לציון",
        'פ"ת': "פתח תקווה",
        'ב"ש': "באר שבע",
        'ת"א': "תל אביב",
        'ר"ג': "רמת גן",
        'ב"ב': "בני ברק",
        'כ"ס': "כפר סבא",
        'ר"ה': "ראש העין",
    }
    for abbr, full in abbreviations.items():
        name = name.replace(abbr, full)

    # Clean up extra whitespace
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        name = store_name.strip()

    return f"{name}, ישראל"


async def geocode_one(client: httpx.AsyncClient, query: str) -> tuple[float, float] | None:
    """Query Nominatim for a single address. Returns (lat, lng) or None."""
    try:
        resp = await client.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "json",
                "countrycodes": "il",
                "limit": 1,
                "accept-language": "he",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        logger.warning(f"Geocode failed for '{query}': {e}")
    return None


async def geocode_all_stores(dry_run: bool = False):
    """Geocode all stores that are missing latitude/longitude."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Store, Chain.name)
            .join(Chain, Store.chain_id == Chain.id)
            .where(Store.latitude.is_(None))
            .order_by(Store.id)
        )
        rows = result.all()

    total = len(rows)
    logger.info(f"Found {total} stores without coordinates")

    if dry_run:
        for store, chain_name in rows[:20]:
            query = build_search_query(store.name or "", chain_name)
            logger.info(f"  [{store.id}] {chain_name} / {store.name} → query: '{query}'")
        if total > 20:
            logger.info(f"  ... and {total - 20} more")
        return

    geocoded = failed = 0
    last_request = 0.0

    async with httpx.AsyncClient() as client:
        for i, (store, chain_name) in enumerate(rows):
            # A store with neither a name nor a city gives build_search_query nothing
            # to work with — it used to fall back to just "ישראל", which Nominatim
            # happily matched to the country's own centroid. Skip these instead of
            # saving a coordinate that puts every one of them in the same wrong place.
            if not (store.name or "").strip() and not (store.city or "").strip():
                failed += 1
                logger.warning(f"  [{i+1}/{total}] store {store.id} → SKIPPED (no name or city to geocode)")
                continue

            query = build_search_query(store.name or store.city or "", chain_name)

            # Rate limiting
            elapsed = time.monotonic() - last_request
            if elapsed < RATE_LIMIT_SECONDS:
                await asyncio.sleep(RATE_LIMIT_SECONDS - elapsed)

            last_request = time.monotonic()
            coords = await geocode_one(client, query)

            if coords:
                lat, lng = coords
                try:
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            s = await session.get(Store, store.id)
                            s.latitude = lat
                            s.longitude = lng
                except Exception as e:
                    logger.warning(f"DB write failed for store {store.id}: {e}")
                    failed += 1
                    continue
                geocoded += 1
                logger.info(f"  [{i+1}/{total}] {store.name} → {lat:.4f}, {lng:.4f}")
            else:
                failed += 1
                logger.warning(f"  [{i+1}/{total}] {store.name} → NOT FOUND (query: '{query}')")

            if (i + 1) % 100 == 0:
                logger.info(f"Progress: {i+1}/{total} ({geocoded} geocoded, {failed} failed)")

    logger.info(f"Done: {geocoded} geocoded, {failed} failed out of {total}")


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    asyncio.run(geocode_all_stores(dry_run=dry))
