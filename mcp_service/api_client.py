import asyncio
from typing import Any

import httpx

from mcp_service import config
from mcp_service.errors import ApiBusy, ToolUserError


class ApiClient:
    """Calls the site's own API. At most MAX_CONCURRENT_API_CALLS requests are in flight, each with a timeout;
    "busy" answers become ApiBusy and rejected requests become ToolUserError carrying the API's explanation."""

    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=config.API_TIMEOUT_SECONDS, transport=transport,
            headers={"User-Agent": "supermarket-mcp"},
        )
        self._slots = asyncio.Semaphore(config.MAX_CONCURRENT_API_CALLS)

    async def get(self, path: str, params: dict | None = None) -> Any:
        return await self._send("GET", path, params=params)

    async def post(self, path: str, json: Any, params: dict | None = None) -> Any:
        return await self._send("POST", path, params=params, json=json)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> Any:
        try:        # under load, shed instead of queueing without bound (abandoned calls must not keep loading the API)
            await asyncio.wait_for(self._slots.acquire(), config.SLOT_WAIT_SECONDS)
        except asyncio.TimeoutError:
            raise ApiBusy() from None
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError:              # timeouts and connection failures
            raise ApiBusy() from None
        finally:
            self._slots.release()
        if response.status_code >= 500:
            raise ApiBusy()
        if response.status_code >= 400:
            raise ToolUserError(_detail(response))
        return response.json()


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    if isinstance(detail, list):             # FastAPI validation errors
        detail = "; ".join(str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail)
    return str(detail) if detail else f"הבקשה נדחתה ({response.status_code})"
