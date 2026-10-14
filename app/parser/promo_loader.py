# app/parser/promo_loader.py
#
# Load a chain's PromoFull file into `promotions`.
#
# Phase A shows the chain's own promotion text next to a product; no price is computed from a
# promotion. So only what can be shown honestly is kept: promotions for everybody (no club, coupon
# or credit-card audience), of the "N for X" family (reward codes 1, 2, 3, 10), still running, with a
# product list small enough to be a product promotion (club-wide and spend-threshold promotions list
# tens of thousands of items). Reward 6 ("buy X get a gift") is dropped on purpose: its
# DiscountedPrice is the gift's price, not the item's.
#
# The parser library yields one dict per promotion with lowercase keys. Nested elements arrive as a
# dict when there is one and as a list when there are several, and the three chain layouts differ
# (items under promotionitems/item, or under groups/group/promotionitems/promotionitem), so every
# lookup below accepts both shapes.

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import Product, Promotion, Store
from app.parser.price_loader import _clean_text, _money
from app.parser.universal_parser import _safe_datetime, _safe_decimal

logger = logging.getLogger(__name__)

ALLOWED_REWARD_TYPES = {"1", "2", "3", "10"}
MAX_ITEMS_PER_PROMOTION = 100
_CANCELLED = "מבוטל"
_COUPON_PREFIX = "קופון"
_MAX_DESCRIPTION = 300


@dataclass
class PromoRecord:
    promotion_id: str
    description: str
    discounted_price: Optional[Decimal]
    min_qty: Optional[int]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    barcodes: list[str] = field(default_factory=list)
    basket_eligible: bool = False        # safe to compute a basket price with (Phase B1)
    max_qty: Optional[int] = None        # most units one purchase gets at the promotion price


def _as_list(value: Any) -> list:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _text(container: Any, *keys: str) -> Optional[str]:
    """First non-empty scalar among `keys` of a dict, as stripped text."""
    if not isinstance(container, dict):
        return None
    for key in keys:
        value = container.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def _items(row: dict) -> list[dict]:
    found: list[dict] = []

    def collect(container: Any) -> None:
        if isinstance(container, dict):
            for key in ("item", "promotionitem"):
                found.extend(i for i in _as_list(container.get(key)) if isinstance(i, dict))

    collect(row.get("promotionitems"))
    groups = row.get("groups")
    for group in _as_list(groups.get("group") if isinstance(groups, dict) else None):
        if isinstance(group, dict):
            collect(group.get("promotionitems"))
    return found


def _club_ids(row: dict) -> set[str]:
    """Every club id the promotion names, wherever the chain put it: on the promotion, in a <Clubs>
    element, or inside <AdditionalRestrictions> (KingStore, Netiv Hased and others)."""
    ids: set[str] = set()
    containers = [row]
    restrictions = row.get("additionalrestrictions")
    if isinstance(restrictions, dict):
        containers.append(restrictions)
    for container in containers:
        single = _text(container, "clubid")
        if single:
            ids.add(single)
        clubs = container.get("clubs")
        if isinstance(clubs, dict):
            ids.update(str(c).strip() for c in _as_list(clubs.get("clubid")) if str(c).strip())
    return ids


def _is_coupon(row: dict) -> bool:
    flags = {_text(row, "additionaliscoupon")}
    restrictions = row.get("additionalrestrictions")
    if isinstance(restrictions, dict):
        flags.add(_text(restrictions, "additionaliscoupon"))
    return "1" in flags


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return _safe_datetime(value.split(".")[0]) if value else None


def _when(row: dict, dt_key: str, date_key: str, hour_key: str, *, end: bool) -> Optional[datetime]:
    full = _parse_dt(_text(row, dt_key))
    if full:
        return full
    day = _parse_dt(_text(row, date_key))
    if day is None:
        return None
    hour = _text(row, hour_key)
    if hour:
        try:
            parts = [int(p) for p in hour.split(":")[:2]]
            return day.replace(hour=parts[0], minute=parts[1])
        except (ValueError, IndexError):
            pass
    return day.replace(hour=23, minute=59, second=59) if end else day


def _min_qty(raw: Optional[str]) -> Optional[int]:
    qty = _safe_decimal(raw)
    if qty is None or not qty.is_finite() or qty < 1 or qty != qty.to_integral_value():
        return None
    return int(qty)


BASKET_REWARD_TYPES = {"1", "10"}


def _positive_int(raw: Optional[str]) -> Optional[int]:
    """'5', '5.00' -> 5; '0', 'NO_BODY', '' and anything else -> None."""
    value = _safe_decimal(raw)
    if value is None or not value.is_finite() or value < 1 or value != value.to_integral_value():
        return None
    return int(value)


