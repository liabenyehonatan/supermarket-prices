# Product pictures: bulk pre-fill by the worker and the lazy endpoint's memory of misses.

from datetime import datetime

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


# ── Second source: Open Food Facts (CC BY-SA pictures, found by barcode) ─────────────────────────

def test_open_food_facts_pictures_are_allowed_but_lookalike_hosts_are_not():
    from app.images import is_allowed_image_url

    assert is_allowed_image_url("https://images.openfoodfacts.org/images/products/729/000/233/1018/front_he.4.400.jpg")
    assert not is_allowed_image_url("https://images.openfoodfacts.org.evil.example/x.jpg")
    assert not is_allowed_image_url("http://images.openfoodfacts.org/x.jpg")


@pytest.mark.parametrize("payload,expected", [
    ({"status": 1, "product": {"image_front_url": "https://images.openfoodfacts.org/a/front.400.jpg"}}, "https://images.openfoodfacts.org/a/front.400.jpg"),
    ({"status": 0}, None),                                                         # unknown barcode
    ({"status": 1, "product": {}}, None),                                          # known, but nobody photographed it
    ({"status": 1, "product": {"image_front_url": "https://tracker.example/a.jpg"}}, None),   # only our allowed hosts
])
def test_open_food_facts_answer_is_read_safely(payload, expected):
    from app.images import off_front_image

    assert off_front_image(payload) == expected


async def test_fill_images_off_asks_about_products_without_a_picture_and_marks_misses_once(session, monkeypatch):
    asked_before = datetime(2026, 10, 1)                                           # Shufersal was asked and had nothing
    session.add_all([Product(barcode="7290000000001", name="חלב", image_checked_at=asked_before),
                     Product(barcode="7290000000002", name="נדיר", image_checked_at=asked_before),
                     Product(barcode="7290000000003", name="יש", image_url="https://cdn.example/3.png"),
                     Product(barcode="7290000000004", name="שופרסל עוד לא נשאל")])
    await session.commit()
    monkeypatch.setattr(images, "OFF_PAUSE", 0)
    asked = []

    async def fake(barcode):
        asked.append(barcode)
        return "https://images.openfoodfacts.org/1.jpg" if barcode == "7290000000001" else None

    monkeypatch.setattr(images, "lookup_off_image_url", fake)
    assert await images.fill_images_off(minutes=1) == (1, 1)
    assert sorted(asked) == ["7290000000001", "7290000000002"]                    # not the one Shufersal has yet to be asked about
    rows = {p.barcode: p for p in (await session.execute(select(Product))).scalars()}
    for p in rows.values():
        await session.refresh(p)
    assert rows["7290000000001"].image_url == "https://images.openfoodfacts.org/1.jpg"
    assert rows["7290000000002"].image_url is None and rows["7290000000002"].off_checked_at is not None
    asked.clear()
    assert await images.fill_images_off(minutes=1) == (0, 0) and asked == []      # a miss is not asked again soon


async def test_fill_images_off_asks_about_products_in_deals_first(session, monkeypatch):
    from datetime import datetime as dt
    from sqlalchemy import update as upd
    from app.db.models import Price, Store
    from app.pipeline import maintenance
    from tests.test_deals import make_world

    product, stores = await make_world(session)                                    # a product in a running deal
    product.image_url = None
    product.image_checked_at = datetime(2026, 10, 1)
    await session.commit()
    plain = Product(barcode="7290000000777", name="בלי מבצע", image_checked_at=datetime(2026, 10, 1))                      # carried by more stores, in no deal
    session.add(plain)
    await session.flush()
    existing = (await session.execute(select(Store))).scalars().all()
    more = Store(chain_id=existing[0].chain_id, store_id="77", name="עוד סניף", city="חיפה")
    session.add(more)
    await session.flush()
    for st in [*existing, more]:                                                     # 4 stores against the deal product's 3
        session.add(Price(product_id=plain.id, store_id=st.id, price="5.00", price_updated_at=dt(2026, 10, 12), is_current=True))
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    monkeypatch.setattr(images, "OFF_PAUSE", 0)
    asked = []

    async def fake(barcode):
        asked.append(barcode)
        return None

    monkeypatch.setattr(images, "lookup_off_image_url", fake)
    monkeypatch.setattr(images, "OFF_BATCH", 1)
    await images.fill_images_off(minutes=1)
    assert asked[0] == product.barcode                                              # the deal's product, not the more widely carried one


