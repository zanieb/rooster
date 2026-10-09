import json
from types import SimpleNamespace

import httpx
import pytest

from rooster import _github


class GitHubAPI:
    def __init__(self):
        self.commits = []
        self.pull_requests = {}
        self.requests = []
        self.page_size = 10
        self.missing_commits = set()
        self.errors = []

    def pull_request(
        self, number, *, subject=None, labels=(), merged=True, author="author"
    ):
        node = {
            "number": number,
            "title": f"Change {number}",
            "url": f"https://github.com/owner/repo/pull/{number}",
            "author": {"login": author} if author else None,
            "labels": {"edges": [{"node": {"name": label}} for label in labels]},
            "merged": merged,
            "mergeCommit": {"message": subject or f"Change {number} (#{number})"},
        }
        self.pull_requests[number] = node
        return node

    def commit(self, message, associated=None, *, oid=None):
        oid = oid or f"{len(self.commits) + 1:040x}"
        self.commits.append(
            {
                "oid": oid,
                "message": message,
                "associatedPullRequests": {
                    "edges": [{"node": associated}] if associated else []
                },
            }
        )
        return SimpleNamespace(id=oid)

    @property
    def lookups(self):
        return [
            r["variables"]["number"]
            for r in self.requests
            if "number" in r["variables"]
        ]

    def handle(self, request):
        assert request.method == "POST"
        assert request.url == "https://api.github.com/graphql"
        payload = json.loads(request.content)
        self.requests.append(payload)
        variables = payload["variables"]
        if "number" in variables:
            node = self.pull_requests.get(variables["number"])
            response = {"data": {"repository": {"pullRequest": node}}}
            if self.errors:
                response["errors"] = self.errors
            elif node is None:
                response["errors"] = [
                    {
                        "type": "NOT_FOUND",
                        "path": ["repository", "pullRequest"],
                        "message": "Could not resolve to a PullRequest",
                    }
                ]
        elif variables["commit"] in self.missing_commits:
            response = {"data": {"repository": {"commit": None}}}
        else:
            start = int(variables["after"] or 0)
            end = start + self.page_size
            response = {
                "data": {
                    "repository": {
                        "commit": {
                            "history": {
                                "nodes": self.commits[start:end],
                                "pageInfo": {
                                    "hasNextPage": end < len(self.commits),
                                    "endCursor": str(end),
                                },
                            }
                        }
                    }
                }
            }
        return httpx.Response(200, json=response)


@pytest.fixture
def github_api(monkeypatch):
    api = GitHubAPI()
    monkeypatch.setattr(_github, "get_github_token", lambda: "test-token")
    monkeypatch.setattr(
        _github,
        "cached_graphql_client",
        lambda: httpx.Client(transport=httpx.MockTransport(api.handle)),
    )
    return api
