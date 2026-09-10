from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QDockWidget
from pytestqt.qtbot import QtBot
from tests.integration.test_project_http_gateway import (
    PASSWORD,
    _http_window,
    _running_server,
    _wait_job,
)
from tests.market_fakes import FakeClassificadorMercado
from tests.pdf_fixtures import create_analysis_pdf

from zeny_project_handler_client.ui.project_gateway import HttpProjectGateway, ProjectGatewayError
from zeny_project_handler_client.ui.theme import Tema, aplicar_tema
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.projects import UpdateProjectMarketRequest
from zeny_project_handler_server.app import create_app
from zeny_project_handler_server.composition import compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("theme", [Tema.CLARO, Tema.ESCURO])
def test_http_market_snapshot_conflict_reanalysis_and_restart(
    qtbot: QtBot, tmp_path: Path, theme: Tema
) -> None:
    application = cast(QApplication, QApplication.instance())
    capture_dir = os.environ.get("ZENY_E04_CAPTURE_DIR")
    if capture_dir:
        assert (
            QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts/segoeui.ttf"))
            >= 0
        )
    settings = ServerSettings(
        password=PASSWORD,
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server",
    )
    classifier = FakeClassificadorMercado()
    runtime = compose_server_runtime(settings, market_classifier=classifier)
    with _running_server(create_app(settings, runtime_factory=lambda _settings: runtime)) as url:
        gateway = HttpProjectGateway(url, PASSWORD)
        project = gateway.create_project("0001234567", idempotency_key="e04-project").project
        project_id = project.project_id.root
        assert gateway.get_market(project_id).classification is None
        assert classifier.consultas == []
        gateway.upload_document(
            project_id, create_analysis_pdf(tmp_path / "network.pdf"), idempotency_key="e04-pdf"
        )
        project = gateway.get_project(project_id).project
        accepted = gateway.create_analysis_job(
            project_id,
            expected_project_version=project.project_version,
            force_reanalysis=False,
            idempotency_key="e04-analysis",
        )
        _wait_job(gateway, accepted.job_id.root, JobStatus.SUCCEEDED)
        with _http_window(url, tmp_path / "client", qtbot) as window:
            aplicar_tema(application, theme)
            panel, gmax, documentation = (
                window.project_panel,
                window.gmax_panel,
                window.documentation_panel,
            )
            assert panel is not None and gmax is not None and documentation is not None
            panel._select_and_activate(gateway.get_project(project_id).project)
            qtbot.waitUntil(panel.market.choice.isEnabled)
            if gateway.get_market(project_id).classification is None:
                documentation._analyze_current_compliance()
                qtbot.waitUntil(lambda: documentation._compliance_job_id is None, timeout=30_000)
                qtbot.waitUntil(panel.market.choice.isEnabled)
            assert panel.market.choice.currentData() == "URBANO"
            qtbot.waitUntil(lambda: gmax._summary is not None)
            snapshot = gmax._summary
            assert snapshot is not None and snapshot.classification is not None
            initial_queries = tuple(classifier.consultas)
            for choice in ("RURAL", "URBANO", "AMBOS"):
                panel.market.choice.setCurrentIndex(panel.market.choice.findData(choice))
                panel.market.save.click()
                qtbot.waitUntil(lambda: not panel.market.saving)
                qtbot.waitUntil(lambda: gmax._summary is not None and gmax._summary.is_stale)
                qtbot.waitUntil(lambda: "desatualizado" in documentation._execution_status.text())
                assert panel._session is not None
                assert (
                    panel._session.project_version == gateway.get_market(project_id).project_version
                )
                assert choice.title() in gmax._current_market.text()
                assert gmax._summary is not None
                assert gmax._summary.classification == snapshot.classification
                assert "Banco inicial: Urbano" in gmax._market.text()
                assert "Origem: banco" in gmax._market.text()
            assert tuple(classifier.consultas) == initial_queries
            assert documentation._compliance_job_id is None
            assert not panel.processando
            if capture_dir:
                window.resize(1600, 1100)
                dock = window.findChild(QDockWidget, "gmaxDock")
                assert dock is not None
                dock.raise_()
                QApplication.processEvents()
                path = Path(capture_dir)
                path.mkdir(parents=True, exist_ok=True)
                assert window.grab().save(str(path / f"{theme.value}-janela-stale.png"))
            # Dois clientes: o segundo muda a versão; o primeiro não sobrescreve nem repete PUT.
            remote = gateway.get_market(project_id)
            gateway.update_market(
                project_id,
                UpdateProjectMarketRequest(
                    effective_market="RURAL", expected_project_version=remote.project_version
                ),
            )
            panel.market.choice.setCurrentIndex(1)
            panel.market.save.click()
            qtbot.waitUntil(lambda: not panel.market.saving)
            assert "Conflito" in panel.market.status.text()
            assert "salvo" not in panel.market.status.text()
            panel.market.refresh.click()
            qtbot.waitUntil(panel.market.choice.isEnabled)
            assert panel.market.choice.currentData() == "RURAL"
            panel.market.choice.setCurrentIndex(2)
            panel.market.save.click()
            qtbot.waitUntil(lambda: not panel.market.saving)
            window.set_connection_available(False, "Teste de desconexão")
            assert not panel.market.choice.isEnabled()
            window.set_connection_available(True, "Teste de reconexão")
            qtbot.waitUntil(panel.market.choice.isEnabled)
            assert panel.market.choice.currentData() == "AMBOS"
            documentation._analyze_current_compliance()
            qtbot.waitUntil(lambda: documentation._compliance_job_id is None, timeout=30_000)
            qtbot.waitUntil(
                lambda: (
                    panel.market.choice.isEnabled()
                    and gmax._summary is not None
                    and not gmax._summary.is_stale
                    and "Resultado atual" in documentation._execution_status.text()
                )
            )
            assert "Ambos" in gmax._market.text()
            assert "Origem: técnico" in gmax._market.text()
            assert "Resultado atual" in documentation._execution_status.text()
            assert tuple(classifier.consultas) == initial_queries
            assert panel._session is not None
            assert (
                panel._session.project_version
                == gateway.get_project(project_id).project.project_version
            )
    with (
        _running_server(create_app(settings)) as url,
        _http_window(url, tmp_path / "client", qtbot) as reopened,
    ):
        assert reopened.project_panel is not None
        market = reopened.project_panel.market
        qtbot.waitUntil(market.choice.isEnabled)
        assert market.choice.currentData() == "AMBOS"
        assert "Banco inicial: Urbano" in market.provenance.text()
    aplicar_tema(application, Tema.CLARO)


def test_market_put_is_never_retried_on_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[str] = []

    def unavailable(
        _self: HttpProjectGateway,
        method: str,
        _path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes | Iterable[bytes] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        attempts.append(method)
        raise TimeoutError

    monkeypatch.setattr(HttpProjectGateway, "_request_once", unavailable)
    gateway = HttpProjectGateway("http://127.0.0.1:1", PASSWORD)
    with pytest.raises(ProjectGatewayError) as error:
        gateway.update_market(
            UUID(int=1),
            UpdateProjectMarketRequest(effective_market="AMBOS", expected_project_version=8),
        )
    assert error.value.code is ErrorCode.INTERNAL_ERROR
    assert attempts == ["PUT"]
