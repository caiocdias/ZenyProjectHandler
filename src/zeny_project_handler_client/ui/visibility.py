"""Recursos visuais do cliente para controles temporários de visibilidade."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from zeny_project_handler_contracts.enums import ElementSituation

REVIEW_HIGHLIGHT_OPACITY = 0.25
REVIEW_SITUATION_COLORS = {
    ElementSituation.INSTALL: ("#22c55e", "Instalar"),
    ElementSituation.EXISTING: ("#facc15", "Existente"),
    ElementSituation.REMOVE: ("#ef4444", "Remover"),
    ElementSituation.CHANGE: ("#3b82f6", "Alterar"),
}


def review_highlight_color(situation: ElementSituation) -> QColor:
    """Cor operacional com transparência, independente da decisão de revisão."""
    color = QColor(REVIEW_SITUATION_COLORS[situation][0])
    color.setAlphaF(REVIEW_HIGHLIGHT_OPACITY)
    return color


def review_highlight_legend() -> str:
    swatches = " &nbsp; ".join(
        f'<span style="color:{color}">■</span> {label}'
        for color, label in REVIEW_SITUATION_COLORS.values()
    )
    return (
        f"{swatches}<br>"
        "Realce = identificação, não aprovação nem leitura completa. "
        "Contorno = seleção; tracejado sem cor = rejeitada."
    )


def visibility_icon(visible: bool) -> QIcon:
    """Crie o ícone de olho usado pelas camadas vetoriais do visualizador."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#2f5f8f"), 1.8)
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(2.0, 5.0, 16.0, 10.0))
    painter.setBrush(QColor("#2f5f8f"))
    painter.drawEllipse(QRectF(8.0, 8.0, 4.0, 4.0))
    if not visible:
        slash = QPen(QColor("#a33a3a"), 2.2)
        slash.setCosmetic(True)
        painter.setPen(slash)
        painter.drawLine(3, 3, 17, 17)
    painter.end()
    return QIcon(pixmap)
