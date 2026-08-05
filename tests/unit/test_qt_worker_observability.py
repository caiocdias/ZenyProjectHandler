from __future__ import annotations

import json
import logging
from threading import Event
from typing import Never, cast
from uuid import UUID

import pytest

from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.logging_config import JsonFormatter
from zeny_project_handler.ui.project_panel import _PipelineWorker

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")


class CancelledPipeline:
    def executar_pipeline(self, _project_id: UUID, **_kwargs: object) -> Never:
        raise FluxoMvpCanceladoError("Cancelada em ponto seguro")


class BrokenPipeline:
    def executar_pipeline(self, _project_id: UUID, **_kwargs: object) -> Never:
        raise RuntimeError("senha=segredo em C:\\clientes\\obra.pdf")


@pytest.mark.parametrize(
    ("service", "correlation_id", "expected_status", "expected_level", "has_traceback"),
    [
        (
            CancelledPipeline(),
            "11111111111111111111111111111111",
            "cancelled",
            logging.INFO,
            False,
        ),
        (
            BrokenPipeline(),
            "22222222222222222222222222222222",
            "failed",
            logging.ERROR,
            True,
        ),
    ],
)
def test_qt_worker_logs_terminal_state_without_touching_widgets(
    service: object,
    correlation_id: str,
    expected_status: str,
    expected_level: int,
    has_traceback: bool,
    app_log_capture: pytest.LogCaptureFixture,
) -> None:
    worker = _PipelineWorker(
        cast(ServicoFluxoMvp, service),
        PROJECT_ID,
        Event(),
        correlation_id,
    )
    failed: list[tuple[str, bool]] = []
    finished: list[bool] = []
    worker.failed.connect(lambda message, cancelled: failed.append((message, cancelled)))
    worker.finished.connect(lambda: finished.append(True))

    worker.run()

    assert failed
    assert finished == [True]
    records = [
        record
        for record in app_log_capture.records
        if getattr(record, "operation", None) == "qt.worker.analysis_pipeline"
    ]
    assert [getattr(record, "status", None) for record in records] == [
        "started",
        expected_status,
    ]
    assert {getattr(record, "correlation_id", None) for record in records} == {correlation_id}
    terminal = records[-1]
    assert terminal.levelno == expected_level
    assert (terminal.exc_info is not None) is has_traceback
    serialized = json.loads(JsonFormatter().format(terminal))
    assert "segredo" not in json.dumps(serialized, ensure_ascii=False)
    assert "clientes" not in json.dumps(serialized, ensure_ascii=False)
