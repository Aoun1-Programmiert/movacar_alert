"""Load and validate typed runtime configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


DEFAULT_POLL_INTERVAL_MINUTES = 15
DEFAULT_DE_BBOX_MIN_LAT = 47.2701114
DEFAULT_DE_BBOX_MAX_LAT = 55.058347
DEFAULT_DE_BBOX_MIN_LON = 5.8663425
DEFAULT_DE_BBOX_MAX_LON = 15.0418962


class SettingsValidationError(ValueError):
    """Raised when runtime settings are missing or malformed."""


@dataclass(frozen=True)
class BoundingBox:
    """Geographic bounds expressed as latitude and longitude limits."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP connection and message addressing configuration."""

    host: str
    port: int
    user: str
    password: str
    sender: str
    recipient: str
    use_tls: bool


@dataclass(frozen=True)
class Settings:
    """Typed runtime configuration consumed by the application modules."""

    api_url: str
    poll_interval_minutes: int
    sqlite_path: Path
    smtp: SmtpSettings
    http_timeout_seconds: float
    de_bbox: BoundingBox
    log_file_path: Path | None


def load_settings(
    environ: Mapping[str, str] | None = None,
    *,
    env_file: Path | None = Path(".env"),
) -> Settings:
    """Load settings from ``.env`` and process environment variables.

    A supplied ``environ`` mapping is used as-is, which keeps callers and unit
    tests independent from process state. In normal operation, values from the
    process environment override values defined in ``.env``.
    """

    values = (
        dict(environ)
        if environ is not None
        else {**_load_env_file(env_file), **os.environ}
    )

    api_url = _required(values, "API_URL")
    _validate_http_url(api_url, "API_URL")

    return Settings(
        api_url=api_url,
        poll_interval_minutes=_positive_integer(
            values.get("POLL_INTERVAL_MINUTES", str(DEFAULT_POLL_INTERVAL_MINUTES)),
            "POLL_INTERVAL_MINUTES",
        ),
        sqlite_path=Path(_required(values, "SQLITE_PATH")),
        smtp=SmtpSettings(
            host=_required(values, "SMTP_HOST"),
            port=_port(_required(values, "SMTP_PORT")),
            user=_required(values, "SMTP_USER"),
            password=_required(values, "SMTP_PASSWORD"),
            sender=_required(values, "SMTP_FROM"),
            recipient=_required(values, "SMTP_TO"),
            use_tls=_boolean(_required(values, "SMTP_USE_TLS"), "SMTP_USE_TLS"),
        ),
        http_timeout_seconds=_positive_float(
            _required(values, "HTTP_TIMEOUT_SECONDS"), "HTTP_TIMEOUT_SECONDS"
        ),
        de_bbox=_load_bbox(values),
        log_file_path=_optional_path(values.get("LOG_FILE_PATH")),
    )


def _load_env_file(env_file: Path | None) -> dict[str, str]:
    if env_file is None or not env_file.is_file():
        return {}

    values: dict[str, str] = {}
    for line_number, line in enumerate(env_file.read_text(encoding="utf-8").splitlines(), start=1):
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue
        if "=" not in stripped_line:
            raise SettingsValidationError(
                f"Invalid .env entry at line {line_number}: expected KEY=VALUE."
            )
        key, value = stripped_line.split("=", maxsplit=1)
        if not key:
            raise SettingsValidationError(
                f"Invalid .env entry at line {line_number}: key must not be empty."
            )
        values[key] = value
    return values


def _load_bbox(values: Mapping[str, str]) -> BoundingBox:
    variable_names = (
        "DE_BBOX_MIN_LAT",
        "DE_BBOX_MAX_LAT",
        "DE_BBOX_MIN_LON",
        "DE_BBOX_MAX_LON",
    )
    provided_names = [name for name in variable_names if values.get(name, "").strip()]
    if provided_names and len(provided_names) != len(variable_names):
        missing_names = ", ".join(name for name in variable_names if name not in provided_names)
        raise SettingsValidationError(
            f"DE bounding-box overrides must be specified together; missing: {missing_names}."
        )

    bbox = BoundingBox(
        min_lat=_float_or_default(
            values.get("DE_BBOX_MIN_LAT"), DEFAULT_DE_BBOX_MIN_LAT, "DE_BBOX_MIN_LAT"
        ),
        max_lat=_float_or_default(
            values.get("DE_BBOX_MAX_LAT"), DEFAULT_DE_BBOX_MAX_LAT, "DE_BBOX_MAX_LAT"
        ),
        min_lon=_float_or_default(
            values.get("DE_BBOX_MIN_LON"), DEFAULT_DE_BBOX_MIN_LON, "DE_BBOX_MIN_LON"
        ),
        max_lon=_float_or_default(
            values.get("DE_BBOX_MAX_LON"), DEFAULT_DE_BBOX_MAX_LON, "DE_BBOX_MAX_LON"
        ),
    )
    if bbox.min_lat >= bbox.max_lat or bbox.min_lon >= bbox.max_lon:
        raise SettingsValidationError("DE bounding-box minimum values must be lower than maximum values.")
    return bbox


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise SettingsValidationError(f"Missing required environment variable: {name}.")
    return value


def _validate_http_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsValidationError(f"{name} must be an absolute HTTP(S) URL.")


def _positive_integer(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise SettingsValidationError(f"{name} must be an integer.") from error
    if parsed <= 0:
        raise SettingsValidationError(f"{name} must be greater than zero.")
    return parsed


def _port(value: str) -> int:
    port = _positive_integer(value, "SMTP_PORT")
    if port > 65535:
        raise SettingsValidationError("SMTP_PORT must not exceed 65535.")
    return port


def _positive_float(value: str, name: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise SettingsValidationError(f"{name} must be a number.") from error
    if not isfinite(parsed) or parsed <= 0:
        raise SettingsValidationError(f"{name} must be greater than zero.")
    return parsed


def _float_or_default(value: str | None, default: float, name: str) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as error:
        raise SettingsValidationError(f"{name} must be a number.") from error
    if not isfinite(parsed):
        raise SettingsValidationError(f"{name} must be a finite number.")
    return parsed


def _boolean(value: str, name: str) -> bool:
    normalized_value = value.lower()
    if normalized_value == "true":
        return True
    if normalized_value == "false":
        return False
    raise SettingsValidationError(f"{name} must be either true or false.")


def _optional_path(value: str | None) -> Path | None:
    if value is None or not value.strip():
        return None
    return Path(value.strip())
