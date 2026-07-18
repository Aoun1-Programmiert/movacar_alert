"""Unit tests for trip-scoped polling orchestration."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.api.api_client import ApiNetworkError
from src.config.timezone import LOCAL_TIMEZONE
from src.loop import poll_loop
from src.mailer.smtp_mailer import SmtpTransportError
from src.models.offer import GeoLocation, Offer, Trip
from src.parser.offer_parser import OfferParsingError
from src.storage.sqlite_store import SQLiteStoreError


class FakeStore:
    """Storage spy exposing only the orchestration boundary."""

    def __init__(self, trips: list[Trip] | None = None) -> None:
        self.trips = [] if trips is None else trips
        self.calls: list[object] = []

    def list_trips(self) -> list[Trip]:
        self.calls.append("list_trips")
        return self.trips

    def purge_unavailable_trip_offers(self, *, now: datetime) -> int:
        self.calls.append(("purge", now))
        return 0


@pytest.fixture
def settings() -> SimpleNamespace:
    return SimpleNamespace(smtp=object(), poll_interval_minutes=15)


@pytest.fixture
def trips() -> list[Trip]:
    return [
        Trip(
            trip_id="trip-1",
            name="Sommerfahrt",
            pickup_start=date(2026, 7, 20),
            pickup_end=date(2026, 7, 25),
            start_city="Berlin",
            latitude=52.52,
            longitude=13.405,
        ),
        Trip(
            trip_id="trip-2",
            name="Herbstfahrt",
            pickup_start=date(2026, 9, 1),
            pickup_end=date(2026, 9, 5),
            start_city="München",
            latitude=48.1372,
            longitude=11.5756,
        ),
    ]


@pytest.fixture
def offer() -> Offer:
    start = datetime(2026, 7, 20, 8, tzinfo=timezone.utc)
    return Offer(
        id="offer-1",
        start_date=start,
        end_date=start + timedelta(days=2),
        free_km=500,
        origin=GeoLocation("Hamburg", 53.5511, 9.9937),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
    )


def _stub_successful_processing(
    monkeypatch: pytest.MonkeyPatch,
    offer: Offer,
    events: list[object] | None = None,
) -> None:
    observed = [] if events is None else events

    def fetch(_settings: object, trip: Trip) -> dict[str, object]:
        observed.append(("fetch", trip.trip_id))
        return {"trip_id": trip.trip_id}

    def parse(response: dict[str, object]) -> list[Offer]:
        observed.append(("parse", response["trip_id"]))
        return [offer]

    def synchronize(_store: object, trip: Trip, offers: object) -> object:
        observed.append(("sync", trip.trip_id, tuple(item.id for item in offers)))
        return SimpleNamespace(offer_ids=frozenset({offer.id}))

    def notify(_store: object, _smtp: object, trip: Trip, **_kwargs: object) -> bool:
        observed.append(("instant", trip.trip_id))
        return True

    def summarize(
        _store: object,
        _smtp: object,
        trip: Trip,
        _now: datetime,
        **_kwargs: object,
    ) -> bool:
        observed.append(("summary", trip.trip_id))
        return False

    monkeypatch.setattr(poll_loop, "fetch_offers", fetch)
    monkeypatch.setattr(poll_loop, "parse_offers", parse)
    monkeypatch.setattr(poll_loop, "synchronize_trip_offers", synchronize)
    monkeypatch.setattr(poll_loop, "send_instant_trip_notification", notify)
    monkeypatch.setattr(poll_loop, "send_due_trip_summary", summarize)


def test_idle_cycle_avoids_http_and_smtp_calls(
    monkeypatch: pytest.MonkeyPatch, settings: SimpleNamespace
) -> None:
    now = datetime(2026, 7, 17, 8, tzinfo=LOCAL_TIMEZONE)
    store = FakeStore()
    monkeypatch.setattr(
        poll_loop,
        "fetch_offers",
        lambda *_args: pytest.fail("Idle cycle must not perform HTTP requests."),
    )
    monkeypatch.setattr(
        poll_loop,
        "send_html_email",
        lambda *_args, **_kwargs: pytest.fail("Idle cycle must not send email."),
    )

    result = poll_loop.run_orchestration_cycle(settings, store, now=now)

    assert result.idle
    assert result.trip_results == ()
    assert store.calls == ["list_trips", ("purge", now)]


def test_all_trips_are_processed_sequentially(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
) -> None:
    events: list[object] = []
    store = FakeStore(trips)
    _stub_successful_processing(monkeypatch, offer, events)

    result = poll_loop.run_orchestration_cycle(
        settings, store, now=datetime(2026, 7, 17, 8)
    )

    assert result.completed
    assert result.completed_trip_count == 2
    assert [item.trip_id for item in result.trip_results] == ["trip-1", "trip-2"]
    assert events == [
        ("fetch", "trip-1"),
        ("parse", "trip-1"),
        ("sync", "trip-1", ("offer-1",)),
        ("instant", "trip-1"),
        ("summary", "trip-1"),
        ("fetch", "trip-2"),
        ("parse", "trip-2"),
        ("sync", "trip-2", ("offer-1",)),
        ("instant", "trip-2"),
        ("summary", "trip-2"),
    ]


def test_successful_trip_processing_logs_trip_context_and_result_counts(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore(trips[:1])
    _stub_successful_processing(monkeypatch, offer)

    with caplog.at_level("INFO"):
        result = poll_loop.run_orchestration_cycle(
            settings, store, now=datetime(2026, 7, 17, 8)
        )

    assert result.trip_results == (
        poll_loop.TripProcessingResult("trip-1", "Sommerfahrt", completed=True),
    )
    assert "id=trip-1" in caplog.text
    assert "name=Sommerfahrt" in caplog.text
    assert "1 Angebote synchronisiert" in caplog.text
    assert "Sofortmail=versendet" in caplog.text
    assert "Übersicht=nicht versendet" in caplog.text


@pytest.mark.parametrize(
    "error",
    (ApiNetworkError("offline"), OfferParsingError("malformed")),
)
def test_fetch_or_parse_failure_is_logged_and_does_not_block_next_trip(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
    error: Exception,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore(trips)
    _stub_successful_processing(monkeypatch, offer)
    original_fetch = poll_loop.fetch_offers

    def fetch(settings: object, trip: Trip) -> object:
        if trip.trip_id == "trip-1":
            raise error
        return original_fetch(settings, trip)

    monkeypatch.setattr(poll_loop, "fetch_offers", fetch)

    with caplog.at_level("ERROR"):
        result = poll_loop.run_orchestration_cycle(
            settings, store, now=datetime(2026, 7, 17, 8)
        )

    assert [item.completed for item in result.trip_results] == [False, True]
    assert "id=trip-1" in caplog.text
    assert "name=Sommerfahrt" in caplog.text
    assert "Abruf/Parsing" in caplog.text


def test_database_failure_is_logged_and_does_not_block_next_trip(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore(trips)
    _stub_successful_processing(monkeypatch, offer)
    original_sync = poll_loop.synchronize_trip_offers

    def synchronize(store: object, trip: Trip, offers: object) -> object:
        if trip.trip_id == "trip-1":
            raise SQLiteStoreError("database unavailable")
        return original_sync(store, trip, offers)

    monkeypatch.setattr(poll_loop, "synchronize_trip_offers", synchronize)

    with caplog.at_level("ERROR"):
        result = poll_loop.run_orchestration_cycle(
            settings, store, now=datetime(2026, 7, 17, 8)
        )

    assert [item.completed for item in result.trip_results] == [False, True]
    assert "id=trip-1" in caplog.text
    assert "name=Sommerfahrt" in caplog.text
    assert "Synchronisierung" in caplog.text


def test_smtp_failure_remains_retryable_and_summary_processing_continues(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    events: list[object] = []
    store = FakeStore(trips[:1])
    _stub_successful_processing(monkeypatch, offer, events)

    def fail_instant(
        _store: object, _smtp: object, trip: Trip, **_kwargs: object
    ) -> bool:
        events.append(("instant", trip.trip_id))
        raise SmtpTransportError("rejected")

    monkeypatch.setattr(poll_loop, "send_instant_trip_notification", fail_instant)

    with caplog.at_level("ERROR"):
        result = poll_loop.run_orchestration_cycle(
            settings, store, now=datetime(2026, 7, 17, 9)
        )

    assert result.trip_results[0].completed
    assert ("summary", "trip-1") in events
    assert "id=trip-1" in caplog.text
    assert "name=Sommerfahrt" in caplog.text
    assert "Sofortbenachrichtigung" in caplog.text


def test_cycle_converts_offer_dates_to_local_time_before_synchronization(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    trips: list[Trip],
    offer: Offer,
) -> None:
    captured: list[Offer] = []
    store = FakeStore(trips[:1])
    _stub_successful_processing(monkeypatch, offer)

    def capture(_store: object, _trip: Trip, offers: object) -> object:
        captured.extend(offers)
        return SimpleNamespace(offer_ids=frozenset({offer.id}))

    monkeypatch.setattr(poll_loop, "synchronize_trip_offers", capture)

    poll_loop.run_orchestration_cycle(
        settings, store, now=datetime(2026, 7, 17, 8)
    )

    assert captured[0].start_date == offer.start_date.astimezone(LOCAL_TIMEZONE)
    assert captured[0].end_date == offer.end_date.astimezone(LOCAL_TIMEZONE)
    assert captured[0].start_date.tzinfo == LOCAL_TIMEZONE


def test_trip_listing_failure_is_reported_as_failed_non_idle_cycle(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore()
    monkeypatch.setattr(
        store,
        "list_trips",
        lambda: (_ for _ in ()).throw(SQLiteStoreError("unavailable")),
    )

    with caplog.at_level("ERROR"):
        result = poll_loop.run_orchestration_cycle(
            settings, store, now=datetime(2026, 7, 17, 8)
        )

    assert not result.completed
    assert not result.idle
    assert "Reisen konnten nicht geladen werden" in caplog.text


def test_poll_forever_waits_until_next_aligned_slot(
    monkeypatch: pytest.MonkeyPatch,
    settings: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr(
        poll_loop,
        "run_orchestration_cycle",
        lambda settings, store, *, now: (
            calls.append(("cycle", now))
            or poll_loop.OrchestrationCycleResult(())
        ),
    )

    def stop_after_first_sleep(seconds: float) -> None:
        calls.append(seconds)
        raise RuntimeError("stop test loop")

    current_time = datetime(2026, 7, 17, 8, 7)
    with caplog.at_level("INFO"), pytest.raises(RuntimeError, match="stop test loop"):
        poll_loop.poll_forever(
            settings,
            object(),
            sleep=stop_after_first_sleep,
            now=lambda: current_time,
        )

    assert calls == [
        480,
    ]
    assert (
        "Programm gestartet; erster Durchlauf um 2026-07-17 08:15:00 "
        "(Wartezeit 480 Sekunden)." in caplog.text
    )


@pytest.mark.parametrize(
    ("current_time", "expected"),
    (
        (datetime(2026, 7, 17, 8, 0), datetime(2026, 7, 17, 8, 15)),
        (datetime(2026, 7, 17, 8, 14, 59), datetime(2026, 7, 17, 8, 15)),
        (datetime(2026, 7, 17, 8, 45), datetime(2026, 7, 17, 9, 0)),
    ),
)
def test_next_aligned_cycle_uses_full_quarter_hours(
    current_time: datetime, expected: datetime
) -> None:
    assert poll_loop._next_aligned_cycle(current_time, 15) == expected.replace(
        tzinfo=LOCAL_TIMEZONE
    )
