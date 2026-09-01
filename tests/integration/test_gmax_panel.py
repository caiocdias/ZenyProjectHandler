from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QMessageBox, QTableWidget, QWidget
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui.documentation_gateway import (
    DocumentationGateway,
    DocumentationGatewayError,
)
from zeny_project_handler_client.ui.documentation_panel import DocumentationPanelWidget
from zeny_project_handler_client.ui.gmax_panel import GmaxPanelWidget
from zeny_project_handler_contracts.base import ComplianceExecutionId, ProjectId
from zeny_project_handler_contracts.enums import JobStatus
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.gmax import (
    GmaxCheckDto,
    GmaxCheckType,
    GmaxHeaderState,
    GmaxMarket,
    GmaxQueryState,
    GmaxSnapshotState,
    GmaxSummaryResponse,
)

pytestmark = pytest.mark.integration


class _GmaxGatewayStub:
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.calls: list[UUID] = []
        self.unexpected_calls: list[str] = []

    def get_gmax(self, project_id: UUID) -> GmaxSummaryResponse:
        self.calls.append(project_id)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, GmaxSummaryResponse)
        return response

    def __getattr__(self, name: str) -> object:
        self.unexpected_calls.append(name)
        raise AssertionError(f"Operação inesperada no gateway GMAX: {name}")


class _ViewerStub(QWidget):
    compliance_callout_selected = Signal(str)

    def definir_callouts_conformidade(self, _callouts: object) -> None:
        pass

    def ir_para_folha(self, _page_number: int) -> None:
        pass

    def definir_destaque_navegacao(self, _navigation: object) -> None:
        pass

    def selecionar_callout(self, _callout_id: str) -> None:
        pass


class _TerminalDocumentationGatewayStub:
    def __init__(self, status: JobStatus) -> None:
        self.status = status
        self.result_calls: list[UUID] = []

    def get_active_registry(self) -> object:
        raise DocumentationGatewayError(ErrorCode.INTERNAL_ERROR, "Registro indisponível")

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> object:
        del limit, offset
        raise DocumentationGatewayError(ErrorCode.INTERNAL_ERROR, "Projetos indisponíveis")

    def get_job(self, _job_id: UUID) -> object:
        return SimpleNamespace(
            status=self.status,
            message="Conformidade concluída" if self.status is JobStatus.SUCCEEDED else "Falhou",
            progress_percent=100,
            error=None,
        )

    def get_job_result(self, job_id: UUID) -> object:
        self.result_calls.append(job_id)
        return object()


def _check(
    check_type: GmaxCheckType,
    *,
    detected: bool,
    query_state: GmaxQueryState,
    row_found: bool | None,
) -> GmaxCheckDto:
    return GmaxCheckDto(
        check_type=check_type,
        label=(
            "Impacto ambiental" if check_type is GmaxCheckType.IMPACTO_AMBIENTAL else "Servidão"
        ),
        detected_in_pdf=detected,
        action=(
            "AVALIAR IMPACTO AMBIENTAL"
            if check_type is GmaxCheckType.IMPACTO_AMBIENTAL
            else "FALTA SERVIDÃO"
        ),
        query_state=query_state,
        row_found=row_found,
    )


