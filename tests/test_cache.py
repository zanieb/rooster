import math

import httpx
import pytest
from httpcore import Request, Response

from rooster._cache import GraphQLCacheController, cached_graphql_client


@pytest.mark.parametrize(
    ("body", "cacheable"),
    [
        (b'{"data": {}}', True),
        (b'{"errors": [{"message": "Unavailable"}]}', False),
        (b"<html>Unavailable</html>", False),
        (b"[]", False),
    ],
)
def test_graphql_cache_rejects_invalid_responses(body, cacheable, monkeypatch):
    monkeypatch.delenv("ROOSTER_NO_CACHE", raising=False)
    controller = GraphQLCacheController(
        allow_heuristics=True, cacheable_methods=["POST"]
    )
    request = Request("POST", "https://api.github.com/graphql")
    response = Response(200, headers=[("cache-control", "max-age=3600")], content=body)
    response.read()
    assert controller.is_cachable(request, response) is cacheable


def test_cached_graphql_requests_retain_finite_transport_timeouts(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ROOSTER_NO_CACHE", "1")
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"data": {"viewer": {"login": "author"}}})

    monkeypatch.setattr(httpx, "HTTPTransport", lambda: httpx.MockTransport(handle))
    with cached_graphql_client() as client:
        response = client.post(
            "https://api.github.com/graphql", json={"query": "{viewer{login}}"}
        )
        assert response.status_code == 200

    timeout = requests[0].extensions["timeout"]
    assert set(timeout) == {"connect", "read", "write", "pool"}
    assert all(
        value is not None and math.isfinite(value) and value > 0
        for value in timeout.values()
    )
