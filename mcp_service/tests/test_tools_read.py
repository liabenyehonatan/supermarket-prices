import pytest

from mcp_service import tools
from mcp_service.errors import ApiBusy, ToolUserError

SEARCH = "/api/v1/products/search"
SUMMARY = "/api/v1/products/price-summary-batch"


def product(barcode, name, brand="תנובה", weighted=False, unit="ליטר"):
    return {"id": 1, "barcode": barcode, "name": name, "brand": brand, "image_url": "http://x/img.png",
            "unit_of_measure": unit, "is_weighted": weighted}


def summary(price, unit_price=None, unit="100 מ״ל"):
    return {"price": price, "chains": ["שופרסל"], "unit_price": unit_price, "unit": unit}


def search_api(make_api, by_query, summaries=None):
    def search(params, body):
        out = by_query[params["q"]]
        if isinstance(out, Exception):
            raise out
        return out
    return make_api({("GET", SEARCH): search, ("POST", SUMMARY): lambda p, b: summaries or {}})


async def test_search_runs_all_queries_with_one_price_call(make_api):
    api = search_api(make_api, {
        "חלב": [product("7290000000011", "חלב 3%")],
        "ביצים": [product("7290000000028", "ביצים L")],
        "לחם": [product("7290000000035", "לחם פרוס")],
    }, {"7290000000011": summary("6.5")})
    out = await tools.search_products(api, ["חלב", "ביצים", "לחם"])
    assert api.count("GET", SEARCH) == 3 and api.count("POST", SUMMARY) == 1
    assert [r["query"] for r in out["results"]] == ["חלב", "ביצים", "לחם"]
    assert out["results"][0]["products"][0]["price_from"] == 6.5


async def test_search_result_has_exactly_the_lean_fields(make_api):
    api = search_api(make_api, {"חלב": [product("7290000000011", "חלב 3%")]}, {"7290000000011": summary("6.50", "0.65")})
    p = (await tools.search_products(api, ["חלב"]))["results"][0]["products"][0]
    assert set(p) == {"barcode", "name", "brand", "price_from", "unit_price", "unit", "is_weighted"}
    assert p["price_from"] == 6.5 and p["unit_price"] == 0.65 and p["unit"] == "100 מ״ל"


async def test_search_sort_unit_price_puts_unpriced_last(make_api):
    api = search_api(make_api, {"חלב": [product("1111111111111", "א"), product("2222222222222", "ב"), product("3333333333333", "ג")]},
                     {"1111111111111": summary("9", "0.9"), "3333333333333": summary("5", "0.5")})
    names = [p["name"] for p in (await tools.search_products(api, ["חלב"], sort="unit_price"))["results"][0]["products"]]
    assert names == ["ג", "א", "ב"]


async def test_search_sort_cheapest_orders_by_price(make_api):
    api = search_api(make_api, {"חלב": [product("1111111111111", "א"), product("2222222222222", "ב")]},
                     {"1111111111111": summary("9"), "2222222222222": summary("5")})
    names = [p["name"] for p in (await tools.search_products(api, ["חלב"], sort="cheapest"))["results"][0]["products"]]
    assert names == ["ב", "א"]


async def test_one_failing_query_does_not_fail_the_others(make_api):
    api = search_api(make_api, {"חלב": ApiBusy(), "לחם": [product("7290000000035", "לחם פרוס")]})
    out = (await tools.search_products(api, ["חלב", "לחם"]))["results"]
    assert out[0]["products"] == [] and "עמוס" in out[0]["error"]
    assert out[1]["error"] is None and out[1]["products"][0]["name"] == "לחם פרוס"


async def test_price_failure_still_returns_products_with_a_warning(make_api):
    def boom(p, b):
        raise ApiBusy()
    api = make_api({("GET", SEARCH): [product("7290000000011", "חלב 3%")], ("POST", SUMMARY): boom})
    out = await tools.search_products(api, ["חלב"])
    assert out["results"][0]["products"][0]["price_from"] is None and out["warnings"]


async def test_11_queries_rejected(make_api):
    with pytest.raises(ToolUserError):
        await tools.search_products(make_api({}), [f"מוצר{i}" for i in range(11)])


async def test_query_over_100_chars_rejected(make_api):
    with pytest.raises(ToolUserError):
        await tools.search_products(make_api({}), ["א" * 101])


async def test_empty_or_blank_query_rejected(make_api):
    with pytest.raises(ToolUserError):
        await tools.search_products(make_api({}), ["  "])


async def test_limit_is_capped_at_5(make_api):
    api = search_api(make_api, {"חלב": []})
    await tools.search_products(api, ["חלב"], limit=50)
    assert api.calls[0][2]["limit"] == 5


async def test_names_are_cut_to_120(make_api):
    api = search_api(make_api, {"חלב": [product("7290000000011", "א" * 300)]})
    p = (await tools.search_products(api, ["חלב"]))["results"][0]["products"][0]
    assert len(p["name"]) == 120


