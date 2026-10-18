# The deals view and endpoint: one row per (brand, promotion), measured against the cheapest shelf price.

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, text, update

from app.db.models import Chain, Price, Product, Promotion, Store
from app.pipeline import maintenance

NOW_IL = lambda: datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)


async def make_world(session, *, ends=None, starts=None, eligible=True, promo_age_days=0, price="9.00", min_qty=3,
                     market_min="4.00", chain_name="רשת א", store_names=("סניף א1", "סניף א2"), cities=("חיפה", "עכו"),
                     wholesale=False, price_is_total=True, other_sells=True, barcode="7290000000501"):
    """Chain A (two stores) runs `min_qty for price` on one product. Chain B sells the same product at `market_min`."""
    chain_a, chain_b = Chain(chain_id="1", name=chain_name), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    stores = [Store(chain_id=chain_a.id, store_id=str(i), name=("סיטונאי " + n) if wholesale else n, city=city)
              for i, (n, city) in enumerate(zip(store_names, cities), 1)]
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב", city="חיפה")
    product = Product(barcode=barcode, name="מוצר", image_url="https://img.example/x.png")
    session.add_all([*stores, store_b, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    for st in stores:
        session.add(Price(product_id=product.id, store_id=st.id, price="5.00", price_updated_at=now, is_current=True))
    if other_sells:
        session.add(Price(product_id=product.id, store_id=store_b.id, price=market_min, price_updated_at=now, is_current=True))
    local = NOW_IL()
    for st in stores:
        session.add(Promotion(
            product_id=product.id, store_id=st.id, promotion_id="p1", description=f"{min_qty} ב-{price}",
            min_qty=min_qty, discounted_price=price, basket_eligible=eligible, price_is_total=price_is_total, is_active=True,
            start_date=starts or local - timedelta(days=3), end_date=ends or local + timedelta(days=5)))
    await session.commit()
    await session.execute(update(Store).where(Store.id.in_([s.id for s in stores])).values(
        last_promo_at=func.now() - timedelta(days=promo_age_days)))
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    return product, stores


async def deals(session):
    rows = await session.execute(text(
        "select brand, stores, products, min_qty, price, unit_price, ref_price, saving_pct, vs_market from promo_deals"))
    return rows.all()


async def test_one_row_per_brand_and_promotion_however_many_stores_run_it(session):
    await make_world(session)
    [row] = await deals(session)
    assert (row.brand, row.stores, row.products, row.min_qty) == ("רשת א", 2, 1, 3)
    assert float(row.unit_price) == 3.0 and float(row.ref_price) == 4.0 and round(float(row.saving_pct), 4) == 0.25


async def test_the_saving_is_measured_against_the_cheapest_shelf_price_anywhere(session):
    await make_world(session, market_min="6.00")                 # nobody sells it below 5.00 (chain A's own shelf) or 6.00
    [row] = await deals(session)
    assert float(row.ref_price) == 5.0                            # the cheapest of all current prices, chain A's own 5.00


async def add_copy(session, product, stores, *, promotion_id, description, price="9.00", min_qty=3, extra_product=None):
    """The same promotion filed again under another promotion_id (chains do this)."""
    local = NOW_IL()
    for st in stores:
        for prod in [product] + ([extra_product] if extra_product else []):
            session.add(Promotion(
                product_id=prod.id, store_id=st.id, promotion_id=promotion_id, description=description, min_qty=min_qty,
                discounted_price=price, basket_eligible=True, price_is_total=True, is_active=True,
                start_date=local - timedelta(days=3), end_date=local + timedelta(days=5)))
    await session.commit()
    await maintenance.refresh_deals()


async def test_the_same_promotion_under_two_promotion_ids_is_one_deal(session):
    product, stores = await make_world(session)
    await add_copy(session, product, stores[:1], promotion_id="p2", description="3 במחיר 9")
    [row] = await deals(session)
    assert (row.stores, row.products) == (2, 1)                    # one card; the stores of both copies, counted once


async def test_a_promotion_with_other_terms_or_other_products_stays_a_separate_deal(session):
    product, stores = await make_world(session)
    other = Product(barcode="7290000000999", name="אחר")
    session.add(other)
    await session.flush()
    for st in stores:
        session.add(Price(product_id=other.id, store_id=st.id, price="5.00", price_updated_at=datetime(2026, 10, 12), is_current=True))
    await session.commit()
    await add_copy(session, product, stores, promotion_id="p2", description="3 ב-8", price="8.00")
    await add_copy(session, product, stores, promotion_id="p3", description="3 ב-9 עם עוד", extra_product=other)
    assert len(await deals(session)) == 3


async def test_a_store_that_has_no_shelf_price_for_the_product_is_not_part_of_the_deal(session):
    product, stores = await make_world(session)
    chain = (await session.execute(select(Chain).where(Chain.chain_id == "1"))).scalar_one()
    ghost = Store(chain_id=chain.id, store_id="9", name="סניף בלי מחיר", city="חיפה")
    session.add(ghost)
    await session.flush()
    await add_copy(session, product, [ghost], promotion_id="p1", description="3 ב-9")
    [row] = await deals(session)
    assert row.stores == 2                                          # the third store never listed the product


async def test_a_promotion_only_in_stores_without_a_shelf_price_is_not_a_deal(session):
    product, stores = await make_world(session)
    await session.execute(update(Price).where(Price.store_id.in_([s.id for s in stores])).values(is_current=False))
    await session.commit()
    await maintenance.refresh_deals()
    assert await deals(session) == []


async def test_copies_with_and_without_a_quantity_limit_are_different_deals(session):
    product, stores = await make_world(session)
    await add_copy(session, product, stores, promotion_id="p2", description="3 ב-9")
    await session.execute(update(Promotion).where(Promotion.promotion_id == "p2").values(max_qty=6))
    await session.commit()
    await maintenance.refresh_deals()
    assert len(await deals(session)) == 2


async def test_the_shortest_description_and_the_earliest_end_are_shown_for_merged_copies(session):
    product, stores = await make_world(session)
    await add_copy(session, product, stores, promotion_id="p2", description="3 ב-9 מבצע ארוך מאוד")
    await session.execute(update(Promotion).where(Promotion.promotion_id == "p2").values(end_date=NOW_IL() + timedelta(days=2)))
    await session.commit()
    await maintenance.refresh_deals()
    row = (await session.execute(text("select description, ends_at from promo_deals"))).one()
    assert row.description == "3 ב-9.00" and row.ends_at < NOW_IL() + timedelta(days=3)


async def test_a_deal_keeps_one_stable_id_whichever_copy_is_filed_first(session):
    product, stores = await make_world(session)
    before = (await session.execute(text("select deal_id from promo_deals"))).scalar_one()
    await add_copy(session, product, stores[:1], promotion_id="p0", description="3 ב-9 ")
    after = (await session.execute(text("select deal_id from promo_deals"))).scalar_one()
    assert before == after


@pytest.mark.parametrize("kwargs", [
    {"eligible": False},
    {"promo_age_days": 8},                                        # the store's promotion data is stale
    {"wholesale": True},
    {"market_min": "0.10"},                                       # a placeholder is not a market price
])
async def test_what_cannot_be_trusted_is_not_in_the_view(session, kwargs):
    await make_world(session, **kwargs)
    assert await deals(session) == []


async def test_ended_and_not_yet_started_promotions_are_not_in_the_view(session):
    await make_world(session, ends=NOW_IL() - timedelta(days=1), starts=NOW_IL() - timedelta(days=9))
    assert await deals(session) == []


async def test_the_mixed_bitan_carrefour_chain_is_split_by_store_name_like_display_chain_name(session):
    from app.chains import MIXED_CHAIN, display_chain_name

    await make_world(session, chain_name=MIXED_CHAIN, store_names=("יינות ביתן טבעון", "קרפור מרקט אילת"), cities=("טבעון", "אילת"))
    rows = await deals(session)
    assert sorted(r.brand for r in rows) == sorted([display_chain_name(MIXED_CHAIN, "יינות ביתן טבעון"),
                                                   display_chain_name(MIXED_CHAIN, "קרפור מרקט אילת")])
    assert all(r.stores == 1 for r in rows)


import httpx
from httpx import ASGITransport

from main import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_the_list_returns_a_deal_with_its_numbers_and_a_picture(client, session):
    await make_world(session)
    body = (await client.get("/api/v1/deals")).json()
    assert body["total"] == 1 and body["chains"] == [{"name": "רשת א", "count": 1}]
    [deal] = body["deals"]
    assert (deal["brand"], deal["kind"], deal["min_qty"], deal["stores"], deal["products"]) == ("רשת א", "single", 3, 2, 1)
    assert float(deal["unit_price"]) == 3.0 and float(deal["ref_price"]) == 4.0 and round(float(deal["saving_pct"]), 2) == 0.25
    assert [p["barcode"] for p in deal["sample_products"]] == ["7290000000501"]
    assert deal["sample_products"][0]["image_url"] == "https://img.example/x.png"


@pytest.mark.parametrize("price", ["12.00", "11.00", "3.00"])       # 0% (not cheaper), 8% (too small), 75% (suspicious)
async def test_deals_that_are_not_clearly_cheaper_or_look_wrong_are_hidden(client, session, price):
    await make_world(session, price=price, market_min="4.00")
    assert (await client.get("/api/v1/deals")).json()["deals"] == []


async def test_a_promotion_that_ended_after_the_last_refresh_disappears_at_query_time(client, session):
    import asyncio
    await make_world(session, ends=NOW_IL() + timedelta(seconds=3))     # still running when the view is refreshed
    assert len((await client.get("/api/v1/deals")).json()["deals"]) == 1
    await asyncio.sleep(3.5)                                        # the view is not refreshed, the query still checks the date
    assert (await client.get("/api/v1/deals")).json()["deals"] == []


async def test_chain_and_city_filters(client, session):
    await make_world(session)
    assert len((await client.get("/api/v1/deals", params={"chain": "רשת א"})).json()["deals"]) == 1
    assert (await client.get("/api/v1/deals", params={"chain": "רשת ב"})).json()["deals"] == []
    assert len((await client.get("/api/v1/deals", params={"city": "עכו"})).json()["deals"]) == 1
    assert (await client.get("/api/v1/deals", params={"city": "אילת"})).json()["deals"] == []


async def test_kind_filter_separates_single_products_from_groups(client, session):
    await make_world(session)
    assert len((await client.get("/api/v1/deals", params={"kind": "single"})).json()["deals"]) == 1
    assert (await client.get("/api/v1/deals", params={"kind": "group"})).json()["deals"] == []


async def test_the_diverse_list_takes_at_most_two_deals_per_brand(client, session):
    await make_world(session)
    chain = (await session.execute(text("select id from chains where name = 'רשת א'"))).scalar_one()
    store_ids = [r[0] for r in (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain})).all()]
    local = NOW_IL()
    for n in range(4):                                              # four more products and deals in chain A
        product = Product(barcode=f"72900000006{n:02d}", name=f"עוד {n}")
        session.add(product)
        await session.flush()
        for sid in store_ids:
            session.add(Price(product_id=product.id, store_id=sid, price="5.00", price_updated_at=datetime(2026, 10, 12), is_current=True))
            session.add(Promotion(product_id=product.id, store_id=sid, promotion_id=f"x{n}", description="3 ב-9",
                                  min_qty=3, discounted_price="9.00", basket_eligible=True, price_is_total=True, is_active=True,
                                  start_date=local - timedelta(days=1), end_date=local + timedelta(days=4)))
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    everything = (await client.get("/api/v1/deals", params={"limit": 10})).json()
    diverse = (await client.get("/api/v1/deals", params={"limit": 10, "diverse": "true"})).json()
    assert len(everything["deals"]) == 5 and len(diverse["deals"]) == 2


