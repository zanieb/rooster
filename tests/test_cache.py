import pytest
from httpcore import Request, Response

from rooster._cache import GraphQLCacheController


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
