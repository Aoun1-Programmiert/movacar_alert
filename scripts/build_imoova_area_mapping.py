#!/usr/bin/env python3
"""Build or refresh ``config/imoova_areas.json`` from OpenStreetMap.

For every configured Imoova area this script queries the Overpass API directly
over HTTP for the geographic boundary of an OSM relation and writes the
resulting polygon into the area configuration file consumed by
``src.areas.imoova_area_resolver``.

The script never runs inside the polling path. It has no third-party GIS
dependency (no ``osmnx``); it only uses the standard library plus the Overpass
HTTP endpoint. A run is all-or-nothing: the mapping is fully built in memory and
only written when every area was fetched successfully, so a network or response
error never corrupts an already valid configuration file.

Usage::

    python scripts/build_imoova_area_mapping.py [--output config/imoova_areas.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LOGGER = logging.getLogger("movacar_alert.scripts.build_imoova_area_mapping")

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_OUTPUT = Path("config/imoova_areas.json")
COORDINATE_PRECISION = 5

HttpGet = Callable[[str, str], str]


@dataclass(frozen=True)
class AreaSpec:
    """One Imoova area mapped to the OSM relation describing its boundary."""

    name: str
    osm_relation_id: int


# Imoova areas mapped to representative OSM relation ids for their boundary.
AREA_SPECS: tuple[AreaSpec, ...] = (
    AreaSpec(name="Europe", osm_relation_id=2214463),
    AreaSpec(name="Canada", osm_relation_id=1428125),
    AreaSpec(name="Australia", osm_relation_id=80500),
)


class OverpassError(RuntimeError):
    """Raised when the Overpass API cannot be queried or parsed."""


def _overpass_query(osm_relation_id: int) -> str:
    return (
        "[out:json];"
        f"relation({osm_relation_id});"
        "out geom;"
    )


def _http_post(overpass_url: str, query: str) -> str:
    request = urllib.request.Request(
        overpass_url,
        data=query.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except (urllib.error.URLError, OSError) as error:
        raise OverpassError(f"Overpass request failed: {error}") from error


def parse_overpass_polygon(response_text: str) -> tuple[tuple[float, float], ...]:
    """Extract an ordered ``(lat, lon)`` polygon from an Overpass response."""

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise OverpassError("Overpass response is not valid JSON.") from error

    elements = payload.get("elements") if isinstance(payload, dict) else None
    if not isinstance(elements, list):
        raise OverpassError("Overpass response contains no elements.")

    points: list[tuple[float, float]] = []
    for element in elements:
        geometry = element.get("geometry") if isinstance(element, dict) else None
        if isinstance(geometry, list):
            for node in geometry:
                if (
                    isinstance(node, dict)
                    and "lat" in node
                    and "lon" in node
                ):
                    points.append(
                        (
                            round(float(node["lat"]), COORDINATE_PRECISION),
                            round(float(node["lon"]), COORDINATE_PRECISION),
                        )
                    )
        members = element.get("members") if isinstance(element, dict) else None
        if isinstance(members, list):
            for member in members:
                geometry = (
                    member.get("geometry") if isinstance(member, dict) else None
                )
                if isinstance(geometry, list):
                    for node in geometry:
                        if (
                            isinstance(node, dict)
                            and "lat" in node
                            and "lon" in node
                        ):
                            points.append(
                                (
                                    round(float(node["lat"]), COORDINATE_PRECISION),
                                    round(float(node["lon"]), COORDINATE_PRECISION),
                                )
                            )

    if len(points) < 3:
        raise OverpassError("Overpass response did not yield a usable polygon.")
    return tuple(points)


def build_mapping(
    area_specs: tuple[AreaSpec, ...] = AREA_SPECS,
    *,
    overpass_url: str = DEFAULT_OVERPASS_URL,
    http_post: HttpGet | None = None,
) -> dict[str, object]:
    """Fetch all area polygons and build the in-memory configuration mapping."""

    fetch = http_post if http_post is not None else _http_post
    areas: list[dict[str, object]] = []
    for spec in sorted(area_specs, key=lambda item: item.name):
        LOGGER.info("Fetching Overpass boundary for area %s", spec.name)
        response_text = fetch(overpass_url, _overpass_query(spec.osm_relation_id))
        polygon = parse_overpass_polygon(response_text)
        areas.append(
            {"name": spec.name, "polygon": [[lat, lon] for lat, lon in polygon]}
        )
    return {"areas": areas}


def serialize_mapping(mapping: dict[str, object]) -> str:
    """Serialize the mapping deterministically for a stable file on re-runs."""

    return json.dumps(mapping, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_mapping(output_path: Path, mapping: dict[str, object]) -> None:
    """Write the mapping only after it was fully and successfully built."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_mapping(mapping), encoding="utf-8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overpass-url", default=DEFAULT_OVERPASS_URL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        mapping = build_mapping(overpass_url=args.overpass_url)
    except OverpassError as error:
        LOGGER.error(
            "Aborting without touching %s: %s", args.output, error
        )
        return 1
    write_mapping(args.output, mapping)
    LOGGER.info("Wrote %d areas to %s", len(mapping["areas"]), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
