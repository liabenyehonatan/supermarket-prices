# app/images.py
#
# Product pictures come from Shufersal's online catalogue (found by barcode, then by a similar
# name) and, for what Shufersal does not carry, from Open Food Facts (found by barcode; their pictures are
# CC BY-SA, credited on the About page). Used lazily by the API (Shufersal only) and in bulk by the worker
# (app/pipeline/images.py).

from typing import Optional

from urllib.parse import urlparse

import httpx

SHUFERSAL_SEARCH = "https://www.shufersal.co.il/online/he/search/results"
SHUFERSAL_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def _names_similar(our_name: str, their_name: str) -> bool:
    our_words = set(our_name.split())
    their_words = set(their_name.split())
    if not our_words:
        return False
    return len(our_words & their_words) / len(our_words) >= 0.6


# Pictures are only ever served from the two sources' own image hosts (the API redirects the browser to them).
_ALLOWED_HOST_SUFFIXES = ("cloudinary.com", "shufersal.co.il", "openfoodfacts.org")


def is_allowed_image_url(url: Optional[str]) -> bool:
    try:
        parts = urlparse(url or "")
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(host == h or host.endswith("." + h) for h in _ALLOWED_HOST_SUFFIXES)


class ImageLookupError(Exception):
    """Shufersal could not be asked (outage, block page, rate limit): says nothing about the picture."""


async def lookup_image_url(barcode: str, name: Optional[str]) -> Optional[str]:
    """Shufersal's picture URL, or None when it has none (found by barcode, then by a similar name).
    Raises ImageLookupError when the lookup itself failed, so callers never record a failure as 'no picture'."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            async def search(q: str) -> list[dict]:
                resp = await client.get(
                    SHUFERSAL_SEARCH, params={"q": q, "format": "json"}, headers=SHUFERSAL_HEADERS)
                resp.raise_for_status()
                return resp.json().get("results", [])

            results = await search(barcode)
            if not results and name:
                results = [r for r in await search(name) if _names_similar(name, r.get("name", ""))]
        url = results[0].get("baseProductImageMedium") if results else None
        return url if is_allowed_image_url(url) else None
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ImageLookupError(str(exc)) from exc


OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
# Open Food Facts asks every app to identify itself, and allows about 100 product reads a minute.
OFF_HEADERS = {"User-Agent": "Sali-price-comparison/1.0 (liabenyehonatan@gmail.com)"}


def off_front_image(payload: dict) -> Optional[str]:
    """The front-of-pack picture in an Open Food Facts answer, only if it is on one of our allowed hosts."""
    if not isinstance(payload, dict) or payload.get("status") != 1:
        return None
    url = (payload.get("product") or {}).get("image_front_url")
    return url if is_allowed_image_url(url) else None


async def lookup_off_image_url(barcode: str) -> Optional[str]:
    """Open Food Facts' front picture for this barcode, or None when it has none.
    Raises ImageLookupError when the lookup itself failed (outage, rate limit): that says nothing about the picture."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(OFF_PRODUCT.format(barcode=barcode), params={"fields": "code,image_front_url"},
                                    headers=OFF_HEADERS)
        if resp.status_code == 404:
            return None                       # an unknown barcode answers 404 with status 0
        resp.raise_for_status()
        return off_front_image(resp.json())
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ImageLookupError(str(exc)) from exc
