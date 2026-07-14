"""Tests for the structured JSON logging contract."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from src.logging.logger import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    REQUIRED_EVENT_FIELDS,
    EventName,
    configure_json_logger,
    log_event,
)


def _read_events(log_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("event", "level"),
    (
        (EventName.CYCLE_STARTED, "INFO"),
        (EventName.CYCLE_COMPLETED, "INFO"),
        (EventName.CYCLE_WAITING, "INFO"),
        (EventName.API_REQUESTED, "INFO"),
        (EventName.API_SUCCEEDED, "INFO"),
        (EventName.API_FAILED, "ERROR"),
        (EventName.DELTA_CALCULATED, "INFO"),
        (EventName.NEW_OFFERS_RECEIVED, "INFO"),
        (EventName.MAIL_SENT, "INFO"),
        (EventName.MAIL_FAILED, "ERROR"),
        (EventName.DB_WRITE_SUCCEEDED, "INFO"),
        (EventName.DB_WRITE_FAILED, "ERROR"),
        (EventName.DB_READ_FAILED, "ERROR"),
        (EventName.DB_CLEANUP_SUCCEEDED, "INFO"),
        (EventName.DB_CLEANUP_FAILED, "ERROR"),
    ),
)
def test_logger_writes_contract_compliant_events_to_file_and_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    event: EventName,
    level: str,
) -> None:
    log_path = tmp_path / "logs" / "movacar.log"
    logger = configure_json_logger(log_path, logger_name=f"logger-contract-{event}")

    log_event(
        logger,
        level=level,
        event=event,
        cycle_id="cycle-42",
        message="Operational event recorded.",
        data={"offer_count": 3},
    )

    file_event = _read_events(log_path)[0]
    stdout_event = json.loads(capsys.readouterr().out)
    assert set(REQUIRED_EVENT_FIELDS).issubset(file_event)
    assert file_event == stdout_event
    assert file_event["level"] == level
    assert file_event["module"] == f"logger-contract-{event}"
    assert file_event["event"] == event
    assert file_event["cycle_id"] == "cycle-42"
    assert file_event["message"] == "Operational event recorded."
    assert file_event["offer_count"] == 3
    assert str(file_event["timestamp"]).endswith("Z")


def test_logger_rotates_files_with_configured_limits(tmp_path: Path) -> None:
    log_path = tmp_path / "movacar.log"
    logger = configure_json_logger(log_path, logger_name="logger-rotation")
    file_handler = next(
        handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)
    )

    assert file_handler.maxBytes == LOG_MAX_BYTES
    assert file_handler.backupCount == LOG_BACKUP_COUNT

    file_handler.maxBytes = 1
    log_event(
        logger,
        level="WARN",
        event=EventName.API_FAILED,
        cycle_id="cycle-43",
        message="First event triggers the configured rollover handler.",
    )
    log_event(
        logger,
        level="WARN",
        event=EventName.API_FAILED,
        cycle_id="cycle-43",
        message="Second event is written after rotation.",
    )

    assert log_path.exists()
    assert log_path.with_name("movacar.log.1").exists()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"level": "DEBUG"}, "level"),
        ({"cycle_id": " "}, "cycle_id"),
        ({"message": " "}, "message"),
        ({"data": {"event": "overridden"}}, "data"),
    ),
)
def test_logger_rejects_invalid_contract_values(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    logger = configure_json_logger(tmp_path / "movacar.log", logger_name=f"invalid-{message}")
    values: dict[str, object] = {
        "level": "INFO",
        "event": EventName.CYCLE_STARTED,
        "cycle_id": "cycle-44",
        "message": "Valid event.",
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        log_event(logger, **values)  # type: ignore[arg-type]
