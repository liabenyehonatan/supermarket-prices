# Pure tests of the promotion filter. Row shapes are the ones il_supermarket_parsers really yields
# (lowercase keys; nested single elements come as dicts, repeated ones as lists).

from datetime import datetime
from decimal import Decimal

import pytest

from app.parser.promo_loader import normalize_promotion

AS_OF = datetime(2026, 5, 12, 6, 0)


def row(**over):
    base = {
        "promotionid": "1", "promotiondescription": "2 ב-18",
        "promotionstartdate": "2026-05-01", "promotionstarthour": "00:00:00",
        "promotionenddate": "2026-12-31", "promotionendhour": "23:59:00",
        "rewardtype": "1", "minqty": "2.00", "discountedprice": "18.00",
        "clubs": {"clubid": "0"},
        "promotionitems": {"item": [{"itemcode": "111"}, {"itemcode": "222"}]},
    }
    base.update(over)
    return base


def test_keeps_a_plain_quantity_promotion():
    rec = normalize_promotion(row(), as_of=AS_OF)
    assert rec.promotion_id == "1" and rec.description == "2 ב-18"
    assert rec.min_qty == 2 and rec.discounted_price == Decimal("18.00")
    assert rec.start_date == datetime(2026, 5, 1, 0, 0) and rec.end_date == datetime(2026, 12, 31, 23, 59)
    assert rec.barcodes == ["111", "222"]


def test_a_single_item_arrives_as_a_dict_not_a_list():
    rec = normalize_promotion(row(promotionitems={"item": {"itemcode": "111"}}), as_of=AS_OF)
    assert rec.barcodes == ["111"]


def test_group_layout_with_item_level_reward_and_millisecond_dates():
    victory = {
        "promotionid": "250678", "promotiondescription": "19.90 יין",
        "promotionstartdatetime": "2026-05-04T00:00:00.000", "promotionenddatetime": "2026-05-30T00:00:00.000",
        "clubid": "0", "additionaliscoupon": "0",
        "groups": {"group": {"groupid": "1", "promotionitems": {"promotionitem": {
            "itemcode": "7290006696595", "rewardtype": "3", "minqty": "1", "discountedprice": "19.9"}}}},
    }
    rec = normalize_promotion(victory, as_of=AS_OF)
    assert rec.barcodes == ["7290006696595"] and rec.min_qty == 1
    assert rec.discounted_price == Decimal("19.90")
    assert rec.end_date == datetime(2026, 5, 30, 0, 0)


def test_date_only_end_means_end_of_that_day():
    rec = normalize_promotion(row(promotionendhour=""), as_of=AS_OF)
    assert rec.end_date == datetime(2026, 12, 31, 23, 59, 59)


def test_duplicate_barcodes_collapse_keeping_order():
    items = {"item": [{"itemcode": "222"}, {"itemcode": "111"}, {"itemcode": "222"}]}
    assert normalize_promotion(row(promotionitems=items), as_of=AS_OF).barcodes == ["222", "111"]


def test_fractional_min_qty_is_kept_without_a_quantity():
    assert normalize_promotion(row(minqty="0.50"), as_of=AS_OF).min_qty is None


@pytest.mark.parametrize("over", [
    {"promotiondescription": "מבוטל"},
    {"promotiondescription": "קופון חטיפים ב 25 שח"},
    {"promotiondescription": "ניסיון- קופון אחוד /חצי ליטר מים ב1"},      # a coupon whose word is not first
    {"promotiondescription": "נסיון מבצע מים ב1"},                          # the same word spelled without the yod
    {"promotiondescription": "ניסיון מבצע מים ב1"},                        # a chain's test promotion
    {"promotiondescription": ""},
    {"promotionid": ""},
    {"clubs": {"clubid": ["1", "2"]}},
    {"clubs": None, "clubid": "1"},
    {"additionaliscoupon": "1"},
    {"additionalrestrictions": {"additionaliscoupon": "1"}},
    {"rewardtype": "6"},
    {"rewardtype": "7"},
    {"promotionenddate": "2026-05-11"},
    {"promotionitems": {"item": []}},
    {"promotionitems": None},
    {"promotionitems": {"item": [{"itemcode": str(i)} for i in range(101)]}},
])
def test_everything_we_cannot_show_honestly_is_dropped(over):
    assert normalize_promotion(row(**over), as_of=AS_OF) is None


def test_a_hundred_items_is_still_fine():
    items = {"item": [{"itemcode": str(i)} for i in range(100)]}
    assert len(normalize_promotion(row(promotionitems=items), as_of=AS_OF).barcodes) == 100


# ── replace_store_promotions (needs the test database) ────────────────────────

from sqlalchemy import select

