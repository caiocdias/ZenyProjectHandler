"""Regressões de rolagem com widgets reais e conteúdo sintético, sem rede externa."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory
from tests.pdf_fixtures import create_feature_pdf

from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui.main_window import MainWindow
from zeny_project_handler_client.ui.panel_scroll import PanelScrollArea
from zeny_project_handler_client.ui.theme import Tema, aplicar_tema

pytestmark = pytest.mark.integration
DOCKS = (
    "projectWorkflowDock",
    "humanReviewDock",
    "documentationComplianceDock",
    "gmaxDock",
    "projectExportDock",
)


def _area(window: MainWindow, name: str) -> tuple[QDockWidget, PanelScrollArea]:
    dock = window.findChild(QDockWidget, name)
    assert dock is not None
    area = dock.widget()
    assert isinstance(area, PanelScrollArea)
    return dock, area


def _wheel(widget: QWidget, delta: int = -120, *, pixels: bool = False) -> None:
    position = widget.rect().center()
    event = QWheelEvent(
        QPointF(position),
        QPointF(widget.mapToGlobal(position)),
        QPoint(0, delta) if pixels else QPoint(),
        QPoint() if pixels else QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(widget, event)


def _extensive(panel: QWidget) -> None:
    for tree in panel.findChildren(QTreeWidget):
        tree.blockSignals(True)
        tree.clear()
        for row in range(150):
            QTreeWidgetItem(
                tree,
                [f"Item sintético {row:03d} — coluna {col}" for col in range(tree.columnCount())],
            )
        tree.blockSignals(False)
    for table in panel.findChildren(QTableWidget):
        table.blockSignals(True)
        if table.objectName() != "gmaxChecksTable":
            table.setRowCount(150)
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                table.setItem(row, col, QTableWidgetItem(f"Resultado {row:03d} — coluna {col}"))
        table.blockSignals(False)
    for listing in panel.findChildren(QListWidget):
        listing.blockSignals(True)
        listing.addItems([f"Folha / serviço sintético {row:03d}" for row in range(150)])
        listing.blockSignals(False)
    for label in panel.findChildren(QLabel):
        if label.wordWrap():
            label.setText(
                "Conteúdo sintético extenso para verificar leitura e quebra de linhas. " * 3
            )
    for browser in panel.findChildren(QTextBrowser):
        browser.setPlainText("Regra sintética com detalhes acessíveis.\n" * 150)


@pytest.mark.parametrize("name", DOCKS)
def test_each_dock_scrolls_independently_and_reveals_keyboard_focus(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
    name: str,
) -> None:
    app, window = application_factory([], settings=ClientSettings(data_directory=tmp_path))
    qtbot.addWidget(window)
    window.resize(1000, 580)
    window.show()
    dock, area = _area(window, name)
    dock.setFloating(True)
    dock.resize(480, 300)
    source = create_feature_pdf(tmp_path / "scroll.pdf")
    window.pdf_viewer.carregar_pdf(source)
    qtbot.waitUntil(lambda: window.pdf_viewer.inspecao is not None)
    panel = area.widget()
    assert panel is not None
    _extensive(panel)
    for button in panel.findChildren(QPushButton):
        button.setEnabled(True)
    dock.raise_()
    app.processEvents()
    qtbot.waitUntil(lambda: area.verticalScrollBar().maximum() > 0)
    positions = [_area(window, other)[1].verticalScrollBar().value() for other in DOCKS]
    transform = window.pdf_viewer.view.transform()
    scene_position = window.pdf_viewer.view.mapToScene(QPoint(0, 0))
    _wheel(area.viewport())
    assert area.verticalScrollBar().value() > 0
    for other, position in zip(DOCKS, positions, strict=True):
        if other != name:
            assert _area(window, other)[1].verticalScrollBar().value() == position
    assert window.pdf_viewer.view.transform() == transform
    assert window.pdf_viewer.view.mapToScene(QPoint(0, 0)) == scene_position

    # Percorre a ordem real de Tab, inclusive ações após tabelas e cartões.
    dock.activateWindow()
    qtbot.waitUntil(dock.isActiveWindow)
    area.setFocus()
    qtbot.waitUntil(area.hasFocus)
    visited: set[str] = set()
    for _ in range(100):
        qtbot.keyClick(QApplication.focusWidget() or area, Qt.Key.Key_Tab)  # type: ignore[no-untyped-call]
        app.processEvents()
        focus = QApplication.focusWidget()
        if focus is not None and panel.isAncestorOf(focus):
            visited.add(focus.objectName())
            if isinstance(focus, QAbstractItemView) and focus.currentIndex().isValid():
                center = focus.viewport().mapTo(
                    area.viewport(), focus.visualRect(focus.currentIndex()).center()
                )
            else:
                center = focus.mapTo(area.viewport(), focus.rect().center())
            assert area.viewport().rect().contains(center), focus.objectName()
    expected = {
        "projectWorkflowDock": "mvpAcceptanceGuideButton",
        "humanReviewDock": "analysisRelationshipTree",
        "documentationComplianceDock": "documentationRefreshButton",
        "gmaxDock": "gmaxChecksTable",
        "projectExportDock": "exportComplianceButton",
    }
    assert expected[name] in visited


def test_market_actions_reflow_and_recover_width(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    app, window = application_factory([], settings=ClientSettings(data_directory=tmp_path))
    qtbot.addWidget(window)
    window.show()
    dock, area = _area(window, "projectWorkflowDock")
    dock.setFloating(True)
    panel = area.widget()
    assert panel is not None
    buttons = [
        panel.findChild(QPushButton, name)
        for name in ("projectMarketSave", "projectMarketCancel", "projectMarketRefresh")
    ]
    assert all(button is not None for button in buttons)
    for width in (350, 800, 350):
        dock.resize(width, 450)
        app.processEvents()
        visible_buttons = [button for button in buttons if button is not None]
        assert all(button.width() >= button.minimumSizeHint().width() for button in visible_buttons)
        assert area.horizontalScrollBar().maximum() == 0
        rows = {button.y() for button in visible_buttons}
        assert len(rows) == (3 if width == 350 else 1)
        status = panel.findChild(QLabel, "projectMarketStatus")
        assert status is not None
        assert max(button.geometry().bottom() for button in visible_buttons) < status.y()


@pytest.mark.parametrize("pixels", [False, True])
def test_wheel_preserves_closed_controls_and_chains_at_table_and_text_edges(
    qtbot: QtBot,
    pixels: bool,
) -> None:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    combo = QComboBox()
    combo.addItems(["Rural", "Urbano", "Ambos"])
    spin = QDoubleSpinBox()
    table = QTableWidget(200, 2)
    text = QTextBrowser()
    text.setPlainText("Detalhes\n" * 200)
    for widget in (combo, spin, table, text, QPushButton("Ação final")):
        layout.addWidget(widget)
    area = PanelScrollArea(panel, "Teste")
    qtbot.addWidget(area)
    area.resize(420, 240)
    area.show()
    qtbot.waitUntil(lambda: area.verticalScrollBar().maximum() > 0)
    for control in (combo, spin):
        control.setFocus()
        area.verticalScrollBar().setValue(0)
        _wheel(control, -40 if pixels else -120, pixels=pixels)
        assert area.verticalScrollBar().value() > 0
    assert combo.currentIndex() == 0
    assert spin.value() == 0
    for nested in (table, text):
        area.ensureWidgetVisible(nested)
        outer = area.verticalScrollBar().value()
        nested.verticalScrollBar().setValue(0)
        _wheel(nested.viewport())
        assert nested.verticalScrollBar().value() > 0
        assert area.verticalScrollBar().value() == outer
        nested.verticalScrollBar().setValue(nested.verticalScrollBar().maximum())
        area.verticalScrollBar().setValue(0)
        _wheel(nested.viewport())
        assert area.verticalScrollBar().value() > 0
        nested.verticalScrollBar().setValue(0)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        outer = area.verticalScrollBar().value()
        _wheel(nested.viewport(), 120)
        assert area.verticalScrollBar().value() < outer
        assert nested.height() <= nested.maximumHeight() < 500
    combo.showPopup()
    qtbot.waitUntil(combo.view().isVisible)
    outer = area.verticalScrollBar().value()
    _wheel(combo.view().viewport())
    assert area.verticalScrollBar().value() == outer
    combo.hidePopup()


def test_floating_tabbed_and_saved_docks_keep_identity(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    settings = ClientSettings(data_directory=tmp_path)
    app, window = application_factory([], settings=settings)
    qtbot.addWidget(window)
    window.show()
    for name in DOCKS:
        dock, area = _area(window, name)
        dock.setFloating(True)
        dock.resize(460, 300)
        app.processEvents()
        assert area.height() < 300
        dock.setFloating(False)
    review, _ = _area(window, "humanReviewDock")
    docs, _ = _area(window, "documentationComplianceDock")
    window.tabifyDockWidget(review, docs)
    docs.raise_()
    gmax, _ = _area(window, "gmaxDock")
    gmax.setFloating(True)
    gmax.resize(480, 330)
    window.close()
    app.processEvents()
    _, restored = application_factory([], settings=settings)
    qtbot.addWidget(restored)
    restored.show()
    assert _area(restored, "gmaxDock")[0].isFloating()
    assert _area(restored, "documentationComplianceDock")[0] in restored.tabifiedDockWidgets(
        _area(restored, "humanReviewDock")[0]
    )


def test_reduced_window_keeps_pdf_controls_and_dock_layout_after_resize(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
) -> None:
    app, window = application_factory([], settings=ClientSettings(data_directory=tmp_path))
    qtbot.addWidget(window)
    window.show()
    state = window.saveState()
    wide = (
        min(1920, window.screen().availableGeometry().width())
        if app.platformName() == "windows"
        else 1920
    )
    for width in (911, wide, 911):
        window.resize(width, 512)
        app.processEvents()
        assert window.width() == width
        viewer = window.pdf_viewer
        assert viewer.view.viewport().width() >= 330
        assert viewer.view.viewport().height() >= 200
        buttons = viewer.findChildren(QPushButton)
        for button in buttons:
            assert button.width() >= button.minimumSizeHint().width()
            assert viewer.rect().contains(button.geometry())
            assert button.geometry().bottom() < viewer.view.y()
        for index, button in enumerate(buttons):
            assert all(
                not button.geometry().intersects(other.geometry()) for other in buttons[index + 1 :]
            )
        assert window.restoreState(state)
        assert all(not _area(window, name)[0].isFloating() for name in DOCKS)


@pytest.mark.parametrize("resolution", [(1366, 768), (1920, 1080)])
@pytest.mark.parametrize("theme", list(Tema))
def test_visual_matrix(
    qtbot: QtBot,
    tmp_path: Path,
    application_factory: ApplicationFactory,
    resolution: tuple[int, int],
    theme: Tema,
) -> None:
    app, window = application_factory([], settings=ClientSettings(data_directory=tmp_path))
    qtbot.addWidget(window)
    aplicar_tema(app, theme)
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    width, height = (round(value / scale) for value in resolution)
    window.resize(width, height)
    window.show()
    window.pdf_viewer.carregar_pdf(create_feature_pdf(tmp_path / "visual-scroll.pdf"))
    qtbot.waitUntil(lambda: window.pdf_viewer.inspecao is not None)
    output = os.environ.get("E05_CAPTURE_DIR")
    compressed: list[str] = []
    clipped_labels: list[str] = []
    for name in DOCKS:
        dock, area = _area(window, name)
        panel = area.widget()
        assert panel is not None
        dock.raise_()
        for state in ("empty", "extensive", "loading", "error"):
            if state == "extensive":
                _extensive(panel)
            elif state in ("loading", "error"):
                for label in panel.findChildren(QLabel):
                    if label.wordWrap():
                        label.setText(
                            (
                                "Carregando dados… "
                                if state == "loading"
                                else "Falha sintética. Atualize para tentar novamente. "
                            )
                            * 3
                        )
            app.processEvents()
            qtbot.wait(30)
            for card in panel.findChildren(QGroupBox):
                if card.isVisible() and card.height() < card.minimumSizeHint().height():
                    compressed.append(f"{name}/{state}: {card.title()}")
            tabs = panel.findChildren(QTabWidget)
            pages = range(tabs[0].count()) if tabs else range(1)
            for page in pages:
                if tabs:
                    tabs[0].setCurrentIndex(page)
                app.processEvents()
                for label in panel.findChildren(QLabel):
                    if (
                        label.isVisible()
                        and label.wordWrap()
                        and label.height() < label.heightForWidth(label.width())
                    ):
                        clipped_labels.append(f"{name}/{state}/{page}: {label.objectName()}")
                for edge in ("top", "bottom"):
                    app.processEvents()
                    area.verticalScrollBar().setValue(
                        0 if edge == "top" else area.verticalScrollBar().maximum()
                    )
                    app.processEvents()
                    if output:
                        directory = (
                            Path(output)
                            / f"{resolution[0]}x{resolution[1]}-{scale:g}-{theme.value}"
                        )
                        directory.mkdir(parents=True, exist_ok=True)
                        assert window.grab().save(
                            str(directory / f"{name}-{state}-{page}-{edge}.png")
                        )
                        panel_directory = directory / "panels"
                        panel_directory.mkdir(exist_ok=True)
                        assert dock.grab().save(
                            str(panel_directory / f"{name}-{state}-{page}-{edge}.png")
                        )
    if output:
        screen = window.screen()
        metadata = {
            "platform": app.platformName(),
            "requested_logical": [width, height],
            "actual_logical": [window.width(), window.height()],
            "device_pixel_ratio": window.devicePixelRatioF(),
            "screen_logical_dpi": screen.logicalDotsPerInch(),
            "central_minimum_width": window.pdf_viewer.minimumSizeHint().width(),
            "compressed_cards": compressed,
            "clipped_labels": clipped_labels,
            "pdf_viewport": [
                window.pdf_viewer.view.viewport().width(),
                window.pdf_viewer.view.viewport().height(),
            ],
        }
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    assert not compressed
    assert not clipped_labels
    assert window.size().width() == width
    assert window.pdf_viewer.view.viewport().width() >= 330
    assert window.pdf_viewer.view.viewport().height() >= 200
    # O Windows reserva a moldura nativa quando o tamanho pedido ocupa a tela inteira.
    if app.platformName() == "windows":
        assert height - 40 <= window.height() <= height
    else:
        assert window.height() == height
