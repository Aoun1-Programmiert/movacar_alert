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
                   free_km, first_seen_timestamp, is_deleted, deleted_at
            FROM offers
            """
        ).fetchone() == (
            offer.id,
            offer.start_date.isoformat(),
            offer.end_date.isoformat(),
            "Berlin",
            "Paris",
            500,
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
