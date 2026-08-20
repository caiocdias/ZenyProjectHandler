from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QToolButton
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui.theme import Tema, aplicar_tema

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("theme", "disabled_text", "disabled_base"),
    [
        (Tema.CLARO, QColor("#64748b"), QColor("#f8fafc")),
        (Tema.ESCURO, QColor("#94a3b8"), QColor("#1b2639")),
    ],
)
def test_theme_keeps_disabled_inputs_distinct_and_tool_buttons_compact(
    qtbot: QtBot,
    qapp: QApplication,
    theme: Tema,
    disabled_text: QColor,
    disabled_base: QColor,
) -> None:
    aplicar_tema(qapp, theme)
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
        assert (
            widget.palette().color(
                QPalette.ColorGroup.Disabled,
                QPalette.ColorRole.Text,
            )
            == disabled_text
        )
        assert (
            widget.palette().color(
                QPalette.ColorGroup.Disabled,
                QPalette.ColorRole.Base,
            )
            == disabled_base
        )

    assert tool.minimumSizeHint().height() <= action.minimumSizeHint().height()


def test_light_and_dark_palettes_are_distinct_and_legible(qapp: QApplication) -> None:
    palette_signatures: list[tuple[str, ...]] = []
    for theme in Tema:
        assert aplicar_tema(qapp, theme) is theme
        palette = qapp.palette()
        assert (
            _contrast(
                palette.color(QPalette.ColorRole.WindowText),
                palette.color(QPalette.ColorRole.Window),
            )
            >= 4.5
        )
        assert (
            _contrast(
                palette.color(QPalette.ColorRole.Text),
                palette.color(QPalette.ColorRole.Base),
            )
            >= 4.5
        )
        assert (
            _contrast(
                palette.color(QPalette.ColorRole.HighlightedText),
                palette.color(QPalette.ColorRole.Highlight),
            )
            >= 4.5
        )
        assert (
            _contrast(
                palette.color(QPalette.ColorRole.ButtonText),
                palette.color(QPalette.ColorRole.Button),
            )
            >= 4.5
        )
        assert (
            _contrast(
                palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text),
                palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base),
            )
            >= 3.0
        )
        assert (
            _contrast(
                palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText),
                palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button),
            )
            >= 3.0
        )
        assert qapp.property("zenyTheme") == theme.value
        palette_signatures.append(
            tuple(
                palette.color(role).name()
                for role in (
                    QPalette.ColorRole.Window,
                    QPalette.ColorRole.WindowText,
                    QPalette.ColorRole.Base,
                    QPalette.ColorRole.Highlight,
                    QPalette.ColorRole.Button,
                )
            )
        )

    assert palette_signatures[0] != palette_signatures[1]


@pytest.mark.parametrize("theme", list(Tema))
def test_theme_orders_interaction_states_before_disabled_override(
    qapp: QApplication,
    theme: Tema,
) -> None:
    original_font = qapp.font()
    preferred_font = QFont(original_font)
    preferred_font.setPointSize(13)
    qapp.setFont(preferred_font)
    try:
        aplicar_tema(qapp, theme)
        stylesheet = qapp.styleSheet()

        assert qapp.font().pointSize() == 13
        assert "\nQWidget {\n" not in stylesheet
        disabled = stylesheet.index("QPushButton:disabled")
        for selector in (
            'QPushButton[role="primary"]:pressed',
            'QPushButton[role="danger"]:pressed',
            'QPushButton[role="quiet"]:pressed',
            "QToolButton:checked",
            "QPushButton:focus, QToolButton:focus",
        ):
            assert selector in stylesheet
            assert stylesheet.index(selector) < disabled
        for selector in (
            "QMenuBar::item:disabled, QMenu::item:disabled",
            "QAbstractItemView::item:hover",
            "QTabBar::tab:disabled",
            "QScrollBar::handle:hover",
            "QToolTip",
        ):
            assert selector in stylesheet
    finally:
        qapp.setFont(original_font)


def test_invalid_theme_falls_back_to_light_without_error(qapp: QApplication) -> None:
    aplicar_tema(qapp, Tema.ESCURO)

    selected = aplicar_tema(qapp, "valor-invalido")

    assert selected is Tema.CLARO
    assert qapp.property("zenyTheme") == Tema.CLARO.value
    assert qapp.palette().color(QPalette.ColorRole.Window) == QColor("#f4f7fb")


def _contrast(foreground: QColor, background: QColor) -> float:
    lighter = max(_luminance(foreground), _luminance(background))
    darker = min(_luminance(foreground), _luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _luminance(color: QColor) -> float:
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return (0.2126 * linear[0]) + (0.7152 * linear[1]) + (0.0722 * linear[2])
