# Store positions: the Nominatim client and the background job.

import httpx
import pytest
from sqlalchemy import select

from app import geocode as geo
from app.db.models import Chain, Store
from app.pipeline import geocode as job


async def _no_sleep():
    return None


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_address_hit_then_city_fallback_and_israel_bounds():
    geo._city_centres.clear()
    seen = []

    def handler(request):
        params = dict(request.url.params)
        seen.append(params)
        if params.get("street") == "הרצל 1":
            return httpx.Response(200, json=[{"lat": "32.08", "lon": "34.78"}])
        if params.get("city") == "תל אביב" and "street" not in params:
            return httpx.Response(200, json=[{"lat": "32.07", "lon": "34.79"}])
        if params.get("city") and "street" not in params:
            return httpx.Response(200, json=[{"lat": "31.77", "lon": "35.21"}])
        if params.get("q") == "Paris":
            return httpx.Response(200, json=[{"lat": "48.85", "lon": "2.35"}])   # outside Israel
        return httpx.Response(200, json=[])

    async with _client(handler) as c:
        assert await geo.geocode(c, "הרצל 1", "תל אביב", _no_sleep) == (32.08, 34.78, "address")
        assert await geo.geocode(c, "רחוב לא קיים 99", "ירושלים", _no_sleep) == (31.77, 35.21, "city")
        assert await geo.geocode(c, "unknown", "ירושלים", _no_sleep) == (31.77, 35.21, "city")   # junk address skipped
        assert await geo.geocode(c, "Paris", None, _no_sleep) is None                            # wrong country rejected
    assert not any(p.get("street") == "unknown" for p in seen)


async def test_service_failure_raises_instead_of_looking_like_a_miss():
    async with _client(lambda r: httpx.Response(429)) as c:
        with pytest.raises(geo.GeocodeError):
            await geo.geocode(c, "הרצל 1", "תל אביב", _no_sleep)


async def _stores(session):
    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    session.add_all([
        Store(chain_id=chain.id, store_id="a", name="סניף א", address="הרצל 1", city="תל אביב"),
        Store(chain_id=chain.id, store_id="b", name="סניף ב", address="לא ידוע", city="חיפה"),
        Store(chain_id=chain.id, store_id="c", name="רשת אונליין", address="https://shop.example", city=None),
    ])
    await session.commit()


async def test_job_locates_marks_misses_and_skips_web_shops(session, monkeypatch):
    await _stores(session)
    monkeypatch.setattr(job, "PAUSE", 0)

    async def fake(client, address, city, sleep, name=None):
        return (32.08, 34.78, "address") if address == "הרצל 1" else None

    monkeypatch.setattr(job, "geocode", fake)

    assert await job.fill_geocodes(minutes=1) == (1, 2)    # the web shop counts as 'none'
    stores = {s.store_id: s for s in (await session.execute(select(Store))).scalars()}
    for s in stores.values():
        await session.refresh(s)
    assert (stores["a"].latitude, stores["a"].geo_precision) == (32.08, "address")
    assert stores["b"].latitude is None and stores["b"].geo_precision == "none" and stores["b"].geocoded_at
    assert stores["c"].geo_precision == "none"

    assert await job.fill_geocodes(minutes=1) == (0, 0)    # nothing is asked twice


async def test_job_does_not_record_failures_and_gives_up(session, monkeypatch):
    await _stores(session)
    monkeypatch.setattr(job, "PAUSE", 0)
    monkeypatch.setattr(job, "MAX_CONSECUTIVE_ERRORS", 2)

    async def down(client, address, city, sleep, name=None):
        raise geo.GeocodeError("429")

    monkeypatch.setattr(job, "geocode", down)

    await job.fill_geocodes(minutes=1)
    stores = (await session.execute(select(Store).where(Store.store_id.in_(["a", "b"])))).scalars().all()
    for s in stores:
        await session.refresh(s)
    assert all(s.geocoded_at is None for s in stores)


async def test_a_poison_address_is_marked_not_found_and_does_not_block_the_rest(session, monkeypatch):
    await _stores(session)
    monkeypatch.setattr(job, "PAUSE", 0)
    monkeypatch.setattr(job, "MAX_CONSECUTIVE_ERRORS", 1)

    async def fake(client, address, city, sleep, name=None):
        if address == "לא ידוע":
            raise geo.GeocodeError("400 for this address", retryable=False)
        return (32.08, 34.78, "address")

    monkeypatch.setattr(job, "geocode", fake)

    found, missed = await job.fill_geocodes(minutes=1)
    stores = {s.store_id: s for s in (await session.execute(select(Store))).scalars()}
    for s in stores.values():
        await session.refresh(s)
    assert stores["a"].latitude == 32.08            # the store after the poison one was still located
    assert stores["b"].geo_precision == "none" and stores["b"].geocoded_at is not None


