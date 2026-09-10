# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
from dataclasses import replace
from functools import partial
from pathlib import Path
from threading import Event
from typing import cast
from uuid import UUID

import pymupdf
import pytest
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTreeWidget,
)
from pytestqt.qtbot import QtBot

from tests.conftest import ApplicationFactory
from tests.market_fakes import FakeVerificadorAcoesConcluidas
from tests.pdf_fixtures import create_action_requirements_pdf, create_golden_pdf
from tests.remote_gateways import DirectProjectGateway
from zeny_project_handler.adapters.analysis import PyMuPdfDocumentAnalyzer, TesseractCliOcr
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.adapters.persistence import (
    SqlAlchemyUnitOfWork,
    create_sqlite_engine,
)
from zeny_project_handler.config import DATABASE_FILE_NAME
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.market import DescricaoAcao
from zeny_project_handler.domain.project_metadata import MetadadosProjeto
from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.project_gateway import ProjectGatewayError
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_contracts.base import ComplianceExecutionId
from zeny_project_handler_contracts.compliance import ComplianceExecutionResponse
from zeny_project_handler_contracts.enums import ComplianceStatus
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.projects import (
    ProjectDetailResponse,
    ProjectServiceCodesResponse,
    ProjectSummaryListResponse,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
]


@pytest.fixture(autouse=True)
def _accept_creation_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )


def _catalog_pdf(path: Path) -> Path:
    code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    document = pymupdf.open()
    try:
        first = document.new_page(width=240, height=160)
        first.insert_text((20, 25), "P1")
        first.insert_text((20, 40), code)
        second = document.new_page(width=240, height=160)
        second.insert_text((20, 40), "SEGUNDA FOLHA")
        document.save(path)
    finally:
        document.close()
    return path


def _application_log(*data_directories: Path) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for data_directory in data_directories:
        for file_name in ("client.jsonl", "application.jsonl"):
            log_path = data_directory / "logs" / file_name
            if not log_path.exists():
                continue
            for line in log_path.read_text(encoding="utf-8").splitlines():
                decoded = json.loads(line)
                assert isinstance(decoded, dict)
                payloads.append(cast(dict[str, object], decoded))
    return tuple(payloads)


def test_search_debounce_discards_delayed_response_and_preserves_input(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "delay")
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    gateway = panel._gateway
    first = gateway.create_project("0000000111", idempotency_key="delay-first")
    second = gateway.create_project("0000000222", idempotency_key="delay-second")
    responses = {note: gateway.search_projects(note) for note in ("111", "222")}
    entered, release = Event(), Event()
    calls: list[str] = []
    threads: list[bool] = []

    def search(query: str, *, limit: int, offset: int) -> ProjectSummaryListResponse:
        assert (limit, offset) == (200, 0)
        calls.append(query)
        threads.append(QThread.currentThread() != app.thread())
        if query == "111":
            entered.set()
            assert release.wait(5)
        return responses[query]

    monkeypatch.setattr(gateway, "search_projects", search)
    panel._select_and_activate(first.project)
    panel._project_search.setText("1")
    panel._project_search.setText("11")
    panel._project_search.setText("111")
    assert calls == []
    assert panel._search_timer.interval() == 300
    assert "Aguardando" in panel._search_status.text()
    qtbot.waitUntil(entered.is_set)
    assert "Pesquisando" in panel._search_status.text()
    old_thread = panel._search_thread
    assert old_thread is not None
    old_generation = old_thread.generation
    try:
        panel._project_search.setText("222")
        panel._project_search.setCursorPosition(1)
        app.processEvents()
        assert calls == ["111"]
        assert panel.projeto_ativo_id == first.project.project_id.root
        # Uma entrega já enfileirada também precisa passar pela verificação de geração.
        panel._search_received(old_generation, "111", responses["111"])
        assert panel._project_search.text() == "222"
        assert "Aguardando" in panel._search_status.text()
    finally:
        release.set()
    qtbot.waitUntil(lambda: calls == ["111", "222"] and panel._search_thread is None)
    assert threads == [True, True]
    assert panel._project_search.text() == "222"
    assert panel._project_search.cursorPosition() == 1
    assert panel._projects.count() == 1
    assert panel._projects.itemData(0) == str(second.project.project_id.root)
    assert panel._projects.currentData() is None  # Nenhum primeiro resultado implícito.
    assert panel.projeto_ativo_id == first.project.project_id.root
    assert gateway.list_projects().page.total == 2


@pytest.mark.parametrize("close", [False, True])
def test_search_response_is_discarded_after_reconnection_or_close(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
    close: bool,
) -> None:
    app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "context")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    response = panel._gateway.list_projects()
    entered, release = Event(), Event()

    def delayed(query: str, *, limit: int, offset: int) -> ProjectSummaryListResponse:
        entered.set()
        assert release.wait(5)
        return response

    monkeypatch.setattr(panel._gateway, "search_projects", delayed)
    panel._project_search.setText("123")
    qtbot.waitUntil(entered.is_set)
    worker = panel._search_thread
    assert worker is not None
    generation = worker.generation
    try:
        if close:
            window.close()
        else:
            window.set_connection_available(False, "Teste de desconexão")
            window.set_connection_available(True, "Teste de reconexão")
        status = panel._search_status.text()
        panel._search_received(generation, "123", response)
        assert panel._search_status.text() == status
        assert panel.projeto_ativo_id is None
    finally:
        release.set()
        assert worker.wait(2000)
    app.processEvents()
    if not close:
        qtbot.waitUntil(lambda: "Nenhuma correspondência" in panel._search_status.text())
    else:
        assert panel._search_stopped
        assert not panel._search_timer.isActive()
        assert panel._search_thread is None


