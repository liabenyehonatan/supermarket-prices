# Behaviour of the bulk price loader (app/parser/price_loader.py).

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.db.models import Price, Product
from app.parser.price_loader import load_price_rows, normalize_row

T0 = datetime(2026, 5, 1, 10, 0)


def item(code, price, name="מוצר", when=T0, **extra):
    row = {
        "itemcode": code,
        "itemname": name,
        "itemprice": str(price),
        "priceupdatedate": when.strftime("%Y-%m-%d %H:%M"),
        "unitofmeasureprice": "1.00",
    }
    row.update(extra)
    return row


async def rows(items):
    for it in items:
        yield it


async def load(session, store, items, *, full=False, ts=T0):
    stats = await load_price_rows(session, store, rows(items), is_full=full, fallback_ts=ts)
    await session.commit()
    return stats


async def current(session, store):
    result = await session.execute(
        select(Product.barcode, Price.price, Price.is_current)
        .join(Product, Price.product_id == Product.id)
        .where(Price.store_id == store.id)
        .order_by(Product.barcode, Price.id)
    )
    return result.all()


async def test_new_items_create_products_and_prices(session, store):
    stats = await load(session, store, [item("111", "6.50"), item("222", "3.30", name="שני")])
    assert (stats.inserted, stats.changed, stats.invalid) == (2, 0, 0)
    rows_ = await current(session, store)
    assert [(b, p, c) for b, p, c in rows_] == [("111", Decimal("6.50"), True), ("222", Decimal("3.30"), True)]


async def test_product_name_first_seen_wins(session, store):
    await load(session, store, [item("111", "5", name="שם ראשון")])
    await load(session, store, [item("111", "5", name="שם שני")])
    name = (await session.execute(select(Product.name).where(Product.barcode == "111"))).scalar_one()
    assert name == "שם ראשון"


async def test_changed_price_closes_old_row_and_keeps_one_current(session, store):
    await load(session, store, [item("111", "5.00")])
    stats = await load(session, store, [item("111", "6.00", when=T0 + timedelta(days=1))])
    assert stats.changed == 1
    assert await current(session, store) == [
        ("111", Decimal("5.00"), False),
        ("111", Decimal("6.00"), True),
    ]


async def test_unchanged_price_writes_nothing_new(session, store):
    await load(session, store, [item("111", "5.00")])
    stats = await load(session, store, [item("111", "5.00", when=T0 + timedelta(days=1))])
    assert (stats.unchanged, stats.inserted, stats.changed) == (1, 0, 0)
    assert len(await current(session, store)) == 1


async def test_unchanged_price_touch_is_throttled(session, store):
    await load(session, store, [item("111", "5.00")])
    first_seen = (await session.execute(select(Price.scraped_at))).scalar_one()

    stats = await load(session, store, [item("111", "5.00")])
    assert stats.touched == 0  # seen again moments later: no write
    assert (await session.execute(select(Price.scraped_at))).scalar_one() == first_seen

    await session.execute(update(Price).values(scraped_at=func.now() - timedelta(hours=30)))
    await session.commit()
    stats = await load(session, store, [item("111", "5.00")])
    assert stats.touched == 1  # older than the touch interval: refreshed once


async def test_older_file_never_overwrites_newer_price(session, store):
    await load(session, store, [item("111", "9.00", when=T0 + timedelta(days=2))])
    stats = await load(session, store, [item("111", "5.00", when=T0)])  # late, stale file
    assert stats.stale_ignored == 1 and stats.changed == 0
    assert await current(session, store) == [("111", Decimal("9.00"), True)]


async def test_invalid_rows_are_skipped_not_fatal(session, store):
    items = [
        item("111", "5.00"),
        item("222", "NaN"),
        item("333", "-1"),
        item("444", "123456789"),         # does not fit Numeric(10, 2)
        item("555", "abc"),
        item("6" * 21, "5"),               # barcode longer than the column
        item("", "5"),
        item("888", "7.00", name="bad\x00name"),   # NUL byte breaks PostgreSQL text
    ]
    stats = await load(session, store, items)
    assert stats.invalid == 6 and stats.inserted == 2
    assert {b for b, _, _ in await current(session, store)} == {"111", "888"}
    name = (await session.execute(select(Product.name).where(Product.barcode == "888"))).scalar_one()
    assert "\x00" not in name


async def test_prices_compare_at_two_decimals(session, store):
    await load(session, store, [item("111", "12.35")])
    stats = await load(session, store, [item("111", "12.345")])  # rounds to 12.35
    assert stats.changed == 0 and stats.unchanged == 1


async def test_duplicate_barcode_in_one_file_newest_wins(session, store):
    stats = await load(session, store, [
        item("111", "5.00", when=T0),
        item("111", "7.00", when=T0 + timedelta(hours=1)),
        item("111", "6.00", when=T0 + timedelta(minutes=5)),
    ])
    assert stats.inserted == 1
    assert await current(session, store) == [("111", Decimal("7.00"), True)]


async def test_many_rows_across_chunk_boundaries(session, store):
    items = [item(f"{i:08d}", f"{1 + i % 50}.00") for i in range(1250)]
    items.append(item("00000007", "99.00", when=T0 + timedelta(hours=1)))  # same barcode, later chunk
    stats = await load(session, store, items)
    assert stats.rows_total == 1251
    assert stats.inserted == 1250 and stats.changed == 1
    count = (await session.execute(
        select(func.count()).select_from(Price).where(Price.is_current.is_(True))
    )).scalar_one()
    assert count == 1250


async def test_full_file_closes_products_it_no_longer_lists(session, store):
    await load(session, store, [item(f"{i}", "5.00") for i in range(10)], full=True)
    stats = await load(session, store, [item(f"{i}", "5.00") for i in range(8)], full=True)
    assert stats.closed_missing == 2
    open_ = {b for b, _, c in await current(session, store) if c}
    assert open_ == {str(i) for i in range(8)}


async def test_truncated_full_file_does_not_wipe_the_store(session, store):
    await load(session, store, [item(f"{i}", "5.00") for i in range(10)], full=True)
    stats = await load(session, store, [item("0", "5.00")], full=True)  # 1 of 10 < 50%
    assert stats.full_close_skipped and stats.closed_missing == 0
    assert len([1 for _, _, c in await current(session, store) if c]) == 10


async def test_delta_file_never_closes_anything(session, store):
    await load(session, store, [item(f"{i}", "5.00") for i in range(10)], full=True)
    stats = await load(session, store, [item("0", "5.00")], full=False)
    assert stats.closed_missing == 0
    assert len([1 for _, _, c in await current(session, store) if c]) == 10


async def test_database_refuses_two_current_rows(session, store):
    await load(session, store, [item("111", "5.00")])
    product_id = (await session.execute(select(Product.id))).scalar_one()
    with pytest.raises(IntegrityError):
        await session.execute(text(
            "INSERT INTO prices (product_id, store_id, price, price_updated_at, is_current) "
            "VALUES (:p, :s, 1, now(), true)"), {"p": product_id, "s": store.id})
    await session.rollback()


def test_normalize_row_uses_fallback_timestamp_and_quantises():
    rec = normalize_row({"itemcode": "1", "itemprice": "1.005"}, T0)
    assert rec.updated_at == T0
    assert rec.price == Decimal("1.01")
    assert isinstance(rec.price, Decimal)
