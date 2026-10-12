# Product pictures: bulk pre-fill by the worker and the lazy endpoint's memory of misses.

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app.api import routes
from app.images import ImageLookupError
from app.db.models import Product
from app.pipeline import images
from main import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _products(session):
    session.add_all([Product(barcode="1", name="חלב"), Product(barcode="2", name="נדיר")])
    await session.commit()


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(images, "PAUSE_BETWEEN_BATCHES", 0)


async def test_fill_images_saves_hits_and_marks_misses_once(session, monkeypatch):
    await _products(session)
    calls = []

    async def fake(barcode, name):
        calls.append(barcode)
        return "https://cdn.example/1.png" if barcode == "1" else None

    monkeypatch.setattr(images, "lookup_image_url", fake)

    assert await images.fill_images(minutes=1) == (1, 1)
    rows = {p.barcode: p for p in (await session.execute(select(Product))).scalars()}
    await session.refresh(rows["1"]); await session.refresh(rows["2"])
    assert rows["1"].image_url == "https://cdn.example/1.png" and rows["1"].image_checked_at is None
    assert rows["2"].image_url is None and rows["2"].image_checked_at is not None

    calls.clear()
    assert await images.fill_images(minutes=1) == (0, 0)   # nothing left to ask about
    assert calls == []


async def test_image_endpoint_remembers_a_miss(client, session, monkeypatch):
    await _products(session)
    calls = []

    async def fake(barcode, name):
        calls.append(barcode)
        return None

    monkeypatch.setattr(routes, "_lookup_image_url", fake)

    first = await client.get("/api/v1/products/2/image")
    second = await client.get("/api/v1/products/2/image")
    assert first.status_code == second.status_code == 404
    assert calls == ["2"]                                   # the second view did not ask again
    assert first.headers["cache-control"] == "public, max-age=3600"


async def test_image_endpoint_redirects_and_stores_a_hit(client, session, monkeypatch):
    await _products(session)

    async def fake(barcode, name):
        return "https://cdn.example/1.png"

    monkeypatch.setattr(routes, "_lookup_image_url", fake)

    r = await client.get("/api/v1/products/1/image", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://cdn.example/1.png"
    product = (await session.execute(select(Product).where(Product.barcode == "1"))).scalar_one()
    await session.refresh(product)
    assert product.image_url == "https://cdn.example/1.png"


async def test_failed_lookups_are_not_recorded_as_missing_pictures(session, monkeypatch):
    await _products(session)

    async def down(barcode, name):
        raise ImageLookupError("429")

    monkeypatch.setattr(images, "lookup_image_url", down)

    assert await images.fill_images(minutes=1) == (0, 0)     # gives up after repeated failed batches
    rows = (await session.execute(select(Product))).scalars().all()
    for p in rows:
        await session.refresh(p)
    assert all(p.image_url is None and p.image_checked_at is None for p in rows)


async def test_image_endpoint_does_not_remember_a_failed_lookup(client, session, monkeypatch):
    await _products(session)

    async def down(barcode, name):
        raise ImageLookupError("blocked")

    monkeypatch.setattr(routes, "_lookup_image_url", down)

    r = await client.get("/api/v1/products/2/image")
    assert r.status_code == 404 and r.headers["cache-control"] == "no-store"
    product = (await session.execute(select(Product).where(Product.barcode == "2"))).scalar_one()
    await session.refresh(product)
    assert product.image_checked_at is None
