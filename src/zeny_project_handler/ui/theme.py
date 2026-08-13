"""Identidade visual leve e centralizada da aplicação."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def aplicar_tema(application: QApplication) -> None:
    """Aplique uma aparência consistente sem alterar o comportamento dos widgets."""
    application.setStyle("Fusion")

    palette = application.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f4f7fb"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#172033"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#172033"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#24324a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#94a3b8"))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#94a3b8"),
    )
    application.setPalette(palette)
    application.setStyleSheet(_STYLE_SHEET)


_STYLE_SHEET = """
QMainWindow, QDialog {
    background: #f4f7fb;
}
QMenuBar, QMenu, QStatusBar {
    background: #ffffff;
    border-color: #dce4ef;
}
QMenuBar {
    border-bottom: 1px solid #dce4ef;
}
QMenuBar::item {
    padding: 6px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #eaf2ff;
    color: #174ea6;
}
QStatusBar {
    border-top: 1px solid #dce4ef;
}
QDockWidget {
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
    color: #94a3b8;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit,
QTextBrowser, QListWidget, QTreeWidget, QTableWidget {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 7px;
    selection-background-color: #dbeafe;
    selection-color: #172033;
}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QTextEdit:disabled, QPlainTextEdit:disabled, QTextBrowser:disabled,
QListWidget:disabled, QTreeWidget:disabled, QTableWidget:disabled {
    background: #f8fafc;
    border-color: #e2e8f0;
    color: #94a3b8;
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
QTabBar::tab:selected {
    color: #1d4ed8;
    border-bottom-color: #2563eb;
    font-weight: 600;
}
QProgressBar {
    background: #e8eef6;
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
    border: 0;
    padding: 5px;
}
"""
