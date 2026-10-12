# app/images.py
#
# Product pictures come from Shufersal's online catalogue (found by barcode, then by a similar
# name). Used lazily by the API and in bulk by the worker (app/pipeline/images.py).

from typing import Optional

import httpx

SHUFERSAL_SEARCH = "https://www.shufersal.co.il/online/he/search/results"
SHUFERSAL_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def _names_similar(our_name: str, their_name: str) -> bool:
    our_words = set(our_name.split())
    their_words = set(their_name.split())
    if not our_words:
        return False
    return len(our_words & their_words) / len(our_words) >= 0.6


async def lookup_image_url(barcode: str, name: Optional[str]) -> Optional[str]:
    """Ask Shufersal's catalogue for a product picture (by barcode, then by similar name)."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                SHUFERSAL_SEARCH,
                params={"q": barcode, "format": "json"},
                headers=SHUFERSAL_HEADERS,
            )
            results = resp.json().get("results", [])

            if not results and name:
                resp2 = await client.get(
                    SHUFERSAL_SEARCH,
                    params={"q": name, "format": "json"},
                    headers=SHUFERSAL_HEADERS,
                )
                name_results = resp2.json().get("results", [])
                results = [r for r in name_results if _names_similar(name, r.get("name", ""))]

        return results[0].get("baseProductImageMedium") if results else None
    except Exception:
        return None
