# app/geocode.py
#
# Find a store's position from its address with OpenStreetMap's Nominatim (free; its usage policy
# allows about one request per second with an identifying User-Agent, fine for a few thousand stores).
# The price files give no coordinates, so "near me" and distances depend on this.

import re
from typing import Optional

import httpx

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "sali-prices/1.0 (https://github.com/liabenyehonatan/supermarket-prices)"}
# Israel, roughly: anything outside is a wrong match (a street of the same name abroad).
LAT_RANGE, LNG_RANGE = (29.3, 33.5), (34.1, 35.95)

JUNK_ADDRESS = re.compile(r"^(unknown|\d+|-+)$", re.I)


class GeocodeError(Exception):
    """The service could not be asked; says nothing about the address.

    `retryable` is True for outages, timeouts, 429 and 5xx (try again later, and stop if it keeps
    happening); False when this particular address makes the service answer with an error."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


def _inside_israel(lat: float, lng: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]


async def _search(client: httpx.AsyncClient, **params) -> Optional[tuple[float, float]]:
    try:
        resp = await client.get(NOMINATIM, params={"format": "jsonv2", "limit": 1, "countrycodes": "il",
                                                   "accept-language": "he", **params}, headers=HEADERS)
        resp.raise_for_status()
        results = resp.json()
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        raise GeocodeError(str(exc), retryable=code == 429 or code >= 500) from exc
    except httpx.HTTPError as exc:
        raise GeocodeError(str(exc)) from exc
    except ValueError as exc:                    # an answer that is not JSON
        raise GeocodeError(str(exc), retryable=False) from exc
    if not results:
        return None
    lat, lng = float(results[0]["lat"]), float(results[0]["lon"])
    return (lat, lng) if _inside_israel(lat, lng) else None


async def geocode(client: httpx.AsyncClient, address: Optional[str], city: Optional[str],
                  sleep) -> Optional[tuple[float, float, str]]:
    """(lat, lng, 'address'|'city') or None. `sleep` is awaited between requests (rate limit)."""
    address = (address or "").strip()
    city = (city or "").strip()
    if address and not JUNK_ADDRESS.match(address) and city:
        hit = await _search(client, street=address, city=city)
        await sleep()
        if hit is None:
            hit = await _search(client, q=f"{address}, {city}")
            await sleep()
        if hit is None:
            # "הסנה 15 א תעשיה": keep the street and number, drop trailing words that confuse the search
            short = re.match(r"^(\D+?\s\d+)", address)
            if short and short.group(1) != address:
                hit = await _search(client, street=short.group(1), city=city)
                await sleep()
        if hit:
            return hit[0], hit[1], "address"
    elif address and not JUNK_ADDRESS.match(address):
        hit = await _search(client, q=address)      # no city on record: let the search work it out
        await sleep()
        if hit:
            return hit[0], hit[1], "address"
    if city:
        hit = await _search(client, city=city)
        await sleep()
        if hit:
            return hit[0], hit[1], "city"
    return None
