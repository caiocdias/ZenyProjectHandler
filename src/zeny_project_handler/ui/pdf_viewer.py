"""Visualizador PDF desacoplado do mecanismo concreto de leitura."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QGraphicsPathItem,
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

from zeny_project_handler.adapters.pdf.coordinates import PontoPlano, TransformadorCoordenadasPagina
from zeny_project_handler.adapters.pdf.errors import PdfError
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import EstadoRevisao, TipoGeometria
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import InspecaoPdf, LeitorPdfPort, PaginaPdfRenderizada


class PdfGraphicsView(QGraphicsView):
    """Cena raster com zoom suave e sobreposições em coordenadas normalizadas."""

    proposta_selecionada = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pdfGraphicsView")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._review_items: dict[str, QGraphicsPathItem] = {}
        self._review_geometries: dict[str, GeometriaDocumento] = {}
        self._review_transformer: TransformadorCoordenadasPagina | None = None
        self._zoom = 1.0
        self.setBackgroundBrush(QBrush(QColor("#3b3d40")))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._scene.selectionChanged.connect(self._emit_selected_proposal)

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
        self._review_items.clear()
        self._review_geometries.clear()
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

    def definir_propostas_revisao(
        self,
        proposals: tuple[PropostaElemento, ...],
        transformer: TransformadorCoordenadasPagina,
    ) -> None:
        for item in self._review_items.values():
            self._scene.removeItem(item)
        self._review_items.clear()
        self._review_geometries.clear()
        self._review_transformer = transformer
        for proposal in proposals:
            item = self._scene.addPath(
                _review_path(proposal.geometria, transformer),
                _review_pen(proposal.estado_revisao),
                QBrush(_review_color(proposal.estado_revisao, alpha=42)),
            )
            item.setFlags(
                QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsPathItem.GraphicsItemFlag.ItemIsMovable
            )
            item.setToolTip(
                f"{proposal.categoria.value} · {proposal.estado_revisao.value} · "
                f"confiança {proposal.confianca if proposal.confianca is not None else '-'}"
            )
            key = str(proposal.id)
            item.setData(0, key)
            self._review_items[key] = item
            self._review_geometries[key] = proposal.geometria

    def selecionar_proposta(self, proposal_id: str) -> None:
        item = self._review_items.get(proposal_id)
        if item is None:
            return
        self._scene.clearSelection()
        item.setSelected(True)
        self.centerOn(item)

    def geometria_proposta(self, proposal_id: str) -> GeometriaDocumento | None:
        item = self._review_items.get(proposal_id)
        geometry = self._review_geometries.get(proposal_id)
        transformer = self._review_transformer
        if item is None or geometry is None or transformer is None:
            return None
        normalized_points: list[PontoNormalizado] = []
        for normalized in geometry.pontos:
            pixel = transformer.normalizado_para_pixel(normalized)
            moved = item.mapToScene(QPointF(pixel.x, pixel.y))
            normalized_points.append(
                transformer.pixel_para_normalizado(PontoPlano(moved.x(), moved.y()))
            )
        return GeometriaDocumento(
            pagina_id=geometry.pagina_id,
            tipo=geometry.tipo,
            pontos=tuple(normalized_points),
        )

    def _emit_selected_proposal(self) -> None:
        selected = self._scene.selectedItems()
        if selected and selected[0].data(0):
            self.proposta_selecionada.emit(str(selected[0].data(0)))

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
    page_changed = Signal(str)
    proposal_selected = Signal(str)

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
        self._inspections: tuple[InspecaoPdf, ...] = ()
        self._project_pages: tuple[tuple[InspecaoPdf, int], ...] = ()
        self._pending_paths: tuple[Path, ...] = ()
        self._password: str | None = None
        self._rotation = 0
        self._overlays: tuple[tuple[PontoNormalizado, ...], ...] = ()
        self._review_proposals: tuple[PropostaElemento, ...] = ()
        self._current_transformer: TransformadorCoordenadasPagina | None = None
        self._last_page_id: str | None = None
        self._build_ui()

    @property
    def inspecao(self) -> InspecaoPdf | None:
        return self._inspection

    @property
    def inspecoes(self) -> tuple[InspecaoPdf, ...]:
        """Documentos abertos, na ordem das folhas do projeto."""
        return self._inspections

    @property
    def folha_atual(self) -> int:
        return self._page.value()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        open_button = QPushButton("Selecionar PDF(s)")
        open_button.setObjectName("openPdfButton")
        open_button.clicked.connect(self.selecionar_pdf)
        toolbar.addWidget(open_button)

        self._merge_button = QPushButton("Unir arquivos em um só projeto")
        self._merge_button.setObjectName("mergePdfsIntoProjectButton")
        self._merge_button.setEnabled(False)
        self._merge_button.clicked.connect(self.unir_arquivos_em_projeto)
        toolbar.addWidget(self._merge_button)

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
        self.view.proposta_selecionada.connect(self.proposal_selected)
        layout.addWidget(self.view, 1)

    def selecionar_pdf(self) -> None:
        file_names, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "Selecionar folhas do projeto em PDF",
            "",
            "Documentos PDF (*.pdf)",
        )
        paths = tuple(Path(file_name) for file_name in file_names)
        if not paths:
            return
        if len(paths) == 1:
            self._pending_paths = ()
            self._merge_button.setEnabled(False)
            self.carregar_pdf(paths[0])
            return
        self._pending_paths = paths
        self._merge_button.setEnabled(True)
        self._metadata.setText(
            f"{len(paths)} PDFs selecionados; clique em “Unir arquivos em um só projeto”"
        )
        self.status_changed.emit(
            f"{len(paths)} arquivos selecionados na ordem em que serão exibidos"
        )

    def unir_arquivos_em_projeto(self) -> None:
        """Abra os PDFs selecionados como documentos ordenados de um mesmo projeto."""
        if len(self._pending_paths) < 2:
            return
        if self.carregar_projeto(self._pending_paths):
            self._pending_paths = ()
            self._merge_button.setEnabled(False)

    def carregar_pdf(self, path: Path, *, password: str | None = None) -> bool:
        return self.carregar_projeto((path,), password=password)

    def limpar(self) -> None:
        self._inspection = None
        self._inspections = ()
        self._project_pages = ()
        self._overlays = ()
        self._review_proposals = ()
        self._current_transformer = None
        self._last_page_id = None
        self._page.blockSignals(True)
        self._page.setRange(1, 1)
        self._page.setValue(1)
        self._page.setEnabled(False)
        self._page.blockSignals(False)
        self._metadata.setText("Projeto sem PDF importado")
        self.view.scene().clear()

    def ir_para_folha(self, numero: int) -> None:
        if not self._project_pages:
            return
        self._page.setValue(min(max(1, numero), len(self._project_pages)))

    def carregar_projeto(
        self,
        paths: tuple[Path, ...],
        *,
        password: str | None = None,
    ) -> bool:
        """Valide todos os PDFs antes de substituir o projeto atualmente exibido."""
        if not paths:
            return False
        try:
            inspections = tuple(self._reader.inspecionar(path, senha=password) for path in paths)
        except PdfError as error:
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Não foi possível abrir o PDF", str(error))
            return False
        hashes = [inspection.documento.sha256 for inspection in inspections]
        if len(set(hashes)) != len(hashes):
            message = "A seleção contém arquivos PDF com conteúdo duplicado"
            self.status_changed.emit(message)
            QMessageBox.warning(self, "Não foi possível unir os arquivos", message)
            return False
        self._activate_project(inspections, password=password)
        return True

    def _activate_project(
        self,
        inspections: tuple[InspecaoPdf, ...],
        *,
        password: str | None,
    ) -> None:
        self._inspections = inspections
        self._overlays = ()
        self._review_proposals = ()
        self._last_page_id = None
        self._project_pages = tuple(
            (inspection, local_page_number)
            for inspection in inspections
            for local_page_number in range(1, len(inspection.paginas) + 1)
        )
        self._inspection = inspections[0]
        self._password = password
        self._rotation = 0
        self._page.blockSignals(True)
        self._page.setRange(1, len(self._project_pages))
        self._page.setValue(1)
        self._page.setEnabled(True)
        self._page.blockSignals(False)
        self._render_current_page()

    def definir_sobreposicoes(self, geometries: tuple[tuple[PontoNormalizado, ...], ...]) -> None:
        self._overlays = geometries
        self._render_current_page()

    def definir_propostas_revisao(self, proposals: tuple[PropostaElemento, ...]) -> None:
        self._review_proposals = proposals
        if self._current_transformer is not None:
            self.view.definir_propostas_revisao(proposals, self._current_transformer)

    def selecionar_proposta(self, proposal_id: str) -> None:
        self.view.selecionar_proposta(proposal_id)

    def geometria_proposta(self, proposal_id: str) -> GeometriaDocumento | None:
        return self.view.geometria_proposta(proposal_id)

    def _render_current_page(self) -> None:
        if not self._project_pages:
            return
        project_page_number = self._page.value()
        inspection, page_number = self._project_pages[project_page_number - 1]
        self._inspection = inspection
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
        self._current_transformer = transformer
        self.view.definir_sobreposicoes(self._overlays, transformer)
        self.view.definir_propostas_revisao(self._review_proposals, transformer)
        diagnostics = len(inspection.paginas[page_number - 1].diagnosticos)
        if len(self._inspections) == 1:
            self._metadata.setText(
                f"{inspection.documento.nome_arquivo}  |  "
                f"{len(inspection.paginas)} página(s)  |  "
                f"SHA-256 {inspection.documento.sha256[:12]}…"
            )
        else:
            document_position = self._inspections.index(inspection) + 1
            self._metadata.setText(
                f"Projeto unido: {len(self._inspections)} arquivos, "
                f"{len(self._project_pages)} folhas  |  "
                f"Arquivo {document_position}: {inspection.documento.nome_arquivo}"
            )
        self.status_changed.emit(
            f"Folha {project_page_number}/{len(self._project_pages)} - "
            f"página {page_number}/{len(inspection.paginas)} de "
            f"{inspection.documento.nome_arquivo} - "
            f"{rendered.largura_pixels}x{rendered.altura_pixels}px - "
            f"{diagnostics} diagnóstico(s)"
        )
        page_id = str(page.id)
        if page_id != self._last_page_id:
            self._last_page_id = page_id
            self.page_changed.emit(page_id)

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


def _review_color(state: EstadoRevisao, *, alpha: int = 255) -> QColor:
    colors = {
        EstadoRevisao.PROPOSTA: (255, 193, 7),
        EstadoRevisao.CONFIRMADA: (52, 199, 89),
        EstadoRevisao.REJEITADA: (142, 142, 147),
        EstadoRevisao.CONFLITANTE: (255, 69, 58),
    }
    red, green, blue = colors[state]
    return QColor(red, green, blue, alpha)


def _review_pen(state: EstadoRevisao) -> QPen:
    pen = QPen(_review_color(state), 3)
    pen.setCosmetic(True)
    if state is EstadoRevisao.REJEITADA:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _review_path(
    geometry: GeometriaDocumento,
    transformer: TransformadorCoordenadasPagina,
) -> QPainterPath:
    pixels = tuple(transformer.normalizado_para_pixel(point) for point in geometry.pontos)
    path = QPainterPath()
    if geometry.tipo is TipoGeometria.PONTO:
        point = pixels[0]
        path.addEllipse(QPointF(point.x, point.y), 8, 8)
        return path
    if geometry.tipo is TipoGeometria.CAIXA:
        first, second = pixels
        path.addRect(
            min(first.x, second.x),
            min(first.y, second.y),
            abs(second.x - first.x),
            abs(second.y - first.y),
        )
        return path
    path.moveTo(pixels[0].x, pixels[0].y)
    for point in pixels[1:]:
        path.lineTo(point.x, point.y)
    if geometry.tipo is TipoGeometria.POLIGONO:
        path.closeSubpath()
    return path
