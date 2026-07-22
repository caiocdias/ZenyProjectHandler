"""Painel operacional para usar o aplicativo como um MVP completo."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import TypeVar
from uuid import UUID

from PySide6.QtCore import QObject, QSettings, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
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

from zeny_project_handler.application.errors import FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import (
    ResultadoFluxoMvp,
    ServicoFluxoMvp,
    SessaoProjetoMvp,
)
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise

from .pdf_viewer import PdfViewerWidget
from .review_panel import ReviewPanelWidget

T = TypeVar("T")


class _PipelineWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str, bool)
    finished = Signal()

    def __init__(self, service: ServicoFluxoMvp, project_id: UUID, cancellation: Event) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.executar_pipeline(
                self._project_id,
                progresso=self.progress.emit,
                cancelado=self._cancellation.is_set,
            )
        except FluxoMvpCanceladoError as error:
            self.failed.emit(str(error), True)
        except Exception as error:  # UI boundary: never expose a traceback to the user.
            message = str(error).strip() or error.__class__.__name__
            self.failed.emit(message, False)
        else:
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
        self._pending_paths: tuple[Path, ...] = ()
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
        select = QPushButton("Selecionar PDF(s)")
        select.setObjectName("mvpSelectPdfsButton")
        select.clicked.connect(self.selecionar_pdfs)
        document_layout.addWidget(select)
        self._selection = QLabel("Nenhum arquivo selecionado")
        self._selection.setObjectName("mvpSelectedPdfsLabel")
        self._selection.setWordWrap(True)
        document_layout.addWidget(self._selection)
        self._import = QPushButton("Unir arquivos em um só projeto")
        self._import.setObjectName("mvpMergePdfsButton")
        self._import.setEnabled(False)
        self._import.clicked.connect(self.importar_pdfs)
        document_layout.addWidget(self._import)
        self._documents = QListWidget()
        self._documents.setObjectName("mvpDocumentList")
        self._documents.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        document_layout.addWidget(self._documents)
        remove_documents = QPushButton("Remover PDF(s) selecionado(s)")
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
        names, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Selecionar folhas do projeto em PDF",
            "",
            "Documentos PDF (*.pdf)",
        )
        self._pending_paths = tuple(Path(name) for name in names)
        if not self._pending_paths:
            return
        self._selection.setText("\n".join(path.name for path in self._pending_paths))
        self._import.setText(
            "Adicionar PDF ao projeto"
            if len(self._pending_paths) == 1
            else "Unir arquivos em um só projeto"
        )
        self._import.setEnabled(self._session is not None)

    def importar_pdfs(self) -> None:
        session = self._session
        if session is None or not self._pending_paths:
            self._warn("Abra um projeto e selecione ao menos um PDF")
            return
        result = self._action(
            lambda: self._service.importar_pdfs(session.projeto.id, self._pending_paths)
        )
        if result is None:
            return
        count = len(result.inspecoes)
        self._pending_paths = ()
        self._selection.setText("Nenhum arquivo selecionado")
        self._import.setEnabled(False)
        self._activate(self._service.abrir_projeto(session.projeto.id))
        self.status_changed.emit(f"{count} PDF(s) adicionados ao projeto na ordem selecionada")

    def remover_pdfs(self) -> None:
        session = self._session
        selected_items = self._documents.selectedItems()
        if session is None or not selected_items:
            self._warn("Selecione no projeto ao menos um PDF para remover")
            return
        if self.processando:
            self._warn("Cancele ou aguarde a análise antes de remover PDFs")
            return
        document_ids = tuple(
            UUID(str(item.data(Qt.ItemDataRole.UserRole))) for item in selected_items
        )
        names = ", ".join(item.text().split(" · ", maxsplit=1)[0] for item in selected_items)
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
        worker = _PipelineWorker(self._service, session.projeto.id, self._cancellation)
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
        latest_execution = (
            result.execucoes_interpretacao[-1] if result.execucoes_interpretacao else None
        )
        self._review_panel.abrir_projeto(result.projeto_id, latest_execution)
        if result.propostas_geradas:
            message = (
                f"Análise concluída: {result.propostas_geradas} proposta(s) prontas para revisão"
            )
        else:
            message = (
                "Análise concluída sem propostas; use a criação manual na revisão se necessário"
            )
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
            "4. No painel Revisão humana, aceite, ajuste ou rejeite propostas.\n"
            "5. Crie ao menos um elemento manual.\n"
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
            if not self._viewer.carregar_projeto(source_paths):
                self._viewer.limpar()
                self.status_changed.emit(
                    "Projeto aberto, mas uma origem PDF precisa ser localizada ou restaurada"
                )
            else:
                self._viewer.ir_para_folha(saved_page)
        else:
            self._viewer.limpar()
        self._documents.clear()
        for document in session.projeto.documentos:
            item = QListWidgetItem(f"{document.nome_arquivo} · {len(document.paginas)} folha(s)")
            item.setData(Qt.ItemDataRole.UserRole, str(document.id))
            self._documents.addItem(item)
        self._import.setEnabled(bool(self._pending_paths))
        self._show_summary(session)

    def _show_summary(self, session: SessaoProjetoMvp) -> None:
        summary = session.resumo
        extraction = _state_label(summary.ultima_extracao)
        interpretation = _state_label(summary.ultima_interpretacao)
        self._summary.setText(
            f"{summary.documentos} PDF(s), {summary.paginas} folha(s)\n"
            f"Extração: {extraction} · Interpretação: {interpretation}\n"
            f"Pendentes: {summary.propostas_pendentes} · Decisões: {summary.decisoes_realizadas}"
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
        self._documents.clear()
        self._summary.setText("Crie ou abra um projeto para começar")


def _state_label(state: EstadoExecucaoAnalise | None) -> str:
    return state.value if state is not None else "não executada"
