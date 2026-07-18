"""Unit tests for SQLite offer state operations."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from src.models.offer import GeoLocation, Offer
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError


@pytest.fixture
def offer() -> Offer:
    return Offer(
        id="offer-1",
        start_date=datetime(2026, 7, 14, 8, 0),
        end_date=datetime(2026, 7, 16, 8, 0),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        price_minor_units=1234,
        currency="EUR",
    )


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    database = SQLiteStore(tmp_path / "offers.sqlite")
    database.initialize_schema()
    return database


def test_read_returns_active_persisted_state(store: SQLiteStore, offer: Offer) -> None:
    store.insert_offers([offer])

    stored = store.read_offers()

    assert stored[offer.id].start_date == offer.start_date.isoformat()
    assert stored[offer.id].destination_city == "Paris"
    assert stored[offer.id].is_deleted is False
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            """
            SELECT id, start_date, end_date, origin_city, destination_city,
                   free_km, price_minor_units, currency, first_seen_timestamp,
                   is_deleted, deleted_at
            FROM offers
            """
        ).fetchone() == (
            offer.id,
            offer.start_date.isoformat(),
            offer.end_date.isoformat(),
            "Berlin",
            "Paris",
            500,
            1234,
            "EUR",
            stored[offer.id].first_seen_timestamp,
            0,
            None,
        )


def test_insert_rejects_invalid_offer(store: SQLiteStore) -> None:
    with pytest.raises(ValueError, match="Offer"):
        store.insert_offers([object()])  # type: ignore[list-item]


def test_soft_delete_marks_missing_ids_without_physical_delete(
    store: SQLiteStore, offer: Offer
) -> None:
    store.insert_offers([offer])

    assert store.soft_delete_removed_offers([]) == 1
    assert store.read_offers() == {}
    deleted = store.read_offers(include_deleted=True)[offer.id]
    assert deleted.is_deleted is True
    assert deleted.deleted_at is not None
    datetime.fromisoformat(deleted.deleted_at)


def test_insert_reactivates_soft_deleted_offer(store: SQLiteStore, offer: Offer) -> None:
    store.insert_offers([offer])
    store.soft_delete_removed_offers([])

    store.insert_offers([offer])

    reactivated = store.read_offers()[offer.id]
    assert reactivated.is_deleted is False
    assert reactivated.deleted_at is None
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM offers").fetchone() == (1,)


def test_existing_global_offer_creates_new_unsent_relation_when_seen_by_trip(
    store: SQLiteStore, offer: Offer
) -> None:
    store.insert_offers([offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES ('trip-1', 'Sommerfahrt', '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """
        )

    assert store.create_trip_offer("trip-1", offer.id, distance_km=12.5) is True

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            """
            SELECT trip_id, offer_id, distance_km, is_available, is_sent, sent_at
            FROM trip_offers
            """
        ).fetchall() == [("trip-1", offer.id, 12.5, 1, 0, None)]
        assert connection.execute("SELECT id FROM offers").fetchall() == [(offer.id,)]


