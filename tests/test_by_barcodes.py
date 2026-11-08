# POST /api/v1/products/by-barcodes: names for a list of barcodes (the basket link import and the MCP use it).

import httpx
import pytest
from httpx import ASGITransport

from app.db.models import Product
from main import app

URL = "/api/v1/products/by-barcodes"
B1, B2 = "7290000000011", "7290000000028"


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _two_products(session):
    session.add_all([
        Product(barcode=B1, name="חלב 3%", brand="תנובה", unit_of_measure="ליטר"),
        Product(barcode=B2, name="ביצים L", brand=None),
    ])
    await session.commit()


async def test_returns_known_products_in_request_order(client, session):
    await _two_products(session)
    r = await client.post(URL, json={"barcodes": [B2, B1]})
    assert r.status_code == 200
    assert [p["barcode"] for p in r.json()] == [B2, B1]
    assert r.json()[1]["name"] == "חלב 3%"
    assert r.json()[1]["unit_of_measure"] == "ליטר"


async def test_unknown_barcode_is_omitted(client, session):
    await _two_products(session)
    r = await client.post(URL, json={"barcodes": ["0000000000000"]})
    assert r.status_code == 200 and r.json() == []


async def test_duplicate_barcode_answered_once(client, session):
    await _two_products(session)
    r = await client.post(URL, json={"barcodes": [B1, B1, B1]})
    assert [p["barcode"] for p in r.json()] == [B1]


async def test_over_100_barcodes_is_422(client):
    r = await client.post(URL, json={"barcodes": [str(i) for i in range(101)]})
    assert r.status_code == 422


async def test_empty_list_returns_empty_list(client):
    r = await client.post(URL, json={"barcodes": []})
    assert r.status_code == 200 and r.json() == []


async def test_chain_item_numbers_are_not_matched(client, session):
    session.add(Product(barcode="12345", name="פריט פנימי של רשת"))   # shorter than MIN_BARCODE_LEN
    await session.commit()
    r = await client.post(URL, json={"barcodes": ["12345"]})
    assert r.json() == []
