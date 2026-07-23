"""Resolve Imoova areas from trip coordinates."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shapely.geometry import Point, Polygon
from shapely.errors import GEOSException

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "imoova_areas.json"
)


@dataclass(frozen=True)
class _ConfiguredArea:
    name: str
    polygon: Polygon


def _load_areas(config_path: Path) -> tuple[tuple[_ConfiguredArea, ...], str | None]:
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        areas = _parse_areas(raw_config)
    except FileNotFoundError:
        message = f"Imoova area configuration is missing: {config_path}"
        LOGGER.error(message)
        return (), message
    except PermissionError:
        message = f"Imoova area configuration is not readable: {config_path}"
        LOGGER.error(message)
        return (), message
    except OSError as error:
        message = f"Imoova area configuration could not be read: {config_path}: {error}"
        LOGGER.error(message)
        return (), message
    except json.JSONDecodeError as error:
        message = f"Imoova area configuration contains invalid JSON: {config_path}: {error}"
        LOGGER.error(message)
        return (), message
    except (TypeError, ValueError, GEOSException) as error:
        message = f"Imoova area configuration is invalid: {config_path}: {error}"
        LOGGER.error(message)
        return (), message

    LOGGER.info("Loaded %d Imoova areas from %s.", len(areas), config_path)
    return areas, None


def _parse_areas(raw_config: Any) -> tuple[_ConfiguredArea, ...]:
    if not isinstance(raw_config, dict):
        raise ValueError("top-level JSON value must be an object")
    if raw_config.get("version") != 1:
        raise ValueError("unsupported or missing configuration version")

    raw_areas = raw_config.get("areas")
    if not isinstance(raw_areas, list):
        raise ValueError("'areas' must be a list")

    parsed_areas: list[_ConfiguredArea] = []
    for index, raw_area in enumerate(raw_areas):
        if not isinstance(raw_area, dict):
            raise ValueError(f"area {index} must be an object")
        name = raw_area.get("name")
        raw_polygon = raw_area.get("polygon")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"area {index} has no valid name")
        if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
            raise ValueError(f"area {name!r} must contain at least three coordinates")

        coordinates = [_parse_coordinate(name, coordinate) for coordinate in raw_polygon]
        polygon = Polygon([(longitude, latitude) for latitude, longitude in coordinates])
        if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
            raise ValueError(f"area {name!r} has an invalid polygon")
        parsed_areas.append(_ConfiguredArea(name=name, polygon=polygon))

    return tuple(parsed_areas)


def _parse_coordinate(area_name: str, coordinate: Any) -> tuple[float, float]:
    if (
        not isinstance(coordinate, list)
        or len(coordinate) != 2
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in coordinate)
    ):
        raise ValueError(f"area {area_name!r} contains an invalid coordinate")
    latitude, longitude = (float(value) for value in coordinate)
    if not math.isfinite(latitude) or not math.isfinite(longitude):
        raise ValueError(f"area {area_name!r} contains a non-finite coordinate")
    return latitude, longitude


_AREAS, CONFIGURATION_ERROR = _load_areas(DEFAULT_CONFIG_PATH)


def resolve_area(latitude: float, longitude: float) -> str | None:
    """Return the configured Imoova area for a latitude/longitude pair."""

    point = Point(longitude, latitude)
    for area in _AREAS:
        if area.polygon.covers(point):
            return area.name
    return None
