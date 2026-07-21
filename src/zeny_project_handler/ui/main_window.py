"""Janela principal da aplicação."""

from PySide6.QtWidgets import QMainWindow, QWidget

from zeny_project_handler.ports.pdf import LeitorPdfPort

from .pdf_viewer import PdfViewerWidget


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        application_name: str,
        pdf_reader: LeitorPdfPort,
        pdf_render_dpi: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("mainWindow")
        self.setWindowTitle(application_name)
        self.resize(1200, 800)
        self.pdf_viewer = PdfViewerWidget(leitor=pdf_reader, dpi=pdf_render_dpi, parent=self)
        self.pdf_viewer.status_changed.connect(self.statusBar().showMessage)
        self.setCentralWidget(self.pdf_viewer)
        self.statusBar().showMessage("Pronto para abrir um PDF")
