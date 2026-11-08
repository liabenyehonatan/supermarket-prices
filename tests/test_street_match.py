# Finding a street written another way than OpenStreetMap writes it.

import httpx

from app import geocode as geo
from app import street_match as sm

STREETS = [
    ("זוהר טל", 32.1724, 34.8027), ("הנשיא", 32.1729, 34.8078), ("יצחק גרינבאום", 32.3, 34.8), ('האצ"ל', 32.1, 34.7),
    ('צה"ל', 31.6, 34.5), ("ג'ורג' קינג", 31.7, 35.2), ("אורוגוואי", 31.7, 35.2), ("שדרות רוטשילד", 32.06, 34.77),
    ("רועי ברש", 31.8, 35.2), ("זאב ז'בוטינסקי", 31.9, 34.8), ("הרצל", 32.0, 34.8), ("בנימין הרצל", 32.5, 34.9),
]


def test_the_same_street_is_found_across_spellings():
    found = lambda q: (sm.best_match(q, STREETS) or (None,))[0]
    assert found("זהר טל") == "זוהר טל"                    # no vowel letter
    assert found("גרינבאום יצחק") == "יצחק גרינבאום"        # surname first
    assert found("אצל") == 'האצ"ל' and found("צהל") == 'צה"ל'   # abbreviation marks dropped
    assert found("קינג גורג") == "ג'ורג' קינג"
    assert found("אורוגאי") == "אורוגוואי"
    assert found("שד` רוטשילד") == "שדרות רוטשילד"           # title and a stray backtick
    assert found("זבוטינסקי") == "זאב ז'בוטינסקי"           # the chain wrote less
    assert found("הנשיא יצחק בן צבי") == "הנשיא"            # the chain wrote more


def test_a_different_street_is_not_taken_for_it():
    assert sm.best_match("הרצל", STREETS)[0] == "הרצל"      # the exact one, not "בנימין הרצל"
    assert sm.best_match("דרך שלא קיימת", STREETS) is None
    assert sm.best_match("", STREETS) is None


def test_of_two_streets_with_one_name_the_one_nearest_the_town_centre_wins():
    streets = [("הרצל", 32.00, 34.80), ("הרצל", 32.30, 34.85)]
    assert sm.best_match("הרצל", streets, near=(32.29, 34.85))[1:] == (32.30, 34.85)
    assert sm.best_match("הרצל", streets, near=(32.01, 34.80))[1:] == (32.00, 34.80)


async def test_a_street_missing_in_the_search_is_found_in_the_towns_own_street_list(monkeypatch):
    geo._city_centres.clear()

    def handler(request):
        if request.url.host == "overpass-api.de":
            assert b"way%28" in request.content or b"way(" in request.content            # a box around the centre, not the boundary lookup
            elements = [{"tags": {"name": name}, "center": {"lat": lat, "lon": lng}} for name, lat, lng in STREETS]
            return httpx.Response(200, json={"elements": elements})
        p = dict(request.url.params)
        if p.get("city") == "הרצליה" and "street" not in p:
            return httpx.Response(200, json=[{"lat": "32.17", "lon": "34.80"}])
        if p.get("street") == "34 זוהר טל":
            return httpx.Response(200, json=[{"lat": "32.17242", "lon": "34.80271"}])     # the house itself
        return httpx.Response(200, json=[])

    async def no_sleep():
        return None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        assert await geo.geocode(c, "34 זהר טל", "הרצליה", no_sleep) == (32.17242, 34.80271, "address")
        # the house is not on the map: the street's own position is still much better than the town's centre
        assert await geo.geocode(c, "99 הנשיא יצחק בן צבי", "הרצליה", no_sleep) == (32.1729, 34.8078, "street")
