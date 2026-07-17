"""Unit tests for trip distance calculations and classifications."""

import pytest

from src.distance.distance_service import (
    EARTH_RADIUS_KM,
    classify_distance,
    distance_between_locations,
    haversine_distance_km,
    round_distance_km,
)
from src.models.offer import DistanceTier, GeoLocation


def test_haversine_distance_is_zero_for_identical_coordinates() -> None:
    assert haversine_distance_km(52.52, 13.405, 52.52, 13.405) == pytest.approx(0)


def test_haversine_distance_uses_great_circle_geometry() -> None:
    distance = haversine_distance_km(0, 0, 0, 1)

    assert distance == pytest.approx(EARTH_RADIUS_KM * 3.141592653589793 / 180)


def test_distance_between_locations_uses_domain_coordinates() -> None:
    berlin = GeoLocation("Berlin", 52.52, 13.405)
    paris = GeoLocation("Paris", 48.8566, 2.3522)

    assert distance_between_locations(berlin, paris) == pytest.approx(877.5, abs=0.5)


@pytest.mark.parametrize(
    ("distance", "tier"),
    (
        (99.999999, DistanceTier.RED),
        (100, DistanceTier.ORANGE),
        (249.999999, DistanceTier.ORANGE),
        (250, DistanceTier.YELLOW),
        (499.999999, DistanceTier.YELLOW),
        (500, DistanceTier.NEUTRAL),
    ),
)
def test_classification_uses_unrounded_thresholds(
    distance: float, tier: DistanceTier
) -> None:
    assert classify_distance(distance) is tier


def test_rounding_is_only_for_presentation() -> None:
    distance = 99.96

    assert classify_distance(distance) is DistanceTier.RED
    assert round_distance_km(distance) == 100.0


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    ((91, 0), (0, 181), (float("nan"), 0), (0, float("inf"))),
)
def test_invalid_coordinates_are_rejected(latitude: float, longitude: float) -> None:
    with pytest.raises(ValueError):
        haversine_distance_km(latitude, longitude, 0, 0)


@pytest.mark.parametrize("distance", (-1, float("nan"), float("inf"), True))
def test_invalid_distances_are_rejected(distance: float) -> None:
    with pytest.raises(ValueError):
        classify_distance(distance)
    with pytest.raises(ValueError):
        round_distance_km(distance)


def test_location_distance_requires_domain_locations() -> None:
    with pytest.raises(TypeError, match="GeoLocation"):
        distance_between_locations("Berlin", GeoLocation("Paris", 48.8566, 2.3522))  # type: ignore[arg-type]