async def test_address_is_read_from_the_name_when_the_chain_publishes_none():
    assert geo.address_in_name("סיטי מרקט הרצוג גבעתיים, הרצוג 23 גבעתיים") == "הרצוג 23 גבעתיים"
    assert geo.address_in_name("סיטי מרקט כרמי גת, שד' לכיש 181 ק.גת") == "שד' לכיש 181 קרית גת"
    assert geo.address_in_name('מתוק שוק, הרצל 70 ראשל"צ') == "הרצל 70 ראשון לציון"
    assert geo.address_in_name("שופרסל דיל אילת") == ""
    assert geo.address_in_name("סניף, בלי מספר") == ""

    queries = []

    def handler(request):
        queries.append(dict(request.url.params))
        return httpx.Response(200, json=[{"lat": "32.07", "lon": "34.81"}])

    async with _client(handler) as c:
        got = await geo.geocode(c, "unknown", None, _no_sleep, name="סיטי מרקט, הרצוג 23 גבעתיים")
    assert got == (32.07, 34.81, "address") and queries[0]["q"] == "הרצוג 23 גבעתיים"


async def test_without_a_city_the_store_name_is_used_never_the_bare_street():
    queries = []

    def handler(request):
        queries.append(dict(request.url.params))
        return httpx.Response(200, json=[{"lat": "32.43", "lon": "34.92"}])

    async with _client(handler) as c:
        got = await geo.geocode(c, 'צה"ל 34', None, _no_sleep, name="חדרה חדש")
        assert got == (32.43, 34.92, "address")
        assert queries[0]["q"] == 'צה"ל 34, חדרה חדש'
        queries.clear()
        assert await geo.geocode(c, 'צה"ל 34', None, _no_sleep) is None      # no city, no name: do not guess
        assert queries == []


async def test_a_street_match_in_another_town_is_rejected_for_the_city_centre():
    geo._city_centres.clear()

    def handler(request):
        params = dict(request.url.params)
        if "street" in params or "q" in params:
            return httpx.Response(200, json=[{"lat": "31.80", "lon": "34.64"}])   # same street name, 55 km away
        return httpx.Response(200, json=[{"lat": "31.77", "lon": "35.21"}])       # the city itself

    async with _client(handler) as c:
        got = await geo.geocode(c, "שד' משה דיין 160", "ירושלים", _no_sleep)
    assert got == (31.77, 35.21, "city")


def test_address_cleaning_and_spelling_variants():
    assert geo.clean_address("רח' דרויאנוב 5") == "דרויאנוב 5"
    assert geo.clean_address("שד' בן גוריון 3 (קומה 2)") == "שדרות בן גוריון 3"
    assert geo.clean_address("רח.משה שפירא 28") == "משה שפירא 28"
    assert geo.clean_address("14 רחוב הבנים") == "14 הבנים"
    assert geo.clean_address("רח' שחר 79, ירושלים.") == "שחר 79"
    assert geo.street_only("הזית פינת גלבוע") == "הזית"
    assert geo.street_only("הרצל 12 א") == "הרצל"
    assert geo.street_only("2 עמק האלה") == "עמק האלה"
    assert "קרית אונו" in geo.city_variants("קריית-אונו") and "באר שבע" in geo.city_variants("באר-שבע")


async def test_an_address_with_a_street_word_or_another_spelling_of_the_town_is_still_found():
    geo._city_centres.clear()

    def handler(request):
        p = dict(request.url.params)
        if p.get("city") == "קרית אונו" and "street" not in p:
            return httpx.Response(200, json=[{"lat": "32.05", "lon": "34.86"}])
        if p.get("street") == "שלמה המלך 2" and p.get("city") == "קרית אונו":
            return httpx.Response(200, json=[{"lat": "32.0545", "lon": "34.8603"}])
        return httpx.Response(200, json=[])

    async with _client(handler) as c:
        # the chain writes "רח'" and "קריית"; the search only knows the clean form
        assert await geo.geocode(c, "רח' שלמה המלך 2", "קריית אונו", _no_sleep) == (32.0545, 34.8603, "address")


async def test_the_street_alone_is_enough_when_the_house_number_is_not_found():
    geo._city_centres.clear()

    def handler(request):
        p = dict(request.url.params)
        if p.get("city") == "גדרה" and "street" not in p:
            return httpx.Response(200, json=[{"lat": "31.81", "lon": "34.77"}])
        if p.get("street") == "הזית" and p.get("city") == "גדרה":
            return httpx.Response(200, json=[{"lat": "31.812", "lon": "34.771"}])
        return httpx.Response(200, json=[])

    async with _client(handler) as c:
        assert await geo.geocode(c, "הזית פינת גלבוע", "גדרה", _no_sleep) == (31.812, 34.771, "street")


async def test_a_store_at_its_town_centre_is_looked_up_again_and_keeps_that_position_when_nothing_better_comes(session, monkeypatch):
    geo._city_centres.clear()
    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    session.add(Store(chain_id=chain.id, store_id="1", name="סניף", address="רחוב שלא קיים 9", city="גדרה",
                      latitude=31.81, longitude=34.77, geo_precision="city"))
    await session.commit()

    async def no_hit(client, address, city, sleep, name=None):
        return None
    monkeypatch.setattr(job, "geocode", no_hit)
    monkeypatch.setattr(job, "PAUSE", 0)
    await job.fill_geocodes(0.05)
    store = (await session.execute(select(Store))).scalar_one()
    await session.refresh(store)
    assert (store.latitude, store.geo_precision) == (31.81, "city") and store.geocoded_at is not None
