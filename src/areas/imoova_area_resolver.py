"""Public interface for resolving Imoova areas from trip coordinates."""


def resolve_area(latitude: float, longitude: float) -> str | None:
    """Return the configured Imoova area for coordinates, if one exists."""

    raise NotImplementedError("Imoova area resolution is implemented in T05.")
