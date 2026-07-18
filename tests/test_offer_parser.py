"""Unit tests for raw offers response parsing."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.parser.offer_parser import OfferParsingError, parse_offers


@pytest.fixture
def example_response() -> dict[str, object]:
    fixture_path = Path(__file__).with_name("example_response.json")
    with fixture_path.open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


def test_parse_offers_resolves_complete_offers_from_example_response(
    example_response: dict[str, object],
) -> None:
    offers = parse_offers(example_response)

    assert [offer.id for offer in offers] == [
        "252266_202065_202066",
        "252265_202065_202066",
        "252372_3699_7532",
    ]
    first_offer = offers[0]
    assert first_offer.start_date == datetime(2026, 7, 20, 4, tzinfo=timezone.utc)
    assert first_offer.end_date == datetime(2026, 7, 26, 19, tzinfo=timezone.utc)
    assert first_offer.free_km == 222
    assert first_offer.price_minor_units == 100
    assert first_offer.currency == "EUR"
    assert first_offer.origin.city == "Saint-Mesmes"
    assert first_offer.origin.latitude == 48.9875914
    assert first_offer.origin.longitude == 2.691353
    assert first_offer.destination.city == "Grigny"
    assert first_offer.destination.latitude == 48.74792
    assert first_offer.destination.longitude == 2.39253


def test_parse_offers_normalizes_offset_dates_to_utc(
    example_response: dict[str, object],
) -> None:
    response = copy.deepcopy(example_response)
    attributes = response["data"][0]["attributes"]
    attributes["start_date"] = "2026-07-20T06:00:00+02:00"
    attributes["end_date"] = "2026-07-26T14:00:00-05:00"

    offer = parse_offers(response)[0]

    assert offer.start_date == datetime(2026, 7, 20, 4, tzinfo=timezone.utc)
    assert offer.end_date == datetime(2026, 7, 26, 19, tzinfo=timezone.utc)
    assert offer.start_date.tzinfo is timezone.utc
    assert offer.end_date.tzinfo is timezone.utc


def test_parse_offers_normalizes_mixed_utc_and_offset_dates_to_utc(
    example_response: dict[str, object],
) -> None:
    response = copy.deepcopy(example_response)
    response["data"][0]["attributes"]["end_date"] = "2026-07-26T21:00:00+02:00"

    offer = parse_offers(response)[0]

    assert offer.start_date.tzinfo is timezone.utc
    assert offer.end_date == datetime(2026, 7, 26, 19, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("start_date", "2026-07-20T04:00:00", "UTC designator or numeric UTC offset"),
        ("end_date", "2026-07-26T19:00:00+25:00", "ISO-8601 datetime"),
    ),
)
def test_parse_offers_rejects_naive_or_invalid_timezone_dates(
    example_response: dict[str, object],
    field: str,
    value: str,
    message: str,
) -> None:
    response = copy.deepcopy(example_response)
    response["data"][0]["attributes"][field] = value

    with pytest.raises(OfferParsingError, match=message):
        parse_offers(response)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda response: response["data"][0]["relationships"].pop("origin"),
            "relationships.origin must be an object",
        ),
        (
            lambda response: response["data"][0]["attributes"].pop("free_km"),
            "attributes.free_km must be an integer",
        ),
        (
            lambda response: response["included"].pop(0),
            "references missing station '6099'",
        ),
    ),
)
def test_parse_offers_signals_missing_required_relationships_or_fields(
    example_response: dict[str, object],
    mutation: object,
    message: str,
) -> None:
    response = copy.deepcopy(example_response)
    mutation(response)  # type: ignore[operator]

    with pytest.raises(OfferParsingError, match=message):
        parse_offers(response)
