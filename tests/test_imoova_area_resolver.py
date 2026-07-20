"""Unit tests for the shapely-based Imoova area resolver."""

import json
from pathlib import Path

import pytest

from src.areas.imoova_area_resolver import (
    ImoovaArea,
    ImoovaAreaConfigError,
    ImoovaAreaResolver,
)

# A simple square around central Europe, given as [lat, lon] pairs.
EUROPE = ImoovaArea(
    "Europe",
    ((60.0, -10.0), (60.0, 30.0), (35.0, 30.0), (35.0, -10.0)),
)
CANADA = ImoovaArea(
    "Canada",
    ((70.0, -140.0), (70.0, -55.0), (42.0, -55.0), (42.0, -140.0)),
)


def test_coordinates_inside_exactly_one_polygon_return_its_name() -> None:
    resolver = ImoovaAreaResolver((EUROPE, CANADA))

    assert resolver.resolve_area(52.52, 13.405) == "Europe"
    assert resolver.resolve_area(45.42, -75.7) == "Canada"


def test_coordinates_outside_every_polygon_return_none() -> None:
    resolver = ImoovaAreaResolver((EUROPE, CANADA))

    assert resolver.resolve_area(-33.87, 151.21) is None


def test_coordinates_on_a_polygon_boundary_count_as_contained() -> None:
    resolver = ImoovaAreaResolver((EUROPE,))

    assert resolver.resolve_area(35.0, 10.0) == "Europe"


def test_resolver_from_file_loads_the_configuration(tmp_path: Path) -> None:
    config = tmp_path / "areas.json"
    config.write_text(
        json.dumps(
            {
                "areas": [
                    {
                        "name": "Europe",
                        "polygon": [[60.0, -10.0], [60.0, 30.0], [35.0, 30.0], [35.0, -10.0]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    resolver = ImoovaAreaResolver.from_file(config)

    assert resolver.resolve_area(52.52, 13.405) == "Europe"


def test_resolver_from_file_reports_missing_configuration(tmp_path: Path) -> None:
    with pytest.raises(ImoovaAreaConfigError):
        ImoovaAreaResolver.from_file(tmp_path / "missing.json")
