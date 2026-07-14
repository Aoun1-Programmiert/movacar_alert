"""Application entry point for the offer monitor."""

from __future__ import annotations

import sys

from src.config.settings import SettingsValidationError, load_settings
from src.logging.logger import configure_json_logger
from src.loop.poll_loop import poll_forever
from src.storage.sqlite_store import SQLiteStore


def main() -> int:
    """Load runtime dependencies, initialize persistence, and start polling."""
    try:
        settings = load_settings()
    except SettingsValidationError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    configure_json_logger(settings.log_file_path)
    store = SQLiteStore(settings.sqlite_path)
    store.initialize_schema()
    poll_forever(settings, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
