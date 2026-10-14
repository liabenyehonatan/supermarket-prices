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
    ids: set[str] = set()
    single = _text(row, "clubid")
    if single:
        ids.add(single)
    clubs = row.get("clubs")
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

    barcodes: list[str] = []
    for item in items:
        code = _clean_text(_text(item, "itemcode"), 20)
        if code and code not in barcodes:
            barcodes.append(code)
    if not barcodes or len(barcodes) > MAX_ITEMS_PER_PROMOTION:
        return None

    end = _when(row, "promotionenddatetime", "promotionenddate", "promotionendhour", end=True)
    if end is not None and end < as_of:
        return None

    first = items[0] if items else {}
    price = _money(_text(row, "discountedprice") or _text(first, "discountedprice"))
    return PromoRecord(
        promotion_id=promotion_id,
        description=description,
        discounted_price=price if price and price > 0 else None,
        min_qty=_min_qty(_text(row, "minqty") or _text(first, "minqty")),
        start_date=_when(row, "promotionstartdatetime", "promotionstartdate", "promotionstarthour", end=False),
        end_date=end,
        barcodes=barcodes,
    )
