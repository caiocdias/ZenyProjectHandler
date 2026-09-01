"""Painel Projeto cliente orientado exclusivamente ao gateway HTTP e DTOs."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from functools import partial
from pathlib import Path
from threading import Event
from typing import Any, TypeVar
from uuid import UUID, uuid4

from PySide6.QtCore import QObject, QRegularExpression, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QKeyEvent, QKeySequence, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
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

from zeny_project_handler_contracts.enums import (
    AnalysisExecutionState,
    JobStatus,
    UploadState,
)
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.jobs import JobResultResponse
from zeny_project_handler_contracts.projects import ProjectDetailDto
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse

from .project_gateway import ProjectGateway, ProjectGatewayError

T = TypeVar("T")
_NUMERO_NS_PATTERN = r"[0-9]{10}"
_NUMERO_NS_SEARCH_PATTERN = r"[0-9]{0,10}"
_SERVICE_CODE_PATTERN = r"[0-9]{4}"
_TERMINAL_JOB_STATES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})


class _AsciiDigitsLineEdit(QLineEdit):
    """Campo numérico simples com atalhos de clipboard previsíveis."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - API Qt
        if event.matches(QKeySequence.StandardKey.Copy):
            selected_digits = "".join(
                character
                for character in self.selectedText()
                if character.isascii() and character.isdigit()
            )
            if selected_digits:
                QApplication.clipboard().setText(selected_digits)
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            pasted_digits = "".join(
                character
                for character in QApplication.clipboard().text()
                if character.isascii() and character.isdigit()
            )
            if pasted_digits:
                self.setText(pasted_digits[: self.maxLength()])
            event.accept()
            return
        super().keyPressEvent(event)


class _JobPollingWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str, bool)
    finished = Signal()

    def __init__(
        self,
        gateway: ProjectGateway,
        job_id: UUID,
        poll_after_ms: int,
        cancellation: Event,
    ) -> None:
        super().__init__()
        self._gateway = gateway
        self._job_id = job_id
        self._poll_seconds = min(0.5, max(0.25, poll_after_ms / 1000))
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        cancellation_sent = False
        try:
            while True:
                if self._cancellation.is_set() and not cancellation_sent:
                    self._gateway.cancel_job(self._job_id)
                    cancellation_sent = True
                status = self._gateway.get_job(self._job_id)
                self.progress.emit(
                    status.progress_percent,
                    status.message or "Acompanhando a execução remota.",
                )
                if status.status in _TERMINAL_JOB_STATES:
                    if status.status is JobStatus.SUCCEEDED:
                        self.completed.emit(self._gateway.get_job_result(self._job_id))
                    elif status.status is JobStatus.CANCELLED:
                        self.failed.emit(status.message or "Análise cancelada.", True)
                    else:
                        error = status.error
                        message = str(error.message if error is not None else status.message)
                        if error is not None:
                            message += f" (correlação {error.correlation_id.root})"
                        self.failed.emit(message, False)
                    return
                self._cancellation.wait(self._poll_seconds)
        except Exception as error:
            self.failed.emit(str(error).strip() or type(error).__name__, False)
        finally:
            self.finished.emit()


class _GlobalOperationPollingWorker(QObject):
    session_received = Signal(object)
    finished = Signal()

    def __init__(self, gateway: ProjectGateway, stopped: Event) -> None:
        super().__init__()
        self._gateway = gateway
        self._stopped = stopped

    @Slot()
    def run(self) -> None:
        try:
            while not self._stopped.is_set():
                with suppress(Exception):
                    self.session_received.emit(self._gateway.session())
                self._stopped.wait(0.4)
        finally:
            self.finished.emit()


