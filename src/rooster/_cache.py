import os
from email.utils import formatdate, mktime_tz, parsedate_tz
from hashlib import sha256

import hishel
import httpx2
from hishel.httpx2 import SyncCacheTransport

from rooster._http import HttpClient


class GraphQLTransport(httpx2.BaseTransport):
    def __init__(self) -> None:
        self.transport = httpx2.HTTPTransport()
        self.storage = hishel.SyncSqliteStorage()
        self.policy = hishel.SpecificationPolicy(hishel.CacheOptions(shared=False))

    def handle_request(self, request: httpx2.Request) -> httpx2.Response:
        if request.method != "POST":
            return self.transport.handle_request(request)

        # GitHub requires POST for read-only GraphQL queries. Give each query a
        # GET cache key so Hishel can reuse and revalidate its response. Scope it
        # to the credential without writing the bearer token to the cache.
        headers = httpx2.Headers(request.headers)
        authorization = headers.pop("Authorization", "")
        key = sha256(authorization.encode() + b"\0" + request.read()).hexdigest()
        lookup = httpx2.Request(
            "GET", request.url.copy_add_param("query", key), headers=headers
        )

        def fetch(lookup: httpx2.Request) -> httpx2.Response:
            headers = httpx2.Headers(lookup.headers)
            if authorization:
                headers["Authorization"] = authorization
            response = self.transport.handle_request(
                httpx2.Request(
                    request.method,
                    request.url,
                    headers=headers,
                    content=request.content,
                    extensions=request.extensions,
                )
            )
            _set_cache_headers(response)
            return response

        cache = SyncCacheTransport(
            httpx2.MockTransport(fetch), storage=self.storage, policy=self.policy
        )
        return cache.handle_request(lookup)

    def close(self) -> None:
        try:
            self.storage.close()
        finally:
            self.transport.close()


def _set_cache_headers(response: httpx2.Response) -> None:
    if response.status_code in (301, 304, 308):
        return
    if response.status_code == 200:
        try:
            response.read()
        finally:
            response.close()
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and not payload.get("errors"):
            # Keep a one-day freshness lifetime when GitHub supplies neither an
            # expiry nor a Last-Modified date for Hishel to use as a heuristic.
            if (
                "expires" not in response.headers
                and "last-modified" not in response.headers
            ):
                date = parsedate_tz(response.headers.get("Date", ""))
                if date is not None:
                    response.headers["Expires"] = formatdate(
                        mktime_tz(date) + 86400, usegmt=True
                    )
            return

    # GitHub also returns a 200 status for GraphQL errors.
    response.headers["Cache-Control"] = "no-store"


def cached_graphql_client() -> HttpClient:
    """Return an HTTP client that caches GraphQL requests in `$PWD/.cache`."""
    transport = (
        httpx2.HTTPTransport()
        if os.environ.get("ROOSTER_NO_CACHE")
        else GraphQLTransport()
    )
    return HttpClient(transport=transport, timeout=None)
