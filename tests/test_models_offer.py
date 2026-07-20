"""Unit tests for global and trip-specific domain models."""

from datetime import date, datetime

import pytest

from src.models.offer import (
    DistanceTier,
    GeoLocation,
    Offer,
    Provider,
    Trip,
    TripOfferView,
    TripProviderSelection,
    TripRecipient,
)
import src.models.offer as offer_models


@pytest.fixture
def offer() -> Offer:
    return Offer(
        id="offer-123",
        start_date=datetime(2026, 7, 14, 8, 0),
        end_date=datetime(2026, 7, 16, 8, 0),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )


@pytest.fixture
def trip() -> Trip:
    return Trip(
        trip_id="trip-123",
        name="Sommerfahrt",
        pickup_start=date(2026, 7, 14),
        pickup_end=date(2026, 7, 20),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )


def test_trip_contains_identity_window_city_and_coordinates(trip: Trip) -> None:
    assert trip.trip_id == "trip-123"
    assert trip.name == "Sommerfahrt"
    assert trip.pickup_start == date(2026, 7, 14)
    assert trip.pickup_end == date(2026, 7, 20)
    assert trip.start_city == "Berlin"
    assert trip.latitude == 52.52
    assert trip.longitude == 13.405


def test_trip_recipient_is_trip_scoped() -> None:
    recipient = TripRecipient("trip-123", "user@example.com")

    assert recipient.trip_id == "trip-123"
    assert recipient.normalized_email == "user@example.com"


@pytest.mark.parametrize(
    ("distance", "tier"),
    (
        (99.999, DistanceTier.RED),
        (100, DistanceTier.ORANGE),
        (249.999, DistanceTier.ORANGE),
        (250, DistanceTier.YELLOW),
        (499.999, DistanceTier.YELLOW),
        (500, DistanceTier.NEUTRAL),
    ),
)
def test_distance_tier_boundaries_are_unambiguous(
    distance: float, tier: DistanceTier
) -> None:
    assert DistanceTier.for_distance(distance) is tier


def test_trip_offer_view_keeps_trip_offer_and_reisespecific_status(
    trip: Trip, offer: Offer
) -> None:
    view = TripOfferView(
        trip=trip,
        offer=offer,
        distance_km=99.94,
        is_available=True,
        state="new",
        is_sent=False,
        distance_tier=DistanceTier.RED,
    )

    assert view.trip is trip
    assert view.offer is offer
    assert view.distance_km == 99.94
    assert view.distance_km_rounded == 99.9
    assert view.is_available is True
    assert view.state == "new"
    assert view.is_sent is False
    assert view.distance_tier is DistanceTier.RED


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("trip_id", ""),
        ("name", ""),
        ("start_city", ""),
        ("latitude", 91),
        ("longitude", 181),
    ),
)
def test_trip_rejects_invalid_values(trip: Trip, field: str, value: object) -> None:
    values = {
        "trip_id": trip.trip_id,
        "name": trip.name,
        "pickup_start": trip.pickup_start,
        "pickup_end": trip.pickup_end,
        "start_city": trip.start_city,
        "latitude": trip.latitude,
        "longitude": trip.longitude,
    }
    values[field] = value

    with pytest.raises(ValueError):
        Trip(**values)


def test_trip_rejects_reversed_pickup_window(trip: Trip) -> None:
    with pytest.raises(ValueError, match="pickup_end"):
        Trip(
            trip_id=trip.trip_id,
            name=trip.name,
            pickup_start=trip.pickup_end,
            pickup_end=trip.pickup_start,
            start_city=trip.start_city,
            latitude=trip.latitude,
            longitude=trip.longitude,
        )


def test_trip_offer_view_rejects_mismatched_tier(trip: Trip, offer: Offer) -> None:
    with pytest.raises(ValueError, match="distance_tier"):
        TripOfferView(
            trip=trip,
            offer=offer,
            distance_km=250,
            is_available=True,
            state="existing",
            is_sent=True,
            distance_tier=DistanceTier.RED,
        )


def test_removed_classified_offer_contract_is_not_exposed() -> None:
    assert not hasattr(offer_models, "ClassifiedOffer")
    assert not hasattr(offer_models, "OfferState")


def _offer_with(**overrides: object) -> Offer:
    defaults: dict[str, object] = dict(
        id="offer-1",
        start_date=datetime(2026, 7, 14, 8, 0),
        end_date=datetime(2026, 7, 16, 8, 0),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )
    defaults.update(overrides)
    return Offer(**defaults)  # type: ignore[arg-type]


def test_imoova_offer_requires_prefixed_id() -> None:
    with pytest.raises(ValueError, match="imoova:"):
        _offer_with(id="1234", provider=Provider.IMOOVA)


def test_imoova_offer_accepts_prefixed_id() -> None:
    assert _offer_with(id="imoova:1234", provider=Provider.IMOOVA).id == "imoova:1234"


def test_movacar_offer_id_is_not_required_to_be_prefixed() -> None:
    assert _offer_with(id="1234", provider=Provider.MOVACAR).id == "1234"
