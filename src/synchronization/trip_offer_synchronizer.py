"""Atomic synchronization of a complete offer response for one trip."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.distance.distance_service import calculate_distance_km
from src.models.offer import Offer
from src.models.trip import Trip
from src.storage.sqlite_store import SQLiteStore

DistanceCalculator = Callable[[float, float, float, float], float]


@dataclass(frozen=True)
class TripSynchronizationResult:
    """IDs affected by one successful trip synchronization."""

    trip_id: str
    offer_ids: frozenset[str]
    new_relation_ids: frozenset[str]

    @property
    def updated_relation_ids(self) -> frozenset[str]:
        """Return relations that existed before this synchronization."""

        return self.offer_ids - self.new_relation_ids


def synchronize_trip_offers(
    store: SQLiteStore,
    trip: Trip,
    offers: Iterable[Offer],
    *,
    distance_calculator: DistanceCalculator = calculate_distance_km,
) -> TripSynchronizationResult:
    """Calculate all distances and persist one complete trip result atomically."""

    if not isinstance(store, SQLiteStore):
        raise TypeError("store must be a SQLiteStore.")
    if not isinstance(trip, Trip):
        raise TypeError("trip must be a Trip.")

    validated_offers = tuple(offers)
    if any(not isinstance(offer, Offer) for offer in validated_offers):
        raise ValueError("offers must contain only valid Offer instances.")
    offer_ids = tuple(offer.id for offer in validated_offers)
    if len(set(offer_ids)) != len(offer_ids):
        raise ValueError("offers must contain unique Movacar IDs.")

    offers_with_distances = tuple(
        (
            offer,
            distance_calculator(
                trip.latitude,
                trip.longitude,
                offer.origin.latitude,
                offer.origin.longitude,
            ),
        )
        for offer in validated_offers
    )
    new_relation_ids = store.synchronize_trip_offers(
        trip.trip_id, offers_with_distances
    )
    return TripSynchronizationResult(
        trip_id=trip.trip_id,
        offer_ids=frozenset(offer_ids),
        new_relation_ids=new_relation_ids,
    )
