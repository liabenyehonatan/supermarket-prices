from datetime import datetime, timedelta, timezone

import pytest

from mcp_service import config, tools
from mcp_service.errors import ToolUserError

COMPARE = "/api/v1/basket/compare"
B1, B2 = "7290000000011", "7290000000028"


def line(barcode, name, qty, unit_price, line_total=None, promo=None):
    total = line_total if line_total is not None else unit_price * qty
    return {"product_name": name, "barcode": barcode, "unit_price": str(unit_price), "quantity": qty,
            "line_total": str(total), "regular_line_total": str(unit_price * qty), "promo": promo}


def store(chain, city, total, lines, missing=0, promos_known=True, savings="0", delivery=None, adjustments=()):
    return {"store": {"id": 1, "store_id": "1", "name": f"{chain} {city}", "city": city, "address": None,
                      "delivery_url": delivery, "chain": {"id": 1, "name": chain, "chain_id": "1"}},
            "total_price": str(total), "items_found": len(lines), "items_missing": missing, "item_prices": lines,
            "savings": savings, "promotions_known": promos_known, "promo_adjustments": list(adjustments)}


def fresh_stamp(hours_ago=1):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def basket_api(make_api, stores, max_savings="12.5", as_of=None):
    return make_api({
        ("POST", COMPARE): {"stores": stores, "total_items_requested": 2, "cheapest_store": "x",
                            "max_savings": max_savings, "total_stores": len(stores), "max_total": "99"},
        ("GET", "/api/v1/stats"): {"last_updated": as_of or fresh_stamp()},
        ("GET", "/api/v1/chains"): [{"name": "שופרסל", "stores": 3}],
        ("GET", "/api/v1/stores/cities"): ["חיפה", "עכו"],
    })


@pytest.fixture(autouse=True)
def site(monkeypatch):
    monkeypatch.setattr(config, "SITE_URL", "https://sali.example")


GOOD = [line(B1, "חלב 3%", 2, 6), line(B2, "ביצים L", 1, 12)]


async def test_compare_builds_request_and_maps_three_stores(make_api):
    stores = [store("שופרסל", "חיפה", 24, GOOD, delivery="https://shufersal.example/o"),
              store("רמי לוי", "עכו", 25, GOOD), store("יוחננוף", "חיפה", 27, GOOD), store("עוד", "חיפה", 30, GOOD)]
    api = basket_api(make_api, stores)
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}], city="חיפה")
    method, path, params, body = next(c for c in api.calls if c[0] == "POST")
    assert params == {"limit": 3, "city": "חיפה"}
    assert body == [{"barcode": B1, "quantity": 2}, {"barcode": B2, "quantity": 1}]
    assert len(out["stores"]) == 3 and out["items_requested"] == 2 and out["max_savings"] == 12.5
    first = out["stores"][0]
    assert (first["chain"], first["city"], first["total"], first["items_missing"]) == ("שופרסל", "חיפה", 24.0, 0)
    assert first["lines"][0] == {"barcode": B1, "name": "חלב 3%", "qty": 2, "unit_price": 6.0, "line_total": 12.0, "promo": None}


async def test_duplicate_barcodes_merged_and_capped_at_99(make_api):
    api = basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 60}, {"barcode": B2, "qty": 1}, {"barcode": B1, "qty": 60}])
    assert api.calls[0][3] == [{"barcode": B1, "quantity": 99}, {"barcode": B2, "quantity": 1}]
    assert out["items_requested"] == 2 and f"{B1}:99" in out["open_in_site_url"]


async def test_41_items_rejected_with_split_message(make_api):
    items = [{"barcode": str(7290000000000 + i), "qty": 1} for i in range(41)]
    with pytest.raises(ToolUserError) as e:
        await tools.compare_basket(make_api({}), items)
    assert "40" in str(e.value) and "לשתיים" in str(e.value)


@pytest.mark.parametrize("qty", [0, 100, -1])
async def test_bad_qty_rejected(make_api, qty):
    with pytest.raises(ToolUserError):
        await tools.compare_basket(make_api({}), [{"barcode": B1, "qty": qty}])


async def test_non_numeric_barcode_rejected(make_api):
    with pytest.raises(ToolUserError):
        await tools.compare_basket(make_api({}), [{"barcode": "abc", "qty": 1}])


async def test_empty_basket_rejected(make_api):
    with pytest.raises(ToolUserError):
        await tools.compare_basket(make_api({}), [])


async def test_no_complete_basket_sets_flag_and_warning(make_api):
    api = basket_api(make_api, [store("שופרסל", "חיפה", 12, [GOOD[0]], missing=1),
                                store("רמי לוי", "עכו", 14, [GOOD[1]], missing=1)])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}])
    assert out["complete_basket_found"] is False
    assert any("אף סניף" in w for w in out["warnings"])
    assert out["stores"][0]["missing_barcodes"] == [B2]
    assert out["cheapest"]["complete"] is False


