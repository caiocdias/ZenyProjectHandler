from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, get_ident
from typing import cast
from uuid import UUID

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressBar, QPushButton
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory

import zeny_project_handler.ui.main_window as main_window_module
from zeny_project_handler.application.errors import (
    PortabilidadeCanceladaError,
    PortabilidadeProjetoError,
)
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.project_portability import (
    CancelCallback,
    PlanoImportacaoProjeto,
    ProgressCallback,
    ResultadoExportacaoProjeto,
    ResumoPreflightImportacaoProjeto,
    ResumoProjetoPortabilidade,
    ServicoPortabilidadeProjeto,
)
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.portability import (
    EstadoIntegridadePacote,
    ManifestoProjetoPortatil,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.ui.portability_panel import PortabilityPanelWidget
from zeny_project_handler.ui.portability_worker import (
    PortabilityCommand,
    PortabilityOperation,
    PortabilityWorker,
)

pytestmark = pytest.mark.integration

PROJECT_ID = UUID("10000000-0000-0000-0000-000000000007")


@dataclass(slots=True)
class ControlledRun:
    progress: tuple[tuple[int, int, str], ...] = (
        (2, 4, "metade"),
        (1, 4, "atrasado"),
        (3, 4, "quase"),
    )
    failure: Exception | None = None
    entered: Event = field(default_factory=Event)
    release: Event = field(default_factory=Event)
    cancellation_seen: Event = field(default_factory=Event)


class ControlledPortabilityService:
    def __init__(self, coordinator: CoordenadorOperacoes, *runs: ControlledRun) -> None:
        self.coordenador = coordinator
        self.runs = list(runs)
        self.calls = 0
        self.worker_thread_ids: list[int] = []
        self.cancel_callback: CancelCallback | None = None

    def listar_projetos(self) -> tuple[ResumoProjetoPortabilidade, ...]:
        return (ResumoProjetoPortabilidade(projeto_id=PROJECT_ID, nome="Projeto controlado"),)

    def exportar_projeto(
        self,
        projeto_id: UUID,
        destino: Path,
        *,
        progresso: ProgressCallback | None = None,
        cancelado: CancelCallback | None = None,
    ) -> ResultadoExportacaoProjeto:
        run = self.runs[self.calls]
        self.calls += 1
        self.worker_thread_ids.append(get_ident())
        self.cancel_callback = cancelado
        with self.coordenador.adquirir(TipoOperacao.EXPORTACAO_PROJETO):
            for current, total, message in run.progress:
                if progresso is not None:
                    progresso(current, total, message)
            run.entered.set()
            if not run.release.wait(timeout=5):
                raise RuntimeError("Teste não liberou o serviço controlado")
            if cancelado is not None and cancelado():
                run.cancellation_seen.set()
                raise PortabilidadeCanceladaError("Exportação cancelada em ponto seguro")
            if run.failure is not None:
                raise run.failure
            return _export_result(projeto_id, destino)


class ControlledImportService:
    def __init__(self, coordinator: CoordenadorOperacoes, plan: PlanoImportacaoProjeto) -> None:
        self.coordenador = coordinator
        self.plan = plan
        self.events: list[str] = []

    def listar_projetos(self) -> tuple[ResumoProjetoPortabilidade, ...]:
        return ()

    def preflight_importacao(
        self,
        _package: Path,
        *,
        cancelado: CancelCallback | None = None,
    ) -> PlanoImportacaoProjeto:
        assert cancelado is not None and not cancelado()
        self.events.append("preflight")
        return self.plan

    def aplicar_plano_importacao(
        self,
        plan: PlanoImportacaoProjeto,
        *,
        confirmar_substituicao: bool = False,
        progresso: ProgressCallback | None = None,
        cancelado: CancelCallback | None = None,
    ) -> object:
        assert plan is self.plan
        assert confirmar_substituicao
        assert progresso is not None
        assert cancelado is not None and not cancelado()
        self.events.append("apply")
        return object()


def _conflicting_import_plan(path: Path) -> PlanoImportacaoProjeto:
    summary = ResumoPreflightImportacaoProjeto(
        projeto_id=PROJECT_ID,
        catalogo_id=PROJECT_ID,
        nome="Projeto controlado",
        quantidade_documentos=1,
        quantidade_fotos=2,
        quantidade_analises=3,
        quantidade_arquivos=4,
        quantidade_omissoes=0,
    )
    return PlanoImportacaoProjeto(
        pacote=path,
        pacote_sha256="a" * 64,
        pacote_tamanho_bytes=100,
        estado_alvo_sha256="b" * 64,
        projeto_existente=True,
        pasta_destino_existente=True,
        resumo=summary,
        integridade_pacote=RelatorioIntegridadeProjeto(),
        omissoes_origem=(),
        fingerprint="c" * 64,
    )


def _export_result(project_id: UUID, destination: Path) -> ResultadoExportacaoProjeto:
    manifest = ManifestoProjetoPortatil(
        versao_formato=2,
        projeto_id=project_id,
        catalogo_id=project_id,
        nome_projeto="Projeto controlado",
        criado_em=datetime.now(UTC),
        arquivos=(),
        estado_integridade=EstadoIntegridadePacote.INTEGRO,
    )
    return ResultadoExportacaoProjeto(
        caminho=destination,
        manifesto=manifest,
        integridade_origem=RelatorioIntegridadeProjeto(),
    )


def _panel(
    qtbot: QtBot,
    service: ControlledPortabilityService,
) -> PortabilityPanelWidget:
    panel = PortabilityPanelWidget(
        service=cast(ServicoPortabilidadeProjeto, service),
        coordinator=service.coordenador,
    )
    qtbot.addWidget(panel)
    panel.show()
    project_combo = panel._project
    project_combo.setCurrentIndex(project_combo.findData(str(PROJECT_ID)))
    return panel


def _export_button(panel: PortabilityPanelWidget) -> QPushButton:
    button = panel.findChild(QPushButton, "portabilityExportButton")
    assert button is not None
    return button


def _start_export(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    panel: PortabilityPanelWidget,
    destination: Path,
) -> None:
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Projeto Zeny (*.zphproj)"),
    )
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        _export_button(panel), Qt.MouseButton.LeftButton
    )


