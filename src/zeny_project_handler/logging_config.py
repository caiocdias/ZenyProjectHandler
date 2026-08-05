"""Logging JSON estruturado, correlacionável e seguro por construção."""

from __future__ import annotations

import json
import logging
import re
import sys
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from uuid import UUID, uuid4

from zeny_project_handler.config import AppSettings

LOGGER_NAME = "zeny_project_handler"
LOG_FILE_NAME = "application.jsonl"

_STRUCTURED_FIELDS = (
    "operation",
    "status",
    "correlation_id",
    "project_id",
    "document_id",
    "document_ids",
    "execution_id",
    "error_code",
    "item_count",
    "cache_hit",
)
_TOKEN_FIELDS = frozenset({"operation", "status", "error_code"})
_ID_FIELDS = frozenset({"correlation_id", "project_id", "document_id", "execution_id"})
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_ID_PATTERN = re.compile(r"^[A-Fa-f0-9-]{8,64}$")
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?i)(?<![\w:])[A-Z]:[\\/](?:[^\\/\r\n\"']+[\\/])*[^\r\n\"',;)]*"
)
_POSIX_PATH_PATTERN = re.compile(r"(?<![:\w])/(?:[^/\r\n\"']+/)*[^\r\n\"',;)]*")
_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|senha|secret|token|conte[uú]do|content|texto|text|"
    r"coordenadas?|coordinates?|fotos?|photos?)\b\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^,;\s}\]]+)"
)
_correlation_id: ContextVar[str | None] = ContextVar("logging_correlation_id", default=None)


def _redact_text(value: str) -> str:
    redacted = _WINDOWS_PATH_PATTERN.sub("<redacted-path>", value)
    redacted = _POSIX_PATH_PATTERN.sub("<redacted-path>", redacted)
    return _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)


def _safe_message(record: logging.LogRecord) -> str:
    """Não interpole argumentos: ``%r`` pode executar um ``repr`` sensível ou hostil."""
    if not isinstance(record.msg, str):
        return "<redacted-message>"
    message = _redact_text(record.msg)
    if record.args:
        return f"{message} [arguments-redacted]"
    return message


def _safe_identifier(value: object) -> str | None:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str) and _ID_PATTERN.fullmatch(value):
        return value
    return None


def _safe_structured_value(name: str, value: object) -> object | None:
    if name in _TOKEN_FIELDS:
        return value if isinstance(value, str) and _TOKEN_PATTERN.fullmatch(value) else None
    if name in _ID_FIELDS:
        return _safe_identifier(value)
    if name == "document_ids" and isinstance(value, (tuple, list)):
        identifiers = tuple(_safe_identifier(item) for item in value)
        return list(identifiers) if all(item is not None for item in identifiers) else None
    if name == "item_count":
        valid_count = isinstance(value, int) and not isinstance(value, bool) and value >= 0
        return value if valid_count else None
    if name == "cache_hit":
        return value if isinstance(value, bool) else None
    return None


def _safe_exception_name(error_type: type[BaseException]) -> str:
    return f"{error_type.__module__}.{error_type.__qualname__}"


def _safe_traceback(
    error_type: type[BaseException],
    error: BaseException,
    traceback_value: TracebackType | None,
    seen: set[int] | None = None,
) -> str:
    """Preserve a pilha sem caminhos absolutos, linhas-fonte ou mensagens da exceção."""
    visited = seen if seen is not None else set()
    if id(error) in visited:
        return "<exception-chain-cycle-redacted>"
    visited.add(id(error))
    lines = ["Traceback (most recent call last):"]
    current = traceback_value
    while current is not None:
        code = current.tb_frame.f_code
        file_name = Path(code.co_filename).name or "<unknown>"
        function_name = _redact_text(code.co_name)
        lines.append(f'  File "{file_name}", line {current.tb_lineno}, in {function_name}')
        current = current.tb_next
    lines.append(f"{_safe_exception_name(error_type)}: <details-redacted>")

    cause = error.__cause__
    if cause is not None:
        lines.append("Caused by:")
        lines.append(_safe_traceback(type(cause), cause, cause.__traceback__, visited))
    elif error.__context__ is not None and not error.__suppress_context__:
        context = error.__context__
        lines.append("During handling of:")
        lines.append(_safe_traceback(type(context), context, context.__traceback__, visited))
    return "\n".join(lines)


