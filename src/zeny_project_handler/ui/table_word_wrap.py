"""Quebra de linha opcional para as tabelas de dados da interface."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRect, QSize, Qt, QTimer
from PySide6.QtWidgets import QTableWidget, QToolButton, QTreeWidget, QTreeWidgetItem


class TableWordWrapController(QObject):
    """Controle local de quebra de texto para um único item view."""

    def __init__(
        self,
        view: QTreeWidget | QTableWidget,
        *,
        button_name: str,
    ) -> None:
        super().__init__(view)
        self._view = view
        self._compact_word_wrap = view.wordWrap()
        self._compact_elide_mode = view.textElideMode()
        self._compact_row_height = (
            view.verticalHeader().defaultSectionSize()
            if isinstance(view, QTableWidget)
            else view.fontMetrics().height() + 8
        )
        self._compact_uniform_rows = (
            view.uniformRowHeights() if isinstance(view, QTreeWidget) else None
        )

        self.button = QToolButton()
        self.button.setObjectName(button_name)
        self.button.setText("Quebrar linhas")
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.button.setCheckable(True)
        self.button.setToolTip("Mostrar todo o texto das células em múltiplas linhas")
        self.button.setAccessibleName("Quebrar linhas")
        self.button.setAccessibleDescription(self.button.toolTip())
        self.button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.button.toggled.connect(self._set_enabled)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._recalculate)
        header = view.header() if isinstance(view, QTreeWidget) else view.horizontalHeader()
        header.sectionResized.connect(self._column_resized)

    def refresh(self) -> None:
        """Recalcule depois de uma recarga de dados ou troca de aba."""
        if self.button.isChecked():
            self._timer.start()

    def _set_enabled(self, enabled: bool) -> None:
        self._view.setWordWrap(True if enabled else self._compact_word_wrap)
        self._view.setTextElideMode(
            Qt.TextElideMode.ElideNone if enabled else self._compact_elide_mode
        )
        if isinstance(self._view, QTreeWidget):
            self._view.setUniformRowHeights(False if enabled else bool(self._compact_uniform_rows))
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()
            self._restore_compact_rows()

    def _column_resized(self, _column: int, _old_size: int, _new_size: int) -> None:
        self.refresh()

    def _recalculate(self) -> None:
        if not self.button.isChecked():
            return
        if isinstance(self._view, QTableWidget):
            self._view.resizeRowsToContents()
            self._view.viewport().update()
            return
        self._resize_tree_rows()

    def _restore_compact_rows(self) -> None:
        if isinstance(self._view, QTableWidget):
            for row in range(self._view.rowCount()):
                self._view.setRowHeight(row, self._compact_row_height)
            self._view.viewport().update()
            return
        for item in _tree_items(self._view):
            item.setSizeHint(0, QSize())
        self._view.doItemsLayout()
        self._view.viewport().update()

    def _resize_tree_rows(self) -> None:
        tree = self._view
        if not isinstance(tree, QTreeWidget):
            return
        metrics = tree.fontMetrics()
        minimum_height = max(self._compact_row_height, metrics.height() + 8)
        flags = int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs)
        for item in _tree_items(tree):
            height = minimum_height
            depth = _item_depth(item)
            for column in range(tree.columnCount()):
                if tree.isColumnHidden(column):
                    continue
                available = tree.columnWidth(column) - 12
                if column == 0:
                    available -= tree.indentation() * (depth + 1)
                text = item.text(column)
                if text:
                    bounds = metrics.boundingRect(
                        QRect(0, 0, max(20, available), 100_000),
                        flags,
                        text,
                    )
                    height = max(height, bounds.height() + 8)
                widget = tree.itemWidget(item, column)
                if widget is not None:
                    height = max(height, widget.sizeHint().height() + 4)
            item.setSizeHint(0, QSize(0, height))
        tree.doItemsLayout()
        tree.viewport().update()


def _tree_items(tree: QTreeWidget) -> tuple[QTreeWidgetItem, ...]:
    pending = [
        item
        for index in range(tree.topLevelItemCount())
        if (item := tree.topLevelItem(index)) is not None
    ]
    items: list[QTreeWidgetItem] = []
    while pending:
        item = pending.pop()
        items.append(item)
        pending.extend(
            child for index in range(item.childCount()) if (child := item.child(index)) is not None
        )
    return tuple(items)


def _item_depth(item: QTreeWidgetItem) -> int:
    depth = 0
    parent = item.parent()
    while parent is not None:
        depth += 1
        parent = parent.parent()
    return depth
