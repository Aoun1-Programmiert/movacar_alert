"""Tests for persistent, trip-scoped scheduled overview delivery."""

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config.settings import SmtpSettings
from src.loop.summary_schedule import SummarySlot, latest_due_summary_slot
from src.mailer.smtp_mailer import SmtpTransportError
from src.models.offer import GeoLocation, Offer, Provider, Trip
from src.notifications.instant_notification import MissingTripRecipientsError
from src.notifications.trip_summary import send_due_trip_summary
from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    database = SQLiteStore(tmp_path / "offers.sqlite")
    database.initialize_schema()
    return database


@pytest.fixture
def trip() -> Trip:
    return Trip(
        trip_id="trip-1",
        name="Sommerfahrt",
        pickup_start=date(2026, 7, 20),
        pickup_end=date(2026, 7, 25),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )


@pytest.fixture
def smtp_settings() -> SmtpSettings:
    return SmtpSettings(
        host="smtp.example.test",
        port=587,
        user="mailer",
        password="secret",
        sender="sender@example.test",
        use_tls=True,
    )


def _offer() -> Offer:
    return Offer(
        id="offer-1",
        start_date=datetime(2026, 7, 20, 8),
        end_date=datetime(2026, 7, 22, 8),
        free_km=500,
        origin=GeoLocation("Potsdam", 52.4, 13.1),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )


def _prepare_trip(store: SQLiteStore, trip: Trip) -> None:
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "trip@example.test")
    store.synchronize_trip_offers(trip.trip_id, [(_offer(), 25.0)])


@pytest.mark.parametrize(
    ("now", "expected"),
    (
        (datetime(2026, 7, 14, 8, 59), None),
        (datetime(2026, 7, 14, 9, 0), SummarySlot(date(2026, 7, 14), 9)),
        (datetime(2026, 7, 14, 21, 0), SummarySlot(date(2026, 7, 14), 21)),
        (
            datetime(2026, 7, 14, 19, 1, tzinfo=timezone.utc),
            SummarySlot(date(2026, 7, 14), 21),
        ),
    ),
)
def test_latest_due_summary_slot_uses_europe_berlin(
    now: datetime, expected: SummarySlot | None
) -> None:
    assert latest_due_summary_slot(now) == expected


def test_successful_summary_is_trip_scoped_and_persisted_once(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    _prepare_trip(store, trip)
    composer = MagicMock(return_value="<p>Übersicht</p>")
    mailer = MagicMock()
    due_time = datetime(2026, 7, 14, 9)

    assert send_due_trip_summary(
        store, smtp_settings, trip, due_time, composer=composer, mailer=mailer
    )
    assert not send_due_trip_summary(
        store, smtp_settings, trip, due_time, composer=composer, mailer=mailer
    )

    assert mailer.call_args.kwargs["recipients"] == ("trip@example.test",)
    assert "Sommerfahrt" in mailer.call_args.kwargs["subject"]
    assert mailer.call_count == 1
    assert store.has_trip_overview_slot(trip.trip_id, due_time.date(), 9)


def test_failed_summary_remains_retryable(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    _prepare_trip(store, trip)
    due_time = datetime(2026, 7, 14, 21)
    failing_mailer = MagicMock(side_effect=SmtpTransportError("rejected"))

    with pytest.raises(SmtpTransportError, match="rejected"):
        send_due_trip_summary(
            store,
            smtp_settings,
            trip,
            due_time,
            composer=lambda _view: "<p>Übersicht</p>",
            mailer=failing_mailer,
        )

    assert not store.has_trip_overview_slot(trip.trip_id, due_time.date(), 21)
    successful_mailer = MagicMock()
    assert send_due_trip_summary(
        store,
        smtp_settings,
        trip,
        due_time,
        composer=lambda _view: "<p>Übersicht</p>",
        mailer=successful_mailer,
    )
    assert successful_mailer.call_count == 1


def test_summary_without_trip_recipients_has_no_global_fallback(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    store.create_trip(trip)
    mailer = MagicMock()

    with pytest.raises(MissingTripRecipientsError, match="trip-1"):
        send_due_trip_summary(
            store,
            smtp_settings,
            trip,
            datetime(2026, 7, 14, 9),
            composer=lambda _view: "<p>Übersicht</p>",
            mailer=mailer,
        )

    mailer.assert_not_called()
    assert not store.has_trip_overview_slot(trip.trip_id, date(2026, 7, 14), 9)
