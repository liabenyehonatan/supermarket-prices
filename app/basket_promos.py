# app/basket_promos.py
#
# Price a store's basket lines with its "N for X" promotions (Phase B1 single products, B2 groups).
#
# Deliberately conservative, so a promotion can only ever make a total cheaper than the shelf price by an
# amount the shopper can really get:
#  - a product is covered by at most one promotion (promotions are not mixed on a product)
#  - among promotions the one with the largest total saving goes first; ties go to the lowest promotion_id
#  - the units of a group promotion are taken cheapest first, so the saving is the smallest possible
#  - a set that saves nothing is never taken, and a purchase limit (max_qty) caps the units covered
#  - an N>1 price at or below the cheapest unit's shelf price is trusted only when the promotion's own
#    text confirmed it as the total for N (otherwise it may be a per-unit price)

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Sequence


@dataclass(frozen=True)
class BasketPromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]
    price_is_total: bool = False


@dataclass(frozen=True)
class PricedLine:
    total: Decimal
    regular_total: Decimal
    promo: Optional[BasketPromo] = None
    sets: int = 0


@dataclass(frozen=True)
class StorePromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]
    price_is_total: bool
    product_ids: frozenset[int]


@dataclass(frozen=True)
class AppliedPromo:
    promo: StorePromo
    sets: int
    units: dict[int, int]
    saving: Decimal


def _evaluate(promo: StorePromo, lines: Mapping[int, tuple[Decimal, int]], locked: set[int]) -> Optional[AppliedPromo]:
    """The most this promotion can save on the basket's still-free products, or None."""
    if promo.min_qty < 1 or promo.price <= 0:
        return None
    pool = sorted(
        (lines[pid][0], pid)
        for pid in promo.product_ids
        if pid in lines and pid not in locked
        for _ in range(lines[pid][1])
    )
    if not pool:
        return None
    if promo.min_qty > 1 and promo.price <= pool[0][0] and not promo.price_is_total:
        return None                       # "N for no more than one unit": maybe a per-unit price, do not trust
    if promo.max_qty is not None:
        pool = pool[:promo.max_qty]       # the cap covers the cheapest units: the smallest saving
    n = promo.min_qty
    covered: dict[int, int] = {}
    saving = Decimal("0")
    sets = 0
    for start in range(0, len(pool) - n + 1, n):
        window = pool[start:start + n]
        gain = sum((price for price, _ in window), Decimal("0")) - promo.price
        if gain <= 0:
            continue                      # a set that saves nothing stays at shelf price
        saving += gain
        sets += 1
        for _, pid in window:
            covered[pid] = covered.get(pid, 0) + 1
    return AppliedPromo(promo, sets, covered, saving) if sets else None


def price_store(lines: Mapping[int, tuple[Decimal, int]], promos: Sequence[StorePromo]) -> list[AppliedPromo]:
    """Which promotions apply to a store's basket, and what each saves. `lines`: product_id -> (shelf price, quantity)."""
    locked: set[int] = set()
    remaining = sorted(promos, key=lambda p: p.promotion_id)
    applied: list[AppliedPromo] = []
    while remaining:
        best: Optional[AppliedPromo] = None
        for promo in remaining:
            candidate = _evaluate(promo, lines, locked)
            if candidate is not None and (best is None or candidate.saving > best.saving):
                best = candidate
        if best is None:
            break
        applied.append(best)
        locked |= set(best.units)
        remaining = [p for p in remaining if p is not best.promo]
    return applied


def price_line(unit_price: Decimal, quantity: int, promos: Sequence[BasketPromo]) -> PricedLine:
    """One product at one store (Phase B1): the single-product case of price_store."""
    regular = unit_price * quantity
    wrapped = [
        StorePromo(p.promotion_id, p.description, p.min_qty, p.price, p.max_qty, p.price_is_total, frozenset({0}))
        for p in promos
    ]
    applied = price_store({0: (unit_price, quantity)}, wrapped)
    if not applied:
        return PricedLine(total=regular, regular_total=regular)
    best = applied[0]
    original = next(p for p, w in zip(promos, wrapped) if w is best.promo)
    return PricedLine(total=regular - best.saving, regular_total=regular, promo=original, sets=best.sets)
