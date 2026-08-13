"""Visualizador PDF desacoplado do mecanismo concreto de leitura."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QFontDatabase,
    QFontInfo,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
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
from zeny_project_handler.adapters.pdf.errors import PdfError, PdfOrigemAlteradaError
from zeny_project_handler.application.compliance_callouts import (
    CalloutConformidade,
    ponto_conexao_callout,
)
from zeny_project_handler.application.pdf_credentials import (
    IdentidadeCredencialPdf,
    ProvedorCredenciaisPdfMemoria,
    identificar_origem_pdf,
)
from zeny_project_handler.config import DEFAULT_PDF_TILE_CACHE_MAX_BYTES
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import EstadoRevisao, TipoGeometria
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.logging_config import OperationLogger, operation_logger
from zeny_project_handler.ports.pdf import (
    InspecaoPdf,
    LeitorPdfPort,
    OrcamentoRenderizacaoPdf,
    PlanoRenderizacaoPdf,
    ReferenciaFontePdf,
    SessaoLeituraPdfPort,
)

from .pdf_credentials import EstadoResolucaoCredencialPdf, ResolvedorCredenciaisPdf
from .pdf_rendering import (
    CacheLruBytes,
    CancelamentoRenderizacao,
    ChaveCacheRenderizacao,
    FilaRenderizacao,
    IdentidadeDocumentoRenderizacao,
    RasterRgbRenderizado,
    ResultadoRenderizacao,
    SolicitacaoRenderizacao,
    TrabalhoRenderizacao,
    regioes_tiles_priorizadas,
)

_FONTE_CALLOUT_REGISTRO_TENTADO = False


@dataclass(frozen=True, slots=True)
class _RasterEmCache:
    pixmap: QPixmap
    plano: PlanoRenderizacaoPdf


@dataclass(frozen=True, slots=True)
class _ResultadoAberturaSessoes:
    sessoes: tuple[SessaoLeituraPdfPort, ...] = ()
    identidades: frozenset[IdentidadeCredencialPdf] = frozenset()
    mensagem_interrupcao: str | None = None
    cancelada: bool = False


@dataclass(frozen=True, slots=True)
class _GraficosCallout:
    caixa: QGraphicsRectItem
    texto: QGraphicsTextItem
    linhas: tuple[QGraphicsPathItem, ...]


class ReviewLinkItem(QGraphicsPathItem):
    """Sublinhado com área de clique confortável, mesmo em zoom reduzido."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())


