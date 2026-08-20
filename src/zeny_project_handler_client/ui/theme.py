"""Temas claro e escuro do cliente."""

from __future__ import annotations

from enum import StrEnum

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


class Tema(StrEnum):
    """Temas que podem ser escolhidos e persistidos pela interface."""

    CLARO = "claro"
    ESCURO = "escuro"


THEME_SETTING_KEY = "appearance/theme"


def aplicar_tema(application: QApplication, tema: Tema | str = Tema.CLARO) -> Tema:
    """Aplique imediatamente um tema válido, usando Claro como fallback seguro."""
    tema_normalizado = _normalizar_tema(tema)
    if application.style().objectName().casefold() != "fusion":
        application.setStyle("Fusion")
    application.setPalette(_palette(tema_normalizado))
    application.setStyleSheet(_STYLE_SHEETS[tema_normalizado])
    application.setProperty("zenyTheme", tema_normalizado.value)
    return tema_normalizado


def _normalizar_tema(tema: Tema | str | object) -> Tema:
    try:
        return Tema(str(tema).strip().lower())
    except ValueError:
        return Tema.CLARO


def _palette(tema: Tema) -> QPalette:
    colors = _PALETTE_COLORS[tema]
    palette = QPalette()
    for role, value in colors["active"].items():
        palette.setColor(role, QColor(value))
    for role, value in colors["disabled"].items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(value))
    return palette


_LIGHT_PALETTE = {
    "active": {
        QPalette.ColorRole.Window: "#f4f7fb",
        QPalette.ColorRole.WindowText: "#172033",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#f8fafc",
        QPalette.ColorRole.ToolTipBase: "#172033",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.Text: "#172033",
        QPalette.ColorRole.Button: "#ffffff",
        QPalette.ColorRole.ButtonText: "#24324a",
        QPalette.ColorRole.BrightText: "#b42318",
        QPalette.ColorRole.Highlight: "#2563eb",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: "#1d4ed8",
        QPalette.ColorRole.LinkVisited: "#6d28d9",
        QPalette.ColorRole.PlaceholderText: "#64748b",
    },
    "disabled": {
        QPalette.ColorRole.WindowText: "#64748b",
        QPalette.ColorRole.Base: "#f8fafc",
        QPalette.ColorRole.Text: "#64748b",
        QPalette.ColorRole.Button: "#f8fafc",
        QPalette.ColorRole.ButtonText: "#64748b",
        QPalette.ColorRole.Highlight: "#cbd5e1",
        QPalette.ColorRole.HighlightedText: "#475569",
        QPalette.ColorRole.PlaceholderText: "#94a3b8",
    },
}

_DARK_PALETTE = {
    "active": {
        QPalette.ColorRole.Window: "#111827",
        QPalette.ColorRole.WindowText: "#e5edf8",
        QPalette.ColorRole.Base: "#182235",
        QPalette.ColorRole.AlternateBase: "#1d293d",
        QPalette.ColorRole.ToolTipBase: "#eef4ff",
        QPalette.ColorRole.ToolTipText: "#111827",
        QPalette.ColorRole.Text: "#e5edf8",
        QPalette.ColorRole.Button: "#22304a",
        QPalette.ColorRole.ButtonText: "#edf3fb",
        QPalette.ColorRole.BrightText: "#fca5a5",
        QPalette.ColorRole.Highlight: "#60a5fa",
        QPalette.ColorRole.HighlightedText: "#0b1220",
        QPalette.ColorRole.Link: "#93c5fd",
        QPalette.ColorRole.LinkVisited: "#c4b5fd",
        QPalette.ColorRole.PlaceholderText: "#a9b7ca",
    },
    "disabled": {
        QPalette.ColorRole.WindowText: "#94a3b8",
        QPalette.ColorRole.Base: "#1b2639",
        QPalette.ColorRole.Text: "#94a3b8",
        QPalette.ColorRole.Button: "#1b2639",
        QPalette.ColorRole.ButtonText: "#94a3b8",
        QPalette.ColorRole.Highlight: "#334155",
        QPalette.ColorRole.HighlightedText: "#94a3b8",
        QPalette.ColorRole.PlaceholderText: "#718096",
    },
}

_PALETTE_COLORS = {
    Tema.CLARO: _LIGHT_PALETTE,
    Tema.ESCURO: _DARK_PALETTE,
}