async def add_deal(session, store_ids, n, *, image):
    """One more product on promotion ("3 for 9", shelf 5.00) in the given stores, with or without a picture."""
    local = NOW_IL()
    product = Product(barcode=f"72900000007{n:02d}", name=f"מוצר {n}", image_url="https://res.cloudinary.com/p.png" if image else None)
    session.add(product)
    await session.flush()
    for sid in store_ids:
        session.add(Price(product_id=product.id, store_id=sid, price="5.00", price_updated_at=datetime(2026, 10, 12), is_current=True))
        session.add(Promotion(product_id=product.id, store_id=sid, promotion_id=f"d{n}", description="3 ב-9",
                              min_qty=3, discounted_price="9.00", basket_eligible=True, price_is_total=True, is_active=True,
                              start_date=local - timedelta(days=1), end_date=local + timedelta(days=4)))


async def many_deals(session, count, *, pictured_from=0):
    """`count` deals of chain A; those numbered `pictured_from` and up have a picture, the first ones have none."""
    await make_world(session)
    chain = (await session.execute(text("select id from chains where name = 'רשת א'"))).scalar_one()
    store_ids = [r[0] for r in (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain})).all()]
    for n in range(count):
        await add_deal(session, store_ids, n, image=n >= pictured_from)
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()


