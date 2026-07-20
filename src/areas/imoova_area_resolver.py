"""Imoova area configuration format and point-in-polygon resolver interface.

The area mapping lives in a versioned JSON file (default
``config/imoova_areas.json``) with the shape::

    {
      "areas": [
        {"name": "Europe", "polygon": [[lat, lon], [lat, lon], ...]}
      ]
    }

Each area carries a human-readable ``name`` and a ``polygon`` given as an
ordered list of ``[latitude, longitude]`` coordinate pairs. A trip is mapped to
an area by testing its coordinates against every polygon; see
``ImoovaAreaResolver.resolve_area``. The point-in-polygon test itself is
implemented in task T05 using ``shapely``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("movacar_alert.areas.imoova_area_resolver")


class ImoovaAreaConfigError(RuntimeError):
    """Raised when the Imoova area configuration cannot be loaded or parsed."""


@dataclass(frozen=True)
class ImoovaArea:
    """One named Imoova area and its geographic boundary polygon."""

    name: str
    polygon: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Imoova area name must be a non-empty string.")
        if len(self.polygon) < 3:
            raise ValueError("Imoova area polygon needs at least three points.")


def load_areas(path: str | Path) -> tuple[ImoovaArea, ...]:
    """Load and validate the Imoova areas from the configuration file."""

    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ImoovaAreaConfigError(
            f"Imoova area configuration not found: {config_path}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ImoovaAreaConfigError(
            f"Imoova area configuration is unreadable: {config_path}"
        ) from error

    if not isinstance(raw, dict) or not isinstance(raw.get("areas"), list):
        raise ImoovaAreaConfigError(
            "Imoova area configuration must contain an 'areas' list."
        )

    areas: list[ImoovaArea] = []
    for entry in raw["areas"]:
        if not isinstance(entry, dict):
            raise ImoovaAreaConfigError("Each Imoova area must be an object.")
        name = entry.get("name")
        polygon = entry.get("polygon")
        if not isinstance(polygon, list):
            raise ImoovaAreaConfigError(
                f"Imoova area {name!r} must provide a polygon list."
            )
        try:
            points = tuple(
                (float(point[0]), float(point[1])) for point in polygon
            )
        except (TypeError, ValueError, IndexError) as error:
            raise ImoovaAreaConfigError(
                f"Imoova area {name!r} has an invalid polygon."
            ) from error
        try:
            areas.append(ImoovaArea(name=name, polygon=points))
        except ValueError as error:
            raise ImoovaAreaConfigError(str(error)) from error

    return tuple(areas)


class ImoovaAreaResolver:
    """Resolves trip coordinates to an Imoova area via point-in-polygon tests."""

    def __init__(self, areas: tuple[ImoovaArea, ...]) -> None:
        self._areas = areas

    @classmethod
    def from_file(cls, path: str | Path) -> "ImoovaAreaResolver":
        """Load the resolver once from the configuration file."""

        return cls(load_areas(path))

    def resolve_area(self, latitude: float, longitude: float) -> str | None:
        """Return the name of the area containing the coordinates, or ``None``.

        Implemented with ``shapely`` in task T05.
        """

        raise NotImplementedError("resolve_area is implemented in task T05.")
