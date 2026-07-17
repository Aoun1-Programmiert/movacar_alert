"""Unit tests for SQLite soft-delete retention."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.storage.sqlite_store import SQLiteStore


@pytest.fixture
def store(tmp_path: Path) -> SQLiteStore:
    database = SQLiteStore(tmp_path / "offers.sqlite")
    database.initialize_schema()
    return database


def insert_offer(
    store: SQLiteStore,
    offer_id: str,
    *,
    deleted: bool,
    deleted_at: datetime | None,
) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, destination_city,
                free_km, first_seen_timestamp, is_deleted, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                offer_id,
                "2026-07-14T08:00:00",
                "2026-07-16T08:00:00",
                "Berlin",
                "Paris",
                500,
                "2026-07-14T09:00:00",
                int(deleted),
                deleted_at.isoformat() if deleted_at is not None else None,
            ),
        )


def test_purge_keeps_soft_delete_younger_than_14_days(
    store: SQLiteStore,
) -> None:
    now = datetime.now().astimezone()
    insert_offer(
        store,
        "young",
        deleted=True,
        deleted_at=now - timedelta(days=14) + timedelta(seconds=1),
    )

    assert store.purge_soft_deleted_offers(now=now) == 0
    assert "young" in store.read_offers(include_deleted=True)


def test_purge_removes_soft_delete_older_than_14_days(store: SQLiteStore) -> None:
    now = datetime.now().astimezone()
    insert_offer(
        store,
        "old",
        deleted=True,
        deleted_at=now - timedelta(days=14, seconds=1),
    )

    assert store.purge_soft_deleted_offers(now=now) == 1
    assert store.read_offers(include_deleted=True) == {}


def test_purge_keeps_soft_delete_at_14_day_boundary_and_is_idempotent(
    store: SQLiteStore,
) -> None:
    now = datetime.now().astimezone()
    insert_offer(
        store,
        "boundary",
        deleted=True,
        deleted_at=now - timedelta(days=14),
    )
    insert_offer(
        store,
        "active",
        deleted=False,
        deleted_at=None,
    )

    assert store.purge_soft_deleted_offers(now=now) == 0
    assert store.purge_soft_deleted_offers(now=now) == 0
    assert set(store.read_offers(include_deleted=True)) == {"boundary", "active"}


def insert_trip_offer(
    store: SQLiteStore,
    trip_id: str,
    offer_id: str,
    *,
    unavailable_since: datetime | None,
) -> None:
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES (?, ?, '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """,
            (trip_id, trip_id),
        )
        connection.execute(
            """
            INSERT INTO trip_offers (
                trip_id, offer_id, distance_km, is_available, unavailable_since
            ) VALUES (?, ?, 10, ?, ?)
            """,
            (
                trip_id,
                offer_id,
                int(unavailable_since is None),
                unavailable_since.isoformat() if unavailable_since else None,
            ),
        )


def test_purge_unavailable_trip_offers_removes_expired_relation_and_orphan(
    store: SQLiteStore,
) -> None:
    now = datetime.now().astimezone()
    insert_offer(store, "expired", deleted=False, deleted_at=None)
    insert_trip_offer(
        store,
        "trip-1",
        "expired",
        unavailable_since=now - timedelta(days=14, seconds=1),
    )

    assert store.purge_unavailable_trip_offers(now=now) == 1

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT * FROM trip_offers").fetchall() == []
        assert connection.execute("SELECT * FROM offers").fetchall() == []


def test_purge_unavailable_trip_offers_keeps_shared_offer_and_boundary_relation(
    store: SQLiteStore,
) -> None:
    now = datetime.now().astimezone()
    insert_offer(store, "shared", deleted=False, deleted_at=None)
    insert_offer(store, "boundary", deleted=False, deleted_at=None)
    insert_trip_offer(
        store,
        "trip-1",
        "shared",
        unavailable_since=now - timedelta(days=14, seconds=1),
    )
    insert_trip_offer(store, "trip-2", "shared", unavailable_since=None)
    insert_trip_offer(
        store,
        "trip-1",
        "boundary",
        unavailable_since=now - timedelta(days=14),
    )

    assert store.purge_unavailable_trip_offers(now=now) == 1
    assert store.purge_unavailable_trip_offers(now=now) == 0

    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute(
            "SELECT id FROM offers ORDER BY id"
        ).fetchall() == [("boundary",), ("shared",)]
        assert connection.execute(
            """
            SELECT trip_id, offer_id, is_available
            FROM trip_offers
            ORDER BY offer_id, trip_id
            """
        ).fetchall() == [
            ("trip-1", "boundary", 0),
            ("trip-2", "shared", 1),
        ]