class JsonFormatter(logging.Formatter):
    """Formate somente campos explicitamente permitidos do ``LogRecord``."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _safe_message(record),
        }
        for field_name in _STRUCTURED_FIELDS:
            value = _safe_structured_value(field_name, getattr(record, field_name, None))
            if value is not None:
                payload[field_name] = value
        if record.exc_info:
            error_type, error, traceback_value = record.exc_info
            if error_type is not None and error is not None:
                payload["exception"] = _safe_traceback(error_type, error, traceback_value)
        return json.dumps(payload, ensure_ascii=False)


class _CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        correlation_id = _correlation_id.get()
        if correlation_id is not None and getattr(record, "correlation_id", None) is None:
            record.correlation_id = correlation_id
        return True


@contextmanager
def correlation_scope(correlation_id: str | None = None) -> Iterator[str]:
    """Propague uma correlação segura pela pilha síncrona atual."""
    selected = correlation_id or _correlation_id.get() or uuid4().hex
    if _safe_identifier(selected) is None:
        raise ValueError("Identificador de correlação inválido")
    token = _correlation_id.set(selected)
    try:
        yield selected
    finally:
        _correlation_id.reset(token)


@dataclass(frozen=True, slots=True)
class OperationLogger:
    """Emita o ciclo de vida de uma operação sem incluir dados livres."""

    logger: logging.Logger
    operation: str
    correlation_id: str
    identifiers: tuple[tuple[str, object], ...] = ()

    @contextmanager
    def context(self) -> Iterator[None]:
        with correlation_scope(self.correlation_id):
            yield

    def started(self, **fields: object) -> None:
        self._emit(logging.INFO, "started", fields)

    def succeeded(self, **fields: object) -> None:
        self._emit(logging.INFO, "succeeded", fields)

    def cancelled(self, **fields: object) -> None:
        self._emit(logging.INFO, "cancelled", fields)

    def failed(self, error: BaseException, *, expected: bool) -> None:
        level = logging.WARNING if expected else logging.ERROR
        self._emit(
            level,
            "failed",
            {"error_code": error.__class__.__name__},
            exc_info=None if expected else (type(error), error, error.__traceback__),
        )

    def _emit(
        self,
        level: int,
        status: str,
        fields: Mapping[str, object],
        *,
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None,
    ) -> None:
        extra = dict(self.identifiers)
        extra.update(fields)
        extra.update(
            operation=self.operation,
            status=status,
            correlation_id=self.correlation_id,
        )
        self.logger.log(
            level,
            f"{self.operation}.{status}",
            extra=extra,
            exc_info=exc_info,
        )


def operation_logger(
    operation: str,
    *,
    logger: logging.Logger | None = None,
    correlation_id: str | None = None,
    **identifiers: object,
) -> OperationLogger:
    """Crie um emissor que reutiliza a correlação atual quando houver uma."""
    selected_correlation = correlation_id or _correlation_id.get() or uuid4().hex
    if not _TOKEN_PATTERN.fullmatch(operation):
        raise ValueError("Nome de operação inválido")
    if _safe_identifier(selected_correlation) is None:
        raise ValueError("Identificador de correlação inválido")
    return OperationLogger(
        logger=logger or logging.getLogger(LOGGER_NAME),
        operation=operation,
        correlation_id=selected_correlation,
        identifiers=tuple(identifiers.items()),
    )


def _file_handler(log_directory: Path) -> RotatingFileHandler:
    log_directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_directory / LOG_FILE_NAME,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_CorrelationFilter())
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
    stream_handler.addFilter(_CorrelationFilter())
    logger.addHandler(stream_handler)

    if write_to_file:
        logger.addHandler(_file_handler(settings.data_directory / "logs"))

    return logger


def _log_unhandled_exception(
    error_type: type[BaseException],
    error: BaseException,
    traceback_value: TracebackType | None,
    *,
    operation: str,
) -> None:
    observation = operation_logger(operation)
    observation._emit(
        logging.CRITICAL,
        "failed",
        {"error_code": error_type.__name__},
        exc_info=(error_type, error, traceback_value),
    )


def _process_exception_hook(
    error_type: type[BaseException],
    error: BaseException,
    traceback_value: TracebackType | None,
) -> None:
    if issubclass(error_type, KeyboardInterrupt):
        sys.__excepthook__(error_type, error, traceback_value)
        return
    _log_unhandled_exception(
        error_type,
        error,
        traceback_value,
        operation="process.unhandled_exception",
    )


def _thread_exception_hook(arguments: threading.ExceptHookArgs) -> None:
    if arguments.exc_type is SystemExit or arguments.exc_value is None:
        return
    _log_unhandled_exception(
        arguments.exc_type,
        arguments.exc_value,
        arguments.exc_traceback,
        operation="thread.unhandled_exception",
    )


def install_unhandled_exception_logging() -> None:
    """Instale hooks idempotentes que apenas registram; eles nunca acessam widgets Qt."""
    sys.excepthook = _process_exception_hook
    threading.excepthook = _thread_exception_hook
