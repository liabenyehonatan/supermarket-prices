# app/parser/price_loader.py
#
# Set-based loading of one PriceFull / Price file into products + prices.
#
# The old loader issued one SELECT per row (and a second for the product). That
# is fine on localhost and unusable over any real network, so this works per
# chunk of PARSE_BATCH_SIZE rows instead:
#
#   1. normalise + validate rows in Python (bad rows are counted, never sent)
#   2. one query for the products, one INSERT ... ON CONFLICT DO NOTHING for new
#      ones (first-seen name wins, race-safe)
#   3. one query for the store's current prices of those products
#   4. decide in Python: new / changed / unchanged / older-than-what-we-hold
#   5. at most one UPDATE (close old rows), one INSERT (new rows), one UPDATE
#      (touch scraped_at)
#
# Money is Decimal end to end and quantised to the column's 2 places before it
# is compared, so "12.345" never looks like a change against a stored 12.35.

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import AsyncIterator, Optional

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import Price, Product, Store
from app.parser.universal_parser import _get, _safe_datetime, _safe_decimal

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")
# Numeric(10, 2) holds |x| < 10**8.
_MAX_MONEY = Decimal("99999999.99")
_MAX_BARCODE_LEN = 20  # products.barcode is String(20)


def _clean_text(value: Optional[str], max_len: Optional[int] = None) -> Optional[str]:
    """Strip NUL bytes (PostgreSQL rejects them) and cut to the column width."""
    if value is None:
        return None
    value = value.replace("\x00", "").strip()
    if not value:
        return None
    return value[:max_len] if max_len else value


def _money(value: Optional[str]) -> Optional[Decimal]:
    """Parse a price string to a finite, in-range Decimal with 2 places."""
    amount = _safe_decimal(value)
    if amount is None or not amount.is_finite():  # rejects NaN / Infinity
        return None
    amount = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    if amount < 0 or amount > _MAX_MONEY:
        return None
    return amount


@dataclass
class PriceRecord:
    barcode: str
    name: str
    brand: Optional[str]
    manufacturer: Optional[str]
    unit_of_measure: Optional[str]
    is_weighted: bool
    price: Decimal
    unit_price: Optional[Decimal]
    updated_at: datetime


def normalize_row(row: dict, fallback_ts: Optional[datetime]) -> Optional[PriceRecord]:
    """Turn one parsed XML item into a PriceRecord, or None if it is unusable."""
    barcode = _clean_text(_get(row, "ItemCode", "itemcode", "ITEMCODE"))
    if not barcode or len(barcode) > _MAX_BARCODE_LEN:
        return None

    price = _money(_get(row, "ItemPrice", "itemprice", "ITEMPRICE"))
    if price is None:
        return None

    unit_price = _money(
        _get(row, "UnitOfMeasurePrice", "unitofmeasureprice",
             "UnitMeasurePrice", "unitmeasureprice")
    )
    updated_at = (
        _safe_datetime(_get(row, "PriceUpdateDate", "PriceUpdateTime",
                            "priceupdatedate", "priceupdatetime"))
        or fallback_ts
        or datetime.now()
    )
    manufacturer = _clean_text(
        _get(row, "ManufacturerName", "ManufactureName",
             "manufacturername", "manufacturename"),
        200,
    )
    return PriceRecord(
        barcode=barcode,
        name=_clean_text(_get(row, "ItemName", "itemname", "ITEMNAME")) or barcode,
        brand=manufacturer,
        manufacturer=manufacturer,
        unit_of_measure=_clean_text(
            _get(row, "UnitOfMeasure", "UnitMeasure", "unitofmeasure", "unitmeasure"), 50
        ),
        is_weighted=_get(row, "bIsWeighted", "BisWeighted", "bisweighted", default="0") == "1",
        price=price,
        unit_price=unit_price,
        updated_at=updated_at,
    )


@dataclass
class LoadStats:
    rows_total: int = 0
    invalid: int = 0
    inserted: int = 0          # first price we hold for (store, product)
    changed: int = 0           # price differs: old row closed, new row inserted
    unchanged: int = 0
    touched: int = 0           # unchanged rows whose scraped_at was refreshed
    stale_ignored: int = 0     # file held an older price than the DB already has
    closed_missing: int = 0    # current prices a full file no longer lists
    full_close_skipped: bool = False
    seen_product_ids: set = field(default_factory=set, repr=False)

    @property
    def rows_applied(self) -> int:
        return self.inserted + self.changed

    @property
    def valid(self) -> int:
        return self.rows_total - self.invalid


async def _product_ids(session: AsyncSession, barcodes: list[str]) -> dict[str, int]:
    result = await session.execute(
        select(Product.barcode, Product.id).where(Product.barcode.in_(barcodes))
    )
    return {barcode: pid for barcode, pid in result.all()}


