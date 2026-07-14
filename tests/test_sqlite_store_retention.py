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
