"""Janela principal da aplicação."""

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QMouseEvent
from PySide6.QtWidgets import (
    QDockWidget,
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
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.ports.pdf import LeitorPdfPort

from .pdf_viewer import PdfViewerWidget
from .portability_panel import PortabilityPanelWidget
from .project_panel import ProjectPanelWidget
from .review_panel import ReviewPanelWidget


class _DockTitleBar(QWidget):
    def __init__(self, dock: QDockWidget) -> None:
        super().__init__(dock)
        self._dock = dock
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(5, 1, 2, 1)
        self._layout.setSpacing(2)

        self._title = QLabel(dock.windowTitle(), self)
        self._layout.addWidget(self._title, 1)
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
        self._float_button = self._button(
            "Desacoplar painel",
            QStyle.StandardPixmap.SP_TitleBarNormalButton,
            self._toggle_floating,
            "FloatButton",
        )
        self._close_button = self._button(
            "Fechar painel",
            QStyle.StandardPixmap.SP_TitleBarCloseButton,
            dock.close,
            "CloseButton",
        )
        dock.topLevelChanged.connect(self._update_state)
        dock.windowTitleChanged.connect(self._title.setText)
        self._update_state(dock.isFloating())

    def _button(
        self,
        tooltip: str,
        icon: QStyle.StandardPixmap,
        callback: Callable[[], object],
        suffix: str,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(f"{self._dock.objectName()}{suffix}")
        button.setAutoRaise(True)
        button.setToolTip(tooltip)
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
        self._float_button.setToolTip("Acoplar painel" if floating else "Desacoplar painel")
        self._update_maximize_button()

    def _update_maximize_button(self) -> None:
        maximized = self._dock.isMaximized()
        self._maximize_button.setToolTip(
            "Restaurar painel" if maximized else "Maximizar painel"
        )
        icon = (
            QStyle.StandardPixmap.SP_TitleBarNormalButton
            if maximized
            else QStyle.StandardPixmap.SP_TitleBarMaxButton
        )
        self._maximize_button.setIcon(self.style().standardIcon(icon))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        event.ignore()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - API Qt
        event.ignore()


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        application_name: str,
        pdf_reader: LeitorPdfPort,
        pdf_render_dpi: int,
        review_service: ServicoRevisaoHumana | None = None,
        workflow_service: ServicoFluxoMvp | None = None,
        portability_service: ServicoPortabilidadeProjeto | None = None,
        ui_state_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
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
        self.pdf_viewer = PdfViewerWidget(leitor=pdf_reader, dpi=pdf_render_dpi, parent=self)
        self.pdf_viewer.status_changed.connect(self.statusBar().showMessage)
        self.setCentralWidget(self.pdf_viewer)
        self.review_panel: ReviewPanelWidget | None = None
        self.project_panel: ProjectPanelWidget | None = None
        self.portability_panel: PortabilityPanelWidget | None = None
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

    def _refresh_after_restore(self) -> None:
        self.pdf_viewer.limpar()
        if self.review_panel is not None:
            self.review_panel.limpar()
        self._refresh_data_panels()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        if self.project_panel is not None and self.project_panel.processando:
            self.project_panel.cancelar_analise()
            QMessageBox.information(
                self,
                "Análise em andamento",
                "O cancelamento foi solicitado. Feche novamente quando a análise terminar.",
            )
            event.ignore()
            return
        super().closeEvent(event)
