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
