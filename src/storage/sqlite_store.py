"""SQLite persistence boundary."""

from __future__ import annotations

from collections.abc import Iterable
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import isfinite
from pathlib import Path

from src.config.timezone import LOCAL_TIMEZONE
from src.models.offer import DistanceTier, GeoLocation, Offer, Provider, TripOfferView
from src.models.trip import Trip, TripRecipient
from src.validation.trip_validation import normalize_email, validate_trip_id

LOGGER = logging.getLogger("movacar_alert.storage.sqlite_store")

SCHEMA_VERSION = 5
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


class TripNotFoundError(SQLiteStoreError):
    """Raised when a requested trip does not exist."""


class DuplicateTripRecipientError(SQLiteStoreError):
    """Raised when a recipient is already assigned to a trip."""


@dataclass(frozen=True)
class StoredOffer:
    """The persisted fields needed to calculate the next offer delta."""

    id: str
    start_date: str
    end_date: str
    origin_city: str
    destination_city: str
    free_km: int
    price_minor_units: int | None
    currency: str | None
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
                connection.execute("PRAGMA foreign_keys = ON")
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
                if 1 not in applied_versions:
                    self._apply_offers_baseline(connection)
                    self._record_migration(connection, 1)
                if 2 not in applied_versions:
                    self._apply_trip_schema(connection)
                    self._record_migration(connection, 2)
                if 3 not in applied_versions:
                    self._apply_offer_coordinate_schema(connection)
                    self._record_migration(connection, 3)
                if 4 not in applied_versions:
                    self._apply_offer_price_schema(connection)
                    self._record_migration(connection, 4)
                if 5 not in applied_versions:
                    self._apply_provider_schema(connection)
                    self._record_migration(connection, 5)
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
                    price_minor_units INTEGER NULL,
                    currency TEXT NULL,
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

    @staticmethod
    def _record_migration(connection: sqlite3.Connection, version: int) -> None:
        """Record a migration only after its schema changes succeeded."""

        connection.execute(
            f"""
            INSERT INTO {_MIGRATIONS_TABLE} (version, applied_at)
            VALUES (?, ?)
            """,
            (version, datetime.now(LOCAL_TIMEZONE).isoformat()),
        )

    @staticmethod
    def _apply_trip_schema(connection: sqlite3.Connection) -> None:
        """Create the trip-scoped persistence tables and their relationships."""

        connection.execute(
            """
            CREATE TABLE trips (
                trip_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                pickup_start TEXT NOT NULL,
                pickup_end TEXT NOT NULL,
                start_city TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE trip_recipients (
                trip_id TEXT NOT NULL,
                normalized_email TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (trip_id, normalized_email),
                FOREIGN KEY (trip_id) REFERENCES trips(trip_id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE trip_offers (
                trip_id TEXT NOT NULL,
                offer_id TEXT NOT NULL,
                distance_km REAL NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1
                    CHECK (is_available IN (0, 1)),
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                unavailable_since TEXT NULL,
                is_sent INTEGER NOT NULL DEFAULT 0 CHECK (is_sent IN (0, 1)),
                sent_at TEXT NULL,
                PRIMARY KEY (trip_id, offer_id),
                FOREIGN KEY (trip_id) REFERENCES trips(trip_id) ON DELETE CASCADE,
                FOREIGN KEY (offer_id) REFERENCES offers(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE trip_overview_slots (
                trip_id TEXT NOT NULL,
                local_date TEXT NOT NULL,
                slot_hour INTEGER NOT NULL,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (trip_id, local_date, slot_hour),
                FOREIGN KEY (trip_id) REFERENCES trips(trip_id) ON DELETE CASCADE
            )
            """
        )

    @staticmethod
    def _apply_offer_coordinate_schema(connection: sqlite3.Connection) -> None:
        """Add station coordinates needed to reconstruct trip offer views."""

        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(offers)")
        }
        coordinate_columns = (
            "origin_latitude",
            "origin_longitude",
            "destination_latitude",
            "destination_longitude",
        )
        for column in coordinate_columns:
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE offers ADD COLUMN {column} REAL")

    @staticmethod
    def _apply_offer_price_schema(connection: sqlite3.Connection) -> None:
        """Add the optional monetary amount returned for an offer."""

        existing_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(offers)")
        }
        price_columns = (
            ("price_minor_units", "INTEGER"),
            ("currency", "TEXT"),
        )
        for column, column_type in price_columns:
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE offers ADD COLUMN {column} {column_type}"
                )

    @staticmethod
    def _apply_provider_schema(connection: sqlite3.Connection) -> None:
        """Add the per-provider columns and provider-scope the overview slots.

        ``offers`` and ``trips`` gain an additive ``provider`` column. The
        ``trip_overview_slots`` primary key must change from
        ``(trip_id, local_date, slot_hour)`` to include ``provider`` so both
        providers of one trip keep independent slots. SQLite cannot alter a
        primary key in place, so the table is rebuilt and a unique index on the
        four-column key replaces the former primary-key uniqueness.
        """

        for table in ("offers", "trips"):
            existing_columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if "provider" not in existing_columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN provider "
                    "TEXT NOT NULL DEFAULT 'movacar'"
                )

        slot_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(trip_overview_slots)")
        }
        if "provider" not in slot_columns:
            connection.execute(
                """
                CREATE TABLE trip_overview_slots_v5 (
                    trip_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    slot_hour INTEGER NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'movacar',
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trip_id) REFERENCES trips(trip_id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO trip_overview_slots_v5 (
                    trip_id, local_date, slot_hour, sent_at
                )
                SELECT trip_id, local_date, slot_hour, sent_at
                FROM trip_overview_slots
                """
            )
            connection.execute("DROP TABLE trip_overview_slots")
            connection.execute(
                "ALTER TABLE trip_overview_slots_v5 RENAME TO trip_overview_slots"
            )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_overview_slots_provider
            ON trip_overview_slots (trip_id, local_date, slot_hour, provider)
            """
        )

    def read_offers(self, *, include_deleted: bool = False) -> dict[str, StoredOffer]:
        """Read persisted offers for the next delta calculation."""

        query = """
            SELECT id, start_date, end_date, origin_city, destination_city,
                   free_km, price_minor_units, currency, first_seen_timestamp,
                   is_deleted, deleted_at
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
                price_minor_units=row[6],
                currency=row[7],
                first_seen_timestamp=row[8],
                is_deleted=bool(row[9]),
                deleted_at=row[10],
            )
            for row in rows
        }

    def create_trip(self, trip: Trip) -> None:
        """Persist a trip configuration."""

        if not isinstance(trip, Trip):
            raise ValueError("create_trip accepts only a valid Trip instance.")

        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO trips (
                        trip_id, name, pickup_start, pickup_end, start_city,
                        latitude, longitude
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trip.trip_id,
                        trip.name,
                        trip.pickup_start.isoformat(),
                        trip.pickup_end.isoformat(),
                        trip.start_city,
                        trip.latitude,
                        trip.longitude,
                    ),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip creation failed: %s", exc)
            raise SQLiteStoreError("Could not create trip in SQLite.") from exc

    def list_trips(self) -> list[Trip]:
        """Return all persisted trips ordered by their stable identity."""

        try:
            with sqlite3.connect(self.database_path) as connection:
                rows = connection.execute(
                    """
                    SELECT trip_id, name, pickup_start, pickup_end, start_city,
                           latitude, longitude
                    FROM trips
                    ORDER BY trip_id
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip listing failed: %s", exc)
            raise SQLiteStoreError("Could not list trips from SQLite.") from exc

        return [
            Trip(
                trip_id=row[0],
                name=row[1],
                pickup_start=datetime.fromisoformat(row[2]).date(),
                pickup_end=datetime.fromisoformat(row[3]).date(),
                start_city=row[4],
                latitude=row[5],
                longitude=row[6],
            )
            for row in rows
        ]

    def delete_trip(self, trip_id: str) -> None:
        """Delete one trip and all of its trip-scoped state."""

        trip_id = validate_trip_id(trip_id)
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                cursor = connection.execute(
                    "DELETE FROM trips WHERE trip_id = ?", (trip_id,)
                )
                if cursor.rowcount == 0:
                    raise TripNotFoundError(f"Trip {trip_id!r} does not exist.")
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip deletion failed: %s", exc)
            raise SQLiteStoreError("Could not delete trip from SQLite.") from exc

    def add_trip_recipient(self, trip_id: str, normalized_email: str) -> None:
        """Assign one normalized recipient address to an existing trip."""

        trip_id = validate_trip_id(trip_id)
        normalized_email = normalize_email(normalized_email)
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)
                try:
                    connection.execute(
                        """
                        INSERT INTO trip_recipients (trip_id, normalized_email)
                        VALUES (?, ?)
                        """,
                        (trip_id, normalized_email),
                    )
                except sqlite3.IntegrityError as exc:
                    raise DuplicateTripRecipientError(
                        f"Recipient {normalized_email!r} already belongs to trip {trip_id!r}."
                    ) from exc
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip recipient creation failed: %s", exc)
            raise SQLiteStoreError("Could not add trip recipient in SQLite.") from exc

    def remove_trip_recipient(self, trip_id: str, normalized_email: str) -> None:
        """Remove one recipient assignment from an existing trip."""

        trip_id = validate_trip_id(trip_id)
        normalized_email = normalize_email(normalized_email)
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)
                connection.execute(
                    """
                    DELETE FROM trip_recipients
                    WHERE trip_id = ? AND normalized_email = ?
                    """,
                    (trip_id, normalized_email),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip recipient deletion failed: %s", exc)
            raise SQLiteStoreError("Could not remove trip recipient from SQLite.") from exc

    def list_trip_recipients(self, trip_id: str) -> list[TripRecipient]:
        """Return the recipients assigned to one existing trip."""

        trip_id = validate_trip_id(trip_id)
        try:
            with sqlite3.connect(self.database_path) as connection:
                self._require_trip(connection, trip_id)
                rows = connection.execute(
                    """
                    SELECT trip_id, normalized_email
                    FROM trip_recipients
                    WHERE trip_id = ?
                    ORDER BY normalized_email
                    """,
                    (trip_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip recipient listing failed: %s", exc)
            raise SQLiteStoreError("Could not list trip recipients from SQLite.") from exc

        return [TripRecipient(trip_id=row[0], normalized_email=row[1]) for row in rows]

    def list_new_unsent_available_trip_offers(
        self, trip_id: str
    ) -> list[TripOfferView]:
        """Return new, available and unsent offers for exactly one trip."""

        return self._list_trip_offer_views(
            trip_id,
            """
            AND trip_offers.is_available = 1
            AND trip_offers.is_sent = 0
            """,
        )

    def list_available_trip_offers(self, trip_id: str) -> list[TripOfferView]:
        """Return all available offers for exactly one trip."""

        return self._list_trip_offer_views(
            trip_id,
            "AND trip_offers.is_available = 1",
        )

    def _list_trip_offer_views(
        self, trip_id: str, relation_filters: str
    ) -> list[TripOfferView]:
        trip_id = validate_trip_id(trip_id)
        try:
            with sqlite3.connect(self.database_path) as connection:
                self._require_trip(connection, trip_id)
                rows = connection.execute(
                    f"""
                    SELECT
                        trips.trip_id, trips.name, trips.pickup_start, trips.pickup_end,
                        trips.start_city, trips.latitude, trips.longitude,
                        offers.id, offers.start_date, offers.end_date, offers.free_km,
                        offers.price_minor_units, offers.currency,
                        offers.origin_city, offers.origin_latitude, offers.origin_longitude,
                        offers.destination_city, offers.destination_latitude,
                        offers.destination_longitude,
                        trip_offers.distance_km, trip_offers.is_available,
                        trip_offers.is_sent
                    FROM trip_offers
                    JOIN trips ON trips.trip_id = trip_offers.trip_id
                    JOIN offers ON offers.id = trip_offers.offer_id
                    WHERE trip_offers.trip_id = ?
                    {relation_filters}
                    ORDER BY trip_offers.distance_km ASC, trip_offers.offer_id ASC
                    """,
                    (trip_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip-offer view read failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not read offer views for trip {trip_id!r}."
            ) from exc

        try:
            return [self._to_trip_offer_view(row) for row in rows]
        except (TypeError, ValueError) as exc:
            LOGGER.error("SQLite trip-offer view contains incomplete data: %s", exc)
            raise SQLiteStoreError(
                f"Could not reconstruct offer views for trip {trip_id!r}."
            ) from exc

    @staticmethod
    def _to_trip_offer_view(row: tuple[object, ...]) -> TripOfferView:
        (
            trip_id,
            trip_name,
            pickup_start,
            pickup_end,
            start_city,
            trip_latitude,
            trip_longitude,
            offer_id,
            start_date,
            end_date,
            free_km,
            price_minor_units,
            currency,
            origin_city,
            origin_latitude,
            origin_longitude,
            destination_city,
            destination_latitude,
            destination_longitude,
            distance_km,
            is_available,
            is_sent,
        ) = row
        trip = Trip(
            trip_id=trip_id,
            name=trip_name,
            pickup_start=datetime.fromisoformat(pickup_start).date(),
            pickup_end=datetime.fromisoformat(pickup_end).date(),
            start_city=start_city,
            latitude=trip_latitude,
            longitude=trip_longitude,
        )
        offer = Offer(
            id=offer_id,
            start_date=datetime.fromisoformat(start_date),
            end_date=datetime.fromisoformat(end_date),
            free_km=free_km,
            origin=GeoLocation(origin_city, origin_latitude, origin_longitude),
            destination=GeoLocation(
                destination_city, destination_latitude, destination_longitude
            ),
            provider=Provider.MOVACAR,
            price_minor_units=price_minor_units,
            currency=currency,
        )
        state = "new" if not is_sent else "existing"
        return TripOfferView(
            trip=trip,
            offer=offer,
            distance_km=distance_km,
            is_available=bool(is_available),
            state=state,
            is_sent=bool(is_sent),
            distance_tier=DistanceTier.for_distance(distance_km),
        )

    @staticmethod
    def _require_trip(connection: sqlite3.Connection, trip_id: str) -> None:
        if connection.execute(
            "SELECT 1 FROM trips WHERE trip_id = ?", (trip_id,)
        ).fetchone() is None:
            raise TripNotFoundError(f"Trip {trip_id!r} does not exist.")

    def insert_offers(self, offers: Iterable[Offer]) -> None:
        """Persist valid offers and reactivate previously soft-deleted ones."""

        validated_offers = tuple(offers)
        if any(not isinstance(offer, Offer) for offer in validated_offers):
            raise ValueError("insert_offers accepts only valid Offer instances.")

        first_seen_timestamp = datetime.now(LOCAL_TIMEZONE).isoformat()
        try:
            with sqlite3.connect(self.database_path) as connection:
                self._upsert_offers(connection, validated_offers, first_seen_timestamp)
        except sqlite3.Error as exc:
            LOGGER.error("SQLite offer insert failed: %s", exc)
            raise SQLiteStoreError("Could not insert offers into SQLite.") from exc

    def synchronize_trip_offers(
        self,
        trip_id: str,
        offers_with_distances: Iterable[tuple[Offer, float]],
    ) -> frozenset[str]:
        """Atomically upsert offers and create or refresh their trip relations.

        Returns the offer IDs whose relations were newly created for this trip.
        Existing relations retain their notification state.
        """

        trip_id = validate_trip_id(trip_id)
        synchronized = tuple(offers_with_distances)
        offer_ids: list[str] = []
        for item in synchronized:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError(
                    "offers_with_distances must contain (Offer, distance_km) tuples."
                )
            offer, distance_km = item
            if not isinstance(offer, Offer):
                raise ValueError(
                    "offers_with_distances must contain valid Offer instances."
                )
            if (
                isinstance(distance_km, bool)
                or not isinstance(distance_km, (int, float))
                or not isfinite(distance_km)
                or distance_km < 0
            ):
                raise ValueError("distance_km must be a finite, non-negative number.")
            offer_ids.append(offer.id)

        if len(set(offer_ids)) != len(offer_ids):
            raise ValueError("offers_with_distances must contain unique offer IDs.")

        observed_at = datetime.now(LOCAL_TIMEZONE).isoformat()
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)

                existing_ids: set[str] = set()
                if offer_ids:
                    placeholders = ", ".join("?" for _ in offer_ids)
                    existing_ids = {
                        row[0]
                        for row in connection.execute(
                            f"""
                            SELECT offer_id
                            FROM trip_offers
                            WHERE trip_id = ? AND offer_id IN ({placeholders})
                            """,
                            (trip_id, *offer_ids),
                        )
                    }

                self._upsert_offers(
                    connection,
                    tuple(offer for offer, _ in synchronized),
                    observed_at,
                )
                connection.executemany(
                    """
                    INSERT INTO trip_offers (
                        trip_id, offer_id, distance_km, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(trip_id, offer_id) DO UPDATE SET
                        distance_km = excluded.distance_km,
                        is_available = 1,
                        last_seen_at = excluded.last_seen_at,
                        unavailable_since = NULL
                    """,
                    (
                        (trip_id, offer.id, distance_km, observed_at, observed_at)
                        for offer, distance_km in synchronized
                    ),
                )
                self._mark_missing_trip_offers_unavailable(
                    connection,
                    trip_id,
                    tuple(offer_ids),
                    observed_at,
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip synchronization failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not synchronize offers for trip {trip_id!r}."
            ) from exc

        return frozenset(set(offer_ids) - existing_ids)

    def reconcile_trip_offer_availability(
        self, trip_id: str, complete_offer_ids: Iterable[str]
    ) -> int:
        """Mark unavailable the trip relations absent from a complete response.

        The supplied IDs must be from a successfully parsed, complete response
        for ``trip_id``. Only relations that are currently available are
        changed, preserving their original unavailable timestamp and all
        notification state on later repeated reconciliations.
        """

        trip_id = validate_trip_id(trip_id)
        offer_ids = self._validate_offer_ids(
            complete_offer_ids, "complete_offer_ids"
        )

        unavailable_since = datetime.now(LOCAL_TIMEZONE).isoformat()
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)
                return self._mark_missing_trip_offers_unavailable(
                    connection,
                    trip_id,
                    offer_ids,
                    unavailable_since,
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip availability reconciliation failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not reconcile offer availability for trip {trip_id!r}."
            ) from exc

    def mark_trip_offers_sent(
        self, trip_id: str, offer_ids: Iterable[str]
    ) -> int:
        """Mark selected available, unsent relations as sent after SMTP acceptance."""

        trip_id = validate_trip_id(trip_id)
        selected_offer_ids = self._validate_offer_ids(offer_ids, "offer_ids")
        if not selected_offer_ids:
            return 0

        sent_at = datetime.now(LOCAL_TIMEZONE).isoformat()
        placeholders = ", ".join("?" for _ in selected_offer_ids)
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)
                cursor = connection.execute(
                    f"""
                    UPDATE trip_offers
                    SET is_sent = 1, sent_at = ?
                    WHERE trip_id = ?
                      AND is_available = 1
                      AND is_sent = 0
                      AND offer_id IN ({placeholders})
                    """,
                    (sent_at, trip_id, *selected_offer_ids),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip-offer sent-state update failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not mark sent offers for trip {trip_id!r}."
            ) from exc

        return cursor.rowcount

    def has_trip_overview_slot(
        self, trip_id: str, local_date: date, slot_hour: int
    ) -> bool:
        """Return whether a trip overview was successfully sent for this slot."""

        trip_id, local_date, slot_hour = self._validate_overview_slot(
            trip_id, local_date, slot_hour
        )
        try:
            with sqlite3.connect(self.database_path) as connection:
                self._require_trip(connection, trip_id)
                row = connection.execute(
                    """
                    SELECT 1
                    FROM trip_overview_slots
                    WHERE trip_id = ? AND local_date = ? AND slot_hour = ?
                    """,
                    (trip_id, local_date.isoformat(), slot_hour),
                ).fetchone()
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip overview slot read failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not read overview slot for trip {trip_id!r}."
            ) from exc
        return row is not None

    def mark_trip_overview_slot_sent(
        self, trip_id: str, local_date: date, slot_hour: int
    ) -> bool:
        """Persist a successful trip overview slot without overwriting history."""

        trip_id, local_date, slot_hour = self._validate_overview_slot(
            trip_id, local_date, slot_hour
        )
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                self._require_trip(connection, trip_id)
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO trip_overview_slots (
                        trip_id, local_date, slot_hour
                    ) VALUES (?, ?, ?)
                    """,
                    (trip_id, local_date.isoformat(), slot_hour),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip overview slot write failed: %s", exc)
            raise SQLiteStoreError(
                f"Could not persist overview slot for trip {trip_id!r}."
            ) from exc
        return cursor.rowcount == 1

    @staticmethod
    def _validate_overview_slot(
        trip_id: str, local_date: date, slot_hour: int
    ) -> tuple[str, date, int]:
        trip_id = validate_trip_id(trip_id)
        if not isinstance(local_date, date) or isinstance(local_date, datetime):
            raise ValueError("local_date must be a date.")
        if isinstance(slot_hour, bool) or slot_hour not in (9, 21):
            raise ValueError("slot_hour must be a configured summary hour.")
        return trip_id, local_date, slot_hour

    def purge_unavailable_trip_offers(self, *, now: datetime | None = None) -> int:
        """Remove unavailable relations older than 14 days and their orphaned offers."""

        reference_time = (
            datetime.now(LOCAL_TIMEZONE)
            if now is None
            else now.astimezone(LOCAL_TIMEZONE)
        )
        cutoff = reference_time - timedelta(days=14)
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.execute("BEGIN IMMEDIATE")
                expired_offer_ids = tuple(
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT offer_id
                        FROM trip_offers
                        WHERE is_available = 0
                          AND unavailable_since IS NOT NULL
                          AND datetime(unavailable_since) < datetime(?)
                        """,
                        (cutoff.isoformat(),),
                    )
                )
                if not expired_offer_ids:
                    return 0

                placeholders = ", ".join("?" for _ in expired_offer_ids)
                cursor = connection.execute(
                    f"""
                    DELETE FROM trip_offers
                    WHERE is_available = 0
                      AND unavailable_since IS NOT NULL
                      AND datetime(unavailable_since) < datetime(?)
                    """,
                    (cutoff.isoformat(),),
                )
                connection.execute(
                    f"""
                    DELETE FROM offers
                    WHERE id IN ({placeholders})
                      AND NOT EXISTS (
                          SELECT 1
                          FROM trip_offers
                          WHERE trip_offers.offer_id = offers.id
                      )
                    """,
                    expired_offer_ids,
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite unavailable trip-offer retention failed: %s", exc)
            raise SQLiteStoreError(
                "Could not purge expired unavailable trip-offer relations."
            ) from exc

        return cursor.rowcount

    @staticmethod
    def _validate_offer_ids(offer_ids: Iterable[str], argument_name: str) -> tuple[str, ...]:
        validated_offer_ids = tuple(offer_ids)
        if any(
            not isinstance(offer_id, str) or not offer_id.strip()
            for offer_id in validated_offer_ids
        ):
            raise ValueError(f"{argument_name} must contain non-empty strings.")
        if len(set(validated_offer_ids)) != len(validated_offer_ids):
            raise ValueError(f"{argument_name} must contain unique offer IDs.")
        return validated_offer_ids

    @staticmethod
    def _mark_missing_trip_offers_unavailable(
        connection: sqlite3.Connection,
        trip_id: str,
        complete_offer_ids: tuple[str, ...],
        unavailable_since: str,
    ) -> int:
        """Update only available relations missing from one complete response."""

        if complete_offer_ids:
            placeholders = ", ".join("?" for _ in complete_offer_ids)
            cursor = connection.execute(
                f"""
                UPDATE trip_offers
                SET is_available = 0, unavailable_since = ?
                WHERE trip_id = ?
                  AND is_available = 1
                  AND offer_id NOT IN ({placeholders})
                """,
                (unavailable_since, trip_id, *complete_offer_ids),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE trip_offers
                SET is_available = 0, unavailable_since = ?
                WHERE trip_id = ? AND is_available = 1
                """,
                (unavailable_since, trip_id),
            )
        return cursor.rowcount

    @staticmethod
    def _upsert_offers(
        connection: sqlite3.Connection,
        offers: tuple[Offer, ...],
        first_seen_timestamp: str,
    ) -> None:
        connection.executemany(
            """
            INSERT INTO offers (
                id, start_date, end_date, origin_city, origin_latitude,
                origin_longitude, destination_city, destination_latitude,
                destination_longitude, free_km, price_minor_units, currency,
                first_seen_timestamp, is_deleted, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            ON CONFLICT(id) DO UPDATE SET
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                origin_city = excluded.origin_city,
                origin_latitude = excluded.origin_latitude,
                origin_longitude = excluded.origin_longitude,
                destination_city = excluded.destination_city,
                destination_latitude = excluded.destination_latitude,
                destination_longitude = excluded.destination_longitude,
                free_km = excluded.free_km,
                price_minor_units = excluded.price_minor_units,
                currency = excluded.currency,
                is_deleted = 0,
                deleted_at = NULL
            """,
            (
                (
                    offer.id,
                    offer.start_date.isoformat(),
                    offer.end_date.isoformat(),
                    offer.origin.city,
                    offer.origin.latitude,
                    offer.origin.longitude,
                    offer.destination.city,
                    offer.destination.latitude,
                    offer.destination.longitude,
                    offer.free_km,
                    offer.price_minor_units,
                    offer.currency,
                    first_seen_timestamp,
                )
                for offer in offers
            ),
        )

    def create_trip_offer(
        self, trip_id: str, offer_id: str, *, distance_km: float
    ) -> bool:
        """Create an unsent trip relation for a globally persisted offer.

        Returns whether this call created the relation. Existing relations are
        deliberately left untouched so their per-trip notification state is
        preserved.
        """

        if not isinstance(trip_id, str) or not trip_id.strip():
            raise ValueError("trip_id must be a non-empty string.")
        if not isinstance(offer_id, str) or not offer_id.strip():
            raise ValueError("offer_id must be a non-empty string.")
        if (
            isinstance(distance_km, bool)
            or not isinstance(distance_km, (int, float))
            or not isfinite(distance_km)
            or distance_km < 0
        ):
            raise ValueError("distance_km must be a finite, non-negative number.")

        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("PRAGMA foreign_keys = ON")
                cursor = connection.execute(
                    """
                    INSERT INTO trip_offers (trip_id, offer_id, distance_km)
                    VALUES (?, ?, ?)
                    ON CONFLICT(trip_id, offer_id) DO NOTHING
                    """,
                    (trip_id, offer_id, distance_km),
                )
        except sqlite3.Error as exc:
            LOGGER.error("SQLite trip-offer creation failed: %s", exc)
            raise SQLiteStoreError("Could not create the trip-offer relation.") from exc

        return cursor.rowcount == 1

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
