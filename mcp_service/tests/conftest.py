import pytest

from mcp_service import filters, tools


class FakeApi:
    """Stands in for ApiClient: `routes` maps (method, path) to a value, or to a callable (params, body) -> value
    (which may raise). Every call is recorded in `calls` as (method, path, params, body)."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[tuple] = []

    async def get(self, path, params=None):
        return self._answer("GET", path, params, None)

    async def post(self, path, json, params=None):
        return self._answer("POST", path, params, json)

    def _answer(self, method, path, params, body):
        self.calls.append((method, path, params, body))
        handler = self.routes[(method, path)]
        return handler(params, body) if callable(handler) else handler

    def count(self, method, path) -> int:
        return sum(1 for c in self.calls if c[0] == method and c[1] == path)


@pytest.fixture(autouse=True)
def _fresh_caches():
    filters._reset_cache()
    tools._reset_cache()
    yield


@pytest.fixture
def make_api():
    return FakeApi
