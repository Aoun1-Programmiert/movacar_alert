"""Unit tests for German bounding-box geographic rules."""

import pytest

from src.config.settings import (
    DEFAULT_DE_BBOX_MAX_LAT,
    DEFAULT_DE_BBOX_MAX_LON,
    DEFAULT_DE_BBOX_MIN_LAT,
    DEFAULT_DE_BBOX_MIN_LON,
    BoundingBox,
)
from src.matcher.geo_rules import is_in_germany, is_outside_germany, load_de_bbox


def test_default_bbox_classifies_inside_and_outside_coordinates() -> None:
    assert is_in_germany(52.52, 13.405)
    assert is_outside_germany(48.8566, 2.3522)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    (
        (DEFAULT_DE_BBOX_MIN_LAT, DEFAULT_DE_BBOX_MIN_LON),
        (DEFAULT_DE_BBOX_MIN_LAT, DEFAULT_DE_BBOX_MAX_LON),
        (DEFAULT_DE_BBOX_MAX_LAT, DEFAULT_DE_BBOX_MIN_LON),
        (DEFAULT_DE_BBOX_MAX_LAT, DEFAULT_DE_BBOX_MAX_LON),
    ),
)
def test_default_bbox_includes_all_boundary_coordinates(
    latitude: float, longitude: float
) -> None:
    assert is_in_germany(latitude, longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    (
        (DEFAULT_DE_BBOX_MIN_LAT - 0.000001, 10.0),
        (DEFAULT_DE_BBOX_MAX_LAT + 0.000001, 10.0),
        (50.0, DEFAULT_DE_BBOX_MIN_LON - 0.000001),
        (50.0, DEFAULT_DE_BBOX_MAX_LON + 0.000001),
    ),
)
def test_coordinates_just_outside_default_bbox_are_rejected(
    latitude: float, longitude: float
) -> None:
    assert is_outside_germany(latitude, longitude)


def test_environment_overrides_are_applied() -> None:
    environment = {
        "DE_BBOX_MIN_LAT": "10",
        "DE_BBOX_MAX_LAT": "20",
        "DE_BBOX_MIN_LON": "30",
        "DE_BBOX_MAX_LON": "40",
    }

    assert load_de_bbox(environment) == BoundingBox(10.0, 20.0, 30.0, 40.0)
    assert is_in_germany(15, 35, environ=environment)
    assert is_outside_germany(25, 35, environ=environment)


def test_partial_environment_override_is_rejected() -> None:
    environment = {"DE_BBOX_MIN_LAT": "10"}

    with pytest.raises(ValueError, match="bounding-box overrides"):
        load_de_bbox(environment)


@pytest.mark.parametrize("coordinate", (float("nan"), float("inf"), float("-inf")))
def test_non_finite_coordinates_are_rejected(coordinate: float) -> None:
    with pytest.raises(ValueError):
        is_in_germany(coordinate, 10.0)
