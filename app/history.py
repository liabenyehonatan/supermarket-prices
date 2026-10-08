# app/history.py
"""Cheapest-price history for one product, built from the `prices` rows.

Each (store, price row) is valid from its price_updated_at until the same store's
next row starts. The cheapest price on a given day is the minimum across stores of
the row valid that day. We only emit a point when that minimum changes.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable


def build_cheapest_history(
    rows: Iterable[tuple[int, datetime, Decimal]],
    since: date,
    today: date,
) -> list[tuple[date, Decimal]]:
    """rows: (store_id, price_updated_at, price). Returns [(date, cheapest_price), ...]."""
    per_store: dict[int, list[tuple[date, Decimal]]] = {}
    for store_id, updated_at, price in rows:
        per_store.setdefault(store_id, []).append((updated_at.date(), price))

    # Per-store change events. A row that started before the window counts as
    # starting at the window start (its price is what was in force then).
    events: list[tuple[date, int, Decimal]] = []
    for store_id, items in per_store.items():
        items.sort(key=lambda it: it[0])
        in_window = [it for it in items if it[0] > since]
        before = [it for it in items if it[0] <= since]
        if before:
            events.append((since, store_id, before[-1][1]))
        for day, price in in_window:
            if day <= today:
                events.append((day, store_id, price))

    events.sort(key=lambda e: e[0])
    current: dict[int, Decimal] = {}
    points: list[tuple[date, Decimal]] = []
    i = 0
    while i < len(events):
        day = events[i][0]
        while i < len(events) and events[i][0] == day:
            _, store_id, price = events[i]
            current[store_id] = price
            i += 1
        cheapest = min(current.values())
        if not points or points[-1][1] != cheapest:
            points.append((day, cheapest))

    # Close the series at today so the line extends to the present
    if points and points[-1][0] < today:
        points.append((today, points[-1][1]))
    return points
