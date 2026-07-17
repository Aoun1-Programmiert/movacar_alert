"""SQLite persistence boundary."""

from __future__ import annotations

from collections.abc import Iterable
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.config.timezone import LOCAL_TIMEZONE
from src.models.offer import Offer

LOGGER = logging.getLogger("movacar_alert.storage.sqlite_store")

SCHEMA_VERSION = 1
_MIGRATIONS_TABLE = "schema_migrations"
_OFFERS_COLUMNS = {
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


class SQLiteStoreError(RuntimeError):
    """Raised when a database operation cannot be completed."""


@dataclass(frozen=True)
class StoredOffer:
    """The persisted fields needed to calculate the next offer delta."""

    id: str
    start_date: str
    end_date: str
    origin_city: str
    destination_city: str
    free_km: int
    first_seen_timestamp: str
    is_deleted: bool
    deleted_at: str | None


class SQLiteStore:
    """Owns the local SQLite database used for offer state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize_schema(self) -> None:
        """Apply all SQLite migrations atomically and idempotently."""

        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("BEGIN")
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                applied_versions = {
                    row[0]
                    for row in connection.execute(
                        f"SELECT version FROM {_MIGRATIONS_TABLE}"
                    )
                }
                if SCHEMA_VERSION not in applied_versions:
                    self._apply_offers_baseline(connection)
                    connection.execute(
                        f"""
                        INSERT INTO {_MIGRATIONS_TABLE} (version, applied_at)
                        VALUES (?, ?)
                        """,
                        (
                            SCHEMA_VERSION,
                            datetime.now(LOCAL_TIMEZONE).isoformat(),
                        ),
                    )
                connection.commit()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite schema initialization failed: %s", exc)
            raise SQLiteStoreError("Could not initialize the SQLite schema.") from exc

    @staticmethod
    def _apply_offers_baseline(connection: sqlite3.Connection) -> None:
        """Create or validate the unversioned offers baseline."""

        offers_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table' AND name = 'offers'
            """
        ).fetchone()
        if offers_exists is None:
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
            return

        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(offers)")
        }
        if not _OFFERS_COLUMNS.issubset(existing_columns):
            missing_columns = ", ".join(sorted(_OFFERS_COLUMNS - existing_columns))
            raise sqlite3.DatabaseError(
                f"Existing offers table is missing required columns: {missing_columns}"
            )

    def read_offers(self, *, include_deleted: bool = False) -> dict[str, StoredOffer]:
        """Read persisted offers for the next delta calculation."""

        query = """
            SELECT id, start_date, end_date, origin_city, destination_city,
                   free_km, first_seen_timestamp, is_deleted, deleted_at
            FROM offers
        """
        parameters: tuple[object, ...] = ()
        if not include_deleted:
            query += " WHERE is_deleted = 0"

        try:
            with sqlite3.connect(self.database_path) as connection:
                rows = connection.execute(query, parameters).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite offer read failed: %s", exc)
            raise SQLiteStoreError("Could not read offers from SQLite.") from exc

        return {
            row[0]: StoredOffer(
                id=row[0],
                start_date=row[1],
                end_date=row[2],
                origin_city=row[3],
                destination_city=row[4],
                free_km=row[5],
                first_seen_timestamp=row[6],
                is_deleted=bool(row[7]),
                deleted_at=row[8],
            )
            for row in rows
        }

    def insert_offers(self, offers: Iterable[Offer]) -> None:
        """Persist valid offers and reactivate previously soft-deleted ones."""

        validated_offers = tuple(offers)
        if any(not isinstance(offer, Offer) for offer in validated_offers):
            raise ValueError("insert_offers accepts only valid Offer instances.")

        first_seen_timestamp = datetime.now(LOCAL_TIMEZONE).isoformat()
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.executemany(
                    """
                    INSERT INTO offers (
                        id, start_date, end_date, origin_city, destination_city,
                        free_km, first_seen_timestamp, is_deleted, deleted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL)
                    ON CONFLICT(id) DO UPDATE SET
                        start_date = excluded.start_date,
                        end_date = excluded.end_date,
                        origin_city = excluded.origin_city,
                        destination_city = excluded.destination_city,
                        free_km = excluded.free_km,
                        is_deleted = 0,
                        deleted_at = NULL
                    """,
                    (
                        (
                            offer.id,
                            offer.start_date.isoformat(),
                            offer.end_date.isoformat(),
                            offer.origin.city,
                            offer.destination.city,
                            offer.free_km,
                            first_seen_timestamp,
                        )
                        for offer in validated_offers
                    ),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite offer insert failed: %s", exc)
            raise SQLiteStoreError("Could not insert offers into SQLite.") from exc

    def soft_delete_removed_offers(self, active_offer_ids: Iterable[str]) -> int:
        """Mark persisted offers absent from the API response as deleted."""

        ids = tuple(active_offer_ids)
        if any(not isinstance(offer_id, str) or not offer_id.strip() for offer_id in ids):
            raise ValueError("active_offer_ids must contain non-empty strings.")

        deleted_at = datetime.now(LOCAL_TIMEZONE).isoformat()
        try:
            with sqlite3.connect(self.database_path) as connection:
                if ids:
                    placeholders = ", ".join("?" for _ in ids)
                    cursor = connection.execute(
                        f"""
                        UPDATE offers
                        SET is_deleted = 1, deleted_at = ?
                        WHERE is_deleted = 0 AND id NOT IN ({placeholders})
                        """,
                        (deleted_at, *ids),
                    )
                else:
                    cursor = connection.execute(
                        """
                        UPDATE offers
                        SET is_deleted = 1, deleted_at = ?
                        WHERE is_deleted = 0
                        """,
                        (deleted_at,),
                    )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite offer cleanup failed: %s", exc)
            raise SQLiteStoreError("Could not soft-delete removed offers.") from exc

        return cursor.rowcount

    def purge_soft_deleted_offers(self, *, now: datetime | None = None) -> int:
        """Permanently remove soft-deleted offers older than 14 local days."""

        reference_time = (
            datetime.now(LOCAL_TIMEZONE)
            if now is None
            else now.astimezone(LOCAL_TIMEZONE)
        )
        cutoff = reference_time - timedelta(days=14)
        try:
            with sqlite3.connect(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    DELETE FROM offers
                    WHERE is_deleted = 1
                      AND deleted_at IS NOT NULL
                      AND datetime(deleted_at) < datetime(?)
                    """,
                    (cutoff.isoformat(),),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite soft-delete purge failed: %s", exc)
            raise SQLiteStoreError("Could not purge expired soft-deleted offers.") from exc

        return cursor.rowcount
