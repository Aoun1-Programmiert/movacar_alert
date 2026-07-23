"""Tests for resolving coordinates to configured Imoova areas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.areas.imoova_area_resolver as resolver


def _write_config(path: Path, areas: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": 1, "areas": areas}),
        encoding="utf-8",
    )


def _use_config(monkeypatch: pytest.MonkeyPatch, path: Path):
    areas, configuration_error = resolver._load_areas(path)
    monkeypatch.setattr(resolver, "_AREAS", areas)
    monkeypatch.setattr(resolver, "CONFIGURATION_ERROR", configuration_error)
    return resolver


def test_resolve_area_returns_matching_polygon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "areas.json"
    _write_config(
        config_path,
        [{"name": "Test Area", "polygon": [[0, 0], [0, 10], [10, 10], [10, 0]]}],
    )
    loaded_resolver = _use_config(monkeypatch, config_path)

    assert loaded_resolver.resolve_area(5, 5) == "Test Area"


def test_resolve_area_returns_none_without_matching_polygon(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "areas.json"
    _write_config(
        config_path,
        [{"name": "Test Area", "polygon": [[0, 0], [0, 10], [10, 10], [10, 0]]}],
    )
    loaded_resolver = _use_config(monkeypatch, config_path)

    assert loaded_resolver.resolve_area(20, 20) is None


def test_missing_configuration_is_logged_and_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing_path = tmp_path / "missing.json"
    loaded_resolver = _use_config(monkeypatch, missing_path)

    assert loaded_resolver.resolve_area(5, 5) is None
    assert loaded_resolver.CONFIGURATION_ERROR is not None
    assert "missing" in caplog.text.lower()


def test_invalid_configuration_is_logged_and_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config_path = tmp_path / "invalid.json"
    config_path.write_text("{not-json", encoding="utf-8")
    loaded_resolver = _use_config(monkeypatch, config_path)

    assert loaded_resolver.resolve_area(5, 5) is None
    assert loaded_resolver.CONFIGURATION_ERROR is not None
    assert "invalid json" in caplog.text.lower()


def test_boundary_coordinate_is_considered_inside(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "areas.json"
    _write_config(
        config_path,
        [{"name": "Test Area", "polygon": [[0, 0], [0, 10], [10, 10], [10, 0]]}],
    )
    loaded_resolver = _use_config(monkeypatch, config_path)

    assert loaded_resolver.resolve_area(0, 5) == "Test Area"