async def test_failed_open_food_facts_lookups_are_not_recorded_as_missing_pictures(session, monkeypatch):
    session.add_all([Product(barcode="7290000000001", name="חלב", image_checked_at=datetime(2026, 10, 1)),
                     Product(barcode="7290000000002", name="נדיר", image_checked_at=datetime(2026, 10, 1))])
    await session.commit()
    monkeypatch.setattr(images, "OFF_PAUSE", 0)

    async def down(barcode):
        raise ImageLookupError("429")

    monkeypatch.setattr(images, "lookup_off_image_url", down)
    assert await images.fill_images_off(minutes=1) == (0, 0)
    rows = (await session.execute(select(Product))).scalars().all()
    for p in rows:
        await session.refresh(p)
    assert all(p.image_url is None and p.off_checked_at is None for p in rows)


@pytest.mark.parametrize("barcode,ok", [
    ("7290000000001", False),          # 13 digits but a wrong check digit
    ("7290000000008", True),
    ("96385074", True),                # EAN-8
    ("1234567", False),                # 7 digits: a chain's own code
    ("729000000000X", False),
    ("../../x", False),
    ("", False),
])
def test_only_real_gtins_are_sent_to_open_food_facts(barcode, ok):
    from app.images import is_gtin

    assert is_gtin(barcode) is ok


async def test_a_picture_found_meanwhile_is_not_overwritten(session, monkeypatch):
    from sqlalchemy import update as upd

    session.add(Product(barcode="7290000000008", name="חלב", image_checked_at=datetime(2026, 10, 1)))
    await session.commit()
    monkeypatch.setattr(images, "OFF_PAUSE", 0)

    async def fake(barcode):
        async with images.AsyncSessionLocal() as other:                              # the lazy endpoint stored Shufersal's meanwhile
            await other.execute(upd(Product).where(Product.barcode == barcode).values(image_url="https://res.cloudinary.com/x.png"))
            await other.commit()
        return "https://images.openfoodfacts.org/1.jpg"

    monkeypatch.setattr(images, "lookup_off_image_url", fake)
    await images.fill_images_off(minutes=1)
    p = (await session.execute(select(Product))).scalar_one()
    await session.refresh(p)
    assert p.image_url == "https://res.cloudinary.com/x.png"


async def test_the_answer_must_be_for_the_barcode_asked(session):
    from app.images import off_front_image

    payload = {"status": 1, "code": "7290000000099", "product": {"image_front_url": "https://images.openfoodfacts.org/a.jpg"}}
    assert off_front_image(payload, barcode="7290000000008") is None
    assert off_front_image(payload, barcode="7290000000099") == "https://images.openfoodfacts.org/a.jpg"


# ── A picture must be of THIS product: the barcode decides, a name only counts when it names everything ──────────

@pytest.mark.parametrize("ours,theirs,ok", [
    ("תירס לייט מופחת קלוריות", "ממרח מיונז לייט מופחת קלוריות 424 גרם", False),     # the real mistake: a corn read as a mayonnaise
    ("חלב תנובה 3% 1 ליטר", "חלב תנובה 3% בקבוק 1 ליטר", True),                       # their name only adds words
    ("שמן קוקוס אורגני", "שמן קוקוס אורגני 500 מל", True),                            # sizes are not part of the match
    ("שום", "שום מגורד", False),                                                       # a single generic word proves nothing
    ("קרם פנים", "קרם פנים לחות יומי", False),                                         # two generic words: still any face cream
    ("גבינה לבנה 5% 250 גרם", "גבינה לבנה תנובה 5% 250 גרם", True),
    ("תה שחור רויאל ציילון", "תה ירוק רויאל ציילון", False),
])
def test_a_name_matches_only_when_all_its_meaningful_words_are_theirs(ours, theirs, ok):
    from app.images import names_match

    assert names_match(ours, theirs) is ok


