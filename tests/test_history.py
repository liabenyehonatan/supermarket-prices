from datetime import date, datetime
from decimal import Decimal as D

from app.history import build_cheapest_history

TODAY = date(2026, 10, 8)
SINCE = date(2026, 7, 10)


def dt(y, m, d):
    return datetime(y, m, d, 12, 0)


def test_single_unchanged_price_gives_flat_series():
    pts = build_cheapest_history([(1, dt(2008, 1, 1), D("5.00"))], SINCE, TODAY)
    assert pts == [(SINCE, D("5.00")), (TODAY, D("5.00"))]


def test_cheapest_store_change_creates_point():
    rows = [
        (1, dt(2026, 1, 1), D("5.00")),
        (2, dt(2026, 1, 1), D("6.00")),
        (2, dt(2026, 9, 1), D("4.00")),   # store 2 drops below store 1
    ]
    pts = build_cheapest_history(rows, SINCE, TODAY)
    assert pts == [(SINCE, D("5.00")), (date(2026, 9, 1), D("4.00")), (TODAY, D("4.00"))]


def test_change_in_non_cheapest_store_adds_no_point():
    rows = [
        (1, dt(2026, 1, 1), D("5.00")),
        (2, dt(2026, 1, 1), D("6.00")),
        (2, dt(2026, 9, 1), D("7.00")),
    ]
    pts = build_cheapest_history(rows, SINCE, TODAY)
    assert pts == [(SINCE, D("5.00")), (TODAY, D("5.00"))]


def test_price_rise_at_cheapest_store_falls_back_to_next():
    rows = [
        (1, dt(2026, 1, 1), D("3.00")),
        (1, dt(2026, 8, 1), D("8.00")),
        (2, dt(2026, 1, 1), D("6.00")),
    ]
    pts = build_cheapest_history(rows, SINCE, TODAY)
    assert pts == [(SINCE, D("3.00")), (date(2026, 8, 1), D("6.00")), (TODAY, D("6.00"))]


def test_no_rows():
    assert build_cheapest_history([], SINCE, TODAY) == []
