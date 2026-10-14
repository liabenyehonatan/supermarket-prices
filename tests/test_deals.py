# The deals view and endpoint: one row per (brand, promotion), measured against the cheapest shelf price.

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, text, update

from app.db.models import Chain, Price, Product, Promotion, Store
from app.pipeline import maintenance

NOW_IL = lambda: datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)


async def make_world(session, *, ends=None, starts=None, eligible=True, promo_age_days=0, price="9.00", min_qty=3,
                     market_min="4.00", chain_name="רשת א", store_names=("סניף א1", "סניף א2"), cities=("חיפה", "עכו"),
                     wholesale=False):
    """Chain A (two stores) runs `min_qty for price` on one product. Chain B sells the same product at `market_min`."""
    chain_a, chain_b = Chain(chain_id="1", name=chain_name), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    stores = [Store(chain_id=chain_a.id, store_id=str(i), name=("סיטונאי " + n) if wholesale else n, city=city)
              for i, (n, city) in enumerate(zip(store_names, cities), 1)]
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב", city="חיפה")
    product = Product(barcode="7290000000501", name="מוצר", image_url="https://img.example/x.png")
    session.add_all([*stores, store_b, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    for st in stores:
        session.add(Price(product_id=product.id, store_id=st.id, price="5.00", price_updated_at=now, is_current=True))
    session.add(Price(product_id=product.id, store_id=store_b.id, price=market_min, price_updated_at=now, is_current=True))
    local = NOW_IL()
    for st in stores:
        session.add(Promotion(
            product_id=product.id, store_id=st.id, promotion_id="p1", description=f"{min_qty} ב-{price}",
            min_qty=min_qty, discounted_price=price, basket_eligible=eligible, price_is_total=True, is_active=True,
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
        "select brand, stores, products, min_qty, price, unit_price, ref_price, saving_pct from promo_deals"))
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
