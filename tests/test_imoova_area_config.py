"""Unit tests for the Imoova area configuration format and loader."""

import json
from pathlib import Path

import pytest

from src.areas.imoova_area_resolver import (
    ImoovaArea,
    ImoovaAreaConfigError,
    ImoovaAreaResolver,
    load_areas,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_repository_example_config_has_at_least_one_area() -> None:
    areas = load_areas(REPO_ROOT / "config" / "imoova_areas.json")

    assert len(areas) >= 1
    assert all(isinstance(area, ImoovaArea) for area in areas)
    assert all(len(area.polygon) >= 3 for area in areas)


def test_loader_accepts_arbitrary_number_of_named_polygon_areas(
    tmp_path: Path,
) -> None:
    config = _write(
        tmp_path / "areas.json",
        {
            "areas": [
                {"name": "Europe", "polygon": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]},
                {"name": "Canada", "polygon": [[10, 20], [30, 40], [50, 60], [10, 20]]},
            ]
        },
    )

    areas = load_areas(config)

    assert [area.name for area in areas] == ["Europe", "Canada"]
    assert areas[0].polygon == ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))


def test_loader_rejects_missing_areas_list(tmp_path: Path) -> None:
    config = _write(tmp_path / "areas.json", {"regions": []})

    with pytest.raises(ImoovaAreaConfigError, match="'areas' list"):
        load_areas(config)


def test_loader_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImoovaAreaConfigError, match="not found"):
        load_areas(tmp_path / "does-not-exist.json")


def test_resolver_exposes_lat_lon_interface_returning_name_or_none() -> None:
    resolver = ImoovaAreaResolver(
        (ImoovaArea("Europe", ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))),)
    )

    with pytest.raises(NotImplementedError):
        resolver.resolve_area(52.52, 13.405)
