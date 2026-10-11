# Chains publish a store's city in three ways: a name ("אילת"), the CBS locality
# code ("2600"), or junk ("0", "unknown", blank). resolve_city() returns a real
# name or None, so the stored city is always something a person (and the city
# filter) can use.
#
# app/data/city_codes.json: CBS locality code -> name, from data.gov.il
# (resource 5c78e9fa-c2e2-4771-93ff-7f400a12f7ba, "יישובים בישראל").

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_CODES_FILE = Path(__file__).resolve().parent.parent / "data" / "city_codes.json"


@lru_cache(maxsize=1)
def city_codes() -> dict[str, str]:
    return json.loads(_CODES_FILE.read_text(encoding="utf-8"))


def resolve_city(raw: Optional[str]) -> Optional[str]:
    value = " ".join((raw or "").split())
    if not value or value.lower() == "unknown":
        return None
    if value.isdigit():
        return city_codes().get(str(int(value)))  # unknown code or "0" -> None
    return value