@pytest.mark.parametrize("accepted", [False, True])
def test_import_worker_confirms_preflight_plan_before_applying(
    tmp_path: Path,
    accepted: bool,
) -> None:
    package = tmp_path / "controlled.zphproj"
    plan = _conflicting_import_plan(package)
    service = ControlledImportService(CoordenadorOperacoes(), plan)
    worker = PortabilityWorker(
        cast(ServicoPortabilidadeProjeto, service),
        PortabilityCommand(PortabilityOperation.IMPORT, package),
        Event(),
        "a" * 32,
    )
    confirmations: list[tuple[str, object, tuple[str, ...]]] = []
    failures: list[tuple[str, bool]] = []
    successes: list[object] = []

    def confirm(_execution_id: str, kind: str, payload: object) -> None:
        confirmations.append((kind, payload, tuple(service.events)))
        worker.resolve_confirmation(accepted)

    worker.confirmation_required.connect(confirm)
    worker.failed.connect(
        lambda _execution_id, message, cancelled: failures.append((message, cancelled))
    )
    worker.succeeded.connect(lambda _execution_id, result: successes.append(result))

    worker.run()

    assert confirmations == [("replace_project", plan, ("preflight",))]
    if accepted:
        assert service.events == ["preflight", "apply"]
        assert len(successes) == 1
        assert failures == []
    else:
        assert service.events == ["preflight"]
        assert successes == []
        assert failures == [("Importação cancelada antes da substituição", True)]


def test_import_panel_shows_plan_summary_and_refusal_never_applies(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "panel-controlled.zphproj"
    plan = _conflicting_import_plan(package)
    service = ControlledImportService(CoordenadorOperacoes(), plan)
    panel = PortabilityPanelWidget(
        service=cast(ServicoPortabilidadeProjeto, service),
        coordinator=service.coordenador,
    )
    qtbot.addWidget(panel)
    panel.show()
    questions: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *_args, **_kwargs: (str(package), "Projeto Zeny (*.zphproj)"),
    )

    def refuse(_parent: object, title: str, message: str, *_args: object) -> object:
        questions.append((title, message))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", refuse)

    qtbot.mouseClick(panel._import, Qt.MouseButton.LeftButton)  # type: ignore[no-untyped-call]
    qtbot.waitUntil(lambda: not panel.processando)

    assert service.events == ["preflight"]
    assert len(questions) == 1
    title, message = questions[0]
    assert title == "Substituir projeto existente"
    assert "Projeto controlado" in message
    assert str(PROJECT_ID)[:8] in message
    assert plan.fingerprint[:12] in message


