from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QToolButton
from pytestqt.qtbot import QtBot

from zeny_project_handler.ui.theme import aplicar_tema

pytestmark = pytest.mark.integration


def test_theme_keeps_disabled_inputs_distinct_and_tool_buttons_compact(
    qtbot: QtBot,
    qapp: QApplication,
) -> None:
    aplicar_tema(qapp)
    line_edit = QLineEdit()
    combo = QComboBox()
    action = QPushButton("Ação")
    tool = QToolButton()
    for widget in (line_edit, combo, action, tool):
        qtbot.addWidget(widget)
        widget.ensurePolished()

    for widget in (line_edit, combo):
        widget.setEnabled(False)
        widget.ensurePolished()
        assert widget.palette().color(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
        ) == QColor("#94a3b8")
        assert widget.palette().color(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Base,
        ) == QColor("#f8fafc")

    assert tool.minimumSizeHint().height() <= action.minimumSizeHint().height()


def test_theme_orders_interaction_states_before_disabled_override(
    qapp: QApplication,
) -> None:
    original_font = qapp.font()
    preferred_font = QFont(original_font)
    preferred_font.setPointSize(13)
    qapp.setFont(preferred_font)
    try:
        aplicar_tema(qapp)
        stylesheet = qapp.styleSheet()

        assert qapp.font().pointSize() == 13
        assert "\nQWidget {\n" not in stylesheet
        disabled = stylesheet.index("QPushButton:disabled")
        for selector in (
            'QPushButton[role="primary"]:pressed',
            'QPushButton[role="danger"]:pressed',
            'QPushButton[role="quiet"]:pressed',
            "QPushButton:focus, QToolButton:focus",
        ):
            assert selector in stylesheet
            assert stylesheet.index(selector) < disabled
    finally:
        qapp.setFont(original_font)
