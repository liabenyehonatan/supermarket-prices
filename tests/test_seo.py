# Search-engine support: page heads, structured data, 404s, robots.txt and the sitemaps.

import json
import re
from datetime import datetime

import httpx
import pytest
from httpx import ASGITransport

from main import app

SHELL = (
    '<!doctype html><html lang="he"><head><meta charset="UTF-8" /><title>old</title>'
    '<meta name="description" content="old" /><meta property="og:title" content="old" /></head>'
    '<body><div id="root"></div></body></html>'
)


@pytest.fixture
async def client(monkeypatch):
    from app import seo

    async def shell():
        return SHELL

    monkeypatch.setattr(seo, "_fetch_shell", shell)
    monkeypatch.setattr(seo, "_shell_cache", None)
    monkeypatch.setattr(seo, "_sitemap_cache", {})
    monkeypatch.setattr(seo.settings, "SITE_URL", "")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://sali.example") as c:
        yield c


async def _product(session, barcode="7290000000105", stores=2, brand="תנובה"):
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    product = Product(barcode=barcode, name='חלב 3% "טרי" 1 ליטר', brand=brand)
    session.add(product)
    now = datetime(2026, 10, 1)
    for i in range(stores):
        st = Store(chain_id=chain.id, store_id=str(i), name=f"סניף {i}", city="חיפה")
        session.add(st)
        await session.flush()
        session.add(Price(product_id=product.id, store_id=st.id, price=5 + i, price_updated_at=now, is_current=True))
    await session.commit()
    return product


def _ld(page: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)]


async def test_product_page_carries_its_own_head_and_structured_data(client, session):
    await _product(session)
    r = await client.get("/_seo/product/7290000000105")
    assert r.status_code == 200
    page = r.text
    assert "<title>old</title>" not in page and page.count("<title>") == 1
    assert "חלב 3% &quot;טרי&quot; 1 ליטר — השוואת מחירים | סלי" in page
    assert '<link rel="canonical" href="http://sali.example/product/7290000000105" />' in page
    assert 'content="index,follow' in page
    assert "<h1>" in page and "5.00 ₪" in page            # summary for crawlers that do not run scripts
    product = next(b for b in _ld(page) if b["@type"] == "Product")
    assert product["gtin13"] == "7290000000105" and product["brand"]["name"] == "תנובה"
    offer = product["offers"]
    assert (offer["lowPrice"], offer["highPrice"], offer["offerCount"], offer["priceCurrency"]) == ("5.00", "6.00", 2, "ILS")
    assert any(b["@type"] == "BreadcrumbList" for b in _ld(page))


async def test_site_url_setting_fixes_the_canonical_address(client, session, monkeypatch):
    from app import seo

    monkeypatch.setattr(seo.settings, "SITE_URL", "https://sali.co.il")
    await _product(session)
    page = (await client.get("/_seo/product/7290000000105")).text
    assert 'href="https://sali.co.il/product/7290000000105"' in page


async def test_unknown_product_and_unknown_page_are_404_and_not_indexed(client, session):
    for path in ("/_seo/product/7290000000999", "/_seo/product/12", "/_seo/nothing-here"):
        r = await client.get(path)
        assert r.status_code == 404 and r.headers["x-robots-tag"] == "noindex"
        assert "noindex" in r.text and "canonical" not in r.text


async def test_product_without_a_real_price_is_404(client, session):
    from app.db.models import Price

    await _product(session, stores=1)
    from sqlalchemy import update
    await session.execute(update(Price).values(price=0))
    await session.commit()
    assert (await client.get("/_seo/product/7290000000105")).status_code == 404


async def test_pages_have_distinct_titles_and_the_home_page_is_a_website(client):
    home = (await client.get("/_seo/")).text
    promos = (await client.get("/_seo/promotions")).text
    assert re.search(r"<title>(.*?)</title>", home).group(1) != re.search(r"<title>(.*?)</title>", promos).group(1)
    assert any(b["@type"] == "WebSite" and "SearchAction" in json.dumps(b) for b in _ld(home))
    assert '<link rel="canonical" href="http://sali.example/" />' in home
    assert '<link rel="canonical" href="http://sali.example/promotions" />' in promos


async def test_tool_pages_are_noindex_and_have_no_canonical(client):
    for path in ("/_seo/basket", "/_seo/scan"):
        r = await client.get(path)
        assert r.status_code == 200 and "noindex,follow" in r.text and "canonical" not in r.text
        assert r.headers["x-robots-tag"] == "noindex"


async def test_trailing_slash_and_old_search_address_redirect(client):
    r = await client.get("/_seo/promotions/?chain=x")
    assert r.status_code == 301 and r.headers["location"] == "/promotions?chain=x"
    r = await client.get("/_seo/search")
    assert r.status_code == 301 and r.headers["location"] == "/"


async def test_page_is_unavailable_when_the_shell_cannot_be_fetched(client, monkeypatch):
    from app import seo

    async def boom():
        raise OSError("frontend down")

    monkeypatch.setattr(seo, "_fetch_shell", boom)
    assert (await client.get("/_seo/promotions")).status_code == 503     # nginx then serves the plain app


async def test_robots_points_at_the_sitemap_index(client):
    robots = await client.get("/robots.txt")
    assert robots.headers["content-type"].startswith("text/plain")
    assert "Disallow: /api/" in robots.text and "Sitemap: http://sali.example/sitemap.xml" in robots.text


async def test_sitemaps_list_pages_and_comparable_products_only(client, session):
    from sqlalchemy import text

    await _product(session, "7290000000105", stores=2)
    await _product_single(session)
    async with session.bind.begin() as conn:
        await conn.execute(text("REFRESH MATERIALIZED VIEW product_store_counts"))

    index = (await client.get("/sitemap.xml")).text
    assert "<sitemapindex" in index
    assert "http://sali.example/sitemap-pages.xml" in index and "http://sali.example/sitemap-products-1.xml" in index

    pages = (await client.get("/sitemap-pages.xml")).text
    assert "<loc>http://sali.example/</loc>" in pages and "/promotions</loc>" in pages and "/about</loc>" in pages
    assert "/basket" not in pages and "/scan" not in pages and "#" not in pages

    products = (await client.get("/sitemap-products-1.xml")).text
    assert "/product/7290000000105</loc>" in products and "7290000000222" not in products   # one store: nothing to compare
    assert (await client.get("/sitemap-products-2.xml")).status_code == 404


async def _product_single(session):
    from app.db.models import Chain, Price, Product, Store

    chain = (await session.execute(__import__("sqlalchemy").select(Chain))).scalars().first()
    st = Store(chain_id=chain.id, store_id="solo", name="יחיד")
    p = Product(barcode="7290000000222", name="מוצר יחיד")
    session.add_all([st, p])
    await session.flush()
    session.add(Price(product_id=p.id, store_id=st.id, price=3, price_updated_at=datetime(2026, 10, 1), is_current=True))
    await session.commit()