@pytest.mark.parametrize(
    "code,status",
    [
        (ErrorCode.RESOURCE_NOT_FOUND, 404),
        (ErrorCode.AUTHENTICATION_FAILED, 401),
        (ErrorCode.VALIDATION_ERROR, 422),
        (ErrorCode.INTERNAL_ERROR, 500),
        (ErrorCode.INTEGRITY_ERROR, 409),
    ],
)
def test_search_error_and_exact_error_never_authorize_creation(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
    code: ErrorCode,
    status: int,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "errors")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    calls: list[str] = []
    warnings: list[str] = []

    def fail(*_args: object, **_kwargs: object) -> ProjectSummaryListResponse:
        raise ProjectGatewayError(code, "Falha sintética", status_code=status)

    monkeypatch.setattr(panel._gateway, "search_projects", fail)
    monkeypatch.setattr(panel._gateway, "find_project_by_service_note", fail)
    monkeypatch.setattr(panel._gateway, "create_project", lambda *a, **k: calls.append("POST"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: calls.append("pergunta"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(str(a[-1])))
    panel._project_search.setText("0000000007")
    qtbot.waitUntil(lambda: "Pesquisa indisponível" in panel._search_status.text())
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert calls == []
    assert warnings == ["Falha sintética"]
    assert panel.projeto_ativo_id is None


def test_search_timeout_allows_exact_open_but_global_operation_blocks_the_action(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "timeout")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    existing = panel._gateway.create_project("0000000007", idempotency_key="timeout-existing")
    calls: list[str] = []

    def fail(*args: object, **kwargs: object) -> ProjectSummaryListResponse:
        raise TimeoutError("Servidor lento")

    def find(note: str) -> ProjectDetailResponse:
        calls.append(note)
        return existing

    monkeypatch.setattr(panel._gateway, "search_projects", fail)
    monkeypatch.setattr(panel._gateway, "find_project_by_service_note", find)
    monkeypatch.setattr(
        panel._gateway, "create_project", lambda *a, **k: pytest.fail("POST indevido")
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("Pergunta indevida"))
    panel._project_search.setText(existing.project.service_note)
    qtbot.waitUntil(lambda: "Pesquisa indisponível" in panel._search_status.text())
    panel.set_global_operation(object())
    panel.abrir_selecionado()
    assert calls == []
    assert not panel._open_project.isEnabled()
    panel.set_global_operation(None)
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert calls == [existing.project.service_note]
    assert panel.projeto_ativo_id == existing.project.project_id.root


def test_empty_suggestions_still_require_exact_resolution_and_repeated_enter_is_one_post(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "repeat")
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    assert panel.findChild(QLineEdit, "mvpProjectNameEdit") is None
    assert panel.findChild(QPushButton, "mvpCreateProjectButton") is None
    gateway = panel._gateway
    real_find, real_create = gateway.find_project_by_service_note, gateway.create_project
    calls: list[str] = []

    def find(note: str) -> ProjectDetailResponse | None:
        calls.append(f"GET {note}")
        return real_find(note)

    def create(note: str, *, idempotency_key: str) -> ProjectDetailResponse:
        calls.append(f"POST {note}")
        panel.abrir_selecionado()
        qtbot.keyClick(panel._project_search, Qt.Key.Key_Return)
        return real_create(note, idempotency_key=idempotency_key)

    def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        assert "0000000007" in str(args[2])
        assert args[-1] == QMessageBox.StandardButton.No
        calls.append("confirmação")
        panel.abrir_selecionado()
        qtbot.keyClick(panel._project_search, Qt.Key.Key_Return)
        qtbot.mouseClick(panel._open_project, Qt.MouseButton.LeftButton)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(gateway, "find_project_by_service_note", find)
    monkeypatch.setattr(gateway, "create_project", create)
    monkeypatch.setattr(QMessageBox, "question", confirm)
    panel._project_search.setText("0000000007")
    qtbot.waitUntil(lambda: "Nenhuma correspondência" in panel._search_status.text())
    assert calls == []
    qtbot.keyClick(panel._project_search, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert calls == ["GET 0000000007", "confirmação", "POST 0000000007"]
    assert panel._session is not None and panel._session.service_note == "0000000007"
    assert gateway.list_projects().page.total == 1


@pytest.mark.parametrize("invalidate", ["text", "connection", "operation", "close"])
def test_creation_confirmation_cannot_outlive_its_intent(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
    invalidate: str,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "intent")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    calls: list[str] = []

    def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        if invalidate == "text":
            panel._project_search.setText("0000000008")
            panel._project_search.setText("0000000007")
        elif invalidate == "connection":
            panel.shutdown_polling()
            panel.restart_polling()
        elif invalidate == "operation":
            panel.set_global_operation(object())
        else:
            window.close()
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    monkeypatch.setattr(panel._gateway, "create_project", lambda *a, **k: calls.append("POST"))
    panel._project_search.setText("0000000007")
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert calls == []
    assert panel.projeto_ativo_id is None


@pytest.mark.parametrize("resolution", ["found", "missing", "ambiguous"])
def test_conflict_without_safe_id_only_retries_exact_read(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
    resolution: str,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "conflict-resolution")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    existing = panel._gateway.create_project("0000000007", idempotency_key="winner")
    calls: list[str] = []
    warnings: list[str] = []

    def find(note: str) -> ProjectDetailResponse | None:
        calls.append("GET")
        if len(calls) == 1 or resolution == "missing":
            return None
        if resolution == "ambiguous":
            raise ProjectGatewayError(ErrorCode.INTEGRITY_ERROR, "NS ambígua", status_code=409)
        return existing

    def create(note: str, *, idempotency_key: str) -> ProjectDetailResponse:
        calls.append("POST")
        raise ProjectGatewayError(
            ErrorCode.PROJECT_ALREADY_EXISTS,
            "Conflito",
            status_code=409,
            details={"project_id": "inválido"},
        )

    monkeypatch.setattr(panel._gateway, "find_project_by_service_note", find)
    monkeypatch.setattr(panel._gateway, "create_project", create)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: warnings.append(str(a[-1])))
    panel._project_search.setText(existing.project.service_note)
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert calls == ["GET", "POST", "GET"]
    if resolution == "found":
        assert panel.projeto_ativo_id == existing.project.project_id.root
        assert not warnings
    else:
        assert panel.projeto_ativo_id is None
        assert warnings


def test_rename_dialog_preserves_session_on_cancel_and_uses_current_version(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "rename")
    )
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    first = panel._gateway.create_project("0000000007", idempotency_key="rename-first")
    second = panel._gateway.create_project("0000000008", idempotency_key="rename-second")
    panel._select_and_activate(first.project)
    # A leitura do mercado atualiza o DTO da sessão antes de testar o cancelamento.
    qtbot.waitUntil(lambda: not panel.market._pending)
    original_session = panel._session
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(str(args[-1])))

    def interact(note: str, accept: bool) -> None:
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        assert dialog.objectName() == "mvpRenameServiceNoteDialog"
        editor = dialog.findChild(QLineEdit, "mvpRenameServiceNoteEdit")
        buttons = dialog.findChild(QDialogButtonBox)
        assert editor is not None and buttons is not None
        assert panel._session is not None and editor.text() == panel._session.service_note
        editor.setText("123")
        assert not buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
        editor.setText(note)
        qtbot.keyClick(dialog, Qt.Key.Key_Return if accept else Qt.Key.Key_Escape)

    QTimer.singleShot(0, lambda: interact("0000000009", False))
    panel.alterar_numero_ns()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert panel._session is original_session
    assert panel._settings.value("last_project_id") == str(first.project.project_id.root)
    assert panel._project_search.text() == "0000000007"
    assert panel._gateway.get_project(first.project.project_id.root) == first

    QTimer.singleShot(0, lambda: interact("0000000009", True))
    panel.alterar_numero_ns()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert panel._session is not None
    assert panel._session.service_note == "0000000009"
    assert panel._session.project_version == first.project.project_version + 1
    assert panel._projects.currentData() == str(first.project.project_id.root)

    QTimer.singleShot(0, lambda: interact(second.project.service_note, True))
    panel.alterar_numero_ns()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert warnings
    assert panel._session.service_note == "0000000009"
    assert panel._gateway.get_project(second.project.project_id.root) == second


