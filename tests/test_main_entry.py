"""Tests for application startup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src import main as app_main
from src.config.settings import SettingsValidationError


def test_main_loads_settings_initializes_schema_then_starts_polling(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(sqlite_path=Path("offers.sqlite"), log_file_path=None)
    calls: list[object] = []

    class FakeStore:
        def __init__(self, database_path: Path) -> None:
            calls.append(("store", database_path))

        def initialize_schema(self) -> None:
            calls.append("initialize_schema")

    monkeypatch.setattr(app_main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        app_main,
        "configure_json_logger",
        lambda log_file_path: calls.append(("logger", log_file_path)),
    )
    monkeypatch.setattr(app_main, "SQLiteStore", FakeStore)
    monkeypatch.setattr(
        app_main,
        "poll_forever",
        lambda received_settings, store: calls.append(("poll", received_settings, store)),
    )

    assert app_main.main() == 0
    assert calls[0:3] == [
        ("logger", None),
        ("store", Path("offers.sqlite")),
        "initialize_schema",
    ]
    assert calls[3][0:2] == ("poll", settings)


def test_main_reports_configuration_errors_and_does_not_start(
    monkeypatch, capsys
) -> None:
    def fail_loading_settings() -> None:
        raise SettingsValidationError("Missing required environment variable: API_URL.")

    monkeypatch.setattr(app_main, "load_settings", fail_loading_settings)
    monkeypatch.setattr(
        app_main,
        "SQLiteStore",
        lambda database_path: (_ for _ in ()).throw(AssertionError("Store must not be created.")),
    )
    monkeypatch.setattr(
        app_main,
        "poll_forever",
        lambda settings, store: (_ for _ in ()).throw(AssertionError("Polling must not start.")),
    )

    assert app_main.main() == 2

    assert capsys.readouterr().err == (
        "Configuration error: Missing required environment variable: API_URL.\n"
    )
