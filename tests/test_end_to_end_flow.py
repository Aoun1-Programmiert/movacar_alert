"""Hermetic integration scenarios for trip-scoped polling orchestration."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

import pytest

from src.config.settings import Settings, SmtpSettings
from src.loop import poll_loop
from src.mailer.smtp_mailer import SmtpTransportError
from src.models.offer import Trip
from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def api_response() -> dict[str, Any]:
    fixture_path = Path(__file__).with_name("example_response.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_url="https://api.example.test/offers",
        poll_interval_minutes=15,
        sqlite_path=tmp_path / "offers.sqlite",
        smtp=SmtpSettings(
            host="smtp.example.test",
            port=587,
            user="user",
            password="password",
            sender="sender@example.test",
            use_tls=True,
        ),
        http_timeout_seconds=15.0,
        log_file_path=None,
    )


@pytest.fixture
def store(settings: Settings) -> SQLiteStore:
    sqlite_store = SQLiteStore(settings.sqlite_path)
    sqlite_store.initialize_schema()
    return sqlite_store


def _trip(trip_id: str, name: str, city: str, latitude: float, longitude: float) -> Trip:
    return Trip(
        trip_id=trip_id,
        name=name,
        pickup_start=date(2026, 7, 20),
        pickup_end=date(2026, 7, 25),
        start_city=city,
        latitude=latitude,
        longitude=longitude,
    )


def test_shared_offers_are_fetched_and_notified_independently_per_trip(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    first_trip = _trip("trip-1", "Nordfahrt", "Berlin", 52.52, 13.405)
    second_trip = _trip("trip-2", "Südfahrt", "München", 48.1372, 11.5756)
    for trip, recipient in (
        (first_trip, "north@example.test"),
        (second_trip, "south@example.test"),
    ):
        store.create_trip(trip)
        store.add_trip_recipient(trip.trip_id, recipient)

    requested_trips: list[str] = []
    sent: list[tuple[tuple[str, ...], str]] = []
    monkeypatch.setattr(
        poll_loop,
        "fetch_offers",
        lambda _settings, trip: (
            requested_trips.append(trip.trip_id) or api_response
        ),
    )
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda _smtp, _html, *, recipients, subject: sent.append(
            (recipients, subject)
        ),
    )
    now = datetime(2026, 7, 17, 8)

    first_cycle = poll_loop.run_orchestration_cycle(settings, store, now=now)
    second_cycle = poll_loop.run_orchestration_cycle(settings, store, now=now)

    assert first_cycle.completed_trip_count == 2
    assert second_cycle.completed_trip_count == 2
    assert requested_trips == ["trip-1", "trip-2", "trip-1", "trip-2"]
    assert sent == [
        (("north@example.test",), "Neue Angebote für Nordfahrt"),
        (("south@example.test",), "Neue Angebote für Südfahrt"),
    ]
    assert len(store.read_offers()) == len(api_response["data"])
    assert store.list_new_unsent_available_trip_offers(first_trip.trip_id) == []
    assert store.list_new_unsent_available_trip_offers(second_trip.trip_id) == []


def test_smtp_failure_keeps_trip_offers_unsent_for_next_cycle(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    trip = _trip("trip-1", "Sommerfahrt", "Berlin", 52.52, 13.405)
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "trip@example.test")
    monkeypatch.setattr(
        poll_loop, "fetch_offers", lambda _settings, _trip: api_response
    )
    send_attempts = 0

    def flaky_mailer(
        _smtp: object,
        _html: str,
        *,
        recipients: tuple[str, ...],
        subject: str,
    ) -> None:
        nonlocal send_attempts
        send_attempts += 1
        if send_attempts == 1:
            raise SmtpTransportError("rejected")

    monkeypatch.setattr(poll_loop, "send_html_email", flaky_mailer)
    now = datetime(2026, 7, 17, 8)

    first_cycle = poll_loop.run_orchestration_cycle(settings, store, now=now)
    assert first_cycle.trip_results[0].completed
    assert len(store.list_new_unsent_available_trip_offers(trip.trip_id)) == len(
        api_response["data"]
    )

    poll_loop.run_orchestration_cycle(settings, store, now=now)

    assert send_attempts == 2
    assert store.list_new_unsent_available_trip_offers(trip.trip_id) == []


def test_failed_trip_does_not_block_successful_trip(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
    api_response: dict[str, Any],
) -> None:
    failed_trip = _trip("trip-1", "Fehlerfahrt", "Berlin", 52.52, 13.405)
    successful_trip = _trip("trip-2", "Erfolgsfahrt", "München", 48.1372, 11.5756)
    for trip in (failed_trip, successful_trip):
        store.create_trip(trip)
        store.add_trip_recipient(trip.trip_id, f"{trip.trip_id}@example.test")

    def fetch(_settings: Settings, trip: Trip) -> dict[str, Any]:
        if trip.trip_id == failed_trip.trip_id:
            raise poll_loop.ApiClientError("simulated request failure")
        return api_response

    sent_subjects: list[str] = []
    monkeypatch.setattr(poll_loop, "fetch_offers", fetch)
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda _smtp, _html, *, recipients, subject: sent_subjects.append(subject),
    )

    result = poll_loop.run_orchestration_cycle(
        settings, store, now=datetime(2026, 7, 17, 8)
    )

    assert [item.completed for item in result.trip_results] == [False, True]
    assert sent_subjects == ["Neue Angebote für Erfolgsfahrt"]


def test_idle_cycle_performs_no_external_calls(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    store: SQLiteStore,
) -> None:
    monkeypatch.setattr(
        poll_loop,
        "fetch_offers",
        lambda *_args: pytest.fail("No HTTP call is allowed without trips."),
    )
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda *_args, **_kwargs: pytest.fail("No SMTP call is allowed without trips."),
    )

    result = poll_loop.run_orchestration_cycle(
        settings, store, now=datetime(2026, 7, 17, 8)
    )

    assert result.idle
