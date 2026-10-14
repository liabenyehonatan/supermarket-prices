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
    """The most this promotion can save on the basket's still-free products, or None.

    The units are walked cheapest first as runs (one run per product: same price, a count), taking sets of
    min_qty. A run holding k full sets is taken in one step, so the cost grows with the number of products
    in the promotion, not with the quantities in the basket (a basket may hold 99 of each of 100 items)."""
    n = promo.min_qty
    if n < 1 or promo.price <= 0:
        return None
    runs = sorted(
        (lines[pid][0], pid, lines[pid][1])
        for pid in promo.product_ids
        if pid in lines and pid not in locked and lines[pid][1] > 0
    )
    if not runs:
        return None
    if n > 1 and promo.price <= runs[0][0] and not promo.price_is_total:
        return None                       # "N for no more than one unit": maybe a per-unit price, do not trust
    left = [units for _, _, units in runs]
    if promo.max_qty is not None:         # the cap covers the cheapest units: the smallest saving
        budget = promo.max_qty
        for i, units in enumerate(left):
            left[i] = min(units, budget)
            budget -= left[i]
    covered: dict[int, int] = {}
    saving = Decimal("0")
    sets = 0
    i = 0
    while i < len(runs):
        price, pid, _ = runs[i]
        if left[i] == 0:
            i += 1
            continue
        if left[i] >= n:                  # whole sets inside one run: all alike, taken at once
            gain = price * n - promo.price
            if gain <= 0:
                if n > 1:
                    break                 # the cheapest pairing saves nothing: a till may pair this way, claim nothing
                left[i] = 0               # one unit at a time: a unit cheaper than the price stays at shelf price
                continue
            k = left[i] // n
            saving += gain * k
            sets += k
            covered[pid] = covered.get(pid, 0) + k * n
            left[i] -= k * n
            continue
        parts: list[tuple[int, int]] = []     # fewer than n units left here: a set spanning this run and the next ones
        need, total, j = n, Decimal("0"), i
        while need and j < len(runs):
            take = min(need, left[j])
            if take:
                parts.append((j, take))
                total += runs[j][0] * take
                need -= take
            j += 1
        if need:
            break                         # not enough units left for another set
        gain = total - promo.price
        if gain <= 0:
            break                         # n > 1 here (a single unit always fits the branch above)
        saving += gain
        sets += 1
        for j, take in parts:
            left[j] -= take
            covered[runs[j][1]] = covered.get(runs[j][1], 0) + take
    return AppliedPromo(promo, sets, covered, saving) if sets else None


def price_store(lines: Mapping[int, tuple[Decimal, int]], promos: Sequence[StorePromo]) -> list[AppliedPromo]:
    """Which promotions apply to a store's basket, and what each saves. `lines`: product_id -> (shelf price, quantity)."""
    locked: set[int] = set()
    remaining = sorted(promos, key=lambda p: p.promotion_id)
    live: dict[str, AppliedPromo] = {}    # promotion_id -> what it would save now (only promotions that save)
    for promo in remaining:
        candidate = _evaluate(promo, lines, locked)
        if candidate is not None:
            live[promo.promotion_id] = candidate
    applied: list[AppliedPromo] = []
    while live:
        best = None
        for candidate in live.values():
            if (best is None or candidate.saving > best.saving
                    or (candidate.saving == best.saving and candidate.promo.promotion_id < best.promo.promotion_id)):
                best = candidate
        applied.append(best)
        newly = set(best.units)
        locked |= newly
        del live[best.promo.promotion_id]
        remaining = [p for p in remaining if p is not best.promo]
        for promo in remaining:           # only promotions that share a locked product can change
            if promo.product_ids & newly:
                candidate = _evaluate(promo, lines, locked)
                if candidate is None:
                    live.pop(promo.promotion_id, None)
                else:
                    live[promo.promotion_id] = candidate
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
