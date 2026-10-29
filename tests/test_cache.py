import json
from email.utils import formatdate

import httpx2
import pytest

from rooster import _github
from rooster._cache import cached_graphql_client


def test_cached_graphql_queries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ROOSTER_NO_CACHE", raising=False)
    token = "test-token"
    monkeypatch.setattr(_github, "get_github_token", lambda: token)
    requests = []

    def respond(self, request):
        assert request.method == "POST"
        assert request.url == "https://api.github.com/graphql"
        assert request.headers["Authorization"] == f"Bearer {token}"
        number = json.loads(request.read())["variables"]["number"]
        requests.append(number)
        if len(requests) == 1:
            body = {"errors": [{"message": "Try again"}]}
        else:
            body = {"data": {"number": number}}
        return httpx2.Response(
            200, json=body, headers={"Date": formatdate(usegmt=True)}
        )

    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", respond)

    def query(number):
        with cached_graphql_client() as client:
            return _github._graphql(
                client,
                'query($number: Int!) { repository(owner: "owner", name: "repo") '
                "{ issue(number: $number) { number } } }",
                {"number": number},
            )

    with pytest.raises(_github.GitHubGraphQLError):
        query(1)
    assert query(1) == {"data": {"number": 1}}
    assert query(2) == {"data": {"number": 2}}
    assert query(1) == {"data": {"number": 1}}
    assert requests == [1, 1, 2]

    token = "second-test-token"
    assert query(1) == {"data": {"number": 1}}
    assert requests == [1, 1, 2, 1]

    monkeypatch.setenv("ROOSTER_NO_CACHE", "1")
    assert query(1) == {"data": {"number": 1}}
    assert requests == [1, 1, 2, 1, 1]
