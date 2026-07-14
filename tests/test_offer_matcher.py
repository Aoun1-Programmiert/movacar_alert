"""Unit tests for offer highlighting and state deltas."""

from datetime import datetime, timedelta, timezone

import pytest

from src.config.settings import BoundingBox
from src.matcher.offer_matcher import OfferDelta, calculate_delta, is_highlighted
from src.models.offer import GeoLocation, Offer


GERMANY = GeoLocation("Berlin", 52.52, 13.405)
ABROAD = GeoLocation("Paris", 48.8566, 2.3522)
GERMANY_BBOX = BoundingBox(47.0, 55.0, 5.0, 16.0)


def make_offer(
    offer_id: str = "offer-1",
    *,
    duration: timedelta = timedelta(days=2),
    origin: GeoLocation = GERMANY,
    destination: GeoLocation = ABROAD,
) -> Offer:
    start = datetime(2026, 7, 14, 8, 0, tzinfo=timezone.utc)
    return Offer(
        id=offer_id,
        start_date=start,
        end_date=start + duration,
        free_km=500,
        origin=origin,
        destination=destination,
    )


def test_highlight_requires_duration_and_both_geo_conditions() -> None:
    assert is_highlighted(make_offer(), GERMANY_BBOX)
    assert not is_highlighted(
        make_offer(duration=timedelta(days=2) - timedelta(seconds=1)), GERMANY_BBOX
    )
    assert not is_highlighted(
        make_offer(origin=ABROAD), GERMANY_BBOX
    )
    assert not is_highlighted(
        make_offer(destination=GERMANY), GERMANY_BBOX
    )


def test_highlight_includes_exactly_two_days_and_bbox_boundaries() -> None:
    boundary_origin = GeoLocation("Boundary DE", 47.0, 5.0)
    boundary_destination = GeoLocation("Boundary abroad", 56.0, 16.0)

    assert is_highlighted(
        make_offer(origin=boundary_origin, destination=boundary_destination),
        GERMANY_BBOX,
    )


def test_highlight_uses_environment_bbox_override() -> None:
    environment = {
        "DE_BBOX_MIN_LAT": "10",
        "DE_BBOX_MAX_LAT": "20",
        "DE_BBOX_MIN_LON": "30",
        "DE_BBOX_MAX_LON": "40",
    }
    origin = GeoLocation("Configured DE", 15, 35)
    destination = GeoLocation("Outside configured DE", 25, 35)

    assert is_highlighted(
        make_offer(origin=origin, destination=destination),
        environ=environment,
    )


def test_calculate_delta_classifies_new_existing_and_removed() -> None:
    current = [make_offer("new"), make_offer("existing")]

    delta = calculate_delta(current, {"existing", "removed"}, GERMANY_BBOX)

    assert isinstance(delta, OfferDelta)
    assert [offer.id for offer in delta.new] == ["new"]
    assert [offer.id for offer in delta.existing] == ["existing"]
    assert delta.removed == ("removed",)
    assert delta.new[0].state == "new"
    assert delta.existing[0].state == "existing"


@pytest.mark.parametrize(
    ("current_ids", "known_ids", "expected_new", "expected_existing", "expected_removed"),
    (
        ([], set(), (), (), ()),
        (["one"], set(), ("one",), (), ()),
        (["one"], {"one"}, (), ("one",), ()),
        ([], {"one"}, (), (), ("one",)),
        (["one", "two"], {"two", "three"}, ("one",), ("two",), ("three",)),
    ),
)
def test_delta_covers_all_state_transitions(
    current_ids: list[str],
    known_ids: set[str],
    expected_new: tuple[str, ...],
    expected_existing: tuple[str, ...],
    expected_removed: tuple[str, ...],
) -> None:
    delta = calculate_delta(
        [make_offer(offer_id) for offer_id in current_ids],
        known_ids,
        GERMANY_BBOX,
    )

    assert tuple(offer.id for offer in delta.new) == expected_new
    assert tuple(offer.id for offer in delta.existing) == expected_existing
    assert delta.removed == expected_removed


def test_identical_input_produces_equal_deltas() -> None:
    current = [make_offer("b"), make_offer("a")]

    first = calculate_delta(current, {"a", "removed"}, GERMANY_BBOX)
    second = calculate_delta(current, {"a", "removed"}, GERMANY_BBOX)

    assert first == second


def test_matcher_rejects_duplicate_or_invalid_input() -> None:
    with pytest.raises(ValueError, match="Duplicate current offer ID"):
        calculate_delta([make_offer(), make_offer()], set(), GERMANY_BBOX)
    with pytest.raises(ValueError, match="non-empty strings"):
        calculate_delta([], [""], GERMANY_BBOX)
    with pytest.raises(TypeError, match="Offer instances"):
        calculate_delta([object()], set(), GERMANY_BBOX)  # type: ignore[list-item]
