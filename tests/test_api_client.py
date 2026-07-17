"""Unit tests for the offers API client."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from src.api import api_client
from src.models.trip import Trip


class FakeResponse:
    """Minimal context-managed HTTP response for transport tests."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


@pytest.fixture
def settings() -> SimpleNamespace:
    return SimpleNamespace(
        api_url="https://api.example.test/v1/offers?existing=value",
        http_timeout_seconds=15.0,
    )


@pytest.fixture
def trip() -> Trip:
    return Trip(
        trip_id="trip-123",
        name="Sommerfahrt",
        pickup_start=date(2026, 7, 20),
        pickup_end=date(2026, 7, 25),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )


def test_fetch_offers_returns_valid_raw_json_and_uses_settings(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, trip: Trip
) -> None:
    captured: dict[str, object] = {}
    payload = b'{"data": [{"id": "offer-1"}], "included": []}'

    def fake_urlopen(request: object, *, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(api_client, "urlopen", fake_urlopen)

    assert api_client.fetch_offers(settings, trip) == {
        "data": [{"id": "offer-1"}],
        "included": [],
    }
    assert captured["timeout"] == 15.0
    request_url = urlsplit(captured["request"].full_url)  # type: ignore[union-attr]
    assert parse_qs(request_url.query) == {
        "existing": ["value"],
        "locale": ["en"],
        "pickupDateFrom": ["2026-07-20"],
        "pickupDateTo": ["2026-07-25"],
    }
    assert captured["request"].get_method() == "GET"  # type: ignore[union-attr]


def test_fetch_offers_retries_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, trip: Trip
) -> None:
    attempts = 0
    sleeps: list[int] = []

    def flaky_urlopen(request: object, *, timeout: float) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        if attempts <= 3:
            raise URLError("offline")
        return FakeResponse(b'{"data": [], "included": []}')

    monkeypatch.setattr(api_client, "urlopen", flaky_urlopen)
    monkeypatch.setattr(api_client.time, "sleep", sleeps.append)

    assert api_client.fetch_offers(settings, trip) == {"data": [], "included": []}
    assert attempts == 4
    assert sleeps == [1, 2, 4]


def test_fetch_offers_signals_timeout_after_all_retries(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace, trip: Trip
) -> None:
    attempts = 0
    sleeps: list[int] = []

    def timed_out_urlopen(request: object, *, timeout: float) -> FakeResponse:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("timed out")

    monkeypatch.setattr(api_client, "urlopen", timed_out_urlopen)
    monkeypatch.setattr(api_client.time, "sleep", sleeps.append)

    with pytest.raises(api_client.ApiNetworkError, match="4 attempts"):
        api_client.fetch_offers(settings, trip)

    assert attempts == 4
    assert sleeps == [1, 2, 4]


@pytest.mark.parametrize(
    "payload, message",
    (
        (b"not-json", "invalid JSON"),
        (b'{"data": []}', "data' and 'included"),
    ),
)
def test_fetch_offers_signals_invalid_json_or_response_structure(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trip: Trip,
    payload: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(api_client, "urlopen", lambda request, *, timeout: FakeResponse(payload))

    with pytest.raises(api_client.ApiResponseError, match=message):
        api_client.fetch_offers(settings, trip)
