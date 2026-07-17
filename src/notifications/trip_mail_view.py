"""Prepared, trip-scoped input for notification mail composers."""

from __future__ import annotations

from dataclasses import dataclass

from src.models.offer import Trip, TripOfferView
from src.storage.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class TripMailView:
    """Mail data for one trip with its explicit recipients and offer sections."""

    trip: Trip
    recipients: tuple[str, ...]
    new_offers: tuple[TripOfferView, ...]
    available_offers: tuple[TripOfferView, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trip, Trip):
            raise TypeError("TripMailView trip must be a Trip.")
        if any(not isinstance(recipient, str) or not recipient for recipient in self.recipients):
            raise ValueError("TripMailView recipients must be non-empty email strings.")
        if len(set(self.recipients)) != len(self.recipients):
            raise ValueError("TripMailView recipients must be unique.")
        self._validate_offers(self.new_offers, require_unsent=True)
        self._validate_offers(self.available_offers, require_unsent=False)

    def _validate_offers(
        self, offers: tuple[TripOfferView, ...], *, require_unsent: bool
    ) -> None:
        previous_distance = -1.0
        for offer_view in offers:
            if not isinstance(offer_view, TripOfferView):
                raise TypeError("TripMailView offers must be TripOfferView instances.")
            if offer_view.trip != self.trip or not offer_view.is_available:
                raise ValueError("TripMailView offers must be available for its trip.")
            if require_unsent and (offer_view.is_sent or not offer_view.is_new):
                raise ValueError("TripMailView new_offers must be new and unsent.")
            if offer_view.distance_km < previous_distance:
                raise ValueError("TripMailView offers must be ordered by distance.")
            previous_distance = offer_view.distance_km


def prepare_trip_mail_view(store: SQLiteStore, trip: Trip) -> TripMailView:
    """Load the two ordered offer sections and recipients for one trip."""

    if not isinstance(store, SQLiteStore):
        raise TypeError("store must be a SQLiteStore.")
    if not isinstance(trip, Trip):
        raise TypeError("trip must be a Trip.")

    recipients = tuple(
        recipient.normalized_email
        for recipient in store.list_trip_recipients(trip.trip_id)
    )
    new_offers = tuple(store.list_new_unsent_available_trip_offers(trip.trip_id))
    available_offers = tuple(store.list_available_trip_offers(trip.trip_id))
    return TripMailView(trip, recipients, new_offers, available_offers)