def _shufersal(results_by_query):
    """A fake Shufersal search endpoint: {query: [results]}."""
    def handler(request):
        return httpx.Response(200, json={"results": results_by_query.get(request.url.params["q"], [])})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _hit(code, name, tag="a"):
    return {"code": f"P_{code}", "name": name,
            "baseProductImageMedium": f"https://res.cloudinary.com/shufersal/image/upload/v1/prod/product_images/products_medium/{tag}_M_P_{code}_1.png"}


async def test_the_barcode_picks_the_picture_even_when_it_is_not_the_first_result():
    from app.images import lookup_image_url

    client = _shufersal({"7290000000008": [_hit("1111111", "משהו אחר", "x"), _hit("7290000000008", "חלב", "y")]})
    assert (await lookup_image_url("7290000000008", "חלב", client=client)).endswith("y_M_P_7290000000008_1.png")


async def test_a_barcode_search_that_finds_only_other_products_is_not_a_match():
    from app.images import lookup_image_url

    client = _shufersal({"7290020431097": [_hit("120874", "ממרח מיונז לייט מופחת קלוריות 424 גרם")],
                         "תירס לייט מופחת קלוריות": [_hit("120874", "ממרח מיונז לייט מופחת קלוריות 424 גרם")]})
    assert await lookup_image_url("7290020431097", "תירס לייט מופחת קלוריות", client=client) is None


async def test_a_private_label_short_code_matches_its_barcode():
    from app.images import lookup_image_url

    client = _shufersal({"7290000120874": [], "ממרח מיונז לייט": [_hit("120874", "ממרח מיונז לייט 424 גרם")]})
    # Shufersal's own code is the tail of the barcode: 7290000 + 120874 (the name here also names everything)
    assert await lookup_image_url("7290000120874", "ממרח מיונז לייט", client=client) is not None


async def test_the_name_fallback_still_works_when_the_name_names_everything():
    from app.images import lookup_image_url

    client = _shufersal({"7290000000999": [], "חלב תנובה 3% 1 ליטר": [_hit("5555555", "חלב תנובה 3% בקבוק 1 ליטר")]})
    assert await lookup_image_url("7290000000999", "חלב תנובה 3% 1 ליטר", client=client) is not None


# ── Checking the pictures we already hold ────────────────────────────────────────────────────────────────────────

async def test_audit_keeps_replaces_and_clears_pictures_and_leaves_failures_alone(session, monkeypatch):
    base = "https://res.cloudinary.com/shufersal/image/upload/v1/prod/product_images/products_medium/"
    session.add_all([
        Product(barcode="7290000000008", name="נכון", image_url=base + "a_M_P_7290000000008_1.png"),      # code = barcode: not even asked
        Product(barcode="7290000000015", name="תמונה של אחר", image_url=base + "a_M_P_9999999_1.png"),    # wrong; the right one exists
        Product(barcode="7290000000022", name="תירס", image_url=base + "a_M_P_120874_1.png"),              # wrong; nothing right exists
        Product(barcode="7290000000039", name="לא נבדק", image_url=base + "a_M_P_8888888_1.png"),          # the lookup fails
    ])
    await session.commit()
    right = base + "b_M_P_7290000000015_1.png"
    asked = []

    async def fake(barcode, name):
        asked.append(barcode)
        if barcode == "7290000000015":
            return right
        if barcode == "7290000000039":
            raise ImageLookupError("429")
        return None

    monkeypatch.setattr(images, "lookup_image_url", fake)
    monkeypatch.setattr(images, "PAUSE_BETWEEN_BATCHES", 0)
    kept, replaced, cleared, failed = await images.audit_images()
    assert (replaced, cleared, failed) == (1, 1, 1) and "7290000000008" not in asked
    rows = {p.barcode: p for p in (await session.execute(select(Product))).scalars()}
    for p in rows.values():
        await session.refresh(p)
    assert rows["7290000000008"].image_url.endswith("P_7290000000008_1.png")
    assert rows["7290000000015"].image_url == right
    assert rows["7290000000022"].image_url is None and rows["7290000000022"].image_checked_at is not None
    assert rows["7290000000039"].image_url.endswith("P_8888888_1.png")
