from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.market_fakes import FakeClassificadorMercado
from zeny_project_handler.adapters.analysis.tesseract_runtime import RuntimeTesseract
from zeny_project_handler.application.compliance_analysis import ExecutarAnaliseConformidade
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.composition import CoreServices
from zeny_project_handler_server import composition as server_composition
from zeny_project_handler_server.composition import JobLifecycle, ServerRuntime
from zeny_project_handler_server.config import ServerSettings


class RecordingCore:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def close(self) -> None:
        self.events.append("engine-disposed")


class RecordingJobs:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def stop_accepting(self) -> None:
        self.events.append("jobs-stopped")

    def cancel_and_wait(self) -> None:
        self.events.append("jobs-cancelled-and-waited")


def test_server_shutdown_orders_jobs_before_engine_and_is_idempotent() -> None:
    events: list[str] = []
    runtime = ServerRuntime(
        core=cast(CoreServices, RecordingCore(events)),
        ocr=RuntimeTesseract(executavel=None, diretorio_tessdata=None),
        jobs=cast(JobLifecycle, RecordingJobs(events)),
    )

    runtime.close()
    runtime.close()

    assert events == ["jobs-stopped", "jobs-cancelled-and-waited", "engine-disposed"]


def test_server_reports_the_independent_distribution_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested: list[str] = []

    def fake_version(distribution: str) -> str:
        requested.append(distribution)
        return "0.1.0"

    monkeypatch.setattr(server_composition, "version", fake_version)

    assert server_composition._server_version() == "0.1.0"
    assert requested == ["zeny-project-handler-server"]


def test_server_composes_one_market_backed_analyzer_for_pipeline_and_reanalysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[ExecutarAnaliseConformidade] = []
    original = server_composition._compose_analysis_workflow

    def record_analyzer(
        core: CoreServices,
        settings: ServerSettings,
        ocr: RuntimeTesseract,
        compliance: ExecutarAnaliseConformidade,
    ) -> ServicoFluxoMvp:
        captured.append(compliance)
        return original(core, settings, ocr, compliance)

    monkeypatch.setattr(server_composition, "_compose_analysis_workflow", record_analyzer)
    classifier = FakeClassificadorMercado()
    settings = ServerSettings(
        password="senha de composição do mercado",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
    )
    runtime = server_composition.compose_server_runtime(
        settings,
        market_classifier=classifier,
    )
    try:
        assert runtime.compliance_api is not None
        assert captured == [runtime.compliance_api.analysis_service]
        assert captured[0]._market_classifier is classifier
    finally:
        runtime.close()
