"""SQLite persistence boundary."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteStore:
    """Owns the local SQLite database used for offer state."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize_schema(self) -> None:
        """Create the offers table when it does not exist yet."""

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
