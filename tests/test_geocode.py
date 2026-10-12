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
    seen = []

    def handler(request):
        params = dict(request.url.params)
        seen.append(params)
        if params.get("street") == "הרצל 1":
            return httpx.Response(200, json=[{"lat": "32.08", "lon": "34.78"}])
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

    async def fake(client, address, city, sleep):
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

    async def down(client, address, city, sleep):
        raise geo.GeocodeError("429")

    monkeypatch.setattr(job, "geocode", down)

    await job.fill_geocodes(minutes=1)
    stores = (await session.execute(select(Store).where(Store.store_id.in_(["a", "b"])))).scalars().all()
    for s in stores:
        await session.refresh(s)
    assert all(s.geocoded_at is None for s in stores)
