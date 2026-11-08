# app/street_match.py
#
# Chains write street names their own way: without the vowel letters ("זהר טל" for OpenStreetMap's "זוהר טל"), with a
# surname first ("גרינבאום יצחק"), with the quote marks of an abbreviation dropped ("צהל" for "צה"ל"), with or without
# the street's title ("רח'", "שד'"). Nominatim only finds an exact spelling, so the stores written the other way stay
# at their town's centre. This asks OpenStreetMap (Overpass) once for every street name of a town and picks the one
# that is the same name once those differences are ignored.

import asyncio
import json
import os as _os
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import httpx

from app import settings

OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "sali-prices/1.0 (https://github.com/liabenyehonatan/supermarket-prices)"}
CACHE_DIR = Path(_os.environ.get("STREETS_CACHE_DIR") or settings.DUMPS_DIR / "streets")      # on the worker's persistent volume

# Words that say what kind of street it is, not which one
_TITLES = {"רח", "רחוב", "שד", "שדרות", "שדרה", "דרך", "סמטת", "סמטה", "כיכר", "שכ", "שכונת", "שכונה", "רובע", "אזור", "ככר", "רחבת", "רחבה"}
_QUOTES = re.compile(r"[\"'`׳״’‘´]")          # inside a word (צה"ל, ג'ורג'): the word stays one word
_PUNCT = re.compile(r"[.,()\-־/\\]")                # between words
MIN_RATIO = 0.9
RETRY_PAUSE, POLITE_PAUSE = 5, 2          # seconds: after a failure, and after every request (the public server is shared)

# town -> [(name, lat, lng)], kept for the life of the process
_streets: dict[str, Optional[list[tuple[str, float, float]]]] = {}


def skeleton(name: str) -> tuple[str, ...]:
    """The name reduced to what stays the same across spellings: no punctuation, title words, house numbers, leading
    'ה', or vowel letters (ו, י); words in alphabetical order (surname first or last)."""
    words = []
    for word in _PUNCT.sub(" ", _QUOTES.sub("", name or "")).split():
        if word.isdigit() or word in _TITLES:
            continue
        if len(word) > 3 and word.startswith("ה"):
            word = word[1:]
        word = word.replace("ו", "").replace("י", "") or word
        if len(word) >= 2 or word in ("א", "ב"):
            words.append(word)
    return tuple(sorted(words))


def _place(group: list[tuple[str, float, float]], near: Optional[tuple[float, float]]) -> tuple[str, float, float]:
    """One position for a street that runs through several ways (or exists in several towns): the way nearest to
    `near` (the town's centre), else the middle of all of them."""
    name = group[0][0]
    ways = [s for s in group if s[0] == name]
    if near:
        lat, lng = min(((w[1], w[2]) for w in ways), key=lambda p: (p[0] - near[0]) ** 2 + ((p[1] - near[1]) * 0.85) ** 2)
        return name, lat, lng
    return name, sum(w[1] for w in ways) / len(ways), sum(w[2] for w in ways) / len(ways)


def best_match(street: str, streets: list[tuple[str, float, float]], near: Optional[tuple[float, float]] = None) -> Optional[tuple[str, float, float]]:
    """(OpenStreetMap's name, lat, lng) of the street that is the same as `street`; for a name that runs through
    several ways, the one nearest `near`. None when nothing is close enough."""
    want = skeleton(street)
    if not want:
        return None
    exact = [s for s in streets if skeleton(s[0]) == want]
    # The chain wrote less than the map does ("זבוטינסקי" for "זאב ז'בוטינסקי"): the map's name has all of the chain's
    # words, and the fewest extra ones wins
    contained = [] if exact or max(len(w) for w in want) < 4 else [
        s for s in streets if skeleton(s[0]) and set(want) < set(skeleton(s[0]))]
    if contained:
        fewest = min(len(skeleton(s[0])) for s in contained)
        names = {s[0] for s in contained if len(skeleton(s[0])) == fewest}
        if len(names) == 1:
            exact = [s for s in contained if s[0] in names]
    if exact:
        group = exact
    else:
        text = " ".join(want)
        scored = [(SequenceMatcher(None, text, " ".join(skeleton(s[0]))).ratio(), s) for s in streets if skeleton(s[0])]
        scored = [x for x in scored if x[0] >= MIN_RATIO]
        if not scored:
            # The chain wrote a longer name than the map does ("הנשיא יצחק בן צבי 75" for "הנשיא"): the map's name, whole,
            # opens the chain's, and it is the longest such name.
            first = skeleton(street.split()[0]) if street.split() else ()
            inside = [s for s in streets if skeleton(s[0]) and set(skeleton(s[0])) <= set(want) and first and first[0] in skeleton(s[0])]
            if not inside:
                return None
            longest = max(len(skeleton(s[0])) for s in inside)
            return _place([s for s in inside if len(skeleton(s[0])) == longest], near)
        top = max(x[0] for x in scored)
        names = {x[1][0] for x in scored if x[0] == top}
        group = [s for s in streets if s[0] in names]
    return _place(group, near)


BOX_LAT, BOX_LNG = 0.075, 0.09          # about 8 km each way around the town's centre


async def town_streets(client: httpx.AsyncClient, city: str, centre: tuple[float, float]) -> Optional[list[tuple[str, float, float]]]:
    """Every named street around the town's centre as (name, lat, lng of the way's middle); None when OpenStreetMap
    does not answer. A box around the centre is asked for, not the town's boundary: the boundary lookup is slow and
    often times out for the big towns. The matching picks the way nearest the centre, so a neighbour's street of
    the same name does not win."""
    city = (city or "").strip()
    if not city or not centre:
        return None
    if city in _streets:
        return _streets[city]
    cache_file = CACHE_DIR / (re.sub(r"[^\w]+", "_", city) + ".json")
    try:
        if cache_file.exists():
            _streets[city] = [tuple(x) for x in json.loads(cache_file.read_text("utf-8"))]
            return _streets[city]
    except Exception:
        pass
    lat, lng = centre
    query = ("[out:json][timeout:90];way(%.4f,%.4f,%.4f,%.4f)[\"highway\"][\"name\"];out tags center;"
             % (lat - BOX_LAT, lng - BOX_LNG, lat + BOX_LAT, lng + BOX_LNG))
    rows: Optional[list[tuple[str, float, float]]] = None
    for _ in range(2):
        try:
            resp = await client.post(OVERPASS, data={"data": query}, headers=HEADERS, timeout=110)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            rows = [(e["tags"]["name"], e["center"]["lat"], e["center"]["lon"]) for e in elements if "center" in e and "name" in e.get("tags", {})]
            break
        except Exception:
            await asyncio.sleep(RETRY_PAUSE)
    await asyncio.sleep(POLITE_PAUSE)
    _streets[city] = rows
    if rows is not None:                               # a failed request is not remembered on disk
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(rows, ensure_ascii=False), "utf-8")
        except Exception:
            pass
    return rows