from app.db.models import Product, Promotion
from app.parser.promo_loader import PromoRecord, replace_store_promotions


def rec(pid, barcodes, desc="2 ב-18", **over):
    base = dict(promotion_id=pid, description=desc, discounted_price=Decimal("18.00"), min_qty=2,
                start_date=None, end_date=None, barcodes=barcodes)
    base.update(over)
    return PromoRecord(**base)


async def stored(session):
    rows = await session.execute(
        select(Promotion.promotion_id, Product.barcode, Promotion.description)
        .join(Product, Promotion.product_id == Product.id)
        .order_by(Promotion.promotion_id, Product.barcode)
    )
    return rows.all()


async def test_writes_one_row_per_product_and_skips_unknown_barcodes(session, store):
    session.add_all([Product(barcode="111", name="a"), Product(barcode="222", name="b")])
    await session.commit()

    stats = await replace_store_promotions(session, store, [rec("p1", ["111", "222", "999"])])
    await session.commit()

    assert await stored(session) == [("p1", "111", "2 ב-18"), ("p1", "222", "2 ב-18")]
    assert (stats.promotions, stats.rows_inserted, stats.unknown_barcodes) == (1, 2, 1)
    assert (await session.execute(select(Product).where(Product.barcode == "999"))).first() is None


async def test_a_newer_file_replaces_the_stores_old_promotions(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()
    await replace_store_promotions(session, store, [rec("old", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [rec("new", ["111"], desc="3 ב-10")])
    await session.commit()

    assert await stored(session) == [("new", "111", "3 ב-10")]


async def test_a_file_with_no_promotions_clears_the_store(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()
    await replace_store_promotions(session, store, [rec("old", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [])
    await session.commit()

    assert await stored(session) == []


async def test_the_same_promotion_listed_twice_does_not_break_the_load(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()

    await replace_store_promotions(session, store, [rec("p1", ["111"]), rec("p1", ["111"], desc="again")])
    await session.commit()

    assert await stored(session) == [("p1", "111", "2 ב-18")]   # the first one wins


async def test_other_stores_keep_their_promotions(session, store):
    from app.db.models import Store
    other = Store(chain_id=store.chain_id, store_id="002", name="Other")
    session.add_all([other, Product(barcode="111", name="a")])
    await session.commit()
    await replace_store_promotions(session, other, [rec("keep", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [rec("mine", ["111"])])
    await session.commit()

    assert [p for p, _, _ in await stored(session)] == ["keep", "mine"]


# ── review fixes ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("restrictions", [
    {"additionaliscoupon": "0", "clubs": {"clubid": "1"}},                    # KingStore / Netiv Hased layout
    {"additionaliscoupon": "0", "clubs": {"clubid": ["0", "2"]}},
    {"additionaliscoupon": "0", "clubid": "1"},
])
def test_a_club_audience_nested_under_additional_restrictions_is_dropped(restrictions):
    assert normalize_promotion(row(clubs=None, additionalrestrictions=restrictions), as_of=AS_OF) is None


def test_nested_club_zero_is_still_for_everybody():
    nested = {"additionaliscoupon": "0", "clubs": {"clubid": "0"}}
    assert normalize_promotion(row(clubs=None, additionalrestrictions=nested), as_of=AS_OF) is not None


def test_a_club_wide_promotion_with_tens_of_thousands_of_items_is_rejected_quickly():
    # Shufersal lists member-wide promotions with ~48,000 items per store file; checking each barcode
    # against a growing list made the filter quadratic (seconds per file, about 45 minutes per cycle).
    import time
    items = {"item": [{"itemcode": str(i)} for i in range(20000)]}
    started = time.perf_counter()
    assert normalize_promotion(row(promotionitems=items), as_of=AS_OF) is None
    assert time.perf_counter() - started < 0.5


# ── basket eligibility (Phase B1) ─────────────────────────────────────────────

def single(**over):
    """A Rami-Levy-shaped '3 for 10' on one product."""
    base = dict(promotionitems={"item": [{"itemcode": "111"}]}, minqty="3.00", discountedprice="10.00")
    base.update(over)
    return row(**base)


def test_a_single_product_n_for_x_is_basket_eligible():
    rec = normalize_promotion(single(), as_of=AS_OF)
    assert rec.basket_eligible is True and rec.max_qty is None


def test_reward_ten_on_one_product_is_eligible_too():
    assert normalize_promotion(single(rewardtype="10"), as_of=AS_OF).basket_eligible is True


def test_item_level_layout_is_eligible():
    victory = {
        "promotionid": "9", "promotiondescription": "2ב15 ביסקוויט",
        "promotionstartdatetime": "2026-05-04T00:00:00.000", "promotionenddatetime": "2026-12-30T00:00:00.000",
        "clubid": "0", "additionaliscoupon": "0", "redemptionlimit": "",
        "groups": {"group": {"groupid": "1", "promotionitems": {"promotionitem": {
            "itemcode": "7290001", "rewardtype": "10", "minqty": "2", "maxqty": "NO_BODY",
            "discountedprice": "15", "bisweighted": "0"}}}},
    }
    rec = normalize_promotion(victory, as_of=AS_OF)
    assert rec.basket_eligible is True and rec.min_qty == 2 and rec.max_qty is None


@pytest.mark.parametrize("over", [
    {"rewardtype": "3"},                                   # meaning not verified
    {"rewardtype": "2"},                                   # percent: no total price
    {"isweightedpromo": "1"},
    {"isgiftitem": "1"},
    {"redemptionlimit": "2"},
    {"discountedprice": ""},
    {"minqty": "0.50"},                                    # fractional: no whole set
])
def test_what_is_not_a_plain_n_for_x_is_not_eligible(over):
    rec = normalize_promotion(single(**over), as_of=AS_OF)
    assert rec is None or rec.basket_eligible is False


def test_two_products_are_eligible_only_with_a_confirmed_price():
    unconfirmed = normalize_promotion(row(promotiondescription="מבצע"), as_of=AS_OF)   # the default row lists two items
    assert unconfirmed is not None and unconfirmed.basket_eligible is False
    confirmed = normalize_promotion(row(), as_of=AS_OF)                              # description "2 ב-18", MinQty 2, price 18
    assert confirmed.basket_eligible is True


def test_a_weighted_item_is_not_eligible():
    items = {"item": [{"itemcode": "111", "bisweighted": "1"}]}
    assert normalize_promotion(single(promotionitems=items), as_of=AS_OF).basket_eligible is False


@pytest.mark.parametrize("raw, expected", [("5", 5), ("5.00", 5), ("0", None), ("NO_BODY", None), ("", None)])
def test_the_purchase_limit_is_read_as_a_positive_integer(raw, expected):
    assert normalize_promotion(single(maxqty=raw), as_of=AS_OF).max_qty == expected


def test_the_item_level_purchase_limit_is_used_when_the_promotion_has_none():
    items = {"item": [{"itemcode": "111", "maxqty": "10"}]}
    assert normalize_promotion(single(promotionitems=items), as_of=AS_OF).max_qty == 10


def test_a_limit_below_the_set_size_makes_it_not_eligible():
    assert normalize_promotion(single(maxqty="2"), as_of=AS_OF).basket_eligible is False


async def test_the_eligibility_and_the_limit_are_stored(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()

    await replace_store_promotions(session, store, [rec("p1", ["111"], basket_eligible=True, max_qty=5)])
    await session.commit()

    row = (await session.execute(select(Promotion.basket_eligible, Promotion.max_qty))).one()
    assert (row.basket_eligible, row.max_qty) == (True, 5)


# ── club ids written as "<number> - <name>" (Shufersal and Tiv Taam, May 2026 files) ──

def test_a_club_id_with_a_label_still_means_everybody_when_the_number_is_zero():
    rec = normalize_promotion(row(clubs=None, clubid="0 - כלל הלקוחות"), as_of=AS_OF)
    assert rec is not None


def test_a_labelled_club_id_with_another_number_is_still_a_club_promotion():
    assert normalize_promotion(row(clubs=None, clubid="3 - מועדון לקוחות & עמותת לשובע-אשראי"), as_of=AS_OF) is None
    assert normalize_promotion(row(clubs={"clubid": ["0 - כלל הלקוחות", "1 - מועדון"]}), as_of=AS_OF) is None


def test_a_labelled_zero_nested_under_additional_restrictions_is_everybody():
    nested = {"additionaliscoupon": "0", "clubs": {"clubid": "0 - כלל הלקוחות"}}
    assert normalize_promotion(row(clubs=None, additionalrestrictions=nested), as_of=AS_OF) is not None


# ── the description confirms that the price is the total for N ────────────────

@pytest.mark.parametrize("description, minqty, price, expected", [
    ("2ב18 ספריי לניקוי חלונות 750 מ\"ל", "2.00", "18.00", True),
    ("בועות סבון 12 ב 10.90 ש\"ח", "12.00", "10.90", True),
    ("גרעיני חמניה 150 גרם 3ב-10", "3.00", "10.00", True),
    ("2ב31.40 פקדון בירה", "2.00", "32.00", False),                 # the number differs (deposit): stay safe
    ("מבצע 2ב18", "2.00", "17.00", False),
    ("מבצע 3ב18", "2.00", "18.00", False),                          # N differs
    ("ספריי לניקוי חלונות", "2.00", "18.00", False),                # no "N ב-X" in the text
])
def test_the_description_confirms_the_price_is_the_total_for_n(description, minqty, price, expected):
    rec = normalize_promotion(single(promotiondescription=description, minqty=minqty, discountedprice=price), as_of=AS_OF)
    assert rec.price_is_total is expected


async def test_price_is_total_is_stored(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()

    await replace_store_promotions(session, store, [rec("p1", ["111"], price_is_total=True)])
    await session.commit()

    assert (await session.execute(select(Promotion.price_is_total))).scalar_one() is True


# ── group promotions (Phase B2) ───────────────────────────────────────────────

def group(**over):
    """A Rami-Levy-shaped '3 for 10' on four products, text confirms the price."""
    base = dict(
        promotiondescription="פטרוזליה/כוסברה/שמיר/נענע 3ב10", minqty="3.00", discountedprice="10.00",
        promotionitems={"item": [{"itemcode": c} for c in ("111", "222", "333", "444")]},
    )
    base.update(over)
    return row(**base)


def test_a_group_promotion_whose_text_confirms_the_price_is_eligible():
    rec = normalize_promotion(group(), as_of=AS_OF)
    assert rec.basket_eligible is True and rec.price_is_total is True and len(rec.barcodes) == 4


def test_a_group_promotion_whose_text_does_not_confirm_the_price_is_not_eligible():
    rec = normalize_promotion(group(promotiondescription="מבצע ירקות"), as_of=AS_OF)
    assert rec is not None and rec.basket_eligible is False


@pytest.mark.parametrize("over", [
    {"promotionitems": {"item": [{"itemcode": "1", "discountedprice": "10"}, {"itemcode": "2", "discountedprice": "12"}]}},
    {"isweightedpromo": "1"},
    {"isgiftitem": "1"},
    {"redemptionlimit": "2"},
    {"rewardtype": "3"},
    {"maxqty": "2"},                                          # below the set size of 3
])
def test_group_promotions_with_anything_unsafe_are_not_eligible(over):
    rec = normalize_promotion(group(**over), as_of=AS_OF)
    assert rec is None or rec.basket_eligible is False


def test_a_promotion_spread_over_several_groups_is_never_pooled():
    two_groups = {"group": [
        {"groupid": "1", "promotionitems": {"promotionitem": {"itemcode": "111"}}},
        {"groupid": "2", "promotionitems": {"promotionitem": {"itemcode": "222"}}},
    ]}
    rec = normalize_promotion(group(promotionitems=None, groups=two_groups), as_of=AS_OF)
    assert rec is not None and rec.basket_eligible is False


def test_a_single_group_in_the_group_layout_is_pooled():
    one_group = {"group": {"groupid": "1", "promotionitems": {"promotionitem": [
        {"itemcode": "111"}, {"itemcode": "222"}]}}}
    rec = normalize_promotion(group(promotionitems=None, groups=one_group), as_of=AS_OF)
    assert rec.basket_eligible is True


def test_a_one_unit_sale_price_for_a_group_needs_the_text_to_show_that_price():
    ok = normalize_promotion(group(promotiondescription="פסטה/ריגטי-ב12.90", minqty="1", discountedprice="12.90"), as_of=AS_OF)
    assert ok.basket_eligible is True
    percent = normalize_promotion(group(promotiondescription="בי 40% הנחה לוריאל", minqty="1", discountedprice="36.90"), as_of=AS_OF)
    assert percent.basket_eligible is False
    unlabelled = normalize_promotion(group(promotiondescription="יין לבן ברקן", minqty="1", discountedprice="34.90"), as_of=AS_OF)
    assert unlabelled.basket_eligible is False


@pytest.mark.parametrize("description, minqty, price, expected", [
    ("מבצע שלגון תמרה 2 יח ב 20 שח", "2.00", "20.00", True),
    ("מנה חמה נודלס 3 יח' ב 24 שח", "3.00", "24.00", True),
    ("נוזל רצפות אולטרה ב10", "1.00", "10.00", True),
    ("פסטה פטוצ'יני-ב12.90", "1.00", "12.90", True),
    ("נוזל רצפות ב10", "2.00", "10.00", False),            # a bare "ב10" confirms nothing when N is 2
    ("בי 40% הנחה לוריאל", "1.00", "36.90", False),
    ("יין לבן ברקן 750 מ\"ל", "1.00", "34.90", False),
])
def test_more_wordings_of_the_total_are_recognised(description, minqty, price, expected):
    rec = normalize_promotion(single(promotiondescription=description, minqty=minqty, discountedprice=price), as_of=AS_OF)
    assert rec.price_is_total is expected
