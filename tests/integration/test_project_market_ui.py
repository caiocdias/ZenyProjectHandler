# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, get_ident
from typing import cast
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui.project_gateway import ProjectGateway, ProjectGatewayError
from zeny_project_handler_client.ui.project_market import ProjectMarketWidget
from zeny_project_handler_client.ui.theme import Tema, aplicar_tema
from zeny_project_handler_contracts.base import ProjectId
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.projects import (
    ProjectDetailDto,
    ProjectMarketClassificationDto,
    ProjectMarketResponse,
    UpdateProjectMarketRequest,
)

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 10, 15, 30, tzinfo=UTC)


def _project(project_id: UUID) -> ProjectDetailDto:
    return ProjectDetailDto.model_validate(
        {
            "project_id": project_id,
            "service_note": "0001234567",
            "state": "CREATED",
            "project_version": 1,
            "documents": [],
            "pages": [],
            "analysis": {"pending_proposals": 0, "completed_decisions": 0},
            "created_at": NOW,
            "updated_at": NOW,
        }
    )


def _market(project_id: UUID) -> ProjectMarketResponse:
    return ProjectMarketResponse(
        project_id=ProjectId(project_id),
        project_version=1,
        classification=ProjectMarketClassificationDto(
            service_note="0001234567",
            database_market="RURAL",
            effective_market="RURAL",
            source="SQL",
            initialized_at=NOW,
            updated_at=NOW,
            revision_id=uuid4(),
            classification_version=1,
        ),
    )


class MarketGateway:
    def __init__(self) -> None:
        self.project_id = uuid4()
        self.value = _market(self.project_id)
        self.failure: Exception | None = None
        self.read_gate: Event | None = None
        self.save_gate: Event | None = None
        self.started = Event()
        self.writes: list[UpdateProjectMarketRequest] = []
        self.threads: list[int] = []

    def get_market(self, _project_id: UUID) -> ProjectMarketResponse:
        self.threads.append(get_ident())
        value, gate, failure = self.value, self.read_gate, self.failure
        self.started.set()
        if gate is not None:
            assert gate.wait(10)
        if failure is not None:
            raise failure
        return value

    def update_market(
        self, _project_id: UUID, request: UpdateProjectMarketRequest
    ) -> ProjectMarketResponse:
        self.threads.append(get_ident())
        self.writes.append(request)
        self.started.set()
        if self.save_gate is not None:
            assert self.save_gate.wait(10)
        if self.failure is not None:
            raise self.failure
        assert request.expected_project_version == self.value.project_version
        classification = self.value.classification
        assert classification is not None
        self.value = self.value.model_copy(
            update={
                "project_version": self.value.project_version + 1,
                "classification": classification.model_copy(
                    update={
                        "effective_market": request.effective_market,
                        "source": "MANUAL",
                        "classification_version": classification.classification_version + 1,
                        "revision_id": uuid4(),
                    }
                ),
            }
        )
        return self.value


def _widget(qtbot: QtBot, gateway: MarketGateway) -> ProjectMarketWidget:
    widget = ProjectMarketWidget(cast(ProjectGateway, gateway))
    container = QWidget()
    widget.__dict__["_test_container"] = container
    qtbot.addWidget(container)
    layout = QVBoxLayout(container)
    layout.addWidget(widget)
    container.resize(540, 350)
    container.show()
    widget.open_project(_project(gateway.project_id))
    qtbot.waitUntil(lambda: not widget._pending)
    return widget


def _capture(widget: ProjectMarketWidget, name: str) -> None:
    directory = os.environ.get("ZENY_E04_CAPTURE_DIR")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        QApplication.processEvents()
        assert (widget.parentWidget() or widget).grab().save(str(path / f"{name}.png"))


@pytest.mark.parametrize("theme", [Tema.CLARO, Tema.ESCURO])
def test_save_cancel_fail_and_reconnect_visually(qtbot: QtBot, theme: Tema) -> None:
    application = cast(QApplication, QApplication.instance())
    if os.environ.get("ZENY_E04_CAPTURE_DIR"):
        font = Path(os.environ["WINDIR"]) / "Fonts" / "segoeui.ttf"
        assert QFontDatabase.addApplicationFont(str(font)) >= 0
    aplicar_tema(application, theme)
    gateway = MarketGateway()
    widget = _widget(qtbot, gateway)
    try:
        assert "Banco inicial: Rural" in widget.provenance.text()
        assert "Cadastro do banco" in widget.provenance.text()
        widget.choice.setFocus()
        qtbot.keyClick(widget.choice, Qt.Key.Key_End)
        assert widget.choice.currentData() == "AMBOS"
        qtbot.mouseClick(widget.cancel, Qt.MouseButton.LeftButton)
        assert widget.choice.currentData() == "RURAL"
        assert not gateway.writes
        for choice in ("URBANO", "AMBOS", "RURAL"):
            widget.choice.setCurrentIndex(widget.choice.findData(choice))
            qtbot.mouseClick(widget.save, Qt.MouseButton.LeftButton)
            qtbot.waitUntil(lambda: not widget.saving)
            assert "Mercado salvo" in widget.status.text()
            assert gateway.value.classification is not None
            assert gateway.value.classification.effective_market == choice
            widget.open_project(_project(gateway.project_id))
            qtbot.waitUntil(lambda: not widget._pending)
            assert widget.choice.currentData() == choice
        _capture(widget, f"{theme.value}-salvo")
        widget.choice.setCurrentIndex(2)
        gateway.failure = ProjectGatewayError(ErrorCode.STALE_STATE, "Outra edição", 409)
        qtbot.mouseClick(widget.save, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not widget.saving)
        assert "Conflito" in widget.status.text()
        assert widget.choice.currentIndex() == -1
        assert not widget.save.isEnabled()
        _capture(widget, f"{theme.value}-falha")
        assert len(gateway.writes) == 4
        widget.set_connected(False)
        assert not widget.refresh.isEnabled()
        _capture(widget, f"{theme.value}-desconectado")
        gateway.failure = None
        widget.set_connected(True)
        qtbot.waitUntil(lambda: not widget._pending)
        assert widget.choice.currentData() == "RURAL"
        assert "Escolha do técnico" in widget.provenance.text()
        _capture(widget, f"{theme.value}-reconectado")
        assert all(thread != get_ident() for thread in gateway.threads)
        assert widget.choice.accessibleName()
        assert widget.save.accessibleName()
    finally:
        aplicar_tema(application, Tema.CLARO)


