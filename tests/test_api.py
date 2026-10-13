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
    rare, common = Product(barcode="7290000000101", name="חלב נדיר"), Product(barcode="7290000000102", name="חלב נפוץ")
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
    assert [p["barcode"] for p in r.json()] == ["7290000000102", "7290000000101"]


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
    product = Product(barcode="7290000000109", name="מוצר")
    session.add_all([bitan, carrefour, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=product.id, store_id=bitan.id, price=5, price_updated_at=now, is_current=True),
        Price(product_id=product.id, store_id=carrefour.id, price=6, price_updated_at=now, is_current=True),
    ])
    await session.commit()

    r = await client.get("/api/v1/products/7290000000109/compare")
    assert [p["chain_name"] for p in r.json()["prices"]] == ["יינות ביתן", "קרפור"]

    r = await client.post("/api/v1/basket/compare", params={"chain": "קרפור"}, json=[{"barcode": "7290000000109", "quantity": 1}])
    assert [s["store"]["chain"]["name"] for s in r.json()["stores"]] == ["קרפור"]


async def test_chains_endpoint_lists_brands_biggest_first(client, session):
    from app.chains import MIXED_CHAIN
    from app.db.models import Chain, Store

    big = Chain(chain_id="1", name="גדולה")
    mixed = Chain(chain_id="2", name=MIXED_CHAIN)
    session.add_all([big, mixed])
    await session.flush()
    session.add_all([
        Store(chain_id=big.id, store_id=str(i), name=f"s{i}") for i in range(3)
    ] + [
        Store(chain_id=mixed.id, store_id="a", name="יינות ביתן טבעון"),
        Store(chain_id=mixed.id, store_id="b", name="קרפור אילת"),
        Store(chain_id=mixed.id, store_id="c", name="היפר עפולה"),
    ])
    await session.commit()

    r = await client.get("/api/v1/chains")
    assert r.json() == [{"name": "גדולה", "stores": 3}, {"name": "קרפור", "stores": 2}, {"name": "יינות ביתן", "stores": 1}]


async def test_zero_prices_are_never_served_or_loaded(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store
    from app.parser.price_loader import normalize_row

    assert normalize_row({"ItemCode": "1", "ItemName": "x", "ItemPrice": "0.00"}, None) is None
    assert normalize_row({"ItemCode": "1", "ItemName": "x", "ItemPrice": "-3"}, None) is None
    assert normalize_row({"ItemCode": "1", "ItemName": "x", "ItemPrice": "2.5"}, None) is not None

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    stores = [Store(chain_id=chain.id, store_id=str(i), name=f"s{i}") for i in range(2)]
    product = Product(barcode="7290000000105", name="מוצר")
    session.add_all(stores + [product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=product.id, store_id=stores[0].id, price=0, price_updated_at=now, is_current=True),
        Price(product_id=product.id, store_id=stores[1].id, price=4, price_updated_at=now, is_current=True),
    ])
    await session.commit()

    r = await client.get("/api/v1/products/7290000000105/compare")
    assert [p["price"] for p in r.json()["prices"]] == ["4.00"]