async def test_cheapest_is_complete_basket_even_if_incomplete_is_cheaper(make_api):
    api = basket_api(make_api, [store("זול חסר", "חיפה", 10, [GOOD[0]], missing=1), store("שופרסל", "חיפה", 24, GOOD)])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}])
    assert out["complete_basket_found"] is True
    assert out["cheapest"] == {"chain": "שופרסל", "city": "חיפה", "total": 24.0, "complete": True}
    assert out["stores"][0]["chain"] == "שופרסל"
    assert out["shopping_list"]["chain"] == "שופרסל"


async def test_no_link_field_when_site_url_empty(make_api, monkeypatch):
    monkeypatch.setattr(config, "SITE_URL", "")
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)]), [{"barcode": B1, "qty": 2}])
    assert "open_in_site_url" not in out


async def test_link_carries_all_items_in_request_order(make_api):
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)]),
                                     [{"barcode": B2, "qty": 1}, {"barcode": B1, "qty": 2}])
    assert out["open_in_site_url"] == f"https://sali.example/basket?items={B2}:1,{B1}:2"


async def test_promotions_unknown_warning(make_api):
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD, promos_known=False)]),
                                     [{"barcode": B1, "qty": 2}])
    assert any("מבצעים" in w and "שופרסל" in w for w in out["warnings"])


async def test_stale_data_warning_and_as_of(make_api):
    stamp = fresh_stamp(hours_ago=50)
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)], as_of=stamp),
                                     [{"barcode": B1, "qty": 2}])
    assert out["prices_as_of"] == stamp and any("שעות" in w for w in out["warnings"])


async def test_fresh_data_has_no_stale_warning(make_api):
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)]), [{"barcode": B1, "qty": 2}])
    assert not any("שעות" in w for w in out["warnings"])


async def test_shopping_list_matches_cheapest_store(make_api):
    promo_line = line(B1, "חלב 3%", 2, 6, line_total=10, promo={"description": "2 ב-10", "min_qty": 2})
    api = basket_api(make_api, [store("שופרסל", "חיפה", 22, [promo_line, GOOD[1]])])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}])
    assert out["shopping_list"] == {
        "chain": "שופרסל", "city": "חיפה", "total": 22.0, "joint_promos": [],
        "lines": [{"name": "חלב 3%", "qty": 2, "price": 10.0}, {"name": "ביצים L", "qty": 1, "price": 12.0}],
    }
    assert out["stores"][0]["lines"][0]["promo"] == "2 ב-10"


async def test_unknown_city_is_error_not_empty_result(make_api):
    api = basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD)])
    with pytest.raises(ToolUserError):
        await tools.compare_basket(api, [{"barcode": B1, "qty": 2}], city="חיפא")


async def test_no_stores_at_all_is_answered_with_a_warning(make_api):
    out = await tools.compare_basket(basket_api(make_api, []), [{"barcode": B1, "qty": 2}])
    assert out["stores"] == [] and out["complete_basket_found"] is False and out["warnings"]
    assert "shopping_list" not in out


async def test_promotions_warning_is_given_once_per_chain(make_api):
    stores = [store("שופרסל", "חיפה", 24, GOOD, promos_known=False), store("שופרסל", "עכו", 25, GOOD, promos_known=False),
              store("רמי לוי", "חיפה", 26, GOOD, promos_known=False)]
    out = await tools.compare_basket(basket_api(make_api, stores), [{"barcode": B1, "qty": 2}])
    promo_warnings = [w for w in out["warnings"] if "מבצעים" in w]
    assert len(promo_warnings) == 2 and "שופרסל" in promo_warnings[0] and "רמי לוי" in promo_warnings[1]


async def test_incomplete_baskets_rank_fewer_missing_first_like_the_site(make_api):
    api = basket_api(make_api, [store("זול חסר שניים", "חיפה", 10, [GOOD[0]], missing=2),
                                store("חסר אחד", "חיפה", 20, [GOOD[0], GOOD[1]], missing=1)])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}])
    assert [s["chain"] for s in out["stores"]] == ["חסר אחד", "זול חסר שניים"]
    assert out["cheapest"]["chain"] == "חסר אחד"


async def test_joint_promotion_is_reported_so_the_lines_add_up_to_the_total(make_api):
    joint = {"description": "2 מוצרים ב-20", "min_qty": 2, "price": "20", "sets": 1, "saving": "4.00", "ends_at": None,
             "barcodes": [B1, B2]}
    api = basket_api(make_api, [store("שופרסל", "חיפה", 20, GOOD, adjustments=[joint])])
    out = await tools.compare_basket(api, [{"barcode": B1, "qty": 2}, {"barcode": B2, "qty": 1}])
    expected = [{"description": "2 מוצרים ב-20", "saving": 4.0, "barcodes": [B1, B2]}]
    assert out["stores"][0]["joint_promos"] == expected
    assert out["shopping_list"]["joint_promos"] == expected and out["shopping_list"]["total"] == 20.0
    line_sum = sum(l["price"] for l in out["shopping_list"]["lines"])
    assert round(line_sum - 4.0, 2) == out["shopping_list"]["total"]


async def test_shopping_list_has_no_delivery_url_the_basket_answer_never_carries_one(make_api):
    out = await tools.compare_basket(basket_api(make_api, [store("שופרסל", "חיפה", 24, GOOD, delivery="https://x.example/o")]),
                                     [{"barcode": B1, "qty": 2}])
    assert "delivery_url" not in out["shopping_list"]
