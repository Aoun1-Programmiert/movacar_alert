"""Typed domain models for global and trip-specific offers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from math import isfinite
from enum import Enum
from typing import Literal


@dataclass(frozen=True)
class GeoLocation:
    """A station location resolved from the API response."""

    city: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.city, str) or not self.city.strip():
            raise ValueError("Location city must not be empty.")
        if (
            isinstance(self.latitude, bool)
            or not isinstance(self.latitude, (int, float))
            or not isfinite(self.latitude)
            or not -90 <= self.latitude <= 90
        ):
            raise ValueError("Location latitude must be between -90 and 90.")
        if (
            isinstance(self.longitude, bool)
            or not isinstance(self.longitude, (int, float))
            or not isfinite(self.longitude)
            or not -180 <= self.longitude <= 180
        ):
            raise ValueError("Location longitude must be between -180 and 180.")

    @property
    def lat(self) -> float:
        """Short coordinate alias used by the domain contract."""

        return self.latitude

    @property
    def lon(self) -> float:
        """Short coordinate alias used by the domain contract."""

        return self.longitude


Location = GeoLocation


@dataclass(frozen=True)
class Offer:
    """A complete offer with both stations resolved."""

    id: str
    start_date: datetime
    end_date: datetime
    free_km: int
    origin: GeoLocation
    destination: GeoLocation

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("Offer id must not be empty.")
        if not isinstance(self.start_date, datetime) or not isinstance(self.end_date, datetime):
            raise ValueError("Offer dates must be datetime values.")
        if self.end_date <= self.start_date:
            raise ValueError("Offer end_date must be after start_date.")
        if not isinstance(self.free_km, int) or isinstance(self.free_km, bool) or self.free_km < 0:
            raise ValueError("Offer free_km must be a non-negative integer.")
        if not isinstance(self.origin, GeoLocation) or not isinstance(self.destination, GeoLocation):
            raise ValueError("Offer origin and destination must be GeoLocation values.")


class DistanceTier(str, Enum):
    """The explicit distance classification used by trip views."""

    GREEN = "green"
    YELLOW = "yellow"
    NEUTRAL = "neutral"

    @classmethod
    def for_distance(cls, distance_km: float) -> "DistanceTier":
        """Classify an unrounded distance in kilometres."""

        if isinstance(distance_km, bool) or not isinstance(distance_km, (int, float)):
            raise ValueError("Distance must be a finite number of kilometres.")
        if not isfinite(distance_km) or distance_km < 0:
            raise ValueError("Distance must be a finite, non-negative number of kilometres.")
        if distance_km < 100:
            return cls.GREEN
        if distance_km < 250:
            return cls.YELLOW
        return cls.NEUTRAL


TripOfferState = Literal["new", "existing"]


@dataclass(frozen=True)
class Trip:
    """A persisted trip configuration."""

    trip_id: str
    name: str
    pickup_start: date
    pickup_end: date
    start_city: str
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not isinstance(self.trip_id, str) or not self.trip_id.strip():
            raise ValueError("Trip trip_id must not be empty.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Trip name must not be empty.")
        if (
            not isinstance(self.pickup_start, date)
            or isinstance(self.pickup_start, datetime)
            or not isinstance(self.pickup_end, date)
            or isinstance(self.pickup_end, datetime)
        ):
            raise ValueError("Trip pickup dates must be date values.")
        if self.pickup_end < self.pickup_start:
            raise ValueError("Trip pickup_end must not be before pickup_start.")
        if not isinstance(self.start_city, str) or not self.start_city.strip():
            raise ValueError("Trip start_city must not be empty.")
        _validate_coordinate(self.latitude, -90, 90, "Trip latitude")
        _validate_coordinate(self.longitude, -180, 180, "Trip longitude")


@dataclass(frozen=True)
class TripRecipient:
    """An email recipient belonging to one trip."""

    trip_id: str
    normalized_email: str

    def __post_init__(self) -> None:
        if not isinstance(self.trip_id, str) or not self.trip_id.strip():
            raise ValueError("TripRecipient trip_id must not be empty.")
        if not isinstance(self.normalized_email, str) or not self.normalized_email.strip():
            raise ValueError("TripRecipient normalized_email must not be empty.")


@dataclass(frozen=True)
class TripOfferView:
    """A trip-specific view of a globally stored offer."""

    trip: Trip
    offer: Offer
    distance_km: float
    is_available: bool
    state: TripOfferState
    is_sent: bool
    distance_tier: DistanceTier

    def __post_init__(self) -> None:
        if not isinstance(self.trip, Trip):
            raise TypeError("TripOfferView trip must be a Trip.")
        if not isinstance(self.offer, Offer):
            raise TypeError("TripOfferView offer must be an Offer.")
        if isinstance(self.distance_km, bool) or not isinstance(self.distance_km, (int, float)):
            raise ValueError("TripOfferView distance_km must be a finite number.")
        if not isfinite(self.distance_km) or self.distance_km < 0:
            raise ValueError("TripOfferView distance_km must be finite and non-negative.")
        if not isinstance(self.is_available, bool):
            raise ValueError("TripOfferView is_available must be a boolean.")
        if self.state not in {"new", "existing"}:
            raise ValueError("TripOfferView state must be 'new' or 'existing'.")
        if not isinstance(self.is_sent, bool):
            raise ValueError("TripOfferView is_sent must be a boolean.")
        if not isinstance(self.distance_tier, DistanceTier):
            raise TypeError("TripOfferView distance_tier must be a DistanceTier.")
        if self.distance_tier is not DistanceTier.for_distance(self.distance_km):
            raise ValueError("TripOfferView distance_tier does not match distance_km.")

    @property
    def distance_km_rounded(self) -> float:
        """Return the distance formatted for presentation."""

        return round(self.distance_km, 1)

    @property
    def trip_id(self) -> str:
        """Return the stable identity of the related trip."""

        return self.trip.trip_id

    @property
    def offer_id(self) -> str:
        """Return the stable identity of the related offer."""

        return self.offer.id

    @property
    def is_new(self) -> bool:
        """Return whether this relation is new for its trip."""

        return self.state == "new"


TripOffer = TripOfferView


def _validate_coordinate(value: object, minimum: int, maximum: int, field: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"{field} must be between {minimum} and {maximum}.")