async def test_pictured_only_leaves_out_deals_without_a_product_picture(client, session):
    await many_deals(session, 3, pictured_from=2)                   # two deals without a picture, one with (plus make_world's)
    everything = (await client.get("/api/v1/deals", params={"limit": 20})).json()
    only = (await client.get("/api/v1/deals", params={"limit": 20, "pictured": "true"})).json()
    assert everything["total"] == 4 and only["total"] == 2
    assert all(any(p["image_url"] for p in d["sample_products"]) for d in only["deals"])


async def test_deals_with_a_picture_come_first_then_the_rest_and_paging_keeps_that_order(client, session):
    await make_world(session)                                       # one deal with a picture, 25% under the market
    chain = (await session.execute(text("select id from chains where name = 'רשת א'"))).scalar_one()
    store_ids = [r[0] for r in (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain})).all()]
    for n in range(6):                                              # 0-2 without a picture, 3-5 with one
        await add_deal(session, store_ids, n, image=n >= 3)
    await session.commit()
    no_picture = (await session.execute(text("select id from products where image_url is null"))).scalars().all()
    await session.execute(update(Promotion).where(Promotion.product_id.in_(no_picture)).values(discounted_price="6.00"))
    await session.commit()                                          # the ones without a picture are the better deals (cheaper per unit)
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()

    async def order(sort, **extra):
        got = []
        for offset in range(0, 7, 2):                               # three pages of two
            body = (await client.get("/api/v1/deals", params={"sort": sort, "limit": 2, "offset": offset, **extra})).json()
            got += [any(p["image_url"] for p in d["sample_products"]) for d in body["deals"]]
        return got

    for sort in ("best", "ending"):
        got = await order(sort)
        assert got == [True] * 4 + [False] * 3, (sort, got)         # four with a picture first, then the three without
    best = (await client.get("/api/v1/deals", params={"limit": 10})).json()["deals"]
    savings = [float(d["saving_pct"]) for d in best]
    assert len(savings) == 7 and max(savings[:4]) < min(savings[4:])    # the picture beats the size of the saving


