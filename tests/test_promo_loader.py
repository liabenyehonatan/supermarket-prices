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
