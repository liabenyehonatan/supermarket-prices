# app/geocode.py
#
# Find a store's position from its address with OpenStreetMap's Nominatim (free; its usage policy
# allows about one request per second with an identifying User-Agent, fine for a few thousand stores).
# The price files give no coordinates, so "near me" and distances depend on this.

import math
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


MAX_KM_FROM_CITY = 30
_city_centres: dict[str, Optional[tuple[float, float]]] = {}


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lng1), (lat2, lng2) = a, b
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2))
    return 6371 * math.hypot(x, math.radians(lat2 - lat1))


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


# Abbreviations chains use for cities, which the search does not know.
_ABBREVIATIONS = {'ראשל"צ': "ראשון לציון", 'ת"א': "תל אביב", 'פ"ת': "פתח תקווה", 'ב"ש': "באר שבע",
                  "ק.גת": "קרית גת", "ק.אונו": "קרית אונו", 'ר"ג': "רמת גן", 'נס"צ': "נס ציונה", 'ק"ש': "קרית שמונה"}


def expand_abbreviations(text: str) -> str:
    for short, full in _ABBREVIATIONS.items():
        text = text.replace(short, full)
    return text


def clean_address(address: str) -> str:
    """"רח' דרויאנוב 5" / "רח.משה שפירא 28" / "14 רחוב הבנים" -> the street and number alone: street words,
    brackets, a trailing town and stray punctuation are things the search does not know."""
    address = re.sub(r"\([^)]*\)", " ", address)
    address = address.replace('"', "").replace("׳", "'").replace("’", "'")
    address = re.sub(r"(?<![\w])(שד'|שד\.)\s*", "שדרות ", address)
    address = re.sub(r"(?<![\w])(רח'|רח\.|רחוב|רח)(?![\w])\.?\s*", " ", address)
    address = address.split(",")[0]                     # "שחר 79, ירושלים." -> "שחר 79"
    return re.sub(r"\s+", " ", address).strip(" .,-")


def street_only(address: str) -> str:
    """The street without the house number or a "corner of" part: "הזית פינת גלבוע" -> "הזית", "הרצל 12 א" -> "הרצל"."""
    address = re.split(r"\s+(?:פינת|ליד|מול|פינה)\s+", address)[0]
    address = re.sub(r"\s+\d.*$", "", address)           # "הרצל 12 א" -> "הרצל"
    address = re.sub(r"^\d+\s+", "", address)            # "12 הרצל" -> "הרצל"
    return address.strip(" ,-")


def city_variants(city: str) -> list[str]:
    """The same town is written in several ways: "קריית"/"קרית", with a hyphen or without."""
    base = city.replace("-", " ").replace("־", " ").replace("  ", " ").strip()
    variants = [city, base, base.replace("קריית", "קרית"), base.replace("קרית", "קריית"), base.replace("'", "")]
    return list(dict.fromkeys(v for v in variants if v))


def address_in_name(name: Optional[str]) -> str:
    """Some chains (City Market) publish no address, but the name ends with it:
    'סיטי מרקט הרצוג גבעתיים, הרצוג 23 גבעתיים' -> 'הרצוג 23 גבעתיים'."""
    parts = (name or "").rsplit(",", 1)
    tail = parts[-1].strip() if len(parts) == 2 else ""
    return expand_abbreviations(tail) if re.search(r"\d", tail) else ""


async def geocode(client: httpx.AsyncClient, address: Optional[str], city: Optional[str],
                  sleep, name: Optional[str] = None) -> Optional[tuple[float, float, str]]:
    """(lat, lng, 'address'|'street'|'city') or None. 'street': the right street, not the house number. `sleep` is awaited between requests (rate limit)."""
    address = (address or "").strip()
    city = (city or "").strip()
    if city and city not in _city_centres:
        _city_centres[city] = None
        for town in city_variants(city)[:3]:
            _city_centres[city] = await _search(client, city=town)
            await sleep()
            if _city_centres[city]:
                break

    def plausible(hit: Optional[tuple[float, float]]) -> Optional[tuple[float, float]]:
        """A street of the same name in another town is the usual wrong match: reject it."""
        centre = _city_centres.get(city) if city else None
        if hit and centre and _km(hit, centre) > MAX_KM_FROM_CITY:
            return None
        return hit

    if (not address or JUNK_ADDRESS.match(address)) and not city:
        tail = address_in_name(name)
        if tail:
            hit = await _search(client, q=tail)
            await sleep()
            if hit:
                return hit[0], hit[1], "address"
    if address and not JUNK_ADDRESS.match(address) and city:
        cleaned = clean_address(address)
        # Each way of writing the street and the town, most exact first. A street of the same name in another town
        # is the usual wrong match, so `plausible` rejects anything far from the town's centre.
        for town in city_variants(city)[:2]:
            for addr in dict.fromkeys([address, cleaned]):
                for params in ({"street": addr, "city": town}, {"q": f"{addr}, {town}"}):
                    hit = plausible(await _search(client, **params))
                    await sleep()
                    if hit:
                        return hit[0], hit[1], "address"
            # "הסנה 15 א תעשיה": keep the street and number, drop trailing words that confuse the search
            short = re.match(r"^(\D+?\s\d+)", cleaned)
            if short and short.group(1) != cleaned:
                hit = plausible(await _search(client, street=short.group(1), city=town))
                await sleep()
                if hit:
                    return hit[0], hit[1], "address"
        # The street itself, without the number: the pin lands on the right street, which is good enough on a map.
        street = street_only(cleaned)
        if len(street) >= 3:
            hit = plausible(await _search(client, street=street, city=city_variants(city)[0]))
            await sleep()
            if hit:
                return hit[0], hit[1], "street"
    elif address and not JUNK_ADDRESS.match(address) and name:
        # No city on record. A bare street ("צה\"ל 34") matches the wrong town, but the store name
        # usually carries the town ("חדרה חדש", "נתניה", "ירושלים תלפיות"): search with both.
        hit = await _search(client, q=f"{address}, {expand_abbreviations(name)}")
        await sleep()
        if hit:
            return hit[0], hit[1], "address"
        # Street not found: at least put the store in the town its name mentions ("פרדס חנה", "חדרה חדש").
        for place in dict.fromkeys([expand_abbreviations(name), " ".join(expand_abbreviations(name).split()[:2])]):
            hit = await _search(client, q=place)
            await sleep()
            if hit:
                return hit[0], hit[1], "city"
    if city and _city_centres.get(city):
        return _city_centres[city][0], _city_centres[city][1], "city"
    return None
