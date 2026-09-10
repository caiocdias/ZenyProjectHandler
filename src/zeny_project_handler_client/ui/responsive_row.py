"""Linhas de controles que se empilham quando o dock perde largura."""

from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QAbstractButton, QBoxLayout, QHBoxLayout, QLabel, QSizePolicy


class ResponsiveRowLayout(QHBoxLayout):
    """Preserve a geometria nativa do Qt e a ordem ao empilhar uma linha estreita."""

    def _sizes(self, *, preferred_labels: bool = False) -> list[QSize]:
        sizes = []
        for index in range(self.count()):
            item = self.itemAt(index)
            if item is not None and not item.isEmpty():
                size = item.minimumSize()
                widget = item.widget()
                if isinstance(widget, QAbstractButton) or (
                    preferred_labels and isinstance(widget, QLabel) and widget.wordWrap()
                ):
                    size = size.expandedTo(item.sizeHint())
                sizes.append(size)
        return sizes

    def _fits(self, width: int) -> bool:
        # Mensagens devem manter largura de leitura quando dividem a linha com ações.
        # Essa preferência não aumenta o mínimo intrínseco do painel rolável.
        sizes = self._sizes(preferred_labels=True)
        margins = self.contentsMargins()
        needed = sum(size.width() for size in sizes) + max(0, len(sizes) - 1) * self.spacing()
        return needed <= width - margins.left() - margins.right()

    def minimumSize(self) -> QSize:  # noqa: N802 - API Qt
        size = super().minimumSize()
        margins = self.contentsMargins()
        size.setWidth(
            max((s.width() for s in self._sizes()), default=0) + margins.left() + margins.right()
        )
        return size

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - API Qt
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - API Qt
        if self._fits(width):
            return super().heightForWidth(width)
        margins = self.contentsMargins()
        inner = max(1, width - margins.left() - margins.right())
        heights = []
        for index in range(self.count()):
            item = self.itemAt(index)
            if item is not None and not item.isEmpty():
                heights.append(
                    max(item.minimumSize().height(), item.heightForWidth(inner))
                    if item.hasHeightForWidth()
                    else item.sizeHint().height()
                )
        return (
            sum(heights)
            + max(0, len(heights) - 1) * self.spacing()
            + margins.top()
            + margins.bottom()
        )

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - API Qt
        direction = (
            QBoxLayout.Direction.LeftToRight
            if self._fits(rect.width())
            else QBoxLayout.Direction.TopToBottom
        )
        if self.direction() != direction:
            if direction == QBoxLayout.Direction.TopToBottom:
                self._horizontal_stretches = [self.stretch(i) for i in range(self.count())]
            for index in range(self.count()):
                self.setStretch(
                    index,
                    0
                    if direction == QBoxLayout.Direction.TopToBottom
                    else self._horizontal_stretches[index],
                )
                item = self.itemAt(index)
                if item is not None and (spacer := item.spacerItem()) is not None:
                    spacer.changeSize(
                        0,
                        0,
                        QSizePolicy.Policy.Expanding
                        if direction == QBoxLayout.Direction.LeftToRight
                        else QSizePolicy.Policy.Minimum,
                        QSizePolicy.Policy.Minimum,
                    )
            self.setDirection(direction)
        super().setGeometry(rect)
