import json
import logging

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from starlette.testclient import TestClient

from mcp_service import server

TOOLS = {"search_products", "get_product_prices", "compare_basket", "get_products", "list_deals", "find_cities",
         "list_chains"}
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.fixture
def fake_api(make_api, monkeypatch):
    api = make_api({
        ("GET", "/api/v1/products/search"): [{"id": 1, "barcode": "7290000000011", "name": "חלב 3%", "brand": "תנובה",
                                              "image_url": None, "unit_of_measure": "ליטר", "is_weighted": False}],
        ("POST", "/api/v1/products/price-summary-batch"): {"7290000000011": {"price": "6.5", "chains": [], "unit_price": None, "unit": None}},
        ("GET", "/api/v1/chains"): [{"name": "שופרסל", "stores": 3}],
    })
    monkeypatch.setattr(server, "_api", api)
    return api


async def session_for(site_url="https://sali.example"):
    return create_connected_server_and_client_session(server.build_server(site_url)._mcp_server)


async def test_tools_list_has_exactly_the_seven_tools():
    async with await session_for() as s:
        listed = (await s.list_tools()).tools
    assert {t.name for t in listed} == TOOLS


async def test_all_tools_are_read_only_annotated():
    async with await session_for() as s:
        listed = (await s.list_tools()).tools
    assert all(t.annotations.readOnlyHint is True and t.annotations.idempotentHint is True for t in listed)


async def test_call_search_products_through_the_protocol(fake_api):
    async with await session_for() as s:
        result = await s.call_tool("search_products", {"queries": ["חלב"]})
    data = json.loads(result.content[0].text)
    assert not result.isError
    assert data["results"][0]["products"][0]["name"] == "חלב 3%" and data["results"][0]["products"][0]["price_from"] == 6.5


async def test_tool_user_error_becomes_is_error_result_not_crash(fake_api):
    async with await session_for() as s:
        result = await s.call_tool("search_products", {"queries": []})
    assert result.isError is True and "חיפוש" in result.content[0].text


async def test_server_instructions_mention_data_age_and_link():
    srv = server.build_server("https://sali.example")
    assert "prices_as_of" in srv.instructions and "open_in_site_url" in srv.instructions and "warnings" in srv.instructions


async def test_plan_shopping_prompt_is_listed():
    async with await session_for() as s:
        prompts = (await s.list_prompts()).prompts
    assert [p.name for p in prompts] == ["plan_shopping"]


async def test_tool_call_logs_one_line_without_user_text(fake_api, caplog):
    caplog.set_level(logging.INFO, logger="mcp_service.server")
    async with await session_for() as s:
        await s.call_tool("search_products", {"queries": ["חלב"]})
    lines = [r.getMessage() for r in caplog.records if r.name == "mcp_service.server"]
    assert len(lines) == 1 and "tool=search_products" in lines[0] and "duration_ms=" in lines[0]
    assert "חלב" not in lines[0]


def http_client(site_url="https://sali.example"):
    return TestClient(server.create_app(site_url), base_url="http://testserver")


def test_tools_list_works_without_prior_session_twice():
    with http_client() as c:
        for _ in range(2):
            r = c.post("/mcp", headers={**HEADERS, "Host": "sali.example"}, json=LIST)
            assert r.status_code == 200
            assert {t["name"] for t in r.json()["result"]["tools"]} == TOOLS


def test_healthz_ok():
    with http_client() as c:
        r = c.get("/healthz", headers={"Host": "mcp:8001"})
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_unknown_host_is_rejected_when_site_url_is_set():
    with http_client() as c:
        r = c.post("/mcp", headers={**HEADERS, "Host": "evil.example"}, json=LIST)
    assert r.status_code in (400, 403, 421)


def test_any_host_is_accepted_when_site_url_is_empty():
    with http_client("") as c:
        r = c.post("/mcp", headers={**HEADERS, "Host": "203.0.113.5"}, json=LIST)
    assert r.status_code == 200


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.0.0.1:8001", "mcp:8001"])
def test_internal_hosts_are_accepted_when_site_url_is_set(host):
    # deploy/deploy.sh asks /mcp from inside the nginx container, whose Host is a bare 127.0.0.1
    with http_client() as c:
        r = c.post("/mcp", headers={**HEADERS, "Host": host}, json=LIST)
    assert r.status_code == 200
