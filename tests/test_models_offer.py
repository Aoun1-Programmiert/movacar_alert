"""Unit tests for offer domain models."""

from datetime import datetime

import pytest

from src.models.offer import ClassifiedOffer, GeoLocation, Offer


@pytest.fixture
def offer_values() -> dict[str, object]:
    return {
        "id": "offer-123",
        "start_date": datetime(2026, 7, 14, 8, 0),
        "end_date": datetime(2026, 7, 16, 8, 0),
        "free_km": 500,
        "origin": GeoLocation("Berlin", 52.52, 13.405),
        "destination": GeoLocation("Paris", 48.8566, 2.3522),
    }


def test_offer_contains_contract_fields_and_resolved_geo_data(
    offer_values: dict[str, object],
) -> None:
    offer = Offer(**offer_values)

    assert offer.id == "offer-123"
    assert offer.start_date == datetime(2026, 7, 14, 8, 0)
    assert offer.end_date == datetime(2026, 7, 16, 8, 0)
    assert offer.free_km == 500
    assert offer.origin.city == "Berlin"
    assert offer.origin.latitude == 52.52
    assert offer.origin.longitude == 13.405
    assert offer.destination.city == "Paris"
    assert offer.destination.lat == 48.8566
    assert offer.destination.lon == 2.3522


def test_classified_offer_extends_offer_with_highlight_and_state(
    offer_values: dict[str, object],
) -> None:
    classified = ClassifiedOffer(**offer_values, is_highlighted=True, state="new")

    assert isinstance(classified, Offer)
    assert classified.is_highlighted is True
    assert classified.state == "new"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("id", "", "id"),
        ("free_km", -1, "free_km"),
    ),
)
def test_offer_rejects_invalid_required_values(
    offer_values: dict[str, object], field: str, value: object, error: str
) -> None:
    offer_values[field] = value

    with pytest.raises(ValueError, match=error):
        Offer(**offer_values)


def test_offer_rejects_end_before_start(offer_values: dict[str, object]) -> None:
    offer_values["end_date"] = datetime(2026, 7, 14, 7, 59)

    with pytest.raises(ValueError, match="end_date"):
        Offer(**offer_values)


def test_classified_offer_rejects_unknown_state(
    offer_values: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="state"):
        ClassifiedOffer(**offer_values, is_highlighted=False, state="removed")


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    ((91, 0), (0, 181)),
)
def test_location_rejects_invalid_coordinates(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError):
        GeoLocation("Berlin", latitude, longitude)
