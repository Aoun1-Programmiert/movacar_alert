"""Tests for atomic trip-specific offer synchronization."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

import pytest

from src.models.offer import GeoLocation, Offer, Provider
from src.models.trip import Trip
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError
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


@pytest.fixture
def offer() -> Offer:
    return Offer(
        id="offer-1",
        start_date=datetime(2026, 7, 20, 8),
        end_date=datetime(2026, 7, 22, 8),
        free_km=500,
        origin=GeoLocation("Hamburg", 53.5511, 9.9937),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )


def test_synchronization_upserts_global_offer_and_creates_unsent_trip_relation(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    store.create_trip(trip)

    result = synchronize_trip_offers(store, trip, [offer])

    assert result.trip_id == trip.trip_id
    assert result.offer_ids == frozenset({offer.id})
    assert result.new_relation_ids == frozenset({offer.id})
    assert result.updated_relation_ids == frozenset()
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT id, free_km FROM offers"
        ).fetchall() == [(offer.id, 500)]
        relation = connection.execute(
            """
            SELECT trip_id, offer_id, distance_km, is_available,
                   unavailable_since, is_sent, sent_at
            FROM trip_offers
            """
        ).fetchone()

    assert relation[:2] == (trip.trip_id, offer.id)
    assert relation[2] == pytest.approx(255.3, abs=0.5)
    assert relation[3:] == (1, None, 0, None)


def test_existing_relation_is_refreshed_without_resetting_notification_state(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    store.create_trip(trip)
    synchronize_trip_offers(store, trip, [offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE trip_offers
            SET distance_km = 999,
                is_available = 0,
                unavailable_since = '2026-07-16T10:00:00+02:00',
                is_sent = 1,
                sent_at = '2026-07-16T11:00:00+02:00',
                first_seen_at = '2026-07-15T10:00:00+02:00',
                last_seen_at = '2026-07-15T10:00:00+02:00'
            """
        )

    changed_offer = Offer(
        id=offer.id,
        provider=Provider.MOVACAR,
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=750,
        origin=GeoLocation("Potsdam", 52.3906, 13.0645),
        destination=offer.destination,
    )
    result = synchronize_trip_offers(store, trip, [changed_offer])

    assert result.new_relation_ids == frozenset()
    assert result.updated_relation_ids == frozenset({offer.id})
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT origin_city, free_km FROM offers WHERE id = ?", (offer.id,)
        ).fetchone() == ("Potsdam", 750)
        relation = connection.execute(
            """
            SELECT distance_km, is_available, unavailable_since, is_sent, sent_at,
                   first_seen_at, last_seen_at
            FROM trip_offers
            """
        ).fetchone()

    assert relation[0] == pytest.approx(27.2, abs=0.5)
    assert relation[1:6] == (
        1,
        None,
        1,
        "2026-07-16T11:00:00+02:00",
        "2026-07-15T10:00:00+02:00",
    )
    assert relation[6] != "2026-07-15T10:00:00+02:00"


def test_global_offer_has_independent_novelty_for_each_trip(
    store: SQLiteStore, trip: Trip, offer: Offer
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
    store.create_trip(trip)
    store.create_trip(second_trip)
    synchronize_trip_offers(store, trip, [offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE trip_offers
            SET is_sent = 1, sent_at = '2026-07-16T11:00:00+02:00'
            WHERE trip_id = ?
            """,
            (trip.trip_id,),
        )

    second_result = synchronize_trip_offers(store, second_trip, [offer])

    assert second_result.new_relation_ids == frozenset({offer.id})
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM offers").fetchone() == (1,)
        assert connection.execute(
            """
            SELECT trip_id, is_sent
            FROM trip_offers
            ORDER BY trip_id
            """
        ).fetchall() == [(trip.trip_id, 1), (second_trip.trip_id, 0)]


def test_distance_failure_leaves_global_and_trip_state_unchanged(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    second_offer = Offer(
        id="offer-2",
        provider=Provider.MOVACAR,
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=offer.free_km,
        origin=GeoLocation("Cologne", 50.9375, 6.9603),
        destination=offer.destination,
    )
    store.create_trip(trip)
    call_count = 0

    def failing_calculator(
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
    ) -> float:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("distance calculation failed")
        return 1.0

    with pytest.raises(RuntimeError, match="distance calculation failed"):
        synchronize_trip_offers(
            store,
            trip,
            [offer, second_offer],
            distance_calculator=failing_calculator,
        )

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT * FROM offers").fetchall() == []
        assert connection.execute("SELECT * FROM trip_offers").fetchall() == []


def test_persistence_failure_rolls_back_global_upsert_and_relation(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    store.create_trip(trip)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER reject_trip_offer
            BEFORE INSERT ON trip_offers
            BEGIN
                SELECT RAISE(ABORT, 'injected relation failure');
            END
            """
        )

    with pytest.raises(SQLiteStoreError, match="Could not synchronize"):
        synchronize_trip_offers(store, trip, [offer])

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT * FROM offers").fetchall() == []
        assert connection.execute("SELECT * FROM trip_offers").fetchall() == []


def test_duplicate_movacar_ids_are_rejected_before_persistence(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    store.create_trip(trip)

    with pytest.raises(ValueError, match="unique Movacar IDs"):
        synchronize_trip_offers(store, trip, [offer, offer])

    assert store.read_offers() == {}


def test_successful_complete_synchronization_marks_missing_relations_unavailable(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    missing_offer = Offer(
        id="offer-2",
        provider=Provider.MOVACAR,
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=offer.free_km,
        origin=GeoLocation("Cologne", 50.9375, 6.9603),
        destination=offer.destination,
    )
    store.create_trip(trip)
    synchronize_trip_offers(store, trip, [offer, missing_offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE trip_offers
            SET is_sent = 1, sent_at = '2026-07-16T11:00:00+02:00'
            WHERE trip_id = ? AND offer_id = ?
            """,
            (trip.trip_id, missing_offer.id),
        )

    synchronize_trip_offers(store, trip, [offer])

    with sqlite3.connect(store.database_path) as connection:
        available, unavailable_since, is_sent, sent_at = connection.execute(
            """
            SELECT is_available, unavailable_since, is_sent, sent_at
            FROM trip_offers
            WHERE trip_id = ? AND offer_id = ?
            """,
            (trip.trip_id, missing_offer.id),
        ).fetchone()
    assert available == 0
    assert unavailable_since is not None
    datetime.fromisoformat(unavailable_since)
    assert (is_sent, sent_at) == (1, "2026-07-16T11:00:00+02:00")


def test_failed_synchronization_does_not_reconcile_existing_availability(
    store: SQLiteStore, trip: Trip, offer: Offer
) -> None:
    missing_offer = Offer(
        id="offer-2",
        provider=Provider.MOVACAR,
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=offer.free_km,
        origin=GeoLocation("Cologne", 50.9375, 6.9603),
        destination=offer.destination,
    )
    store.create_trip(trip)
    synchronize_trip_offers(store, trip, [offer, missing_offer])

    def failing_calculator(
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
    ) -> float:
        raise RuntimeError("simulated parser or API failure")

    with pytest.raises(RuntimeError, match="simulated parser or API failure"):
        synchronize_trip_offers(
            store,
            trip,
            [offer],
            distance_calculator=failing_calculator,
        )

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            """
            SELECT is_available, unavailable_since
            FROM trip_offers
            WHERE trip_id = ? AND offer_id = ?
            """,
            (trip.trip_id, missing_offer.id),
        ).fetchone() == (1, None)
