import contextlib
import hashlib
import json

import hishel
import httpx
from httpcore import Request, Response


class GraphQLCacheController(hishel.Controller):
    def __init__(self):
        super().__init__(allow_heuristics=True)
        # Hack support for POST requests as hishel does not allow caching of them
        self._cacheable_methods = ["POST"]

    def is_cachable(self, request: Request, response: Response) -> bool:
        # Since GraphQL always returns a 200, we check the response body for errors
        error_in_response_body = False
        try:
            error_in_response_body = json.loads(response.read()).get("errors")
        except Exception:
            pass  # The response cannot be parsed as JSON
        return super().is_cachable(request, response) and not error_in_response_body


@contextlib.contextmanager
def graphql_http_client():
    """
    A HTTP client with support for caching GraphQL requests.

    The cache will be stored at `$PWD/.cache`.
    """
    with httpx.Client(
        transport=hishel.CacheTransport(
            transport=httpx.HTTPTransport(),
            controller=GraphQLCacheController(),
        ),
        timeout=None,
    ) as client:
        yield client


def _generate_key_patch(request: Request) -> str:
    """
    Patches Hishel's cache key generation to include the request body for GraphQL requests
    which are always hitting the same endpoint.
    """
    base_key = _generate_key(request)
    hash = hashlib.new("sha256")
    hash.update(base_key.encode())
    for item in request.stream:
        hash.update(item)
    patched_key = hash.hexdigest()
    return patched_key


# Eek! Hishel doesn't let you change this so I patch it for now instead of implementing
# the whole transport again
_generate_key = hishel._sync._transports.generate_key
hishel._sync._transports.generate_key = _generate_key_patch