def _summary(
    project_id: UUID,
    snapshot_state: GmaxSnapshotState,
    *,
    header_notes: tuple[str, ...] = ("0000001234",),
    market: GmaxMarket | None = None,
    query_states: tuple[GmaxQueryState, GmaxQueryState] = (
        GmaxQueryState.NOT_EXECUTED,
        GmaxQueryState.NOT_EXECUTED,
    ),
    rows: tuple[bool | None, bool | None] = (None, None),
    detected: tuple[bool, bool] = (True, False),
) -> GmaxSummaryResponse:
    has_execution = snapshot_state is not GmaxSnapshotState.NEVER_EXECUTED
    header_state = (
        GmaxHeaderState.NOT_FOUND
        if not header_notes
        else GmaxHeaderState.MISMATCH
        if any(note != "0000001234" for note in header_notes)
        else GmaxHeaderState.MATCH
    )
    return GmaxSummaryResponse(
        project_id=ProjectId(project_id),
        project_service_note="0000001234",
        header_service_notes=header_notes,
        header_state=header_state,
        blocking_reason=(
            "A NS 9999999999 do cabeçalho diverge da NS 0000001234 do projeto."
            if snapshot_state is GmaxSnapshotState.BLOCKED_NS_MISMATCH
            else None
        ),
        snapshot_state=snapshot_state,
        last_execution_id=ComplianceExecutionId(uuid4()) if has_execution else None,
        last_executed_at=datetime(2026, 9, 1, 15, 30, tzinfo=UTC) if has_execution else None,
        is_stale=snapshot_state in {GmaxSnapshotState.STALE, GmaxSnapshotState.BLOCKED_NS_MISMATCH},
        market=market,
        checks=(
            _check(
                GmaxCheckType.IMPACTO_AMBIENTAL,
                detected=detected[0],
                query_state=query_states[0],
                row_found=rows[0],
            ),
            _check(
                GmaxCheckType.SERVIDAO,
                detected=detected[1],
                query_state=query_states[1],
                row_found=rows[1],
            ),
        ),
    )


def _table_text(table: QTableWidget, row: int, column: int) -> str:
    item = table.item(row, column)
    assert item is not None
    return item.text()


def test_gmax_panel_is_read_only_accessible_and_maps_current_select_results(
    qtbot: QtBot,
) -> None:
    project_id = uuid4()
    gateway = _GmaxGatewayStub(
        _summary(
            project_id,
            GmaxSnapshotState.CURRENT,
            market=GmaxMarket.RURAL,
            query_states=(GmaxQueryState.EXECUTED, GmaxQueryState.EXECUTED),
            rows=(False, True),
            detected=(True, True),
        )
    )
    panel = GmaxPanelWidget(gateway=cast(DocumentationGateway, gateway))
    qtbot.addWidget(panel)

    state = panel.findChild(QLabel, "gmaxStateLabel")
    market = panel.findChild(QLabel, "gmaxMarketLabel")
    table = panel.findChild(QTableWidget, "gmaxChecksTable")
    assert state is not None and market is not None and table is not None
    assert "Nenhum projeto ativo" in state.text()

    panel.abrir_projeto(project_id)

    assert gateway.calls == [project_id]
    assert gateway.unexpected_calls == []
    assert panel.projeto_ativo_id == project_id
    assert "Resultado atual" in state.text()
    assert market.text() == "Rural"
    assert table.rowCount() == 2
    assert [_table_text(table, row, 0) for row in range(2)] == [
        "Impacto ambiental",
        "Servidão",
    ]
    assert [_table_text(table, row, 1) for row in range(2)] == ["Detectado", "Detectado"]
    assert [_table_text(table, row, 2) for row in range(2)] == [
        "AVALIAR IMPACTO AMBIENTAL",
        "FALTA SERVIDÃO",
    ]
    assert [_table_text(table, row, 3) for row in range(2)] == ["Executado", "Executado"]
    assert [_table_text(table, row, 4) for row in range(2)] == [
        "Sem linha",
        "Linha encontrada",
    ]
    assert table.editTriggers() is QTableWidget.EditTrigger.NoEditTriggers
    assert table.accessibleName()
    assert state.accessibleName()


