"""Tests for trip-scoped instant notifications."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config.settings import SmtpSettings
from src.mailer.smtp_mailer import SmtpTransportError
from src.models.offer import GeoLocation, Offer, Trip
from src.notifications.instant_notification import (
    MissingTripRecipientsError,
    send_instant_trip_notification,
)
from src.notifications.trip_mail_view import TripMailView
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
        recipients=("global@example.test",),
        use_tls=True,
    )


def make_offer(offer_id: str) -> Offer:
    return Offer(
        id=offer_id,
        start_date=datetime(2026, 7, 20, 8),
        end_date=datetime(2026, 7, 22, 8),
        free_km=500,
        origin=GeoLocation("Hamburg", 53.5511, 9.9937),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
    )


def test_success_sends_prepared_view_to_trip_recipients_and_marks_new_offers(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    new_offer = make_offer("new")
    existing_offer = make_offer("existing")
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "TRIP@EXAMPLE.TEST")
    store.synchronize_trip_offers(
        trip.trip_id, [(new_offer, 20.0), (existing_offer, 30.0)]
    )
    store.mark_trip_offers_sent(trip.trip_id, [existing_offer.id])
    composer = MagicMock(return_value="<p>Reiseangebote</p>")
    mailer = MagicMock()

    sent = send_instant_trip_notification(
        store,
        smtp_settings,
        trip,
        composer=composer,
        mailer=mailer,
    )

    assert sent is True
    view = composer.call_args.args[0]
    assert isinstance(view, TripMailView)
    assert [offer.offer_id for offer in view.new_offers] == [new_offer.id]
    assert [offer.offer_id for offer in view.available_offers] == [
        new_offer.id,
        existing_offer.id,
    ]
    assert mailer.call_args.kwargs["recipients"] == ("trip@example.test",)
    assert "Sommerfahrt" in mailer.call_args.kwargs["subject"]
    assert store.list_new_unsent_available_trip_offers(trip.trip_id) == []


def test_smtp_failure_keeps_new_offers_retryable(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    offer = make_offer("retry")
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "trip@example.test")
    store.synchronize_trip_offers(trip.trip_id, [(offer, 10.0)])
    failing_mailer = MagicMock(side_effect=SmtpTransportError("rejected"))

    with pytest.raises(SmtpTransportError, match="rejected"):
        send_instant_trip_notification(
            store,
            smtp_settings,
            trip,
            composer=lambda _view: "<p>Reiseangebote</p>",
            mailer=failing_mailer,
        )

    assert [
        offer_view.offer_id
        for offer_view in store.list_new_unsent_available_trip_offers(trip.trip_id)
    ] == [offer.id]


def test_without_new_offers_does_not_compose_or_send(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    store.create_trip(trip)
    composer = MagicMock()
    mailer = MagicMock()

    assert (
        send_instant_trip_notification(
            store,
            smtp_settings,
            trip,
            composer=composer,
            mailer=mailer,
        )
        is False
    )
    composer.assert_not_called()
    mailer.assert_not_called()


def test_without_trip_recipients_does_not_use_global_fallback(
    store: SQLiteStore, trip: Trip, smtp_settings: SmtpSettings
) -> None:
    offer = make_offer("new")
    store.create_trip(trip)
    store.synchronize_trip_offers(trip.trip_id, [(offer, 10.0)])
    mailer = MagicMock()

    with pytest.raises(MissingTripRecipientsError, match="trip-1"):
        send_instant_trip_notification(
            store,
            smtp_settings,
            trip,
            composer=lambda _view: "<p>Reiseangebote</p>",
            mailer=mailer,
        )

    mailer.assert_not_called()
    assert len(store.list_new_unsent_available_trip_offers(trip.trip_id)) == 1