async def test_get_products_reports_not_found(make_api):
    api = make_api({("POST", "/api/v1/products/by-barcodes"): [product("7290000000011", "חלב 3%")]})
    out = await tools.get_products(api, ["7290000000011", "0000000000000", "0000000000000"])
    assert out["products"] == [{"barcode": "7290000000011", "name": "חלב 3%", "brand": "תנובה", "unit": "ליטר"}]
    assert out["not_found"] == ["0000000000000"]


async def test_get_products_rejects_non_numeric_barcode(make_api):
    with pytest.raises(ToolUserError):
        await tools.get_products(make_api({}), ["abc"])


def offer(chain, city, price, promos=(), delivery="https://shop.example/x"):
    return {"store_id": 1, "store_name": "סניף", "store_city": city, "store_address": None, "chain_name": chain,
            "price": price, "unit_price": None, "price_updated_at": "2026-11-08T08:00:00", "latitude": None,
            "longitude": None, "delivery_url": delivery, "promotions": list(promos)}


def compare_api(make_api, prices):
    return make_api({
        ("GET", "/api/v1/products/7290000000011/compare"): {"product": product("7290000000011", "חלב 3%"), "prices": prices},
        ("GET", "/api/v1/chains"): [{"name": "שופרסל", "stores": 3}, {"name": "רמי לוי", "stores": 2}],
        ("GET", "/api/v1/stores/cities"): ["חיפה", "עכו"],
        ("GET", "/api/v1/stats"): {"last_updated": "2026-11-08T05:00:00Z"},
    })


async def test_prices_filtered_by_chain_and_limited_to_5(make_api):
    prices = [offer("שופרסל", "חיפה", f"{5 + i}.0") for i in range(8)] + [offer("רמי לוי", "חיפה", "9.0")]
    out = await tools.get_product_prices(compare_api(make_api, prices), "7290000000011", chain="שופרסל")
    assert len(out["offers"]) == 5 and {o["chain"] for o in out["offers"]} == {"שופרסל"}
    assert out["offers"][0]["price"] == 5.0 and out["prices_as_of"] == "2026-11-08T05:00:00Z"


async def test_prices_city_filter_and_promo_text(make_api):
    prices = [offer("שופרסל", "עכו", "5.0"),
              offer("רמי לוי", "חיפה", "6.0", [{"description": "2 ב-10", "min_qty": 2, "ends_at": None}])]
    out = await tools.get_product_prices(compare_api(make_api, prices), "7290000000011", city="חיפה")
    assert [o["city"] for o in out["offers"]] == ["חיפה"] and out["offers"][0]["promo"] == "2 ב-10"


async def test_non_http_delivery_url_is_dropped(make_api):
    out = await tools.get_product_prices(compare_api(make_api, [offer("שופרסל", "חיפה", "5", delivery="javascript:x")]), "7290000000011")
    assert out["offers"][0]["delivery_url"] is None


async def test_prices_with_no_matching_offer_say_so(make_api):
    out = await tools.get_product_prices(compare_api(make_api, [offer("שופרסל", "חיפה", "5")]), "7290000000011", chain="רמי לוי")
    assert out["offers"] == [] and out["note"]


async def test_unknown_chain_in_prices_is_an_error_not_empty(make_api):
    with pytest.raises(ToolUserError):
        await tools.get_product_prices(compare_api(make_api, []), "7290000000011", chain="שופר")


async def test_find_cities_filters_and_limits(make_api):
    api = make_api({("GET", "/api/v1/stores/cities"): ["חיפה", "חדרה", "חולון", "עכו"] + [f"חיל{i}" for i in range(20)]})
    out = await tools.find_cities(api, "ח", limit=50)
    assert len(out["cities"]) == 10 and "עכו" not in out["cities"]


async def test_list_chains_returns_names_and_counts(make_api):
    api = make_api({("GET", "/api/v1/chains"): [{"name": "שופרסל", "stores": 3}]})
    assert await tools.list_chains(api) == {"chains": [{"name": "שופרסל", "stores": 3}]}


async def test_deals_saving_pct_is_whole_percent_and_limit_capped(make_api):
    deal = {"deal_id": "d1", "brand": "תנובה", "description": "3 ב-10", "kind": "single", "min_qty": 3, "price": "10.00",
            "unit_price": "3.33", "ref_price": "4", "saving_pct": "0.25", "stores": 12, "products": 2, "ends_at": None}
    api = make_api({("GET", "/api/v1/deals"): lambda p, b: {"total": 1, "deals": [deal], "chains": [], "rules": {}}})
    out = await tools.list_deals(api, limit=99, q="חלב")
    assert out["deals"] == [{"brand": "תנובה", "description": "3 ב-10", "price": 10.0, "min_qty": 3,
                             "saving_pct": 25, "ends_at": None, "stores": 12}]
    assert api.calls[0][2]["limit"] == 10 and api.calls[0][2]["q"] == "חלב"
