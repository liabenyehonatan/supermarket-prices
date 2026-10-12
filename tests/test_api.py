# Wiring of the API process: CORS, removed admin routes, health endpoints.

import httpx
import pytest
from httpx import ASGITransport

from main import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health_checks_the_database(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "db": True}


async def test_health_reports_503_when_database_is_down(client, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def boom(self, *a, **k):
        raise ConnectionError("db down")

    monkeypatch.setattr(AsyncSession, "execute", boom)
    r = await client.get("/health")
    assert r.status_code == 503 and r.json()["db"] is False


async def test_data_health_is_503_until_an_ingest_succeeded(client, session):
    from app.db.models import IngestRun
    from sqlalchemy import func

    assert (await client.get("/health/data")).status_code == 503
    session.add(IngestRun(phase="cycle", status="ok", finished_at=func.now()))
    await session.commit()
    r = await client.get("/health/data")
    assert r.status_code == 200 and r.json()["status"] == "ok"


async def test_task_endpoints_are_gone(client):
    for method, path in [("POST", "/api/v1/tasks/scrape"), ("POST", "/api/v1/tasks/parse"),
                         ("POST", "/api/v1/tasks/scrape-and-parse"), ("GET", "/api/v1/tasks/abc")]:
        assert (await client.request(method, path)).status_code == 404


async def test_cors_is_not_wide_open(client):
    allowed = await client.options("/api/v1/stats", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = await client.options("/api/v1/stats", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in denied.headers


async def test_read_endpoints_work_on_an_empty_database(client):
    assert (await client.get("/api/v1/stats")).status_code == 200
    assert (await client.get("/api/v1/products/search", params={"q": "חלב"})).status_code == 200


async def test_search_ranks_by_store_count_from_the_refreshed_view(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store
    from app.pipeline import maintenance

    chain = Chain(chain_id="123", name="רשת")
    session.add(chain)
    await session.flush()
    stores = [Store(chain_id=chain.id, store_id=str(i), name=f"s{i}") for i in range(2)]
    rare, common = Product(barcode="1", name="חלב נדיר"), Product(barcode="2", name="חלב נפוץ")
    session.add_all(stores + [rare, common])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=rare.id, store_id=stores[0].id, price=5, price_updated_at=now, is_current=True),
        Price(product_id=common.id, store_id=stores[0].id, price=5, price_updated_at=now, is_current=True),
        Price(product_id=common.id, store_id=stores[1].id, price=6, price_updated_at=now, is_current=True),
    ])
    await session.commit()

    await maintenance.refresh_popularity()

    r = await client.get("/api/v1/products/search", params={"q": "חלב"})
    assert [p["barcode"] for p in r.json()] == ["2", "1"]


async def test_bitan_and_carrefour_are_told_apart_by_store_name(client, session):
    from datetime import datetime
    from app.chains import MIXED_CHAIN, display_chain_name
    from app.db.models import Chain, Price, Product, Store

    assert display_chain_name(MIXED_CHAIN, "יינות ביתן טבעון") == "יינות ביתן"
    assert display_chain_name(MIXED_CHAIN, "קרפור מרקט אילת") == "קרפור"
    assert display_chain_name(MIXED_CHAIN, "היפר עפולה") == "קרפור"
    assert display_chain_name("שופרסל", "יינות ביתן") == "שופרסל"

    chain = Chain(chain_id="7290055700007", name=MIXED_CHAIN)
    session.add(chain)
    await session.flush()
    bitan = Store(chain_id=chain.id, store_id="1", name="יינות ביתן טבעון")
    carrefour = Store(chain_id=chain.id, store_id="2", name="קרפור מרקט אילת")
    product = Product(barcode="9", name="מוצר")
    session.add_all([bitan, carrefour, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=product.id, store_id=bitan.id, price=5, price_updated_at=now, is_current=True),
        Price(product_id=product.id, store_id=carrefour.id, price=6, price_updated_at=now, is_current=True),
    ])
    await session.commit()

    r = await client.get("/api/v1/products/9/compare")
    assert [p["chain_name"] for p in r.json()["prices"]] == ["יינות ביתן", "קרפור"]

    r = await client.post("/api/v1/basket/compare", params={"chain": "קרפור"}, json=[{"barcode": "9", "quantity": 1}])
    assert [s["store"]["chain"]["name"] for s in r.json()["stores"]] == ["קרפור"]
