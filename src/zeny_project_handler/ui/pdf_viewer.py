"""Visualizador PDF desacoplado do mecanismo concreto de leitura."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler.adapters.pdf.coordinates import TransformadorCoordenadasPagina
from zeny_project_handler.adapters.pdf.errors import PdfError
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import InspecaoPdf, LeitorPdfPort, PaginaPdfRenderizada


class PdfGraphicsView(QGraphicsView):
    """Cena raster com zoom suave e sobreposições em coordenadas normalizadas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pdfGraphicsView")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._zoom = 1.0
        self.setBackgroundBrush(QBrush(QColor("#3b3d40")))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    @property
    def zoom(self) -> float:
        return self._zoom

    def definir_pagina(self, rendered: PaginaPdfRenderizada) -> None:
        image = QImage(
            rendered.dados_rgb,
            rendered.largura_pixels,
            rendered.altura_pixels,
            rendered.stride,
            QImage.Format.Format_RGB888,
        ).copy()
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(QPixmap.fromImage(image))
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.ajustar_pagina()

    def definir_sobreposicoes(
        self,
        geometries: tuple[tuple[PontoNormalizado, ...], ...],
        transformer: TransformadorCoordenadasPagina,
    ) -> None:
        if self._pixmap_item is None:
            return
        pen = QPen(QColor("#ff3b30"), 2)
        pen.setCosmetic(True)
        for geometry in geometries:
            if not geometry:
                continue
            first = transformer.normalizado_para_pixel(geometry[0])
            path = QPainterPath(QPointF(first.x, first.y))
            for point in geometry[1:]:
                mapped = transformer.normalizado_para_pixel(point)
                path.lineTo(mapped.x, mapped.y)
            if len(geometry) > 2:
                path.closeSubpath()
            self._scene.addPath(path, pen)

    def definir_zoom(self, value: float) -> None:
        self._zoom = min(16.0, max(0.05, value))
        self.resetTransform()
        self.scale(self._zoom, self._zoom)

    def ampliar(self) -> None:
        self.definir_zoom(self._zoom * 1.25)

    def reduzir(self) -> None:
        self.definir_zoom(self._zoom / 1.25)

    def ajustar_pagina(self) -> None:
        if self._pixmap_item is None:
            return
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - API Qt
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ampliar() if event.angleDelta().y() > 0 else self.reduzir()
            event.accept()
            return
        super().wheelEvent(event)


