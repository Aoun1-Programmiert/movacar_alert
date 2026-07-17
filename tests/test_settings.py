"""Unit tests for runtime settings loading and validation."""

from pathlib import Path

import pytest

from src.config.settings import DEFAULT_POLL_INTERVAL_MINUTES, SettingsValidationError, load_settings


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
    assert settings.smtp.use_tls is True
    assert settings.http_timeout_seconds == 30.0
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


def test_load_settings_ignores_legacy_settings_without_validating_them(
    valid_environment: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    valid_environment.update(
        {
            "POLL_INTERVAL_MINUTES": "20",
            "SMTP_TO": "not-an-email-list",
            "DE_BBOX_MIN_LAT": "not-a-number",
            "LOG_FILE_PATH": "./var/movacar.log",
        }
    )

    with caplog.at_level("WARNING"):
        settings = load_settings(valid_environment)

    assert settings.poll_interval_minutes == 20
    assert settings.log_file_path == Path("./var/movacar.log")
    assert "SMTP_TO" in caplog.text
    assert "DE_BBOX_MIN_LAT" in caplog.text


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