def test_user_can_reorder_project_pdfs_and_reopen_in_reading_order(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    first = _catalog_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create = panel.findChild(QPushButton, "mvpOpenProjectButton")
    assert name is not None and create is not None
    assert name.inputMask() == ""
    assert name.maxLength() == 10
    assert name.validator() is not None
    assert name.placeholderText() == "Pesquisar ou cadastrar NS"
    name.setText("0000000082")
    assert name.hasAcceptableInput()
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert project_combo is not None
    project_id = project_combo.currentData()

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: (
            [str(first), str(second)],
            "Documentos PDF (*.pdf)",
        ),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    pages = panel.findChild(QListWidget, "mvpPageOrderList")
    move_down = panel.findChild(QPushButton, "mvpMovePageDownButton")
    assert add_pdfs is not None and pages is not None and move_down is not None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert pages.count() == 3

    pages.setCurrentRow(0)
    qtbot.mouseClick(move_down, Qt.MouseButton.LeftButton)

    assert "folha-01.pdf · página 2" in pages.item(0).text()
    assert "folha-01.pdf · página 1" in pages.item(1).text()

    _reopened_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    assert reopened_combo is not None
    assert reopened_combo.currentData() == project_id
    reopened_pages = reopened_panel.findChild(QListWidget, "mvpPageOrderList")
    assert reopened_pages is not None
    assert "folha-01.pdf · página 2" in reopened_pages.item(0).text()
    assert "folha-01.pdf · página 1" in reopened_pages.item(1).text()


def test_project_service_codes_ui_is_remote_canonical_accessible_and_conflict_safe(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "service-codes", pdf_render_dpi=72)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    panel_layout = panel.layout()
    assert panel_layout is not None
    group_titles: list[str] = []
    for index in range(panel_layout.count()):
        layout_item = panel_layout.itemAt(index)
        if layout_item is None:
            continue
        widget = layout_item.widget()
        if isinstance(widget, QGroupBox):
            group_titles.append(widget.title())
    assert group_titles[:4] == [
        "Projeto",
        "Mercado do projeto",
        "Serviços do projeto",
        "Folhas PDF",
    ]

    service_box = panel.findChild(QGroupBox, "mvpProjectServiceCodesBox")
    service_field = panel.findChild(QLineEdit, "mvpProjectServiceCodeEdit")
    service_list = panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    add_service = panel.findChild(QPushButton, "mvpAddServiceCodeButton")
    remove_services = panel.findChild(QPushButton, "mvpRemoveServiceCodesButton")
    assert service_box is not None
    assert service_field is not None
    assert service_list is not None
    assert add_service is not None
    assert remove_services is not None
    assert not service_box.isEnabled()
    assert service_list.count() == 0
    assert service_box.accessibleName() == "Serviços do projeto"
    assert service_field.accessibleName() == "Código do serviço"
    assert service_list.accessibleName() == "Códigos de serviço do projeto"
    assert add_service.accessibleName() == "Adicionar código de serviço"
    assert remove_services.accessibleName() == "Remover códigos de serviço selecionados"
    assert service_field.inputMask() == ""
    assert service_field.maxLength() == 4
    assert service_field.validator() is not None
    assert service_field.placeholderText() == "0000"

    name = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create = panel.findChild(QPushButton, "mvpOpenProjectButton")
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert name is not None and create is not None and project_combo is not None
    name.setText("0000000701")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    first_project_id = UUID(str(project_combo.currentData()))
    assert service_box.isEnabled()
    initial_version = panel._session.project_version if panel._session is not None else -1

    service_field.setText("007")
    assert not service_field.hasAcceptableInput()
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0
    assert panel._session is not None
    assert panel._session.project_version == initial_version

    service_field.setText("\uff11\uff12\uff13\uff14")
    assert not service_field.hasAcceptableInput()
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0

    clipboard = application.clipboard()
    previous_clipboard_text = clipboard.text()
    try:
        clipboard.setText("Serviço 0007-x")
        qtbot.keyClick(
            service_field,
            Qt.Key.Key_V,
            Qt.KeyboardModifier.ControlModifier,
        )
        assert service_field.text() == "0007"
        assert service_field.hasAcceptableInput()
        service_field.selectAll()
        clipboard.clear()
        qtbot.keyClick(
            service_field,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        )
        assert clipboard.text() == "0007"
    finally:
        clipboard.setText(previous_clipboard_text)

    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["0007"]
    assert panel._session is not None
    version_after_first_add = panel._session.project_version
    service_field.setText("0007")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert panel._session.project_version == version_after_first_add
    assert service_list.count() == 1
    assert any("já está cadastrado" in message for message in warnings)

    service_field.setText("9012")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == [
        "0007",
        "9012",
    ]
    service_list.selectAll()
    assert remove_services.isEnabled()
    qtbot.mouseClick(remove_services, Qt.MouseButton.LeftButton)
    assert service_list.count() == 0
    assert panel._gateway.get_service_codes(first_project_id).service_codes == ()

    service_field.setText("0007")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    name.setText("0000000702")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    second_project_id = UUID(str(project_combo.currentData()))
    assert service_list.count() == 0
    service_field.setText("1234")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)

    first_index = project_combo.findData(str(first_project_id))
    project_combo.setCurrentIndex(first_index)
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["0007"]
    second_index = project_combo.findData(str(second_project_id))
    project_combo.setCurrentIndex(second_index)
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert [service_list.item(index).text() for index in range(service_list.count())] == ["1234"]

    assert panel._session is not None
    external = panel._gateway.replace_service_codes(
        second_project_id,
        ("3456", "1234"),
        expected_project_version=panel._session.project_version,
    )
    service_field.setText("9999")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    assert [service_list.item(index).text() for index in range(service_list.count())] == [
        "1234",
        "3456",
    ]
    assert panel._session is not None
    assert panel._session.project_version == external.project_version
    assert "9999" not in panel._gateway.get_service_codes(second_project_id).service_codes
    assert any("outra janela" in message for message in warnings)

    panel.set_global_operation(object())
    assert not service_box.isEnabled()
    panel.set_global_operation(None)
    assert service_box.isEnabled()
    fake_analysis_thread = QThread()
    panel._thread = fake_analysis_thread
    panel._apply_operation_state()
    assert not service_box.isEnabled()
    panel._thread = None
    panel._apply_operation_state()
    fake_analysis_thread.deleteLater()
    assert service_box.isEnabled()
    assert all("service" not in key.casefold() for key in panel._settings.allKeys())

    _reopened_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    reopened_services = reopened_panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    assert reopened_combo is not None and reopened_services is not None
    assert UUID(str(reopened_combo.currentData())) == second_project_id
    assert [reopened_services.item(index).text() for index in range(reopened_services.count())] == [
        "1234",
        "3456",
    ]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    reopened_delete = reopened_panel.findChild(QPushButton, "mvpDeleteProjectButton")
    reopened_service_box = reopened_panel.findChild(QGroupBox, "mvpProjectServiceCodesBox")
    assert reopened_delete is not None and reopened_service_box is not None
    qtbot.mouseClick(reopened_delete, Qt.MouseButton.LeftButton)
    assert reopened_combo.findData(str(second_project_id)) < 0
    assert not reopened_service_box.isEnabled()
    assert reopened_services.count() == 0


