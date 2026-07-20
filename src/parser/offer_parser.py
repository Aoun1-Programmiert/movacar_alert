"""Conversion of raw offers API responses into complete domain objects."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from src.models.offer import GeoLocation, Offer, Provider


class OfferParsingError(ValueError):
    """Raised when an API response cannot be converted into complete offers."""


def parse_offers(response: Mapping[str, Any]) -> list[Offer]:
    """Parse every API offer after resolving its origin and destination stations.

    The parser is intentionally all-or-nothing: a malformed record invalidates the
    response instead of allowing a partial offer set into subsequent processing.
    """

    data = _require_list(response, "data", "response")
    included = _require_list(response, "included", "response")
    stations = _index_stations(included)
    monetary_amounts = _index_resources(included, "monetary_amount")

    return [
        _parse_offer(record, index, stations, monetary_amounts)
        for index, record in enumerate(data)
    ]


def _index_stations(included: list[Any]) -> dict[str, Mapping[str, Any]]:
    stations: dict[str, Mapping[str, Any]] = {}
    for resource in included:
        if not isinstance(resource, Mapping) or resource.get("type") != "station":
            continue

        station_id = _require_string(resource, "id", "station")
        if station_id in stations:
            raise OfferParsingError(f"Duplicate station id '{station_id}' in included.")
        stations[station_id] = resource
    return stations


def _index_resources(
    included: list[Any], resource_type: str
) -> dict[str, Mapping[str, Any]]:
    resources: dict[str, Mapping[str, Any]] = {}
    for resource in included:
        if not isinstance(resource, Mapping) or resource.get("type") != resource_type:
            continue

        resource_id = _require_string(resource, "id", resource_type)
        if resource_id in resources:
            raise OfferParsingError(
                f"Duplicate {resource_type} id '{resource_id}' in included."
            )
        resources[resource_id] = resource
    return resources


def _parse_offer(
    record: Any,
    index: int,
    stations: Mapping[str, Mapping[str, Any]],
    monetary_amounts: Mapping[str, Mapping[str, Any]],
) -> Offer:
    offer = _require_mapping(record, f"data[{index}]")
    attributes = _require_mapping(offer.get("attributes"), f"data[{index}].attributes")
    relationships = _require_mapping(
        offer.get("relationships"), f"data[{index}].relationships"
    )

    origin = _resolve_station(relationships, "origin", stations, index)
    destination = _resolve_station(relationships, "destination", stations, index)
    price_minor_units, currency = _resolve_price(
        relationships, monetary_amounts, index
    )

    try:
        return Offer(
            id=_require_string(offer, "id", f"data[{index}]"),
            start_date=_parse_datetime(
                _require_string(attributes, "start_date", f"data[{index}].attributes"),
                f"data[{index}].attributes.start_date",
            ),
            end_date=_parse_datetime(
                _require_string(attributes, "end_date", f"data[{index}].attributes"),
                f"data[{index}].attributes.end_date",
            ),
            free_km=_require_integer(
                attributes, "free_km", f"data[{index}].attributes"
            ),
            origin=origin,
            destination=destination,
            provider=Provider.MOVACAR,
            price_minor_units=price_minor_units,
            currency=currency,
        )
    except ValueError as error:
        raise OfferParsingError(f"Invalid data[{index}]: {error}") from error


def _resolve_station(
    relationships: Mapping[str, Any],
    name: str,
    stations: Mapping[str, Mapping[str, Any]],
    offer_index: int,
) -> GeoLocation:
    relationship = _require_mapping(
        relationships.get(name), f"data[{offer_index}].relationships.{name}"
    )
    reference = _require_mapping(
        relationship.get("data"), f"data[{offer_index}].relationships.{name}.data"
    )
    if reference.get("type") != "station":
        raise OfferParsingError(
            f"data[{offer_index}].relationships.{name}.data must reference a station."
        )

    station_id = _require_string(
        reference, "id", f"data[{offer_index}].relationships.{name}.data"
    )
    station = stations.get(station_id)
    if station is None:
        raise OfferParsingError(
            f"data[{offer_index}].relationships.{name} references missing station "
            f"'{station_id}'."
        )

    attributes = _require_mapping(station.get("attributes"), f"station '{station_id}'.attributes")
    try:
        return GeoLocation(
            city=_require_string(attributes, "city", f"station '{station_id}'.attributes"),
            latitude=_require_number(
                attributes, "latitude", f"station '{station_id}'.attributes"
            ),
            longitude=_require_number(
                attributes, "longitude", f"station '{station_id}'.attributes"
            ),
        )
    except ValueError as error:
        raise OfferParsingError(f"Invalid station '{station_id}': {error}") from error


def _resolve_price(
    relationships: Mapping[str, Any],
    monetary_amounts: Mapping[str, Mapping[str, Any]],
    offer_index: int,
) -> tuple[int | None, str | None]:
    relationship_value = relationships.get("base_price")
    if relationship_value is None:
        return None, None

    relationship = _require_mapping(
        relationship_value, f"data[{offer_index}].relationships.base_price"
    )
    reference = _require_mapping(
        relationship.get("data"),
        f"data[{offer_index}].relationships.base_price.data",
    )
    if reference.get("type") != "monetary_amount":
        raise OfferParsingError(
            f"data[{offer_index}].relationships.base_price.data must reference "
            "a monetary_amount."
        )

    amount_id = _require_string(
        reference, "id", f"data[{offer_index}].relationships.base_price.data"
    )
    amount = monetary_amounts.get(amount_id)
    if amount is None:
        raise OfferParsingError(
            f"data[{offer_index}].relationships.base_price references missing "
            f"monetary_amount '{amount_id}'."
        )

    attributes = _require_mapping(
        amount.get("attributes"), f"monetary_amount '{amount_id}'.attributes"
    )
    return (
        _require_non_negative_integer(
            attributes,
            "amount_minor_units",
            f"monetary_amount '{amount_id}'.attributes",
        ),
        _require_string(
            attributes, "currency", f"monetary_amount '{amount_id}'.attributes"
        ),
    )


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OfferParsingError(f"{context} must be an object.")
    return value


def _require_non_negative_integer(
    container: Mapping[str, Any], key: str, context: str
) -> int:
    value = _require_integer(container, key, context)
    if value < 0:
        raise OfferParsingError(f"{context}.{key} must not be negative.")
    return value


def _require_list(container: Mapping[str, Any], key: str, context: str) -> list[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        raise OfferParsingError(f"{context}.{key} must be an array.")
    return value


def _require_string(container: Mapping[str, Any], key: str, context: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OfferParsingError(f"{context}.{key} must be a non-empty string.")
    return value


def _require_integer(container: Mapping[str, Any], key: str, context: str) -> int:
    value = container.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise OfferParsingError(f"{context}.{key} must be an integer.")
    return value


def _require_number(container: Mapping[str, Any], key: str, context: str) -> float:
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OfferParsingError(f"{context}.{key} must be a number.")
    return float(value)


def _parse_datetime(value: str, context: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise OfferParsingError(f"{context} must be an ISO-8601 datetime.") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfferParsingError(
            f"{context} must include a UTC designator or numeric UTC offset."
        )
    return parsed.astimezone(timezone.utc)