def _basket_eligible(
    row: dict, items: list[dict], rewards: set[str], barcodes: dict, min_qty: Optional[int],
    price: Optional[Decimal], max_qty: Optional[int],
) -> bool:
    """One product, "N for X" (reward 1 or 10), nothing that changes what N units cost at the till."""
    if len(barcodes) != 1 or not rewards <= BASKET_REWARD_TYPES:
        return False
    if min_qty is None or price is None or price <= 0:
        return False
    if _text(row, "isweightedpromo") == "1" or any(_text(i, "bisweighted") == "1" for i in items):
        return False
    if _text(row, "isgiftitem") == "1" or any(_text(i, "isgiftitem") == "1" for i in items):
        return False
    if _text(row, "redemptionlimit") not in (None, "0"):
        return False
    return max_qty is None or max_qty >= min_qty


def promotion_is_cancelled(row: dict) -> bool:
    return _CANCELLED in (_text(row, "promotiondescription") or "")


def promotion_has_items(row: dict) -> bool:
    return bool(_items(row))


def normalize_promotion(row: dict, *, as_of: datetime) -> Optional[PromoRecord]:
    """One parsed promotion → PromoRecord, or None when Phase A does not show it."""
    promotion_id = _clean_text(_text(row, "promotionid"), 50)
    description = _clean_text(_text(row, "promotiondescription"), _MAX_DESCRIPTION)
    if not promotion_id or not description:
        return None
    if _CANCELLED in description or description.startswith(_COUPON_PREFIX):
        return None
    if _is_coupon(row) or not _club_ids(row) <= {"0"}:
        return None

    items = _items(row)
    rewards = {_text(row, "rewardtype")} | {_text(i, "rewardtype") for i in items}
    rewards.discard(None)
    if not rewards or not rewards <= ALLOWED_REWARD_TYPES:
        return None

    barcodes: dict[str, None] = {}      # an ordered set: club-wide promotions list tens of thousands of items
    for item in items:
        code = _clean_text(_text(item, "itemcode"), 20)
        if code and code not in barcodes:
            barcodes[code] = None
            if len(barcodes) > MAX_ITEMS_PER_PROMOTION:
                return None             # not a product promotion; stop reading the rest of the list
    if not barcodes:
        return None

    end = _when(row, "promotionenddatetime", "promotionenddate", "promotionendhour", end=True)
    if end is not None and end < as_of:
        return None

    first = items[0] if items else {}
    price = _money(_text(row, "discountedprice") or _text(first, "discountedprice"))
    price = price if price and price > 0 else None
    min_qty = _min_qty(_text(row, "minqty") or _text(first, "minqty"))
    max_qty = _positive_int(_text(row, "maxqty")) or _positive_int(_text(first, "maxqty"))
    return PromoRecord(
        promotion_id=promotion_id,
        description=description,
        discounted_price=price,
        min_qty=min_qty,
        start_date=_when(row, "promotionstartdatetime", "promotionstartdate", "promotionstarthour", end=False),
        end_date=end,
        barcodes=list(barcodes),
        basket_eligible=_basket_eligible(row, items, rewards, barcodes, min_qty, price, max_qty),
        max_qty=max_qty,
    )


@dataclass
class PromoLoadStats:
    promotions: int = 0
    rows_inserted: int = 0
    unknown_barcodes: int = 0


async def replace_store_promotions(
    session: AsyncSession, store: Store, records: list[PromoRecord]
) -> PromoLoadStats:
    """Make `records` the store's whole promotion list. Runs in the caller's transaction."""
    stats = PromoLoadStats(promotions=len(records))
    wanted = sorted({code for record in records for code in record.barcodes})
    product_ids: dict[str, int] = {}
    for start in range(0, len(wanted), settings.PARSE_BATCH_SIZE):
        chunk = wanted[start:start + settings.PARSE_BATCH_SIZE]
        result = await session.execute(select(Product.barcode, Product.id).where(Product.barcode.in_(chunk)))
        product_ids.update(result.all())
    stats.unknown_barcodes = len(wanted) - len(product_ids)

    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        for code in record.barcodes:
            product_id = product_ids.get(code)
            if product_id is None or (record.promotion_id, product_id) in seen:
                continue
            seen.add((record.promotion_id, product_id))
            rows.append({
                "product_id": product_id, "store_id": store.id, "promotion_id": record.promotion_id,
                "description": record.description, "discounted_price": record.discounted_price,
                "min_qty": record.min_qty, "start_date": record.start_date, "end_date": record.end_date,
                "is_active": True,
            })

    await session.execute(delete(Promotion).where(Promotion.store_id == store.id))
    for start in range(0, len(rows), settings.PARSE_BATCH_SIZE):
        await session.execute(insert(Promotion), rows[start:start + settings.PARSE_BATCH_SIZE])
    stats.rows_inserted = len(rows)
    return stats
