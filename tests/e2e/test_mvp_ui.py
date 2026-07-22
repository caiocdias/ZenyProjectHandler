# mypy: disable-error-code="no-untyped-call"
from __future__ import annotations

from pathlib import Path

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
    QTableWidget,
)
from pytestqt.qtbot import QtBot

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.bootstrap import create_application
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.ui.project_panel import ProjectPanelWidget

pytestmark = [pytest.mark.integration, pytest.mark.e2e]


def _catalog_pdf(path: Path) -> Path:
    code = carregar_catalogo_inicial().itens_ativos(CategoriaElemento.POSTE)[0].codigo
    document = pymupdf.open()
    try:
        first = document.new_page(width=240, height=160)
        first.insert_text((20, 40), code)
        second = document.new_page(width=240, height=160)
        second.insert_text((20, 40), "SEGUNDA FOLHA")
        document.save(path)
    finally:
        document.close()
    return path


def test_user_can_create_import_analyze_review_and_reopen_from_ui(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettings(data_directory=tmp_path / "data", pdf_render_dpi=72)
    source = _catalog_pdf(tmp_path / "projeto.pdf")
    _application, window = create_application([], settings=settings)
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
    select = panel.findChild(QPushButton, "mvpSelectPdfsButton")
    merge = panel.findChild(QPushButton, "mvpMergePdfsButton")
    assert select is not None and merge is not None
    qtbot.mouseClick(select, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(merge, Qt.MouseButton.LeftButton)
    assert window.pdf_viewer.inspecao is not None

    run = panel.findChild(QPushButton, "mvpRunAnalysisButton")
    assert run is not None
    qtbot.mouseClick(run, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: not panel.processando, timeout=30_000)

    review_panel = window.review_panel
    assert review_panel is not None
    review_project = review_panel.findChild(QComboBox, "reviewProjectCombo")
    proposals = review_panel.findChild(QTableWidget, "reviewProposalTable")
    assert review_project is not None and proposals is not None
    assert review_project.currentData() == project_id
    assert proposals.rowCount() >= 1

    window.pdf_viewer.ir_para_folha(2)
    assert window.pdf_viewer.folha_atual == 2
    _second_application, reopened = create_application([], settings=settings)
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
    document_list = reopened_panel.findChild(QListWidget, "mvpDocumentList")
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
