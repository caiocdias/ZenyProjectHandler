"""Painel Qt de fotos, projeto portátil, integridade e recuperação."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.application.project_portability import (
    ResultadoImportacaoProjeto,
    ServicoPortabilidadeProjeto,
)
from zeny_project_handler.domain.project import FotoElemento

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
        self._photos: dict[UUID, FotoElemento] = {}
        self._element_photos: dict[UUID, tuple[FotoElemento, ...]] = {}
        self._build_ui()
        self.atualizar_projetos()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._project = QComboBox()
        self._project.setObjectName("portabilityProjectCombo")
        self._project.currentIndexChanged.connect(self._project_changed)
        layout.addWidget(self._project)

        photo_box = QGroupBox("Fotos dos elementos")
        photo_layout = QVBoxLayout(photo_box)
        self._element = QComboBox()
        self._element.setObjectName("portabilityElementCombo")
        self._element.currentIndexChanged.connect(self._element_changed)
        photo_layout.addWidget(self._element)
        self._photos_list = QListWidget()
        self._photos_list.setObjectName("portabilityPhotoList")
        self._photos_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        photo_layout.addWidget(self._photos_list)
        self._caption = QLineEdit()
        self._caption.setObjectName("portabilityPhotoCaptionEdit")
        self._caption.setPlaceholderText("Legenda opcional da nova foto")
        photo_layout.addWidget(self._caption)
        photo_actions = QHBoxLayout()
        attach = QPushButton("Anexar foto")
        attach.setObjectName("portabilityAttachPhotoButton")
        attach.clicked.connect(self.anexar_foto)
        photo_actions.addWidget(attach)
        locate = QPushButton("Localizar arquivo")
        locate.setObjectName("portabilityLocatePhotoButton")
        locate.clicked.connect(self.localizar_foto)
        photo_actions.addWidget(locate)
        remove = QPushButton("Remover")
        remove.setObjectName("portabilityRemovePhotoButton")
        remove.clicked.connect(self.remover_foto)
        photo_actions.addWidget(remove)
        photo_layout.addLayout(photo_actions)
        layout.addWidget(photo_box)

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

        integrity_box = QGroupBox("Relatório de integridade")
        integrity_layout = QVBoxLayout(integrity_box)
        pdf_row = QHBoxLayout()
        self._pdf = QComboBox()
        self._pdf.setObjectName("portabilityPdfCombo")
        pdf_row.addWidget(self._pdf, 1)
        locate_pdf = QPushButton("Localizar PDF")
        locate_pdf.setObjectName("portabilityLocatePdfButton")
        locate_pdf.clicked.connect(self.localizar_pdf)
        pdf_row.addWidget(locate_pdf)
        integrity_layout.addLayout(pdf_row)
        check = QPushButton("Verificar integridade")
        check.setObjectName("portabilityIntegrityButton")
        check.clicked.connect(self.verificar_integridade)
        integrity_layout.addWidget(check)
        self._integrity_summary = QLabel("Selecione um projeto para verificar seus arquivos.")
        self._integrity_summary.setObjectName("portabilityIntegritySummary")
        self._integrity_summary.setWordWrap(True)
        integrity_layout.addWidget(self._integrity_summary)
        self._issues = QTableWidget(0, 3)
        self._issues.setObjectName("portabilityIntegrityTable")
        self._issues.setHorizontalHeaderLabels(("Código", "Arquivo", "Ação necessária"))
        self._issues.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._issues.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        integrity_layout.addWidget(self._issues)
        layout.addWidget(integrity_box)
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
            self._project.addItem(
                f"{summary.nome} · {summary.fotos} foto(s)", str(summary.projeto_id)
            )
        if selected is not None:
            index = self._project.findData(selected)
            if index >= 0:
                self._project.setCurrentIndex(index)
        self._project.blockSignals(False)
        self._project_changed()

    def abrir_projeto(self, projeto_id: UUID) -> None:
        self.atualizar_projetos()
        index = self._project.findData(str(projeto_id))
        if index >= 0:
            self._project.setCurrentIndex(index)

    def _project_changed(self) -> None:
        project_id = self._project_id()
        self._element_photos.clear()
        self._element.clear()
        self._element.addItem("Selecione um elemento", None)
        self._pdf.clear()
        self._pdf.addItem("Selecione um PDF", None)
        if project_id is None:
            self._refresh_photos(())
            return
        elements = self._action(lambda: self._service.listar_elementos(project_id))
        if elements is None:
            return
        for element in elements:
            self._element.addItem(element.rotulo, str(element.elemento_id))
            self._element_photos[element.elemento_id] = element.fotos
        pdfs = self._action(lambda: self._service.listar_pdfs(project_id))
        if pdfs is not None:
            for document in pdfs:
                status = "disponível" if document.disponivel else "ausente"
                self._pdf.addItem(f"{document.nome} · {status}", str(document.documento_id))
        self._integrity_summary.setText("Clique em Verificar integridade.")
        self._issues.setRowCount(0)

    def _element_changed(self) -> None:
        value = self._element.currentData()
        photos = self._element_photos.get(UUID(str(value)), ()) if value is not None else ()
        self._refresh_photos(photos)

    def _refresh_photos(self, photos: tuple[FotoElemento, ...]) -> None:
        self._photos = {item.id: item for item in photos}
        self._photos_list.clear()
        for photo in photos:
            label = photo.legenda or Path(photo.caminho_relativo).name
            suffix = "" if photo.sha256 else " · metadados pendentes"
            item = QListWidgetItem(f"{label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, str(photo.id))
            self._photos_list.addItem(item)

    def anexar_foto(self) -> None:
        ids = self._selected_ids()
        if ids is None:
            self._warn("Selecione um projeto e um elemento")
            return
        name, _filter = QFileDialog.getOpenFileName(
            self,
            "Selecionar foto",
            "",
            "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp)",
        )
        if not name:
            return
        result = self._action(
            lambda: self._service.anexar_foto(
                ids[0], ids[1], Path(name), legenda=self._caption.text()
            )
        )
        if result is None:
            return
        self._caption.clear()
        self.abrir_projeto(ids[0])
        self._select_element(ids[1])
        self.data_changed.emit()
        self.status_changed.emit(
            "Foto já vinculada; arquivo deduplicado"
            if result.deduplicada
            else "Foto anexada com hash e tipo validados"
        )

    def remover_foto(self) -> None:
        ids = self._selected_ids()
        photo = self._selected_photo()
        if ids is None or photo is None:
            self._warn("Selecione a foto que deseja remover")
            return
        confirmation = QMessageBox.question(
            self,
            "Remover foto",
            "Remover esta foto do elemento? O arquivo gerenciado será apagado se não estiver "
            "vinculado a outro elemento.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        if self._action(lambda: self._service.remover_foto(ids[0], ids[1], photo.id)) is None:
            return
        self.abrir_projeto(ids[0])
        self._select_element(ids[1])
        self.data_changed.emit()
        self.status_changed.emit("Foto removida do projeto")

    def localizar_foto(self) -> None:
        ids = self._selected_ids()
        photo = self._selected_photo()
        if ids is None or photo is None:
            self._warn("Selecione uma foto ausente ou divergente")
            return
        name, _filter = QFileDialog.getOpenFileName(
            self,
            "Localizar foto correspondente",
            "",
            "Imagens (*.jpg *.jpeg *.png *.tif *.tiff *.webp)",
        )
        if not name:
            return
        if (
            self._action(lambda: self._service.localizar_foto(ids[0], ids[1], photo.id, Path(name)))
            is None
        ):
            return
        self.abrir_projeto(ids[0])
        self._select_element(ids[1])
        self.verificar_integridade()
        self.data_changed.emit()
        self.status_changed.emit("Foto localizada e integridade atualizada")

    def verificar_integridade(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            self._warn("Selecione um projeto")
            return
        report = self._action(lambda: self._service.verificar_integridade(project_id))
        if report is None:
            return
        self._issues.setRowCount(0)
        for problem in report.problemas:
            row = self._issues.rowCount()
            self._issues.insertRow(row)
            for column, value in enumerate(
                (problem.codigo, problem.caminho_relativo or "—", problem.mensagem)
            ):
                self._issues.setItem(row, column, QTableWidgetItem(value))
        if report.integro:
            self._integrity_summary.setText("Todos os PDFs e fotos estão íntegros.")
        else:
            self._integrity_summary.setText(
                f"{len(report.problemas)} problema(s) encontrado(s); o projeto continua "
                "abrindo e as ações necessárias estão listadas abaixo."
            )

    def localizar_pdf(self) -> None:
        project_id = self._project_id()
        document_value = self._pdf.currentData()
        if project_id is None or document_value is None:
            self._warn("Selecione o PDF que precisa ser localizado")
            return
        name, _filter = QFileDialog.getOpenFileName(
            self, "Localizar PDF correspondente", "", "Documentos PDF (*.pdf)"
        )
        if not name:
            return
        if (
            self._action(
                lambda: self._service.localizar_pdf(
                    project_id, UUID(str(document_value)), Path(name)
                )
            )
            is None
        ):
            return
        self.abrir_projeto(project_id)
        self.verificar_integridade()
        self.data_changed.emit()
        self.status_changed.emit("PDF localizado e hash conferido")

    def exportar_projeto(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            self._warn("Selecione um projeto para exportar")
            return
        name, _filter = QFileDialog.getSaveFileName(
            self, "Exportar projeto portátil", "projeto.zphproj", "Projeto Zeny (*.zphproj)"
        )
        if not name:
            return
        result = self._action(
            lambda: self._service.exportar_projeto(
                project_id, _with_suffix(Path(name), ".zphproj"), progresso=self._show_progress
            )
        )
        self._reset_progress()
        if result is not None:
            self.status_changed.emit(f"Projeto exportado para {result.caminho}")

    def importar_projeto(self) -> None:
        name, _filter = QFileDialog.getOpenFileName(
            self, "Importar projeto portátil", "", "Projeto Zeny (*.zphproj)"
        )
        if not name:
            return
        result: ResultadoImportacaoProjeto | None
        try:
            result = self._service.importar_projeto(Path(name), progresso=self._show_progress)
        except Exception as error:
            if "confirme explicitamente" not in str(error):
                self._reset_progress()
                self._warn(str(error).strip() or error.__class__.__name__)
                return
            confirmation = QMessageBox.question(
                self,
                "Substituir projeto existente",
                "O pacote possui o mesmo ID de um projeto local. Substituir seus dados e arquivos "
                "pela versão importada?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirmation != QMessageBox.StandardButton.Yes:
                self._reset_progress()
                return
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
        self.status_changed.emit("Projeto importado com IDs, revisões e grafo preservados")

    def criar_backup(self) -> None:
        name, _filter = QFileDialog.getSaveFileName(
            self, "Criar backup completo", "zeny-backup.zphbackup", "Backup Zeny (*.zphbackup)"
        )
        if not name:
            return
        result = self._action(
            lambda: self._service.criar_backup(
                _with_suffix(Path(name), ".zphbackup"), progresso=self._show_progress
            )
        )
        self._reset_progress()
        if result is not None:
            self.status_changed.emit(f"Backup íntegro criado em {result}")

    def restaurar_backup(self) -> None:
        name, _filter = QFileDialog.getOpenFileName(
            self, "Restaurar backup completo", "", "Backup Zeny (*.zphbackup)"
        )
        if not name:
            return
        confirmation = QMessageBox.question(
            self,
            "Restaurar backup",
            "Substituir o banco e os arquivos gerenciados atuais pelo backup selecionado? O estado "
            "atual será preservado temporariamente para reversão se houver falha.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        if (
            self._action(
                lambda: self._service.restaurar_backup(Path(name), progresso=self._show_progress)
            )
            is None
        ):
            self._reset_progress()
            return
        self._reset_progress()
        self.atualizar_projetos()
        self.data_restored.emit()
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

    def _selected_ids(self) -> tuple[UUID, UUID] | None:
        project_id = self._project_id()
        element = self._element.currentData()
        if project_id is None or element is None:
            return None
        return project_id, UUID(str(element))

    def _selected_photo(self) -> FotoElemento | None:
        item = self._photos_list.currentItem()
        if item is None:
            return None
        identifier = item.data(Qt.ItemDataRole.UserRole)
        return self._photos.get(UUID(str(identifier))) if identifier is not None else None

    def _select_element(self, element_id: UUID) -> None:
        index = self._element.findData(str(element_id))
        if index >= 0:
            self._element.setCurrentIndex(index)

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