@pytest.mark.parametrize(
    ("summary", "state_fragment", "market_fragment", "query_fragment"),
    (
        (
            lambda project_id: _summary(
                project_id,
                GmaxSnapshotState.NEVER_EXECUTED,
                header_notes=(),
            ),
            "ainda não executada",
            "ainda não executada",
            "Não executado",
        ),
        (
            lambda project_id: _summary(
                project_id,
                GmaxSnapshotState.STALE,
                market=GmaxMarket.URBANO,
                query_states=(
                    GmaxQueryState.EXECUTED,
                    GmaxQueryState.NOT_EXECUTED_NO_TRIGGER,
                ),
                rows=(False, None),
            ),
            "Resultado desatualizado",
            "última execução",
            "última execução desatualizada",
        ),
        (
            lambda project_id: _summary(
                project_id,
                GmaxSnapshotState.BLOCKED_NS_MISMATCH,
                header_notes=("0000001234", "9999999999"),
            ),
            "Consultas bloqueadas por divergência da NS",
            "Não exibido",
            "Não executado",
        ),
    ),
)
def test_gmax_panel_distinguishes_non_current_states_without_color(
    qtbot: QtBot,
    summary: object,
    state_fragment: str,
    market_fragment: str,
    query_fragment: str,
) -> None:
    project_id = uuid4()
    response = summary(project_id)  # type: ignore[operator]
    gateway = _GmaxGatewayStub(response)
    panel = GmaxPanelWidget(gateway=cast(DocumentationGateway, gateway))
    qtbot.addWidget(panel)

    panel.abrir_projeto(project_id)

    state = panel.findChild(QLabel, "gmaxStateLabel")
    market = panel.findChild(QLabel, "gmaxMarketLabel")
    table = panel.findChild(QTableWidget, "gmaxChecksTable")
    assert state is not None and market is not None and table is not None
    assert state_fragment in state.text()
    assert market_fragment in market.text()
    assert query_fragment in _table_text(table, 0, 3)
    if isinstance(response, GmaxSummaryResponse) and (
        response.snapshot_state is GmaxSnapshotState.BLOCKED_NS_MISMATCH
    ):
        assert "Corrija o projeto ou os PDFs e reanalise" in state.text()
        assert "Rural" not in market.text() and "Urbano" not in market.text()
        assert "Linha encontrada" not in _table_text(table, 0, 4)
        assert "Sem linha" not in _table_text(table, 0, 4)


def test_gmax_panel_refreshes_only_the_active_project_and_clears_on_error(qtbot: QtBot) -> None:
    project_id = uuid4()
    error = DocumentationGatewayError(
        ErrorCode.INTERNAL_ERROR,
        "Resumo indisponível",
        correlation_id="corr-gmax-1",
    )
    gateway = _GmaxGatewayStub(
        _summary(
            project_id,
            GmaxSnapshotState.CURRENT,
            market=GmaxMarket.RURAL,
            query_states=(GmaxQueryState.EXECUTED, GmaxQueryState.EXECUTED),
            rows=(True, True),
        ),
        error,
    )
    panel = GmaxPanelWidget(gateway=cast(DocumentationGateway, gateway))
    qtbot.addWidget(panel)
    statuses: list[str] = []
    panel.status_changed.connect(statuses.append)
    panel.abrir_projeto(project_id)

    panel.atualizar_apos_conformidade(uuid4(), JobStatus.SUCCEEDED)
    assert gateway.calls == [project_id]
    panel.atualizar_apos_conformidade(project_id, JobStatus.FAILED)

    market = panel.findChild(QLabel, "gmaxMarketLabel")
    table = panel.findChild(QTableWidget, "gmaxChecksTable")
    assert market is not None and table is not None
    assert gateway.calls == [project_id, project_id]
    assert market.text() == "Indisponível — falha ao carregar o resumo"
    assert "Linha encontrada" not in _table_text(table, 0, 4)
    assert statuses == ["Resumo indisponível (correlação corr-gmax-1)"]

    panel.limpar()
    assert panel.projeto_ativo_id is None
    assert not market.text().startswith("Rural")


@pytest.mark.parametrize("terminal_status", (JobStatus.SUCCEEDED, JobStatus.FAILED))
def test_documentation_panel_emits_project_and_terminal_status_for_gmax_refresh(
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: JobStatus,
) -> None:
    gateway = _TerminalDocumentationGatewayStub(terminal_status)
    viewer = _ViewerStub()
    qtbot.addWidget(viewer)
    panel = DocumentationPanelWidget(
        gateway=cast(DocumentationGateway, gateway),
        viewer=viewer,  # type: ignore[arg-type]
    )
    qtbot.addWidget(panel)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args, **_kwargs: None)
    project_id = uuid4()
    job_id = uuid4()
    events: list[tuple[object, object]] = []
    panel.compliance_finished.connect(lambda project, status: events.append((project, status)))
    panel._compliance_job_id = job_id
    panel._compliance_project_id = project_id

    panel._poll_compliance_job()

    assert events == [(project_id, terminal_status)]
    assert panel._compliance_job_id is None
    assert panel._compliance_project_id is None
    assert gateway.result_calls == ([job_id] if terminal_status is JobStatus.SUCCEEDED else [])
