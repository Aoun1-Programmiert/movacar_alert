"""Unit tests for trip-scoped offer delivery-state persistence."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.models.offer import GeoLocation, Offer
from src.models.trip import Trip
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
        pickup_start=datetime(2026, 7, 20).date(),
        pickup_end=datetime(2026, 7, 25).date(),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
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


def test_mark_trip_offers_sent_marks_only_successfully_delivered_relations(
    store: SQLiteStore, trip: Trip
) -> None:
    delivered_offer = make_offer("offer-delivered")
    retry_offer = make_offer("offer-retry")
    store.create_trip(trip)
    store.synchronize_trip_offers(
        trip.trip_id, [(delivered_offer, 10.0), (retry_offer, 20.0)]
    )

    assert store.mark_trip_offers_sent(trip.trip_id, [delivered_offer.id]) == 1

    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            """
            SELECT offer_id, is_sent, sent_at
            FROM trip_offers
            ORDER BY offer_id
            """
        ).fetchall()
    assert rows[0][0] == delivered_offer.id
    assert rows[0][1] == 1
    assert rows[0][2] is not None
    datetime.fromisoformat(rows[0][2])
    assert rows[1] == (retry_offer.id, 0, None)


def test_unsent_relation_remains_retryable_when_smtp_handoff_fails(
    store: SQLiteStore, trip: Trip
) -> None:
    offer = make_offer("offer-retry")
    store.create_trip(trip)
    store.synchronize_trip_offers(trip.trip_id, [(offer, 10.0)])

    # A failed SMTP handoff deliberately does not invoke mark_trip_offers_sent.
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            """
            SELECT is_sent, sent_at
            FROM trip_offers
            WHERE trip_id = ? AND offer_id = ?
            """,
            (trip.trip_id, offer.id),
        ).fetchone() == (0, None)


def test_mark_trip_offers_sent_is_trip_scoped_and_keeps_unavailable_relations_unsent(
    store: SQLiteStore, trip: Trip
) -> None:
    second_trip = Trip(
        trip_id="trip-2",
        name="Herbstfahrt",
        pickup_start=trip.pickup_start,
        pickup_end=trip.pickup_end,
        start_city="Munich",
        latitude=48.1372,
        longitude=11.5756,
    )
    offer = make_offer("offer-shared")
    unavailable_offer = make_offer("offer-unavailable")
    store.create_trip(trip)
    store.create_trip(second_trip)
    store.synchronize_trip_offers(
        trip.trip_id, [(offer, 10.0), (unavailable_offer, 20.0)]
    )
    store.synchronize_trip_offers(second_trip.trip_id, [(offer, 15.0)])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE trip_offers
            SET is_available = 0, unavailable_since = '2026-07-01T10:00:00+02:00'
            WHERE trip_id = ? AND offer_id = ?
            """,
            (trip.trip_id, unavailable_offer.id),
        )

    assert store.mark_trip_offers_sent(
        trip.trip_id, [offer.id, unavailable_offer.id]
    ) == 1

    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            """
            SELECT trip_id, offer_id, is_sent
            FROM trip_offers
            ORDER BY trip_id, offer_id
            """
        ).fetchall()
    assert rows == [
        (trip.trip_id, offer.id, 1),
        (trip.trip_id, unavailable_offer.id, 0),
        (second_trip.trip_id, offer.id, 0),
    ]


@pytest.mark.parametrize("offer_ids", [("",), ("offer-1", "offer-1")])
def test_mark_trip_offers_sent_rejects_invalid_offer_ids(
    store: SQLiteStore, trip: Trip, offer_ids: tuple[str, ...]
) -> None:
    store.create_trip(trip)

    with pytest.raises(ValueError):
        store.mark_trip_offers_sent(trip.trip_id, offer_ids)
