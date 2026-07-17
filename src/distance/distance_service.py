"""Pure geographic distance calculations for trip-specific offer views."""

from __future__ import annotations

from math import asin, cos, isfinite, radians, sin, sqrt

from src.models.offer import DistanceTier, GeoLocation


EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    """Return the unrounded great-circle distance between two coordinates."""

    origin_latitude, origin_longitude = _validate_coordinates(
        origin_latitude, origin_longitude, "origin"
    )
    destination_latitude, destination_longitude = _validate_coordinates(
        destination_latitude, destination_longitude, "destination"
    )

    latitude_delta = radians(destination_latitude - origin_latitude)
    longitude_delta = radians(destination_longitude - origin_longitude)
    origin_latitude_radians = radians(origin_latitude)
    destination_latitude_radians = radians(destination_latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_latitude_radians)
        * cos(destination_latitude_radians)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(haversine))


def calculate_distance_km(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> float:
    """Explicit alias for the distance calculation used by synchronizers."""

    return haversine_distance_km(
        origin_latitude,
        origin_longitude,
        destination_latitude,
        destination_longitude,
    )


def distance_between_locations(origin: GeoLocation, destination: GeoLocation) -> float:
    """Return the unrounded distance between two validated domain locations."""

    if not isinstance(origin, GeoLocation) or not isinstance(destination, GeoLocation):
        raise TypeError("origin and destination must be GeoLocation values.")
    return haversine_distance_km(
        origin.latitude,
        origin.longitude,
        destination.latitude,
        destination.longitude,
    )


def classify_distance(distance_km: float) -> DistanceTier:
    """Classify an unrounded distance according to the trip distance tiers."""

    return DistanceTier.for_distance(distance_km)


def round_distance_km(distance_km: float) -> float:
    """Round a validated distance only for presentation."""

    _validate_distance(distance_km)
    return round(distance_km, 1)


def _validate_coordinates(
    latitude: float, longitude: float, label: str
) -> tuple[float, float]:
    if (
        isinstance(latitude, bool)
        or not isinstance(latitude, (int, float))
        or not isfinite(latitude)
        or not -90 <= latitude <= 90
    ):
        raise ValueError(f"{label} latitude must be between -90 and 90.")
    if (
        isinstance(longitude, bool)
        or not isinstance(longitude, (int, float))
        or not isfinite(longitude)
        or not -180 <= longitude <= 180
    ):
        raise ValueError(f"{label} longitude must be between -180 and 180.")
    return float(latitude), float(longitude)


def _validate_distance(distance_km: float) -> None:
    if (
        isinstance(distance_km, bool)
        or not isinstance(distance_km, (int, float))
        or not isfinite(distance_km)
        or distance_km < 0
    ):
        raise ValueError("Distance must be a finite, non-negative number of kilometres.")
