# Pure tests of line pricing: no database.

from decimal import Decimal

from app.basket_promos import BasketPromo, price_line

D = Decimal


def promo(pid="p", n=3, price="10.00", max_qty=None, desc="3 ב-10"):
    return BasketPromo(promotion_id=pid, description=desc, min_qty=n, price=D(price), max_qty=max_qty)


def test_no_promotions_is_the_shelf_price():
    line = price_line(D("4.00"), 3, [])
    assert (line.total, line.regular_total, line.promo, line.sets) == (D("12.00"), D("12.00"), None, 0)


def test_a_full_set_uses_the_promotion():
    line = price_line(D("4.00"), 3, [promo()])
    assert line.total == D("10.00") and line.regular_total == D("12.00")
    assert line.promo.promotion_id == "p" and line.sets == 1


def test_the_remainder_after_full_sets_is_at_shelf_price():
    line = price_line(D("4.00"), 7, [promo()])          # two sets of 3, one left over
    assert line.total == D("24.00") and line.sets == 2


def test_below_the_minimum_quantity_nothing_applies():
    line = price_line(D("4.00"), 2, [promo()])
    assert line.total == D("8.00") and line.promo is None


def test_the_best_of_several_tiers_wins_without_mixing_them():
    tiers = [promo("a", 2, "13.00", desc="2 ב-13"), promo("b", 3, "18.00", desc="3 ב-18"), promo("c", 4, "20.00", desc="4 ב-20")]
    line = price_line(D("7.90"), 5, tiers)
    assert line.promo.promotion_id == "c"
    assert line.total == D("27.90")                      # 4 for 20.00 plus one at 7.90


def test_a_purchase_limit_caps_the_units_that_get_the_promotion():
    line = price_line(D("14.00"), 5, [promo("s", 1, "10.90", max_qty=3, desc="1 ב-10.90")])
    assert line.total == D("60.70") and line.sets == 3   # 3 x 10.90 + 2 x 14.00


def test_a_limit_below_the_set_size_means_no_promotion():
    line = price_line(D("4.00"), 6, [promo(n=3, max_qty=2)])
    assert line.total == D("24.00") and line.promo is None


def test_a_plain_sale_price_is_a_set_of_one():
    line = price_line(D("12.90"), 4, [promo(n=1, price="10.90", desc="1 ב-10.90")])
    assert line.total == D("43.60")


def test_a_promotion_that_is_not_cheaper_per_unit_is_ignored():
    assert price_line(D("3.00"), 3, [promo(price="9.00")]).promo is None     # same as shelf
    assert price_line(D("3.00"), 3, [promo(price="12.00")]).total == D("9.00")  # dearer than shelf


def test_nonsense_promotions_are_ignored():
    for bad in (promo(price="0.00"), promo(n=0)):
        assert price_line(D("4.00"), 3, [bad]).total == D("12.00")


def test_a_tie_between_promotions_is_decided_by_promotion_id():
    twins = [promo("b", desc="second"), promo("a", desc="first")]
    assert price_line(D("4.00"), 3, twins).promo.description == "first"
