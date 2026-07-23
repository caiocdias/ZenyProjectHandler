from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
)
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.bootstrap import create_application, run
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import InspecaoPdf
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget


@pytest.mark.integration
def test_main_window_smoke(qtbot: QtBot, tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    application, window = create_application([], settings=settings)
    qtbot.addWidget(window)
    window.show()

    assert application.applicationName() == "Zeny Project Handler"
    assert window.windowTitle() == "Zeny Project Handler"
    assert window.centralWidget().objectName() == "pdfViewerWidget"
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    graph_dock = window.findChild(QDockWidget, "projectGraphDock")
    portability_dock = window.findChild(QDockWidget, "projectPortabilityDock")
    assert review_dock is not None
    assert window.findChild(QDockWidget, "projectWorkflowDock") is not None
    assert graph_dock is None
    assert portability_dock is not None
    assert portability_dock in window.tabifiedDockWidgets(review_dock)
    assert window.review_panel is not None
    assert window.project_panel is not None
    assert window.portability_panel is not None
    assert window.statusBar().currentMessage() == "Pronto para abrir um PDF"
    assert settings.database_path.is_file()


@pytest.mark.integration
def test_floating_panel_has_window_controls_and_can_be_reopened(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    settings = AppSettings(data_directory=tmp_path)
    _application, window = create_application([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    panels_menu = window.findChild(QMenu, "panelsMenu")
    assert review_dock is not None
    assert panels_menu is not None

    review_dock.setFloating(True)
    qtbot.waitUntil(review_dock.isFloating)
    minimize_button = review_dock.findChild(QToolButton, "humanReviewDockMinimizeButton")
    maximize_button = review_dock.findChild(QToolButton, "humanReviewDockMaximizeButton")
    float_button = review_dock.findChild(QToolButton, "humanReviewDockFloatButton")
    close_button = review_dock.findChild(QToolButton, "humanReviewDockCloseButton")
    assert minimize_button is not None and minimize_button.isVisible()
    assert maximize_button is not None and maximize_button.isVisible()
    assert float_button is not None and float_button.isVisible()
    assert close_button is not None and close_button.isVisible()

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        maximize_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(review_dock.isMaximized)
    assert maximize_button.toolTip() == "Restaurar painel"
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        maximize_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(lambda: not review_dock.isMaximized())

    window.showMaximized()
    qtbot.waitUntil(window.isMaximized)
    portability_dock = window.findChild(QDockWidget, "projectPortabilityDock")
    assert portability_dock is not None

    def layout_occupies_window_width() -> bool:
        docked_right_edges = [
            dock.geometry().right()
            for dock in window.findChildren(QDockWidget)
            if dock.isVisible() and not dock.isFloating()
        ]
        occupied_right_edge = max(
            window.centralWidget().geometry().right(),
            *docked_right_edges,
        )
        return occupied_right_edge >= window.contentsRect().right() - 2

    qtbot.waitUntil(layout_occupies_window_width)

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        close_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(lambda: not review_dock.isVisible())
    toggle_action = next(
        action
        for action in panels_menu.actions()
        if action.objectName() == "humanReviewDockToggleAction"
    )
    assert not toggle_action.isChecked()

    toggle_action.trigger()

    qtbot.waitUntil(review_dock.isVisible)
    assert toggle_action.isChecked()
    assert review_dock.isFloating()

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        float_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(lambda: not review_dock.isFloating())
    assert not minimize_button.isVisible()
    assert not maximize_button.isVisible()

    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        float_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(review_dock.isFloating)


@pytest.mark.integration
def test_application_smoke_mode_opens_and_closes(tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    exit_code = run(["zeny-project-handler", "--smoke-test"], settings=settings)

    assert exit_code == 0


@pytest.mark.integration
def test_pdf_viewer_navigation_zoom_rotation_and_overlays(qtbot: QtBot, tmp_path: Path) -> None:
    source = create_feature_pdf(tmp_path / "interface.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.resize(800, 600)
    viewer.show()

    viewer.carregar_pdf(source)

    assert viewer.inspecao is not None
    assert viewer.view.scene() is not None
    assert viewer.view.scene().items()
    viewer.definir_sobreposicoes(
        (
            (
                PontoNormalizado(Decimal("0.1"), Decimal("0.1")),
                PontoNormalizado(Decimal("0.5"), Decimal("0.5")),
            ),
        )
    )
    assert len(viewer.view.scene().items()) >= 2

    zoom_before = viewer.view.zoom
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        viewer.findChild(QPushButton, "pdfZoomInButton"),
        pytest.importorskip("PySide6.QtCore").Qt.MouseButton.LeftButton,
    )
    assert viewer.view.zoom > zoom_before
    qtbot.mouseClick(  # type: ignore[no-untyped-call]
        viewer.findChild(QPushButton, "pdfRotateButton"),
        pytest.importorskip("PySide6.QtCore").Qt.MouseButton.LeftButton,
    )
    assert viewer.view.scene().items()


@pytest.mark.integration
def test_pdf_viewer_reports_controlled_open_failure(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    messages: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: messages.append(str(message)),
    )

    viewer.carregar_pdf(tmp_path / "ausente.pdf")

    assert messages
    assert viewer.inspecao is None


@pytest.mark.integration
def test_pdf_viewer_opens_selected_files_as_one_ordered_project(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = create_feature_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.show()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *_args, **_kwargs: ([str(first), str(second)], "Documentos PDF (*.pdf)"),
    )

    viewer.selecionar_pdf()

    inspections: tuple[InspecaoPdf, ...] = viewer.inspecoes
    assert [item.documento.nome_arquivo for item in inspections] == [
        "folha-01.pdf",
        "folha-02.pdf",
    ]
    assert viewer.findChild(QPushButton, "mergePdfsIntoProjectButton") is None
    page_selector = viewer.findChild(QSpinBox, "pdfPageSpinBox")
    assert page_selector is not None
    assert page_selector.maximum() == sum(len(item.paginas) for item in inspections)
    page_selector.setValue(page_selector.maximum())
    assert viewer.inspecao is not None
    assert viewer.inspecao.documento.nome_arquivo == "folha-02.pdf"
    metadata = viewer.findChild(QLabel, "pdfMetadataLabel")
    assert metadata is not None
    assert "Projeto: 2 PDFs" in metadata.text()


@pytest.mark.integration
def test_pdf_viewer_follows_page_order_across_different_files(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    first = create_feature_pdf(tmp_path / "folha-01.pdf")
    second = create_golden_pdf(tmp_path / "folha-02.pdf")
    reader = PyMuPdfReader()
    documents = (
        reader.inspecionar(first).documento,
        reader.inspecionar(second).documento,
    )
    first_page, second_page, third_page = documents[0].paginas
    fourth_page = documents[1].paginas[0]
    viewer = PdfViewerWidget(leitor=reader, dpi=72)
    qtbot.addWidget(viewer)

    loaded = viewer.carregar_projeto(
        (first, second),
        documentos=documents,
        ordem_paginas=(fourth_page.id, second_page.id, first_page.id, third_page.id),
    )

    assert loaded
    assert viewer.inspecao is not None
    assert viewer.inspecao.documento.nome_arquivo == "folha-02.pdf"
    viewer.ir_para_folha(2)
    assert viewer.inspecao is not None
    assert viewer.inspecao.documento.nome_arquivo == "folha-01.pdf"


@pytest.mark.integration
def test_pdf_viewer_keeps_current_project_when_one_selected_file_is_invalid(
    qtbot: QtBot,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = create_feature_pdf(tmp_path / "atual.pdf")
    another = create_golden_pdf(tmp_path / "outra.pdf")
    viewer = PdfViewerWidget(leitor=PyMuPdfReader(), dpi=72)
    qtbot.addWidget(viewer)
    viewer.carregar_pdf(current)
    original_inspections = viewer.inspecoes
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(str(message)),
    )

    duplicated = viewer.carregar_projeto((another, another))

    loaded = viewer.carregar_projeto((another, tmp_path / "ausente.pdf"))

    assert not duplicated
    assert not loaded
    assert any("duplicado" in message for message in warnings)
    assert viewer.inspecoes == original_inspections
    assert viewer.inspecao == original_inspections[0]
