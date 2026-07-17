"""Hermetic integration scenarios for trip-scoped polling orchestration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from src import admin_cli
from src.api import api_client
from src.config.settings import Settings, SmtpSettings
from src.config.timezone import LOCAL_TIMEZONE
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


class _HttpResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "_HttpResponse":
        return self

    def __exit__(
        self, exc_type: object, exc_value: object, traceback: object
    ) -> bool:
        return False

    def read(self) -> bytes:
        return self.payload


def _movacar_payload(
    offers: tuple[tuple[str, str, float, float], ...],
) -> bytes:
    destination_id = "destination"
    data = []
    included = [
        {
            "type": "station",
            "id": destination_id,
            "attributes": {
                "city": "Paris",
                "latitude": 48.8566,
                "longitude": 2.3522,
            },
        }
    ]
    for offer_id, origin_city, latitude, longitude in offers:
        origin_id = f"origin-{offer_id}"
        data.append(
            {
                "type": "offer",
                "id": offer_id,
                "attributes": {
                    "start_date": "2026-07-20T08:00:00Z",
                    "end_date": "2026-07-22T08:00:00Z",
                    "free_km": 500,
                },
                "relationships": {
                    "origin": {"data": {"type": "station", "id": origin_id}},
                    "destination": {
                        "data": {"type": "station", "id": destination_id}
                    },
                },
            }
        )
        included.append(
            {
                "type": "station",
                "id": origin_id,
                "attributes": {
                    "city": origin_city,
                    "latitude": latitude,
                    "longitude": longitude,
                },
            }
        )
    return json.dumps({"data": data, "included": included}).encode()


def _offer_ids_in_order(html: str, section_id: str) -> list[str]:
    section = html.split(f'id="{section_id}"', maxsplit=1)[1]
    section = section.split("</section>", maxsplit=1)[0]
    marker = 'data-offer-id="'
    return [
        fragment.split('"', maxsplit=1)[0]
        for fragment in section.split(marker)[1:]
    ]


def test_complete_trip_journey_is_hermetic(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_path = str(settings.sqlite_path)

    def run_cli(*arguments: str) -> None:
        assert (
            admin_cli.main(["--sqlite-path", database_path, *arguments])
            == 0
        )

    run_cli(
        "trip",
        "create",
        "--trip-id",
        "north",
        "--name",
        "Nordfahrt",
        "--pickup-start",
        "2026-07-20",
        "--pickup-end",
        "2026-07-25",
        "--start-city",
        "Berlin",
        "--latitude",
        "52.52",
        "--longitude",
        "13.405",
    )
    run_cli(
        "trip",
        "create",
        "--trip-id",
        "south",
        "--name",
        "Südfahrt",
        "--pickup-start",
        "2026-08-10",
        "--pickup-end",
        "2026-08-15",
        "--start-city",
        "München",
        "--latitude",
        "48.1372",
        "--longitude",
        "11.5756",
    )
    run_cli(
        "trip",
        "recipient",
        "add",
        "--trip-id",
        "north",
        "--email",
        "north@example.test",
    )
    run_cli(
        "trip",
        "recipient",
        "add",
        "--trip-id",
        "south",
        "--email",
        "south@example.test",
    )
    capsys.readouterr()

    store = SQLiteStore(settings.sqlite_path)
    store.initialize_schema()
    north_window = ("2026-07-20", "2026-07-25")
    south_window = ("2026-08-10", "2026-08-15")
    shared_offer = ("shared", "Potsdam", 52.4, 13.1)
    orange_offer = ("orange", "Leipzig", 51.3397, 12.3731)
    response_mode = {"value": "initial"}
    requests: list[tuple[str, dict[str, list[str]]]] = []

    def movacar_double(request: object, *, timeout: float) -> _HttpResponse:
        assert timeout == settings.http_timeout_seconds
        query = parse_qs(urlsplit(request.full_url).query)  # type: ignore[union-attr]
        requests.append((response_mode["value"], query))
        window = (
            query["pickupDateFrom"][0],
            query["pickupDateTo"][0],
        )
        if response_mode["value"] == "north-fails" and window == north_window:
            raise URLError("simulated Movacar outage")
        if window == north_window:
            offers = (
                (orange_offer,)
                if response_mode["value"] == "north-without-shared"
                else (shared_offer, orange_offer)
            )
        elif window == south_window:
            offers = (shared_offer,)
        else:
            pytest.fail(f"Unexpected trip request window: {window}")
        return _HttpResponse(_movacar_payload(offers))

    mail_attempts: list[tuple[str, tuple[str, ...], str]] = []
    fail_once = {"Neue Angebote für Nordfahrt"}

    def smtp_double(
        _smtp: SmtpSettings,
        html: str,
        *,
        recipients: tuple[str, ...],
        subject: str,
    ) -> None:
        mail_attempts.append((subject, recipients, html))
        if subject in fail_once:
            fail_once.remove(subject)
            raise SmtpTransportError("simulated SMTP rejection")

    monkeypatch.setattr(api_client, "urlopen", movacar_double)
    monkeypatch.setattr(api_client.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(poll_loop, "send_html_email", smtp_double)

    cycle_time = datetime(2026, 7, 17, 9, tzinfo=LOCAL_TIMEZONE)
    first_cycle = poll_loop.run_orchestration_cycle(
        settings, store, now=cycle_time
    )

    assert first_cycle.completed_trip_count == 2
    assert [query for mode, query in requests if mode == "initial"] == [
        {
            "locale": ["en"],
            "pickupDateFrom": [north_window[0]],
            "pickupDateTo": [north_window[1]],
        },
        {
            "locale": ["en"],
            "pickupDateFrom": [south_window[0]],
            "pickupDateTo": [south_window[1]],
        },
    ]
    assert [(subject, recipients) for subject, recipients, _html in mail_attempts] == [
        ("Neue Angebote für Nordfahrt", ("north@example.test",)),
        ("Regelmäßiges Update - Nordfahrt", ("north@example.test",)),
        ("Neue Angebote für Südfahrt", ("south@example.test",)),
        ("Regelmäßiges Update - Südfahrt", ("south@example.test",)),
    ]

    north_instant = mail_attempts[0][2]
    north_summary = mail_attempts[1][2]
    south_instant = mail_attempts[2][2]
    for html in (north_instant, north_summary):
        assert "Nordfahrt" in html
        assert "20.07.2026 bis 25.07.2026" in html
        assert "Startstadt:</strong> Berlin" in html
        assert "offer--red" in html
        assert "offer--orange" in html
        assert _offer_ids_in_order(html, "available-offers") == [
            "shared",
            "orange",
        ]
    assert _offer_ids_in_order(north_instant, "new-offers") == [
        "shared",
        "orange",
    ]
    assert "Südfahrt" in south_instant
    assert 'data-offer-id="shared"' in south_instant

    poll_loop.run_orchestration_cycle(settings, store, now=cycle_time)

    north_instant_attempts = [
        attempt
        for attempt in mail_attempts
        if attempt[0] == "Neue Angebote für Nordfahrt"
    ]
    assert len(north_instant_attempts) == 2
    assert store.list_new_unsent_available_trip_offers("north") == []
    assert store.list_new_unsent_available_trip_offers("south") == []

    response_mode["value"] = "north-fails"
    attempts_before_failure = len(mail_attempts)
    failed_cycle = poll_loop.run_orchestration_cycle(
        settings, store, now=cycle_time
    )

    assert [result.completed for result in failed_cycle.trip_results] == [
        False,
        True,
    ]
    assert len(
        [request for request in requests if request[0] == "north-fails"]
    ) == 5
    assert len(mail_attempts) == attempts_before_failure
    assert [
        view.offer_id for view in store.list_available_trip_offers("north")
    ] == ["shared", "orange"]

    response_mode["value"] = "north-without-shared"
    availability_cycle = poll_loop.run_orchestration_cycle(
        settings, store, now=cycle_time
    )

    assert availability_cycle.completed_trip_count == 2
    assert [
        view.offer_id for view in store.list_available_trip_offers("north")
    ] == ["orange"]
    assert [
        view.offer_id for view in store.list_available_trip_offers("south")
    ] == ["shared"]

    retention_time = datetime.now(LOCAL_TIMEZONE) + timedelta(
        days=15, seconds=1
    )
    poll_loop.run_orchestration_cycle(settings, store, now=retention_time)

    with sqlite3.connect(settings.sqlite_path) as connection:
        assert connection.execute(
            """
            SELECT trip_id, offer_id
            FROM trip_offers
            ORDER BY trip_id, offer_id
            """
        ).fetchall() == [("north", "orange"), ("south", "shared")]
        assert connection.execute(
            "SELECT id FROM offers ORDER BY id"
        ).fetchall() == [("orange",), ("shared",)]

    run_cli("trip", "delete", "--trip-id", "north")
    run_cli("trip", "delete", "--trip-id", "south")
    request_count = len(requests)
    mail_attempt_count = len(mail_attempts)

    idle_cycle = poll_loop.run_orchestration_cycle(
        settings, store, now=retention_time
    )

    assert idle_cycle.idle
    assert len(requests) == request_count
    assert len(mail_attempts) == mail_attempt_count


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
