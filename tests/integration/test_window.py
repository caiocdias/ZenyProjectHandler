from decimal import Decimal
from pathlib import Path
from threading import Event
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFrame,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
)
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory
from tests.pdf_fixtures import create_feature_pdf, create_golden_pdf

from zeny_project_handler import bootstrap
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.operation_coordinator import TipoOperacao
from zeny_project_handler.bootstrap import _EngineLifetime, run
from zeny_project_handler.config import AppSettings
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import InspecaoPdf
from zeny_project_handler.ui.main_window import _DockTitleBar
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler.ui.project_panel import _PipelineWorker


@pytest.mark.integration
def test_main_window_smoke(
    qtbot: QtBot, tmp_path: Path, application_factory: ApplicationFactory
) -> None:
    settings = AppSettings(data_directory=tmp_path)

    application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()

    assert application.applicationName() == "Zeny Project Handler"
    assert window.windowTitle() == "Zeny Project Handler"
    assert window.centralWidget().objectName() == "pdfViewerWidget"
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    graph_dock = window.findChild(QDockWidget, "projectGraphDock")
    portability_dock = window.findChild(QDockWidget, "projectPortabilityDock")
    documentation_dock = window.findChild(QDockWidget, "documentationComplianceDock")
    assert review_dock is not None
    assert window.findChild(QDockWidget, "projectWorkflowDock") is not None
    assert graph_dock is None
    assert portability_dock is not None
    assert documentation_dock is not None
    assert documentation_dock in window.tabifiedDockWidgets(review_dock)
    assert portability_dock in window.tabifiedDockWidgets(review_dock)
    assert window.review_panel is not None
    assert window.project_panel is not None
    assert window.portability_panel is not None
    assert window.documentation_panel is not None
    workflow_coordinator = window.project_panel._service._coordinator
    assert workflow_coordinator is window.project_panel._service._importer._coordenador
    assert workflow_coordinator is window.portability_panel._service._coordinator
    assert (
        window.project_panel._service._managed_files
        is window.portability_panel._service._managed_files
    )
    assert window.statusBar().currentMessage() == "Pronto para abrir um PDF"
    assert settings.database_path.is_file()


@pytest.mark.integration
def test_bootstrapped_analysis_worker_refuses_restore_conflict_before_mutation(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path / "coordinated-window")
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    panel = window.project_panel
    assert panel is not None
    service = panel._service
    coordinator = service._coordinator
    created = service.criar_projeto("Projeto para recusa no worker")
    source = create_golden_pdf(tmp_path / "worker-source.pdf")
    service.importar_pdfs(created.projeto.id, (source,))
    worker = _PipelineWorker(
        service,
        created.projeto.id,
        Event(),
        "44444444444444444444444444444444",
    )
    failures: list[tuple[str, bool]] = []
    worker.failed.connect(lambda message, cancelled: failures.append((message, cancelled)))

    with coordinator.adquirir(TipoOperacao.RESTAURACAO):
        worker.run()

    assert failures == [
        (
            "Não foi possível iniciar análise do projeto: restauração do backup está em andamento. "
            "Aguarde a conclusão ou o cancelamento.",
            False,
        )
    ]
    summary = service.abrir_projeto(created.projeto.id).resumo
    assert summary.ultima_extracao is None
    assert summary.ultima_interpretacao is None


