"""Command-line administration for persisted trip configurations."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Any

from src.models.trip import Trip
from src.storage.sqlite_store import SQLiteStore, SQLiteStoreError
from src.validation.trip_validation import TripValidationError, normalize_email


def main(argv: Sequence[str] | None = None) -> int:
    """Run the trip administration CLI and return its process exit code."""

    parser = _build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    try:
        return arguments.handler(arguments)
    except (SQLiteStoreError, TripValidationError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="movacar-alert-admin",
        description="Manage persisted Movacar Alert trips.",
    )
    parser.add_argument(
        "--sqlite-path",
        type=Path,
        default=Path(os.environ.get("SQLITE_PATH", "movacar_alert.sqlite")),
        help="SQLite database path (default: SQLITE_PATH or movacar_alert.sqlite).",
    )
    commands = parser.add_subparsers(dest="resource", required=True)
    trip_parser = commands.add_parser("trip", help="Manage trips.")
    trip_commands = trip_parser.add_subparsers(dest="trip_command", required=True)

    create = trip_commands.add_parser("create", help="Create a trip.")
    create.add_argument("--trip-id", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--pickup-start", required=True, type=_parse_date)
    create.add_argument("--pickup-end", required=True, type=_parse_date)
    create.add_argument("--start-city", required=True)
    create.add_argument("--latitude", required=True, type=float)
    create.add_argument("--longitude", required=True, type=float)
    _add_json_option(create)
    create.set_defaults(handler=_create_trip)

    delete = trip_commands.add_parser("delete", help="Delete a trip.")
    delete.add_argument("--trip-id", required=True)
    _add_json_option(delete)
    delete.set_defaults(handler=_delete_trip)

    list_command = trip_commands.add_parser("list", help="List all trips.")
    _add_json_option(list_command)
    list_command.set_defaults(handler=_list_trips)

    recipient = trip_commands.add_parser("recipient", help="Manage trip recipients.")
    recipient_commands = recipient.add_subparsers(
        dest="recipient_command", required=True
    )

    add_recipient = recipient_commands.add_parser(
        "add", help="Add an email recipient to a trip."
    )
    add_recipient.add_argument("--trip-id", required=True)
    add_recipient.add_argument("--email", required=True)
    _add_json_option(add_recipient)
    add_recipient.set_defaults(handler=_add_recipient)

    remove_recipient = recipient_commands.add_parser(
        "remove", help="Remove an email recipient from a trip."
    )
    remove_recipient.add_argument("--trip-id", required=True)
    remove_recipient.add_argument("--email", required=True)
    _add_json_option(remove_recipient)
    remove_recipient.set_defaults(handler=_remove_recipient)

    list_recipients = recipient_commands.add_parser(
        "list", help="List the recipients of a trip."
    )
    list_recipients.add_argument("--trip-id", required=True)
    _add_json_option(list_recipients)
    list_recipients.set_defaults(handler=_list_recipients)
    return parser


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid date {value!r}; use ISO format YYYY-MM-DD."
        ) from error


def _create_trip(arguments: argparse.Namespace) -> int:
    trip = Trip(
        trip_id=arguments.trip_id,
        name=arguments.name,
        pickup_start=arguments.pickup_start,
        pickup_end=arguments.pickup_end,
        start_city=arguments.start_city,
        latitude=arguments.latitude,
        longitude=arguments.longitude,
    )
    store = _open_store(arguments.sqlite_path)
    store.create_trip(trip)
    _write_result(
        arguments.json,
        {"trip": _trip_as_dict(trip)},
        f"Created trip {trip.trip_id!r}.",
    )
    return 0


def _delete_trip(arguments: argparse.Namespace) -> int:
    store = _open_store(arguments.sqlite_path)
    store.delete_trip(arguments.trip_id)
    _write_result(
        arguments.json,
        {"deleted_trip_id": arguments.trip_id.strip()},
        f"Deleted trip {arguments.trip_id.strip()!r}.",
    )
    return 0


def _list_trips(arguments: argparse.Namespace) -> int:
    trips = _open_store(arguments.sqlite_path).list_trips()
    _write_result(
        arguments.json,
        {"trips": [_trip_as_dict(trip) for trip in trips]},
        _format_trip_list(trips),
    )
    return 0


def _add_recipient(arguments: argparse.Namespace) -> int:
    email = normalize_email(arguments.email)
    _open_store(arguments.sqlite_path).add_trip_recipient(arguments.trip_id, email)
    _write_result(
        arguments.json,
        {"trip_id": arguments.trip_id.strip(), "recipient": email},
        f"Added recipient {email!r} to trip {arguments.trip_id.strip()!r}.",
    )
    return 0


def _remove_recipient(arguments: argparse.Namespace) -> int:
    email = normalize_email(arguments.email)
    _open_store(arguments.sqlite_path).remove_trip_recipient(arguments.trip_id, email)
    _write_result(
        arguments.json,
        {"trip_id": arguments.trip_id.strip(), "recipient": email},
        f"Removed recipient {email!r} from trip {arguments.trip_id.strip()!r}.",
    )
    return 0


def _list_recipients(arguments: argparse.Namespace) -> int:
    recipients = _open_store(arguments.sqlite_path).list_trip_recipients(
        arguments.trip_id
    )
    trip_id = arguments.trip_id.strip()
    emails = [recipient.normalized_email for recipient in recipients]
    _write_result(
        arguments.json,
        {"trip_id": trip_id, "recipients": emails},
        _format_recipient_list(trip_id, emails),
    )
    return 0


def _open_store(database_path: Path) -> SQLiteStore:
    store = SQLiteStore(database_path)
    store.initialize_schema()
    return store


def _trip_as_dict(trip: Trip) -> dict[str, Any]:
    return {
        "trip_id": trip.trip_id,
        "name": trip.name,
        "pickup_start": trip.pickup_start.isoformat(),
        "pickup_end": trip.pickup_end.isoformat(),
        "start_city": trip.start_city,
        "latitude": trip.latitude,
        "longitude": trip.longitude,
    }


def _format_trip_list(trips: Sequence[Trip]) -> str:
    if not trips:
        return "No trips configured."
    return "\n".join(
        (
            f"{trip.trip_id}: {trip.name}\n"
            f"  Pickup: {trip.pickup_start.isoformat()} to {trip.pickup_end.isoformat()}\n"
            f"  Start city: {trip.start_city} ({trip.latitude}, {trip.longitude})"
        )
        for trip in trips
    )


def _format_recipient_list(trip_id: str, recipients: Sequence[str]) -> str:
    if not recipients:
        return f"No recipients configured for trip {trip_id!r}."
    return "\n".join(
        [f"{trip_id}:"] + [f"  {recipient}" for recipient in recipients]
    )


def _write_result(as_json: bool, result: dict[str, Any], text: str) -> None:
    print(json.dumps(result, sort_keys=True) if as_json else text)


if __name__ == "__main__":
    raise SystemExit(main())
