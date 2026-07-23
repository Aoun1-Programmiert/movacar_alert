"""Tests for trip and trip-recipient repository operations."""

from datetime import date, datetime
from pathlib import Path

import pytest

from src.models.offer import GeoLocation, Offer, Provider
from src.models.trip import Trip, TripRecipient
from src.storage.sqlite_store import (
    DuplicateTripRecipientError,
    SQLiteStore,
    TripNotFoundError,
)


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
        pickup_start=date(2026, 7, 14),
        pickup_end=date(2026, 7, 20),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )


def test_trips_are_persisted_and_listed_in_stable_order(
    store: SQLiteStore, trip: Trip
) -> None:
    later_trip = Trip(
        trip_id="trip-2",
        name="Herbstfahrt",
        pickup_start=date(2026, 9, 1),
        pickup_end=date(2026, 9, 7),
        start_city="Hamburg",
        latitude=53.5511,
        longitude=9.9937,
    )

    store.create_trip(later_trip)
    store.create_trip(trip)

    assert store.list_trips() == [trip, later_trip]


def test_recipients_are_persisted_and_listed_per_trip(
    store: SQLiteStore, trip: Trip
) -> None:
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, " Z@EXAMPLE.COM ")
    store.add_trip_recipient(trip.trip_id, "a@example.com")

    assert store.list_trip_recipients(trip.trip_id) == [
        TripRecipient(trip.trip_id, "a@example.com"),
        TripRecipient(trip.trip_id, "z@example.com"),
    ]


def test_duplicate_recipient_and_unknown_trip_have_distinct_errors(
    store: SQLiteStore, trip: Trip
) -> None:
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "recipient@example.com")

    with pytest.raises(DuplicateTripRecipientError):
        store.add_trip_recipient(trip.trip_id, "recipient@example.com")
    with pytest.raises(TripNotFoundError):
        store.add_trip_recipient("missing-trip", "recipient@example.com")
    with pytest.raises(TripNotFoundError):
        store.list_trip_recipients("missing-trip")
    with pytest.raises(TripNotFoundError):
        store.remove_trip_recipient("missing-trip", "recipient@example.com")
    with pytest.raises(TripNotFoundError):
        store.delete_trip("missing-trip")


def test_removing_recipient_leaves_its_trip_intact(
    store: SQLiteStore, trip: Trip
) -> None:
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "recipient@example.com")

    store.remove_trip_recipient(trip.trip_id, "recipient@example.com")

    assert store.list_trips() == [trip]
    assert store.list_trip_recipients(trip.trip_id) == []


def test_deleting_trip_atomically_removes_trip_state_but_keeps_global_offer(
    store: SQLiteStore, trip: Trip
) -> None:
    offer = Offer(
        id="offer-1",
        start_date=datetime(2026, 7, 14, 8),
        end_date=datetime(2026, 7, 16, 8),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )
    store.insert_offers([offer])
    store.create_trip(trip)
    store.add_trip_recipient(trip.trip_id, "recipient@example.com")
    store.create_trip_offer(trip.trip_id, offer.id, distance_km=12.5)

    store.delete_trip(trip.trip_id)

    assert store.list_trips() == []
    assert set(store.read_offers()) == {offer.id}
    with pytest.raises(TripNotFoundError):
        store.list_trip_recipients(trip.trip_id)