async def test_price_freshness_comes_from_the_stores_last_full_file(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף", last_full_at=datetime(2026, 10, 13, 6, 0))
    product = Product(barcode="7290000000107", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    session.add(Price(product_id=product.id, store_id=store.id, price=5, price_updated_at=datetime(2026, 1, 1),
                      scraped_at=datetime(2026, 10, 1), is_current=True))
    await session.commit()

    r = await client.get("/api/v1/products/7290000000107/compare")
    assert r.json()["prices"][0]["scraped_at"].startswith("2026-10-13T06:00")   # not the row's own old stamp


async def test_robots_and_sitemap_use_the_address_they_are_asked_on(client):
    robots = await client.get("/robots.txt", headers={"host": "sali.example"})
    assert robots.status_code == 200 and robots.headers["content-type"].startswith("text/plain")
    assert "Disallow: /api/" in robots.text and "Sitemap: http://sali.example/sitemap.xml" in robots.text

    sitemap = await client.get("/sitemap.xml", headers={"host": "sali.example"})
    assert sitemap.status_code == 200 and "xml" in sitemap.headers["content-type"]
    assert "<loc>http://sali.example/</loc>" in sitemap.text


async def test_timestamps_carry_a_timezone_so_browsers_do_not_misread_them(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף", last_full_at=datetime(2026, 10, 13, 6, 0))
    product = Product(barcode="7290000000108", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    session.add(Price(product_id=product.id, store_id=store.id, price=5, scraped_at=datetime(2026, 10, 1),
                      price_updated_at=datetime(2026, 1, 1, 0, 0), is_current=True))   # Israel local midnight
    await session.commit()

    row = (await client.get("/api/v1/products/7290000000108/compare")).json()["prices"][0]
    assert row["scraped_at"] == "2026-10-13T06:00:00Z"                 # UTC, stated as such
    assert row["price_updated_at"] == "2025-12-31T22:00:00Z"          # 00:00 in Israel (UTC+2 in January)
    from app.api import routes
    routes._stats_cache = None                                      # the stats answer is cached across tests
    stats = (await client.get("/api/v1/stats")).json()
    assert stats["last_updated"].endswith("Z")
    routes._stats_cache = None


async def test_examples_come_from_the_view_and_skip_placeholder_prices(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store
    from app.pipeline import maintenance

    chain = Chain(chain_id="1", name="רשת")
    other = Chain(chain_id="2", name="אחרת")
    session.add_all([chain, other])
    await session.flush()
    stores = [Store(chain_id=(chain if i % 2 else other).id, store_id=str(i), name=f"s{i}") for i in range(24)]
    good = Product(barcode="7290000000011", name="גבינה לבנה", image_url="https://res.cloudinary.com/x.png")
    coupon = Product(barcode="7290000000022", name="קופון", image_url="https://res.cloudinary.com/y.png")
    internal = Product(barcode="12345", name="קוד פנימי", image_url="https://res.cloudinary.com/z.png")
    session.add_all(stores + [good, coupon, internal])
    await session.flush()
    now = datetime(2026, 10, 12)
    for i, st in enumerate(stores):
        session.add(Price(product_id=good.id, store_id=st.id, price=5 + (i % 4), price_updated_at=now, is_current=True))
        session.add(Price(product_id=coupon.id, store_id=st.id, price=0.01 if i == 0 else 90, price_updated_at=now, is_current=True))
        session.add(Price(product_id=internal.id, store_id=st.id, price=5 + (i % 4), price_updated_at=now, is_current=True))
    await session.commit()
    await maintenance.refresh_popularity()

    from app.api import routes
    routes._examples_cache = None
    r = await client.get("/api/v1/products/examples?limit=6")
    assert [e["barcode"] for e in r.json()] == ["7290000000011"]       # not the 0.01-vs-90 coupon, not the short code
    routes._examples_cache = None


async def test_nearest_city_comes_from_our_own_stores(client, session):
    from app.db.models import Chain, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    session.add_all([
        Store(chain_id=chain.id, store_id="1", name="a", city="חיפה", latitude=32.80, longitude=34.99),
        Store(chain_id=chain.id, store_id="2", name="b", city="אילת", latitude=29.55, longitude=34.95),
    ])
    await session.commit()
    near = await client.get("/api/v1/location/city", params={"lat": 32.79, "lng": 35.0})
    assert near.json()["city"] == "חיפה"
    far = await client.get("/api/v1/location/city", params={"lat": 31.0, "lng": 35.0})   # nothing within 25 km
    assert far.json() == {"city": None}
    assert (await client.get("/api/v1/location/city", params={"lat": 48.0, "lng": 2.0})).status_code == 422


async def test_images_only_for_known_products_and_only_from_allowed_hosts(client, session, monkeypatch):
    from app.api import routes
    from app.db.models import Product
    from app.images import is_allowed_image_url

    assert is_allowed_image_url("https://res.cloudinary.com/shufersal/a.png")
    assert not is_allowed_image_url("http://res.cloudinary.com/a.png")            # not https
    assert not is_allowed_image_url("https://evil.example/a.png")
    assert not is_allowed_image_url("https://cloudinary.com.evil.example/a.png")
    assert not is_allowed_image_url("javascript:alert(1)")

    called = []

    async def fake(barcode, name):
        called.append(barcode)
        return "https://res.cloudinary.com/a.png"

    monkeypatch.setattr(routes, "_lookup_image_url", fake)
    assert (await client.get("/api/v1/products/999999999/image")).status_code == 404
    assert called == []                                                           # unknown barcode: no lookup

    session.add(Product(barcode="5", name="x", image_url="https://evil.example/p.png"))
    await session.commit()
    r = await client.get("/api/v1/products/5/image", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://res.cloudinary.com/a.png"   # bad stored URL replaced



async def test_short_item_codes_and_tiny_prices_are_not_compared(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store
    from app.parser.price_loader import normalize_row

    assert normalize_row({"ItemCode": "7290000000111", "ItemName": "x", "ItemPrice": "0.01"}, None) is None
    assert normalize_row({"ItemCode": "7290000000111", "ItemName": "x", "ItemPrice": "0.09"}, None) is None
    assert normalize_row({"ItemCode": "7290000000111", "ItemName": "x", "ItemPrice": "0.10"}, None) is not None   # a bag

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    real, internal = Product(barcode="7290000000111", name="חלב אמיתי"), Product(barcode="12345", name="חלב קוד פנימי")
    session.add_all([store, real, internal])
    await session.flush()
    now = datetime(2026, 10, 12)
    for prod in (real, internal):
        session.add(Price(product_id=prod.id, store_id=store.id, price=5, price_updated_at=now, is_current=True))
    await session.commit()

    found = await client.get("/api/v1/products/search", params={"q": "חלב"})
    assert [p["barcode"] for p in found.json()] == ["7290000000111"]               # the internal code is hidden
    assert (await client.get("/api/v1/products/12345/compare")).status_code == 404
    assert (await client.get("/api/v1/products/7290000000111/compare")).status_code == 200
    assert (await client.get("/api/v1/products/search", params={"q": "12345"})).json() == []


async def test_basket_limits_and_duplicates(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    product = Product(barcode="7290000000112", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    session.add(Price(product_id=product.id, store_id=store.id, price=5, price_updated_at=datetime(2026, 10, 12), is_current=True))
    await session.commit()

    post = lambda body: client.post("/api/v1/basket/compare", json=body)
    assert (await post([{"barcode": "7290000000112", "quantity": -5}])).status_code == 422       # negative total would rank first
    assert (await post([{"barcode": "7290000000112", "quantity": 100}])).status_code == 422
    assert (await post([{"barcode": "7290000000112" * 3, "quantity": 1}])).status_code == 422     # barcode too long
    too_many = [{"barcode": f"72900000{i:05d}", "quantity": 1} for i in range(101)]
    assert (await post(too_many)).status_code == 422

    r = await post([{"barcode": "7290000000112", "quantity": 2}, {"barcode": "7290000000112", "quantity": 3}])
    body = r.json()
    assert r.status_code == 200 and body["total_items_requested"] == 1                            # duplicates merged
    assert body["stores"][0]["items_missing"] == 0 and float(body["stores"][0]["total_price"]) == 25.0   # 5 x (2+3)

    batch = await client.post("/api/v1/products/cheapest-batch", json={"barcodes": ["1"] * 101})
    assert batch.status_code == 422


async def test_search_input_limits(client):
    assert (await client.get("/api/v1/products/search", params={"q": "ח" * 101})).status_code == 422
    assert (await client.get("/api/v1/products/search", params={"q": "חלב", "offset": 10001})).status_code == 422
    assert (await client.get("/api/v1/products/search", params={"q": "a b c d e f g h i j k l"})).status_code == 200   # extra words ignored
    assert (await client.get("/api/v1/products/search", params={"q": "ח ב"})).json() == []         # only one-letter words


async def test_fuzzy_search_still_forgives_a_typo(client, session):
    from app.db.models import Product

    session.add(Product(barcode="7290000000113", name="גבינה לבנה 5%"))
    await session.commit()
    r = await client.get("/api/v1/products/search", params={"q": "גבימה"})
    assert [p["barcode"] for p in r.json()] == ["7290000000113"]
