import contextlib
import json
import os

import hishel
import httpx
from httpcore import Request, Response


class GraphQLCacheController(hishel.Controller):
    def is_cachable(self, request: Request, response: Response) -> bool:
        # Allow the cache to be disabled
        if os.environ.get("ROOSTER_NO_CACHE"):
            return False

        # Since GraphQL always returns a 200, we check the response body for errors
        error_in_response_body = False
        try:
            error_in_response_body = json.loads(response.read()).get("errors")
        except Exception:
            pass  # The response cannot be parsed as JSON
        return super().is_cachable(request, response) and not error_in_response_body


@contextlib.contextmanager
def cached_graphql_client():
    """
    A HTTP client with support for caching GraphQL requests.

    The cache will be stored at `$PWD/.cache`.
    """
    with httpx.Client(
        transport=hishel.CacheTransport(
            transport=httpx.HTTPTransport(),
            controller=GraphQLCacheController(
                allow_heuristics=True, cacheable_methods=["POST"]
            ),
        ),
        timeout=None,
    ) as client:
        yield client
