"""Load and validate typed runtime configuration from environment variables."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse


DEFAULT_POLL_INTERVAL_MINUTES = 15


class SettingsValidationError(ValueError):
    """Raised when runtime settings are missing or malformed."""


@dataclass(frozen=True)
class SmtpSettings:
    """SMTP connection and sender configuration."""

    host: str
    port: int
    user: str
    password: str
    sender: str
    use_tls: bool


@dataclass(frozen=True)
class Settings:
    """Typed runtime configuration consumed by the application modules."""

    api_url: str
    poll_interval_minutes: int
    sqlite_path: Path
    smtp: SmtpSettings
    http_timeout_seconds: float
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
    _warn_about_legacy_settings(values)

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
            use_tls=_boolean(_required(values, "SMTP_USE_TLS"), "SMTP_USE_TLS"),
        ),
        http_timeout_seconds=_positive_float(
            _required(values, "HTTP_TIMEOUT_SECONDS"), "HTTP_TIMEOUT_SECONDS"
        ),
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


def _warn_about_legacy_settings(values: Mapping[str, str]) -> None:
    legacy_names = [
        name
        for name in (
            "SMTP_TO",
            "DE_BBOX_MIN_LAT",
            "DE_BBOX_MAX_LAT",
            "DE_BBOX_MIN_LON",
            "DE_BBOX_MAX_LON",
        )
        if values.get(name, "").strip()
    ]
    if legacy_names:
        logging.getLogger("movacar_alert.config.settings").warning(
            "Ignoring legacy settings: %s. They no longer affect recipients or offer filtering.",
            ", ".join(legacy_names),
        )
