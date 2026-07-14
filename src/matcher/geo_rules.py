"""Geographic domain rules based on the configured German bounding box."""

from __future__ import annotations

import os
from math import isfinite
from typing import Mapping

from src.config.settings import (
    DEFAULT_DE_BBOX_MAX_LAT,
    DEFAULT_DE_BBOX_MAX_LON,
    DEFAULT_DE_BBOX_MIN_LAT,
    DEFAULT_DE_BBOX_MIN_LON,
    BoundingBox,
    _load_bbox,
)


DEFAULT_DE_BBOX = BoundingBox(
    min_lat=DEFAULT_DE_BBOX_MIN_LAT,
    max_lat=DEFAULT_DE_BBOX_MAX_LAT,
    min_lon=DEFAULT_DE_BBOX_MIN_LON,
    max_lon=DEFAULT_DE_BBOX_MAX_LON,
)


def load_de_bbox(environ: Mapping[str, str] | None = None) -> BoundingBox:
    """Return the default bounds or a complete set of environment overrides."""

    values = os.environ if environ is None else environ
    return _load_bbox(values)


def is_in_germany(
    latitude: float,
    longitude: float,
    bbox: BoundingBox | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether a coordinate lies inside the inclusive German bounding box."""

    effective_bbox = bbox if bbox is not None else load_de_bbox(environ)
    _validate_coordinate(latitude, longitude)
    return (
        effective_bbox.min_lat <= latitude <= effective_bbox.max_lat
        and effective_bbox.min_lon <= longitude <= effective_bbox.max_lon
    )


def is_outside_germany(
    latitude: float,
    longitude: float,
    bbox: BoundingBox | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether a coordinate lies outside the inclusive German bounding box."""

    return not is_in_germany(latitude, longitude, bbox, environ=environ)


def _validate_coordinate(latitude: float, longitude: float) -> None:
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not isfinite(latitude)
    ):
        raise ValueError("Latitude must be a numeric value.")
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not isfinite(longitude)
    ):
        raise ValueError("Longitude must be a numeric value.")
