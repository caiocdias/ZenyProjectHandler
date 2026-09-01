"""Painel GMAX somente leitura alimentado pelo DTO remoto dedicado."""

from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler_contracts.gmax import (
    GmaxCheckDto,
    GmaxHeaderState,
    GmaxMarket,
    GmaxQueryState,
    GmaxSnapshotState,
    GmaxSummaryResponse,
)

from .documentation_gateway import DocumentationGateway, DocumentationGatewayError

_CHECK_LABELS = ("Impacto ambiental", "Servidão")
_QUERY_LABELS = {
    GmaxQueryState.NOT_EXECUTED: "Não executado",
    GmaxQueryState.NOT_EXECUTED_NO_TRIGGER: "Não executado — gatilho ausente",
    GmaxQueryState.NOT_EXECUTED_NO_SERVICE_CODES: ("Não executado — sem códigos de serviço"),
    GmaxQueryState.EXECUTED: "Executado",
}


class GmaxPanelWidget(QWidget):
    """Apresente a projeção GMAX sem inferir fatos nem iniciar conformidade."""

    status_changed = Signal(str)

    def __init__(
        self,
        *,
        gateway: DocumentationGateway,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("gmaxPanel")
        self.setAccessibleName("Painel GMAX")
        self._gateway = gateway
        self._project_id: UUID | None = None
        self._summary: GmaxSummaryResponse | None = None
        self._build_ui()
        self.limpar()

    @property
    def projeto_ativo_id(self) -> UUID | None:
        return self._project_id

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        actions = QHBoxLayout()
        title = QLabel("Resumo GMAX")
        title.setObjectName("gmaxTitleLabel")
        title.setProperty("role", "summary")
        actions.addWidget(title, 1)
        self._refresh = QPushButton("Atualizar")
        self._refresh.setObjectName("gmaxRefreshButton")
        self._refresh.setAccessibleName("Atualizar resumo GMAX")
        self._refresh.clicked.connect(self.atualizar)
        actions.addWidget(self._refresh)
        layout.addLayout(actions)

        self._state = QLabel()
        self._state.setObjectName("gmaxStateLabel")
        self._state.setProperty("role", "summary")
        self._state.setWordWrap(True)
        self._state.setAccessibleName("Estado do resumo GMAX")
        layout.addWidget(self._state)

        summary_group = QGroupBox("NS, cabeçalho e execução")
        summary_group.setObjectName("gmaxSummaryGroup")
        summary_layout = QVBoxLayout(summary_group)
        self._project_service_note = self._summary_label(
            "gmaxProjectServiceNoteLabel",
            "NS do projeto",
        )
        summary_layout.addWidget(self._project_service_note)
        self._header_service_notes = self._summary_label(
            "gmaxHeaderServiceNotesLabel",
            "NS identificadas nos cabeçalhos dos PDFs",
        )
        summary_layout.addWidget(self._header_service_notes)
        self._execution = self._summary_label(
            "gmaxExecutionLabel",
            "Última execução de conformidade",
        )
        summary_layout.addWidget(self._execution)
        layout.addWidget(summary_group)

        market_group = QGroupBox("Mercado")
        market_group.setObjectName("gmaxMarketGroup")
        market_layout = QVBoxLayout(market_group)
        self._market = QLabel()
        self._market.setObjectName("gmaxMarketLabel")
        self._market.setProperty("role", "summary")
        self._market.setWordWrap(True)
        self._market.setAccessibleName("Mercado da Nota de Serviço")
        market_layout.addWidget(self._market)
        layout.addWidget(market_group)

        self._checks = QTableWidget(2, 5)
        self._checks.setObjectName("gmaxChecksTable")
        self._checks.setAccessibleName("Verificações GMAX de impacto ambiental e servidão")
        self._checks.setAccessibleDescription(
            "Tabela somente leitura com detecção no PDF, ação, execução da consulta e resultado."
        )
        self._checks.setHorizontalHeaderLabels(
            ("Verificação", "PDF", "Ação", "Consulta", "Resultado do SELECT")
        )
        self._checks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._checks.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._checks.setAlternatingRowColors(True)
        self._checks.verticalHeader().setVisible(False)
        header = self._checks.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(False)
        layout.addWidget(self._checks, 1)

        note = QLabel(
            "Este painel apenas lê o último resumo persistido. Atualizar não executa "
            "conformidade nem consulta o SQL Server."
        )
        note.setObjectName("gmaxReadOnlyNotice")
        note.setProperty("role", "hint")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _summary_label(self, object_name: str, accessible_name: str) -> QLabel:
        label = QLabel(self)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setAccessibleName(accessible_name)
        return label

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self._project_id = projeto_id
        self.atualizar()

    def atualizar(self) -> None:
        project_id = self._project_id
        if project_id is None:
            self.limpar()
            return
        try:
            summary = self._gateway.get_gmax(project_id)
            if summary.project_id.root != project_id:
                raise ValueError("O servidor devolveu o resumo GMAX de outro projeto.")
        except (DocumentationGatewayError, ValueError) as error:
            self._show_error(str(error))
            self.status_changed.emit(str(error))
            return
        self._summary = summary
        self._populate(summary)

    def atualizar_apos_conformidade(self, projeto_id: object, _status: object) -> None:
        if isinstance(projeto_id, UUID) and projeto_id == self._project_id:
            self.atualizar()

    def limpar(self) -> None:
        self._project_id = None
        self._summary = None
        self._state.setText("Nenhum projeto ativo. Abra um projeto para consultar o resumo GMAX.")
        self._state.setAccessibleDescription(self._state.text())
        self._project_service_note.setText("NS do projeto: —")
        self._header_service_notes.setText("NS nos cabeçalhos dos PDFs: —")
        self._execution.setText("Última execução de conformidade: —")
        self._market.setText("Não disponível — nenhum projeto ativo")
        self._refresh.setEnabled(False)
        self._populate_empty_checks("Não disponível — nenhum projeto ativo")

    def _show_error(self, message: str) -> None:
        self._summary = None
        self._state.setText(
            "Não foi possível carregar o resumo GMAX. Nenhum resultado anterior é exibido "
            "como atual."
        )
        self._state.setAccessibleDescription(f"{self._state.text()} {message}")
        self._project_service_note.setText("NS do projeto: indisponível")
        self._header_service_notes.setText("NS nos cabeçalhos dos PDFs: indisponível")
        self._execution.setText("Última execução de conformidade: indisponível")
        self._market.setText("Indisponível — falha ao carregar o resumo")
        self._refresh.setEnabled(True)
        self._populate_empty_checks("Indisponível — falha ao carregar o resumo")

    def _populate(self, summary: GmaxSummaryResponse) -> None:
        self._state.setText(_snapshot_text(summary))
        self._state.setAccessibleDescription(self._state.text())
        self._project_service_note.setText(f"NS do projeto: {summary.project_service_note}")
        self._header_service_notes.setText(_header_text(summary))
        self._execution.setText(_execution_text(summary))
        self._market.setText(_market_text(summary))
        self._refresh.setEnabled(True)
        stale = summary.snapshot_state is GmaxSnapshotState.STALE
        for row, check in enumerate(summary.checks):
            values = _check_values(check, stale=stale)
            for column, value in enumerate(values):
                self._set_table_text(row, column, value)

    def _populate_empty_checks(self, unavailable_text: str) -> None:
        for row, label in enumerate(_CHECK_LABELS):
            values = (label, unavailable_text, "—", "Não executado", "Não aplicável")
            for column, value in enumerate(values):
                self._set_table_text(row, column, value)

    def _set_table_text(self, row: int, column: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setToolTip(text)
        item.setData(Qt.ItemDataRole.AccessibleTextRole, text)
        self._checks.setItem(row, column, item)


def _snapshot_text(summary: GmaxSummaryResponse) -> str:
    if summary.snapshot_state is GmaxSnapshotState.NEVER_EXECUTED:
        return (
            "Conformidade ainda não executada. Mercado e resultado do SELECT não estão disponíveis."
        )
    if summary.snapshot_state is GmaxSnapshotState.CURRENT:
        return "Resultado atual da última execução de conformidade."
    if summary.snapshot_state is GmaxSnapshotState.STALE:
        return (
            "Resultado desatualizado. Mercado e consultas abaixo pertencem à última execução; "
            "reanálise necessária para obter valores atuais."
        )
    reason = summary.blocking_reason or "A NS do projeto diverge do cabeçalho dos PDFs."
    return (
        "Consultas bloqueadas por divergência da NS. "
        f"{reason} Corrija o projeto ou os PDFs e reanalise a conformidade. "
        "Resultados antigos não são exibidos como atuais."
    )


def _header_text(summary: GmaxSummaryResponse) -> str:
    if summary.header_state is GmaxHeaderState.NOT_FOUND:
        return "NS nos cabeçalhos dos PDFs: não identificada"
    notes = ", ".join(summary.header_service_notes)
    state = "coincide com o projeto" if summary.header_state is GmaxHeaderState.MATCH else "diverge"
    return f"NS nos cabeçalhos dos PDFs: {notes} — {state}"


def _execution_text(summary: GmaxSummaryResponse) -> str:
    if summary.last_execution_id is None or summary.last_executed_at is None:
        return "Última execução de conformidade: ainda não executada"
    instant = summary.last_executed_at.strftime("%d/%m/%Y %H:%M:%S UTC")
    prefix = (
        "Última execução histórica"
        if summary.snapshot_state is GmaxSnapshotState.BLOCKED_NS_MISMATCH
        else "Última execução de conformidade"
    )
    return f"{prefix}: {instant} · {summary.last_execution_id.root}"


def _market_text(summary: GmaxSummaryResponse) -> str:
    if summary.market is not None:
        label = {
            GmaxMarket.RURAL: "Rural",
            GmaxMarket.URBANO: "Urbano",
        }[summary.market]
        if summary.snapshot_state is GmaxSnapshotState.STALE:
            return f"{label} — última execução, resultado desatualizado"
        return label
    if summary.snapshot_state is GmaxSnapshotState.BLOCKED_NS_MISMATCH:
        return "Não exibido — consultas bloqueadas por divergência da NS"
    return "Não disponível — conformidade ainda não executada"


def _check_values(check: GmaxCheckDto, *, stale: bool) -> tuple[str, ...]:
    pdf = "Detectado" if check.detected_in_pdf else "Não detectado"
    query = _QUERY_LABELS[check.query_state]
    if check.query_state is GmaxQueryState.EXECUTED:
        result = "Linha encontrada" if check.row_found else "Sem linha"
    else:
        result = "Não aplicável — SELECT não executado"
    if stale and check.query_state is GmaxQueryState.EXECUTED:
        query += " — última execução desatualizada"
        result += " — última execução desatualizada"
    return check.label, pdf, check.action, query, result