@pytest.mark.parametrize("code", [ErrorCode.INTERNAL_ERROR, ErrorCode.OPERATION_CONFLICT])
def test_uninitialized_error_retry_and_foreign_response(qtbot: QtBot, code: ErrorCode) -> None:
    gateway = MarketGateway()
    initialized = gateway.value
    gateway.value = initialized.model_copy(update={"classification": None})
    widget = _widget(qtbot, gateway)
    assert "não inicializado" in widget.status.text()
    assert not widget.choice.isEnabled()
    assert widget.refresh.isEnabled()
    gateway.failure = ProjectGatewayError(code, "Indisponível", 404)
    widget.reload()
    qtbot.waitUntil(lambda: not widget._pending)
    assert not widget.choice.isEnabled()
    assert "Indisponível" in widget.status.text()
    gateway.failure = None
    gateway.value = _market(uuid4())
    widget.reload()
    qtbot.waitUntil(lambda: not widget._pending)
    assert not widget.save.isEnabled()
    assert widget.choice.currentIndex() == -1
    gateway.value = initialized
    widget.reload()
    qtbot.waitUntil(widget.choice.isEnabled)
    assert not gateway.writes


def test_delayed_read_cannot_cross_project_or_connection_and_does_not_block_qt(
    qtbot: QtBot,
) -> None:
    gateway = MarketGateway()
    widget = _widget(qtbot, gateway)
    gate = gateway.read_gate = Event()
    gateway.started.clear()
    widget.reload()
    qtbot.waitUntil(gateway.started.is_set)
    ticks: list[bool] = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    qtbot.waitUntil(lambda: bool(ticks))
    try:
        widget.set_connected(False)
        second = uuid4()
        gateway.value = _market(second)
        gateway.read_gate = None
        widget.open_project(_project(second))
        widget.set_connected(True)
        qtbot.waitUntil(widget.choice.isEnabled)
        assert widget._response is not None and widget._response.project_id.root == second
    finally:
        gate.set()
    qtbot.wait(50)
    assert widget._response is not None and widget._response.project_id.root == second
    widget.clear()
    assert widget.choice.currentIndex() == -1


def test_disconnect_during_save_reconciles_without_repeating_mutation(qtbot: QtBot) -> None:
    gateway = MarketGateway()
    widget = _widget(qtbot, gateway)
    gateway.save_gate = Event()
    gateway.started.clear()
    widget.choice.setCurrentIndex(2)
    widget.save.click()
    qtbot.waitUntil(gateway.started.is_set)
    assert not widget.cancel.isEnabled()
    assert not widget.save.isEnabled()
    widget.set_connected(False)
    gateway.save_gate.set()
    qtbot.waitUntil(lambda: gateway.value.project_version == 2)
    assert "interrompida" in widget.status.text()
    widget.set_connected(True)
    qtbot.waitUntil(widget.choice.isEnabled)
    assert widget.choice.currentData() == "AMBOS"
    assert len(gateway.writes) == 1


def test_technician_can_confirm_database_value_and_draft_never_changes_provenance(
    qtbot: QtBot,
) -> None:
    gateway = MarketGateway()
    widget = _widget(qtbot, gateway)
    widget.save.click()
    qtbot.waitUntil(lambda: not widget.saving)
    assert gateway.writes[0].effective_market == "RURAL"
    assert "Escolha do técnico" in widget.provenance.text()
    provenance = widget.provenance.text()
    widget.choice.setCurrentIndex(2)
    assert widget.provenance.text() == provenance
    assert gateway.value.classification is not None
    assert gateway.value.classification.effective_market == "RURAL"


def test_old_response_on_same_project_and_renamed_ns_are_discarded(qtbot: QtBot) -> None:
    gateway = MarketGateway()
    widget = _widget(qtbot, gateway)
    gate = gateway.read_gate = Event()
    gateway.started.clear()
    widget.reload()
    qtbot.waitUntil(gateway.started.is_set)
    try:
        gateway.read_gate = None
        classification = gateway.value.classification
        assert classification is not None
        gateway.value = gateway.value.model_copy(
            update={
                "classification": classification.model_copy(update={"effective_market": "AMBOS"})
            }
        )
        widget.reload()
        qtbot.waitUntil(widget.choice.isEnabled)
        assert widget.choice.currentData() == "AMBOS"
    finally:
        gate.set()
    qtbot.wait(50)
    assert widget.choice.currentData() == "AMBOS"
    widget.open_project(
        _project(gateway.project_id).model_copy(update={"service_note": "0007654321"})
    )
    qtbot.waitUntil(lambda: not widget._pending)
    assert not widget.choice.isEnabled()
    assert not gateway.writes
