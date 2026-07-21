"""Logging estruturado com um conjunto deliberadamente pequeno de campos."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from zeny_project_handler.config import AppSettings

LOGGER_NAME = "zeny_project_handler"
LOG_FILE_NAME = "application.jsonl"


class JsonFormatter(logging.Formatter):
    """Formate eventos como JSON sem serializar o ambiente ou o ``LogRecord`` inteiro."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _file_handler(log_directory: Path) -> RotatingFileHandler:
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_directory / LOG_FILE_NAME,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    return handler


def configure_logging(settings: AppSettings, *, write_to_file: bool = True) -> logging.Logger:
    """Configure e retorne o logger raiz da aplicação de forma idempotente."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.propagate = False

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JsonFormatter())
    logger.addHandler(stream_handler)

    if write_to_file:
        logger.addHandler(_file_handler(settings.data_directory / "logs"))

    return logger
