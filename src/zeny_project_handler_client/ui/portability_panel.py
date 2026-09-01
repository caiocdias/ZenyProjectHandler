"""Painel Qt de exportação dos arquivos finais compilados pelo servidor."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler_client.logging_config import operation_logger
from zeny_project_handler_client.ui.portability_gateway import (
    PortabilityGateway,
    PortabilityGatewayError,
    PortabilityTransferCancelledError,
)
from zeny_project_handler_contracts.exports import (
    CalloutPositionOverrideDto,
    CreateDeliverableExportRequest,
    DeliverableExportKind,
)

CalloutPositions = Callable[[], tuple[CalloutPositionOverrideDto, ...]]


class _DeliverableExportWorker(QObject):
    progress = Signal(str, int, int, str)
    succeeded = Signal(str, str)
    failed = Signal(str, str)
    finished = Signal()

    def __init__(
        self,
        *,
        gateway: PortabilityGateway,
        project_id: UUID,
        request: CreateDeliverableExportRequest,
        destination: Path,
        cancellation: Event,
        execution_id: str,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._project_id = project_id
        self._request = request
        self._destination = destination
        self._cancellation = cancellation
        self._execution_id = execution_id

    @Slot()
    def run(self) -> None:
        observation = operation_logger(
            "export.deliverable",
            project_id=self._project_id,
            kind=self._request.kind.value,
        )
        with observation.context():
            observation.started()
            try:
                self.progress.emit(
                    self._execution_id,
                    0,
                    0,
                    "Compilando arquivo no servidor",
                )
                metadata = self._gateway.create_deliverable_export(
                    self._project_id,
                    self._request,
                )
                if self._cancellation.is_set():
                    raise PortabilityTransferCancelledError(
                        "Exportação cancelada antes do download"
                    )
                self._gateway.download_to(
                    metadata.download_id.root,
                    self._destination,
                    progress=lambda current, total, message: self.progress.emit(
                        self._execution_id,
                        current,
                        total,
                        message,
                    ),
                    cancelled=self._cancellation.is_set,
                )
            except PortabilityTransferCancelledError as error:
                observation.cancelled(message=str(error))
                self.failed.emit(self._execution_id, str(error))
            except (PortabilityGatewayError, OSError, ValueError) as error:
                observation.failed(error, expected=True)
                self.failed.emit(self._execution_id, str(error).strip() or error.__class__.__name__)
            except Exception as error:
                observation.failed(error, expected=False)
                self.failed.emit(
                    self._execution_id,
                    "Não foi possível gerar o arquivo solicitado.",
                )
            else:
                observation.succeeded(destination=self._destination)
                self.succeeded.emit(self._execution_id, str(self._destination))
            finally:
                self.finished.emit()


class PortabilityPanelWidget(QWidget):
    """Mantém o nome interno legado para não alterar o bootstrap do cliente."""

    status_changed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self,
        *,
        gateway: PortabilityGateway,
        callout_positions: CalloutPositions | None = None,
        parent: QWidget | None = None,
        **_obsolete: object,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("exportPanel")
        self._gateway = gateway
        self._callout_positions = callout_positions or (lambda: ())
        self._thread: QThread | None = None
        self._worker: _DeliverableExportWorker | None = None
        self._cancellation: Event | None = None
        self._execution_id: str | None = None
        self._global_operation: object | None = None
        self._project_versions: dict[UUID, int] = {}
        self._build_ui()
        self.atualizar_projetos()

    @property
    def processando(self) -> bool:
        return self._execution_id is not None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self._project = QComboBox()
        self._project.setObjectName("exportProjectCombo")
        self._project.currentIndexChanged.connect(self._apply_action_state)
        layout.addWidget(self._project)

        guidance = QLabel(
            "Os arquivos são compilados pelo servidor e baixados diretamente para esta máquina. "
            "O PDF respeita a ordem das folhas e inclui as anotações de conformidade disponíveis."
        )
        guidance.setObjectName("exportGuidance")
        guidance.setProperty("role", "hint")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)

        group = QGroupBox("Arquivos do projeto")
        actions = QVBoxLayout(group)
        self._pdf = self._button(
            "Baixar PDF com anotações",
            "exportAnnotatedPdfButton",
            DeliverableExportKind.ANNOTATED_PDF,
            primary=True,
        )
        actions.addWidget(self._pdf)
        self._results = self._button(
            "Baixar Resultados (.xlsx)",
            "exportResultsButton",
            DeliverableExportKind.RESULTS_XLSX,
        )
        actions.addWidget(self._results)
        self._documentation = self._button(
            "Baixar Documentação (.xlsx)",
            "exportDocumentationButton",
            DeliverableExportKind.DOCUMENTATION_XLSX,
        )
        actions.addWidget(self._documentation)
        self._compliance = self._button(
            "Baixar Conformidade e regras (.xlsx)",
            "exportComplianceButton",
            DeliverableExportKind.COMPLIANCE_XLSX,
        )
        actions.addWidget(self._compliance)
        self._cancel = QPushButton("Cancelar download")
        self._cancel.setObjectName("exportCancelButton")
        self._cancel.setProperty("role", "danger")
        self._cancel.clicked.connect(self.cancelar_operacao)
        actions.addWidget(self._cancel)
        self._progress = QProgressBar()
        self._progress.setObjectName("exportProgress")
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        actions.addWidget(self._progress)
        layout.addWidget(group)
        layout.addStretch(1)
        self._apply_action_state()

    def _button(
        self,
        text: str,
        object_name: str,
        kind: DeliverableExportKind,
        *,
        primary: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        if primary:
            button.setProperty("role", "primary")
        button.clicked.connect(lambda _checked=False, value=kind: self.exportar(value))
        return button

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        try:
            response = self._gateway.list_projects(limit=200, offset=0)
        except Exception as error:
            self.status_changed.emit(str(error).strip() or error.__class__.__name__)
            return
        self._project_versions = {
            item.project_id.root: item.project_version for item in response.items
        }
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto", None)
        for summary in response.items:
            self._project.addItem(summary.service_note, str(summary.project_id.root))
        if selected is not None:
            index = self._project.findData(selected)
            if index >= 0:
                self._project.setCurrentIndex(index)
        self._project.blockSignals(False)
        self._apply_action_state()

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index >= 0:
            self._project.setCurrentIndex(index)

    def limpar(self) -> None:
        signals_were_blocked = self._project.blockSignals(True)
        try:
            self._project.setCurrentIndex(0 if self._project.count() else -1)
        finally:
            self._project.blockSignals(signals_were_blocked)
        self._apply_action_state()

    def exportar(self, kind: DeliverableExportKind) -> None:
        if self._reject_reentry():
            return
        project_id = self._project_id()
        if project_id is None:
            self.status_changed.emit("Selecione um projeto para exportar")
            return
        service_note = self._project.currentText().strip() or "projeto"
        suffix = ".pdf" if kind is DeliverableExportKind.ANNOTATED_PDF else ".xlsx"
        stem = {
            DeliverableExportKind.ANNOTATED_PDF: "pdf-anotado",
            DeliverableExportKind.RESULTS_XLSX: "resultados",
            DeliverableExportKind.DOCUMENTATION_XLSX: "documentacao",
            DeliverableExportKind.COMPLIANCE_XLSX: "conformidade",
        }[kind]
        title = {
            DeliverableExportKind.ANNOTATED_PDF: "Baixar PDF com anotações",
            DeliverableExportKind.RESULTS_XLSX: "Baixar resultados",
            DeliverableExportKind.DOCUMENTATION_XLSX: "Baixar documentação",
            DeliverableExportKind.COMPLIANCE_XLSX: "Baixar conformidade e regras",
        }[kind]
        file_filter = "Documento PDF (*.pdf)" if suffix == ".pdf" else "Planilha Excel (*.xlsx)"
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            title,
            f"{service_note}-{stem}{suffix}",
            file_filter,
        )
        if not selected:
            return
        destination = _with_suffix(Path(selected), suffix)
        overrides = self._callout_positions() if kind is DeliverableExportKind.ANNOTATED_PDF else ()
        self._start_operation(
            project_id,
            CreateDeliverableExportRequest(
                kind=kind,
                expected_project_version=self._project_versions[project_id],
                callout_positions=overrides,
            ),
            destination,
        )

    def set_global_operation(self, operation: object | None) -> None:
        self._global_operation = operation
        self._apply_action_state()

    def cancelar_operacao(self) -> None:
        if self._cancellation is None:
            return
        self._cancellation.set()
        self._cancel.setEnabled(False)
        self.status_changed.emit("Cancelamento solicitado; aguardando um ponto seguro")

    def cancelar_e_aguardar(self, timeout_ms: int) -> bool:
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        self.cancelar_operacao()
        return thread.wait(max(0, timeout_ms))

    def _start_operation(
        self,
        project_id: UUID,
        request: CreateDeliverableExportRequest,
        destination: Path,
    ) -> None:
        execution_id = uuid4().hex
        cancellation = Event()
        thread = QThread(self)
        thread.setObjectName(f"deliverable-export-{execution_id[:8]}")
        worker = _DeliverableExportWorker(
            gateway=self._gateway,
            project_id=project_id,
            request=request,
            destination=destination,
            cancellation=cancellation,
            execution_id=execution_id,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._show_progress)
        worker.succeeded.connect(self._operation_succeeded)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._cancellation = cancellation
        self._execution_id = execution_id
        self._progress.setRange(0, 0)
        self._progress.setFormat("Compilando arquivo no servidor…")
        self._apply_action_state()
        self.busy_changed.emit(True)
        thread.start()

    def _reject_reentry(self) -> bool:
        if not self.processando and self._global_operation is None:
            return False
        self.status_changed.emit(
            "Uma exportação já está em andamento"
            if self.processando
            else "Outra operação global está em andamento; aguarde a conclusão"
        )
        return True

    @Slot(str, int, int, str)
    def _show_progress(self, execution_id: str, current: int, total: int, message: str) -> None:
        if execution_id != self._execution_id:
            return
        if total <= 0:
            self._progress.setRange(0, 0)
            self._progress.setFormat(f"{message}…")
        else:
            safe_total = max(1, total)
            self._progress.setRange(0, safe_total)
            self._progress.setValue(min(max(0, current), safe_total))
            self._progress.setFormat(f"{message} · %p%")
        self.status_changed.emit(message)

    @Slot(str, str)
    def _operation_succeeded(self, execution_id: str, destination: str) -> None:
        if execution_id == self._execution_id:
            self.status_changed.emit(f"Arquivo exportado para {destination}")

    @Slot(str, str)
    def _operation_failed(self, execution_id: str, message: str) -> None:
        if execution_id == self._execution_id:
            self.status_changed.emit(message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._cancellation = None
        self._execution_id = None
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("")
        self._apply_action_state()
        self.busy_changed.emit(False)

    def _project_id(self) -> UUID | None:
        value = self._project.currentData()
        return UUID(str(value)) if value is not None else None

    def _apply_action_state(self) -> None:
        enabled = (
            not self.processando
            and self._global_operation is None
            and self._project.currentData() is not None
        )
        for button in (self._pdf, self._results, self._documentation, self._compliance):
            button.setEnabled(enabled)
        self._project.setEnabled(not self.processando and self._global_operation is None)
        self._cancel.setEnabled(self.processando)


def _with_suffix(path: Path, suffix: str) -> Path:
    return path if path.suffix.casefold() == suffix else path.with_suffix(suffix)
