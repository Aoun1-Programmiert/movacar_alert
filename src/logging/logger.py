"""Human-readable application logging with rotating file and stdout output."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final


LOG_MAX_BYTES: Final = 10 * 1024 * 1024
LOG_BACKUP_COUNT: Final = 5
LOG_FORMAT: Final = "%(asctime)s — %(name)s — %(levelname)s — %(message)s"
LOG_DATE_FORMAT: Final = "%Y-%m-%d %H:%M:%S"


def configure_logger(
    log_file_path: Path | None,
    *,
    logger_name: str = "movacar_alert",
) -> logging.Logger:
    """Configure readable application logs with rotating file and stdout handlers.

    When a log file is configured, its handler is installed first and remains
    the primary destination. Existing handlers on this dedicated logger are
    replaced to keep repeated application setup from duplicating events.
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    _replace_handlers(logger)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
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


def _replace_handlers(logger: logging.Logger) -> None:
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
