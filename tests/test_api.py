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


async def test_a_database_timeout_is_a_busy_503_not_a_500(client, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.api import routes

    async def too_slow(self, *a, **k):
        raise DBAPIError("SELECT 1", {}, Exception("canceling statement due to statement timeout"))

    routes._stats_cache = None
    monkeypatch.setattr(AsyncSession, "execute", too_slow)
    r = await client.get("/api/v1/stats")
    assert r.status_code == 503 and r.headers["retry-after"] == "5"
    assert "busy" in r.json()["detail"]
    routes._stats_cache = None


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
    assert "<loc>http://sali.example/promotions</loc>" in sitemap.text and "#" not in sitemap.text


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


async def test_examples_rotate_daily_and_always_have_a_picture(client, session, monkeypatch):
    from datetime import datetime
    from app.api import routes
    from app.db.models import Chain, Price, Product, Store
    from app.pipeline import maintenance

    chain = Chain(chain_id="1", name="רשת")
    other = Chain(chain_id="2", name="אחרת")
    session.add_all([chain, other])
    await session.flush()
    stores = [Store(chain_id=(chain if i % 2 else other).id, store_id=str(i), name=f"s{i}") for i in range(24)]
    session.add_all(stores)
    names = ["גבינה", "חלב", "לחם", "אורז", "שמן", "קפה", "תה", "סוכר", "קמח", "פסטה", "טחינה", "חומוס"]
    products = [Product(barcode=f"72900000001{i:02d}", name=f"{n} משפחתי", image_url=f"https://res.cloudinary.com/{i}.png")
                for i, n in enumerate(names)]
    no_picture = Product(barcode="7290000000999", name="ללא תמונה")
    wrong_host = Product(barcode="7290000000998", name="תמונה ממקור לא מאושר", image_url="https://evil.example/x.png")
    session.add_all(products + [no_picture, wrong_host])
    await session.flush()
    now = datetime(2026, 10, 12)
    for prod in products + [no_picture, wrong_host]:
        for i, st in enumerate(stores):
            session.add(Price(product_id=prod.id, store_id=st.id, price=5 + (i % 4), price_updated_at=now, is_current=True))
    await session.commit()
    await maintenance.refresh_popularity()

    async def on_day(seed):
        monkeypatch.setattr(routes, "_rotation_seed", lambda: seed)
        r = await client.get("/api/v1/products/examples?limit=4")
        return [e["barcode"] for e in r.json()], r.json()

    seen = set()
    day1, body = await on_day(1)
    routes._examples_cache = None                  # another worker, or a later hour: the answer is computed afresh
    again, _ = await on_day(1)
    day2, more = await on_day(2)
    assert day1 == again and len(day1) == 4        # the same all day, whoever computes it
    assert day1 != day2                            # a different selection the next day
    for _ in range(10):                            # whatever the day, never a product without a usable picture
        routes._examples_cache = None
        seen.update((await on_day(_ + 3))[0])
    assert not seen & {"7290000000999", "7290000000998"} and len(seen) > 4
    assert all(e["image_url"].startswith("https://res.cloudinary.com/") for e in body)
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


async def test_keyboard_smash_gets_no_fuzzy_matches(client, session):
    from app.db.models import Product

    session.add(Product(barcode="7290000000124", name="ממרח קקאו אגוזי לוז 350 גרם"))
    await session.commit()
    # one letter repeated is not a typo of anything: loosely matching it only returned "cacao" products
    smash = await client.get("/api/v1/products/search", params={"q": "קקקקקקקק"})
    assert smash.status_code == 200 and smash.json() == []
    # a real typo of the same word still finds it
    typo = await client.get("/api/v1/products/search", params={"q": "קקאוו"})
    assert [p["barcode"] for p in typo.json()] == ["7290000000124"]


async def test_basket_limit_keeps_the_best_stores_and_reports_the_totals(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    stores = [Store(chain_id=chain.id, store_id=str(i), name=f"s{i}") for i in range(5)]
    a, b = Product(barcode="7290000000201", name="א"), Product(barcode="7290000000202", name="ב")
    session.add_all(stores + [a, b])
    await session.flush()
    now = datetime(2026, 10, 12)
    for i, st in enumerate(stores):
        session.add(Price(product_id=a.id, store_id=st.id, price=10 + i, price_updated_at=now, is_current=True))
        if i < 4:                                                       # store 4 lacks product b: incomplete
            session.add(Price(product_id=b.id, store_id=st.id, price=1 + i, price_updated_at=now, is_current=True))
    await session.commit()

    body = [{"barcode": "7290000000201", "quantity": 2}, {"barcode": "7290000000202", "quantity": 1}]
    full = (await client.post("/api/v1/basket/compare", json=body)).json()
    cut = (await client.post("/api/v1/basket/compare", params={"limit": 2}, json=body)).json()

    assert full["total_stores"] == cut["total_stores"] == 5 and len(full["stores"]) == 5 and len(cut["stores"]) == 2
    assert [s["store"]["name"] for s in cut["stores"]] == [s["store"]["name"] for s in full["stores"][:2]] == ["s0", "s1"]
    assert full["stores"][-1]["items_missing"] == 1                      # the incomplete store comes last
    assert float(full["stores"][0]["total_price"]) == 21.0               # 10*2 + 1
    assert float(full["max_total"]) == 30.0 == float(cut["max_total"])   # most expensive COMPLETE basket: s3 = 13*2 + 4
    assert [i["barcode"] for i in full["stores"][0]["item_prices"]] == ["7290000000201", "7290000000202"]   # basket order


async def _promo_fixture(session):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    product = Product(barcode="7290000000111", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add(Price(product_id=product.id, store_id=store.id, price=5, price_updated_at=now, is_current=True))
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)

    def promo(pid, desc, start, end):
        return Promotion(product_id=product.id, store_id=store.id, promotion_id=pid, description=desc,
                         min_qty=2, start_date=start, end_date=end, is_active=True)

    session.add_all([
        promo("run", "2 ב-18", local_now - timedelta(days=1), local_now + timedelta(days=3)),
        promo("open", "מבצע פתוח", None, None),
        promo("over", "נגמר", local_now - timedelta(days=9), local_now - timedelta(days=1)),
        promo("later", "עוד לא התחיל", local_now + timedelta(days=1), local_now + timedelta(days=5)),
    ])
    await session.commit()
    return product, store


async def test_compare_lists_only_running_promotions_soonest_end_first(client, session):
    product, _ = await _promo_fixture(session)
    r = await client.get(f"/api/v1/products/{product.barcode}/compare")
    promos = r.json()["prices"][0]["promotions"]
    assert [p["description"] for p in promos] == ["2 ב-18", "מבצע פתוח"]
    assert promos[0]["min_qty"] == 2 and promos[0]["ends_at"] is not None
    assert promos[1]["ends_at"] is None


async def test_compare_returns_an_empty_promotion_list_when_there_are_none(client, session):
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

    r = await client.get("/api/v1/products/7290000000112/compare")
    assert r.json()["prices"][0]["promotions"] == []


async def test_compare_shows_at_most_three_promotions_per_store(client, session):
    from app.db.models import Promotion
    product, store = await _promo_fixture(session)
    session.add_all([
        Promotion(product_id=product.id, store_id=store.id, promotion_id=f"x{i}", description=f"x{i}",
                  start_date=None, end_date=None, is_active=True)
        for i in range(5)
    ])
    await session.commit()
    r = await client.get(f"/api/v1/products/{product.barcode}/compare")
    assert len(r.json()["prices"][0]["promotions"]) == 3


async def _basket_world(session, *, promo_age_days=0, eligible=True, max_qty=None, ends_yesterday=False,
                        min_qty=3, promo_price="10.00", shelf_a="4.00", shelf_b="5.00", price_is_total=False):
    """Two stores sell one product. A is cheaper on the shelf. B runs '3 for 10' (when eligible)."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, update
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain_a, chain_b = Chain(chain_id="1", name="רשת א"), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    store_a = Store(chain_id=chain_a.id, store_id="1", name="סניף א")
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב")
    product = Product(barcode="7290000000201", name="חלב")
    session.add_all([store_a, store_b, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=product.id, store_id=store_a.id, price=shelf_a, price_updated_at=now, is_current=True),
        Price(product_id=product.id, store_id=store_b.id, price=shelf_b, price_updated_at=now, is_current=True),
    ])
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)
    session.add(Promotion(
        product_id=product.id, store_id=store_b.id, promotion_id="p1", description="3 ב-10",
        min_qty=min_qty, discounted_price=promo_price, max_qty=max_qty, basket_eligible=eligible, is_active=True, price_is_total=price_is_total,
        start_date=local_now - timedelta(days=5),
        end_date=local_now - timedelta(days=1) if ends_yesterday else local_now + timedelta(days=5),
    ))
    await session.commit()
    await session.execute(update(Store).where(Store.id == store_b.id).values(
        last_promo_at=func.now() - timedelta(days=promo_age_days)))
    await session.commit()
    return product


async def _basket(client, qty):
    r = await client.post("/api/v1/basket/compare", json=[{"barcode": "7290000000201", "quantity": qty}])
    assert r.status_code == 200
    return r.json()


def _by_chain(body):
    return {s["store"]["chain"]["name"]: s for s in body["stores"]}


async def test_a_promotion_can_make_the_dearer_shelf_store_win(client, session):
    await _basket_world(session)
    body = await _basket(client, 3)
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת ב", "רשת א"]       # B: 10.00 < A: 12.00
    b = _by_chain(body)["רשת ב"]
    assert (float(b["total_price"]), float(b["savings"]), b["promotions_known"]) == (10.0, 5.0, True)
    line = b["item_prices"][0]
    assert float(line["unit_price"]) == 5.0 and float(line["regular_line_total"]) == 15.0
    assert float(line["line_total"]) == 10.0
    assert {k: v for k, v in line["promo"].items() if k != "ends_at"} == {"description": "3 ב-10", "min_qty": 3, "price": "10.00", "sets": 1}
    a = _by_chain(body)["רשת א"]
    assert (float(a["savings"]), a["promotions_known"], a["item_prices"][0]["promo"]) == (0.0, False, None)


async def test_below_the_set_size_the_shelf_price_decides(client, session):
    await _basket_world(session)
    body = await _basket(client, 2)
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת א", "רשת ב"]       # 8.00 < 10.00
    assert float(_by_chain(body)["רשת ב"]["savings"]) == 0.0


async def test_the_remainder_and_the_purchase_limit_are_priced_at_shelf(client, session):
    await _basket_world(session, min_qty=1, promo_price="3.00", max_qty=3)
    body = await _basket(client, 5)
    b = _by_chain(body)["רשת ב"]
    assert float(b["total_price"]) == 19.0                  # 3 x 3.00 + 2 x 5.00
    assert b["item_prices"][0]["promo"]["sets"] == 3


async def test_a_store_without_fresh_promotion_data_gets_no_promotion(client, session):
    await _basket_world(session, promo_age_days=8)
    b = _by_chain(await _basket(client, 3))["רשת ב"]
    assert (float(b["total_price"]), b["promotions_known"], b["item_prices"][0]["promo"]) == (15.0, False, None)


async def test_an_ineligible_promotion_never_changes_a_total(client, session):
    await _basket_world(session, eligible=False)
    assert float(_by_chain(await _basket(client, 3))["רשת ב"]["total_price"]) == 15.0


async def test_an_ended_promotion_is_not_applied(client, session):
    await _basket_world(session, ends_yesterday=True)
    assert float(_by_chain(await _basket(client, 3))["רשת ב"]["total_price"]) == 15.0


async def test_a_promotion_that_is_not_cheaper_is_ignored(client, session):
    await _basket_world(session, promo_price="15.00")        # 3 for 15.00 = the shelf price
    b = _by_chain(await _basket(client, 3))["רשת ב"]
    assert float(b["total_price"]) == 15.0 and b["item_prices"][0]["promo"] is None


async def test_complete_baskets_still_rank_before_incomplete_ones_with_promotions(client, session):
    from datetime import datetime
    from sqlalchemy import select
    from app.db.models import Chain, Price, Product, Store

    await _basket_world(session)                              # A: 4.00, B: 5.00 with "3 for 10"
    milk = (await session.execute(select(Product).where(Product.barcode == "7290000000201"))).scalar_one()
    bread = Product(barcode="7290000000202", name="לחם")
    chain_c = Chain(chain_id="3", name="רשת ג")
    session.add_all([bread, chain_c])
    await session.flush()
    store_c = Store(chain_id=chain_c.id, store_id="1", name="סניף ג")
    session.add(store_c)
    await session.flush()
    stores = {s.name: s for s in (await session.execute(select(Store))).scalars().all()}
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=bread.id, store_id=stores["סניף א"].id, price="1.00", price_updated_at=now, is_current=True),
        Price(product_id=bread.id, store_id=stores["סניף ב"].id, price="1.00", price_updated_at=now, is_current=True),
        Price(product_id=milk.id, store_id=store_c.id, price="1.00", price_updated_at=now, is_current=True),   # C has no bread
    ])
    await session.commit()

    r = await client.post("/api/v1/basket/compare", json=[
        {"barcode": "7290000000201", "quantity": 3}, {"barcode": "7290000000202", "quantity": 1}])
    stores_out = r.json()["stores"]
    assert [(s["store"]["chain"]["name"], s["items_missing"]) for s in stores_out] == [
        ("רשת ב", 0), ("רשת א", 0), ("רשת ג", 1)]               # B 11.00 (promotion), A 13.00, then the cheap incomplete C
    assert [float(s["total_price"]) for s in stores_out] == [11.0, 13.0, 3.0]


async def test_a_total_the_description_confirms_is_applied_even_below_one_unit_price(client, session):
    # "2 for 8.00" on a 10.00 shelf price: the description confirmed it is the total for 2.
    await _basket_world(session, min_qty=2, promo_price="8.00", shelf_b="10.00", shelf_a="12.00", price_is_total=True)
    b = _by_chain(await _basket(client, 2))["רשת ב"]
    assert float(b["total_price"]) == 8.0 and b["item_prices"][0]["promo"]["sets"] == 1


async def test_the_same_promotion_without_confirmation_is_not_applied(client, session):
    await _basket_world(session, min_qty=2, promo_price="8.00", shelf_b="10.00", shelf_a="12.00", price_is_total=False)
    b = _by_chain(await _basket(client, 2))["רשת ב"]
    assert float(b["total_price"]) == 20.0 and b["item_prices"][0]["promo"] is None


async def _group_world(session, *, with_group=True, group_age_days=0):
    """Store A is cheaper on the shelf; store B runs '3 for 10' on any of milk, yogurt and cheese."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, update
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain_a, chain_b = Chain(chain_id="1", name="רשת א"), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    store_a = Store(chain_id=chain_a.id, store_id="1", name="סניף א")
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב")
    products = [Product(barcode=f"729000000030{i}", name=name) for i, name in enumerate(("חלב", "יוגורט", "גבינה"), 1)]
    session.add_all([store_a, store_b, *products])
    await session.flush()
    now = datetime(2026, 10, 12)
    shelf_a, shelf_b = ("4.00", "5.00", "6.00"), ("5.00", "6.00", "7.00")
    for product, a, b in zip(products, shelf_a, shelf_b):
        session.add_all([
            Price(product_id=product.id, store_id=store_a.id, price=a, price_updated_at=now, is_current=True),
            Price(product_id=product.id, store_id=store_b.id, price=b, price_updated_at=now, is_current=True),
        ])
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)
    if with_group:
        for product in products:
            session.add(Promotion(
                product_id=product.id, store_id=store_b.id, promotion_id="g1", description="3 מוצרי חלב ב-10",
                min_qty=3, discounted_price="10.00", basket_eligible=True, price_is_total=True, is_active=True,
                start_date=local_now - timedelta(days=5), end_date=local_now + timedelta(days=5)))
    await session.commit()
    await session.execute(update(Store).where(Store.id == store_b.id).values(
        last_promo_at=func.now() - timedelta(days=group_age_days)))
    await session.commit()
    return products


async def _group_basket(client, quantities):
    body = [{"barcode": f"729000000030{i}", "quantity": q} for i, q in enumerate(quantities, 1) if q]
    r = await client.post("/api/v1/basket/compare", json=body)
    assert r.status_code == 200
    return r.json()


async def test_a_group_promotion_pools_different_products_and_can_flip_the_ranking(client, session):
    await _group_world(session)
    body = await _group_basket(client, (1, 1, 1))           # A: 4+5+6 = 15.00, B: shelf 18.00, promotion 10.00
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת ב", "רשת א"]
    b = _by_chain(body)["רשת ב"]
    assert (float(b["total_price"]), float(b["savings"]), b["promotions_known"]) == (10.0, 8.0, True)
    [adjustment] = b["promo_adjustments"]
    assert adjustment["description"] == "3 מוצרי חלב ב-10" and adjustment["sets"] == 1
    assert float(adjustment["saving"]) == 8.0 and sorted(adjustment["barcodes"]) == ["7290000000301", "7290000000302", "7290000000303"]
    assert all(line["promo"] is None for line in b["item_prices"])         # group savings are not spread over lines
    assert sum(float(line["line_total"]) for line in b["item_prices"]) == 18.0


async def test_the_basket_below_the_set_size_gets_no_group_promotion(client, session):
    await _group_world(session)
    body = await _group_basket(client, (1, 1, 0))
    b = _by_chain(body)["רשת ב"]
    assert float(b["total_price"]) == 11.0 and b["promo_adjustments"] == []


async def test_a_store_without_fresh_promotion_data_gets_no_group_promotion(client, session):
    await _group_world(session, group_age_days=8)
    b = _by_chain(await _group_basket(client, (1, 1, 1)))["רשת ב"]
    assert (float(b["total_price"]), b["promo_adjustments"], b["promotions_known"]) == (18.0, [], False)


async def test_stores_without_any_promotion_report_an_empty_adjustment_list(client, session):
    await _group_world(session, with_group=False)
    for store in (await _group_basket(client, (1, 1, 1)))["stores"]:
        assert store["promo_adjustments"] == []


async def _split_world(session, rows):
    """One store, two products at 6.00. `rows`: per-product promotion rows with the SAME promotion_id,
    as chains that write one record per product do. Each row: dict(min_qty, price, price_is_total)."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, update
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    products = [Product(barcode=f"729000000040{i}", name=f"מוצר {i}") for i in (1, 2)]
    session.add_all([store, *products])
    await session.flush()
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)
    for product, spec in zip(products, rows):
        session.add(Price(product_id=product.id, store_id=store.id, price="6.00",
                          price_updated_at=datetime(2026, 10, 12), is_current=True))
        session.add(Promotion(
            product_id=product.id, store_id=store.id, promotion_id="s1", description="2 ב-10 מוצרים",
            min_qty=spec["min_qty"], discounted_price=spec["price"], basket_eligible=True,
            price_is_total=spec["price_is_total"], is_active=True,
            start_date=local_now - timedelta(days=5), end_date=local_now + timedelta(days=5)))
    await session.commit()
    await session.execute(update(Store).where(Store.id == store.id).values(last_promo_at=func.now()))
    await session.commit()


async def _split_basket(client):
    r = await client.post("/api/v1/basket/compare", json=[
        {"barcode": "7290000000401", "quantity": 1}, {"barcode": "7290000000402", "quantity": 1}])
    assert r.status_code == 200
    return r.json()["stores"][0]


async def test_records_split_per_product_are_not_pooled_unless_the_price_is_confirmed(client, session):
    # Each record alone was judged as a single product (no text check). Pooled they would be a group
    # promotion that skipped the group rules, so the pooled promotion is ignored.
    await _split_world(session, [dict(min_qty=2, price="10.00", price_is_total=False)] * 2)
    store = await _split_basket(client)
    assert float(store["total_price"]) == 12.0 and store["promo_adjustments"] == []


async def test_records_split_per_product_that_disagree_are_ignored(client, session):
    await _split_world(session, [
        dict(min_qty=2, price="10.00", price_is_total=True), dict(min_qty=2, price="11.00", price_is_total=True)])
    store = await _split_basket(client)
    assert float(store["total_price"]) == 12.0 and store["promo_adjustments"] == []


async def test_records_split_per_product_that_agree_and_are_confirmed_are_pooled(client, session):
    await _split_world(session, [dict(min_qty=2, price="10.00", price_is_total=True)] * 2)
    store = await _split_basket(client)
    assert float(store["total_price"]) == 10.0 and len(store["promo_adjustments"]) == 1



def _days_from_now(iso):
    from datetime import datetime, timezone
    return (datetime.fromisoformat(iso) - datetime.now(timezone.utc)).total_seconds() / 86400


async def test_a_basket_line_promotion_says_when_it_ends(client, session):
    await _basket_world(session)                                    # B's promotion runs for 5 more days (Israel time)
    line = _by_chain(await _basket(client, 3))["רשת ב"]["item_prices"][0]
    assert 4.0 < _days_from_now(line["promo"]["ends_at"]) < 5.2


async def test_a_group_promotion_adjustment_says_when_it_ends(client, session):
    await _group_world(session)
    b = _by_chain(await _group_basket(client, (1, 1, 1)))["רשת ב"]
    [adjustment] = b["promo_adjustments"]
    assert 4.0 < _days_from_now(adjustment["ends_at"]) < 5.2


async def test_a_promotion_without_an_end_date_has_no_end_in_the_basket(client, session):
    from sqlalchemy import update
    from app.db.models import Promotion

    await _basket_world(session)
    await session.execute(update(Promotion).values(end_date=None))
    await session.commit()
    assert _by_chain(await _basket(client, 3))["רשת ב"]["item_prices"][0]["promo"]["ends_at"] is None


async def test_price_summary_names_every_chain_at_the_cheapest_price_with_its_unit_price(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    shufersal = Chain(chain_id="7290027600007", name="שופרסל")
    victory = Chain(chain_id="7290696200003", name="ויקטורי")
    yohananof = Chain(chain_id="7290803800003", name="יוחננוף")
    session.add_all([shufersal, victory, yohananof])
    await session.flush()
    s1 = Store(chain_id=shufersal.id, store_id="1", name="שופרסל דיל")
    s2 = Store(chain_id=shufersal.id, store_id="2", name="שופרסל שלי")
    v1 = Store(chain_id=victory.id, store_id="1", name="ויקטורי")
    y1 = Store(chain_id=yohananof.id, store_id="1", name="יוחננוף")
    wholesale = Store(chain_id=yohananof.id, store_id="2", name="יוחננוף סיטונאות")
    bread = Product(barcode="7290000000201", name="לחם 750 גרם", unit_of_measure="100 גרם")
    eggs = Product(barcode="7290000000202", name="ביצים 12", unit_of_measure="יחידות")
    session.add_all([s1, s2, v1, y1, wholesale, bread, eggs])
    await session.flush()
    now = datetime(2026, 10, 17)
    p = lambda prod, store, price, unit=None, current=True: Price(
        product_id=prod.id, store_id=store.id, price=price, unit_price=unit, price_updated_at=now, is_current=current)
    session.add_all([
        p(bread, s1, "15.30", "2.04"), p(bread, s2, "15.30", "2.04"),   # two stores, one chain, at the cheapest
        p(bread, v1, "15.30", "2.04"), p(bread, y1, "17.90", "2.39"),
        p(bread, wholesale, "9.00", "1.20"),                           # wholesale is never the cheapest
        p(bread, y1, "1.00", "0.13", current=False),                   # nor an old price
        p(eggs, y1, "20.20", "20.20"),
    ])
    await session.commit()

    r = await client.post("/api/v1/products/price-summary-batch",
                          json={"barcodes": ["7290000000201", "7290000000202", "7290000000999"]})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"7290000000201", "7290000000202"}             # unknown barcodes are left out
    assert float(body["7290000000201"]["price"]) == 15.30
    assert body["7290000000201"]["chains"] == ["ויקטורי", "שופרסל"]     # each chain once
    assert float(body["7290000000201"]["unit_price"]) == 2.04 and body["7290000000201"]["unit"] == "100 גרם"
    assert body["7290000000202"]["chains"] == ["יוחננוף"]

    too_many = await client.post("/api/v1/products/price-summary-batch", json={"barcodes": ["1"] * 101})
    assert too_many.status_code == 422
