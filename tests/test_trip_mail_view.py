"""Tests for prepared trip-specific mail views."""

from datetime import date, datetime
from pathlib import Path
import sqlite3

import pytest

from src.models.offer import DistanceTier, GeoLocation, Offer, Trip
from src.notifications.trip_mail_view import prepare_trip_mail_view
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError, TripNotFoundError
from src.synchronization.trip_offer_synchronizer import synchronize_trip_offers


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


def make_offer(offer_id: str, city: str, latitude: float) -> Offer:
    return Offer(
        id=offer_id,
        start_date=datetime(2026, 7, 20, 8),
        end_date=datetime(2026, 7, 22, 8),
        free_km=500,
        origin=GeoLocation(city, latitude, 13.0),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
    )


def test_prepare_mail_view_is_trip_scoped_sorted_and_includes_new_in_both_sections(
    store: SQLiteStore, trip: Trip
) -> None:
    other_trip = Trip(
        trip_id="trip-2",
        name="Herbstfahrt",
        pickup_start=trip.pickup_start,
        pickup_end=trip.pickup_end,
        start_city="Hamburg",
        latitude=53.5511,
        longitude=9.9937,
    )
    new_near = make_offer("new-near", "Potsdam", 52.0)
    sent_far = make_offer("sent-far", "Leipzig", 51.0)
    other_offer = make_offer("other", "Cologne", 50.0)
    store.create_trip(trip)
    store.create_trip(other_trip)
    store.add_trip_recipient(trip.trip_id, " Z@EXAMPLE.COM ")
    store.add_trip_recipient(trip.trip_id, "a@example.com")
    synchronize_trip_offers(
        store,
        trip,
        [sent_far, new_near],
        distance_calculator=lambda *coordinates: (
            100.00001
            if coordinates[2] == sent_far.origin.latitude
            else 99.99999
        ),
    )
    synchronize_trip_offers(
        store, other_trip, [other_offer], distance_calculator=lambda *_: 1.0
    )
    assert store.mark_trip_offers_sent(trip.trip_id, [sent_far.id]) == 1

    view = prepare_trip_mail_view(store, trip)

    assert view.trip == trip
    assert view.recipients == ("a@example.com", "z@example.com")
    assert [offer.offer_id for offer in view.new_offers] == [new_near.id]
    assert [offer.offer_id for offer in view.available_offers] == [
        new_near.id,
        sent_far.id,
    ]
    assert view.new_offers[0].distance_tier is DistanceTier.RED
    assert view.available_offers[1].distance_tier is DistanceTier.ORANGE
    assert view.available_offers[0].distance_km < view.available_offers[1].distance_km
    assert view.new_offers[0].offer.origin == new_near.origin
    assert view.available_offers[1].is_sent is True


def test_trip_offer_queries_reject_unknown_trip(store: SQLiteStore) -> None:
    with pytest.raises(TripNotFoundError):
        store.list_new_unsent_available_trip_offers("missing")
    with pytest.raises(TripNotFoundError):
        store.list_available_trip_offers("missing")


def test_trip_offer_queries_fail_explicitly_for_legacy_offer_without_coordinates(
    store: SQLiteStore, trip: Trip
) -> None:
    store.create_trip(trip)

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, destination_city,
                free_km, first_seen_timestamp
            ) VALUES ('legacy', '2026-07-20T08:00:00', '2026-07-22T08:00:00',
                      'Berlin', 'Paris', 500, '2026-07-20T08:00:00')
            """
        )
        connection.execute(
            """
            INSERT INTO trip_offers (trip_id, offer_id, distance_km)
            VALUES (?, 'legacy', 10)
            """,
            (trip.trip_id,),
        )

    with pytest.raises(SQLiteStoreError, match="Could not reconstruct"):
        store.list_available_trip_offers(trip.trip_id)
