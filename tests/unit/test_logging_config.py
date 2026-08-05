from __future__ import annotations

import io
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Never
from uuid import UUID

from zeny_project_handler.config import AppSettings
from zeny_project_handler.logging_config import (
    JsonFormatter,
    configure_logging,
    install_unhandled_exception_logging,
    operation_logger,
)

CORRELATION_ID = "1234567890abcdef1234567890abcdef"
PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
DOCUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")


class HostileValue:
    def __repr__(self) -> Never:
        raise AssertionError("repr não deveria ser chamado")

    def __str__(self) -> Never:
        raise AssertionError("str não deveria ser chamado")


def _json_handler(stream: io.StringIO) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    return handler


def _payloads(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_json_formatter_exposes_only_supported_structured_fields() -> None:
    record = logging.LogRecord(
        name="zeny_project_handler.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="application.started",
        args=(),
        exc_info=None,
    )
    record.operation = "application.bootstrap"
    record.status = "started"
    record.correlation_id = CORRELATION_ID
    record.project_id = PROJECT_ID
    record.password = "não-deve-aparecer"
    record.pdf_text = "conteúdo confidencial"
    record.coordinates = (1, 2)
    record.path = Path("C:/clientes/segredo.pdf")
    record.photo = b"imagem"

    payload = json.loads(JsonFormatter().format(record))

    assert set(payload) == {
        "timestamp",
        "level",
        "logger",
        "event",
        "operation",
        "status",
        "correlation_id",
        "project_id",
    }
    assert payload["project_id"] == str(PROJECT_ID)
    serialized = json.dumps(payload)
    assert "não-deve-aparecer" not in serialized
    assert "conteúdo confidencial" not in serialized
    assert "clientes" not in serialized


def test_formatter_redacts_messages_without_evaluating_repr_or_extra() -> None:
    record = logging.LogRecord(
        name="zeny_project_handler.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="falha em C:\\clientes\\obra.pdf com senha=segredo: %r",
        args=(HostileValue(),),
        exc_info=None,
    )
    record.operation = HostileValue()
    record.document_id = "conteúdo do PDF"
    record.untrusted = HostileValue()

    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)

    assert "segredo" not in formatted
    assert "clientes" not in formatted
    assert "conteúdo do PDF" not in formatted
    assert "arguments-redacted" in str(payload["event"])
    assert "operation" not in payload
    assert "document_id" not in payload


def test_operation_events_have_levels_correlation_and_safe_traceback() -> None:
    stream = io.StringIO()
    logger = logging.Logger("zeny_project_handler.test", level=logging.DEBUG)
    logger.addHandler(_json_handler(stream))
    observation = operation_logger(
        "pdf.import",
        logger=logger,
        correlation_id=CORRELATION_ID,
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    with observation.context():
        observation.started(item_count=1)
        nested = operation_logger("pdf.inspect", logger=logger, document_id=DOCUMENT_ID)
        nested.succeeded()
        observation.cancelled()
        observation.failed(ValueError("senha=segredo"), expected=True)
        try:
            raise RuntimeError("conteúdo PDF sigiloso; password=segredo; C:\\clientes\\obra.pdf")
        except RuntimeError as error:
            observation.failed(error, expected=False)

    payloads = _payloads(stream)
    assert [item["level"] for item in payloads] == [
        "INFO",
        "INFO",
        "INFO",
        "WARNING",
        "ERROR",
    ]
    assert {item["correlation_id"] for item in payloads} == {CORRELATION_ID}
    assert payloads[0]["status"] == "started"
    assert payloads[1]["operation"] == "pdf.inspect"
    assert payloads[2]["status"] == "cancelled"
    assert "exception" not in payloads[3]
    traceback_text = str(payloads[4]["exception"])
    assert "Traceback (most recent call last)" in traceback_text
    assert "RuntimeError" in traceback_text
    assert Path(__file__).name in traceback_text
    assert str(Path(__file__).resolve().parent) not in traceback_text
    serialized = json.dumps(payloads, ensure_ascii=False)
    assert "segredo" not in serialized
    assert "conteúdo PDF sigiloso" not in serialized
    assert "clientes" not in serialized


def test_configure_logging_is_idempotent_and_can_skip_file_creation(tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    first_logger = configure_logging(settings, write_to_file=False)
    first_handler = first_logger.handlers[0]
    logger = configure_logging(settings, write_to_file=False)

    assert logger is first_logger
    assert logger.name == "zeny_project_handler"
    assert len(logger.handlers) == 1
    assert logger.handlers[0] is not first_handler
    assert not (tmp_path / "logs").exists()


def test_unhandled_exception_hooks_are_idempotent_and_only_log() -> None:
    stream = io.StringIO()
    logger = logging.getLogger("zeny_project_handler")
    previous_handlers = tuple(logger.handlers)
    previous_level = logger.level
    previous_process_hook = sys.excepthook
    previous_thread_hook = threading.excepthook
    logger.handlers = [_json_handler(stream)]
    logger.setLevel(logging.DEBUG)
    try:
        install_unhandled_exception_logging()
        installed_process_hook = sys.excepthook
        installed_thread_hook = threading.excepthook
        install_unhandled_exception_logging()

        assert sys.excepthook is installed_process_hook
        assert threading.excepthook is installed_thread_hook
        try:
            raise RuntimeError("senha=segredo em C:\\clientes\\obra.pdf")
        except RuntimeError:
            error_type, error, traceback_value = sys.exc_info()
            assert error_type is not None
            assert error is not None
            installed_process_hook(error_type, error, traceback_value)
    finally:
        sys.excepthook = previous_process_hook
        threading.excepthook = previous_thread_hook
        logger.handlers = list(previous_handlers)
        logger.setLevel(previous_level)

    payload = _payloads(stream)[0]
    assert payload["level"] == "CRITICAL"
    assert payload["operation"] == "process.unhandled_exception"
    assert payload["status"] == "failed"
    assert "exception" in payload
    assert "segredo" not in stream.getvalue()
    assert "clientes" not in stream.getvalue()
