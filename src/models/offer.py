"""Typed domain models for parsed and classified offers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
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


OfferState = Literal["new", "existing"]


@dataclass(frozen=True)
class ClassifiedOffer(Offer):
    """An offer annotated for mail and persistence workflow decisions."""

    is_highlighted: bool
    state: OfferState

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.is_highlighted, bool):
            raise ValueError("ClassifiedOffer is_highlighted must be a boolean.")
        if self.state not in {"new", "existing"}:
            raise ValueError("ClassifiedOffer state must be 'new' or 'existing'.")
