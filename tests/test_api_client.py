"""Unit tests for the offers API client."""

from __future__ import annotations

from types import SimpleNamespace
from urllib.error import URLError

import pytest

from src.api import api_client


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
        api_url="https://api.example.test/v1/offers?locale=en",
        http_timeout_seconds=15.0,
    )


def test_fetch_offers_returns_valid_raw_json_and_uses_settings(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace
) -> None:
    captured: dict[str, object] = {}
    payload = b'{"data": [{"id": "offer-1"}], "included": []}'

    def fake_urlopen(request: object, *, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse(payload)

    monkeypatch.setattr(api_client, "urlopen", fake_urlopen)

    assert api_client.fetch_offers(settings) == {
        "data": [{"id": "offer-1"}],
        "included": [],
    }
    assert captured["timeout"] == 15.0
    assert captured["request"].full_url == settings.api_url  # type: ignore[union-attr]
    assert captured["request"].get_method() == "GET"  # type: ignore[union-attr]


def test_fetch_offers_retries_with_exponential_backoff(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace
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

    assert api_client.fetch_offers(settings) == {"data": [], "included": []}
    assert attempts == 4
    assert sleeps == [1, 2, 4]


def test_fetch_offers_signals_timeout_after_all_retries(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace
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
        api_client.fetch_offers(settings)

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
    payload: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(api_client, "urlopen", lambda request, *, timeout: FakeResponse(payload))

    with pytest.raises(api_client.ApiResponseError, match=message):
        api_client.fetch_offers(settings)
