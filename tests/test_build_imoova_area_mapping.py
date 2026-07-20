"""Unit tests for the Overpass-based Imoova area mapping script."""

import json
from pathlib import Path

import pytest

from scripts.build_imoova_area_mapping import (
    AreaSpec,
    OverpassError,
    build_mapping,
    main,
    parse_overpass_polygon,
    serialize_mapping,
    write_mapping,
)


def _relation_response() -> str:
    return json.dumps(
        {
            "elements": [
                {
                    "type": "relation",
                    "members": [
                        {
                            "geometry": [
                                {"lat": 60.0, "lon": -10.0},
                                {"lat": 60.0, "lon": 30.0},
                                {"lat": 35.0, "lon": 30.0},
                                {"lat": 35.0, "lon": -10.0},
                            ]
                        }
                    ],
                }
            ]
        }
    )


def test_parse_overpass_polygon_extracts_ordered_points() -> None:
    polygon = parse_overpass_polygon(_relation_response())

    assert polygon == (
        (60.0, -10.0),
        (60.0, 30.0),
        (35.0, 30.0),
        (35.0, -10.0),
    )


def test_parse_overpass_polygon_rejects_degenerate_geometry() -> None:
    response = json.dumps({"elements": [{"geometry": [{"lat": 1.0, "lon": 2.0}]}]})

    with pytest.raises(OverpassError):
        parse_overpass_polygon(response)


def test_build_mapping_uses_injected_http_and_sorts_areas() -> None:
    calls: list[str] = []

    def fake_http(url: str, query: str) -> str:
        calls.append(query)
        return _relation_response()

    mapping = build_mapping(
        (AreaSpec("Europe", 1), AreaSpec("Canada", 2)),
        http_post=fake_http,
    )

    assert [area["name"] for area in mapping["areas"]] == ["Canada", "Europe"]
    assert len(calls) == 2


def test_repeated_run_with_unchanged_areas_is_byte_stable() -> None:
    def fake_http(url: str, query: str) -> str:
        return _relation_response()

    first = serialize_mapping(build_mapping((AreaSpec("Europe", 1),), http_post=fake_http))
    second = serialize_mapping(build_mapping((AreaSpec("Europe", 1),), http_post=fake_http))

    assert first == second


def test_network_error_leaves_existing_valid_config_untouched(tmp_path: Path) -> None:
    output = tmp_path / "imoova_areas.json"
    original = '{"areas": [{"name": "Europe", "polygon": [[1, 2], [3, 4], [5, 6]]}]}'
    output.write_text(original, encoding="utf-8")

    def failing_http(url: str, query: str) -> str:
        raise OverpassError("network down")

    import scripts.build_imoova_area_mapping as module

    monkeypatched = module._http_post
    module._http_post = failing_http  # type: ignore[assignment]
    try:
        exit_code = main(["--output", str(output)])
    finally:
        module._http_post = monkeypatched  # type: ignore[assignment]

    assert exit_code == 1
    assert output.read_text(encoding="utf-8") == original


def test_write_mapping_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "imoova_areas.json"

    write_mapping(output, {"areas": []})

    assert json.loads(output.read_text(encoding="utf-8")) == {"areas": []}
