# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pymupdf
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTreeWidget,
)
from pytestqt.qtbot import QtBot

from tests.conftest import ApplicationFactory
from tests.pdf_fixtures import create_golden_pdf
from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.ui.project_panel import ProjectPanelWidget

pytestmark = [
    pytest.mark.integration,
    pytest.mark.e2e,
]


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


def _application_log(data_directory: Path) -> tuple[dict[str, object], ...]:
    log_path = data_directory / "logs" / "application.jsonl"
    payloads: list[dict[str, object]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        decoded = json.loads(line)
        assert isinstance(decoded, dict)
        payloads.append(cast(dict[str, object], decoded))
    return tuple(payloads)


def test_user_can_reorder_project_pdfs_and_reopen_in_reading_order(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    first = _catalog_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    assert name is not None and create is not None
    name.setText("Projeto ordenado")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
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


def test_user_can_create_import_analyze_review_and_reopen_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    source = _catalog_pdf(tmp_path / "projeto.pdf")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)

    name = panel.findChild(QLineEdit, "mvpProjectNameEdit")
    create = panel.findChild(QPushButton, "mvpCreateProjectButton")
    assert name is not None and create is not None
    name.setText("Projeto MVP")
    qtbot.mouseClick(create, Qt.MouseButton.LeftButton)
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

    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert run is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    log_payloads = _application_log(settings.data_directory)
    for operation in (
        "application.bootstrap",
        "pdf.import",
        "pdf.viewer.open",
        "pdf.viewer.render",
        "pdf.analysis",
        "qt.worker.analysis_pipeline",
    ):
        records = [item for item in log_payloads if item.get("operation") == operation]
        assert {item.get("status") for item in records} >= {"started", "succeeded"}
    worker_records = [
        item for item in log_payloads if item.get("operation") == "qt.worker.analysis_pipeline"
    ]
    assert len({item.get("correlation_id") for item in worker_records}) == 1
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

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
    )
    document_list = reopened_panel.findChild(QListWidget, "mvpPageOrderList")
    remove_pdf = reopened_panel.findChild(QPushButton, "mvpRemovePdfsButton")
    assert document_list is not None and remove_pdf is not None
    document_list.item(0).setSelected(True)
    qtbot.mouseClick(remove_pdf, Qt.MouseButton.LeftButton)
    assert document_list.count() == 0
    assert reopened.pdf_viewer.inspecao is None

    delete_project = reopened_panel.findChild(QPushButton, "mvpDeleteProjectButton")
    assert delete_project is not None
    qtbot.mouseClick(delete_project, Qt.MouseButton.LeftButton)
    assert reopened_combo.findData(project_id) < 0
