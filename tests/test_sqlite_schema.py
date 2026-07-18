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
        "origin_latitude",
        "origin_longitude",
        "destination_city",
        "destination_latitude",
        "destination_longitude",
        "free_km",
        "price_minor_units",
        "currency",
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

    assert [version for version, _ in first_metadata] == [1, 2, 3, 4]


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
        ).fetchall() == [(1,), (2,), (3,), (4,)]
        assert connection.execute("SELECT id FROM offers").fetchall() == [("legacy",)]
        assert connection.execute(
            """
            SELECT origin_latitude, origin_longitude,
                   destination_latitude, destination_longitude
            FROM offers WHERE id = 'legacy'
            """
        ).fetchone() == (None, None, None, None)


def test_initialize_schema_adds_trip_schema_to_version_one_database(
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
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (1, '2026-07-17T12:00:00+02:00')"
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
        ).fetchall() == [(1,), (2,), (3,), (4,)]
        assert connection.execute("SELECT id FROM offers").fetchall() == [("legacy",)]
        assert {
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name IN ('trips', 'trip_recipients', 'trip_offers', 'trip_overview_slots')
                """
            )
        } == {"trips", "trip_recipients", "trip_offers", "trip_overview_slots"}
        assert connection.execute("SELECT * FROM trip_offers").fetchall() == []


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


def test_trip_schema_has_required_identities_and_foreign_keys(tmp_path: Path) -> None:
    database_path = tmp_path / "offers.sqlite"

    SQLiteStore(database_path).initialize_schema()

    with sqlite3.connect(database_path) as connection:
        trip_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(trips)")
        }
        assert trip_columns == {
            "trip_id",
            "name",
            "pickup_start",
            "pickup_end",
            "start_city",
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
        }
        assert {
            row[1] for row in connection.execute("PRAGMA table_info(trip_recipients)")
        } == {"trip_id", "normalized_email", "created_at"}
        assert {
            row[1] for row in connection.execute("PRAGMA table_info(trip_offers)")
        } == {
            "trip_id",
            "offer_id",
            "distance_km",
            "is_available",
            "first_seen_at",
            "last_seen_at",
            "unavailable_since",
            "is_sent",
            "sent_at",
        }
        assert {
            row[1] for row in connection.execute("PRAGMA table_info(trip_overview_slots)")
        } == {"trip_id", "local_date", "slot_hour", "sent_at"}

        assert connection.execute(
            "PRAGMA index_info(sqlite_autoindex_trip_recipients_1)"
        ).fetchall() == [(0, 0, "trip_id"), (1, 1, "normalized_email")]
        assert connection.execute(
            "PRAGMA index_info(sqlite_autoindex_trip_offers_1)"
        ).fetchall() == [(0, 0, "trip_id"), (1, 1, "offer_id")]
        assert connection.execute(
            "PRAGMA index_info(sqlite_autoindex_trip_overview_slots_1)"
        ).fetchall() == [
            (0, 0, "trip_id"),
            (1, 1, "local_date"),
            (2, 2, "slot_hour"),
        ]

        assert {
            (row[2], row[3], row[6])
            for row in connection.execute("PRAGMA foreign_key_list(trip_offers)")
        } == {
            ("offers", "offer_id", "NO ACTION"),
            ("trips", "trip_id", "CASCADE"),
        }


def test_deleting_trip_cascades_trip_data_but_retains_global_offer(tmp_path: Path) -> None:
    database_path = tmp_path / "offers.sqlite"
    SQLiteStore(database_path).initialize_schema()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, destination_city,
                free_km, first_seen_timestamp
            ) VALUES ('offer-1', '2026-07-14', '2026-07-15', 'Berlin', 'Paris', 1, 'now')
            """
        )
        connection.execute(
            """
            INSERT INTO trips (
                trip_id, name, pickup_start, pickup_end, start_city, latitude, longitude
            ) VALUES ('trip-1', 'Sommerfahrt', '2026-07-14', '2026-07-20', 'Berlin', 52.52, 13.405)
            """
        )
        connection.execute(
            "INSERT INTO trip_recipients (trip_id, normalized_email) VALUES ('trip-1', 'a@example.com')"
        )
        connection.execute(
            "INSERT INTO trip_offers (trip_id, offer_id, distance_km) VALUES ('trip-1', 'offer-1', 10)"
        )
        connection.execute(
            "INSERT INTO trip_overview_slots (trip_id, local_date, slot_hour) VALUES ('trip-1', '2026-07-14', 9)"
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO trip_recipients (trip_id, normalized_email) VALUES ('trip-1', 'a@example.com')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO trip_offers (trip_id, offer_id, distance_km) VALUES ('trip-1', 'offer-1', 20)"
            )

        connection.execute("DELETE FROM trips WHERE trip_id = 'trip-1'")

        assert connection.execute("SELECT * FROM trip_recipients").fetchall() == []
        assert connection.execute("SELECT * FROM trip_offers").fetchall() == []
        assert connection.execute("SELECT * FROM trip_overview_slots").fetchall() == []
        assert connection.execute("SELECT id FROM offers").fetchall() == [("offer-1",)]
