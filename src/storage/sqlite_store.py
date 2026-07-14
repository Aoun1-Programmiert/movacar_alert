"""SQLite persistence boundary."""

from __future__ import annotations

from collections.abc import Iterable
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from src.models.offer import Offer

LOGGER = logging.getLogger(__name__)


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
        """Create the offers table when it does not exist yet."""

        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS offers (
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
        except sqlite3.Error as exc:
            LOGGER.error("SQLite schema initialization failed: %s", exc)
            raise SQLiteStoreError("Could not initialize the SQLite schema.") from exc

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

        first_seen_timestamp = datetime.now().astimezone().isoformat()
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

        deleted_at = datetime.now().astimezone().isoformat()
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

        reference_time = datetime.now().astimezone() if now is None else now.astimezone()
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
