import pytest

from mcp_service import filters
from mcp_service.errors import ToolUserError

CITIES = ["תל אביב - יפו", "חיפה", "חדרה", "123", "הרצליה"]
CHAINS = [{"name": "שופרסל", "stores": 300}, {"name": "רמי לוי", "stores": 200}]


def api_with(make_api):
    return make_api({("GET", "/api/v1/stores/cities"): CITIES, ("GET", "/api/v1/chains"): CHAINS})


async def test_city_matching_by_substring_passes(make_api):
    assert await filters.validate_city(api_with(make_api), " חיפ ") == "חיפ"


async def test_unknown_city_error_lists_close_candidates(make_api):
    with pytest.raises(ToolUserError) as e:
        await filters.validate_city(api_with(make_api), "חיפא")
    assert "חיפה" in str(e.value)


async def test_unknown_city_with_nothing_close_still_explains(make_api):
    with pytest.raises(ToolUserError) as e:
        await filters.validate_city(api_with(make_api), "zzzzzz")
    assert "find_cities" in str(e.value)


async def test_chain_is_matched_exactly_and_returned_canonical(make_api):
    assert await filters.validate_chain(api_with(make_api), "שופרסל") == "שופרסל"


async def test_unknown_chain_lists_all_valid_names(make_api):
    with pytest.raises(ToolUserError) as e:
        await filters.validate_chain(api_with(make_api), "שופר")
    assert "שופרסל" in str(e.value) and "רמי לוי" in str(e.value)


async def test_cities_list_is_cached_and_numeric_names_dropped(make_api):
    api = api_with(make_api)
    first = await filters.get_cities(api)
    await filters.get_cities(api)
    assert "123" not in first and api.count("GET", "/api/v1/stores/cities") == 1