class ProjectPanelWidget(QWidget):
    """Execute CRUD, uploads e análise somente por contratos do gateway remoto."""

    status_changed = Signal(str)
    busy_changed = Signal(bool)
    project_opened = Signal(object)
    project_cleared = Signal()

    def __init__(
        self,
        *,
        gateway: ProjectGateway,
        viewer: Any,
        review_panel: Any,
        state_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("projectPanel")
        self._gateway = gateway
        self._viewer = viewer
        self._review_panel = review_panel
        self._settings = QSettings(str(state_path), QSettings.Format.IniFormat)
        self._session: ProjectDetailDto | None = None
        self._service_codes: tuple[str, ...] = ()
        self._service_codes_loaded = False
        self._updating_page_order = False
        self._thread: QThread | None = None
        self._worker: _JobPollingWorker | None = None
        self._cancellation: Event | None = None
        self._job_id: UUID | None = None
        self._server_operation: object | None = None
        self._external_operation: object | None = None
        self._ignore_job_signals = False
        self._global_poll_stop = Event()
        self._global_poll_thread: QThread | None = None
        self._global_poll_worker: _GlobalOperationPollingWorker | None = None
        self._build_ui()
        self._viewer.page_changed.connect(self._remember_page)
        self.atualizar_projetos(restaurar_ultimo=True, mostrar_erro=False)
        self._start_global_polling()

    @property
    def processando(self) -> bool:
        return self._thread is not None

    @property
    def projeto_ativo_id(self) -> UUID | None:
        return self._session.project_id.root if self._session is not None else None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        self._project_box = QGroupBox("Projeto")
        project_layout = QVBoxLayout(self._project_box)
        self._projects = QComboBox()
        self._projects.setObjectName("mvpProjectCombo")
        self._projects.setEditable(True)
        self._projects.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._project_search = _AsciiDigitsLineEdit(self._projects)
        self._project_search.setMaxLength(10)
        self._project_search.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(_NUMERO_NS_SEARCH_PATTERN),
                self._project_search,
            )
        )
        self._project_search.setPlaceholderText("Pesquise a NS")
        self._project_search.setToolTip("Pesquise por até 10 dígitos da NS")
        self._project_search.setAccessibleName("Pesquisar projeto pela NS")
        self._projects.setLineEdit(self._project_search)
        completer = QCompleter(self._projects.model(), self._projects)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._projects.setCompleter(completer)
        project_layout.addWidget(self._projects)
        service_note_label = QLabel("Número da NS")
        service_note_label.setObjectName("mvpProjectServiceNoteLabel")
        project_layout.addWidget(service_note_label)
        self._service_note = _AsciiDigitsLineEdit()
        self._service_note.setObjectName("mvpProjectNameEdit")
        self._service_note.setMaxLength(10)
        self._service_note.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(_NUMERO_NS_PATTERN),
                self._service_note,
            )
        )
        self._service_note.setPlaceholderText("Número da NS")
        self._service_note.setToolTip("Informe os 10 dígitos do número da NS")
        self._service_note.setAccessibleName("Número da NS")
        project_layout.addWidget(self._service_note)
        project_actions = QGridLayout()
        project_actions.setHorizontalSpacing(8)
        project_actions.setVerticalSpacing(8)
        self._create_project = QPushButton("Criar")
        self._create_project.setObjectName("mvpCreateProjectButton")
        self._create_project.clicked.connect(self.criar_projeto)
        project_actions.addWidget(self._create_project, 0, 0)
        self._open_project = QPushButton("Abrir")
        self._open_project.setObjectName("mvpOpenProjectButton")
        self._open_project.clicked.connect(self.abrir_selecionado)
        project_actions.addWidget(self._open_project, 0, 1)
        self._rename_project = QPushButton("Alterar NS")
        self._rename_project.setObjectName("mvpRenameProjectButton")
        self._rename_project.clicked.connect(self.alterar_numero_ns)
        project_actions.addWidget(self._rename_project, 1, 0)
        self._delete_project = QPushButton("Excluir projeto")
        self._delete_project.setObjectName("mvpDeleteProjectButton")
        self._delete_project.setProperty("role", "danger")
        self._delete_project.clicked.connect(self.excluir_projeto)
        project_actions.addWidget(self._delete_project, 1, 1)
        project_layout.addLayout(project_actions)
        layout.addWidget(self._project_box)

        self._service_box = QGroupBox("Serviços do projeto")
        self._service_box.setObjectName("mvpProjectServiceCodesBox")
        self._service_box.setAccessibleName("Serviços do projeto")
        service_layout = QVBoxLayout(self._service_box)
        service_code_label = QLabel("Código do serviço")
        service_code_label.setObjectName("mvpProjectServiceCodeLabel")
        service_layout.addWidget(service_code_label)
        service_entry = QHBoxLayout()
        self._service_code = _AsciiDigitsLineEdit()
        self._service_code.setObjectName("mvpProjectServiceCodeEdit")
        self._service_code.setMaxLength(4)
        self._service_code.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(_SERVICE_CODE_PATTERN),
                self._service_code,
            )
        )
        self._service_code.setPlaceholderText("0000")
        self._service_code.setToolTip("Informe os quatro dígitos do código de serviço")
        self._service_code.setAccessibleName("Código do serviço")
        self._service_code.textChanged.connect(self._update_service_controls)
        service_code_label.setBuddy(self._service_code)
        service_entry.addWidget(self._service_code)
        self._add_service_code = QPushButton("Adicionar")
        self._add_service_code.setObjectName("mvpAddServiceCodeButton")
        self._add_service_code.setAccessibleName("Adicionar código de serviço")
        self._add_service_code.clicked.connect(self.adicionar_codigo_servico)
        service_entry.addWidget(self._add_service_code)
        service_layout.addLayout(service_entry)
        self._service_code_list = QListWidget()
        self._service_code_list.setObjectName("mvpProjectServiceCodeList")
        self._service_code_list.setAccessibleName("Códigos de serviço do projeto")
        self._service_code_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._service_code_list.setMinimumHeight(76)
        self._service_code_list.itemSelectionChanged.connect(self._update_service_controls)
        service_layout.addWidget(self._service_code_list)
        self._remove_service_codes = QPushButton("Remover selecionados")
        self._remove_service_codes.setObjectName("mvpRemoveServiceCodesButton")
        self._remove_service_codes.setAccessibleName("Remover códigos de serviço selecionados")
        self._remove_service_codes.setProperty("role", "danger")
        self._remove_service_codes.clicked.connect(self.remover_codigos_servico)
        service_layout.addWidget(self._remove_service_codes)
        layout.addWidget(self._service_box)

        self._document_box = QGroupBox("Folhas PDF")
        document_layout = QVBoxLayout(self._document_box)
        select = QPushButton("Adicionar PDF(s) ao projeto")
        select.setObjectName("mvpAddPdfsButton")
        select.clicked.connect(self.selecionar_pdfs)
        document_layout.addWidget(select)
        order_help = QLabel(
            "Ordem de leitura: arraste qualquer página ou use os botões abaixo. "
            "O conteúdo enviado é mantido no servidor."
        )
        order_help.setObjectName("mvpPageOrderHelp")
        order_help.setProperty("role", "hint")
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
        remove_documents = QPushButton("Remover selecionados")
        remove_documents.setObjectName("mvpRemovePdfsButton")
        remove_documents.setProperty("role", "danger")
        remove_documents.setToolTip("Remover do projeto os PDFs das páginas selecionadas")
        remove_documents.clicked.connect(self.remover_pdfs)
        document_layout.addWidget(remove_documents)
        layout.addWidget(self._document_box)

        analysis_box = QGroupBox("Análise")
        analysis_layout = QVBoxLayout(analysis_box)
        self._summary = QLabel("Crie ou abra um projeto para começar")
        self._summary.setObjectName("mvpProjectSummaryLabel")
        self._summary.setProperty("role", "summary")
        self._summary.setWordWrap(True)
        analysis_layout.addWidget(self._summary)
        self._progress = QProgressBar()
        self._progress.setObjectName("mvpAnalysisProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        analysis_layout.addWidget(self._progress)
        analysis_actions = QHBoxLayout()
        self._run = QPushButton("Analisar projeto")
        self._run.setObjectName("mvpRunAnalysisButton")
        self._run.setProperty("role", "primary")
        self._run.clicked.connect(self.executar_analise)
        analysis_actions.addWidget(self._run)
        self._cancel = QPushButton("Cancelar")
        self._cancel.setObjectName("mvpCancelAnalysisButton")
        self._cancel.setProperty("role", "danger")
        self._cancel.setEnabled(False)
        self._cancel.clicked.connect(self.cancelar_analise)
        analysis_actions.addWidget(self._cancel)
        analysis_layout.addLayout(analysis_actions)
        layout.addWidget(analysis_box)

        guide = QPushButton("Como usar")
        guide.setObjectName("mvpAcceptanceGuideButton")
        guide.setProperty("role", "quiet")
        guide.clicked.connect(self.exibir_guia_aceite)
        layout.addWidget(guide)
        layout.addStretch(1)
        self._apply_operation_state()

    def atualizar_projetos(
        self,
        *,
        restaurar_ultimo: bool = False,
        mostrar_erro: bool = True,
    ) -> None:
        selected_id = self._selected_project_id()
        if selected_id is None and self._session is not None:
            selected_id = self._session.project_id.root
        selected = str(selected_id) if selected_id is not None else None
        if restaurar_ultimo:
            selected = self._settings.value("last_project_id")
        response = self._action(
            lambda: self._gateway.list_projects(limit=200, offset=0),
            mostrar_erro=mostrar_erro,
        )
        if response is None:
            return
        selected_index = -1
        signals_were_blocked = self._projects.blockSignals(True)
        try:
            self._projects.clear()
            self._projects.addItem("Selecione um projeto", None)
            for summary in response.items:
                self._projects.addItem(summary.service_note, str(summary.project_id.root))
            if selected is not None:
                selected_index = self._projects.findData(str(selected))
            if selected_index >= 0:
                self._projects.setCurrentIndex(selected_index)
            elif self._session is not None and str(self._session.project_id.root) == str(selected):
                self._projects.setCurrentIndex(-1)
                self._projects.setEditText(self._session.service_note)
            else:
                self._clear_project_selection()
        finally:
            self._projects.blockSignals(signals_were_blocked)
        if selected_index >= 0:
            self.abrir_selecionado()

    def criar_projeto(self) -> None:
        numero_ns = self._service_note.text()
        if not self._service_note.hasAcceptableInput():
            self._warn("Informe o número da NS com exatamente 10 dígitos")
            return
        try:
            existing = self._gateway.find_project_by_service_note(numero_ns)
        except Exception as error:
            self._warn(str(error).strip() or type(error).__name__)
            return
        if existing is not None:
            self._offer_open_existing(existing.project.project_id.root)
            return
        self._create_project_once(numero_ns)

    def _create_project_once(self, numero_ns: str) -> None:
        try:
            response = self._gateway.create_project(
                numero_ns,
                idempotency_key=f"project-{uuid4()}",
            )
        except ProjectGatewayError as error:
            if error.code is ErrorCode.PROJECT_ALREADY_EXISTS:
                project_id = _project_id_from_conflict(error)
                if project_id is not None:
                    self._offer_open_existing(project_id)
                    return
            self._warn(str(error).strip() or type(error).__name__)
            return
        except Exception as error:
            self._warn(str(error).strip() or type(error).__name__)
            return
        self._service_note.clear()
        self.atualizar_projetos()
        self._select_and_activate(response.project)
        self.status_changed.emit("Projeto criado e pronto para receber PDFs")

    def abrir_selecionado(self) -> None:
        project_id = self._selected_project_id()
        if project_id is not None:
            self._open_project_id(project_id)
            return
        numero_ns = self._project_search.text().strip()
        if not _is_complete_service_note(numero_ns):
            self._warn("Selecione um projeto ou informe a NS com exatamente 10 dígitos")
            return
        try:
            response = self._gateway.find_project_by_service_note(numero_ns)
        except Exception as error:
            self._warn(str(error).strip() or type(error).__name__)
            return
        if response is None:
            self._offer_create_missing(numero_ns)
            return
        self._select_and_activate(response.project)

    def _open_project_id(self, project_id: UUID) -> None:
        response = self._action(lambda: self._gateway.get_project(project_id))
        if response is not None:
            self._select_and_activate(response.project)

    def _offer_create_missing(self, numero_ns: str) -> None:
        confirmation = QMessageBox.question(
            self,
            "Nota de Serviço não cadastrada",
            "A Nota de Serviço não existe. Deseja criar o projeto da nota?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation == QMessageBox.StandardButton.Yes:
            self._create_project_once(numero_ns)
            return
        self._reset_to_initial_state()

    def _offer_open_existing(self, project_id: UUID) -> None:
        confirmation = QMessageBox.question(
            self,
            "Projeto já cadastrado",
            "Já existe um projeto para a Nota de Serviço informada. Deseja abrir esse projeto?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation == QMessageBox.StandardButton.Yes:
            self._open_project_id(project_id)
            return
        self._reset_to_initial_state()

    def alterar_numero_ns(self) -> None:
        session = self._session
        numero_ns = self._service_note.text()
        if session is None or not self._service_note.hasAcceptableInput():
            self._warn("Selecione o projeto e informe o número da NS com exatamente 10 dígitos")
            return
        response = self._action(
            lambda: self._gateway.update_project(
                session.project_id.root,
                numero_ns,
                expected_project_version=session.project_version,
            )
        )
        if response is not None:
            self._service_note.clear()
            self.atualizar_projetos()
            self._select_and_activate(response.project)
            self._review_panel.atualizar_projetos()

    def adicionar_codigo_servico(self) -> None:
        session = self._session
        code = self._service_code.text()
        if session is None or not self._service_codes_loaded:
            self._warn("Crie ou abra um projeto antes de adicionar serviços")
            return
        if not self._service_code.hasAcceptableInput():
            self._warn("Informe o código de serviço com exatamente quatro dígitos")
            return
        if code in self._service_codes:
            self._warn(f"O código de serviço {code} já está cadastrado no projeto")
            return
        self._replace_service_codes(tuple(sorted((*self._service_codes, code))))

    def remover_codigos_servico(self) -> None:
        if self._session is None or not self._service_codes_loaded:
            self._warn("Crie ou abra um projeto antes de remover serviços")
            return
        selected = {item.text() for item in self._service_code_list.selectedItems()}
        if not selected:
            self._warn("Selecione ao menos um código de serviço para remover")
            return
        self._replace_service_codes(
            tuple(code for code in self._service_codes if code not in selected)
        )

    def _replace_service_codes(self, service_codes: tuple[str, ...]) -> None:
        session = self._session
        if session is None or not self._service_codes_loaded:
            return
        try:
            response = self._gateway.replace_service_codes(
                session.project_id.root,
                service_codes,
                expected_project_version=session.project_version,
            )
        except Exception as error:
            if getattr(error, "code", None) is ErrorCode.STALE_STATE:
                self._warn(
                    "O projeto mudou em outra janela; os serviços mais recentes serão recarregados."
                )
                self._reload_after_service_code_conflict(session.project_id.root)
                return
            self._warn(str(error).strip() or type(error).__name__)
            return
        if self.projeto_ativo_id != response.project_id.root:
            return
        self._session = session.model_copy(update={"project_version": response.project_version})
        self._set_service_codes(response.service_codes)
        self._service_code.clear()
        self.status_changed.emit("Serviços do projeto atualizados")

    def _reload_after_service_code_conflict(self, project_id: UUID) -> None:
        self._clear_service_codes()
        refreshed = self._action(lambda: self._gateway.get_project(project_id))
        if refreshed is not None and self.projeto_ativo_id == project_id:
            self._activate(refreshed.project)

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
            f"Excluir permanentemente o projeto “{session.service_note}”, seu cadastro, "
            "análises, revisões, fotos e arquivos gerenciados no servidor?\n\n"
            "Arquivos já baixados ou mantidos fora do servidor não serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        project_id = session.project_id.root
        result = self._action(lambda: self._gateway.delete_project(project_id))
        if result is None:
            return
        self._settings.beginGroup(f"projects/{project_id}")
        self._settings.remove("")
        self._settings.endGroup()
        self._reset_to_initial_state()
        self.atualizar_projetos()
        self.status_changed.emit(
            f"Projeto excluído no servidor: {result.counts.documents} PDF(s), "
            f"{result.counts.analyses} análise(s) e {result.counts.photos} foto(s)"
        )

    def selecionar_pdfs(self) -> None:
        session = self._session
        if session is None:
            self._warn("Crie ou abra um projeto antes de adicionar PDFs")
            return
        if self.processando:
            self._warn("Aguarde ou cancele a análise antes de adicionar PDFs")
            return
        names, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Selecionar folhas do projeto em PDF",
            "",
            "Documentos PDF (*.pdf)",
        )
        paths = tuple(Path(name) for name in names)
        if paths:
            self._importar_selecao(session.project_id.root, paths)

    def _importar_selecao(self, projeto_id: UUID, caminhos: tuple[Path, ...]) -> None:
        importados = 0
        cancelados = 0
        tentativas_esgotadas = 0
        falhas = 0
        detalhes_falha: list[str] = []
        for caminho in caminhos:
            try:
                uploaded = self._gateway.upload_document(
                    projeto_id,
                    caminho,
                    idempotency_key=f"upload-{uuid4()}",
                )
                if uploaded.state is UploadState.PASSWORD_REQUIRED:
                    outcome = self._unlock_upload(
                        uploaded.upload_id.root,
                        uploaded.display_name,
                    )
                    if outcome == "cancelled":
                        cancelados += 1
                        continue
                    if outcome == "exhausted":
                        tentativas_esgotadas += 1
                        continue
                elif uploaded.state is not UploadState.IMPORTED:
                    raise RuntimeError("O servidor não concluiu a importação do PDF")
            except Exception as error:
                falhas += 1
                detalhes_falha.append(
                    f"{caminho.name}: {str(error).strip() or type(error).__name__}"
                )
            else:
                importados += 1
        if importados:
            refreshed = self._action(lambda: self._gateway.get_project(projeto_id))
            if refreshed is not None:
                self._activate(refreshed.project)
        resumo = (
            f"Importação concluída: {importados} adicionado(s), {cancelados} cancelado(s), "
            f"{tentativas_esgotadas} sem senha válida e {falhas} com erro"
        )
        if detalhes_falha:
            resumo += "\n" + "\n".join(detalhes_falha)
        self.status_changed.emit(resumo)
        if cancelados or tentativas_esgotadas or falhas:
            QMessageBox.information(self, "Resumo da importação", resumo)

    def _unlock_upload(self, upload_id: UUID, display_name: str) -> str:
        for attempt in range(1, 4):
            password, accepted = QInputDialog.getText(
                self,
                "Senha do PDF",
                f"{display_name}\nTentativa {attempt} de 3",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return "cancelled"
            try:
                self._gateway.unlock_upload(upload_id, password)
            except ProjectGatewayError as error:
                if error.code.value == "PDF_PASSWORD_INVALID":
                    remaining = (error.details or {}).get("password_attempts_remaining", 0)
                    remaining_count = int(remaining) if isinstance(remaining, (int, str)) else 0
                    if remaining_count > 0:
                        continue
                    return "exhausted"
                raise
            finally:
                password = ""
            return "imported"
        return "exhausted"

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
        current_ids = tuple(page.page_id.root for page in session.pages)
        if ordered_ids == current_ids:
            self._update_order_controls()
            return
        updated = self._action(
            lambda: self._gateway.replace_page_order(
                session.project_id.root,
                ordered_ids,
                expected_project_version=session.project_version,
            )
        )
        if updated is None:
            self._activate(session)
            return
        refreshed = self._action(lambda: self._gateway.get_project(session.project_id.root))
        if refreshed is None:
            return
        self._activate(refreshed.project)
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
        document_by_id = {item.document_id.root: item for item in session.documents}
        names = ", ".join(document_by_id[item].file.display_name for item in document_ids)
        confirmation = QMessageBox.question(
            self,
            "Remover PDFs do projeto",
            f"Remover do projeto: {names}?\n\nAnálises, propostas, decisões, elementos e "
            "fotos dependentes também poderão ser removidos no servidor. Cópias mantidas fora "
            "do servidor serão preservadas.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirmation != QMessageBox.StandardButton.Yes:
            return
        removed = 0
        for document_id in document_ids:
            result = self._action(
                partial(
                    self._gateway.remove_document,
                    session.project_id.root,
                    document_id,
                )
            )
            if result is None:
                break
            removed += 1
        refreshed = self._action(lambda: self._gateway.get_project(session.project_id.root))
        if refreshed is None:
            return
        self._activate(refreshed.project)
        self._review_panel.limpar()
        self._review_panel.atualizar_projetos()
        self.status_changed.emit(f"{removed} PDF(s) e dados dependentes removidos no servidor")

    def executar_analise(self) -> None:
        session = self._session
        if session is None:
            self._warn("Crie ou abra um projeto antes de executar a análise")
            return
        if not session.documents:
            self._warn("Importe ao menos um PDF antes de executar a análise")
            return
        if self.processando:
            return
        accepted = self._action(
            lambda: self._gateway.create_analysis_job(
                session.project_id.root,
                expected_project_version=session.project_version,
                force_reanalysis=False,
                idempotency_key=f"analysis-{uuid4()}",
            )
        )
        if accepted is None:
            return
        self._cancellation = Event()
        self._job_id = accepted.job_id.root
        self._ignore_job_signals = False
        thread = QThread(self)
        worker = _JobPollingWorker(
            self._gateway,
            accepted.job_id.root,
            accepted.poll_after_ms,
            self._cancellation,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._update_progress)
        worker.completed.connect(self._pipeline_completed)
        worker.failed.connect(self._pipeline_failed)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.destroyed.connect(self._pipeline_finished)
        self._thread = thread
        self._worker = worker
        self._run.setText("Análise em andamento…")
        self._pages.setDragEnabled(False)
        self._update_order_controls()
        self._summary.setText("Execução remota ativa: preparando documentos")
        self._apply_operation_state()
        self.busy_changed.emit(True)
        thread.start()

    def cancelar_analise(self) -> None:
        if self._cancellation is not None:
            self._cancellation.set()
            self._cancel.setEnabled(False)
            self.status_changed.emit("Cancelamento solicitado; aguardando um ponto seguro")

    def cancelar_e_aguardar(self, timeout_ms: int) -> bool:
        thread = self._thread
        if thread is None or not thread.isRunning():
            return True
        self.cancelar_analise()
        finished = thread.wait(max(0, timeout_ms))
        if finished:
            self._ignore_job_signals = True
        return finished

    def shutdown_polling(self, timeout_ms: int = 1_000) -> bool:
        self._global_poll_stop.set()
        thread = self._global_poll_thread
        if thread is None or not thread.isRunning():
            return True
        finished = thread.wait(max(0, timeout_ms))
        if finished:
            self._global_poll_thread = None
            self._global_poll_worker = None
        return finished

    def restart_polling(self) -> None:
        """Retome a observação global usando o gateway reconectável já atualizado."""
        thread = self._global_poll_thread
        if thread is not None and thread.isRunning():
            return
        self._global_poll_stop = Event()
        self._start_global_polling()

    def set_global_operation(self, operation: object | None) -> None:
        self._external_operation = operation
        self._apply_operation_state()

    @Slot(int, str)
    def _update_progress(self, percent: int, message: str) -> None:
        if self._ignore_job_signals:
            return
        self._progress.setValue(max(self._progress.value(), percent))
        self._summary.setText(f"Execução remota ativa: {message}")
        self.status_changed.emit(message)

    @Slot(object)
    def _pipeline_completed(self, result: object) -> None:
        if self._ignore_job_signals or not isinstance(result, JobResultResponse):
            return
        payload = result.result or {}
        raw_project_id = payload.get("project_id")
        project_id = UUID(str(raw_project_id)) if raw_project_id is not None else None
        if project_id is None:
            return
        refreshed = self._action(lambda: self._gateway.get_project(project_id))
        if refreshed is None:
            return
        self._activate(refreshed.project)
        self._review_panel.abrir_projeto(project_id)
        raw_count = payload.get("proposals_generated", 0)
        count = int(raw_count) if isinstance(raw_count, (int, str)) else 0
        message = (
            f"Análise concluída: {count} identificação(ões) incorporada(s) ao projeto"
            if count
            else "Análise concluída sem novas identificações"
        )
        self.status_changed.emit(message)
        self._summary.setText(message)

    @Slot(str, bool)
    def _pipeline_failed(self, message: str, cancelled: bool) -> None:
        if self._ignore_job_signals:
            return
        title = "Análise cancelada" if cancelled else "Análise não concluída"
        self._summary.setText(message)
        self.status_changed.emit(message)
        if not cancelled:
            QMessageBox.warning(self, title, message)

    @Slot(object)
    def _pipeline_finished(self, _destroyed_thread: object | None = None) -> None:
        self._thread = None
        self._worker = None
        self._cancellation = None
        self._job_id = None
        self._run.setText("Analisar novamente")
        self._pages.setDragEnabled(True)
        self._apply_operation_state()
        self.busy_changed.emit(False)
        self._update_order_controls()
        session = self._session
        if session is not None:
            response = self._action(lambda: self._gateway.get_project(session.project_id.root))
            if response is not None:
                self._session = response.project
                self._show_summary(self._session)

    @Slot(object)
    def _session_received(self, response: object) -> None:
        if not isinstance(response, SessionCapabilitiesResponse):
            return
        operation = response.global_operation
        self._server_operation = operation
        if operation is not None and not self.processando:
            self._progress.setValue(max(self._progress.value(), operation.progress_percent))
            self._summary.setText(
                f"Operação global no servidor: {operation.message or operation.kind.value}"
            )
        self._apply_operation_state()

    def _apply_operation_state(self) -> None:
        blocked = (
            self._server_operation is not None
            or self._external_operation is not None
            or self.processando
        )
        has_session = self._session is not None
        self._project_box.setEnabled(not blocked)
        self._rename_project.setEnabled(has_session and not blocked)
        self._delete_project.setEnabled(has_session and not blocked)
        self._service_box.setEnabled(
            has_session and self._service_codes_loaded and not blocked
        )
        self._document_box.setEnabled(has_session and not blocked)
        self._run.setEnabled(has_session and not blocked)
        self._cancel.setEnabled(self.processando and self._cancellation is not None)
        self._update_service_controls()

    def _start_global_polling(self) -> None:
        thread = QThread(self)
        worker = _GlobalOperationPollingWorker(self._gateway, self._global_poll_stop)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.session_received.connect(self._session_received)
        worker.finished.connect(thread.quit, Qt.ConnectionType.DirectConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.destroyed.connect(self._global_polling_destroyed)
        self._global_poll_thread = thread
        self._global_poll_worker = worker
        thread.start()

    @Slot()
    def _global_polling_destroyed(self) -> None:
        self._global_poll_thread = None
        self._global_poll_worker = None

    def exibir_guia_aceite(self) -> None:
        QMessageBox.information(
            self,
            "Como usar o projeto",
            "1. Crie ou abra um projeto no servidor.\n"
            "2. Cadastre os códigos de serviço com quatro dígitos.\n"
            "3. Selecione um ou vários PDFs para upload.\n"
            "4. Execute a análise remota e acompanhe o progresso.\n"
            "5. Confira os vínculos no painel Resultados.\n"
            "6. Clique nos itens para conferir os sublinhados no PDF.\n"
            "7. Reinicie cliente e servidor e confira se o trabalho foi preservado.",
        )

    def _select_and_activate(self, session: ProjectDetailDto) -> None:
        index = self._projects.findData(str(session.project_id.root))
        if index >= 0:
            self._projects.setCurrentIndex(index)
        else:
            self._projects.setCurrentIndex(-1)
            self._projects.setEditText(session.service_note)
        self._activate(session)

    def _selected_project_id(self) -> UUID | None:
        index = self._projects.currentIndex()
        if index < 0:
            return None
        value = self._projects.itemData(index)
        if value is None or self._projects.currentText().strip() != self._projects.itemText(index):
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _clear_project_selection(self) -> None:
        signals_were_blocked = self._projects.blockSignals(True)
        try:
            self._projects.setCurrentIndex(0 if self._projects.count() else -1)
            self._projects.clearEditText()
        finally:
            self._projects.blockSignals(signals_were_blocked)

    def _activate(self, session: ProjectDetailDto) -> None:
        self._session = session
        self._load_service_codes(session.project_id.root)
        project_id = str(session.project_id.root)
        self._settings.setValue("last_project_id", project_id)
        self._settings.sync()
        if session.pages:
            saved_page = int(str(self._settings.value(f"projects/{project_id}/page", 1)))
            if self._viewer.carregar_projeto_remoto(session.project_id.root):
                self._viewer.ir_para_folha(saved_page)
            else:
                self._viewer.limpar()
                self.status_changed.emit(
                    "Projeto aberto, mas o visualizador remoto não pôde carregar as folhas"
                )
        else:
            self._viewer.limpar()
        self._updating_page_order = True
        self._pages.clear()
        documents = {item.document_id.root: item for item in session.documents}
        for position, page in enumerate(session.pages, start=1):
            document = documents[page.document_id.root]
            item = QListWidgetItem(
                f"{position}. {document.file.display_name} · página {page.source_page_number}"
            )
            item.setData(Qt.ItemDataRole.UserRole, str(page.page_id.root))
            item.setData(Qt.ItemDataRole.UserRole + 1, str(page.document_id.root))
            self._pages.addItem(item)
        self._updating_page_order = False
        self._update_order_controls()
        self._show_summary(session)
        self.project_opened.emit(session.project_id.root)

    def _load_service_codes(self, project_id: UUID) -> None:
        self._clear_service_codes()
        response = self._action(lambda: self._gateway.get_service_codes(project_id))
        if response is None or self.projeto_ativo_id != project_id:
            return
        session = self._session
        if session is None:
            return
        self._session = session.model_copy(update={"project_version": response.project_version})
        self._service_codes_loaded = True
        self._set_service_codes(response.service_codes)
        self._apply_operation_state()

    def _set_service_codes(self, service_codes: tuple[str, ...]) -> None:
        self._service_codes = service_codes
        self._service_code_list.clear()
        self._service_code_list.addItems(service_codes)
        self._update_service_controls()

    def _clear_service_codes(self) -> None:
        self._service_codes = ()
        self._service_codes_loaded = False
        self._service_code.clear()
        self._service_code_list.clear()
        self._apply_operation_state()

    def _update_service_controls(self) -> None:
        enabled = self._service_box.isEnabled()
        self._add_service_code.setEnabled(enabled)
        self._remove_service_codes.setEnabled(
            enabled and bool(self._service_code_list.selectedItems())
        )

    def _show_summary(self, session: ProjectDetailDto) -> None:
        analysis = session.analysis
        extraction = _state_label(analysis.last_extraction)
        interpretation = _state_label(analysis.last_interpretation)
        self._summary.setText(
            f"{len(session.documents)} PDF(s), {len(session.pages)} folha(s)\n"
            f"Extração: {extraction} · Interpretação: {interpretation}\n"
            f"Identificações automáticas: {analysis.completed_decisions} · "
            f"Exceções: {analysis.pending_proposals}"
        )

    def _remember_page(self, _page_id: str) -> None:
        if self._session is None:
            return
        self._settings.setValue(
            f"projects/{self._session.project_id.root}/page",
            self._viewer.folha_atual,
        )
        self._settings.sync()

    def _warn(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Ação não concluída", message)

    def _action(self, action: Callable[[], T], *, mostrar_erro: bool = True) -> T | None:
        try:
            return action()
        except Exception as error:
            message = str(error).strip() or type(error).__name__
            if mostrar_erro:
                self._warn(message)
            else:
                self.status_changed.emit(message)
            return None

    def _show_empty_state(self) -> None:
        self._clear_service_codes()
        self._updating_page_order = True
        self._pages.clear()
        self._updating_page_order = False
        self._update_order_controls()
        self._progress.setValue(0)
        self._run.setText("Analisar projeto")
        self._summary.setText("Crie ou abra um projeto para começar")
        self._apply_operation_state()

    def _reset_to_initial_state(self) -> None:
        self._session = None
        self._service_note.clear()
        self._clear_project_selection()
        self._settings.remove("last_project_id")
        self._settings.sync()
        self._show_empty_state()
        self.project_cleared.emit()
        self.status_changed.emit("Nenhum projeto ativo")


def _state_label(state: AnalysisExecutionState | None) -> str:
    if state is None:
        return "não executada"
    return {
        AnalysisExecutionState.STARTED: "INICIADA",
        AnalysisExecutionState.SUCCEEDED: "CONCLUÍDA",
        AnalysisExecutionState.FAILED: "FALHOU",
        AnalysisExecutionState.CANCELLED: "CANCELADA",
    }[state]


def _is_complete_service_note(value: str) -> bool:
    return len(value) == 10 and value.isascii() and value.isdigit()


def _project_id_from_conflict(error: ProjectGatewayError) -> UUID | None:
    raw_project_id = (error.details or {}).get("project_id")
    try:
        return UUID(str(raw_project_id)) if raw_project_id is not None else None
    except (TypeError, ValueError):
        return None
