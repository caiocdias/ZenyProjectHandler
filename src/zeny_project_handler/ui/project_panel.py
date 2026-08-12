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

from zeny_project_handler.adapters.pdf.errors import PdfError
from zeny_project_handler.application.errors import ApplicationError, FluxoMvpCanceladoError
from zeny_project_handler.application.mvp_workflow import (
    ResultadoFluxoMvp,
    ServicoFluxoMvp,
    SessaoProjetoMvp,
)
from zeny_project_handler.application.operation_coordinator import TipoOperacao
from zeny_project_handler.application.pdf_credentials import IdentidadeCredencialPdf
from zeny_project_handler.application.pdf_import import ResultadoImportacaoPdfs
from zeny_project_handler.domain.enums import EstadoExecucaoAnalise
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.logging_config import operation_logger
from zeny_project_handler.ports.pdf import LeitorPdfPort, ReferenciaFontePdf

from .pdf_credentials import EstadoResolucaoCredencialPdf, ResolvedorCredenciaisPdf
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
        senhas_documentos: dict[UUID, str] | None = None,
    ) -> None:
        super().__init__()
        self._service = service
        self._project_id = project_id
        self._cancellation = cancellation
        self._correlation_id = correlation_id
        self._senhas_documentos = dict(senhas_documentos or {})

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
                    senhas_documentos=self._senhas_documentos,
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
                self._senhas_documentos.clear()
                self.finished.emit()


