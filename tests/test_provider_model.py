"""Unit tests for the provider domain model added in cycle v3.0."""

from datetime import date, datetime

import pytest

from src.models.offer import (
    GeoLocation,
    Offer,
    Provider,
    Trip,
    TripProviderSelection,
)


def _offer(**overrides: object) -> Offer:
    defaults = dict(
        id="offer-1",
        start_date=datetime(2026, 7, 14, 8, 0),
        end_date=datetime(2026, 7, 16, 8, 0),
        free_km=500,
        origin=GeoLocation("Berlin", 52.52, 13.405),
        destination=GeoLocation("Paris", 48.8566, 2.3522),
        provider=Provider.MOVACAR,
    )
    defaults.update(overrides)
    return Offer(**defaults)  # type: ignore[arg-type]


def test_provider_enum_has_exactly_movacar_and_imoova() -> None:
    assert {member.value for member in Provider} == {"movacar", "imoova"}


def test_trip_provider_selection_has_movacar_imoova_and_both() -> None:
    assert {member.value for member in TripProviderSelection} == {
        "movacar",
        "imoova",
        "both",
    }


@pytest.mark.parametrize(
    "selection, expected",
    [
        (TripProviderSelection.MOVACAR, (Provider.MOVACAR,)),
        (TripProviderSelection.IMOOVA, (Provider.IMOOVA,)),
        (TripProviderSelection.BOTH, (Provider.MOVACAR, Provider.IMOOVA)),
    ],
)
def test_trip_provider_selection_resolves_to_concrete_providers(
    selection: TripProviderSelection, expected: tuple[Provider, ...]
) -> None:
    assert selection.resolve() == expected


def _trip(**overrides: object) -> Trip:
    defaults = dict(
        trip_id="trip-1",
        name="Sommerfahrt",
        pickup_start=date(2026, 7, 14),
        pickup_end=date(2026, 7, 20),
        start_city="Berlin",
        latitude=52.52,
        longitude=13.405,
    )
    defaults.update(overrides)
    return Trip(**defaults)  # type: ignore[arg-type]


def test_trip_without_provider_defaults_to_movacar() -> None:
    assert _trip().provider is TripProviderSelection.MOVACAR


def test_trip_accepts_string_provider_and_coerces_to_enum() -> None:
    assert _trip(provider="both").provider is TripProviderSelection.BOTH


def test_trip_rejects_unknown_provider_value() -> None:
    with pytest.raises(ValueError):
        _trip(provider="hertz")


def test_offer_requires_a_provider_field() -> None:
    with pytest.raises(TypeError):
        Offer(  # type: ignore[call-arg]
            id="offer-1",
            start_date=datetime(2026, 7, 14, 8, 0),
            end_date=datetime(2026, 7, 16, 8, 0),
            free_km=500,
            origin=GeoLocation("Berlin", 52.52, 13.405),
            destination=GeoLocation("Paris", 48.8566, 2.3522),
        )


def test_offer_rejects_non_provider_value() -> None:
    with pytest.raises(ValueError):
        _offer(provider="movacar")


def test_offer_keeps_assigned_provider() -> None:
    assert _offer(id="imoova:1", provider=Provider.IMOOVA).provider is Provider.IMOOVA