def test_creating_existing_trip_offer_preserves_its_notification_state(
    store: SQLiteStore, offer: Offer
) -> None:
    store.insert_offers([offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES ('trip-1', 'Sommerfahrt', '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """
        )
        connection.execute(
            """
            INSERT INTO trip_offers (trip_id, offer_id, distance_km, is_sent, sent_at)
            VALUES ('trip-1', ?, 25, 1, '2026-07-14T12:00:00+02:00')
            """,
            (offer.id,),
        )

    assert store.create_trip_offer("trip-1", offer.id, distance_km=12.5) is False

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT distance_km, is_sent, sent_at FROM trip_offers"
        ).fetchone() == (25.0, 1, "2026-07-14T12:00:00+02:00")


@pytest.mark.parametrize(
    ("trip_id", "offer_id", "distance_km"),
    [
        ("", "offer-1", 1),
        ("trip-1", "", 1),
        ("trip-1", "offer-1", -1),
        ("trip-1", "offer-1", True),
        ("trip-1", "offer-1", float("nan")),
        ("trip-1", "offer-1", float("inf")),
    ],
)
def test_create_trip_offer_rejects_invalid_values(
    store: SQLiteStore, trip_id: str, offer_id: str, distance_km: float
) -> None:
    with pytest.raises(ValueError):
        store.create_trip_offer(trip_id, offer_id, distance_km=distance_km)


def test_database_failures_are_logged_explicit_and_recoverable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    broken_store = SQLiteStore(tmp_path / "missing" / "offers.sqlite")

    with caplog.at_level("ERROR"):
        with pytest.raises(SQLiteStoreError):
            broken_store.read_offers()

    assert "SQLite offer read failed" in caplog.text

    working_store = SQLiteStore(tmp_path / "offers.sqlite")
    working_store.initialize_schema()
    assert working_store.read_offers() == {}


def test_cleanup_preserves_ids_present_in_current_response(
    store: SQLiteStore, offer: Offer
) -> None:
    second_offer = Offer(
        id="offer-2",
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=offer.free_km,
        origin=offer.origin,
        destination=offer.destination,
    )
    store.insert_offers([offer, second_offer])

    assert store.soft_delete_removed_offers([offer.id]) == 1
    assert set(store.read_offers()) == {offer.id}
    assert set(store.read_offers(include_deleted=True)) == {offer.id, second_offer.id}


def test_cleanup_rejects_invalid_ids(store: SQLiteStore) -> None:
    with pytest.raises(ValueError, match="non-empty strings"):
        store.soft_delete_removed_offers([""])


def test_reconcile_trip_offer_availability_is_trip_scoped_and_preserves_sent_state(
    store: SQLiteStore, offer: Offer
) -> None:
    second_offer = Offer(
        id="offer-2",
        start_date=offer.start_date,
        end_date=offer.end_date,
        free_km=offer.free_km,
        origin=offer.origin,
        destination=offer.destination,
    )
    store.insert_offers([offer, second_offer])
    with sqlite3.connect(store.database_path) as connection:
        connection.executemany(
            """
            INSERT INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES (?, ?, '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """,
            [("trip-1", "Sommerfahrt"), ("trip-2", "Herbstfahrt")],
        )
    store.create_trip_offer("trip-1", offer.id, distance_km=12.5)
    store.create_trip_offer("trip-1", second_offer.id, distance_km=25)
    store.create_trip_offer("trip-2", second_offer.id, distance_km=50)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            UPDATE trip_offers
            SET is_sent = 1, sent_at = '2026-07-16T11:00:00+02:00'
            WHERE trip_id = 'trip-1' AND offer_id = 'offer-2'
            """
        )

    assert store.reconcile_trip_offer_availability("trip-1", {offer.id}) == 1

    with sqlite3.connect(store.database_path) as connection:
        rows = connection.execute(
            """
            SELECT trip_id, offer_id, is_available, unavailable_since, is_sent, sent_at
            FROM trip_offers
            ORDER BY trip_id, offer_id
            """
        ).fetchall()
    assert rows[0] == ("trip-1", "offer-1", 1, None, 0, None)
    assert rows[1][:3] == ("trip-1", "offer-2", 0)
    assert rows[1][4:] == (1, "2026-07-16T11:00:00+02:00")
    assert rows[1][3] is not None
    datetime.fromisoformat(rows[1][3])
    assert rows[2] == ("trip-2", "offer-2", 1, None, 0, None)


@pytest.mark.parametrize("complete_offer_ids", [("",), ("offer-1", "offer-1")])
def test_reconcile_trip_offer_availability_rejects_invalid_complete_ids_without_changes(
    store: SQLiteStore, offer: Offer, complete_offer_ids: tuple[str, ...]
) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES ('trip-1', 'Sommerfahrt', '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """
        )
    store.insert_offers([offer])
    store.create_trip_offer("trip-1", offer.id, distance_km=12.5)

    with pytest.raises(ValueError):
        store.reconcile_trip_offer_availability("trip-1", complete_offer_ids)

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT is_available, unavailable_since FROM trip_offers"
        ).fetchone() == (1, None)
