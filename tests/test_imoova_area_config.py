"""Tests for the Imoova area configuration format."""

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).parents[1] / "config" / "imoova_areas.json"


def test_imoova_area_config_contains_versioned_named_polygons() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert config["version"] == 1
    assert isinstance(config["areas"], list)
    assert config["areas"]

    for area in config["areas"]:
        assert isinstance(area["name"], str)
        assert area["name"]
        assert len(area["polygon"]) >= 3
        assert all(
            len(coordinate) == 2
            and all(isinstance(value, (int, float)) for value in coordinate)
            for coordinate in area["polygon"]
        )