class ProjectPanelWidget(QWidget):
    """Conecte criação, importação, análise e revisão em um único fluxo visível."""

    status_changed = Signal(str)
    busy_changed = Signal(bool)
    project_opened = Signal(object)

    def __init__(
        self,
        *,
        service: ServicoFluxoMvp,
        viewer: PdfViewerWidget,
        review_panel: ReviewPanelWidget,
        leitor_pdf: LeitorPdfPort,
        resolvedor_credenciais: ResolvedorCredenciaisPdf,
        state_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectPanel")
        self._service = service
        self._viewer = viewer
        self._review_panel = review_panel
        self._pdf_reader = leitor_pdf
        self._credential_resolver = resolvedor_credenciais
        self._settings = QSettings(str(state_path), QSettings.Format.IniFormat)
        self._session: SessaoProjetoMvp | None = None
        self._updating_page_order = False
        self._thread: QThread | None = None
        self._worker: _PipelineWorker | None = None
        self._cancellation: Event | None = None
        self._global_operation: TipoOperacao | None = None
        self._ignore_pipeline_signals = False
        self._build_ui()
        self._viewer.page_changed.connect(self._remember_page)
        self.atualizar_projetos(restaurar_ultimo=True)

    @property
    def processando(self) -> bool:
        return self._thread is not None

    @property
    def projeto_ativo_id(self) -> UUID | None:
        return self._session.projeto.id if self._session is not None else None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._project_box = QGroupBox("Projeto")
        project_layout = QVBoxLayout(self._project_box)
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
        layout.addWidget(self._project_box)

        self._document_box = QGroupBox("Folhas PDF")
        document_layout = QVBoxLayout(self._document_box)
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
        layout.addWidget(self._document_box)

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
        self._apply_operation_state()

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
            f"Excluir permanentemente o projeto “{session.projeto.nome}”, seu cadastro, "
            "análises, revisões, fotos e cópias de arquivos mantidas na pasta gerenciada?\n\n"
            "Os arquivos PDF originais externos permanecem no local de origem e não serão "
            "apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        project_id = session.projeto.id
        result = self._action(lambda: self._service.excluir_projeto(project_id))
        if result is None:
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
        if result.limpeza_pendente:
            self.status_changed.emit(
                "Projeto excluído e PDFs originais externos preservados; a limpeza da pasta "
                "gerenciada ficou registrada para nova tentativa"
            )
        else:
            self.status_changed.emit(
                "Projeto e sua pasta gerenciada excluídos; PDFs originais externos preservados"
            )

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
            self._importar_selecao(session.projeto.id, paths)

    def _importar_selecao(self, projeto_id: UUID, caminhos: tuple[Path, ...]) -> None:
        importados = 0
        cancelados = 0
        tentativas_esgotadas = 0
        falhas = 0
        for caminho in caminhos:
            try:
                result = self._credential_resolver.executar(
                    parent=self,
                    caminho=caminho,
                    acao=self._acao_importacao_pdf(projeto_id, caminho),
                )
            except (ApplicationError, DomainValidationError, PdfError, ValueError):
                falhas += 1
                continue
            except Exception:
                falhas += 1
                continue
            if result.estado is EstadoResolucaoCredencialPdf.CANCELADA:
                cancelados += 1
            elif result.estado is EstadoResolucaoCredencialPdf.TENTATIVAS_ESGOTADAS:
                tentativas_esgotadas += 1
            else:
                importados += 1
        if importados:
            self._activate(self._service.abrir_projeto(projeto_id))
        resumo = (
            f"Importação concluída: {importados} adicionado(s), {cancelados} cancelado(s), "
            f"{tentativas_esgotadas} sem senha válida e {falhas} com erro"
        )
        self.status_changed.emit(resumo)
        if cancelados or tentativas_esgotadas or falhas:
            QMessageBox.information(self, "Resumo da importação", resumo)

    def _acao_importacao_pdf(
        self,
        projeto_id: UUID,
        caminho: Path,
    ) -> Callable[[str | None], ResultadoImportacaoPdfs]:
        def execute(senha: str | None) -> ResultadoImportacaoPdfs:
            return self._service.importar_pdfs(projeto_id, (caminho,), senha=senha)

        return execute

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
            "dependentes dessas folhas também serão removidos. Fotos gerenciadas desses "
            "elementos serão apagadas somente quando nenhuma referência viva usar o mesmo "
            "conteúdo. Os arquivos PDF originais externos serão preservados.",
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
        message = (
            f"{len(result.documentos_removidos)} PDF(s), {result.execucoes_removidas} "
            f"execução(ões), {result.elementos_removidos} elemento(s) e "
            f"{result.arquivos_gerenciados_removidos} foto(s) sem referência removidos; "
            "PDFs originais externos preservados"
        )
        if result.limpeza_pendente:
            message += "; limpeza restante registrada para nova tentativa"
        self.status_changed.emit(message)

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
        senhas_documentos = self._preflight_credenciais_analise(session)
        if senhas_documentos is None:
            return
        self._cancellation = Event()
        self._ignore_pipeline_signals = False
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
            senhas_documentos,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.completed.connect(self._pipeline_completed)
        worker.failed.connect(self._pipeline_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(self._pipeline_finished)
        self._thread = thread
        self._worker = worker
        self._run.setText("Análise em andamento…")
        self._pages.setDragEnabled(False)
        self._update_order_controls()
        self._summary.setText("Execução ativa: preparando documentos")
        self._apply_operation_state()
        self.busy_changed.emit(True)
        thread.start()

    def _preflight_credenciais_analise(
        self,
        session: SessaoProjetoMvp,
    ) -> dict[UUID, str] | None:
        fontes = {fonte.documento_id: fonte for fonte in session.fontes_pdf}
        senhas: dict[UUID, str] = {}
        for validados, documento in enumerate(session.projeto.documentos):
            fonte = fontes.get(documento.id)
            if fonte is None:
                self._warn(
                    "Análise não iniciada: uma origem PDF não está disponível para o preflight"
                )
                return None

            try:
                result = self._credential_resolver.executar(
                    parent=self,
                    caminho=fonte.caminho_canonico,
                    identidade_sugerida=IdentidadeCredencialPdf.da_fonte(fonte),
                    acao=self._acao_preflight_analise(
                        documento.id,
                        documento.sha256,
                        fonte,
                    ),
                )
            except (PdfError, ValueError) as error:
                self._warn(f"Análise não iniciada no preflight: {error}")
                return None
            if result.estado is not EstadoResolucaoCredencialPdf.SUCESSO:
                motivo = (
                    "solicitação de senha cancelada"
                    if result.estado is EstadoResolucaoCredencialPdf.CANCELADA
                    else "limite de 3 tentativas de senha atingido"
                )
                self._warn(
                    f"Análise não iniciada: {motivo} em {documento.nome_arquivo}; "
                    f"{validados} PDF(s) já haviam sido validados"
                )
                return None
            if result.senha is not None:
                senhas[documento.id] = result.senha
        return senhas

    def _acao_preflight_analise(
        self,
        documento_id: UUID,
        sha256_esperado: str,
        fonte: ReferenciaFontePdf,
    ) -> Callable[[str | None], bool]:
        def execute(senha: str | None) -> bool:
            return self._validar_credencial_analise(
                documento_id,
                sha256_esperado,
                fonte,
                senha,
            )

        return execute

    def _validar_credencial_analise(
        self,
        documento_id: UUID,
        sha256_esperado: str,
        fonte: ReferenciaFontePdf,
        senha: str | None,
    ) -> bool:
        sessao = self._pdf_reader.abrir_sessao(
            fonte.caminho_canonico,
            senha=senha,
            documento_id=documento_id,
            sha256_esperado=sha256_esperado,
        )
        sessao.fechar()
        return True

    def cancelar_analise(self) -> None:
        if self._cancellation is not None:
            self._cancellation.set()
            self._cancel.setEnabled(False)
            self.status_changed.emit("Cancelamento solicitado; aguardando um ponto seguro")

    def cancelar_e_aguardar(self, timeout_ms: int) -> bool:
        """Cancele cooperativamente e aguarde sem finalizar a thread à força."""
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        self.cancelar_analise()
        finished = thread.wait(max(0, timeout_ms))
        if finished:
            self._ignore_pipeline_signals = True
        return finished

    def set_global_operation(self, operation: TipoOperacao | None) -> None:
        self._global_operation = operation
        self._apply_operation_state()

    @Slot(int, int, str)
    def _update_progress(self, current: int, total: int, message: str) -> None:
        if self._ignore_pipeline_signals:
            return
        self._progress.setRange(0, max(1, total))
        self._progress.setValue(current)
        self._summary.setText(f"Execução ativa: {message}")
        self.status_changed.emit(message)

    @Slot(object)
    def _pipeline_completed(self, result: object) -> None:
        if self._ignore_pipeline_signals:
            return
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
        if self._ignore_pipeline_signals:
            return
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
        self._run.setText("Retomar / executar análise")
        self._pages.setDragEnabled(True)
        self._apply_operation_state()
        self.busy_changed.emit(False)
        self._update_order_controls()
        if self._session is not None:
            self._session = self._service.abrir_projeto(self._session.projeto.id)
            self._show_summary(self._session)

    def _apply_operation_state(self) -> None:
        blocked = self._global_operation is not None or self.processando
        self._project_box.setEnabled(not blocked)
        self._document_box.setEnabled(not blocked)
        self._run.setEnabled(not blocked)
        self._cancel.setEnabled(self.processando)

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
                fontes=session.fontes_pdf,
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
        self.project_opened.emit(session.projeto.id)

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
