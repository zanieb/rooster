import math
import random
import sys
import time
from typing import Any, Callable

import httpx

MAX_RETRIES = 5
RETRY_JITTER_FACTOR = 0.2
HTTP_429_TOO_MANY_REQUESTS = 429
HTTP_503_SERVICE_UNAVAILABLE = 503
HTTP_502_BAD_GATEWAY = 502
HTTP_408_REQUEST_TIMEOUT = 408


def poisson_interval(
    average_interval: float, lower: float = 0, upper: float = 1
) -> float:
    """
    Generates an "inter-arrival time" for a Poisson process.

    Draws a random variable from an exponential distribution using the inverse-CDF
    method. Can optionally be passed a lower and upper bound between (0, 1] to clamp
    the potential output values.
    """

    # note that we ensure the argument to the logarithm is stabilized to prevent
    # calling log(0), which results in a DomainError
    return -math.log(max(1 - random.uniform(lower, upper), 1e-10)) * average_interval


def exponential_cdf(x: float, average_interval: float) -> float:
    ld = 1 / average_interval
    return 1 - math.exp(-ld * x)


def lower_clamp_multiple(k: float) -> float:
    """
    Computes a lower clamp multiple that can be used to bound a random variate drawn
    from an exponential distribution.

    Given an upper clamp multiple `k` (and corresponding upper bound k * average_interval),
    this function computes a lower clamp multiple `c` (corresponding to a lower bound
    c * average_interval) where the probability mass between the lower bound and the
    median is equal to the probability mass between the median and the upper bound.
    """
    if k >= 50:
        # return 0 for large values of `k` to prevent numerical overflow
        return 0.0

    return math.log(max(2**k / (2**k - 1), 1e-10), 2)


def clamped_poisson_interval(
    average_interval: float, clamping_factor: float = 0.3
) -> float:
    """
    Bounds Poisson "inter-arrival times" to a range defined by the clamping factor.

    The upper bound for this random variate is: average_interval * (1 + clamping_factor).
    A lower bound is picked so that the average interval remains approximately fixed.
    """
    if clamping_factor <= 0:
        raise ValueError("`clamping_factor` must be >= 0.")

    upper_clamp_multiple = 1 + clamping_factor
    upper_bound = average_interval * upper_clamp_multiple
    lower_bound = max(0, average_interval * lower_clamp_multiple(upper_clamp_multiple))

    upper_rv = exponential_cdf(upper_bound, average_interval)
    lower_rv = exponential_cdf(lower_bound, average_interval)
    return poisson_interval(average_interval, lower_rv, upper_rv)


def bounded_poisson_interval(lower_bound: float, upper_bound: float) -> float:
    """
    Bounds Poisson "inter-arrival times" to a range.

    Unlike `clamped_poisson_interval` this does not take a target average interval.
    Instead, the interval is predetermined and the average is calculated as their
    midpoint. This allows Poisson intervals to be used in cases where a lower bound
    must be enforced.
    """
    average = (float(lower_bound) + float(upper_bound)) / 2.0
    upper_rv = exponential_cdf(upper_bound, average)
    lower_rv = exponential_cdf(lower_bound, average)
    return poisson_interval(average, lower_rv, upper_rv)


class HttpClient(httpx.Client):
    """
    A wrapper httpx client with support for retry-after headers and retry on
    transient errors.
    """

    def _send_with_retry(
        self,
        request: httpx.Request,
        send: Callable[[httpx.Request], httpx.Response],
        send_args: tuple[Any, ...],
        send_kwargs: dict[str, Any],
        retry_codes: set[int] = set(),
        retry_exceptions: tuple[type[Exception], ...] = tuple(),
    ):
        """
        Send a request and retry it if it fails.

        Sends the provided request and retries it up to MAX_RETRIES times if the
        request either raises an exception listed in `retry_exceptions` or
        receives a response with a status code listed in `retry_codes`.

        Retries will be delayed based on either the retry header (preferred) or
        exponential backoff if a retry header is not provided.
        """
        try_count = 0
        response = None

        while try_count <= MAX_RETRIES:
            retry_seconds = None
            exc_info = None

            try:
                response = send(request, *send_args, **send_kwargs)
            except retry_exceptions:  # type: ignore
                try_count += 1
                if try_count > MAX_RETRIES:
                    raise
                # Otherwise, we will ignore this error but capture the info for logging
                exc_info = sys.exc_info()
            else:
                if response.status_code not in retry_codes:
                    return response
                try_count += 1
                if try_count > MAX_RETRIES:
                    break

                if "Retry-After" in response.headers:
                    retry_seconds = float(response.headers["Retry-After"])

            # Use an exponential back-off if not set in a header
            if retry_seconds is None:
                retry_seconds = 2**try_count

            # Add jitter
            jitter_factor = RETRY_JITTER_FACTOR
            if retry_seconds > 0 and jitter_factor > 0:
                if response is not None and "Retry-After" in response.headers:
                    # Always wait for _at least_ retry seconds if requested by the API
                    retry_seconds = bounded_poisson_interval(
                        retry_seconds, retry_seconds * (1 + jitter_factor)
                    )
                else:
                    # Otherwise, use a symmetrical jitter
                    retry_seconds = clamped_poisson_interval(
                        retry_seconds, jitter_factor
                    )

            print(
                (
                    f"Encountered retryable exception during request {exc_info[1]!r}. "
                    if exc_info
                    else (
                        "Received response with retryable status code"
                        f" {response.status_code if response else 'unknown'}. "
                    )
                )
                + f"Another attempt will be made in {round(retry_seconds, 2)}s. "
                "This is attempt"
                f" {try_count}/{MAX_RETRIES + 1}.",
            )
            time.sleep(retry_seconds)

        assert response is not None, (
            "Retry handling ended without response or exception"
        )

        # We ran out of retries, return the failed response
        return response

    def send(self, request: httpx.Request, *args: Any, **kwargs: Any) -> httpx.Response:
        """
        Send a request with automatic retry behavior for the following status codes:

        - 403 Forbidden, if the request failed due to CSRF protection
        - 408 Request Timeout
        - 429 CloudFlare-style rate limiting
        - 502 Bad Gateway
        - 503 Service unavailable
        """

        super_send = super().send
        response = self._send_with_retry(
            request=request,
            send=super_send,
            send_args=args,
            send_kwargs=kwargs,
            retry_codes={
                HTTP_429_TOO_MANY_REQUESTS,
                HTTP_503_SERVICE_UNAVAILABLE,
                HTTP_502_BAD_GATEWAY,
                HTTP_408_REQUEST_TIMEOUT,
            },
            retry_exceptions=(
                httpx.ReadTimeout,
                httpx.PoolTimeout,
                httpx.ConnectTimeout,
                # `ConnectionResetError` when reading socket raises as a `ReadError`
                httpx.ReadError,
                # Sockets can be closed during writes resulting in a `WriteError`
                httpx.WriteError,
                httpx.RemoteProtocolError,
                httpx.LocalProtocolError,
            ),
        )

        return response
