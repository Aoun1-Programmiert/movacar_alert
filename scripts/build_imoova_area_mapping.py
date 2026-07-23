"""Build Imoova area polygons from OpenStreetMap boundaries via Overpass."""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "imoova_areas.json"
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_SECONDS = 60
LOGGER = logging.getLogger(__name__)


class OverpassError(RuntimeError):
    """Raised when Overpass cannot provide a usable area boundary."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch OSM boundaries and update config/imoova_areas.json."
    )
    parser.add_argument("areas", nargs="+", help="Imoova area names, for example canada europe")
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--overpass-url", default=DEFAULT_OVERPASS_URL)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def build_overpass_query(area_name: str) -> str:
    """Return a case-insensitive exact-name relation query for one area."""

    escaped_name = re.escape(area_name.strip())
    return (
        "[out:json][timeout:60];"
        f'relation["name"~"^{escaped_name}$",i]["type"="boundary"];'
        "out tags;"
    )


def fetch_area_polygon(
    area_name: str,
    *,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[str, list[list[float]]]:
    """Fetch an OSM relation and return its canonical name and outer polygon."""

    if not area_name.strip():
        raise OverpassError("Area name must not be blank.")

    candidates = _fetch_overpass_elements(
        build_overpass_query(area_name),
        area_name=area_name,
        overpass_url=overpass_url,
        timeout_seconds=timeout_seconds,
    )
    candidates = [
        element
        for element in candidates
        if isinstance(element, dict) and element.get("type") == "relation"
    ]
    if not candidates:
        raise OverpassError(f"Overpass found no boundary relation for {area_name!r}.")

    selected_relation = min(candidates, key=_relation_sort_key)
    relation_id = selected_relation.get("id")
    if not isinstance(relation_id, int):
        raise OverpassError(f"Overpass relation for {area_name!r} has no valid ID.")
    geometry_elements = _fetch_overpass_elements(
        f"[out:json][timeout:60];relation({relation_id});out geom;",
        area_name=area_name,
        overpass_url=overpass_url,
        timeout_seconds=timeout_seconds,
    )
    relation = next(
        (
            element
            for element in geometry_elements
            if isinstance(element, dict)
            and element.get("type") == "relation"
            and element.get("id") == relation_id
        ),
        None,
    )
    if relation is None:
        raise OverpassError(f"Overpass returned no geometry for {area_name!r}.")

    canonical_name = _relation_name(relation, area_name)
    polygon = _extract_outer_polygon(relation)
    return canonical_name, polygon


def _fetch_overpass_elements(
    query: str,
    *,
    area_name: str,
    overpass_url: str,
    timeout_seconds: float,
) -> list[Any]:
    LOGGER.info(
        "Requesting Overpass area %r from %s with query: %s",
        area_name,
        overpass_url,
        query,
    )
    request = Request(
        overpass_url,
        data=urlencode({"data": query}).encode(),
        headers={"User-Agent": "movacar-alert/3.0 (Imoova area configuration builder)"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise OverpassError(f"Overpass request for {area_name!r} failed: {error}") from error

    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise OverpassError(f"Overpass returned invalid JSON for {area_name!r}.") from error

    if not isinstance(decoded, dict) or not isinstance(decoded.get("elements"), list):
        raise OverpassError(f"Overpass response for {area_name!r} has no elements list.")
    return decoded["elements"]


def update_area_config(
    area_names: list[str],
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> None:
    """Fetch all requested areas before atomically replacing the configuration."""

    existing_config = _load_existing_config(config_path)
    fetched_areas = [
        fetch_area_polygon(
            area_name,
            overpass_url=overpass_url,
            timeout_seconds=timeout_seconds,
        )
        for area_name in area_names
    ]

    areas_by_name = {
        area["name"].casefold(): area
        for area in existing_config["areas"]
    }
    for name, polygon in fetched_areas:
        areas_by_name[name.casefold()] = {"name": name, "polygon": polygon}

    updated_config = {
        "version": 1,
        "areas": sorted(areas_by_name.values(), key=lambda area: area["name"].casefold()),
    }
    _write_json_atomically(config_path, updated_config)


def _load_existing_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {"version": 1, "areas": []}

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OverpassError(
            f"Existing area configuration is unreadable or invalid: {config_path}: {error}"
        ) from error

    if (
        not isinstance(config, dict)
        or config.get("version") != 1
        or not isinstance(config.get("areas"), list)
    ):
        raise OverpassError(f"Existing area configuration has an unsupported format: {config_path}")
    return config


def _relation_sort_key(relation: dict[str, Any]) -> tuple[int, int]:
    tags = relation.get("tags")
    if not isinstance(tags, dict):
        tags = {}
    boundary_rank = 0 if tags.get("boundary") in {"administrative", "political"} else 1
    relation_id = relation.get("id")
    return boundary_rank, relation_id if isinstance(relation_id, int) else sys.maxsize


def _relation_name(relation: dict[str, Any], requested_name: str) -> str:
    tags = relation.get("tags")
    name = tags.get("name") if isinstance(tags, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise OverpassError(f"Overpass relation for {requested_name!r} has no valid name.")
    return name


def _extract_outer_polygon(relation: dict[str, Any]) -> list[list[float]]:
    direct_geometry = relation.get("geometry")
    if isinstance(direct_geometry, list):
        polygon = _geometry_to_polygon(direct_geometry)
        if polygon is not None:
            return polygon

    paths = []
    members = relation.get("members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict) or member.get("role") not in {"", "outer"}:
                continue
            geometry = member.get("geometry")
            if isinstance(geometry, list):
                polygon = _geometry_to_polygon(geometry)
                if polygon is not None:
                    return polygon
                path = _geometry_to_path(geometry)
                if path is not None:
                    paths.append(path)

    polygon = _stitch_largest_closed_path(paths)
    if polygon is None:
        raise OverpassError("Overpass relation has no usable closed outer boundary.")
    return polygon


def _geometry_to_polygon(geometry: list[Any]) -> list[list[float]] | None:
    path = _geometry_to_path(geometry)
    if path is None or path[0] != path[-1]:
        return None
    return [list(coordinate) for coordinate in path[:-1]]


def _geometry_to_path(geometry: list[Any]) -> list[tuple[float, float]] | None:
    path: list[tuple[float, float]] = []
    for coordinate in geometry:
        if not isinstance(coordinate, dict):
            return None
        latitude, longitude = coordinate.get("lat"), coordinate.get("lon")
        if (
            isinstance(latitude, bool)
            or isinstance(longitude, bool)
            or not isinstance(latitude, (int, float))
            or not isinstance(longitude, (int, float))
        ):
            return None
        path.append((float(latitude), float(longitude)))
    return path if len(path) >= 2 else None


def _stitch_largest_closed_path(
    paths: list[list[tuple[float, float]]],
) -> list[list[float]] | None:
    rings: list[list[tuple[float, float]]] = []
    remaining = [path[:] for path in paths]
    while remaining:
        ring = remaining.pop(0)
        while ring[0] != ring[-1]:
            for index, path in enumerate(remaining):
                if ring[-1] == path[0]:
                    ring.extend(path[1:])
                elif ring[-1] == path[-1]:
                    ring.extend(reversed(path[:-1]))
                elif ring[0] == path[-1]:
                    ring[:0] = path[:-1]
                elif ring[0] == path[0]:
                    ring[:0] = reversed(path[1:])
                else:
                    continue
                remaining.pop(index)
                break
            else:
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring[:-1])

    if not rings:
        return None
    largest_ring = max(rings, key=_polygon_area)
    return [list(coordinate) for coordinate in largest_ring]


def _polygon_area(polygon: list[tuple[float, float]]) -> float:
    return abs(
        sum(
            longitude * next_latitude - latitude * next_longitude
            for (latitude, longitude), (next_latitude, next_longitude) in zip(
                polygon, polygon[1:] + polygon[:1]
            )
        )
    )


def _write_json_atomically(config_path: Path, config: dict[str, Any]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(config, indent=2, ensure_ascii=True) + "\n"
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=config_path.parent,
        prefix=f".{config_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        temporary_file.write(serialized)
        temporary_path = Path(temporary_file.name)
    temporary_path.replace(config_path)


def main() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        update_area_config(
            args.areas,
            config_path=args.config_path,
            overpass_url=args.overpass_url,
            timeout_seconds=args.timeout_seconds,
        )
    except OverpassError as error:
        print(f"Could not update Imoova area configuration: {error}", file=sys.stderr)
        return 1

    print(f"Updated Imoova area configuration: {args.config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
