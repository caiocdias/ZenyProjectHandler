"""Painel Qt de transporte e recuperação de projetos."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
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

from zeny_project_handler.application.project_portability import (
    ResultadoImportacaoProjeto,
    ServicoPortabilidadeProjeto,
)
from zeny_project_handler.domain.portability import (
    EstadoIntegridadePacote,
    RelatorioIntegridadeProjeto,
)
from zeny_project_handler.logging_config import operation_logger

T = TypeVar("T")


class PortabilityPanelWidget(QWidget):
    status_changed = Signal(str)
    data_changed = Signal()
    data_restored = Signal()

    def __init__(
        self,
        *,
        service: ServicoPortabilidadeProjeto,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("portabilityPanel")
        self._service = service
        self._build_ui()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._project = QComboBox()
        self._project.setObjectName("portabilityProjectCombo")
        layout.addWidget(self._project)

        package_box = QGroupBox("Transporte e recuperação")
        package_layout = QVBoxLayout(package_box)
        project_actions = QHBoxLayout()
        export_button = QPushButton("Exportar projeto")
        export_button.setObjectName("portabilityExportButton")
        export_button.clicked.connect(self.exportar_projeto)
        project_actions.addWidget(export_button)
        import_button = QPushButton("Importar projeto")
        import_button.setObjectName("portabilityImportButton")
        import_button.clicked.connect(self.importar_projeto)
        project_actions.addWidget(import_button)
        package_layout.addLayout(project_actions)
        backup_actions = QHBoxLayout()
        backup = QPushButton("Criar backup")
        backup.setObjectName("portabilityBackupButton")
        backup.clicked.connect(self.criar_backup)
        backup_actions.addWidget(backup)
        restore = QPushButton("Restaurar backup")
        restore.setObjectName("portabilityRestoreButton")
        restore.clicked.connect(self.restaurar_backup)
        backup_actions.addWidget(restore)
        package_layout.addLayout(backup_actions)
        self._progress = QProgressBar()
        self._progress.setObjectName("portabilityProgress")
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        package_layout.addWidget(self._progress)
        layout.addWidget(package_box)
        layout.addStretch(1)

    def atualizar_projetos(self) -> None:
        selected = self._project.currentData()
        summaries = self._action(self._service.listar_projetos)
        if summaries is None:
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
            result = self._action(
                lambda: self._service.exportar_projeto(
                    project_id,
                    _with_suffix(Path(name), ".zphproj"),
                    progresso=self._show_progress,
                )
            )
        self._reset_progress()
        if result is not None:
            if result.estado_integridade is EstadoIntegridadePacote.DEGRADADO:
                self.status_changed.emit(f"Projeto exportado com ressalvas para {result.caminho}")
            else:
                self.status_changed.emit(f"Projeto exportado para {result.caminho}")

    def importar_projeto(self) -> None:
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
            result: ResultadoImportacaoProjeto | None
            try:
                result = self._service.importar_projeto(Path(name), progresso=self._show_progress)
            except Exception as error:
                if "confirme explicitamente" not in str(error):
                    self._reset_progress()
                    self._warn(str(error).strip() or error.__class__.__name__)
                    return
                confirmation_log = operation_logger("portability.import.replace_confirmation")
                confirmation_log.started()
                confirmation = QMessageBox.question(
                    self,
                    "Substituir projeto existente",
                    "O pacote possui o mesmo ID de um projeto local. Substituir seus dados e "
                    "arquivos pela versão importada?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirmation != QMessageBox.StandardButton.Yes:
                    confirmation_log.cancelled()
                    self._reset_progress()
                    return
                confirmation_log.succeeded()
                result = self._action(
                    lambda: self._service.importar_projeto(
                        Path(name),
                        substituir_existente=True,
                        progresso=self._show_progress,
                    )
                )
                if result is None:
                    self._reset_progress()
                    return
            if result is None:
                self._reset_progress()
                return
        self._reset_progress()
        self.atualizar_projetos()
        self.abrir_projeto(result.projeto.id)
        self.data_changed.emit()
        if result.omissoes_origem:
            self.status_changed.emit(
                "Projeto importado com ressalvas da origem; PDFs omitidos continuam indisponíveis"
            )
        else:
            self.status_changed.emit("Projeto importado com IDs, análises e revisões preservados")

    def criar_backup(self) -> None:
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
            report = self._action(self._service.preflight_backup)
            if report is None:
                return
            confirmed_degraded = False
            if not report.integro:
                confirmation_log = operation_logger("portability.backup.degraded_confirmation")
                confirmation_log.started()
                confirmation = QMessageBox.question(
                    self,
                    "Criar backup com ressalvas",
                    _backup_confirmation_message(report),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if confirmation != QMessageBox.StandardButton.Yes:
                    confirmation_log.cancelled()
                    self._reset_progress()
                    return
                confirmation_log.succeeded()
                confirmed_degraded = True
            result = self._action(
                lambda: self._service.criar_backup(
                    _with_suffix(Path(name), ".zphbackup"),
                    confirmar_degradado=confirmed_degraded,
                    relatorio_integridade=report,
                    progresso=self._show_progress,
                )
            )
        self._reset_progress()
        if result is not None:
            if result.estado_integridade is EstadoIntegridadePacote.DEGRADADO:
                self.status_changed.emit(f"Backup criado com ressalvas em {result.caminho}")
            else:
                self.status_changed.emit(f"Backup criado em {result.caminho}")

    def restaurar_backup(self) -> None:
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
            result = self._action(
                lambda: self._service.restaurar_backup(Path(name), progresso=self._show_progress)
            )
            if result is None:
                self._reset_progress()
                return
        self._reset_progress()
        self.atualizar_projetos()
        self.data_restored.emit()
        if result.estado_integridade is EstadoIntegridadePacote.DEGRADADO:
            count = len(result.manifesto.omissoes)
            self.status_changed.emit(
                f"Backup restaurado com ressalvas; {count} PDF(s) continuam indisponíveis"
            )
        else:
            self.status_changed.emit("Backup restaurado e dados da interface recarregados")

    def _show_progress(self, current: int, total: int, message: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(current)
        self._progress.setFormat(f"{message} · %p%")
        self.status_changed.emit(message)
        QApplication.processEvents()

    def _reset_progress(self) -> None:
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("%p%")

    def _project_id(self) -> UUID | None:
        value = self._project.currentData()
        return UUID(str(value)) if value is not None else None

    def _warn(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Ação não concluída", message)

    def _action(self, action: Callable[[], T]) -> T | None:
        try:
            return action()
        except Exception as error:
            self._warn(str(error).strip() or error.__class__.__name__)
            return None


def _with_suffix(path: Path, suffix: str) -> Path:
    return path if path.suffix.casefold() == suffix else path.with_suffix(suffix)


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