async def test_pictured_looks_at_every_product_a_card_can_show_and_follows_the_city_filter(client, session):
    product, stores = await make_world(session)                      # one deal: the product has a picture
    await session.execute(update(Product).where(Product.id == product.id).values(image_url=None))
    others = []
    for n in range(10):                                              # a group deal whose only picture is the 10th product
        other = Product(barcode=f"72900000008{n:02d}", name=f"חבר {n}",
                        image_url="https://res.cloudinary.com/g.png" if n == 9 else None)
        session.add(other)
        others.append(other)
    await session.flush()
    for st in stores:
        for other in others:
            session.add(Price(product_id=other.id, store_id=st.id, price="5.00", price_updated_at=datetime(2026, 10, 12), is_current=True))
    await session.commit()
    await add_copy(session, product, stores, promotion_id="grp", description="3 ב-9 קבוצה", extra_product=others[0])
    for other in others[1:]:
        await add_copy(session, other, stores, promotion_id="grp", description="3 ב-9 קבוצה")
    group = [d for d in (await client.get("/api/v1/deals", params={"limit": 20})).json()["deals"] if d["kind"] == "group"]
    assert len(group) == 1
    shown = (await client.get("/api/v1/deals", params={"limit": 20, "pictured": "true"})).json()["deals"]
    assert [d["deal_id"] for d in shown] == [group[0]["deal_id"]]      # the single deal has no picture, the group has one
    assert any(p["image_url"] for p in shown[0]["sample_products"])    # and the card really gets it
    haifa = (await client.get("/api/v1/deals", params={"limit": 20, "pictured": "true", "city": "חיפה"})).json()
    nowhere = (await client.get("/api/v1/deals", params={"limit": 20, "pictured": "true", "city": "אילת"})).json()
    assert len(haifa["deals"]) == 1 and haifa["total"] == 1 and nowhere["deals"] == [] and nowhere["total"] == 0


async def test_a_few_big_brands_do_not_shrink_the_daily_pick(client, session, monkeypatch):
    from app.api import routes

    await make_world(session)
    chain = (await session.execute(text("select id from chains where name = 'רשת א'"))).scalar_one()
    store_ids = [r[0] for r in (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain})).all()]
    for n in range(30):                                              # thirty deals of one brand ...
        await add_deal(session, store_ids, n, image=True)
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    monkeypatch.setattr(routes, "_rotation_seed", lambda: 5)
    body = (await client.get("/api/v1/deals", params={"limit": 8, "daily": "true", "pictured": "true"})).json()
    assert len(body["deals"]) == 2 and body["total"] == 2            # ... give two cards (the per-brand cap), not an empty strip


