"""Unit tests for SQLite schema initialization."""

import sqlite3
from pathlib import Path

import pytest

from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError


def test_initialize_schema_creates_offers_table_with_required_columns(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "offers.sqlite"

    SQLiteStore(database_path).initialize_schema()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]: {"type": row[2], "notnull": row[3], "default": row[4], "pk": row[5]}
            for row in connection.execute("PRAGMA table_info(offers)")
        }

    assert set(columns) == {
        "id",
        "start_date",
        "end_date",
        "origin_city",
        "destination_city",
        "free_km",
        "first_seen_timestamp",
        "is_deleted",
        "deleted_at",
    }
    assert columns["id"]["pk"] == 1
    assert columns["is_deleted"]["type"] == "INTEGER"
    assert columns["is_deleted"]["notnull"] == 1
    assert columns["is_deleted"]["default"] == "0"
    assert columns["deleted_at"]["type"] == "TEXT"
    assert columns["deleted_at"]["notnull"] == 0


def test_initialize_schema_records_version_and_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "offers.sqlite"
    store = SQLiteStore(database_path)

    store.initialize_schema()
    with sqlite3.connect(database_path) as connection:
        first_metadata = connection.execute(
            "SELECT version, applied_at FROM schema_migrations"
        ).fetchall()

    store.initialize_schema()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version, applied_at FROM schema_migrations"
        ).fetchall() == first_metadata

    assert first_metadata and first_metadata[0][0] == 1


def test_initialize_schema_baselines_existing_unversioned_offers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "offers.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE offers (
                id TEXT PRIMARY KEY,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                origin_city TEXT NOT NULL,
                destination_city TEXT NOT NULL,
                free_km INTEGER NOT NULL,
                first_seen_timestamp TEXT NOT NULL,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, destination_city,
                free_km, first_seen_timestamp
            ) VALUES ('legacy', '2026-07-14', '2026-07-15', 'Berlin', 'Paris', 1, 'now')
            """
        )

    SQLiteStore(database_path).initialize_schema()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall() == [(1,)]
        assert connection.execute("SELECT id FROM offers").fetchall() == [("legacy",)]


def test_failed_baseline_does_not_activate_migration(tmp_path: Path) -> None:
    database_path = tmp_path / "offers.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE offers (id TEXT PRIMARY KEY)")

    with pytest.raises(SQLiteStoreError, match="initialize the SQLite schema"):
        SQLiteStore(database_path).initialize_schema()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone() is None


def test_initialize_schema_is_idempotent_and_preserves_existing_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "offers.sqlite"
    store = SQLiteStore(database_path)
    store.initialize_schema()

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, destination_city,
                free_km, first_seen_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "offer-1",
                "2026-07-14T08:00:00",
                "2026-07-16T08:00:00",
                "Berlin",
                "Paris",
                500,
                "2026-07-14T09:00:00",
            ),
        )

    store.initialize_schema()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM offers").fetchone() == (1,)
        assert connection.execute(
            "SELECT id, is_deleted, deleted_at FROM offers"
        ).fetchone() == ("offer-1", 0, None)