_LIGHT_STYLE_SHEET = """
QMainWindow, QDialog {
    background: #f4f7fb;
    color: #172033;
}
QMenuBar, QMenu, QStatusBar {
    background: #ffffff;
    color: #172033;
    border-color: #dce4ef;
}
QMenuBar {
    border-bottom: 1px solid #dce4ef;
}
QMenuBar::item, QMenu::item {
    padding: 6px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #eaf2ff;
    color: #174ea6;
}
QMenuBar::item:disabled, QMenu::item:disabled {
    color: #64748b;
}
QMenu::separator {
    height: 1px;
    background: #dce4ef;
    margin: 4px 8px;
}
QStatusBar {
    border-top: 1px solid #dce4ef;
}
QStatusBar::item {
    border: 0;
}
QDockWidget {
    color: #172033;
    font-weight: 600;
}
QDockWidget > QWidget {
    font-weight: 400;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #dce4ef;
    border-radius: 9px;
    margin-top: 12px;
    padding-top: 9px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 11px;
    padding: 0 5px;
    color: #334155;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    min-height: 30px;
    padding: 0 11px;
    color: #24324a;
}
QToolButton {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
    padding: 1px 4px;
    color: #24324a;
}
QPushButton:hover, QToolButton:hover {
    background: #f1f5f9;
    border-color: #94a3b8;
}
QPushButton:pressed, QToolButton:pressed {
    background: #e2e8f0;
}
QToolButton:checked {
    background: #dbeafe;
    border-color: #2563eb;
    color: #174ea6;
    font-weight: 600;
}
QPushButton[role="primary"] {
    background: #2563eb;
    border-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[role="primary"]:hover {
    background: #1d4ed8;
    border-color: #1d4ed8;
}
QPushButton[role="primary"]:pressed {
    background: #1e40af;
    border-color: #1e40af;
}
QPushButton[role="danger"] {
    color: #b42318;
    border-color: #f2b8b5;
    background: #fffafa;
}
QPushButton[role="danger"]:hover {
    background: #fff0ef;
    border-color: #dc6b64;
}
QPushButton[role="danger"]:pressed {
    background: #fee2e2;
    border-color: #b42318;
}
QPushButton[role="quiet"] {
    background: transparent;
    border-color: transparent;
    color: #475569;
}
QPushButton[role="quiet"]:hover {
    background: #f1f5f9;
    border-color: transparent;
}
QPushButton[role="quiet"]:pressed {
    background: #e2e8f0;
    border-color: transparent;
}
QPushButton:focus, QToolButton:focus {
    border: 2px solid #2563eb;
}
QPushButton[role="primary"]:focus {
    border-color: #bfdbfe;
}
QPushButton:disabled, QToolButton:disabled,
QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled,
QPushButton[role="quiet"]:disabled {
    background: #f8fafc;
    border-color: #e2e8f0;
    color: #64748b;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit,
QTextBrowser, QListWidget, QTreeWidget, QTableWidget {
    background: #ffffff;
    color: #172033;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QTextEdit:disabled, QPlainTextEdit:disabled, QTextBrowser:disabled,
QListWidget:disabled, QTreeWidget:disabled, QTableWidget:disabled {
    background: #f8fafc;
    border-color: #e2e8f0;
    color: #64748b;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    min-height: 30px;
    padding: 0 7px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QListWidget:focus,
QTreeWidget:focus, QTableWidget:focus {
    border: 1px solid #2563eb;
}
QAbstractItemView::item:hover {
    background: #eef5ff;
}
QHeaderView::section {
    background: #eef3f8;
    color: #334155;
    border: 0;
    border-right: 1px solid #dce4ef;
    border-bottom: 1px solid #dce4ef;
    padding: 7px;
    font-weight: 600;
}
QTabWidget::pane {
    background: #ffffff;
    border: 1px solid #dce4ef;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #64748b;
    padding: 8px 13px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover {
    background: #f1f5f9;
    color: #334155;
}
QTabBar::tab:selected {
    color: #1d4ed8;
    border-bottom-color: #2563eb;
    font-weight: 600;
}
QTabBar::tab:disabled {
    color: #94a3b8;
}
QProgressBar {
    background: #e8eef6;
    color: #172033;
    border: 0;
    border-radius: 5px;
    min-height: 18px;
    max-height: 18px;
    text-align: center;
}
QProgressBar::chunk {
    background: #2563eb;
    border-radius: 5px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #eef3f8;
    border: 0;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #94a3b8;
    border-radius: 5px;
    min-height: 22px;
    min-width: 22px;
}
QScrollBar::handle:hover {
    background: #64748b;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QSplitter::handle {
    background: #dce4ef;
}
QLabel[role="summary"], QLabel[role="hint"] {
    border-radius: 7px;
    padding: 9px 10px;
}
QLabel[role="summary"] {
    background: #eef5ff;
    border: 1px solid #d6e6ff;
    color: #24446f;
}
QLabel[role="hint"] {
    background: #f8fafc;
    color: #5b6b82;
}
QToolTip {
    background: #172033;
    color: #ffffff;
    border: 1px solid #334155;
    padding: 5px;
}
"""


