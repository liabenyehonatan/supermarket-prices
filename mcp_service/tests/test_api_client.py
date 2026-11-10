import asyncio

import httpx
import pytest

from mcp_service import config
from mcp_service.api_client import ApiClient
from mcp_service.errors import ApiBusy, ToolUserError


def client_with(handler) -> ApiClient:
    return ApiClient("http://api", transport=httpx.MockTransport(handler))


async def test_get_returns_json():
    api = client_with(lambda req: httpx.Response(200, json={"a": 1}))
    assert await api.get("/x", {"q": "חלב"}) == {"a": 1}


async def test_post_sends_json_and_params():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"], seen["query"] = req.content, req.url.query
        return httpx.Response(200, json=[])

    api = client_with(handler)
    await api.post("/p", [{"barcode": "1"}], {"limit": 3})
    assert b'"barcode"' in seen["body"] and seen["query"] == b"limit=3"


async def test_503_raises_api_busy():
    api = client_with(lambda req: httpx.Response(503, json={"detail": "busy"}))
    with pytest.raises(ApiBusy) as e:
        await api.get("/x")
    assert "עמוס" in str(e.value)


async def test_timeout_raises_api_busy():
    def handler(req):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ApiBusy):
        await client_with(handler).get("/x")


async def test_connection_error_raises_api_busy():
    def handler(req):
        raise httpx.ConnectError("down")

    with pytest.raises(ApiBusy):
        await client_with(handler).get("/x")


async def test_422_raises_tool_user_error_with_detail():
    api = client_with(lambda req: httpx.Response(422, json={"detail": "Basket cannot be empty"}))
    with pytest.raises(ToolUserError) as e:
        await api.get("/x")
    assert "Basket cannot be empty" in str(e.value) and not isinstance(e.value, ApiBusy)


async def test_at_most_4_calls_in_flight():
    running = peak = 0

    async def handler(req):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return httpx.Response(200, json={})

    api = client_with(handler)
    await asyncio.gather(*[api.get("/x") for _ in range(10)])
    assert peak == 4


async def test_waiting_for_a_free_slot_gives_up_with_api_busy(monkeypatch):
    monkeypatch.setattr(config, "SLOT_WAIT_SECONDS", 0.05)

    async def handler(req):
        await asyncio.sleep(0.4)
        return httpx.Response(200, json={})

    api = client_with(handler)
    results = await asyncio.gather(*[api.get("/x") for _ in range(6)], return_exceptions=True)
    assert sum(isinstance(r, ApiBusy) for r in results) == 2          # 4 slots; the other 2 calls shed, not queued
    assert sum(r == {} for r in results) == 4


async def test_slots_are_released_after_a_shed_call(monkeypatch):
    monkeypatch.setattr(config, "SLOT_WAIT_SECONDS", 0.05)
    api = client_with(lambda req: httpx.Response(200, json={"ok": 1}))
    for _ in range(10):                                               # more calls than slots, one after another
        assert await api.get("/x") == {"ok": 1}
