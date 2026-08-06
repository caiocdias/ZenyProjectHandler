"""Janela principal da aplicação."""

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStyle,
    QToolButton,
    QWidget,
)

from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.domain.compliance import RegistroRegrasConformidade
from zeny_project_handler.ports.pdf import LeitorPdfPort, OrcamentoRenderizacaoPdf

from .documentation_panel import DocumentationPanelWidget
from .pdf_viewer import PdfViewerWidget
from .portability_panel import PortabilityPanelWidget
from .project_panel import ProjectPanelWidget
from .review_panel import ReviewPanelWidget

_CLOSE_WAIT_MS = 300


class _OperationStateBridge(QObject):
    """Converta observações thread-safe do coordenador em sinais enfileirados do Qt."""

    state_changed = Signal(object)

    def __init__(self, coordinator: CoordenadorOperacoes, parent: QObject) -> None:
        super().__init__(parent)
        self.current = coordinator.operacao_em_andamento
        self._remove_observer: Callable[[], None] | None = coordinator.observar(self._relay)

    def _relay(self, operation: TipoOperacao | None) -> None:
        self.current = operation
        self.state_changed.emit(operation)

    def close(self) -> None:
        remove = self._remove_observer
        self._remove_observer = None
        if remove is not None:
            remove()


class _DockTitleBar(QWidget):
    def __init__(self, dock: QDockWidget) -> None:
        super().__init__(dock)
        self._dock = dock
        self._drag_origin: QPoint | None = None
        self._dragging = False
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(5, 1, 2, 1)
        self._layout.setSpacing(2)

        self._title = QLabel(dock.windowTitle(), self)
        self._title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._layout.addWidget(self._title, 1)
        self._float_button = self._button(
            "Desacoplar painel",
            None,
            self._toggle_floating,
            "FloatButton",
        )
        self._float_button.setText("Desacoplar")
        self._float_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._controls_separator = QFrame(self)
        self._controls_separator.setObjectName(f"{self._dock.objectName()}WindowControlsSeparator")
        self._controls_separator.setFrameShape(QFrame.Shape.VLine)
        self._controls_separator.setFrameShadow(QFrame.Shadow.Sunken)
        self._layout.addSpacing(6)
        self._layout.addWidget(self._controls_separator)
        self._layout.addSpacing(6)
        self._minimize_button = self._button(
            "Minimizar painel",
            QStyle.StandardPixmap.SP_TitleBarMinButton,
            dock.showMinimized,
            "MinimizeButton",
        )
        self._maximize_button = self._button(
            "Maximizar painel",
            QStyle.StandardPixmap.SP_TitleBarMaxButton,
            self._toggle_maximized,
            "MaximizeButton",
        )
        self._close_button = self._button(
            "Fechar painel",
            QStyle.StandardPixmap.SP_TitleBarCloseButton,
            dock.close,
            "CloseButton",
        )
        dock.topLevelChanged.connect(self._update_state)
        dock.windowTitleChanged.connect(self._title.setText)
        dock.installEventFilter(self)
        self._update_state(dock.isFloating())

    def _button(
        self,
        tooltip: str,
        icon: QStyle.StandardPixmap | None,
        callback: Callable[[], object],
        suffix: str,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(f"{self._dock.objectName()}{suffix}")
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
        if icon is not None:
            button.setIcon(self.style().standardIcon(icon))
        button.clicked.connect(callback)
        self._layout.addWidget(button)
        return button

    def _toggle_maximized(self) -> None:
        if self._dock.isMaximized():
            self._dock.showNormal()
        else:
            self._dock.showMaximized()
        self._update_maximize_button()

    def _toggle_floating(self) -> None:
        if self._dock.isMaximized() or self._dock.isMinimized():
            self._dock.showNormal()
        self._dock.setFloating(not self._dock.isFloating())

    def _update_state(self, floating: bool) -> None:
        self._minimize_button.setVisible(floating)
        self._maximize_button.setVisible(floating)
        self._float_button.setText("Reacoplar" if floating else "Desacoplar")
        self._float_button.setToolTip(
            "Reacoplar painel à janela principal" if floating else "Desacoplar painel"
        )
        self._update_maximize_button()

    def _update_maximize_button(self) -> None:
        maximized = self._dock.isMaximized()
        self._maximize_button.setToolTip("Restaurar painel" if maximized else "Maximizar painel")
        icon = (
            QStyle.StandardPixmap.SP_TitleBarNormalButton
            if maximized
            else QStyle.StandardPixmap.SP_TitleBarMaxButton
        )
        self._maximize_button.setIcon(self.style().standardIcon(icon))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - API Qt
        if watched is self._dock and event.type() == QEvent.Type.WindowStateChange:
            self._update_maximize_button()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            self._dragging = False
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if (
            self._drag_origin is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.globalPosition().toPoint() - self._drag_origin).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._dragging = True
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        should_finish_drag = event.button() == Qt.MouseButton.LeftButton and self._dragging
        release_position = event.globalPosition().toPoint()
        allow_docking = not bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self._drag_origin = None
        self._dragging = False
        event.ignore()
        if should_finish_drag:
            QTimer.singleShot(
                0,
                self,
                lambda: self._finish_drag(release_position, allow_docking),
            )

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.MouseButton.LeftButton and self._dock.isFloating():
            self._toggle_maximized()
            event.accept()
            return
        event.ignore()

    @staticmethod
    def _screen_edge_geometry(
        cursor: QPoint,
        available: QRect,
        threshold: int = 12,
    ) -> QRect | None:
        near_left = cursor.x() <= available.left() + threshold
        near_right = cursor.x() >= available.right() - threshold
        near_top = cursor.y() <= available.top() + threshold
        near_bottom = cursor.y() >= available.bottom() - threshold

        if near_top and not near_left and not near_right:
            return QRect()
        if not near_left and not near_right:
            return None

        left_width = available.width() // 2
        x = available.left() if near_left else available.left() + left_width
        width = left_width if near_left else available.width() - left_width
        if near_top or near_bottom:
            top_height = available.height() // 2
            y = available.top() if near_top else available.top() + top_height
            height = top_height if near_top else available.height() - top_height
        else:
            y = available.top()
            height = available.height()
        return QRect(x, y, width, height)

    def _main_window(self) -> QMainWindow | None:
        widget = self._dock.parentWidget()
        while widget is not None and not isinstance(widget, QMainWindow):
            widget = widget.parentWidget()
        return widget

    def _docking_target(
        self,
        global_position: QPoint,
    ) -> tuple[QMainWindow, Qt.DockWidgetArea, QDockWidget | None] | None:
        main_window = self._main_window()
        if main_window is None:
            return None
        local_position = main_window.mapFromGlobal(global_position)
        contents = main_window.contentsRect()
        if not contents.contains(local_position):
            return None

        for candidate in main_window.findChildren(QDockWidget):
            if (
                candidate is self._dock
                or candidate.isFloating()
                or not candidate.isVisible()
                or not candidate.geometry().contains(local_position)
            ):
                continue
            area = main_window.dockWidgetArea(candidate)
            if self._dock.isAreaAllowed(area):
                return main_window, area, candidate

        edge_margin = min(220, max(80, contents.width() // 6))
        if local_position.x() <= contents.left() + edge_margin:
            area = Qt.DockWidgetArea.LeftDockWidgetArea
        elif local_position.x() >= contents.right() - edge_margin:
            area = Qt.DockWidgetArea.RightDockWidgetArea
        else:
            return None
        if not self._dock.isAreaAllowed(area):
            return None
        return main_window, area, None

    def _dock_at_position(self, global_position: QPoint) -> bool:
        target = self._docking_target(global_position)
        if target is None:
            return False
        main_window, area, sibling = target
        if self._dock.isMaximized() or self._dock.isMinimized():
            self._dock.showNormal()
        main_window.addDockWidget(area, self._dock)
        if self._dock.isFloating():
            self._dock.setFloating(False)
        if sibling is not None:
            main_window.tabifyDockWidget(sibling, self._dock)
        self._dock.show()
        self._dock.raise_()
        return not self._dock.isFloating()

    def _finish_drag(self, global_position: QPoint, allow_docking: bool) -> None:
        if not self._dock.isFloating():
            return
        if allow_docking and self._dock_at_position(global_position):
            return
        self._snap_to_screen_edge(global_position)

    def _snap_to_screen_edge(self, cursor: QPoint) -> None:
        if not self._dock.isFloating():
            return
        screen = QGuiApplication.screenAt(cursor)
        if screen is None:
            return
        target = self._screen_edge_geometry(cursor, screen.availableGeometry())
        if target is None:
            return
        if target.isNull():
            self._dock.showMaximized()
        else:
            self._dock.showNormal()
            self._dock.setGeometry(target)
        self._update_maximize_button()


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        application_name: str,
        pdf_reader: LeitorPdfPort,
        pdf_render_dpi: int,
        pdf_render_budget: OrcamentoRenderizacaoPdf,
        review_service: ServicoRevisaoHumana | None = None,
        workflow_service: ServicoFluxoMvp | None = None,
        portability_service: ServicoPortabilidadeProjeto | None = None,
        operation_coordinator: CoordenadorOperacoes | None = None,
        compliance_registry: RegistroRegrasConformidade | None = None,
        ui_state_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resource_cleanup: Callable[[], None] = lambda: None
        self._operation_bridge: _OperationStateBridge | None = None
        self._coordinator_operation: TipoOperacao | None = None
        self.setObjectName("mainWindow")
        self.setWindowTitle(application_name)
        self.resize(1400, 900)
        self.setDockNestingEnabled(True)
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.AnimatedDocks
        )
        self._panels_menu = self.menuBar().addMenu("Painéis")
        self._panels_menu.setObjectName("panelsMenu")
        self.pdf_viewer = PdfViewerWidget(
            leitor=pdf_reader,
            dpi=pdf_render_dpi,
            orcamento=pdf_render_budget,
            parent=self,
        )
        self.pdf_viewer.status_changed.connect(self.statusBar().showMessage)
        self.setCentralWidget(self.pdf_viewer)
        self.review_panel: ReviewPanelWidget | None = None
        self.project_panel: ProjectPanelWidget | None = None
        self.portability_panel: PortabilityPanelWidget | None = None
        self.documentation_panel: DocumentationPanelWidget | None = None
        right_docks: list[QDockWidget] = []
        if review_service is not None:
            self.review_panel = ReviewPanelWidget(
                service=review_service,
                viewer=self.pdf_viewer,
                parent=self,
            )
            self.review_panel.status_changed.connect(self.statusBar().showMessage)
            dock = QDockWidget("Resultados da análise", self)
            dock.setObjectName("humanReviewDock")
            dock.setAllowedAreas(
                Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
            )
            dock.setWidget(self.review_panel)
            self._register_dock(dock)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
            self.pdf_viewer.proposal_selected.connect(
                lambda _proposal_id, review_dock=dock: review_dock.raise_()
            )
            right_docks.append(dock)
            if compliance_registry is not None:
                self.documentation_panel = DocumentationPanelWidget(
                    service=review_service,
                    registry=compliance_registry,
                    viewer=self.pdf_viewer,
                    parent=self,
                )
                self.documentation_panel.status_changed.connect(self.statusBar().showMessage)
                documentation_dock = QDockWidget(
                    "Documentação e conformidade",
                    self,
                )
                documentation_dock.setObjectName("documentationComplianceDock")
                documentation_dock.setAllowedAreas(
                    Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
                )
                documentation_dock.setWidget(self.documentation_panel)
                self._register_dock(documentation_dock)
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, documentation_dock)
                self.review_panel.session_changed.connect(self.documentation_panel.abrir_sessao)
                right_docks.append(documentation_dock)
        if (
            workflow_service is not None
            and self.review_panel is not None
            and ui_state_path is not None
        ):
            self.project_panel = ProjectPanelWidget(
                service=workflow_service,
                viewer=self.pdf_viewer,
                review_panel=self.review_panel,
                state_path=ui_state_path,
                parent=self,
            )
            self.project_panel.status_changed.connect(self.statusBar().showMessage)
            self.project_panel.busy_changed.connect(self._refresh_operation_controls)
            project_dock = QDockWidget("Fluxo do projeto", self)
            project_dock.setObjectName("projectWorkflowDock")
            project_dock.setAllowedAreas(
                Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
            )
            project_dock.setWidget(self.project_panel)
            self._register_dock(project_dock)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, project_dock)
        if portability_service is not None:
            self.portability_panel = PortabilityPanelWidget(
                service=portability_service,
                parent=self,
            )
            self.portability_panel.status_changed.connect(self.statusBar().showMessage)
            self.portability_panel.data_changed.connect(self._refresh_data_panels)
            self.portability_panel.data_restored.connect(self._refresh_after_restore)
            self.portability_panel.busy_changed.connect(self._refresh_operation_controls)
            portability_dock = QDockWidget("Portabilidade e recuperação", self)
            portability_dock.setObjectName("projectPortabilityDock")
            portability_dock.setAllowedAreas(
                Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
            )
            portability_dock.setWidget(self.portability_panel)
            self._register_dock(portability_dock)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, portability_dock)
            right_docks.append(portability_dock)
        for current, following in pairwise(right_docks):
            self.tabifyDockWidget(current, following)
        if right_docks:
            right_docks[0].raise_()
        selected_coordinator = operation_coordinator
        if selected_coordinator is None and workflow_service is not None:
            selected_coordinator = workflow_service.coordenador
        if selected_coordinator is None and portability_service is not None:
            selected_coordinator = portability_service.coordenador
        if selected_coordinator is not None:
            self._operation_bridge = _OperationStateBridge(selected_coordinator, self)
            self._operation_bridge.state_changed.connect(self._operation_state_changed)
            self._operation_state_changed(self._operation_bridge.current)
        self.statusBar().showMessage("Pronto para abrir um PDF")

    def _register_dock(self, dock: QDockWidget) -> None:
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        dock.setTitleBarWidget(_DockTitleBar(dock))
        toggle_action = dock.toggleViewAction()
        toggle_action.setObjectName(f"{dock.objectName()}ToggleAction")
        self._panels_menu.addAction(toggle_action)

    def _refresh_data_panels(self) -> None:
        if self.project_panel is not None:
            self.project_panel.atualizar_projetos()
        if self.review_panel is not None:
            self.review_panel.atualizar_projetos()
        if self.documentation_panel is not None:
            self.documentation_panel.atualizar_projetos()

    def _refresh_after_restore(self) -> None:
        self.pdf_viewer.limpar()
        if self.review_panel is not None:
            self.review_panel.limpar()
        if self.documentation_panel is not None:
            self.documentation_panel.limpar()
        self._refresh_data_panels()

    @Slot(object)
    def _operation_state_changed(self, operation: object) -> None:
        self._coordinator_operation = operation if isinstance(operation, TipoOperacao) else None
        self._refresh_operation_controls()

    @Slot(bool)
    def _refresh_operation_controls(self, _busy: bool = False) -> None:
        project_busy = self.project_panel is not None and self.project_panel.processando
        portability_busy = self.portability_panel is not None and self.portability_panel.processando
        busy = self._coordinator_operation is not None or project_busy or portability_busy
        if self.project_panel is not None:
            self.project_panel.setEnabled(not portability_busy)
            self.project_panel.set_global_operation(self._coordinator_operation)
        if self.portability_panel is not None:
            self.portability_panel.setEnabled(not project_busy)
            self.portability_panel.set_global_operation(self._coordinator_operation)
        if self.review_panel is not None:
            self.review_panel.setEnabled(not busy)
        if self.documentation_panel is not None:
            self.documentation_panel.setEnabled(not busy)

    def set_resource_cleanup(self, callback: Callable[[], None]) -> None:
        self._resource_cleanup = callback

    def release_resources(self) -> None:
        self._resource_cleanup()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        active = (self.project_panel is not None and self.project_panel.processando) or (
            self.portability_panel is not None and self.portability_panel.processando
        )
        if active:
            deadline = monotonic() + (_CLOSE_WAIT_MS / 1000)
            finished = True
            if self.project_panel is not None:
                remaining = max(0, round((deadline - monotonic()) * 1000))
                finished = self.project_panel.cancelar_e_aguardar(remaining) and finished
            if self.portability_panel is not None:
                remaining = max(0, round((deadline - monotonic()) * 1000))
                finished = self.portability_panel.cancelar_e_aguardar(remaining) and finished
            if finished:
                active = False
        if active:
            QMessageBox.information(
                self,
                "Operação em andamento",
                "O cancelamento foi solicitado. A operação está concluindo um trecho seguro; "
                "feche novamente quando ela terminar.",
            )
            event.ignore()
            return
        super().closeEvent(event)
        if event.isAccepted():
            if self._operation_bridge is not None:
                self._operation_bridge.close()
            self.release_resources()