async def test_the_daily_selection_is_stable_within_a_day_and_changes_with_the_day(client, session, monkeypatch):
    from app.api import routes

    # chain A can show only two per brand, so spread the deals over several brands
    await make_world(session)
    local = NOW_IL()
    for b in range(12):
        chain = Chain(chain_id=f"9{b}", name=f"מותג {b}")
        session.add(chain)
        await session.flush()
        store = Store(chain_id=chain.id, store_id="1", name=f"סניף {b}", city="חיפה")
        session.add(store)
        await session.flush()
        for n in range(2):
            await add_deal(session, [store.id], b * 10 + n, image=True)
        await session.commit()
        await session.execute(update(Store).where(Store.id == store.id).values(last_promo_at=func.now()))
        await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()

    async def today(seed):
        monkeypatch.setattr(routes, "_rotation_seed", lambda: seed)
        r = await client.get("/api/v1/deals", params={"limit": 6, "daily": "true", "pictured": "true"})
        return [d["deal_id"] for d in r.json()["deals"]]

    monday, monday_again, tuesday = await today(100), await today(100), await today(101)
    assert len(monday) == 6 and monday == monday_again          # the same all day
    assert monday != tuesday                                    # a different pick the next day
    assert len(set(monday)) == 6


async def test_ending_sort_lists_the_soonest_first_and_pages(client, session):
    await make_world(session)
    body = (await client.get("/api/v1/deals", params={"sort": "ending", "limit": 1, "offset": 0})).json()
    assert body["total"] == 1 and len(body["deals"]) == 1
    assert (await client.get("/api/v1/deals", params={"limit": 1, "offset": 1})).json()["deals"] == []


async def test_a_deals_products_are_listed_and_an_unknown_deal_is_404(client, session):
    await make_world(session)
    deal_id = (await client.get("/api/v1/deals")).json()["deals"][0]["deal_id"]
    products = (await client.get(f"/api/v1/deals/{deal_id}/products")).json()
    assert [p["barcode"] for p in products] == ["7290000000501"]
    assert (await client.get("/api/v1/deals/nope/products")).status_code == 404


async def test_the_limits_are_enforced(client):
    assert (await client.get("/api/v1/deals", params={"limit": 61})).status_code == 422
    assert (await client.get("/api/v1/deals", params={"offset": 10001})).status_code == 422
    # the list is ~4,000 long and pictured promotions come first, so the unpictured ones start past 1,000
    assert (await client.get("/api/v1/deals", params={"offset": 3000})).status_code == 200
    assert (await client.get("/api/v1/deals", params={"sort": "random"})).status_code == 422



# ── review fixes ──────────────────────────────────────────────────────────────

async def test_a_price_the_text_does_not_confirm_is_not_a_set_price_unless_it_is_for_one_unit(session):
    # "MinQty 2, price 4.50" without "2 ב-4.50" in the text may be 4.50 EACH: the card would claim 2.25 a unit.
    await make_world(session, min_qty=2, price="4.50", price_is_total=False)
    assert await deals(session) == []


async def test_a_one_unit_sale_price_needs_no_confirmation(session):
    await make_world(session, min_qty=1, price="3.00", price_is_total=False)
    assert len(await deals(session)) == 1


async def test_an_item_with_a_short_internal_code_is_not_a_deal(session):
    # codes under 7 characters are chain-scoped: one products row mixes unrelated items, its prices mean nothing
    await make_world(session, barcode="123")
    assert await deals(session) == []


async def test_a_product_only_the_promoting_brand_sells_is_marked_as_not_compared_with_the_market(session):
    await make_world(session, other_sells=False)
    [row] = await deals(session)
    assert row.vs_market is False and float(row.ref_price) == 5.0     # its own shelf, possibly inflated
    await session.execute(text("truncate chains, products restart identity cascade"))
    await session.commit()
    await make_world(session)
    [row] = await deals(session)
    assert row.vs_market is True


