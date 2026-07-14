"""Highlight and state-delta rules for parsed offers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from src.config.settings import BoundingBox
from src.matcher.geo_rules import is_in_germany, is_outside_germany
from src.models.offer import ClassifiedOffer, Offer, OfferState


HIGHLIGHT_MINIMUM_DURATION = timedelta(days=2)


@dataclass(frozen=True)
class OfferDelta:
    """Deterministic classification of one polling cycle."""

    new: tuple[ClassifiedOffer, ...]
    existing: tuple[ClassifiedOffer, ...]
    removed: tuple[str, ...]

    @property
    def new_count(self) -> int:
        return len(self.new)

    @property
    def existing_count(self) -> int:
        return len(self.existing)

    @property
    def removed_count(self) -> int:
        return len(self.removed)


def is_highlighted(
    offer: Offer,
    bbox: BoundingBox | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether an offer satisfies all highlight criteria."""

    _require_offer(offer)
    try:
        duration = offer.end_date - offer.start_date
    except TypeError as error:
        raise ValueError("Offer start_date and end_date must use compatible timezones.") from error

    return (
        duration >= HIGHLIGHT_MINIMUM_DURATION
        and is_in_germany(
            offer.origin.latitude,
            offer.origin.longitude,
            bbox,
            environ=environ,
        )
        and is_outside_germany(
            offer.destination.latitude,
            offer.destination.longitude,
            bbox,
            environ=environ,
        )
    )


def classify_offers(
    offers: Iterable[Offer],
    known_offer_ids: Iterable[str] | Mapping[str, object],
    bbox: BoundingBox | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> OfferDelta:
    """Classify current offers against the previously persisted offer IDs.

    Current offer order is retained for ``new`` and ``existing`` results.
    Removed IDs are sorted so the result does not depend on set iteration order.
    """

    current_offers = tuple(offers)
    known_ids = _validated_known_ids(known_offer_ids)
    current_ids: set[str] = set()
    new: list[ClassifiedOffer] = []
    existing: list[ClassifiedOffer] = []

    for offer in current_offers:
        _require_offer(offer)
        if offer.id in current_ids:
            raise ValueError(f"Duplicate current offer ID: '{offer.id}'.")
        current_ids.add(offer.id)

        state: OfferState = "existing" if offer.id in known_ids else "new"
        classified = ClassifiedOffer(
            id=offer.id,
            start_date=offer.start_date,
            end_date=offer.end_date,
            free_km=offer.free_km,
            origin=offer.origin,
            destination=offer.destination,
            is_highlighted=is_highlighted(offer, bbox, environ=environ),
            state=state,
        )
        (existing if state == "existing" else new).append(classified)

    return OfferDelta(
        new=tuple(new),
        existing=tuple(existing),
        removed=tuple(sorted(known_ids - current_ids)),
    )


def calculate_delta(
    offers: Iterable[Offer],
    known_offer_ids: Iterable[str] | Mapping[str, object],
    bbox: BoundingBox | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> OfferDelta:
    """Alias expressing the state-comparison operation explicitly."""

    return classify_offers(offers, known_offer_ids, bbox, environ=environ)


def _validated_known_ids(
    known_offer_ids: Iterable[str] | Mapping[str, object],
) -> set[str]:
    ids = known_offer_ids.keys() if isinstance(known_offer_ids, Mapping) else known_offer_ids
    validated_ids: set[str] = set()
    for offer_id in ids:
        if not isinstance(offer_id, str) or not offer_id.strip():
            raise ValueError("known_offer_ids must contain non-empty strings.")
        validated_ids.add(offer_id)
    return validated_ids


def _require_offer(offer: Offer) -> None:
    if not isinstance(offer, Offer):
        raise TypeError("Matcher accepts only Offer instances.")