class PdfViewerWidget(QWidget):
    status_changed = Signal(str)

    def __init__(
        self,
        *,
        leitor: LeitorPdfPort,
        dpi: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pdfViewerWidget")
        self._reader = leitor
        self._dpi = dpi
        self._inspection: InspecaoPdf | None = None
        self._password: str | None = None
        self._rotation = 0
        self._overlays: tuple[tuple[PontoNormalizado, ...], ...] = ()
        self._build_ui()

    @property
    def inspecao(self) -> InspecaoPdf | None:
        return self._inspection

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        open_button = QPushButton("Abrir PDF")
        open_button.setObjectName("openPdfButton")
        open_button.clicked.connect(self.selecionar_pdf)
        toolbar.addWidget(open_button)

        previous_button = QPushButton("Anterior")
        previous_button.clicked.connect(lambda: self._change_page(-1))
        toolbar.addWidget(previous_button)
        self._page = QSpinBox()
        self._page.setObjectName("pdfPageSpinBox")
        self._page.setRange(1, 1)
        self._page.setEnabled(False)
        self._page.valueChanged.connect(self._render_current_page)
        toolbar.addWidget(self._page)
        next_button = QPushButton("Próxima")
        next_button.clicked.connect(lambda: self._change_page(1))
        toolbar.addWidget(next_button)

        zoom_out = QPushButton("-")
        zoom_out.setObjectName("pdfZoomOutButton")
        zoom_out.clicked.connect(self._zoom_out)
        toolbar.addWidget(zoom_out)
        zoom_in = QPushButton("+")
        zoom_in.setObjectName("pdfZoomInButton")
        zoom_in.clicked.connect(self._zoom_in)
        toolbar.addWidget(zoom_in)
        fit_button = QPushButton("Ajustar")
        fit_button.clicked.connect(self._fit_page)
        toolbar.addWidget(fit_button)
        rotate_button = QPushButton("Girar 90°")
        rotate_button.setObjectName("pdfRotateButton")
        rotate_button.clicked.connect(self._rotate_page)
        toolbar.addWidget(rotate_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._metadata = QLabel("Nenhum PDF aberto")
        self._metadata.setObjectName("pdfMetadataLabel")
        layout.addWidget(self._metadata)
        self.view = PdfGraphicsView()
        layout.addWidget(self.view, 1)

    def selecionar_pdf(self) -> None:
        file_name, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Abrir projeto em PDF",
            "",
            "Documentos PDF (*.pdf)",
        )
        if file_name:
            self.carregar_pdf(Path(file_name))

    def carregar_pdf(self, path: Path, *, password: str | None = None) -> None:
        try:
            inspection = self._reader.inspecionar(path, senha=password)
        except PdfError as error:
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Não foi possível abrir o PDF", str(error))
            return
        self._inspection = inspection
        self._password = password
        self._rotation = 0
        self._page.blockSignals(True)
        self._page.setRange(1, len(inspection.paginas))
        self._page.setValue(1)
        self._page.setEnabled(True)
        self._page.blockSignals(False)
        self._metadata.setText(
            f"{inspection.documento.nome_arquivo}  |  "
            f"{len(inspection.paginas)} página(s)  |  "
            f"SHA-256 {inspection.documento.sha256[:12]}…"
        )
        self._render_current_page()

    def definir_sobreposicoes(self, geometries: tuple[tuple[PontoNormalizado, ...], ...]) -> None:
        self._overlays = geometries
        self._render_current_page()

    def _render_current_page(self) -> None:
        inspection = self._inspection
        if inspection is None:
            return
        page_number = self._page.value()
        try:
            rendered = self._reader.renderizar_pagina(
                inspection.caminho_origem,
                page_number,
                dpi=self._dpi,
                rotacao_adicional_graus=self._rotation,
                senha=self._password,
                sha256_esperado=inspection.documento.sha256,
            )
        except PdfError as error:
            self.status_changed.emit(str(error))
            return
        self.view.definir_pagina(rendered)
        page = inspection.paginas[page_number - 1].pagina
        transformer = TransformadorCoordenadasPagina(
            page,
            dpi=self._dpi,
            largura_pixels=rendered.largura_pixels,
            altura_pixels=rendered.altura_pixels,
            rotacao_adicional_graus=self._rotation,
        )
        self.view.definir_sobreposicoes(self._overlays, transformer)
        diagnostics = len(inspection.paginas[page_number - 1].diagnosticos)
        self.status_changed.emit(
            f"Página {page_number}/{len(inspection.paginas)} - "
            f"{rendered.largura_pixels}x{rendered.altura_pixels}px - "
            f"{diagnostics} diagnóstico(s)"
        )

    def _change_page(self, offset: int) -> None:
        self._page.setValue(self._page.value() + offset)

    def _zoom_in(self) -> None:
        self.view.ampliar()
        self.status_changed.emit(f"Zoom {self.view.zoom:.0%}")

    def _zoom_out(self) -> None:
        self.view.reduzir()
        self.status_changed.emit(f"Zoom {self.view.zoom:.0%}")

    def _fit_page(self) -> None:
        self.view.ajustar_pagina()
        self.status_changed.emit(f"Zoom {self.view.zoom:.0%}")

    def _rotate_page(self) -> None:
        self._rotation = (self._rotation + 90) % 360
        self._render_current_page()
