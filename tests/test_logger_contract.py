"""Tests for the human-readable logging configuration."""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.logging.logger import (
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_MAX_BYTES,
    configure_logger,
)


def test_logger_writes_readable_lines_to_file_and_stdout(
    tmp_path: Path, capsys
) -> None:
    log_path = tmp_path / "logs" / "movacar.log"
    logger = configure_logger(log_path, logger_name="movacar_alert.test")

    logger.warning("API request will be retried.")

    file_line = log_path.read_text(encoding="utf-8").strip()
    stdout_line = capsys.readouterr().out.strip()
    assert file_line == stdout_line
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} — "
        r"movacar_alert\.test — WARNING — API request will be retried\.",
        file_line,
    )
    assert logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)._fmt == LOG_FORMAT


def test_logger_rotates_files_with_configured_limits(tmp_path: Path) -> None:
    log_path = tmp_path / "movacar.log"
    logger = configure_logger(log_path, logger_name="movacar_alert.rotation")
    file_handler = next(
        handler for handler in logger.handlers if isinstance(handler, RotatingFileHandler)
    )

    assert file_handler.maxBytes == LOG_MAX_BYTES
    assert file_handler.backupCount == LOG_BACKUP_COUNT

    file_handler.maxBytes = 1
    logger.error("First error triggers the configured rollover handler.")
    logger.error("Second error is written after rotation.")

    assert log_path.exists()
    assert log_path.with_name("movacar.log.1").exists()


def test_logger_outputs_to_stdout_without_a_log_file(capsys) -> None:
    logger = configure_logger(None, logger_name="movacar_alert.stdout")

    logger.error("Database write failed.")

    assert "movacar_alert.stdout — ERROR — Database write failed." in capsys.readouterr().out
