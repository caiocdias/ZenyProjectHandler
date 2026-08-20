"""Recursos visuais do cliente para controles temporários de visibilidade."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


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