def test_worker_keeps_gui_responsive_and_reports_monotonic_success_once(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun()
    coordinator = CoordenadorOperacoes()
    service = ControlledPortabilityService(coordinator, run)
    panel = _panel(qtbot, service)
    busy: list[bool] = []
    statuses: list[str] = []
    panel.busy_changed.connect(busy.append)
    panel.status_changed.connect(statuses.append)
    main_thread_id = get_ident()

    _start_export(qtbot, monkeypatch, panel, tmp_path / "responsive.zphproj")
    qtbot.waitUntil(run.entered.is_set)

    gui_tick = Event()
    QTimer.singleShot(0, gui_tick.set)
    qtbot.waitUntil(gui_tick.is_set)
    progress = panel.findChild(QProgressBar, "portabilityProgress")
    assert progress is not None
    qtbot.waitUntil(lambda: progress.value() == 3)
    assert progress.maximum() == 4
    assert len(service.worker_thread_ids) == 1
    assert service.worker_thread_ids[0] != main_thread_id
    assert not _export_button(panel).isEnabled()
    assert panel._cancel.isEnabled()

    panel.exportar_projeto()
    assert service.calls == 1
    stale_id = "f" * 32
    panel._show_progress(stale_id, 4, 4, "resultado obsoleto")
    assert progress.value() == 3
    assert panel.processando

    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)

    assert busy == [True, False]
    assert coordinator.operacao_em_andamento is None
    assert _export_button(panel).isEnabled()
    assert not panel._cancel.isEnabled()
    assert any(message.startswith("Projeto exportado para") for message in statuses)


def test_worker_failure_restores_controls_and_coordinator_exactly_once(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun(failure=PortabilidadeProjetoError("falha controlada"))
    coordinator = CoordenadorOperacoes()
    states: list[TipoOperacao | None] = []
    coordinator.observar(states.append)
    service = ControlledPortabilityService(coordinator, run)
    panel = _panel(qtbot, service)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    _start_export(qtbot, monkeypatch, panel, tmp_path / "failure.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)

    assert warnings == ["falha controlada"]
    assert states == [None, TipoOperacao.EXPORTACAO_PROJETO, None]
    assert coordinator.operacao_em_andamento is None
    assert _export_button(panel).isEnabled()


def test_worker_cancellation_is_cooperative_and_has_no_error_dialog(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = ControlledRun()
    coordinator = CoordenadorOperacoes()
    service = ControlledPortabilityService(coordinator, run)
    panel = _panel(qtbot, service)
    warnings: list[str] = []
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    _start_export(qtbot, monkeypatch, panel, tmp_path / "cancel.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        panel._cancel, Qt.MouseButton.LeftButton
    )
    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)

    assert run.cancellation_seen.is_set()
    assert warnings == []
    assert coordinator.operacao_em_andamento is None
    assert "Exportação cancelada em ponto seguro" in statuses


def test_window_disables_incompatible_panels_and_close_wait_is_bounded(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _application, window = application_factory(
        [], settings=AppSettings(data_directory=tmp_path / "window")
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.portability_panel
    assert panel is not None
    project_panel = window.project_panel
    review_panel = window.review_panel
    documentation_panel = window.documentation_panel
    assert project_panel is not None
    assert review_panel is not None
    assert documentation_panel is not None
    coordinator = panel._coordinator
    run = ControlledRun()
    service = ControlledPortabilityService(coordinator, run)
    panel._service = cast(ServicoPortabilidadeProjeto, service)
    panel.atualizar_projetos()
    panel._project.setCurrentIndex(panel._project.findData(str(PROJECT_ID)))
    information: list[str] = []
    monkeypatch.setattr(main_window_module, "_CLOSE_WAIT_MS", 20)
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda _parent, _title, message: information.append(str(message)),
    )

    _start_export(qtbot, monkeypatch, panel, tmp_path / "window.zphproj")
    qtbot.waitUntil(run.entered.is_set)
    qtbot.waitUntil(lambda: not project_panel.isEnabled())

    assert not review_panel.isEnabled()
    assert not documentation_panel.isEnabled()
    assert panel._cancel.isEnabled()
    panel.exportar_projeto()
    assert service.calls == 1

    assert not window.close()
    assert information
    assert service.cancel_callback is not None and service.cancel_callback()
    assert panel._thread is not None and panel._thread.isRunning()

    run.release.set()
    qtbot.waitUntil(lambda: not panel.processando)
    assert project_panel.isEnabled()
    assert review_panel.isEnabled()
    assert documentation_panel.isEnabled()
    assert window.close()
