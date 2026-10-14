# Pure tests of line pricing: no database.

from decimal import Decimal

from app.basket_promos import BasketPromo, price_line

D = Decimal


def promo(pid="p", n=3, price="10.00", max_qty=None, desc="3 ב-10", price_is_total=False):
    return BasketPromo(promotion_id=pid, description=desc, min_qty=n, price=D(price), max_qty=max_qty,
                       price_is_total=price_is_total)


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


def test_n_units_for_less_than_one_unit_is_read_as_a_per_unit_price_and_ignored():
    # "MinQty 2, DiscountedPrice 7.90" with a shelf price of 9.90 could mean 7.90 EACH when buying 2:
    # charging 7.90 for both would understate the basket. A real "N for X" never costs less than one unit.
    line = price_line(D("9.90"), 2, [promo(n=2, price="7.90")])
    assert line.promo is None and line.total == D("19.80")
    assert price_line(D("9.90"), 2, [promo(n=2, price="9.90")]).promo is None     # "2 for the price of 1" is skipped too (safe side)
    assert price_line(D("9.90"), 2, [promo(n=2, price="15.80")]).total == D("15.80")   # a real 2-for-15.80 still applies


def test_a_price_the_description_confirms_as_a_total_is_used_even_when_not_above_one_unit():
    # Real Shufersal case: "2ב18" on a product whose shelf price is 20.90. The description states the
    # total for N, so the per-unit reading is ruled out and the promotion applies.
    confirmed = promo(n=2, price="18.00", desc="2ב18 ספריי", price_is_total=True)
    line = price_line(D("20.90"), 3, [confirmed])
    assert line.promo is not None and line.total == D("38.90") and line.sets == 1     # 18.00 + 20.90
    assert price_line(D("20.90"), 3, [promo(n=2, price="18.00")]).promo is None         # unconfirmed: still skipped


def test_confirmation_does_not_override_a_price_that_is_dearer_than_the_shelf():
    assert price_line(D("3.00"), 3, [promo(price="12.00", price_is_total=True)]).total == D("9.00")


# ── price_store: group promotions pooled across products (Phase B2) ──────────

from app.basket_promos import StorePromo, price_store


def sp(pid="g", n=3, price="10.00", cap=None, total=True, products=(1, 2), desc="3 ב-10"):
    return StorePromo(pid, desc, n, D(price), cap, total, frozenset(products))


def test_a_group_promotion_pools_the_quantities_of_its_products():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 1)}          # 3 units: 4 + 4 + 5
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 1 and applied.saving == D("3.00") and applied.units == {1: 2, 2: 1}


def test_the_cheapest_units_are_taken_first_so_a_saving_is_never_overstated():
    lines = {1: (D("2.00"), 1), 2: (D("9.00"), 2)}          # units 2, 9, 9; a set of 2 takes the 2 and a 9
    [applied] = price_store(lines, [sp(n=2, price="10.00")])
    assert applied.saving == D("1.00") and applied.units == {1: 1, 2: 1}


def test_fewer_units_than_the_set_size_means_no_promotion():
    assert price_store({1: (D("4.00"), 1), 2: (D("5.00"), 1)}, [sp(n=3)]) == []


def test_units_left_over_after_full_sets_stay_at_shelf_price():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 3)}          # 5 units, one set of 3
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 1 and sum(applied.units.values()) == 3


def test_several_full_sets():
    lines = {1: (D("4.00"), 3), 2: (D("5.00"), 3)}          # sets [4,4,4] and [5,5,5]
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 2 and applied.saving == D("7.00")


def test_a_purchase_limit_caps_the_units_covered_across_the_group():
    [applied] = price_store({1: (D("4.00"), 4), 2: (D("5.00"), 4)}, [sp(cap=3)])
    assert applied.sets == 1


def test_a_one_unit_group_price_only_applies_to_units_dearer_than_the_price():
    lines = {1: (D("12.00"), 2), 2: (D("8.00"), 1)}
    [applied] = price_store(lines, [sp(n=1, price="10.00", desc="1 ב-10")])
    assert applied.units == {1: 2} and applied.saving == D("4.00")      # the 8.00 unit is cheaper than the price


def test_an_unconfirmed_price_at_or_below_one_unit_is_not_trusted():
    lines = {1: (D("9.90"), 2)}
    assert price_store(lines, [sp(n=2, price="7.90", total=False, products=(1,))]) == []
    assert len(price_store(lines, [sp(n=2, price="7.90", total=True, products=(1,))])) == 1


def test_nonsense_promotions_are_ignored():
    lines = {1: (D("4.00"), 3)}
    assert price_store(lines, [sp(price="0.00", products=(1,)), sp(n=0, products=(1,))]) == []


def test_a_product_is_covered_by_one_promotion_only():
    lines = {1: (D("4.00"), 4)}
    twos = sp("a", n=2, price="6.00", products=(1,), desc="2 ב-6")        # saving 2 per set, 4 in total
    fours = sp("b", n=4, price="10.00", products=(1,), desc="4 ב-10")     # saving 6
    [applied] = price_store(lines, [twos, fours])
    assert applied.promo.promotion_id == "b"


def test_the_largest_saving_wins_a_shared_product():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 2)}
    single = sp("a", n=2, price="6.00", products=(1,), desc="2 ב-6")      # saves 2
    pooled = sp("g", n=3, price="10.00", products=(1, 2))                # [4,4,5] saves 3
    [applied] = price_store(lines, [single, pooled])
    assert applied.promo.promotion_id == "g"


def test_a_promotion_on_other_products_still_applies_next_to_a_group():
    lines = {1: (D("4.00"), 3), 2: (D("5.00"), 1), 3: (D("7.00"), 2)}
    group_promo = sp("g", n=3, price="10.00", products=(1, 2))           # [4,4,4] saves 2
    other = sp("o", n=2, price="12.00", products=(3,), desc="2 ב-12")     # saves 2
    assert {a.promo.promotion_id for a in price_store(lines, [group_promo, other])} == {"g", "o"}


def test_a_tie_is_decided_by_promotion_id():
    lines = {1: (D("4.00"), 3)}
    first, second = sp("a", products=(1,)), sp("b", products=(1,))
    assert price_store(lines, [second, first])[0].promo.promotion_id == "a"
