from email.utils import formatdate

import httpx
import pytest

from rooster import _http
from rooster._http import HttpClient


@pytest.fixture
def retry_delays(monkeypatch):
    delays = []
    monkeypatch.setattr(_http, "RETRY_JITTER_FACTOR", 0)
    monkeypatch.setattr(_http.time, "sleep", delays.append)
    return delays


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("3", 3),
        ("0", 0),
        ("-1", 2),
        ("invalid", 2),
        ("nan", 2),
        ("inf", 2),
        (formatdate(1_800_000_010, usegmt=True), 10),
        (formatdate(1_799_999_990, usegmt=True), 0),
    ],
)
def test_retry_after_dates_and_invalid_values(
    monkeypatch, retry_delays, header, expected
):
    monkeypatch.setattr(_http.time, "time", lambda: 1_800_000_000)
    attempts = []

    def handle(request):
        attempts.append(request)
        return (
            httpx.Response(503, headers={"Retry-After": header})
            if len(attempts) == 1
            else httpx.Response(200)
        )

    with HttpClient(transport=httpx.MockTransport(handle)) as client:
        assert client.get("https://example.com").status_code == 200

    assert len(attempts) == 2
    assert retry_delays == [expected]


def test_retry_jitter_respects_the_servers_minimum_delay(monkeypatch, retry_delays):
    monkeypatch.setattr(_http, "RETRY_JITTER_FACTOR", 0.2)
    responses = iter(
        [httpx.Response(503, headers={"Retry-After": "10"}), httpx.Response(200)]
    )
    with HttpClient(
        transport=httpx.MockTransport(lambda request: next(responses))
    ) as client:
        assert client.get("https://example.com").status_code == 200
    assert len(retry_delays) == 1
    assert 10 <= retry_delays[0] <= 12


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadError,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.RemoteProtocolError,
    ],
)
def test_transient_transport_errors_are_retried(retry_delays, error):
    attempts = []

    def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise error("Temporary failure", request=request)
        return httpx.Response(200)

    with HttpClient(transport=httpx.MockTransport(handle)) as client:
        assert client.get("https://example.com").status_code == 200
    assert len(attempts) == 2
    assert retry_delays == [2]


def test_invalid_local_requests_are_not_retried(retry_delays):
    attempts = []

    def handle(request):
        attempts.append(request)
        raise httpx.LocalProtocolError("Invalid request", request=request)

    with (
        HttpClient(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(httpx.LocalProtocolError, match="Invalid request"),
    ):
        client.get("https://example.com")
    assert len(attempts) == 1
    assert retry_delays == []


def test_transport_retries_are_bounded(monkeypatch, retry_delays):
    monkeypatch.setattr(_http, "MAX_RETRIES", 2)
    attempts = []

    def handle(request):
        attempts.append(request)
        raise httpx.ConnectError("Still unavailable", request=request)

    with (
        HttpClient(transport=httpx.MockTransport(handle)) as client,
        pytest.raises(httpx.ConnectError, match="Still unavailable"),
    ):
        client.get("https://example.com")
    assert len(attempts) == 3
    assert retry_delays == [2, 4]