class CalloutLinkItem(QGraphicsPathItem):
    """Seta de callout com área de clique confortável em qualquer zoom."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())


class PdfGraphicsView(QGraphicsView):
    """Cena raster com zoom suave e sobreposições em coordenadas normalizadas."""

    proposta_selecionada = Signal(str)
    callout_selecionado = Signal(str)
    viewport_alterado = Signal()
    zoom_alterado = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pdfGraphicsView")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._tile_items: dict[ChaveCacheRenderizacao, QGraphicsPixmapItem] = {}
        self._overlay_items: list[QGraphicsPathItem] = []
        self._review_items: dict[str, QGraphicsPathItem] = {}
        self._review_geometries: dict[str, GeometriaDocumento] = {}
        self._review_transformer: TransformadorCoordenadasPagina | None = None
        self._callout_layer: QGraphicsRectItem | None = None
        self._callout_items: dict[str, _GraficosCallout] = {}
        self._selected_callout_id: str | None = None
        self._zoom = 1.0
        self.setBackgroundBrush(QBrush(QColor("#3b3d40")))
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._scene.selectionChanged.connect(self._emit_selected_item)

    @property
    def zoom(self) -> float:
        return self._zoom

    def definir_previa(self, pixmap: QPixmap) -> None:
        self._review_items.clear()
        self._review_geometries.clear()
        self._tile_items.clear()
        self._overlay_items.clear()
        self._callout_layer = None
        self._callout_items.clear()
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._pixmap_item.setZValue(0)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self.ajustar_pagina(notificar=False)

    def adicionar_tile(
        self,
        key: ChaveCacheRenderizacao,
        pixmap: QPixmap,
        *,
        plano: PlanoRenderizacaoPdf,
        plano_previa: PlanoRenderizacaoPdf,
    ) -> None:
        if self._pixmap_item is None or key in self._tile_items:
            return
        scale_x = plano_previa.largura_pagina_pixels / plano.largura_pagina_pixels
        scale_y = plano_previa.altura_pagina_pixels / plano.altura_pagina_pixels
        item = self._scene.addPixmap(pixmap)
        item.setZValue(1)
        item.setTransform(QTransform.fromScale(scale_x, scale_y))
        item.setPos(plano.origem_x_pixels * scale_x, plano.origem_y_pixels * scale_y)
        self._tile_items[key] = item

    def limpar_tiles(self) -> None:
        for item in self._tile_items.values():
            self._scene.removeItem(item)
        self._tile_items.clear()

    def limpar(self) -> None:
        self._review_items.clear()
        self._review_geometries.clear()
        self._review_transformer = None
        self._tile_items.clear()
        self._overlay_items.clear()
        self._callout_layer = None
        self._callout_items.clear()
        self._scene.clear()
        self._pixmap_item = None

    def definir_sobreposicoes(
        self,
        geometries: tuple[tuple[PontoNormalizado, ...], ...],
        transformer: TransformadorCoordenadasPagina,
    ) -> None:
        if self._pixmap_item is None:
            return
        for item in self._overlay_items:
            self._scene.removeItem(item)
        self._overlay_items.clear()
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
            item = self._scene.addPath(path, pen)
            item.setZValue(10)
            self._overlay_items.append(item)

    def definir_callouts_conformidade(
        self,
        callouts: tuple[CalloutConformidade, ...],
        transformer: TransformadorCoordenadasPagina,
    ) -> None:
        """Reconstrua a camada vetorial de callouts sem tocar no raster ou nos links."""
        self._remover_camada_callouts()
        if self._pixmap_item is None:
            return
        layer = QGraphicsRectItem(self._scene.sceneRect())
        layer.setPen(QPen(Qt.PenStyle.NoPen))
        layer.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        layer.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        layer.setZValue(30)
        self._scene.addItem(layer)
        self._callout_layer = layer
        for callout in callouts:
            if callout.pagina_id != transformer.pagina.id:
                continue
            self._callout_items[str(callout.id)] = _criar_graficos_callout(
                callout,
                transformer,
                layer,
                zoom=self._zoom,
            )
        self._atualizar_realce_callouts()

    def _remover_camada_callouts(self) -> None:
        layer = self._callout_layer
        self._callout_items.clear()
        self._callout_layer = None
        if layer is not None and layer.scene() is self._scene:
            self._scene.removeItem(layer)

    def definir_propostas_revisao(
        self,
        proposals: tuple[PropostaElemento, ...],
        transformer: TransformadorCoordenadasPagina,
        link_geometries: Mapping[str, GeometriaDocumento] | None = None,
    ) -> None:
        signals_were_blocked = self._scene.blockSignals(True)
        try:
            for item in self._review_items.values():
                self._scene.removeItem(item)
            self._review_items.clear()
            self._review_geometries.clear()
        finally:
            self._scene.blockSignals(signals_were_blocked)
        self._review_transformer = transformer
        for proposal in proposals:
            key = str(proposal.id)
            link_geometry = (
                link_geometries.get(key, proposal.geometria)
                if link_geometries is not None
                else proposal.geometria
            )
            item = ReviewLinkItem(
                _review_link_path(link_geometry, transformer),
            )
            item.setPen(_review_link_pen(proposal.estado_revisao))
            self._scene.addItem(item)
            item.setZValue(20)
            item.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.setToolTip(
                f"Abrir {proposal.categoria.value} na revisão · "
                f"{proposal.estado_revisao.value} · "
                f"confiança {proposal.confianca if proposal.confianca is not None else '-'}"
            )
            item.setData(0, key)
            item.setData(1, proposal.estado_revisao.value)
            item.setData(2, "review_proposal")
            self._review_items[key] = item
            self._review_geometries[key] = proposal.geometria

    def selecionar_proposta(self, proposal_id: str) -> None:
        item = self._review_items.get(proposal_id)
        if item is None:
            return
        self._scene.clearSelection()
        item.setSelected(True)
        self.centerOn(item)

    def selecionar_callout(self, callout_id: str) -> None:
        """Realce e centralize sem reemitir a seleção programática."""
        self._selected_callout_id = callout_id
        self._atualizar_realce_callouts()
        graphics = self._callout_items.get(callout_id)
        if graphics is not None:
            self.centerOn(graphics.caixa)

    def limpar_selecao_callout(self) -> None:
        self._selected_callout_id = None
        self._atualizar_realce_callouts()

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

    def _emit_selected_item(self) -> None:
        selected = self._scene.selectedItems()
        selected_item = selected[0] if selected else None
        selected_id = (
            str(selected_item.data(0))
            if selected_item is not None and selected_item.data(0)
            else None
        )
        selected_kind = selected_item.data(2) if selected_item is not None else None
        for key, item in self._review_items.items():
            item.setPen(
                _review_link_pen(
                    EstadoRevisao(str(item.data(1))),
                    selected=selected_kind == "review_proposal" and key == selected_id,
                )
            )
        if selected_kind == "compliance_callout" and selected_id is not None:
            self._selected_callout_id = selected_id
            self._atualizar_realce_callouts()
            self.callout_selecionado.emit(selected_id)
        elif selected_kind == "review_proposal" and selected_id is not None:
            self.proposta_selecionada.emit(selected_id)

    def _atualizar_realce_callouts(self) -> None:
        for callout_id, graphics in self._callout_items.items():
            selected = callout_id == self._selected_callout_id
            color = QColor("#8e0000" if selected else "#c62828")
            pen = QPen(color, 3.2 if selected else 2.0)
            pen.setCosmetic(True)
            graphics.caixa.setPen(pen)
            graphics.caixa.setBrush(QBrush(QColor("#fff3e0") if selected else QColor("white")))
            graphics.caixa.setZValue(4 if selected else 1)
            graphics.texto.setDefaultTextColor(color)
            graphics.texto.setZValue(5 if selected else 2)
            for line in graphics.linhas:
                line.setPen(pen)
                line.setZValue(3 if selected else 0)

    def definir_zoom(self, value: float) -> None:
        self._zoom = min(16.0, max(0.05, value))
        self.resetTransform()
        self.scale(self._zoom, self._zoom)
        self.zoom_alterado.emit(self._zoom)

    def ampliar(self) -> None:
        self.definir_zoom(self._zoom * 1.25)

    def reduzir(self) -> None:
        self.definir_zoom(self._zoom / 1.25)

    def ajustar_pagina(self, *, notificar: bool = True) -> None:
        if self._pixmap_item is None:
            return
        self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        if notificar:
            self.zoom_alterado.emit(self._zoom)

    def viewport_normalizado(self) -> tuple[float, float, float, float]:
        scene_rect = self._scene.sceneRect()
        if self._pixmap_item is None or scene_rect.isEmpty():
            return (0.0, 0.0, 1.0, 1.0)
        visible = self.mapToScene(self.viewport().rect()).boundingRect().intersected(scene_rect)
        if visible.isEmpty():
            return (0.0, 0.0, 1.0, 1.0)
        return (
            max(0.0, visible.left() / scene_rect.width()),
            max(0.0, visible.top() / scene_rect.height()),
            min(1.0, visible.right() / scene_rect.width()),
            min(1.0, visible.bottom() / scene_rect.height()),
        )

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - API Qt
        super().scrollContentsBy(dx, dy)
        self.viewport_alterado.emit()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        self.viewport_alterado.emit()

    def event(self, event: QEvent) -> bool:
        handled = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self.viewport_alterado.emit()
        return handled

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
    compliance_callout_selected = Signal(str)

    def __init__(
        self,
        *,
        leitor: LeitorPdfPort,
        dpi: int,
        orcamento: OrcamentoRenderizacaoPdf,
        cache_limite_bytes: int = DEFAULT_PDF_TILE_CACHE_MAX_BYTES,
        resolvedor_credenciais: ResolvedorCredenciaisPdf | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pdfViewerWidget")
        self._reader = leitor
        self._credential_resolver = resolvedor_credenciais or ResolvedorCredenciaisPdf(
            ProvedorCredenciaisPdfMemoria()
        )
        self._dpi = dpi
        self._render_budget = orcamento
        self._render_cache: CacheLruBytes[ChaveCacheRenderizacao, _RasterEmCache] = CacheLruBytes(
            cache_limite_bytes
        )
        self._render_queue = FilaRenderizacao()
        self._generation = 0
        self._render_cancellation = CancelamentoRenderizacao()
        self._scheduled_requests: set[ChaveCacheRenderizacao] = set()
        self._retired_sessions: list[tuple[SessaoLeituraPdfPort, ...]] = []
        self._current_preview: _RasterEmCache | None = None
        self._closed = False
        self._inspection: InspecaoPdf | None = None
        self._inspections: tuple[InspecaoPdf, ...] = ()
        self._sessions: tuple[SessaoLeituraPdfPort, ...] = ()
        self._project_pages: tuple[tuple[InspecaoPdf, SessaoLeituraPdfPort, int], ...] = ()
        self._rotation = 0
        self._overlays: tuple[tuple[PontoNormalizado, ...], ...] = ()
        self._review_proposals: tuple[PropostaElemento, ...] = ()
        self._review_link_geometries: dict[str, GeometriaDocumento] = {}
        self._compliance_callouts: tuple[CalloutConformidade, ...] = ()
        self._selected_compliance_callout_id: str | None = None
        self._current_transformer: TransformadorCoordenadasPagina | None = None
        self._last_page_id: str | None = None
        self._build_ui()
        self._detail_timer = QTimer(self)
        self._detail_timer.setSingleShot(True)
        self._detail_timer.setInterval(0)
        self._detail_timer.timeout.connect(self._schedule_viewport_tiles)
        self._result_timer = QTimer(self)
        self._result_timer.setInterval(1)
        self._result_timer.timeout.connect(self._drain_render_results)
        self.view.zoom_alterado.connect(self._zoom_changed)
        self.view.viewport_alterado.connect(self._viewport_changed)

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
        open_button = QPushButton("Abrir PDF(s)")
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
        self.view.proposta_selecionada.connect(self.proposal_selected)
        self.view.callout_selecionado.connect(self._callout_selected)
        layout.addWidget(self.view, 1)

    def selecionar_pdf(self) -> None:
        observation = operation_logger("pdf.viewer.selection")
        with observation.context():
            observation.started()
            file_names, _selected_filter = QFileDialog.getOpenFileNames(
                self,
                "Selecionar folhas do projeto em PDF",
                "",
                "Documentos PDF (*.pdf)",
            )
            paths = tuple(Path(file_name) for file_name in file_names)
            if not paths:
                observation.cancelled()
                return
            observation.succeeded(item_count=len(paths))
            self.carregar_projeto(paths)

    def carregar_pdf(self, path: Path, *, password: str | None = None) -> bool:
        if password is not None:
            self._credential_resolver.provedor.guardar(identificar_origem_pdf(path), password)
        return self.carregar_projeto((path,))

    def limpar(self) -> None:
        self._cancel_current_rendering()
        self._render_cache.limpar()
        self._current_preview = None
        self._retire_sessions(self._sessions)
        self._sessions = ()
        self._inspection = None
        self._inspections = ()
        self._project_pages = ()
        self._overlays = ()
        self._review_proposals = ()
        self._review_link_geometries = {}
        self._compliance_callouts = ()
        self._selected_compliance_callout_id = None
        self._current_transformer = None
        self._last_page_id = None
        self._page.blockSignals(True)
        self._page.setRange(1, 1)
        self._page.setValue(1)
        self._page.setEnabled(False)
        self._page.blockSignals(False)
        self._metadata.setText("Projeto sem PDF importado")
        self.view.limpar()
        self.view.limpar_selecao_callout()
        self._credential_resolver.provedor.limpar()

    def preparar_para_restauracao(self, timeout_ms: int) -> bool:
        """Libere sessões PDF antes de substituir arquivos; nunca espere sem limite."""
        _require_ui_thread()
        if self._closed:
            return True
        self._cancel_current_rendering()
        if not self._render_queue.cancelar_e_aguardar_ociosa(timeout_ms):
            return False
        self._render_queue.retirar_resultados()
        self._liberar_sessoes_apos_renderizacao()
        self.limpar()
        return True

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        self.encerrar()
        super().closeEvent(event)

    def encerrar(self) -> None:
        """Pare a fila e libere sessões mesmo quando o contêiner fecha o widget central."""
        if not self._closed:
            self._closed = True
            self._detail_timer.stop()
            self._result_timer.stop()
            self._render_cancellation.cancelar()
            self._render_queue.encerrar()
            if self._render_queue.isRunning():
                self._render_queue.wait()
            self._render_queue.retirar_resultados()
            sessions = self._sessions
            self._sessions = ()
            retired = tuple(session for group in self._retired_sessions for session in group)
            self._retired_sessions.clear()
            _close_sessions((*sessions, *retired))
            self._render_cache.limpar()
            self._credential_resolver.provedor.limpar()

    def ir_para_folha(self, numero: int) -> None:
        if not self._project_pages:
            return
        self._page.setValue(min(max(1, numero), len(self._project_pages)))

    def carregar_projeto(
        self,
        paths: tuple[Path, ...],
        *,
        documentos: tuple[DocumentoProjeto, ...] | None = None,
        fontes: tuple[ReferenciaFontePdf, ...] | None = None,
        ordem_paginas: tuple[UUID, ...] | None = None,
    ) -> bool:
        """Valide todos os PDFs antes de substituir o projeto atualmente exibido."""
        observation = operation_logger("pdf.viewer.open")
        with observation.context():
            observation.started(item_count=len(paths))
            if not paths:
                observation.cancelled()
                return False
            try:
                return self._load_project(
                    paths,
                    documentos=documentos,
                    fontes=fontes,
                    ordem_paginas=ordem_paginas,
                    observation=observation,
                )
            except Exception as error:
                observation.failed(error, expected=False)
                raise

    def _load_project(
        self,
        paths: tuple[Path, ...],
        *,
        documentos: tuple[DocumentoProjeto, ...] | None,
        fontes: tuple[ReferenciaFontePdf, ...] | None,
        ordem_paginas: tuple[UUID, ...] | None,
        observation: OperationLogger,
    ) -> bool:
        if documentos is not None and len(documentos) != len(paths):
            error = ValueError(
                "A quantidade de fontes PDF não corresponde aos documentos persistidos"
            )
            observation.failed(error, expected=True)
            self._open_warning(str(error))
            return False
        if fontes is not None and len(fontes) != len(paths):
            error = ValueError("A quantidade de fontes PDF não corresponde aos caminhos informados")
            observation.failed(error, expected=True)
            self._open_warning(str(error))
            return False
        try:
            opening = _open_verified_sessions(
                self._reader,
                paths,
                parent=self,
                resolvedor=self._credential_resolver,
                documents=documentos,
                sources=fontes,
            )
        except PdfError as error:
            observation.failed(error, expected=True)
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Não foi possível abrir o PDF", str(error))
            return False
        if opening.mensagem_interrupcao is not None:
            if opening.cancelada:
                observation.cancelled()
            else:
                observation.failed(ValueError(opening.mensagem_interrupcao), expected=True)
            self._open_warning(opening.mensagem_interrupcao)
            return False
        sessions = opening.sessoes
        inspections = tuple(session.inspecao for session in sessions)
        if documentos is not None:
            try:
                inspections = tuple(
                    _align_persisted_document(inspection, document)
                    for inspection, document in zip(inspections, documentos, strict=True)
                )
            except ValueError as error:
                _close_sessions(sessions)
                observation.failed(error, expected=True)
                self._open_warning(str(error))
                return False
        try:
            project_pages = _ordered_project_pages(inspections, sessions, ordem_paginas)
        except ValueError as error:
            _close_sessions(sessions)
            observation.failed(error, expected=True)
            self._open_warning(str(error))
            return False
        hashes = [inspection.documento.sha256 for inspection in inspections]
        if len(set(hashes)) != len(hashes):
            _close_sessions(sessions)
            message = "A seleção contém arquivos PDF com conteúdo duplicado"
            observation.failed(ValueError(message), expected=True)
            self.status_changed.emit(message)
            QMessageBox.warning(self, "Não foi possível abrir os arquivos", message)
            return False
        self._activate_project(
            inspections,
            sessions=sessions,
            project_pages=project_pages,
        )
        self._credential_resolver.provedor.reter(set(opening.identidades))
        observation.succeeded(
            item_count=len(inspections),
            document_ids=tuple(item.documento.id for item in inspections),
        )
        return True

    def _open_warning(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Não foi possível abrir os arquivos", message)

    def _activate_project(
        self,
        inspections: tuple[InspecaoPdf, ...],
        *,
        sessions: tuple[SessaoLeituraPdfPort, ...],
        project_pages: tuple[tuple[InspecaoPdf, SessaoLeituraPdfPort, int], ...],
    ) -> None:
        previous_sessions = self._sessions
        self._cancel_current_rendering()
        self._render_cache.limpar()
        self._current_preview = None
        self.view.limpar()
        self._inspections = inspections
        self._sessions = sessions
        self._overlays = ()
        self._review_proposals = ()
        self._review_link_geometries = {}
        self._compliance_callouts = ()
        self._selected_compliance_callout_id = None
        self._last_page_id = None
        self._project_pages = project_pages
        self._inspection = inspections[0]
        self._rotation = 0
        self.view.limpar_selecao_callout()
        self._page.blockSignals(True)
        self._page.setRange(1, len(self._project_pages))
        self._page.setValue(1)
        self._page.setEnabled(True)
        self._page.blockSignals(False)
        self._retire_sessions(previous_sessions)
        self._render_current_page()

    def definir_sobreposicoes(self, geometries: tuple[tuple[PontoNormalizado, ...], ...]) -> None:
        self._overlays = geometries
        if self._current_transformer is not None:
            self.view.definir_sobreposicoes(geometries, self._current_transformer)

    def definir_propostas_revisao(
        self,
        proposals: tuple[PropostaElemento, ...],
        *,
        geometrias_links: Mapping[UUID, GeometriaDocumento] | None = None,
    ) -> None:
        self._review_proposals = proposals
        self._review_link_geometries = {
            str(proposal_id): geometry for proposal_id, geometry in (geometrias_links or {}).items()
        }
        if self._current_transformer is not None:
            self.view.definir_propostas_revisao(
                proposals,
                self._current_transformer,
                self._review_link_geometries,
            )

    def definir_callouts_conformidade(
        self,
        callouts: tuple[CalloutConformidade, ...],
    ) -> None:
        self._compliance_callouts = callouts
        visible_ids = {str(item.id) for item in callouts}
        if self._selected_compliance_callout_id not in visible_ids:
            self._selected_compliance_callout_id = None
            self.view.limpar_selecao_callout()
        if self._current_transformer is not None:
            self.view.definir_callouts_conformidade(callouts, self._current_transformer)
            if self._selected_compliance_callout_id is not None:
                self.view.selecionar_callout(self._selected_compliance_callout_id)

    def selecionar_callout(self, callout_id: str) -> None:
        if all(str(item.id) != callout_id for item in self._compliance_callouts):
            return
        self._selected_compliance_callout_id = callout_id
        self.view.selecionar_callout(callout_id)

    def _callout_selected(self, callout_id: str) -> None:
        self._selected_compliance_callout_id = callout_id
        self.compliance_callout_selected.emit(callout_id)

    def selecionar_proposta(self, proposal_id: str) -> None:
        self.view.selecionar_proposta(proposal_id)

    def geometria_proposta(self, proposal_id: str) -> GeometriaDocumento | None:
        return self.view.geometria_proposta(proposal_id)

    def _render_current_page(self) -> None:
        if not self._project_pages:
            return
        project_page_number = self._page.value()
        inspection, session, page_number = self._project_pages[project_page_number - 1]
        self._inspection = inspection
        self._cancel_current_rendering()
        self._current_preview = None
        self._current_transformer = None
        self.view.limpar()
        self._update_metadata(inspection)
        page_id = str(inspection.paginas[page_number - 1].pagina.id)
        if page_id != self._last_page_id:
            self._last_page_id = page_id
            self.page_changed.emit(page_id)
        request = self._new_request(
            inspection,
            page_number=page_number,
            region=(0.0, 0.0, 1.0, 1.0),
            dpi=self._dpi,
            preview=True,
        )
        self._request_raster(request, session=session, priority=-2_000_000)

    def _new_request(
        self,
        inspection: InspecaoPdf,
        *,
        page_number: int,
        region: tuple[float, float, float, float],
        dpi: int,
        preview: bool,
    ) -> SolicitacaoRenderizacao:
        return SolicitacaoRenderizacao(
            geracao=self._generation,
            documento=_render_document_identity(inspection),
            pagina=page_number,
            rotacao=self._rotation,
            zoom=_stable_scale(self.view.zoom),
            device_pixel_ratio=_stable_scale(self.view.devicePixelRatioF()),
            regiao=region,
            dpi=dpi,
            previa=preview,
        )

    def _request_raster(
        self,
        request: SolicitacaoRenderizacao,
        *,
        session: SessaoLeituraPdfPort,
        priority: int,
    ) -> None:
        if request.chave_cache in self._scheduled_requests:
            return
        self._scheduled_requests.add(request.chave_cache)
        cached = self._render_cache.obter(request.chave_cache)
        if cached is not None:
            self._apply_raster(request, cached)
            return
        submitted = self._render_queue.enviar(
            TrabalhoRenderizacao(
                solicitacao=request,
                sessao=session,
                orcamento=self._render_budget,
                prioridade=priority,
                cancelamento=self._render_cancellation,
            )
        )
        if submitted:
            self._result_timer.start()

    def _drain_render_results(self) -> None:
        _require_ui_thread()
        for result in self._render_queue.retirar_resultados():
            self._dispatch_render_result(result)
        if self._render_queue.esta_ociosa():
            self._result_timer.stop()
            self._liberar_sessoes_apos_renderizacao()

    def _dispatch_render_result(self, result: ResultadoRenderizacao) -> None:
        if result.pagina is not None:
            self._receber_renderizacao(result.solicitacao, result.pagina)
            return
        assert result.erro is not None
        self._receber_falha_renderizacao(result.solicitacao, result.erro)

    def _receber_renderizacao(
        self,
        request: SolicitacaoRenderizacao,
        rendered: RasterRgbRenderizado,
    ) -> None:
        _require_ui_thread()
        if not self._request_is_current(request):
            if request.previa and self._request_needs_replacement(request):
                self._render_current_page()
            return
        self._scheduled_requests.discard(request.chave_cache)
        if (
            rendered.pagina_numero != request.pagina
            or rendered.rotacao_adicional_graus != request.rotacao
            or rendered.plano.dpi_solicitado != request.dpi
            or (
                (request.previa and not rendered.plano.pagina_inteira)
                or (not request.previa and rendered.plano.recorte_normalizado != request.regiao)
            )
        ):
            self.status_changed.emit("O backend devolveu uma região PDF incompatível")
            return
        raster = _RasterEmCache(
            pixmap=_rgb_to_pixmap(rendered),
            plano=rendered.plano,
        )
        self._render_cache.armazenar(
            request.chave_cache,
            raster,
            tamanho_bytes=_pixmap_size_bytes(raster.pixmap),
        )
        self._apply_raster(request, raster)

    def _apply_raster(
        self,
        request: SolicitacaoRenderizacao,
        raster: _RasterEmCache,
    ) -> None:
        if not self._request_is_current(request):
            return
        if request.previa:
            self._finish_preview(request, raster)
            return
        preview = self._current_preview
        if preview is None:
            return
        self.view.adicionar_tile(
            request.chave_cache,
            raster.pixmap,
            plano=raster.plano,
            plano_previa=preview.plano,
        )

    def _finish_preview(
        self,
        request: SolicitacaoRenderizacao,
        raster: _RasterEmCache,
    ) -> None:
        if not raster.plano.pagina_inteira:
            self.status_changed.emit("A prévia do PDF não corresponde à página inteira")
            return
        inspection, _session, page_number = self._current_page_context()
        self._current_preview = raster
        signals_blocked = self.view.blockSignals(True)
        try:
            self.view.definir_previa(raster.pixmap)
        finally:
            self.view.blockSignals(signals_blocked)
        page = inspection.paginas[page_number - 1].pagina
        transformer = TransformadorCoordenadasPagina(
            page,
            dpi=raster.plano.dpi_efetivo,
            largura_pixels=raster.plano.largura_pixels,
            altura_pixels=raster.plano.altura_pixels,
            largura_pagina_pixels=raster.plano.largura_pagina_pixels,
            altura_pagina_pixels=raster.plano.altura_pagina_pixels,
            origem_x_pixels=raster.plano.origem_x_pixels,
            origem_y_pixels=raster.plano.origem_y_pixels,
            rotacao_adicional_graus=request.rotacao,
        )
        self._current_transformer = transformer
        self.view.definir_sobreposicoes(self._overlays, transformer)
        self.view.definir_propostas_revisao(
            self._review_proposals,
            transformer,
            self._review_link_geometries,
        )
        self.view.definir_callouts_conformidade(self._compliance_callouts, transformer)
        if self._selected_compliance_callout_id is not None:
            self.view.selecionar_callout(self._selected_compliance_callout_id)
        diagnostics = len(inspection.paginas[page_number - 1].diagnosticos)
        project_page_number = self._page.value()
        self.status_changed.emit(
            f"Folha {project_page_number}/{len(self._project_pages)} - "
            f"página {page_number}/{len(inspection.paginas)} de "
            f"{inspection.documento.nome_arquivo} - "
            f"{raster.plano.largura_pixels}x{raster.plano.altura_pixels}px - "
            f"{raster.plano.dpi_efetivo}/{raster.plano.dpi_solicitado} DPI - "
            f"{diagnostics} diagnóstico(s)"
        )
        self._cancel_current_rendering()
        self._detail_timer.start()

    def _update_metadata(self, inspection: InspecaoPdf) -> None:
        if len(self._inspections) == 1:
            self._metadata.setText(
                f"{inspection.documento.nome_arquivo}  |  "
                f"{len(inspection.paginas)} página(s)  |  "
                f"SHA-256 {inspection.documento.sha256[:12]}…"
            )
        else:
            document_position = self._inspections.index(inspection) + 1
            self._metadata.setText(
                f"Projeto: {len(self._inspections)} PDFs, "
                f"{len(self._project_pages)} folhas  |  "
                f"Arquivo {document_position}: {inspection.documento.nome_arquivo}"
            )

    def _schedule_viewport_tiles(self) -> None:
        if self._closed or self._current_preview is None or not self._project_pages:
            return
        preview = self._current_preview
        target_dpi = min(
            self._dpi,
            max(
                1,
                math.ceil(
                    preview.plano.dpi_efetivo * self.view.zoom * self.view.devicePixelRatioF()
                ),
            ),
        )
        if target_dpi <= preview.plano.dpi_efetivo:
            return
        inspection, session, page_number = self._current_page_context()
        for priority, region in regioes_tiles_priorizadas(
            largura_pagina_pixels=preview.plano.largura_pagina_pixels,
            altura_pagina_pixels=preview.plano.altura_pagina_pixels,
            dpi_previa=preview.plano.dpi_efetivo,
            dpi_detalhe=target_dpi,
            viewport_normalizado=self.view.viewport_normalizado(),
            rotacao=self._rotation,
            orcamento=self._render_budget,
        ):
            request = self._new_request(
                inspection,
                page_number=page_number,
                region=region,
                dpi=target_dpi,
                preview=False,
            )
            self._request_raster(request, session=session, priority=priority)

    def _receber_falha_renderizacao(
        self,
        request: SolicitacaoRenderizacao,
        error: Exception,
    ) -> None:
        _require_ui_thread()
        if not self._request_is_current(request):
            return
        self._scheduled_requests.discard(request.chave_cache)
        if isinstance(error, PdfOrigemAlteradaError):
            self.limpar()
        self.status_changed.emit(str(error))

    def _request_is_current(self, request: SolicitacaoRenderizacao) -> bool:
        if self._closed or request.geracao != self._generation or not self._project_pages:
            return False
        inspection, _session, page_number = self._current_page_context()
        return (
            request.documento == _render_document_identity(inspection)
            and request.pagina == page_number
            and request.rotacao == self._rotation
            and request.zoom == _stable_scale(self.view.zoom)
            and request.device_pixel_ratio == _stable_scale(self.view.devicePixelRatioF())
        )

    def _request_needs_replacement(self, request: SolicitacaoRenderizacao) -> bool:
        if self._closed or request.geracao != self._generation or not self._project_pages:
            return False
        inspection, _session, page_number = self._current_page_context()
        return (
            request.documento == _render_document_identity(inspection)
            and request.pagina == page_number
            and request.rotacao == self._rotation
        )

    def _current_page_context(
        self,
    ) -> tuple[InspecaoPdf, SessaoLeituraPdfPort, int]:
        return self._project_pages[self._page.value() - 1]

    def _cancel_current_rendering(self) -> None:
        self._render_cancellation.cancelar()
        self._render_cancellation = CancelamentoRenderizacao()
        self._generation += 1
        self._scheduled_requests.clear()
        if hasattr(self, "_detail_timer"):
            self._detail_timer.stop()

    def _zoom_changed(self, _zoom: float) -> None:
        if not self._project_pages:
            return
        if self._current_preview is None:
            self._render_current_page()
            return
        self._cancel_current_rendering()
        self.view.limpar_tiles()
        if self._current_transformer is not None:
            self.view.definir_callouts_conformidade(
                self._compliance_callouts,
                self._current_transformer,
            )
            if self._selected_compliance_callout_id is not None:
                self.view.selecionar_callout(self._selected_compliance_callout_id)
        self._detail_timer.start()

    def _viewport_changed(self) -> None:
        if not self._project_pages:
            return
        if self._current_preview is None:
            self._render_current_page()
            return
        self._cancel_current_rendering()
        self._detail_timer.start()

    def _retire_sessions(self, sessions: tuple[SessaoLeituraPdfPort, ...]) -> None:
        if not sessions:
            return
        if self._render_queue.esta_ociosa():
            _close_sessions(sessions)
            return
        self._retired_sessions.append(sessions)

    def _liberar_sessoes_apos_renderizacao(self) -> None:
        retired, self._retired_sessions = self._retired_sessions, []
        for sessions in retired:
            _close_sessions(sessions)

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


def _render_document_identity(inspection: InspecaoPdf) -> IdentidadeDocumentoRenderizacao:
    return IdentidadeDocumentoRenderizacao(
        documento_id=inspection.documento.id,
        sha256=inspection.documento.sha256,
        tamanho_bytes=inspection.tamanho_bytes,
        modificado_em_ns=inspection.modificado_em_ns,
    )


def _stable_scale(value: float) -> float:
    return round(value, 6)


def _require_ui_thread() -> None:
    application = QApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        raise RuntimeError("QPixmap e widgets do visualizador exigem a thread da interface")


def _rgb_to_pixmap(rendered: RasterRgbRenderizado) -> QPixmap:
    _require_ui_thread()
    image = QImage(
        rendered.dados_rgb,
        rendered.largura_pixels,
        rendered.altura_pixels,
        rendered.stride,
        QImage.Format.Format_RGB888,
    )
    if image.isNull():
        raise ValueError("O buffer RGB do PDF não pôde ser convertido em imagem")
    return QPixmap.fromImage(image)


def _pixmap_size_bytes(pixmap: QPixmap) -> int:
    bytes_per_pixel = max(1, math.ceil(pixmap.depth() / 8))
    return pixmap.width() * pixmap.height() * bytes_per_pixel


def _ordered_project_pages(
    inspections: tuple[InspecaoPdf, ...],
    sessions: tuple[SessaoLeituraPdfPort, ...],
    reading_order: tuple[UUID, ...] | None,
) -> tuple[tuple[InspecaoPdf, SessaoLeituraPdfPort, int], ...]:
    page_by_id = {
        page.id: (inspection, session, page.numero)
        for inspection, session in zip(inspections, sessions, strict=True)
        for page in inspection.documento.paginas
    }
    if reading_order is None:
        return tuple(
            (inspection, session, page.numero)
            for inspection, session in zip(inspections, sessions, strict=True)
            for page in inspection.documento.paginas
        )
    if len(reading_order) != len(page_by_id) or set(reading_order) != set(page_by_id):
        raise ValueError("A ordem de leitura não corresponde às páginas dos PDFs abertos")
    return tuple(page_by_id[page_id] for page_id in reading_order)


def _open_verified_sessions(
    reader: LeitorPdfPort,
    paths: tuple[Path, ...],
    *,
    parent: QWidget,
    resolvedor: ResolvedorCredenciaisPdf,
    documents: tuple[DocumentoProjeto, ...] | None,
    sources: tuple[ReferenciaFontePdf, ...] | None,
) -> _ResultadoAberturaSessoes:
    sessions: list[SessaoLeituraPdfPort] = []
    identities: set[IdentidadeCredencialPdf] = set()
    try:
        for index, path in enumerate(paths):
            persisted = documents[index] if documents is not None else None
            source = sources[index] if sources is not None else None
            suggested_identity = (
                IdentidadeCredencialPdf.da_fonte(source) if source is not None else None
            )

            result = resolvedor.executar(
                parent=parent,
                caminho=path,
                identidade_sugerida=suggested_identity,
                acao=_session_action(reader, path, persisted),
            )
            if result.estado is not EstadoResolucaoCredencialPdf.SUCESSO:
                _close_sessions(tuple(sessions))
                if result.estado is EstadoResolucaoCredencialPdf.CANCELADA:
                    message = (
                        f"A abertura foi cancelada em {path.name} após {len(sessions)} PDF(s) "
                        "validados; a visualização anterior foi preservada"
                    )
                    return _ResultadoAberturaSessoes(
                        mensagem_interrupcao=message,
                        cancelada=True,
                    )
                message = (
                    f"O limite de 3 tentativas de senha foi atingido em {path.name}; "
                    "a visualização anterior foi preservada"
                )
                return _ResultadoAberturaSessoes(mensagem_interrupcao=message)
            session = result.valor
            assert session is not None
            sessions.append(session)
            if result.identidade is not None:
                identities.add(result.identidade)
    except BaseException:
        _close_sessions(tuple(sessions))
        raise
    return _ResultadoAberturaSessoes(
        sessoes=tuple(sessions),
        identidades=frozenset(identities),
    )


def _session_action(
    reader: LeitorPdfPort,
    path: Path,
    persisted: DocumentoProjeto | None,
) -> Callable[[str | None], SessaoLeituraPdfPort]:
    def open_session(password: str | None) -> SessaoLeituraPdfPort:
        return reader.abrir_sessao(
            path,
            senha=password,
            documento_id=persisted.id if persisted is not None else None,
            sha256_esperado=persisted.sha256 if persisted is not None else None,
        )

    return open_session


def _close_sessions(sessions: tuple[SessaoLeituraPdfPort, ...]) -> None:
    for session in sessions:
        session.fechar()


def _review_color(state: EstadoRevisao, *, alpha: int = 255) -> QColor:
    colors = {
        EstadoRevisao.PROPOSTA: (255, 193, 7),
        EstadoRevisao.CONFIRMADA: (52, 199, 89),
        EstadoRevisao.REJEITADA: (142, 142, 147),
        EstadoRevisao.CONFLITANTE: (255, 69, 58),
    }
    red, green, blue = colors[state]
    return QColor(red, green, blue, alpha)


def _criar_graficos_callout(
    callout: CalloutConformidade,
    transformer: TransformadorCoordenadasPagina,
    layer: QGraphicsRectItem,
    *,
    zoom: float,
) -> _GraficosCallout:
    color = QColor("#c62828")
    box = callout.caixa_sugerida
    top_left = transformer.normalizado_para_pixel(PontoNormalizado(box.esquerda, box.topo))
    top_right = transformer.normalizado_para_pixel(PontoNormalizado(box.direita, box.topo))
    bottom_left = transformer.normalizado_para_pixel(PontoNormalizado(box.esquerda, box.base))
    box_width = math.hypot(top_right.x - top_left.x, top_right.y - top_left.y)
    box_height = math.hypot(bottom_left.x - top_left.x, bottom_left.y - top_left.y)
    angle = math.degrees(math.atan2(top_right.y - top_left.y, top_right.x - top_left.x))
    rectangle = QGraphicsRectItem(QRectF(0, 0, box_width, box_height), layer)
    pen = QPen(color, 2)
    pen.setCosmetic(True)
    rectangle.setPen(pen)
    rectangle.setBrush(QBrush(QColor("white")))
    rectangle.setData(0, str(callout.id))
    rectangle.setData(2, "compliance_callout")
    rectangle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    rectangle.setCursor(Qt.CursorShape.PointingHandCursor)
    rectangle.setPos(top_left.x, top_left.y)
    rectangle.setRotation(angle)
    rectangle.setZValue(1)
    text_item = QGraphicsTextItem(layer)
    text_item.setDefaultTextColor(color)
    text_item.document().setDocumentMargin(0)
    points_width = float(box.largura) * float(transformer.pagina.largura_pontos)
    pixels_per_point = box_width / points_width
    padding = max(2.0, 6.0 * pixels_per_point)
    available_width = max(1.0, box_width - 2 * padding)
    available_height = max(1.0, box_height - 2 * padding)
    minimum_scene_pixels = max(1, math.ceil(7.0 / zoom))
    for font_points in (10.5, 10.0, 9.5, 9.0):
        font = _fonte_callout(max(minimum_scene_pixels, round(font_points * pixels_per_point)))
        text_item.setFont(font)
        text_item.setPlainText(callout.texto)
        text_item.setTextWidth(available_width)
        if text_item.boundingRect().height() <= available_height:
            break
    radians = math.radians(angle)
    text_item.setPos(
        top_left.x + math.cos(radians) * padding - math.sin(radians) * padding,
        top_left.y + math.sin(radians) * padding + math.cos(radians) * padding,
    )
    text_item.setRotation(angle)
    text_item.setData(0, str(callout.id))
    text_item.setData(2, "compliance_callout")
    text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    text_item.setCursor(Qt.CursorShape.PointingHandCursor)
    text_item.setZValue(2)
    tooltip = callout.texto.replace("\n", " ")
    rectangle.setToolTip(tooltip)
    text_item.setToolTip(tooltip)
    scene_bounds = layer.rect()
    arrow_pen = QPen(color, 2)
    arrow_pen.setCosmetic(True)
    lines: list[QGraphicsPathItem] = []
    for anchor in callout.ancoras:
        connection = ponto_conexao_callout(box, anchor.ponto)
        start = transformer.normalizado_para_pixel(connection)
        end = transformer.normalizado_para_pixel(anchor.ponto)
        path = _caminho_seta_aberta(start, end, pixels_per_point, scene_bounds)
        line = CalloutLinkItem(path, layer)
        line.setPen(arrow_pen)
        line.setData(0, str(callout.id))
        line.setData(2, "compliance_callout")
        line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        line.setCursor(Qt.CursorShape.PointingHandCursor)
        line.setToolTip(tooltip)
        lines.append(line)
    return _GraficosCallout(rectangle, text_item, tuple(lines))


def _caminho_seta_aberta(
    start: PontoPlano,
    end: PontoPlano,
    pixels_per_point: float,
    page_bounds: QRectF,
) -> QPainterPath:
    path = QPainterPath(QPointF(start.x, start.y))
    path.lineTo(end.x, end.y)
    backward_x = start.x - end.x
    backward_y = start.y - end.y
    length = math.hypot(backward_x, backward_y)
    if length <= 1e-9:
        return path
    backward_x /= length
    backward_y /= length
    wing_length = max(5.0, 8.0 * pixels_per_point)
    angle = math.radians(28)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    for direction in (-1.0, 1.0):
        wing_x = end.x + wing_length * (backward_x * cosine - direction * backward_y * sine)
        wing_y = end.y + wing_length * (direction * backward_x * sine + backward_y * cosine)
        wing = _conter_ponto_pagina(wing_x, wing_y, page_bounds)
        path.moveTo(end.x, end.y)
        path.lineTo(wing)
    return path


def _conter_ponto_pagina(x: float, y: float, bounds: QRectF) -> QPointF:
    return QPointF(
        min(bounds.right(), max(bounds.left(), x)),
        min(bounds.bottom(), max(bounds.top(), y)),
    )


def _fonte_callout(pixel_size: int) -> QFont:
    global _FONTE_CALLOUT_REGISTRO_TENTADO

    family = "Arial"
    font = QFont(family)
    font.setPixelSize(pixel_size)
    if QFontInfo(font).exactMatch() or _FONTE_CALLOUT_REGISTRO_TENTADO:
        return font
    _FONTE_CALLOUT_REGISTRO_TENTADO = True
    windows_directory = os.environ.get("WINDIR", r"C:\Windows")
    font_path = Path(windows_directory) / "Fonts" / "arial.ttf"
    if font_path.is_file():
        QFontDatabase.addApplicationFont(str(font_path))
        font = QFont(family)
        font.setPixelSize(pixel_size)
    return font


def _align_persisted_document(
    inspection: InspecaoPdf,
    persisted: DocumentoProjeto,
) -> InspecaoPdf:
    if inspection.documento.sha256 != persisted.sha256:
        raise ValueError(f"O conteúdo de {persisted.nome_arquivo} foi alterado desde a importação")
    if len(inspection.paginas) != len(persisted.paginas):
        raise ValueError(f"A paginação de {persisted.nome_arquivo} não corresponde ao projeto")
    return replace(
        inspection,
        documento=persisted,
        paginas=tuple(
            replace(inventory, pagina=page)
            for inventory, page in zip(inspection.paginas, persisted.paginas, strict=True)
        ),
    )


def _review_link_pen(state: EstadoRevisao, *, selected: bool = False) -> QPen:
    pen = QPen(QColor("#0078d4") if selected else _review_color(state), 5 if selected else 3)
    pen.setCosmetic(True)
    if state is EstadoRevisao.REJEITADA:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _review_link_path(
    geometry: GeometriaDocumento,
    transformer: TransformadorCoordenadasPagina,
) -> QPainterPath:
    pixels = tuple(transformer.normalizado_para_pixel(point) for point in geometry.pontos)
    if geometry.tipo is TipoGeometria.POLIGONO and len(pixels) == 4:
        return _polygon_review_link_path(pixels)
    left = min(point.x for point in pixels)
    right = max(point.x for point in pixels)
    bottom = max(point.y for point in pixels)
    minimum_width = 24.0
    if right - left < minimum_width:
        center = (left + right) / 2
        left = max(0.0, center - minimum_width / 2)
        right = min(float(transformer.largura_pixels), center + minimum_width / 2)
    baseline = min(float(transformer.altura_pixels) - 2, bottom + 5)
    path = QPainterPath()
    path.moveTo(left, baseline)
    path.lineTo(right, baseline)
    path.moveTo(left, baseline - 4)
    path.lineTo(left, baseline)
    path.moveTo(right, baseline - 4)
    path.lineTo(right, baseline)
    return path


def _polygon_review_link_path(points: tuple[PontoPlano, ...]) -> QPainterPath:
    top_center = PontoPlano(
        (points[0].x + points[1].x) / 2,
        (points[0].y + points[1].y) / 2,
    )
    bottom_center = PontoPlano(
        (points[2].x + points[3].x) / 2,
        (points[2].y + points[3].y) / 2,
    )
    outward_x = bottom_center.x - top_center.x
    outward_y = bottom_center.y - top_center.y
    outward_length = math.hypot(outward_x, outward_y)
    if outward_length <= 1e-9:
        outward_x, outward_y = 0.0, 1.0
    else:
        outward_x /= outward_length
        outward_y /= outward_length

    start = PontoPlano(points[3].x + outward_x * 4, points[3].y + outward_y * 4)
    end = PontoPlano(points[2].x + outward_x * 4, points[2].y + outward_y * 4)

    path = QPainterPath(QPointF(start.x, start.y))
    path.lineTo(end.x, end.y)
    path.moveTo(start.x - outward_x * 4, start.y - outward_y * 4)
    path.lineTo(start.x, start.y)
    path.moveTo(end.x - outward_x * 4, end.y - outward_y * 4)
    path.lineTo(end.x, end.y)
    return path
