"""Painel Qt assíncrono de transporte e recuperação de projetos."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.project_portability import (
    PlanoImportacaoProjeto,
    ResultadoBackupCompleto,
    ResultadoExportacaoProjeto,
    ResultadoImportacaoProjeto,
    ResultadoRestauracaoBackup,
    ServicoPortabilidadeProjeto,
)
from zeny_project_handler.domain.portability import (
    EstadoIntegridadePacote,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.logging_config import operation_logger

from .portability_worker import (
    PortabilityCommand,
    PortabilityOperation,
    PortabilityWorker,
)


class PortabilityPanelWidget(QWidget):
    status_changed = Signal(str)
    data_changed = Signal()
    data_restored = Signal()
    busy_changed = Signal(bool)

    def __init__(
        self,
        *,
        service: ServicoPortabilidadeProjeto,
        coordinator: CoordenadorOperacoes | None = None,
        preparar_restauracao: Callable[[], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("portabilityPanel")
        self._service = service
        self._coordinator = coordinator or service.coordenador
        self._preparar_restauracao = preparar_restauracao or (lambda: True)
        self._thread: QThread | None = None
        self._worker: PortabilityWorker | None = None
        self._cancellation: Event | None = None
        self._execution_id: str | None = None
        self._worker_finished_id: str | None = None
        self._operation: PortabilityOperation | None = None
        self._global_operation: TipoOperacao | None = None
        self._last_progress = 0.0
        self._build_ui()
        self.atualizar_projetos()

    @property
    def processando(self) -> bool:
        return self._execution_id is not None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._project = QComboBox()
        self._project.setObjectName("portabilityProjectCombo")
        layout.addWidget(self._project)

        package_box = QGroupBox("Transporte e recuperação")
        package_layout = QVBoxLayout(package_box)
        project_actions = QHBoxLayout()
        self._export = QPushButton("Exportar projeto")
        self._export.setObjectName("portabilityExportButton")
        self._export.clicked.connect(self.exportar_projeto)
        project_actions.addWidget(self._export)
        self._import = QPushButton("Importar projeto")
        self._import.setObjectName("portabilityImportButton")
        self._import.clicked.connect(self.importar_projeto)
        project_actions.addWidget(self._import)
        package_layout.addLayout(project_actions)
        backup_actions = QHBoxLayout()
        self._backup = QPushButton("Criar backup")
        self._backup.setObjectName("portabilityBackupButton")
        self._backup.clicked.connect(self.criar_backup)
        backup_actions.addWidget(self._backup)
        self._restore = QPushButton("Restaurar backup")
        self._restore.setObjectName("portabilityRestoreButton")
        self._restore.clicked.connect(self.restaurar_backup)
        backup_actions.addWidget(self._restore)
        package_layout.addLayout(backup_actions)
        self._cancel = QPushButton("Cancelar operação")
        self._cancel.setObjectName("portabilityCancelButton")
        self._cancel.clicked.connect(self.cancelar_operacao)
        package_layout.addWidget(self._cancel)
        self._progress = QProgressBar()
        self._progress.setObjectName("portabilityProgress")
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        package_layout.addWidget(self._progress)
        layout.addWidget(package_box)
        layout.addStretch(1)
        self._apply_action_state()

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        try:
            summaries = self._service.listar_projetos()
        except Exception as error:
            self._warn(str(error).strip() or error.__class__.__name__)
            return
        self._project.blockSignals(True)
        self._project.clear()
        self._project.addItem("Selecione um projeto", None)
        for summary in summaries:
            self._project.addItem(summary.nome, str(summary.projeto_id))
        if selected is not None:
            index = self._project.findData(selected)
            if index >= 0:
                self._project.setCurrentIndex(index)
        self._project.blockSignals(False)

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index >= 0:
            self._project.setCurrentIndex(index)

    def exportar_projeto(self) -> None:
        if self._reject_reentry():
            return
        project_id = self._project_id()
        if project_id is None:
            self._warn("Selecione um projeto para exportar")
            return
        selection = operation_logger("portability.export.selection", project_id=project_id)
        with selection.context():
            selection.started()
            name, _filter = QFileDialog.getSaveFileName(
                self, "Exportar projeto portátil", "projeto.zphproj", "Projeto Zeny (*.zphproj)"
            )
            if not name:
                selection.cancelled()
                return
            selection.succeeded()
        self._start_operation(
            PortabilityCommand(
                PortabilityOperation.EXPORT,
                _with_suffix(Path(name), ".zphproj"),
                project_id,
            )
        )

    def importar_projeto(self) -> None:
        if self._reject_reentry():
            return
        selection = operation_logger("portability.import.selection")
        with selection.context():
            selection.started()
            name, _filter = QFileDialog.getOpenFileName(
                self, "Importar projeto portátil", "", "Projeto Zeny (*.zphproj)"
            )
            if not name:
                selection.cancelled()
                return
            selection.succeeded()
        self._start_operation(PortabilityCommand(PortabilityOperation.IMPORT, Path(name)))

    def criar_backup(self) -> None:
        if self._reject_reentry():
            return
        selection = operation_logger("portability.backup.selection")
        with selection.context():
            selection.started()
            name, _filter = QFileDialog.getSaveFileName(
                self,
                "Criar backup completo",
                "zeny-backup.zphbackup",
                "Backup Zeny (*.zphbackup)",
            )
            if not name:
                selection.cancelled()
                return
            selection.succeeded()
        self._start_operation(
            PortabilityCommand(
                PortabilityOperation.BACKUP,
                _with_suffix(Path(name), ".zphbackup"),
            )
        )

    def restaurar_backup(self) -> None:
        if self._reject_reentry():
            return
        selection = operation_logger("portability.restore.selection")
        with selection.context():
            selection.started()
            name, _filter = QFileDialog.getOpenFileName(
                self, "Restaurar backup completo", "", "Backup Zeny (*.zphbackup)"
            )
            if not name:
                selection.cancelled()
                return
            selection.succeeded()
        confirmation_log = operation_logger("portability.restore.confirmation")
        confirmation_log.started()
        confirmation = QMessageBox.question(
            self,
            "Restaurar backup",
            "Substituir o banco e os arquivos gerenciados atuais pelo backup selecionado? O "
            "estado atual será preservado temporariamente para reversão se houver falha.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            confirmation_log.cancelled()
            return
        confirmation_log.succeeded()
        if not self._preparar_restauracao():
            message = (
                "A restauração não foi iniciada porque o PDF ainda está em uso. "
                "Aguarde a renderização terminar e tente novamente."
            )
            self.status_changed.emit(message)
            QMessageBox.warning(self, "Restauração não iniciada", message)
            return
        self._start_operation(PortabilityCommand(PortabilityOperation.RESTORE, Path(name)))

    def set_global_operation(self, operation: TipoOperacao | None) -> None:
        self._global_operation = operation
        self._apply_action_state()

    def cancelar_operacao(self) -> None:
        if not self.processando:
            return
        if self._worker is not None:
            self._worker.request_cancel()
        elif self._cancellation is not None:
            self._cancellation.set()
        self._cancel.setEnabled(False)
        self.status_changed.emit("Cancelamento solicitado; aguardando um ponto seguro")

    def cancelar_e_aguardar(self, timeout_ms: int) -> bool:
        """Cancele cooperativamente e espere sem finalizar a thread à força."""
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        self.cancelar_operacao()
        return thread.wait(max(0, timeout_ms))

    def _start_operation(self, command: PortabilityCommand) -> None:
        if self._reject_reentry():
            return
        execution_id = uuid4().hex
        cancellation = Event()
        thread = QThread(self)
        thread.setObjectName(f"portability-{command.operation.value}-{execution_id[:8]}")
        worker = PortabilityWorker(
            self._service,
            command,
            cancellation,
            execution_id,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._show_progress)
        worker.confirmation_required.connect(self._confirmation_required)
        worker.succeeded.connect(self._operation_succeeded)
        worker.failed.connect(self._operation_failed)
        worker.finished.connect(self._worker_finished)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.destroyed.connect(self._thread_stopped)
        self._thread = thread
        self._worker = worker
        self._cancellation = cancellation
        self._execution_id = execution_id
        self._worker_finished_id = None
        self._operation = command.operation
        self._last_progress = 0.0
        self._progress.setRange(0, 0)
        self._progress.setFormat("Preparando operação…")
        self._apply_action_state()
        self.busy_changed.emit(True)
        thread.start()

    def _reject_reentry(self) -> bool:
        thread_running = self._thread is not None and self._thread.isRunning()
        active = self._coordinator.operacao_em_andamento
        if not self.processando and not thread_running and active is None:
            return False
        if self.processando or thread_running:
            message = "Uma operação de portabilidade já está em andamento"
        else:
            assert active is not None
            message = f"{active.value.capitalize()} está em andamento; aguarde a conclusão"
        self.status_changed.emit(message)
        return True

    @Slot(str, int, int, str)
    def _show_progress(self, execution_id: str, current: int, total: int, message: str) -> None:
        if execution_id != self._execution_id:
            return
        safe_total = max(1, total)
        safe_current = min(max(0, current), safe_total)
        fraction = safe_current / safe_total
        if fraction < self._last_progress:
            return
        self._last_progress = fraction
        self._progress.setRange(0, safe_total)
        self._progress.setValue(safe_current)
        self._progress.setFormat(f"{message} · %p%")
        self.status_changed.emit(message)

    @Slot(str, str, object)
    def _confirmation_required(self, execution_id: str, kind: str, payload: object) -> None:
        sender = self.sender()
        worker = sender if isinstance(sender, PortabilityWorker) else None
        if execution_id != self._execution_id or worker is not self._worker:
            if worker is not None:
                worker.resolve_confirmation(False)
            return
        assert worker is not None
        if kind == "replace_project" and isinstance(payload, PlanoImportacaoProjeto):
            confirmation_log = operation_logger("portability.import.replace_confirmation")
            title = "Substituir projeto existente"
            message = _import_confirmation_message(payload)
        elif kind == "degraded_backup" and isinstance(payload, RelatorioIntegridadeProjeto):
            confirmation_log = operation_logger("portability.backup.degraded_confirmation")
            title = "Criar backup com ressalvas"
            message = _backup_confirmation_message(payload)
        else:
            worker.resolve_confirmation(False)
            return
        confirmation_log.started()
        accepted = (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
        if accepted:
            confirmation_log.succeeded()
        else:
            confirmation_log.cancelled()
        worker.resolve_confirmation(accepted)

    @Slot(str, object)
    def _operation_succeeded(self, execution_id: str, result: object) -> None:
        if execution_id != self._execution_id:
            return
        operation = self._operation
        if operation is PortabilityOperation.EXPORT and isinstance(
            result, ResultadoExportacaoProjeto
        ):
            qualifier = " com ressalvas" if _is_degraded(result.estado_integridade) else ""
            self.status_changed.emit(f"Projeto exportado{qualifier} para {result.caminho}")
        elif operation is PortabilityOperation.IMPORT and isinstance(
            result, ResultadoImportacaoProjeto
        ):
            self.atualizar_projetos()
            self.abrir_projeto(result.projeto.id)
            self.data_changed.emit()
            if result.omissoes_origem:
                self.status_changed.emit(
                    "Projeto importado com ressalvas da origem; "
                    "PDFs omitidos continuam indisponíveis"
                )
            else:
                self.status_changed.emit(
                    "Projeto importado com IDs, análises e revisões preservados"
                )
        elif operation is PortabilityOperation.BACKUP and isinstance(
            result, ResultadoBackupCompleto
        ):
            qualifier = " com ressalvas" if _is_degraded(result.estado_integridade) else ""
            self.status_changed.emit(f"Backup criado{qualifier} em {result.caminho}")
        elif operation is PortabilityOperation.RESTORE and isinstance(
            result, ResultadoRestauracaoBackup
        ):
            self.atualizar_projetos()
            self.data_restored.emit()
            if _is_degraded(result.estado_integridade):
                count = len(result.manifesto.omissoes)
                self.status_changed.emit(
                    f"Backup restaurado com ressalvas; {count} PDF(s) continuam indisponíveis"
                )
            else:
                self.status_changed.emit("Backup restaurado e dados da interface recarregados")

    @Slot(str, str, bool)
    def _operation_failed(self, execution_id: str, message: str, cancelled: bool) -> None:
        if execution_id != self._execution_id:
            return
        self.status_changed.emit(message)
        if not cancelled:
            QMessageBox.warning(self, "Ação não concluída", message)

    @Slot(str)
    def _worker_finished(self, execution_id: str) -> None:
        if execution_id != self._execution_id:
            return
        self._worker_finished_id = execution_id

    def _finalize_execution(self, execution_id: str) -> None:
        if execution_id != self._execution_id:
            return
        self._execution_id = None
        self._worker_finished_id = None
        self._operation = None
        self._cancellation = None
        self._reset_progress()
        self._apply_action_state()
        self.busy_changed.emit(False)

    @Slot(object)
    def _thread_stopped(self, _destroyed_thread: object | None = None) -> None:
        execution_id = self._execution_id
        self._thread = None
        self._worker = None
        if execution_id is not None:
            self._finalize_execution(execution_id)
        self._apply_action_state()

    def _apply_action_state(self) -> None:
        thread_running = self._thread is not None and self._thread.isRunning()
        blocked = self.processando or thread_running or self._global_operation is not None
        for widget in (self._project, self._export, self._import, self._backup, self._restore):
            widget.setEnabled(not blocked)
        self._cancel.setEnabled(self.processando)

    def _reset_progress(self) -> None:
        self._last_progress = 0.0
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")

    def _project_id(self) -> UUID | None:
        value = self._project.currentData()
        return UUID(str(value)) if value is not None else None

    def _warn(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Ação não concluída", message)


def _with_suffix(path: Path, suffix: str) -> Path:
    return path if path.suffix.casefold() == suffix else path.with_suffix(suffix)


def _is_degraded(state: EstadoIntegridadePacote) -> bool:
    return state is EstadoIntegridadePacote.DEGRADADO


def _import_confirmation_message(plan: PlanoImportacaoProjeto) -> str:
    summary = plan.resumo
    conflicts: list[str] = []
    if plan.projeto_existente:
        conflicts.append("há um projeto local com o mesmo ID")
    if plan.pasta_destino_existente:
        conflicts.append("há arquivos na pasta gerenciada desse ID")
    conflict_text = " e ".join(conflicts)
    return (
        "O preflight validou o pacote e detectou que "
        f"{conflict_text}.\n\n"
        f"Projeto: {summary.nome}\n"
        f"ID: {str(summary.projeto_id)[:8]}\n"
        f"Conteúdo: {summary.quantidade_documentos} PDF(s), "
        f"{summary.quantidade_fotos} foto(s) e "
        f"{summary.quantidade_analises} análise(s)\n"
        f"Fingerprint do plano: {plan.fingerprint[:12]}\n\n"
        "Substituir os dados e arquivos locais pela versão importada? O pacote e o destino serão "
        "revalidados antes de qualquer troca."
    )


def _backup_confirmation_message(report: RelatorioIntegridadeProjeto) -> str:
    labels = {
        "PDF_AUSENTE": "ausente",
        "PDF_ADULTERADO": "alterado desde a importação",
        "PDF_ILEGIVEL": "ilegível",
    }
    treatments = {
        "OMITIDO": "cópia omitida; não há origem registrada",
        "PERMANECE_EXTERNO": "cópia omitida; referência permanecerá externa",
    }
    details = "\n".join(
        f"• Documento {str(item.referencia_id)[:8]} — "
        f"{labels.get(item.codigo, 'indisponível')}; "
        f"{treatments.get(str(item.tratamento), 'cópia omitida')}"
        for item in report.problemas
    )
    return (
        "Os PDFs abaixo não serão copiados. O efeito de cada omissão após uma restauração está "
        "indicado individualmente:\n\n"
        f"{details}\n\n"
        "Criar o backup degradado mesmo assim?"
    )
