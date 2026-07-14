"""Structured JSON logging with rotating file and stdout output."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Final, Mapping


LOG_MAX_BYTES: Final = 10 * 1024 * 1024
LOG_BACKUP_COUNT: Final = 5
REQUIRED_EVENT_FIELDS: Final = (
    "timestamp",
    "level",
    "module",
    "event",
    "cycle_id",
    "message",
)


class EventName(StrEnum):
    """Names for the operational events emitted by the application."""

    CYCLE_STARTED = "cycle_started"
    CYCLE_COMPLETED = "cycle_completed"
    CYCLE_WAITING = "cycle_waiting"
    API_REQUESTED = "api_requested"
    API_SUCCEEDED = "api_succeeded"
    API_FAILED = "api_failed"
    DELTA_CALCULATED = "delta_calculated"
    NEW_OFFERS_RECEIVED = "new_offers_received"
    MAIL_SENT = "mail_sent"
    MAIL_FAILED = "mail_failed"
    DB_WRITE_SUCCEEDED = "db_write_succeeded"
    DB_WRITE_FAILED = "db_write_failed"
    DB_READ_FAILED = "db_read_failed"
    DB_CLEANUP_SUCCEEDED = "db_cleanup_succeeded"
    DB_CLEANUP_FAILED = "db_cleanup_failed"


class JsonEventFormatter(logging.Formatter):
    """Render structured application events as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": _level_name(record.levelno),
            "module": record.name,
            "event": getattr(record, "event", "unclassified"),
            "cycle_id": getattr(record, "cycle_id", "unclassified"),
            "message": record.getMessage(),
        }
        payload.update(getattr(record, "event_data", {}))
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)


def configure_json_logger(
    log_file_path: Path | None,
    *,
    logger_name: str = "movacar_alert",
) -> logging.Logger:
    """Configure the application logger with rotating file and stdout handlers.

    When a log file is configured, its handler is installed first and remains
    the primary destination. Existing handlers on this dedicated logger are
    replaced to keep repeated application setup from duplicating events.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _replace_handlers(logger)

    formatter = JsonEventFormatter()
    stdout_handler = logging.StreamHandler(sys.stdout)
    handlers: list[logging.Handler] = [stdout_handler]
    if log_file_path is not None:
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.insert(
            0,
            RotatingFileHandler(
                log_file_path,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding="utf-8",
            ),
        )
    for handler in handlers:
        handler.setLevel(logging.INFO)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def log_event(
    logger: logging.Logger,
    *,
    level: str,
    event: EventName | str,
    cycle_id: str,
    message: str,
    data: Mapping[str, Any] | None = None,
) -> None:
    """Emit one contract-compliant JSON event.

    Additional data is included as top-level JSON fields, except for contract
    fields which cannot be overridden.
    """
    if level not in {"INFO", "WARN", "ERROR"}:
        raise ValueError("level must be one of INFO, WARN, or ERROR.")
    if not cycle_id.strip():
        raise ValueError("cycle_id must not be empty.")
    if not message.strip():
        raise ValueError("message must not be empty.")

    event_data = dict(data or {})
    conflicting_fields = set(event_data).intersection(REQUIRED_EVENT_FIELDS)
    if conflicting_fields:
        field_names = ", ".join(sorted(conflicting_fields))
        raise ValueError(f"data must not override required fields: {field_names}.")

    logger.log(
        _logging_level(level),
        message,
        extra={
            "event": str(event),
            "cycle_id": cycle_id,
            "event_data": event_data,
        },
    )


def _replace_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()


def _logging_level(level: str) -> int:
    return {
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }[level]


def _level_name(level: int) -> str:
    return {
        logging.INFO: "INFO",
        logging.WARNING: "WARN",
        logging.ERROR: "ERROR",
    }.get(level, logging.getLevelName(level))
