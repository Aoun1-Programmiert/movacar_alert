"""Unit tests for trip administration validation."""

from datetime import date, datetime

import pytest

from src.validation.trip_validation import (
    EmailValidationError,
    TripValidationError,
    normalize_email,
    validate_coordinates,
    validate_pickup_window,
    validate_start_city,
    validate_trip_name,
)


@pytest.mark.parametrize("validator", (validate_trip_name, validate_start_city))
@pytest.mark.parametrize("value", ("", "   ", None, 42))
def test_required_trip_text_is_rejected(validator, value: object) -> None:
    with pytest.raises(TripValidationError):
        validator(value)


def test_trip_text_is_trimmed() -> None:
    assert validate_trip_name("  Sommerfahrt  ") == "Sommerfahrt"
    assert validate_start_city("\tBerlin ") == "Berlin"


@pytest.mark.parametrize(
    ("start", "end"),
    (
        (date(2026, 7, 20), date(2026, 7, 19)),
        (datetime(2026, 7, 20), date(2026, 7, 21)),
        (date(2026, 7, 20), "2026-07-21"),
    ),
)
def test_invalid_pickup_windows_are_rejected(start: object, end: object) -> None:
    with pytest.raises(TripValidationError):
        validate_pickup_window(start, end)


def test_same_day_pickup_window_is_valid() -> None:
    pickup_day = date(2026, 7, 20)
    assert validate_pickup_window(pickup_day, pickup_day) == (pickup_day, pickup_day)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    ((91, 0), (0, 181), (float("nan"), 0), (0, float("inf")), (True, 0)),
)
def test_invalid_coordinates_are_rejected(latitude: object, longitude: object) -> None:
    with pytest.raises(TripValidationError):
        validate_coordinates(latitude, longitude)


def test_coordinates_are_returned_as_floats() -> None:
    assert validate_coordinates(52, 13) == (52.0, 13.0)


@pytest.mark.parametrize(
    "value",
    ("", "   ", "missing-at.example.com", "a@", "@example.com", "a b@example.com", None),
)
def test_invalid_email_addresses_are_rejected(value: object) -> None:
    with pytest.raises(EmailValidationError):
        normalize_email(value)


def test_email_is_trimmed_and_casefolded_before_comparison() -> None:
    assert normalize_email("  User@Example.COM ") == "user@example.com"
