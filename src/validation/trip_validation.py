"""Validation and normalization for trip administration input."""

from __future__ import annotations

from datetime import date, datetime
from math import isfinite
import re


class TripValidationError(ValueError):
    """Raised when a trip field violates the domain contract."""


class EmailValidationError(ValueError):
    """Raised when an email address is empty or malformed."""


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_trip_id(value: object) -> str:
    """Validate and return a stable, non-empty trip identifier."""

    return _required_text(value, "trip_id", TripValidationError)


def validate_trip_name(value: object) -> str:
    """Validate and return a normalized trip name."""

    return _required_text(value, "name", TripValidationError)


def validate_start_city(value: object) -> str:
    """Validate and return a normalized trip start city."""

    return _required_text(value, "start_city", TripValidationError)


def validate_pickup_window(start: object, end: object) -> tuple[date, date]:
    """Validate a date-only, non-reversed pick-up window."""

    if (
        not isinstance(start, date)
        or isinstance(start, datetime)
        or not isinstance(end, date)
        or isinstance(end, datetime)
    ):
        raise TripValidationError("pickup_start and pickup_end must be date values.")
    if end < start:
        raise TripValidationError("pickup_end must not be before pickup_start.")
    return start, end


def validate_coordinates(latitude: object, longitude: object) -> tuple[float, float]:
    """Validate finite latitude and longitude in their geographic ranges."""

    _coordinate(latitude, -90, 90, "latitude")
    _coordinate(longitude, -180, 180, "longitude")
    return float(latitude), float(longitude)


def normalize_email(value: object) -> str:
    """Validate an address and return its canonical comparison form."""

    if not isinstance(value, str):
        raise EmailValidationError("Email address must be a string.")
    normalized = value.strip().casefold()
    if not normalized or not _EMAIL_PATTERN.fullmatch(normalized):
        raise EmailValidationError(f"Invalid email address: {value!r}.")
    return normalized


def _required_text(
    value: object,
    field: str,
    error_type: type[ValueError],
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field} must not be empty.")
    return value.strip()


def _coordinate(value: object, minimum: int, maximum: int, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise TripValidationError(f"{field} must be between {minimum} and {maximum}.")