async def _resolve_products(session: AsyncSession, records: list[PriceRecord]) -> dict[str, int]:
    """barcode -> product id, creating missing products (first-seen name wins)."""
    ids = await _product_ids(session, [r.barcode for r in records])
    missing = sorted((r for r in records if r.barcode not in ids), key=lambda r: r.barcode)
    if missing:
        # Sorted so concurrent loaders take row locks in the same order.
        await session.execute(
            pg_insert(Product)
            .values([
                {
                    "barcode": r.barcode,
                    "name": r.name,
                    "brand": r.brand,
                    "manufacturer": r.manufacturer,
                    "unit_of_measure": r.unit_of_measure,
                    "is_weighted": r.is_weighted,
                }
                for r in missing
            ])
            .on_conflict_do_nothing(index_elements=[Product.barcode])
        )
        ids.update(await _product_ids(session, [r.barcode for r in missing]))
    return ids


async def _apply_chunk(
    session: AsyncSession, store: Store, records: list[PriceRecord], stats: LoadStats
) -> None:
    product_ids = await _resolve_products(session, records)

    touch_after = timedelta(hours=settings.TOUCH_INTERVAL_HOURS)
    existing_rows = await session.execute(
        select(
            Price.id,
            Price.product_id,
            Price.price,
            Price.price_updated_at,
            (func.now() - Price.scraped_at > touch_after).label("needs_touch"),
        ).where(
            Price.store_id == store.id,
            Price.is_current.is_(True),
            Price.product_id.in_(list(product_ids.values())),
        )
    )
    existing = {row.product_id: row for row in existing_rows.all()}

    to_close: list[int] = []
    to_insert: list[dict] = []
    to_touch: list[int] = []

    for rec in records:
        pid = product_ids.get(rec.barcode)
        if pid is None:  # product insert raced and lost with no row visible: skip safely
            stats.invalid += 1
            continue
        stats.seen_product_ids.add(pid)
        current = existing.get(pid)

        new_row = {
            "product_id": pid,
            "store_id": store.id,
            "price": rec.price,
            "unit_price": rec.unit_price,
            "price_updated_at": rec.updated_at,
            "is_current": True,
        }
        if current is None:
            to_insert.append(new_row)
            stats.inserted += 1
        elif rec.updated_at < current.price_updated_at:
            # A late or re-run file must never overwrite a newer price.
            stats.stale_ignored += 1
        elif current.price != rec.price:
            to_close.append(current.id)
            to_insert.append(new_row)
            stats.changed += 1
        else:
            stats.unchanged += 1
            if current.needs_touch:
                to_touch.append(current.id)

    # Order matters: close the old rows before inserting their replacements, or
    # the "one current row per (store, product)" unique index rejects the insert.
    if to_close:
        await session.execute(
            update(Price).where(Price.id.in_(to_close)).values(is_current=False)
        )
    if to_insert:
        await session.execute(insert(Price), to_insert)
    if to_touch:
        await session.execute(
            update(Price).where(Price.id.in_(to_touch)).values(scraped_at=func.now())
        )
        stats.touched += len(to_touch)


def _dedupe(records: list[PriceRecord]) -> list[PriceRecord]:
    """One record per barcode: the newest by price date, later row on a tie."""
    best: dict[str, PriceRecord] = {}
    for rec in records:
        prev = best.get(rec.barcode)
        if prev is None or rec.updated_at >= prev.updated_at:
            best[rec.barcode] = rec
    return list(best.values())


async def _close_missing(session: AsyncSession, store: Store, stats: LoadStats) -> None:
    """After a PriceFull file: close current prices the chain no longer lists."""
    current = (await session.execute(
        select(Price.id, Price.product_id).where(
            Price.store_id == store.id, Price.is_current.is_(True)
        )
    )).all()
    if not current:
        return
    if len(stats.seen_product_ids) < settings.STALE_CLOSE_MIN_RATIO * len(current):
        # Looks truncated or partial: closing the difference would wipe the store.
        stats.full_close_skipped = True
        logger.warning(
            "Store %s: full file lists %d of %d current products; not closing the rest",
            store.id, len(stats.seen_product_ids), len(current),
        )
        return
    gone = [pid_row.id for pid_row in current if pid_row.product_id not in stats.seen_product_ids]
    for start in range(0, len(gone), 5000):
        await session.execute(
            update(Price).where(Price.id.in_(gone[start:start + 5000])).values(is_current=False)
        )
    stats.closed_missing = len(gone)


async def load_price_rows(
    session: AsyncSession,
    store: Store,
    rows: AsyncIterator[dict],
    *,
    is_full: bool,
    fallback_ts: Optional[datetime] = None,
) -> LoadStats:
    """
    Load every row of one price file for one store inside the caller's
    transaction. Raises on a database error so the caller can roll back the file.
    """
    stats = LoadStats()
    chunk: list[PriceRecord] = []

    async for row in rows:
        stats.rows_total += 1
        rec = normalize_row(row, fallback_ts)
        if rec is None:
            stats.invalid += 1
            continue
        chunk.append(rec)
        if len(chunk) >= settings.PARSE_BATCH_SIZE:
            await _apply_chunk(session, store, _dedupe(chunk), stats)
            chunk = []
    if chunk:
        await _apply_chunk(session, store, _dedupe(chunk), stats)

    if is_full and stats.valid > 0:
        await _close_missing(session, store, stats)
    return stats
