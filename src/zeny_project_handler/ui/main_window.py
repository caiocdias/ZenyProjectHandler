"""Janela principal da aplicação."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDockWidget, QMainWindow, QMessageBox, QWidget

from zeny_project_handler.application.human_review import ServicoRevisaoHumana
from zeny_project_handler.application.mvp_workflow import ServicoFluxoMvp
from zeny_project_handler.application.project_graph import ServicoGrafoProjeto
from zeny_project_handler.application.project_portability import ServicoPortabilidadeProjeto
from zeny_project_handler.ports.pdf import LeitorPdfPort

from .graph_panel import GraphPanelWidget
from .pdf_viewer import PdfViewerWidget
from .portability_panel import PortabilityPanelWidget
from .project_panel import ProjectPanelWidget
from .review_panel import ReviewPanelWidget


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        application_name: str,
        pdf_reader: LeitorPdfPort,
        pdf_render_dpi: int,
        review_service: ServicoRevisaoHumana | None = None,
        workflow_service: ServicoFluxoMvp | None = None,
        graph_service: ServicoGrafoProjeto | None = None,
        portability_service: ServicoPortabilidadeProjeto | None = None,
        ui_state_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.setWindowTitle(application_name)
        self.resize(1200, 800)
        self.pdf_viewer = PdfViewerWidget(leitor=pdf_reader, dpi=pdf_render_dpi, parent=self)
        self.pdf_viewer.status_changed.connect(self.statusBar().showMessage)
        self.setCentralWidget(self.pdf_viewer)
        self.review_panel: ReviewPanelWidget | None = None
        self.project_panel: ProjectPanelWidget | None = None
        self.graph_panel: GraphPanelWidget | None = None
        self.portability_panel: PortabilityPanelWidget | None = None
        if review_service is not None:
            self.review_panel = ReviewPanelWidget(
                service=review_service,
                viewer=self.pdf_viewer,
                parent=self,
            )
            self.review_panel.status_changed.connect(self.statusBar().showMessage)
            dock = QDockWidget("Revisão humana", self)
            dock.setObjectName("humanReviewDock")
            dock.setAllowedAreas(
                Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
            )
            dock.setWidget(self.review_panel)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
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
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, project_dock)
        if graph_service is not None:
            self.graph_panel = GraphPanelWidget(
                service=graph_service,
                viewer=self.pdf_viewer,
                parent=self,
            )
            self.graph_panel.status_changed.connect(self.statusBar().showMessage)
            graph_dock = QDockWidget("Grafo do projeto", self)
            graph_dock.setObjectName("projectGraphDock")
            graph_dock.setAllowedAreas(
                Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
            )
            graph_dock.setWidget(self.graph_panel)
            self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, graph_dock)
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
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, portability_dock)
        self.statusBar().showMessage("Pronto para abrir um PDF")

    def _refresh_data_panels(self) -> None:
        if self.project_panel is not None:
            self.project_panel.atualizar_projetos()
        if self.review_panel is not None:
            self.review_panel.atualizar_projetos()
        if self.graph_panel is not None:
            self.graph_panel.atualizar_projetos()

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