def test_project_combo_searches_only_digits_without_inserting_or_losing_ids(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _application, window = application_factory(
        [],
        settings=ClientSettings(data_directory=tmp_path / "project-search", pdf_render_dpi=72),
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    gateway = panel._gateway
    assert isinstance(gateway, DirectProjectGateway)
    combo = panel.findChild(QComboBox, "mvpProjectCombo")
    open_button = panel.findChild(QPushButton, "mvpOpenProjectButton")
    assert combo is not None and open_button is not None
    search = combo.lineEdit()
    assert search is not None
    assert combo.isEditable()
    assert combo.insertPolicy() is QComboBox.InsertPolicy.NoInsert
    assert search.maxLength() == 10
    assert search.validator() is not None

    first = gateway.create_project("1234567890", idempotency_key="search-first")
    second = gateway.create_project("9234567890", idempotency_key="search-second")
    for index in range(198):
        gateway.create_project(
            f"{1000 + index:010d}",
            idempotency_key=f"search-page-{index}",
        )
    hidden = gateway.create_project("0000009999", idempotency_key="search-hidden")
    panel.atualizar_projetos()
    assert combo.count() == 200
    assert combo.findData(str(first.project.project_id.root)) >= 0
    assert combo.findData(str(second.project.project_id.root)) >= 0
    assert combo.findData(str(hidden.project.project_id.root)) < 0
    monkeypatch.setattr(
        gateway, "create_project", lambda *a, **k: pytest.fail("NS existente não permite POST")
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: pytest.fail("NS existente abre sem pergunta")
    )
    item_ids = {combo.itemText(index): combo.itemData(index) for index in range(combo.count())}
    assert item_ids[first.project.service_note] == str(first.project.project_id.root)
    assert item_ids[second.project.service_note] == str(second.project.project_id.root)
    combo.setEditText(hidden.project.service_note)
    qtbot.mouseClick(open_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert panel.projeto_ativo_id == hidden.project.project_id.root
    assert combo.findData(str(hidden.project.project_id.root)) >= 0

    search.setText("9999")
    qtbot.waitUntil(lambda: combo.count() == 1 and combo.itemText(0) == hidden.project.service_note)
    assert panel.projeto_ativo_id == hidden.project.project_id.root
    assert search.text() == "9999"
    search.clear()
    qtbot.keyClicks(search, "456a78")
    assert search.text() == "45678"
    qtbot.waitUntil(lambda: combo.count() == 2)
    assert panel.projeto_ativo_id == hidden.project.project_id.root
    completer = combo.completer()
    assert completer is not None
    completer.setCompletionPrefix(search.text())
    completion_model = completer.completionModel()
    suggestions = {
        str(completion_model.index(row, 0).data()) for row in range(completion_model.rowCount())
    }
    assert suggestions == {first.project.service_note, second.project.service_note}
    assert combo.count() == 2
    search.clear()
    qtbot.keyClicks(search, "123456789012")
    assert search.text() == "1234567890"
    assert combo.count() == 2

    def unexpected_resolution(_service_note: str) -> object:
        raise AssertionError("Uma opção selecionada deve abrir pelo ID preservado")

    monkeypatch.setattr(gateway, "find_project_by_service_note", unexpected_resolution)
    selected_index = combo.findData(str(second.project.project_id.root))
    combo.setCurrentIndex(selected_index)
    qtbot.mouseClick(open_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert panel.projeto_ativo_id == second.project.project_id.root
    assert combo.currentData() == str(second.project.project_id.root)

    search.clear()
    assert combo.currentData() is None
    qtbot.waitUntil(lambda: "200 de 201" in panel._search_status.text())
    assert "Refine" in panel._search_status.text()
    assert search.text() == ""
    assert panel.projeto_ativo_id == second.project.project_id.root


def test_project_open_create_dialogs_and_refusals_return_to_initial_state(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "project-dialogs", pdf_render_dpi=72)
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    gateway = panel._gateway
    assert isinstance(gateway, DirectProjectGateway)
    existing = gateway.create_project("0000000801", idempotency_key="dialog-existing")
    panel.atualizar_projetos()
    combo = panel.findChild(QComboBox, "mvpProjectCombo")
    service_note = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create_button = panel.findChild(QPushButton, "mvpOpenProjectButton")
    open_button = panel.findChild(QPushButton, "mvpOpenProjectButton")
    run_button = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    rename_button = panel.findChild(QPushButton, "mvpRenameProjectButton")
    delete_button = panel.findChild(QPushButton, "mvpDeleteProjectButton")
    assert combo is not None and service_note is not None
    assert create_button is not None and open_button is not None
    assert run_button is not None and rename_button is not None and delete_button is not None

    original_create = gateway.create_project
    original_find = gateway.find_project_by_service_note
    create_calls: list[str] = []
    find_calls: list[str] = []

    def counted_create(note: str, *, idempotency_key: str):  # type: ignore[no-untyped-def]
        create_calls.append(note)
        return original_create(note, idempotency_key=idempotency_key)

    def counted_find(note: str):  # type: ignore[no-untyped-def]
        find_calls.append(note)
        return original_find(note)

    monkeypatch.setattr(gateway, "create_project", counted_create)
    monkeypatch.setattr(gateway, "find_project_by_service_note", counted_find)
    answers = [QMessageBox.StandardButton.No]
    questions: list[str] = []

    def answer_question(*args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        questions.extend(item for item in args if isinstance(item, str))
        return answers[-1]

    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "question", answer_question)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    cleared: list[bool] = []
    panel.project_cleared.connect(lambda: cleared.append(True))

    combo.setCurrentIndex(combo.findData(str(existing.project.project_id.root)))
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert panel.projeto_ativo_id == existing.project.project_id.root
    assert panel._settings.contains("last_project_id")
    source = create_golden_pdf(tmp_path / "residual.pdf")
    assert window.pdf_viewer.carregar_pdf(source)
    assert window.pdf_viewer.inspecao is not None
    review = window.review_panel
    documentation = window.documentation_panel
    gmax = window.gmax_panel
    export = window.portability_panel
    assert (
        review is not None and documentation is not None and gmax is not None and export is not None
    )
    review._project.addItem("Projeto residual", str(existing.project.project_id.root))
    review._project.setCurrentIndex(review._project.count() - 1)
    documentation._project.addItem("Projeto residual", str(existing.project.project_id.root))
    documentation._project.setCurrentIndex(documentation._project.count() - 1)
    assert export._project.currentData() == str(existing.project.project_id.root)

    service_note.setText("0000000802")
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)

    assert create_calls == []
    assert gateway.list_projects(limit=1, offset=0).page.total == 1
    assert cleared == [True]
    assert panel.projeto_ativo_id is None
    assert combo.currentData() is None and combo.currentText() == ""
    assert service_note.text() == ""
    assert not panel._settings.contains("last_project_id")
    assert window.pdf_viewer.inspecao is None
    assert review._project.currentData() is None
    review_accept = review.findChild(QPushButton, "reviewAcceptButton")
    review_reject = review.findChild(QPushButton, "reviewRejectButton")
    assert review_accept is not None and not review_accept.isEnabled()
    assert review_reject is not None and not review_reject.isEnabled()
    assert documentation._project.currentData() is None
    assert gmax.projeto_ativo_id is None
    gmax_state = gmax.findChild(QLabel, "gmaxStateLabel")
    assert gmax_state is not None and "Nenhum projeto ativo" in gmax_state.text()
    assert export._project.currentData() is None
    assert not export._pdf.isEnabled()
    assert not panel._service_box.isEnabled()
    assert not panel._document_box.isEnabled()
    assert not run_button.isEnabled()
    assert not rename_button.isEnabled()
    assert not delete_button.isEnabled()

    answers.append(QMessageBox.StandardButton.Yes)
    service_note.setText(existing.project.service_note)
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert create_calls == []
    assert gateway.list_projects(limit=1, offset=0).page.total == 1
    assert panel.projeto_ativo_id == existing.project.project_id.root

    missing = "0000000802"
    answers.append(QMessageBox.StandardButton.No)
    combo.setEditText(missing)
    qtbot.mouseClick(open_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert create_calls == []
    assert gateway.list_projects(limit=1, offset=0).page.total == 1
    assert panel.projeto_ativo_id is None
    assert combo.currentText() == ""

    created_from_open = "0000000803"
    answers.append(QMessageBox.StandardButton.Yes)
    combo.setEditText(created_from_open)
    qtbot.mouseClick(open_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert create_calls == [created_from_open]
    assert gateway.list_projects(limit=1, offset=0).page.total == 2
    assert panel._session is not None
    assert panel._session.service_note == created_from_open

    before_find = len(find_calls)
    combo.setEditText("123")
    qtbot.mouseClick(open_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    service_note.setText("123")
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert len(find_calls) == before_find
    assert create_calls == [created_from_open]
    assert any("exatamente 10 dígitos" in message for message in warnings)
    assert not any("Deseja abrir" in question for question in questions)
    assert sum("Deseja criar" in question for question in questions) == 3
    assert any(created_from_open in question for question in questions)


def test_project_creation_race_opens_winner_without_repeating_post(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    _application, window = application_factory(
        [],
        settings=ClientSettings(data_directory=tmp_path / "project-race", pdf_render_dpi=72),
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    gateway = panel._gateway
    assert isinstance(gateway, DirectProjectGateway)
    existing = gateway.create_project("0000000810", idempotency_key="race-existing")
    create_calls: list[str] = []

    monkeypatch.setattr(gateway, "find_project_by_service_note", lambda _note: None)

    def conflicting_create(note: str, *, idempotency_key: str) -> object:
        del idempotency_key
        create_calls.append(note)
        raise ProjectGatewayError(
            ErrorCode.PROJECT_ALREADY_EXISTS,
            "Já existe um projeto para a Nota de Serviço informada.",
            status_code=409,
            details={
                "project_id": str(existing.project.project_id.root),
                "service_note": note,
            },
        )

    monkeypatch.setattr(gateway, "create_project", conflicting_create)
    answers = [QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No]
    questions: list[str] = []

    def answer_question(*args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        questions.extend(item for item in args if isinstance(item, str))
        return answers.pop(0)

    monkeypatch.setattr(QMessageBox, "question", answer_question)
    service_note = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create_button = panel.findChild(QPushButton, "mvpOpenProjectButton")
    assert service_note is not None and create_button is not None

    service_note.setText(existing.project.service_note)
    qtbot.mouseClick(create_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    assert create_calls == [existing.project.service_note]
    assert panel.projeto_ativo_id == existing.project.project_id.root
    assert sum("Deseja criar" in question for question in questions) == 1
    assert not any("Deseja abrir" in question for question in questions)


def test_environmental_actions_full_client_matrix_uses_current_service_codes(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "actions-flow", pdf_render_dpi=72)
    catalog_code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    source = create_action_requirements_pdf(tmp_path / "acoes-sinteticas.pdf", catalog_code)
    verifier = FakeVerificadorAcoesConcluidas(resultado=False)
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )
    _application, window = application_factory(
        [],
        settings=settings,
        action_verifier=verifier,
    )
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create = panel.findChild(QPushButton, "mvpOpenProjectButton")
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    service_field = panel.findChild(QLineEdit, "mvpProjectServiceCodeEdit")
    service_list = panel.findChild(QListWidget, "mvpProjectServiceCodeList")
    add_service = panel.findChild(QPushButton, "mvpAddServiceCodeButton")
    assert name is not None and create is not None and project_combo is not None
    assert service_field is not None and service_list is not None and add_service is not None
    name.setText("0000007401")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    project_id = UUID(str(project_combo.currentData()))
    for code in ("0007", "9012"):
        service_field.setText(code)
        qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)

    assert isinstance(panel._gateway, DirectProjectGateway)
    assert panel._session is not None
    second_client = DirectProjectGateway(panel._gateway._runtime)
    server_wins = second_client.replace_service_codes(
        project_id,
        ("1234", "0007"),
        expected_project_version=panel._session.project_version,
    )
    assert isinstance(server_wins, ProjectServiceCodesResponse)
    service_field.setText("9999")
    qtbot.mouseClick(add_service, Qt.MouseButton.LeftButton)
    current_codes = tuple(service_list.item(index).text() for index in range(service_list.count()))
    assert current_codes == ("0007", "1234")
    assert any("outra janela" in message for message in warnings)
    canonical = panel._gateway.get_service_codes(project_id)
    assert isinstance(canonical, ProjectServiceCodesResponse)
    assert canonical.service_codes == current_codes
    assert canonical.project_version == server_wins.project_version

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(source)], "Documentos PDF (*.pdf)"),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert add_pdfs is not None and run is not None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert window.pdf_viewer.inspecao is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    documentation = window.documentation_panel
    gmax = window.gmax_panel
    assert documentation is not None
    assert gmax is not None
    findings_tree = documentation.findChild(QTreeWidget, "complianceFindingsTree")
    reanalyze = documentation.findChild(QPushButton, "complianceAnalyzeButton")
    assert findings_tree is not None and reanalyze is not None
    gmax_state = gmax.findChild(QLabel, "gmaxStateLabel")
    gmax_market = gmax.findChild(QLabel, "gmaxMarketLabel")
    gmax_checks = gmax.findChild(QTableWidget, "gmaxChecksTable")
    assert gmax_state is not None and gmax_market is not None and gmax_checks is not None
    action_rules = {
        "bi.acoes.impacto-ambiental": (
            "IMPACTO AMBIENTAL PENDENTE",
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL,
        ),
        "bi.acoes.falta-servidao": (
            "FALTA SERVIDÃO PENDENTE",
            DescricaoAcao.FALTA_SERVIDAO,
        ),
    }

    def assert_action_projection(
        impact_completed: bool,
        servitude_completed: bool,
    ) -> ComplianceExecutionResponse:
        # O fim da análise dispara novas leituras do mercado e do resumo GMAX.
        qtbot.waitUntil(
            lambda: (
                not panel.market._pending
                and documentation._result is not None
                and gmax._summary is not None
                and gmax._summary.last_execution_id == documentation._result.execution.execution_id
                and "Resultado atual" in gmax_state.text()
            ),
            timeout=10_000,
        )
        result = documentation._result
        assert isinstance(result, ComplianceExecutionResponse)
        by_rule = {item.rule_id: item for item in result.findings if item.rule_id in action_rules}
        assert set(by_rule) == set(action_rules)
        completed_by_rule = {
            "bi.acoes.impacto-ambiental": impact_completed,
            "bi.acoes.falta-servidao": servitude_completed,
        }
        visible_action_titles = {
            item.text(2)
            for index in range(findings_tree.topLevelItemCount())
            if (item := findings_tree.topLevelItem(index)) is not None
            and item.text(2) in {value[0] for value in action_rules.values()}
        }
        assert visible_action_titles == {
            action_rules[rule_id][0]
            for rule_id, completed in completed_by_rule.items()
            if not completed
        }
        for rule_id, finding in by_rule.items():
            title, _action = action_rules[rule_id]
            assert finding.title == title
            expected_status = (
                ComplianceStatus.COMPLIANT
                if completed_by_rule[rule_id]
                else ComplianceStatus.DIVERGENCE
            )
            assert finding.status is expected_status
            assert bool(finding.callout) is not completed_by_rule[rule_id]
            assert finding.evidence
            if finding.callout is None:
                continue
            assert finding.navigation is not None
            assert finding.callout.navigation.page_id == finding.navigation.page_id
            assert finding.callout.finding_id == finding.finding_id
        impact_callout = by_rule["bi.acoes.impacto-ambiental"].callout
        servitude_callout = by_rule["bi.acoes.falta-servidao"].callout
        if impact_callout is not None:
            assert float(impact_callout.anchor.y) >= 0.76
        if servitude_callout is not None:
            assert float(servitude_callout.anchor.y) < 0.76
        divergent = next((item for item in by_rule.values() if item.callout is not None), None)
        callout = divergent.callout if divergent is not None else None
        if divergent is not None and callout is not None:
            row = next(
                item
                for index in range(findings_tree.topLevelItemCount())
                if (item := findings_tree.topLevelItem(index)) is not None
                and item.text(2) == divergent.title
            )
            findings_tree.setCurrentItem(row)
            qtbot.waitUntil(
                lambda: (
                    window.pdf_viewer._selected_compliance_callout_id
                    == str(callout.callout_id.root)
                ),
                timeout=10_000,
            )
            assert window.pdf_viewer.folha_atual == 1
            assert str(callout.callout_id.root) in window.pdf_viewer.view._callout_items
        assert "Resultado atual" in gmax_state.text()
        assert gmax_market.text() == (
            "Última execução: Urbano\nBanco inicial: Urbano · Origem: banco"
        )
        query_cells = tuple(gmax_checks.item(row, 3) for row in range(gmax_checks.rowCount()))
        result_cells = tuple(gmax_checks.item(row, 4) for row in range(gmax_checks.rowCount()))
        assert all(cell is not None for cell in (*query_cells, *result_cells))
        assert [cell.text() for cell in query_cells if cell is not None] == [
            "Executado",
            "Executado",
        ]
        assert [cell.text() for cell in result_cells if cell is not None] == [
            "Linha encontrada" if impact_completed else "Sem linha",
            "Linha encontrada" if servitude_completed else "Sem linha",
        ]
        return result

    def result_changed(expected_id: ComplianceExecutionId) -> bool:
        result = documentation._result
        return (
            documentation._compliance_job_id is None
            and result is not None
            and result.execution.execution_id != expected_id
        )

    expected_calls = [
        ("0000007401", current_codes, action_rules[rule_id][1]) for rule_id in action_rules
    ]
    assert verifier.consultas == expected_calls
    previous = assert_action_projection(False, False)
    matrix = ((True, False), (False, True), (True, True))
    for impact_completed, servitude_completed in matrix:
        verifier.resultados = {
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL: impact_completed,
            DescricaoAcao.FALTA_SERVIDAO: servitude_completed,
        }
        before_calls = len(verifier.consultas)
        previous_id = previous.execution.execution_id
        qtbot.mouseClick(reanalyze, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            partial(result_changed, previous_id),
            timeout=30_000,
        )
        assert verifier.consultas[before_calls:] == expected_calls
        previous = assert_action_projection(impact_completed, servitude_completed)

    _reopened_application, reopened = application_factory(
        [],
        settings=settings,
        action_verifier=verifier,
    )
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_services = reopened_panel.findChild(
        QListWidget,
        "mvpProjectServiceCodeList",
    )
    assert reopened_services is not None
    assert (
        tuple(reopened_services.item(index).text() for index in range(reopened_services.count()))
        == current_codes
    )
    reopened_documentation = reopened.documentation_panel
    assert reopened_documentation is not None
    reopened_documentation.abrir_projeto(project_id)
    assert reopened_documentation._result == previous


def test_user_can_create_import_analyze_review_and_reopen_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    source = _catalog_pdf(tmp_path / "projeto.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectSearchEdit")
    create = panel.findChild(QPushButton, "mvpOpenProjectButton")
    assert name is not None and create is not None
    name.setText("0000000139")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel._project_action_active)
    project_combo = panel.findChild(QComboBox, "mvpProjectCombo")
    assert project_combo is not None
    project_id = project_combo.currentData()
    assert project_id is not None

    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(source)], "Documentos PDF (*.pdf)"),
    )
    add_pdfs = panel.findChild(QPushButton, "mvpAddPdfsButton")
    assert add_pdfs is not None
    assert panel.findChild(QPushButton, "mvpMergePdfsButton") is None
    qtbot.mouseClick(add_pdfs, Qt.MouseButton.LeftButton)
    assert window.pdf_viewer.inspecao is not None

    assert window.review_panel is not None
    server_database = (
        settings.data_directory.parent
        / f"{settings.data_directory.name}-server"
        / DATABASE_FILE_NAME
    )
    persistence = create_sqlite_engine(server_database)
    with SqlAlchemyUnitOfWork(persistence) as work:
        project = work.projetos.obter(UUID(str(project_id)))
        assert project is not None
        work.projetos.salvar(
            replace(project, metadados=MetadadosProjeto(tipo_servico="Rede urbana"))
        )
        work.commit()
    persistence.dispose()
    panel.abrir_selecionado()
    qtbot.waitUntil(lambda: not panel._project_action_active)

    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert run is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    server_data_directory = (
        settings.data_directory.parent / f"{settings.data_directory.name}-server"
    )
    log_payloads = _application_log(settings.data_directory, server_data_directory)
    for operation in (
        "client.bootstrap",
        "pdf.viewer.open",
        "pdf.viewer.render",
    ):
        records = [item for item in log_payloads if item.get("operation") == operation]
        assert {item.get("status") for item in records} >= {
            "started",
            "succeeded",
        }, operation
    serialized_log = json.dumps(log_payloads, ensure_ascii=False)
    assert str(source.resolve()) not in serialized_log
    assert "password" not in serialized_log.casefold()
    assert "senha" not in serialized_log.casefold()

    review_panel = window.review_panel
    assert review_panel is not None
    review_project = review_panel.findChild(QComboBox, "reviewProjectCombo")
    results = review_panel.findChild(QTreeWidget, "analysisRelationshipTree")
    assert review_project is not None and results is not None
    assert review_project.currentData() == project_id
    assert results.topLevelItemCount() >= 1

    documentation_panel = window.documentation_panel
    assert documentation_panel is not None
    compliance_tree = documentation_panel.findChild(QTreeWidget, "complianceFindingsTree")
    compliance_status = documentation_panel.findChild(QLabel, "complianceExecutionStatusLabel")
    reapply = documentation_panel.findChild(QPushButton, "complianceAnalyzeButton")
    assert compliance_tree is not None
    assert compliance_status is not None
    assert reapply is not None
    qtbot.waitUntil(
        lambda: not panel.market._pending and "Resultado atual" in compliance_status.text(),
        timeout=10_000,
    )
    assert compliance_tree.topLevelItemCount() >= 1
    divergence = compliance_tree.topLevelItem(0)
    assert divergence is not None
    assert divergence.text(0) == "Divergência"
    assert "ausente" in divergence.text(3).casefold()
    assert "presente" in divergence.text(4).casefold()
    assert "Resultado atual" in compliance_status.text()

    def forbidden_call(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("Reaplicar conformidade não pode executar extração ou OCR")

    monkeypatch.setattr(PyMuPdfDocumentAnalyzer, "analisar", forbidden_call)
    monkeypatch.setattr(TesseractCliOcr, "reconhecer", forbidden_call)
    previous_count = compliance_tree.topLevelItemCount()
    qtbot.mouseClick(reapply, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: "Resultado atual" in compliance_status.text(), timeout=30_000)
    assert compliance_tree.topLevelItemCount() == previous_count
    assert "Resultado atual" in compliance_status.text()

    window.pdf_viewer.ir_para_folha(2)
    assert window.pdf_viewer.folha_atual == 2
    _second_application, reopened = application_factory([], settings=settings)
    qtbot.addWidget(reopened)
    reopened.show()
    reopened_panel = reopened.project_panel
    assert isinstance(reopened_panel, ProjectPanelWidget)
    reopened_combo = reopened_panel.findChild(QComboBox, "mvpProjectCombo")
    assert reopened_combo is not None
    assert reopened_combo.currentData() == project_id
    assert reopened.pdf_viewer.folha_atual == 2
    reopened_documentation = reopened.documentation_panel
    assert reopened_documentation is not None
    reopened_findings = reopened_documentation.findChild(QTreeWidget, "complianceFindingsTree")
    assert reopened_findings is not None
    assert reopened_findings.topLevelItemCount() == previous_count

    confirmations: list[str] = []

    def confirm(*args: object, **_kwargs: object) -> QMessageBox.StandardButton:
        confirmations.extend(item for item in args if isinstance(item, str))
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    document_list = reopened_panel.findChild(QListWidget, "mvpPageOrderList")
    remove_pdf = reopened_panel.findChild(QPushButton, "mvpRemovePdfsButton")
    assert document_list is not None and remove_pdf is not None
    document_list.item(0).setSelected(True)
    qtbot.mouseClick(remove_pdf, Qt.MouseButton.LeftButton)
    assert document_list.count() == 0
    assert reopened.pdf_viewer.inspecao is None
    assert any(
        "Análises, propostas" in message
        and "Cópias mantidas fora do servidor serão preservadas" in message
        for message in confirmations
    )

    delete_project = reopened_panel.findChild(QPushButton, "mvpDeleteProjectButton")
    assert delete_project is not None
    qtbot.mouseClick(delete_project, Qt.MouseButton.LeftButton)
    assert reopened_combo.findData(project_id) < 0
    assert any(
        "arquivos gerenciados no servidor" in message
        and "Arquivos já baixados ou mantidos fora do servidor" in message
        for message in confirmations
    )
