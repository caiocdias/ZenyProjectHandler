"""Painel operacional para usar o aplicativo como um MVP completo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import QObject, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.application.errors import ApplicationError, FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import (
    ResultadoFluxoMvp,
    ServicoFluxoMvp,
    SessaoProjetoMvp,
)
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import operation_logger

from .pdf_viewer import PdfViewerWidget
from .review_panel import ReviewPanelWidget

T = TypeVar("T")


class _PipelineWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str, bool)
    finished = Signal()

    def __init__(
        self,
        service: ServicoFluxoMvp,
        project_id: UUID,
        cancellation: Event,
        correlation_id: str,
    ) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._cancellation = cancellation
        self._correlation_id = correlation_id

    @Slot()
    def run(self) -> None:
        observation = operation_logger(
            "qt.worker.analysis_pipeline",
            correlation_id=self._correlation_id,
            project_id=self._project_id,
        )
        with observation.context():
            observation.started()
            try:
                result = self._service.executar_pipeline(
                    self._project_id,
                    progresso=self.progress.emit,
                    cancelado=self._cancellation.is_set,
                )
            except FluxoMvpCanceladoError as error:
                observation.cancelled(error_code=error.__class__.__name__)
                self.failed.emit(str(error), True)
            except (ApplicationError, DomainValidationError, ValueError) as error:
                observation.failed(error, expected=True)
                message = str(error).strip() or error.__class__.__name__
                self.failed.emit(message, False)
            except Exception as error:  # UI boundary: never expose a traceback to the user.
                observation.failed(error, expected=False)
                message = str(error).strip() or error.__class__.__name__
                self.failed.emit(message, False)
            else:
                observation.succeeded()
                self.completed.emit(result)
            finally:
                self.finished.emit()


class ProjectPanelWidget(QWidget):
    """Conecte criação, importação, análise e revisão em um único fluxo visível."""

    status_changed = Signal(str)

    def __init__(
        self,
        *,
        service: ServicoFluxoMvp,
        viewer: PdfViewerWidget,
        review_panel: ReviewPanelWidget,
        state_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectPanel")
        self._service = service
        self._viewer = viewer
        self._review_panel = review_panel
        self._settings = QSettings(str(state_path), QSettings.Format.IniFormat)
        self._session: SessaoProjetoMvp | None = None
        self._updating_page_order = False
        self._thread: QThread | None = None
        self._worker: _PipelineWorker | None = None
        self._cancellation: Event | None = None
        self._build_ui()
        self._viewer.page_changed.connect(self._remember_page)
        self.atualizar_projetos(restaurar_ultimo=True)

    @property
    def processando(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        project_box = QGroupBox("Projeto")
        project_layout = QVBoxLayout(project_box)
        self._projects = QComboBox()
        self._projects.setObjectName("mvpProjectCombo")
        project_layout.addWidget(self._projects)
        self._name = QLineEdit()
        self._name.setObjectName("mvpProjectNameEdit")
        self._name.setPlaceholderText("Nome do projeto")
        project_layout.addWidget(self._name)
        project_actions = QHBoxLayout()
        create = QPushButton("Criar")
        create.setObjectName("mvpCreateProjectButton")
        create.clicked.connect(self.criar_projeto)
        project_actions.addWidget(create)
        open_button = QPushButton("Abrir")
        open_button.setObjectName("mvpOpenProjectButton")
        open_button.clicked.connect(self.abrir_selecionado)
        project_actions.addWidget(open_button)
        rename = QPushButton("Renomear")
        rename.setObjectName("mvpRenameProjectButton")
        rename.clicked.connect(self.renomear_projeto)
        project_actions.addWidget(rename)
        delete_project = QPushButton("Excluir projeto")
        delete_project.setObjectName("mvpDeleteProjectButton")
        delete_project.clicked.connect(self.excluir_projeto)
        project_actions.addWidget(delete_project)
        project_layout.addLayout(project_actions)
        layout.addWidget(project_box)

        document_box = QGroupBox("Folhas PDF")
        document_layout = QVBoxLayout(document_box)
        select = QPushButton("Adicionar PDF(s) ao projeto")
        select.setObjectName("mvpAddPdfsButton")
        select.clicked.connect(self.selecionar_pdfs)
        document_layout.addWidget(select)
        order_help = QLabel(
            "Ordem de leitura: arraste qualquer página ou use os botões abaixo. "
            "Os PDFs originais não são modificados."
        )
        order_help.setObjectName("mvpPageOrderHelp")
        order_help.setWordWrap(True)
        document_layout.addWidget(order_help)
        self._pages = QListWidget()
        self._pages.setObjectName("mvpPageOrderList")
        self._pages.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._pages.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._pages.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._pages.model().rowsMoved.connect(self._page_order_changed)
        self._pages.itemSelectionChanged.connect(self._update_order_controls)
        document_layout.addWidget(self._pages)
        order_actions = QHBoxLayout()
        self._move_up = QPushButton("Subir")
        self._move_up.setObjectName("mvpMovePageUpButton")
        self._move_up.clicked.connect(lambda: self._move_selected_page(-1))
        order_actions.addWidget(self._move_up)
        self._move_down = QPushButton("Descer")
        self._move_down.setObjectName("mvpMovePageDownButton")
        self._move_down.clicked.connect(lambda: self._move_selected_page(1))
        order_actions.addWidget(self._move_down)
        document_layout.addLayout(order_actions)
        remove_documents = QPushButton("Remover PDF(s) das páginas selecionadas")
        remove_documents.setObjectName("mvpRemovePdfsButton")
        remove_documents.clicked.connect(self.remover_pdfs)
        document_layout.addWidget(remove_documents)
        layout.addWidget(document_box)

        analysis_box = QGroupBox("Análise")
        analysis_layout = QVBoxLayout(analysis_box)
        self._summary = QLabel("Crie ou abra um projeto para começar")
        self._summary.setObjectName("mvpProjectSummaryLabel")
        self._summary.setWordWrap(True)
        analysis_layout.addWidget(self._summary)
        self._progress = QProgressBar()
        self._progress.setObjectName("mvpAnalysisProgress")
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        analysis_layout.addWidget(self._progress)
        analysis_actions = QHBoxLayout()
        self._run = QPushButton("Executar análise completa")
        self._run.setObjectName("mvpRunAnalysisButton")
        self._run.clicked.connect(self.executar_analise)
        analysis_actions.addWidget(self._run)
        self._cancel = QPushButton("Cancelar")
        self._cancel.setObjectName("mvpCancelAnalysisButton")
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self.cancelar_analise)
        analysis_actions.addWidget(self._cancel)
        analysis_layout.addLayout(analysis_actions)
        layout.addWidget(analysis_box)

        guide = QPushButton("Como validar este MVP")
        guide.setObjectName("mvpAcceptanceGuideButton")
        guide.clicked.connect(self.exibir_guia_aceite)
        layout.addWidget(guide)
        layout.addStretch(1)

    def atualizar_projetos(self, *, restaurar_ultimo: bool = False) -> None:
        selected = self._projects.currentData()
        if restaurar_ultimo:
            selected = self._settings.value("last_project_id")
        self._projects.clear()
        self._projects.addItem("Selecione um projeto", None)
        for summary in self._service.listar_projetos():
            self._projects.addItem(summary.nome, str(summary.projeto_id))
        if selected is not None:
            index = self._projects.findData(str(selected))
            if index >= 0:
                self._projects.setCurrentIndex(index)
                self.abrir_selecionado()

    def criar_projeto(self) -> None:
        name = self._name.text().strip()
        if not name:
            self._warn("Informe um nome para criar o projeto")
            return
        session = self._action(lambda: self._service.criar_projeto(name))
        if session is None:
            return
        self._name.clear()
        self.atualizar_projetos()
        self._select_and_activate(session)
        self.status_changed.emit("Projeto criado e pronto para receber PDFs")

    def abrir_selecionado(self) -> None:
        value = self._projects.currentData()
        if value is None:
            return
        session = self._action(lambda: self._service.abrir_projeto(UUID(str(value))))
        if session is not None:
            self._activate(session)

    def renomear_projeto(self) -> None:
        value = self._projects.currentData()
        name = self._name.text().strip()
        if value is None or not name:
            self._warn("Selecione o projeto e informe o novo nome")
            return
        session = self._action(lambda: self._service.renomear_projeto(UUID(str(value)), name))
        if session is not None:
            self._name.clear()
            self.atualizar_projetos()
            self._select_and_activate(session)
            self._review_panel.atualizar_projetos()

    def excluir_projeto(self) -> None:
        session = self._session
        if session is None:
            self._warn("Selecione um projeto para excluir")
            return
        if self.processando:
            self._warn("Cancele ou aguarde a análise antes de excluir o projeto")
            return
        confirmation = QMessageBox.question(
            self,
            "Excluir projeto",
            f"Excluir permanentemente o projeto “{session.projeto.nome}” e todos os seus "
            "dados locais?\n\nOs arquivos PDF originais no disco não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        project_id = session.projeto.id
        if self._action(lambda: self._service.excluir_projeto(project_id)) is None:
            return
        self._session = None
        self._settings.remove("last_project_id")
        self._settings.beginGroup(f"projects/{project_id}")
        self._settings.remove("")
        self._settings.endGroup()
        self._settings.sync()
        self._viewer.limpar()
        self._review_panel.limpar()
        self.atualizar_projetos()
        self._show_empty_state()
        self.status_changed.emit("Projeto excluído; os PDFs originais foram preservados")

    def selecionar_pdfs(self) -> None:
        session = self._session
        if session is None:
            self._warn("Crie ou abra um projeto antes de adicionar PDFs")
            return
        if self.processando:
            self._warn("Aguarde ou cancele a análise antes de adicionar PDFs")
            return
        observation = operation_logger(
            "pdf.import.selection",
            project_id=session.projeto.id,
        )
        with observation.context():
            observation.started()
            names, _selected_filter = QFileDialog.getOpenFileNames(
                self,
                "Selecionar folhas do projeto em PDF",
                "",
                "Documentos PDF (*.pdf)",
            )
            paths = tuple(Path(name) for name in names)
            if not paths:
                observation.cancelled()
                return
            observation.succeeded(item_count=len(paths))
            result = self._action(lambda: self._service.importar_pdfs(session.projeto.id, paths))
            if result is None:
                return
            count = len(result.inspecoes)
            self._activate(self._service.abrir_projeto(session.projeto.id))
            self.status_changed.emit(
                f"{count} PDF(s) adicionados; ajuste abaixo a ordem das páginas"
            )

    def _move_selected_page(self, offset: int) -> None:
        if self.processando:
            self._warn("Aguarde ou cancele a análise antes de alterar a ordem das páginas")
            return
        selected = self._pages.selectedItems()
        if len(selected) != 1:
            self._warn("Selecione uma única página para alterar sua posição")
            return
        row = self._pages.row(selected[0])
        destination = row + offset
        if destination < 0 or destination >= self._pages.count():
            return
        self._updating_page_order = True
        item = self._pages.takeItem(row)
        self._pages.insertItem(destination, item)
        self._pages.setCurrentItem(item)
        self._updating_page_order = False
        self._persist_page_order()

    def _page_order_changed(self, *_args: object) -> None:
        if not self._updating_page_order:
            QTimer.singleShot(0, self._persist_page_order)

    def _persist_page_order(self) -> None:
        session = self._session
        if session is None or self._updating_page_order:
            return
        if self.processando:
            self._warn("Aguarde ou cancele a análise antes de alterar a ordem das páginas")
            self._activate(session)
            return
        ordered_ids = tuple(
            UUID(str(self._pages.item(row).data(Qt.ItemDataRole.UserRole)))
            for row in range(self._pages.count())
        )
        current_ids = session.projeto.ordem_leitura_paginas
        if ordered_ids == current_ids:
            self._update_order_controls()
            return
        updated = self._action(
            lambda: self._service.reordenar_paginas(session.projeto.id, ordered_ids)
        )
        if updated is None:
            self._activate(session)
            return
        self._activate(updated)
        self.status_changed.emit("Ordem de leitura do projeto atualizada")

    def _update_order_controls(self) -> None:
        selected = self._pages.selectedItems()
        row = self._pages.row(selected[0]) if len(selected) == 1 else -1
        enabled = not self.processando and row >= 0
        self._move_up.setEnabled(enabled and row > 0)
        self._move_down.setEnabled(enabled and row < self._pages.count() - 1)

    def remover_pdfs(self) -> None:
        session = self._session
        selected_items = self._pages.selectedItems()
        if session is None or not selected_items:
            self._warn("Selecione no projeto ao menos um PDF para remover")
            return
        if self.processando:
            self._warn("Cancele ou aguarde a análise antes de remover PDFs")
            return
        document_ids = tuple(
            dict.fromkeys(
                UUID(str(item.data(Qt.ItemDataRole.UserRole + 1))) for item in selected_items
            )
        )
        document_by_id = {document.id: document for document in session.projeto.documentos}
        names = ", ".join(document_by_id[item].nome_arquivo for item in document_ids)
        confirmation = QMessageBox.question(
            self,
            "Remover PDFs do projeto",
            f"Remover do projeto: {names}?\n\nAnálises, propostas, decisões e elementos "
            "dependentes dessas folhas também serão removidos. Os arquivos originais no disco "
            "serão preservados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        result = self._action(
            lambda: self._service.remover_documentos(session.projeto.id, document_ids)
        )
        if result is None:
            return
        self._activate(result.sessao)
        self._review_panel.limpar()
        self._review_panel.atualizar_projetos()
        self.status_changed.emit(
            f"{len(result.documentos_removidos)} PDF(s), {result.execucoes_removidas} "
            f"execução(ões) e {result.elementos_removidos} elemento(s) removidos do projeto"
        )

    def executar_analise(self) -> None:
        session = self._session
        if session is None:
            self._warn("Crie ou abra um projeto antes de executar a análise")
            return
        if not session.projeto.documentos:
            self._warn("Importe ao menos um PDF antes de executar a análise")
            return
        if self.processando:
            return
        self._cancellation = Event()
        thread = QThread(self)
        worker_observation = operation_logger(
            "qt.worker.analysis_pipeline",
            project_id=session.projeto.id,
        )
        worker = _PipelineWorker(
            self._service,
            session.projeto.id,
            self._cancellation,
            worker_observation.correlation_id,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.completed.connect(self._pipeline_completed)
        worker.failed.connect(self._pipeline_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._pipeline_finished)
        self._thread = thread
        self._worker = worker
        self._run.setEnabled(False)
        self._run.setText("Análise em andamento…")
        self._cancel.setEnabled(True)
        self._pages.setDragEnabled(False)
        self._update_order_controls()
        self._summary.setText("Execução ativa: preparando documentos")
        thread.start()

    def cancelar_analise(self) -> None:
        if self._cancellation is not None:
            self._cancellation.set()
            self._cancel.setEnabled(False)
            self.status_changed.emit("Cancelamento solicitado; aguardando um ponto seguro")

    @Slot(int, int, str)
    def _update_progress(self, current: int, total: int, message: str) -> None:
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(current)
        self._summary.setText(f"Execução ativa: {message}")
        self.status_changed.emit(message)

    @Slot(object)
    def _pipeline_completed(self, result: object) -> None:
        if not isinstance(result, ResultadoFluxoMvp):
            return
        self._activate(self._service.abrir_projeto(result.projeto_id))
        self._review_panel.abrir_projeto(result.projeto_id)
        if result.propostas_geradas:
            message = (
                f"Análise concluída: {result.propostas_geradas} identificação(ões) "
                "incorporada(s) ao projeto"
            )
        else:
            message = "Análise concluída sem novas identificações"
        self.status_changed.emit(message)
        self._summary.setText(message)

    @Slot(str, bool)
    def _pipeline_failed(self, message: str, cancelled: bool) -> None:
        title = "Análise cancelada" if cancelled else "Análise não concluída"
        self._summary.setText(message)
        self.status_changed.emit(message)
        if not cancelled:
            QMessageBox.warning(self, title, message)

    @Slot()
    def _pipeline_finished(self) -> None:
        thread = self._thread
        if thread is not None:
            thread.deleteLater()
        if self._worker is not None:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None
        self._cancellation = None
        self._run.setEnabled(True)
        self._run.setText("Retomar / executar análise")
        self._cancel.setEnabled(False)
        self._pages.setDragEnabled(True)
        self._update_order_controls()
        if self._session is not None:
            self._session = self._service.abrir_projeto(self._session.projeto.id)
            self._show_summary(self._session)

    def exibir_guia_aceite(self) -> None:
        QMessageBox.information(
            self,
            "Roteiro de aceite do MVP",
            "1. Crie ou abra um projeto.\n"
            "2. Selecione um ou vários PDFs e adicione-os ao projeto.\n"
            "3. Execute a análise e acompanhe o progresso.\n"
            "4. Confira os vínculos no painel Resultados da análise.\n"
            "5. Clique nos itens para conferir os sublinhados no PDF.\n"
            "6. Feche e reabra o aplicativo e confira se o trabalho foi preservado.",
        )

    def _select_and_activate(self, session: SessaoProjetoMvp) -> None:
        index = self._projects.findData(str(session.projeto.id))
        if index >= 0:
            self._projects.setCurrentIndex(index)
        self._activate(session)

    def _activate(self, session: SessaoProjetoMvp) -> None:
        self._session = session
        project_id = str(session.projeto.id)
        self._settings.setValue("last_project_id", project_id)
        self._settings.sync()
        source_paths = tuple(source.caminho_canonico for source in session.fontes_pdf)
        if source_paths:
            saved_page = int(str(self._settings.value(f"projects/{project_id}/page", 1)))
            if not self._viewer.carregar_projeto(
                source_paths,
                documentos=session.projeto.documentos,
                ordem_paginas=session.projeto.ordem_leitura_paginas,
            ):
                self._viewer.limpar()
                self.status_changed.emit(
                    "Projeto aberto, mas uma origem PDF precisa ser localizada ou restaurada"
                )
            else:
                self._viewer.ir_para_folha(saved_page)
        else:
            self._viewer.limpar()
        self._updating_page_order = True
        self._pages.clear()
        page_by_id = {
            page.id: (document, page)
            for document in session.projeto.documentos
            for page in document.paginas
        }
        for position, page_id in enumerate(session.projeto.ordem_leitura_paginas, start=1):
            document, page = page_by_id[page_id]
            item = QListWidgetItem(f"{position}. {document.nome_arquivo} · página {page.numero}")
            item.setData(Qt.ItemDataRole.UserRole, str(page.id))
            item.setData(Qt.ItemDataRole.UserRole + 1, str(document.id))
            self._pages.addItem(item)
        self._updating_page_order = False
        self._update_order_controls()
        self._show_summary(session)

    def _show_summary(self, session: SessaoProjetoMvp) -> None:
        summary = session.resumo
        extraction = _state_label(summary.ultima_extracao)
        interpretation = _state_label(summary.ultima_interpretacao)
        self._summary.setText(
            f"{summary.documentos} PDF(s), {summary.paginas} folha(s)\n"
            f"Extração: {extraction} · Interpretação: {interpretation}\n"
            f"Identificações automáticas: {summary.decisoes_realizadas} · "
            f"Exceções: {summary.propostas_pendentes}"
        )

    def _remember_page(self, _page_id: str) -> None:
        if self._session is None:
            return
        self._settings.setValue(
            f"projects/{self._session.projeto.id}/page",
            self._viewer.folha_atual,
        )
        self._settings.sync()

    def _warn(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Ação não concluída", message)

    def _action(self, action: Callable[[], T]) -> T | None:
        try:
            return action()
        except Exception as error:  # UI boundary: convert expected failures into guidance.
            self._warn(str(error).strip() or error.__class__.__name__)
            return None

    def _show_empty_state(self) -> None:
        self._updating_page_order = True
        self._pages.clear()
        self._updating_page_order = False
        self._update_order_controls()
        self._summary.setText("Crie ou abra um projeto para começar")


def _state_label(state: EstadoExecucaoAnalise | None) -> str:
    return state.value if state is not None else "não executada"
