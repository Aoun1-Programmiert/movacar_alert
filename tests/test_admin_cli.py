"""Tests for trip administration command-line operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import admin_cli
from src.storage.sqlite_store import SQLiteStoreError


def _database_argument(database_path: Path) -> list[str]:
    return ["--sqlite-path", str(database_path)]


def test_create_and_list_trip_with_readable_output(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "trips.sqlite"

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "create",
                "--trip-id",
                "summer-2026",
                "--name",
                "Summer drive",
                "--pickup-start",
                "2026-07-20",
                "--pickup-end",
                "2026-07-25",
                "--start-city",
                "Berlin",
                "--latitude",
                "52.52",
                "--longitude",
                "13.405",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "Created trip 'summer-2026'.\n"

    assert admin_cli.main([*_database_argument(database_path), "trip", "list"]) == 0
    assert capsys.readouterr().out == (
        "summer-2026: Summer drive\n"
        "  Pickup: 2026-07-20 to 2026-07-25\n"
        "  Start city: Berlin (52.52, 13.405)\n"
    )


def test_list_returns_structured_json_in_stable_repository_order(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "trips.sqlite"
    for trip_id in ("z-trip", "a-trip"):
        assert (
            admin_cli.main(
                [
                    *_database_argument(database_path),
                    "trip",
                    "create",
                    "--trip-id",
                    trip_id,
                    "--name",
                    trip_id,
                    "--pickup-start",
                    "2026-07-20",
                    "--pickup-end",
                    "2026-07-25",
                    "--start-city",
                    "Berlin",
                    "--latitude",
                    "52.52",
                    "--longitude",
                    "13.405",
                ]
            )
            == 0
        )
        capsys.readouterr()

    assert (
        admin_cli.main([*_database_argument(database_path), "trip", "list", "--json"])
        == 0
    )

    assert json.loads(capsys.readouterr().out) == {
        "trips": [
            {
                "trip_id": "a-trip",
                "name": "a-trip",
                "pickup_start": "2026-07-20",
                "pickup_end": "2026-07-25",
                "start_city": "Berlin",
                "latitude": 52.52,
                "longitude": 13.405,
            },
            {
                "trip_id": "z-trip",
                "name": "z-trip",
                "pickup_start": "2026-07-20",
                "pickup_end": "2026-07-25",
                "start_city": "Berlin",
                "latitude": 52.52,
                "longitude": 13.405,
            },
        ]
    }


def test_delete_returns_json_and_unknown_trip_returns_nonzero(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "trips.sqlite"
    create_arguments = [
        *_database_argument(database_path),
        "trip",
        "create",
        "--trip-id",
        "summer-2026",
        "--name",
        "Summer drive",
        "--pickup-start",
        "2026-07-20",
        "--pickup-end",
        "2026-07-25",
        "--start-city",
        "Berlin",
        "--latitude",
        "52.52",
        "--longitude",
        "13.405",
    ]
    assert admin_cli.main(create_arguments) == 0
    capsys.readouterr()

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "delete",
                "--trip-id",
                "summer-2026",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"deleted_trip_id": "summer-2026"}

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "delete",
                "--trip-id",
                "missing",
            ]
        )
        == 1
    )
    assert "Error: Trip 'missing' does not exist." in capsys.readouterr().err


def test_invalid_trip_input_and_argument_errors_return_nonzero(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "trips.sqlite"

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "create",
                "--trip-id",
                "summer-2026",
                "--name",
                "Summer drive",
                "--pickup-start",
                "2026-07-25",
                "--pickup-end",
                "2026-07-20",
                "--start-city",
                "Berlin",
                "--latitude",
                "52.52",
                "--longitude",
                "13.405",
            ]
        )
        == 1
    )
    assert "pickup_end must not be before pickup_start" in capsys.readouterr().err

    assert (
        admin_cli.main([*_database_argument(database_path), "trip", "create"]) == 2
    )
    assert "the following arguments are required" in capsys.readouterr().err


def test_persistence_errors_return_nonzero(monkeypatch, capsys) -> None:
    class FailingStore:
        def __init__(self, database_path: Path) -> None:
            self.database_path = database_path

        def initialize_schema(self) -> None:
            raise SQLiteStoreError("Could not initialize the SQLite schema.")

    monkeypatch.setattr(admin_cli, "SQLiteStore", FailingStore)

    assert admin_cli.main(["trip", "list"]) == 1
    assert capsys.readouterr().err == "Error: Could not initialize the SQLite schema.\n"


def _create_trip(database_path: Path) -> None:
    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "create",
                "--trip-id",
                "summer-2026",
                "--name",
                "Summer drive",
                "--pickup-start",
                "2026-07-20",
                "--pickup-end",
                "2026-07-25",
                "--start-city",
                "Berlin",
                "--latitude",
                "52.52",
                "--longitude",
                "13.405",
            ]
        )
        == 0
    )


def test_recipient_add_and_list_follow_text_and_json_contract(
    tmp_path: Path, capsys
) -> None:
    database_path = tmp_path / "trips.sqlite"
    _create_trip(database_path)
    capsys.readouterr()

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "add",
                "--trip-id",
                "summer-2026",
                "--email",
                " User@Example.COM ",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == (
        "Added recipient 'user@example.com' to trip 'summer-2026'.\n"
    )

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "list",
                "--trip-id",
                "summer-2026",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "trip_id": "summer-2026",
        "recipients": ["user@example.com"],
    }


def test_recipient_remove_and_empty_list_are_persisted(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "trips.sqlite"
    _create_trip(database_path)
    capsys.readouterr()
    admin_cli.main(
        [
            *_database_argument(database_path),
            "trip",
            "recipient",
            "add",
            "--trip-id",
            "summer-2026",
            "--email",
            "recipient@example.com",
        ]
    )
    capsys.readouterr()

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "remove",
                "--trip-id",
                "summer-2026",
                "--email",
                "RECIPIENT@EXAMPLE.COM",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "trip_id": "summer-2026",
        "recipient": "recipient@example.com",
    }

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "list",
                "--trip-id",
                "summer-2026",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == (
        "No recipients configured for trip 'summer-2026'.\n"
    )


@pytest.mark.parametrize(
    ("email", "expected_error"),
    (
        ("not-an-email", "Invalid email address"),
        ("recipient@example.com", "already belongs to trip"),
    ),
)
def test_recipient_add_rejects_invalid_or_duplicate_addresses(
    tmp_path: Path, capsys, email: str, expected_error: str
) -> None:
    database_path = tmp_path / "trips.sqlite"
    _create_trip(database_path)
    capsys.readouterr()
    if email == "recipient@example.com":
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "add",
                "--trip-id",
                "summer-2026",
                "--email",
                email,
            ]
        )
        capsys.readouterr()

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "add",
                "--trip-id",
                "summer-2026",
                "--email",
                email,
            ]
        )
        == 1
    )
    assert expected_error in capsys.readouterr().err


def test_recipient_commands_reject_unknown_trip(tmp_path: Path, capsys) -> None:
    database_path = tmp_path / "trips.sqlite"

    assert (
        admin_cli.main(
            [
                *_database_argument(database_path),
                "trip",
                "recipient",
                "list",
                "--trip-id",
                "missing",
            ]
        )
        == 1
    )
    assert "Trip 'missing' does not exist." in capsys.readouterr().err
