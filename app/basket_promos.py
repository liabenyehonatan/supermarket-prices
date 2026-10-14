# app/basket_promos.py
#
# Price one basket line with the best "N for X" promotion of a store (Phase B1).
#
# Deliberately conservative, so a promotion can only ever make a line cheaper than the shelf price by
# an amount the shopper can really get:
#  - one promotion per line (promotions are not mixed: "2 for 13" and "3 for 18" on 5 units is
#    priced with the better single one, repeated, never with a 2 + 3 split)
#  - a promotion that is not below the shelf price per unit is ignored
#  - a purchase limit (max_qty) caps the units that get the promotion price; the rest cost shelf price

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence


@dataclass(frozen=True)
class BasketPromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]


@dataclass(frozen=True)
class PricedLine:
    total: Decimal
    regular_total: Decimal
    promo: Optional[BasketPromo] = None
    sets: int = 0


def price_line(unit_price: Decimal, quantity: int, promos: Sequence[BasketPromo]) -> PricedLine:
    regular = unit_price * quantity
    best = PricedLine(total=regular, regular_total=regular)
    for promo in sorted(promos, key=lambda p: p.promotion_id):
        if promo.min_qty < 1 or promo.price <= 0 or promo.price >= unit_price * promo.min_qty:
            continue
        covered = quantity if promo.max_qty is None else min(quantity, promo.max_qty)
        sets = covered // promo.min_qty
        if sets == 0:
            continue
        total = sets * promo.price + (quantity - sets * promo.min_qty) * unit_price
        if total < best.total:
            best = PricedLine(total=total, regular_total=regular, promo=promo, sets=sets)
    return best
