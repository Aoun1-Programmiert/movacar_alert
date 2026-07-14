"""Unit tests for runtime settings loading and validation."""

from pathlib import Path

import pytest

from src.config.settings import (
    DEFAULT_DE_BBOX_MAX_LAT,
    DEFAULT_DE_BBOX_MAX_LON,
    DEFAULT_DE_BBOX_MIN_LAT,
    DEFAULT_DE_BBOX_MIN_LON,
    DEFAULT_POLL_INTERVAL_MINUTES,
    SettingsValidationError,
    load_settings,
)


@pytest.fixture
def valid_environment() -> dict[str, str]:
    return {
        "API_URL": "https://api.example.test/offers",
        "SQLITE_PATH": "./var/offers.sqlite",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USER": "mailer",
        "SMTP_PASSWORD": "secret",
        "SMTP_FROM": "sender@example.test",
        "SMTP_TO": '["recipient@example.test"]',
        "SMTP_USE_TLS": "true",
        "HTTP_TIMEOUT_SECONDS": "30",
    }


def test_load_settings_returns_typed_configuration_with_defaults(
    valid_environment: dict[str, str],
) -> None:
    settings = load_settings(valid_environment)

    assert settings.api_url == "https://api.example.test/offers"
    assert settings.poll_interval_minutes == DEFAULT_POLL_INTERVAL_MINUTES
    assert settings.sqlite_path == Path("./var/offers.sqlite")
    assert settings.smtp.host == "smtp.example.test"
    assert settings.smtp.port == 587
    assert settings.smtp.recipients == ("recipient@example.test",)
    assert settings.smtp.use_tls is True
    assert settings.http_timeout_seconds == 30.0
    assert settings.de_bbox.min_lat == DEFAULT_DE_BBOX_MIN_LAT
    assert settings.de_bbox.max_lat == DEFAULT_DE_BBOX_MAX_LAT
    assert settings.de_bbox.min_lon == DEFAULT_DE_BBOX_MIN_LON
    assert settings.de_bbox.max_lon == DEFAULT_DE_BBOX_MAX_LON
    assert settings.log_file_path is None


@pytest.mark.parametrize(
    "missing_name",
    (
        "API_URL",
        "SQLITE_PATH",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_TO",
        "SMTP_USE_TLS",
        "HTTP_TIMEOUT_SECONDS",
    ),
)
def test_load_settings_rejects_missing_required_values(
    valid_environment: dict[str, str], missing_name: str
) -> None:
    valid_environment.pop(missing_name)

    with pytest.raises(SettingsValidationError, match=missing_name):
        load_settings(valid_environment)


def test_load_settings_applies_complete_bbox_overrides(
    valid_environment: dict[str, str],
) -> None:
    valid_environment.update(
        {
            "POLL_INTERVAL_MINUTES": "20",
            "DE_BBOX_MIN_LAT": "47.0",
            "DE_BBOX_MAX_LAT": "55.0",
            "DE_BBOX_MIN_LON": "5.0",
            "DE_BBOX_MAX_LON": "15.0",
            "LOG_FILE_PATH": "./var/movacar.log",
        }
    )

    settings = load_settings(valid_environment)

    assert settings.poll_interval_minutes == 20
    assert settings.de_bbox.min_lat == 47.0
    assert settings.de_bbox.max_lon == 15.0
    assert settings.log_file_path == Path("./var/movacar.log")


def test_load_settings_rejects_partial_bbox_override(
    valid_environment: dict[str, str],
) -> None:
    valid_environment["DE_BBOX_MIN_LAT"] = "47.0"

    with pytest.raises(SettingsValidationError, match="bounding-box overrides"):
        load_settings(valid_environment)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        ("API_URL", "not-a-url", "API_URL"),
        ("POLL_INTERVAL_MINUTES", "0", "POLL_INTERVAL_MINUTES"),
        ("SMTP_PORT", "70000", "SMTP_PORT"),
        ("SMTP_USE_TLS", "sometimes", "SMTP_USE_TLS"),
        ("HTTP_TIMEOUT_SECONDS", "nan", "HTTP_TIMEOUT_SECONDS"),
    ),
)
def test_load_settings_rejects_invalid_values(
    valid_environment: dict[str, str], name: str, value: str, message: str
) -> None:
    valid_environment[name] = value

    with pytest.raises(SettingsValidationError, match=message):
        load_settings(valid_environment)


@pytest.mark.parametrize(
    "smtp_to",
    (
        "recipient@example.test",
        "[]",
        '["recipient@example.test", 3]',
        '["recipient@example.test", " "]',
    ),
)
def test_load_settings_rejects_invalid_smtp_recipient_lists(
    valid_environment: dict[str, str], smtp_to: str
) -> None:
    valid_environment["SMTP_TO"] = smtp_to

    with pytest.raises(SettingsValidationError, match="SMTP_TO"):
        load_settings(valid_environment)


def test_load_settings_accepts_multiple_smtp_recipients(
    valid_environment: dict[str, str],
) -> None:
    valid_environment["SMTP_TO"] = '["first@example.test", "second@example.test"]'

    settings = load_settings(valid_environment)

    assert settings.smtp.recipients == ("first@example.test", "second@example.test")
