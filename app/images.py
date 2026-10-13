# app/images.py
#
# Product pictures come from Shufersal's online catalogue (found by barcode, then by a similar
# name). Used lazily by the API and in bulk by the worker (app/pipeline/images.py).

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


# Pictures are only ever served from Shufersal's own image hosts (the API redirects the browser to them).
_ALLOWED_HOST_SUFFIXES = ("cloudinary.com", "shufersal.co.il")


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
