"""City and chain names, checked against what the API actually holds: a name that matches nothing is an error that
lists valid values, never an empty result that would read as "no data"."""

import difflib
import time

from mcp_service.errors import ToolUserError

CITIES_TTL_SECONDS = 600
_cities: tuple[float, list[str]] | None = None


def _reset_cache() -> None:
    global _cities
    _cities = None


async def get_cities(api) -> list[str]:
    """Every city with a store, minus the numeric city codes some chains publish. Cached for 10 minutes."""
    global _cities
    now = time.monotonic()
    if _cities is None or now - _cities[0] > CITIES_TTL_SECONDS:
        raw = await api.get("/api/v1/stores/cities")
        _cities = (now, [c for c in raw if c and not c.strip().isdigit()])
    return _cities[1]


async def validate_city(api, city: str) -> str:
    """The API matches a city by substring, so any text contained in a real city name is fine."""
    wanted = city.strip()
    cities = await get_cities(api)
    if any(wanted.lower() in c.lower() for c in cities):
        return wanted
    close = difflib.get_close_matches(wanted, cities, n=5, cutoff=0.5)
    hint = f"האם התכוונת ל: {', '.join(close)}?" if close else "חפש עיר עם find_cities."
    raise ToolUserError(f"לא נמצאה עיר בשם \"{wanted}\". {hint}")


async def validate_chain(api, chain: str) -> str:
    """The API wants a chain's exact name; returns the canonical spelling."""
    wanted = chain.strip()
    names = [c["name"] for c in await api.get("/api/v1/chains")]
    for name in names:
        if name.lower() == wanted.lower():
            return name
    raise ToolUserError(f"לא נמצאה רשת בשם \"{wanted}\". הרשתות: {', '.join(names)}")

