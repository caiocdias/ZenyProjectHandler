"""Rolagem dos docks sem comprimir cartões nem expandir tabelas por linha."""

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFormLayout,
    QFrame,
    QLayout,
    QListView,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QWidget,
)


class PanelScrollArea(QScrollArea):
    """Viewport independente; Tab revela o foco e a roda encadeia nas bordas."""

    def __init__(self, panel: QWidget, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"{panel.objectName()}ScrollArea")
        self.setAccessibleName(f"Rolagem do painel {title}")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # Preserva acesso se o dock for menor que a largura intrínseca de uma ação.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._prepare(panel)
        layout = panel.layout()
        if layout is not None:
            layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setWidget(panel)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        return QSize(420, 600)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - API Qt
        # O mínimo do conteúdo pertence ao scroll, não à janela principal.
        return QSize(240, 120)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - API Qt
        if not event.pixelDelta().isNull():
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - event.pixelDelta().y())
            horizontal = self.horizontalScrollBar()
            horizontal.setValue(horizontal.value() - event.pixelDelta().x())
            event.accept()
        else:
            super().wheelEvent(event)

    def _prepare(self, widget: QWidget) -> None:
        widget.installEventFilter(self)
        if isinstance(widget, QComboBox):
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            widget.setMinimumContentsLength(8)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # O popup continua sendo uma lista nativa com roda e teclado próprios.
            return
        if isinstance(widget, (QAbstractItemView, QTextEdit)):
            line = widget.fontMetrics().lineSpacing()
            rows = 5 if isinstance(widget, QListView) else 9
            widget.setMinimumHeight(max(widget.minimumHeight(), rows * line + 40))
            widget.setMaximumHeight(max(widget.minimumHeight(), (rows + 5) * line + 40))
            widget.viewport().installEventFilter(self)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            if isinstance(widget, QAbstractItemView):
                widget.setTabKeyNavigation(False)
            else:
                widget.setTabChangesFocus(True)
            return
        layout = widget.layout()
        if isinstance(layout, QFormLayout):
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for child in widget.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            self._prepare(child)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - API Qt
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QWidget):
            QTimer.singleShot(0, watched, lambda: self.ensureWidgetVisible(watched))
        if isinstance(event, QWheelEvent) and isinstance(watched, QWidget):
            return self._route_wheel(watched, event)
        return super().eventFilter(watched, event)

    def _route_wheel(self, watched: QWidget, event: QWheelEvent) -> bool:
        if QApplication.activePopupWidget() is not None:
            return False
        nested = watched if isinstance(watched, QAbstractScrollArea) else watched.parentWidget()
        if isinstance(nested, QAbstractScrollArea) and nested is not self:
            delta = event.pixelDelta().y() or event.angleDelta().y()
            bar = nested.verticalScrollBar()
            if (
                delta == 0
                or (delta > 0 and bar.value() > bar.minimum())
                or (delta < 0 and bar.value() < bar.maximum())
            ):
                return False
        elif not isinstance(watched, (QComboBox, QAbstractSpinBox)):
            return False
        # Combos/spins fechados nunca mudam só por passar a roda, mesmo com foco.
        # Nas bordas de listas, tabelas e texto a mesma roda passa ao painel.
        self.wheelEvent(event)
        event.accept()
        return True
