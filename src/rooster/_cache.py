import contextlib
import os

import hishel
import httpx
from httpcore import Request, Response

from rooster._http import HttpClient


class GraphQLCacheController(hishel.Controller):
    def is_cachable(self, request: Request, response: Response) -> bool:
        # Allow the cache to be disabled
        if os.environ.get("ROOSTER_NO_CACHE"):
            return False

        # Since GraphQL always returns a 200, we check the response body for errors
        error_in_response_body = False
        try:
            cooked_response = httpx.Response(
                status_code=response.status,
                headers=response.headers,
                content=response.content,
            )
            error_in_response_body = cooked_response.json().get("errors")
        except Exception:
            pass  # The response cannot be parsed as JSON
        return super().is_cachable(request, response) and not error_in_response_body


@contextlib.contextmanager
def cached_graphql_client():
    """
    A HTTP client with support for caching GraphQL requests.

    The cache will be stored at `$PWD/.cache`.
    """
    with HttpClient(
        transport=hishel.CacheTransport(
            transport=httpx.HTTPTransport(),
            controller=GraphQLCacheController(
                allow_heuristics=True, cacheable_methods=["POST"]
            ),
        ),
        timeout=None,
    ) as client:
        yield client
