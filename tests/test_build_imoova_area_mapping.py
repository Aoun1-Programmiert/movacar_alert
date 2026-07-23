"""Tests for the standalone Overpass-based Imoova area mapping script."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_imoova_area_mapping.py"
SPEC = importlib.util.spec_from_file_location("build_imoova_area_mapping", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
area_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(area_script)


def _response_for(name: str, relation_id: int) -> bytes:
    return json.dumps(
        {
            "elements": [
                {
                    "type": "relation",
                    "id": relation_id,
                    "tags": {"name": name, "boundary": "administrative"},
                    "members": [
                        {
                            "type": "way",
                            "role": "outer",
                            "geometry": [
                                {"lat": 0, "lon": 0},
                                {"lat": 0, "lon": 10},
                                {"lat": 10, "lon": 10},
                            ],
                        },
                        {
                            "type": "way",
                            "role": "outer",
                            "geometry": [
                                {"lat": 10, "lon": 10},
                                {"lat": 10, "lon": 0},
                                {"lat": 0, "lon": 0},
                            ],
                        },
                    ],
                }
            ]
        }
    ).encode()


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_update_area_config_writes_deterministic_polygons(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "imoova_areas.json"

    def fake_urlopen(request: object, timeout: float) -> _Response:
        assert getattr(request, "method") == "POST"
        assert getattr(request, "get_header")("User-agent").startswith("movacar-alert/")
        if b"canada" in getattr(request, "data") or b"relation%282%29" in getattr(request, "data"):
            return _Response(_response_for("Canada", 2))
        return _Response(_response_for("Europe", 1))

    monkeypatch.setattr(area_script, "urlopen", fake_urlopen)

    area_script.update_area_config(["canada", "europe"], config_path=config_path)
    first_content = config_path.read_text(encoding="utf-8")
    area_script.update_area_config(["canada", "europe"], config_path=config_path)

    assert config_path.read_text(encoding="utf-8") == first_content
    assert json.loads(first_content) == {
        "version": 1,
        "areas": [
            {"name": "Canada", "polygon": [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]},
            {"name": "Europe", "polygon": [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]},
        ],
    }


def test_update_area_config_preserves_existing_file_when_overpass_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "imoova_areas.json"
    original_content = '{"version": 1, "areas": [{"name": "Existing", "polygon": [[0, 0], [0, 1], [1, 0]]}]}\n'
    config_path.write_text(original_content, encoding="utf-8")

    def raise_error(*args: object, **kwargs: object) -> tuple[str, list[list[float]]]:
        raise area_script.OverpassError("network failure")

    monkeypatch.setattr(area_script, "fetch_area_polygon", raise_error)

    with pytest.raises(area_script.OverpassError, match="network failure"):
        area_script.update_area_config(["canada"], config_path=config_path)

    assert config_path.read_text(encoding="utf-8") == original_content


def test_fetch_area_polygon_rejects_invalid_overpass_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(area_script, "urlopen", lambda *args, **kwargs: _Response(b"{}"))

    with caplog.at_level("INFO", logger=area_script.__name__), pytest.raises(
        area_script.OverpassError, match="no elements list"
    ):
        area_script.fetch_area_polygon("canada")

    assert "Requesting Overpass area 'canada'" in caplog.text
    assert 'relation["name"~"^canada$",i]["type"="boundary"]' in caplog.text
