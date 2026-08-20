"""Logging local do cliente com redação de credenciais e caminhos."""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from types import TracebackType
from uuid import uuid4

from zeny_project_handler_client.config import ClientSettings

LOGGER_NAME = "zeny_project_handler_client"
LOG_FILE_NAME = "client.jsonl"
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;}\]]+")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|password|senha|secret|token)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^,;\s}\]]+)"
)


class _SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.msg if isinstance(record.msg, str) else "<redacted-message>"
        message = _SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}=<redacted>",
            _BEARER_PATTERN.sub("Bearer <redacted>", message),
        )
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": message,
        }
        for name in ("operation", "status", "correlation_id", "error_code", "item_count"):
            value = getattr(record, name, None)
            if isinstance(value, (str, int)):
                payload[name] = value
        return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class OperationLogger:
    logger: logging.Logger
    operation: str
    correlation_id: str
    identifiers: tuple[tuple[str, object], ...] = ()

    @contextmanager
    def context(self) -> Iterator[None]:
        yield

    def started(self, **fields: object) -> None:
        self._emit(logging.INFO, "started", fields)

    def succeeded(self, **fields: object) -> None:
        self._emit(logging.INFO, "succeeded", fields)

    def cancelled(self, **fields: object) -> None:
        self._emit(logging.INFO, "cancelled", fields)

    def failed(self, error: BaseException, *, expected: bool, **fields: object) -> None:
        data = dict(fields)
        data["error_code"] = error.__class__.__name__
        self._emit(logging.WARNING if expected else logging.ERROR, "failed", data)

    def _emit(self, level: int, status: str, fields: Mapping[str, object]) -> None:
        extra = dict(self.identifiers)
        extra.update(fields)
        extra.update(
            operation=self.operation,
            status=status,
            correlation_id=self.correlation_id,
        )
        self.logger.log(level, f"{self.operation}.{status}", extra=extra)


def operation_logger(
    operation: str,
    *,
    logger: logging.Logger | None = None,
    correlation_id: str | None = None,
    **identifiers: object,
) -> OperationLogger:
    if not _TOKEN_PATTERN.fullmatch(operation):
        raise ValueError("Nome de operação inválido")
    return OperationLogger(
        logger or logging.getLogger(LOGGER_NAME),
        operation,
        correlation_id or uuid4().hex,
        tuple(identifiers.items()),
    )


def configure_logging(
    settings: ClientSettings,
    *,
    write_to_file: bool = True,
) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.log_level)
    logger.propagate = False
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    formatter = _SafeJsonFormatter()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if write_to_file:
        log_directory = settings.data_directory / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_directory / LOG_FILE_NAME,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


def _unhandled(
    error_type: type[BaseException],
    error: BaseException,
    _traceback: TracebackType | None,
) -> None:
    operation_logger("client.unhandled_exception").failed(error, expected=False)
    if issubclass(error_type, KeyboardInterrupt):
        sys.__excepthook__(error_type, error, _traceback)


def _thread_unhandled(arguments: threading.ExceptHookArgs) -> None:
    if arguments.exc_value is not None and arguments.exc_type is not SystemExit:
        _unhandled(arguments.exc_type, arguments.exc_value, arguments.exc_traceback)


def install_unhandled_exception_logging() -> None:
    sys.excepthook = _unhandled
    threading.excepthook = _thread_unhandled