async def test_deals_sold_elsewhere_rank_before_deals_only_one_brand_sells(client, session):
    await make_world(session, other_sells=False)                       # a 40% deal against its own shelf only
    local = NOW_IL()
    chain_b = (await session.execute(text("select id from chains where name = 'רשת ב'"))).scalar_one()
    store_b = (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain_b})).scalar_one()
    store_a = (await session.execute(text("select id from stores where name = 'סניף א1'"))).scalar_one()
    other = Product(barcode="7290000000777", name="נמכר גם ברשת אחרת", image_url="https://img.example/o.png")   # a picture too: only the market comparison decides
    session.add(other)
    await session.flush()
    for sid, shelf in ((store_a, "5.00"), (store_b, "4.90")):
        session.add(Price(product_id=other.id, store_id=sid, price=shelf, price_updated_at=datetime(2026, 10, 12), is_current=True))
    session.add(Promotion(product_id=other.id, store_id=store_a, promotion_id="q1", description="3 ב-12", min_qty=3,
                          discounted_price="12.00", basket_eligible=True, price_is_total=True, is_active=True,
                          start_date=local - timedelta(days=1), end_date=local + timedelta(days=4)))   # 18% only
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    deals_json = (await client.get("/api/v1/deals")).json()["deals"]
    assert [d["vs_market"] for d in deals_json] == [True, False]       # the weaker deal compared with the market goes first


async def test_ties_are_ordered_by_deal_id_so_paging_never_repeats_or_skips(client, session):
    await make_world(session)
    chain = (await session.execute(text("select id from chains where name = 'רשת א'"))).scalar_one()
    store_ids = [r[0] for r in (await session.execute(text("select id from stores where chain_id = :c"), {"c": chain})).all()]
    local = NOW_IL()
    for n in range(5):                                              # five more deals with exactly the same numbers
        product = Product(barcode=f"72900000007{n:02d}", name=f"עוד {n}")
        session.add(product)
        await session.flush()
        for sid in store_ids:
            session.add(Price(product_id=product.id, store_id=sid, price="4.00", price_updated_at=datetime(2026, 10, 12), is_current=True))
            session.add(Promotion(product_id=product.id, store_id=sid, promotion_id=f"t{n}", description="3 ב-9",
                                  min_qty=3, discounted_price="9.00", basket_eligible=True, price_is_total=True, is_active=True,
                                  start_date=local - timedelta(days=1), end_date=local + timedelta(days=4)))
    await session.commit()
    await maintenance.refresh_popularity()
    await maintenance.refresh_deals()
    tied = [d for d in (await client.get("/api/v1/deals", params={"limit": 20})).json()["deals"] if d["description"] == "3 ב-9"]
    assert len(tied) == 5 and [d["deal_id"] for d in tied] == sorted(d["deal_id"] for d in tied)
    pages = []
    for offset in range(6):
        pages += (await client.get("/api/v1/deals", params={"limit": 1, "offset": offset})).json()["deals"]
    assert len({d["deal_id"] for d in pages}) == 6                    # no card repeated or skipped across pages


async def test_the_store_count_follows_the_city_filter(client, session):
    await make_world(session)
    assert (await client.get("/api/v1/deals")).json()["deals"][0]["stores"] == 2
    assert (await client.get("/api/v1/deals", params={"city": "עכו"})).json()["deals"][0]["stores"] == 1


# ── the rules the customer is told about ──────────────────────────────────────

async def test_the_response_states_the_rules_the_page_explains(client, session):
    from app.api.routes import MAX_DEAL_SAVING, MIN_DEAL_SAVING, MIN_REFERENCE_PRICE
    await make_world(session)
    rules = (await client.get("/api/v1/deals")).json()["rules"]
    assert float(rules["min_saving"]) == float(MIN_DEAL_SAVING) == 0.10
    assert float(rules["max_saving"]) == float(MAX_DEAL_SAVING) == 0.60
    assert float(rules["min_reference_price"]) == float(MIN_REFERENCE_PRICE) == 0.50


async def test_the_rules_are_stated_even_when_there_are_no_deals(client):
    await maintenance.refresh_popularity()                          # the view survives between tests: rebuild it empty
    await maintenance.refresh_deals()
    body = (await client.get("/api/v1/deals")).json()
    assert body["deals"] == [] and "rules" in body


async def test_the_stated_minimum_reference_price_is_what_the_view_really_uses(session):
    # the page tells shoppers "no comparison against prices under 0.50": the view must agree to the agora
    from app.api.routes import MIN_REFERENCE_PRICE
    await make_world(session, market_min=str(MIN_REFERENCE_PRICE - Decimal("0.01")), price="1.20", min_qty=3)
    assert await deals(session) == []                               # a reference of 0.49 is a placeholder
    await session.execute(text("truncate chains, products restart identity cascade"))
    await session.commit()
    await make_world(session, market_min=str(MIN_REFERENCE_PRICE), price="1.20", min_qty=3)   # 0.40 a unit against 0.50
    [row] = await deals(session)
    assert round(float(row.saving_pct), 2) == 0.20