_DARK_STYLE_SHEET = """
QMainWindow, QDialog {
    background: #111827;
    color: #e5edf8;
}
QMenuBar, QMenu, QStatusBar {
    background: #182235;
    color: #e5edf8;
    border-color: #334155;
}
QMenuBar {
    border-bottom: 1px solid #334155;
}
QMenuBar::item, QMenu::item {
    padding: 6px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #27466f;
    color: #eff6ff;
}
QMenuBar::item:disabled, QMenu::item:disabled {
    color: #94a3b8;
}
QMenu::separator {
    height: 1px;
    background: #334155;
    margin: 4px 8px;
}
QStatusBar {
    border-top: 1px solid #334155;
}
QStatusBar::item {
    border: 0;
}
QDockWidget {
    color: #e5edf8;
    font-weight: 600;
}
QDockWidget > QWidget {
    font-weight: 400;
}
QGroupBox {
    background: #182235;
    border: 1px solid #334155;
    border-radius: 9px;
    margin-top: 12px;
    padding-top: 9px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 11px;
    padding: 0 5px;
    color: #cbd5e1;
}
QPushButton {
    background: #22304a;
    border: 1px solid #475569;
    border-radius: 7px;
    min-height: 30px;
    padding: 0 11px;
    color: #edf3fb;
}
QToolButton {
    background: #22304a;
    border: 1px solid #475569;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
    padding: 1px 4px;
    color: #edf3fb;
}
QPushButton:hover, QToolButton:hover {
    background: #2b3b57;
    border-color: #64748b;
}
QPushButton:pressed, QToolButton:pressed {
    background: #344762;
}
QToolButton:checked {
    background: #1e3a5f;
    border-color: #60a5fa;
    color: #dbeafe;
    font-weight: 600;
}
QPushButton[role="primary"] {
    background: #2563eb;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[role="primary"]:hover {
    background: #1d4ed8;
    border-color: #60a5fa;
}
QPushButton[role="primary"]:pressed {
    background: #1e40af;
    border-color: #3b82f6;
}
QPushButton[role="danger"] {
    color: #fecaca;
    border-color: #9f4b55;
    background: #321d25;
}
QPushButton[role="danger"]:hover {
    background: #48232d;
    border-color: #f87171;
}
QPushButton[role="danger"]:pressed {
    background: #5f2733;
    border-color: #fca5a5;
}
QPushButton[role="quiet"] {
    background: transparent;
    border-color: transparent;
    color: #cbd5e1;
}
QPushButton[role="quiet"]:hover {
    background: #22304a;
    border-color: transparent;
}
QPushButton[role="quiet"]:pressed {
    background: #2b3b57;
    border-color: transparent;
}
QPushButton:focus, QToolButton:focus {
    border: 2px solid #60a5fa;
}
QPushButton[role="primary"]:focus {
    border-color: #bfdbfe;
}
QPushButton:disabled, QToolButton:disabled,
QPushButton[role="primary"]:disabled, QPushButton[role="danger"]:disabled,
QPushButton[role="quiet"]:disabled {
    background: #1b2639;
    border-color: #334155;
    color: #94a3b8;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit,
QTextBrowser, QListWidget, QTreeWidget, QTableWidget {
    background: #182235;
    color: #e5edf8;
    border: 1px solid #475569;
    border-radius: 7px;
    selection-background-color: #60a5fa;
    selection-color: #0b1220;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QTextEdit:disabled, QPlainTextEdit:disabled, QTextBrowser:disabled,
QListWidget:disabled, QTreeWidget:disabled, QTableWidget:disabled {
    background: #1b2639;
    border-color: #334155;
    color: #94a3b8;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    min-height: 30px;
    padding: 0 7px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTextEdit:focus, QPlainTextEdit:focus, QTextBrowser:focus, QListWidget:focus,
QTreeWidget:focus, QTableWidget:focus {
    border: 1px solid #60a5fa;
}
QAbstractItemView::item:hover {
    background: #223a5c;
}
QHeaderView::section {
    background: #22304a;
    color: #dbe5f3;
    border: 0;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
    padding: 7px;
    font-weight: 600;
}
QTabWidget::pane {
    background: #182235;
    border: 1px solid #334155;
    border-radius: 8px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #a9b7ca;
    padding: 8px 13px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover {
    background: #22304a;
    color: #e5edf8;
}
QTabBar::tab:selected {
    color: #bfdbfe;
    border-bottom-color: #60a5fa;
    font-weight: 600;
}
QTabBar::tab:disabled {
    color: #718096;
}
QProgressBar {
    background: #26354e;
    color: #e5edf8;
    border: 0;
    border-radius: 5px;
    min-height: 18px;
    max-height: 18px;
    text-align: center;
}
QProgressBar::chunk {
    background: #3b82f6;
    border-radius: 5px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #172033;
    border: 0;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #475569;
    border-radius: 5px;
    min-height: 22px;
    min-width: 22px;
}
QScrollBar::handle:hover {
    background: #64748b;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QSplitter::handle {
    background: #334155;
}
QLabel[role="summary"], QLabel[role="hint"] {
    border-radius: 7px;
    padding: 9px 10px;
}
QLabel[role="summary"] {
    background: #1d3555;
    border: 1px solid #31527c;
    color: #dbeafe;
}
QLabel[role="hint"] {
    background: #1b2639;
    color: #b6c3d5;
}
QToolTip {
    background: #eef4ff;
    color: #111827;
    border: 1px solid #cbd5e1;
    padding: 5px;
}
"""


_STYLE_SHEETS = {
    Tema.CLARO: _LIGHT_STYLE_SHEET,
    Tema.ESCURO: _DARK_STYLE_SHEET,
}