@pytest.mark.integration
def test_floating_panel_has_window_controls_and_can_be_reopened(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path)
    _application, window = application_factory([], settings=settings)
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
    assert float_button.text() == "Reacoplar"
    controls_separator = review_dock.findChild(
        QFrame,
        "humanReviewDockWindowControlsSeparator",
    )
    assert controls_separator is not None and controls_separator.isVisible()
    assert float_button.geometry().right() < controls_separator.geometry().left()
    assert controls_separator.geometry().right() < minimize_button.geometry().left()

    title_bar = review_dock.titleBarWidget()
    assert title_bar is not None
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

    qtbot.mouseDClick(  # type: ignore[no-untyped-call]
        title_bar,
        Qt.MouseButton.LeftButton,
    )
    qtbot.waitUntil(review_dock.isMaximized)
    assert review_dock.isFloating()
    assert maximize_button.toolTip() == "Restaurar painel"
    qtbot.mouseDClick(  # type: ignore[no-untyped-call]
        title_bar,
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
def test_floating_panel_screen_edge_snap_geometry(
    qtbot: QtBot, tmp_path: Path, application_factory: ApplicationFactory
) -> None:
    settings = AppSettings(data_directory=tmp_path)
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    assert review_dock is not None
    title_bar = review_dock.titleBarWidget()
    assert isinstance(title_bar, _DockTitleBar)
    available = QRect(0, 0, 1920, 1080)

    assert title_bar._screen_edge_geometry(QPoint(960, 0), available) == QRect()
    assert title_bar._screen_edge_geometry(QPoint(0, 540), available) == QRect(
        0,
        0,
        960,
        1080,
    )
    assert title_bar._screen_edge_geometry(QPoint(1919, 0), available) == QRect(
        960,
        0,
        960,
        540,
    )
    assert title_bar._screen_edge_geometry(QPoint(960, 540), available) is None


@pytest.mark.integration
def test_dock_title_bar_propagates_drag_events_to_qdockwidget(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path)
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    assert review_dock is not None
    title_bar = review_dock.titleBarWidget()
    assert isinstance(title_bar, _DockTitleBar)
    press = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(20, 10),
        QPointF(200, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(21, 10),
        QPointF(201, 100),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(20, 10),
        QPointF(200, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    title_bar.mousePressEvent(press)
    title_bar.mouseMoveEvent(move)
    title_bar.mouseReleaseEvent(release)

    assert not press.isAccepted()
    assert not move.isAccepted()
    assert not release.isAccepted()


@pytest.mark.integration
def test_floating_panel_has_consistent_docking_fallback(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    settings = AppSettings(data_directory=tmp_path)
    _application, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.resize(1200, 800)
    window.show()
    review_dock = window.findChild(QDockWidget, "humanReviewDock")
    assert review_dock is not None
    title_bar = review_dock.titleBarWidget()
    assert isinstance(title_bar, _DockTitleBar)

    for x, expected_area in (
        (window.contentsRect().left() + 5, Qt.DockWidgetArea.LeftDockWidgetArea),
        (window.contentsRect().right() - 5, Qt.DockWidgetArea.RightDockWidgetArea),
    ):
        review_dock.setFloating(True)
        qtbot.waitUntil(review_dock.isFloating)
        drop_position = window.mapToGlobal(QPoint(x, window.contentsRect().center().y()))

        title_bar._finish_drag(drop_position, allow_docking=True)

        assert not review_dock.isFloating()
        assert window.dockWidgetArea(review_dock) == expected_area


@pytest.mark.integration
def test_application_smoke_mode_opens_and_closes(tmp_path: Path) -> None:
    settings = AppSettings(data_directory=tmp_path)

    exit_code = run(["zeny-project-handler", "--smoke-test"], settings=settings)

    assert exit_code == 0
    moved_database = tmp_path / "closed.sqlite3"
    settings.database_path.replace(moved_database)
    moved_database.unlink()
    assert not moved_database.exists()


@pytest.mark.integration
def test_engine_lifetime_disposes_once_and_bootstrap_failure_disposes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = Mock()
    lifetime = _EngineLifetime(engine)

    lifetime.dispose()
    lifetime.dispose(object())

    engine.dispose.assert_called_once_with()
    failed_engine = Mock()
    monkeypatch.setattr(bootstrap, "initialize_local_storage", lambda _settings: failed_engine)

    def fail_composition(*_args: object) -> None:
        raise RuntimeError("composição interrompida")

    monkeypatch.setattr(bootstrap, "_compose_initialized_application", fail_composition)
    with pytest.raises(RuntimeError, match="interrompida"):
        bootstrap._compose_application([], AppSettings(data_directory=tmp_path))
    failed_engine.dispose.assert_called_once_with()


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
