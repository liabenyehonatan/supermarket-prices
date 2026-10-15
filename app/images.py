# app/images.py
#
# Product pictures come from Shufersal's online catalogue (found by barcode, then by a similar
# name) and, for what Shufersal does not carry, from Open Food Facts (found by barcode; their pictures are
# CC BY-SA, credited on the About page). Used lazily by the API (Shufersal only) and in bulk by the worker
# (app/pipeline/images.py).

import re
from contextlib import nullcontext
from typing import Optional

from urllib.parse import urlparse

import httpx

MIN_BARCODE_LEN = 7        # shorter codes are chain-internal: no one else's picture can be tied to them
SHUFERSAL_SEARCH = "https://www.shufersal.co.il/online/he/search/results"
SHUFERSAL_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# Sizes and units say nothing about WHAT a product is (a percentage like 3% does count).
_UNITS = {"גרם", "גר", "ג", "קג", "קילו", "מל", "ליטר", "ל", "יח", "יחידות", "יחידה", "מ", "סמ", "סמק", "ml", "g", "kg", "l", "cm"}
_NUMBER = re.compile(r"^\d+(\.\d+)?$")
_NUMBER_WITH_UNIT = re.compile(r"^\d+(\.\d+)?([^\d.%]+)$")      # 500מל
_PACK = re.compile(r"^(\d+[x×]|[x×]\d+)$")                       # 6x, x6


def _meaningful_tokens(name: str) -> list[str]:
    """The words of a product name that say WHAT it is, in order and without repeats."""
    words: dict[str, None] = {}
    for token in re.split(r"[\s/\-–()]+", (name or "").lower()):
        token = token.strip(",;:*+&!?.\"'״׳")
        core = token.replace('"', "").replace("״", "").replace("'", "").replace("׳", "")
        if not any(ch.isalnum() for ch in core) or _NUMBER.match(core) or _PACK.match(core) or core in _UNITS:
            continue
        glued = _NUMBER_WITH_UNIT.match(core)
        if glued and glued.group(2) in _UNITS:
            continue
        words[core] = None
    return list(words)


def _meaningful_words(name: str) -> set[str]:
    return set(_meaningful_tokens(name))


def names_match(our_name: str, their_name: str) -> bool:
    """True when their name names the same thing as ours. The first meaningful word of ours (the category: corn,
    shampoo, ice lolly) must be in theirs, and so must the rest, except that a long name (5+ words) may miss one.
    Matching only by overlap paired a corn with a mayonnaise ("light, reduced calories"); names are often cut short,
    so demanding more would throw away the many pictures that are right (dill, tomatoes, canola oil)."""
    ours = _meaningful_tokens(our_name)
    if not ours:
        return False
    theirs = _meaningful_words(their_name)
    if ours[0] not in theirs:
        return False
    return len([w for w in ours if w not in theirs]) <= (1 if len(ours) >= 5 else 0)


def code_matches_barcode(code: str, barcode: str) -> bool:
    """Shufersal's own item code (digits) is this barcode, its private-label tail (7290000 + 120874), or the same
    code with a leading zero (UPC-A against EAN-13). A short chain-internal code never matches anything."""
    if not code or not barcode or len(barcode) < MIN_BARCODE_LEN:
        return False
    if code == barcode:
        return True
    if len(code) >= 6 and barcode.startswith("7290") and barcode.endswith(code):
        return True
    return code.endswith(barcode) and len(code) - len(barcode) <= 1 and len(barcode) >= 8


def picture_code(url: Optional[str]) -> Optional[str]:
    """The Shufersal item code inside a picture URL (…/XYZ_M_P_120874_1.png -> 120874)."""
    found = re.search(r"P_(\d+)_", url or "")
    return found.group(1) if found else None


def picture_matches_barcode(url: Optional[str], barcode: str) -> bool:
    return code_matches_barcode(picture_code(url) or "", barcode)


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


async def lookup_image_url(barcode: str, name: Optional[str], client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Shufersal's picture URL for THIS product, or None. Found by barcode (the result's own code must be this
    barcode); failing that by name, but only when their name contains every meaningful word of ours (the closest
    name wins). Raises ImageLookupError when the lookup itself failed, so callers never record a failure as
    'no picture'."""
    if len(barcode or "") < MIN_BARCODE_LEN:
        return None
    try:
        async with (nullcontext(client) if client is not None else httpx.AsyncClient(timeout=8)) as http:
            async def search(q: str) -> list[dict]:
                resp = await http.get(SHUFERSAL_SEARCH, params={"q": q, "format": "json"}, headers=SHUFERSAL_HEADERS)
                resp.raise_for_status()
                return resp.json().get("results", [])

            def picture(result: dict) -> Optional[str]:
                url = result.get("baseProductImageMedium")
                return url if is_allowed_image_url(url) else None

            for result in await search(barcode):
                if code_matches_barcode(str(result.get("code", "")).removeprefix("P_"), barcode) and picture(result):
                    return picture(result)
            ours = _meaningful_words(name or "")
            if ours:                                             # nothing that names the product: do not ask
                best, fewest_extra = None, None
                for result in await search(name):
                    if picture(result) and names_match(name, result.get("name", "")):
                        extra = len(_meaningful_words(result.get("name", "")) - ours)
                        if fewest_extra is None or extra < fewest_extra:
                            best, fewest_extra = picture(result), extra
                return best
        return None
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ImageLookupError(str(exc)) from exc


OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
# Open Food Facts asks every app to identify itself, and allows about 100 product reads a minute.
OFF_HEADERS = {"User-Agent": "Sali-price-comparison/1.0 (liabenyehonatan@gmail.com)"}


def is_gtin(code: str) -> bool:
    """A real GTIN (EAN-8, UPC-A, EAN-13, GTIN-14) with a valid check digit. Chain-internal item codes are not:
    asking a public database about one could return another product's picture."""
    if not code or not code.isascii() or not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def off_front_image(payload: dict, barcode: Optional[str] = None) -> Optional[str]:
    """The front-of-pack picture in an Open Food Facts answer, only if it is on one of our allowed hosts
    (and, when `barcode` is given, only if the answer is for that barcode)."""
    if not isinstance(payload, dict) or payload.get("status") != 1:
        return None
    if barcode is not None and str(payload.get("code")) != barcode:
        return None
    url = (payload.get("product") or {}).get("image_front_url")
    return url if is_allowed_image_url(url) else None


async def lookup_off_image_url(barcode: str) -> Optional[str]:
    """Open Food Facts' front picture for this barcode, or None when it has none.
    Raises ImageLookupError when the lookup itself failed (outage, rate limit): that says nothing about the picture."""
    if not is_gtin(barcode):
        return None                           # not a real GTIN: nothing to ask, and no picture to trust
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(OFF_PRODUCT.format(barcode=barcode), params={"fields": "code,image_front_url"},
                                    headers=OFF_HEADERS)
        if resp.status_code == 404:
            return None                       # an unknown barcode answers 404 with status 0
        resp.raise_for_status()
        return off_front_image(resp.json(), barcode)
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        raise ImageLookupError(str(exc)) from exc
