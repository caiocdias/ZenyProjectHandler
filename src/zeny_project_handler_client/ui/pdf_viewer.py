"""Visualizador cliente desacoplado do mecanismo concreto de leitura."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID, uuid4

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
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
)

from zeny_project_handler_client.config import DEFAULT_PDF_TILE_CACHE_MAX_BYTES
from zeny_project_handler_client.contract_values import decimal_string
from zeny_project_handler_client.logging_config import OperationLogger, operation_logger
from zeny_project_handler_client.presentation import NormalizedPoint, PresentationGeometry
from zeny_project_handler_contracts.base import DocumentId, PageId
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
)
from zeny_project_handler_contracts.compliance import ComplianceCalloutDto
from zeny_project_handler_contracts.enums import ComplianceStatus, ReviewGeometryKind, ReviewState
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.exports import CalloutPositionOverrideDto
from zeny_project_handler_contracts.review import ReviewGeometryDto, ReviewOverlayDto
from zeny_project_handler_contracts.viewer import (
    CreateViewerSessionResponse,
    ViewerDocumentDto,
    ViewerPageDto,
)

from .pdf_gateway import PdfViewerGateway, ViewerGatewayError
from .pdf_rendering import (
    CacheLruBytes,
    CancelamentoRenderizacao,
    ChaveCacheRenderizacao,
    FilaRenderizacao,
    IdentidadeDocumentoRenderizacao,
    PlanoRasterRemoto,
    RasterPngRenderizado,
    ResultadoRenderizacao,
    SolicitacaoRenderizacao,
    TrabalhoRenderizacao,
    regioes_tiles_priorizadas,
)

_FONTE_CALLOUT_REGISTRO_TENTADO = False


@dataclass(frozen=True, slots=True)
class PontoPlano:
    x: float
    y: float


class _NormalizedPointLike(Protocol):
    @property
    def x(self) -> Decimal: ...

    @property
    def y(self) -> Decimal: ...


class TransformadorViewport:
    """Converta somente coordenadas normalizadas do contrato para o raster remoto."""

    def __init__(self, page: ViewerPageDto, plan: PlanoRasterRemoto) -> None:
        self.pagina = page
        self.dpi = plan.dpi_efetivo
        self.rotacao_adicional_graus = plan.rotacao_adicional_graus
        self.largura_pixels = plan.largura_pixels
        self.altura_pixels = plan.altura_pixels
        self.largura_pagina_pixels = plan.largura_pagina_pixels
        self.altura_pagina_pixels = plan.altura_pagina_pixels
        self.origem_x_pixels = plan.origem_x_pixels
        self.origem_y_pixels = plan.origem_y_pixels

    def normalizado_para_pixel(self, point: _NormalizedPointLike) -> PontoPlano:
        x, y = _rotate_normalized(float(point.x), float(point.y), self.rotacao_adicional_graus)
        return PontoPlano(
            x * self.largura_pagina_pixels - self.origem_x_pixels,
            y * self.altura_pagina_pixels - self.origem_y_pixels,
        )

    def pixel_para_normalizado(self, point: PontoPlano) -> NormalizedPoint:
        x = (point.x + self.origem_x_pixels) / self.largura_pagina_pixels
        y = (point.y + self.origem_y_pixels) / self.altura_pagina_pixels
        x, y = _unrotate_normalized(x, y, self.rotacao_adicional_graus)
        return NormalizedPoint(Decimal(str(x)), Decimal(str(y)))


@dataclass(frozen=True, slots=True)
class _RasterEmCache:
    pixmap: QPixmap
    plano: PlanoRasterRemoto


@dataclass(frozen=True, slots=True)
class _PaginaProjetoRemota:
    documento: ViewerDocumentDto
    pagina: ViewerPageDto
    pagina_remota_id: UUID


@dataclass(frozen=True, slots=True)
class _GraficosCallout:
    caixa: CalloutBoxItem
    texto: QGraphicsTextItem
    linhas: tuple[QGraphicsPathItem, ...]
    resultado: ComplianceStatus


class ReviewLinkItem(QGraphicsPathItem):
    """Sublinhado com área de clique confortável, mesmo em zoom reduzido."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())


class CalloutLinkItem(QGraphicsPathItem):
    """Seta de callout com seleção restrita ao traço visível."""

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(14)
        return stroker.createStroke(self.path())

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - API Qt
        if not self.shape().contains(event.pos()):
            event.ignore()
            return
        super().mousePressEvent(event)

    def paint(
        self,
        painter: QPainter,
        _option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        # QGraphicsPathItem desenha por padrão um retângulo pontilhado em torno de
        # todo o boundingRect quando selecionado. Em setas diagonais longas esse
        # retângulo parece (e se comporta visualmente) como uma grande sobreposição.
        # O realce do callout já é aplicado no próprio traço pela caneta selecionada.
        painter.save()
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawPath(self.path())
        painter.restore()


class CalloutBoxItem(QGraphicsRectItem):
    """Caixa arrastável, contida na página e com atualização vetorial ao mover."""

    def __init__(self, rectangle: QRectF, parent: QGraphicsItem) -> None:
        super().__init__(rectangle, parent)
        self._drag_bounds = QRectF()
        self._position_changed: Callable[[], None] | None = None
        self._drag_finished: Callable[[], None] | None = None

    def habilitar_arraste(
        self,
        *,
        limites: QRectF,
        posicao_alterada: Callable[[], None],
        arraste_concluido: Callable[[], None],
    ) -> None:
        self._drag_bounds = QRectF(limites)
        self._position_changed = posicao_alterada
        self._drag_finished = arraste_concluido
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def itemChange(  # noqa: N802 - API Qt
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: object,
    ) -> object:
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self._position_changed is not None
            and isinstance(value, QPointF)
        ):
            value = self._posicao_contida(value)
        result = super().itemChange(change, value)
        if (
            change is QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and self._position_changed is not None
        ):
            self._position_changed()
        return result

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - API Qt
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:  # noqa: N802 - API Qt
        super().mouseReleaseEvent(event)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self._drag_finished is not None:
            self._drag_finished()

    def _posicao_contida(self, proposed: QPointF) -> QPointF:
        current_bounds = self.mapRectToParent(self.rect())
        delta = proposed - self.pos()
        desired = current_bounds.translated(delta)
        correction_x = 0.0
        correction_y = 0.0
        if desired.left() < self._drag_bounds.left():
            correction_x = self._drag_bounds.left() - desired.left()
        elif desired.right() > self._drag_bounds.right():
            correction_x = self._drag_bounds.right() - desired.right()
        if desired.top() < self._drag_bounds.top():
            correction_y = self._drag_bounds.top() - desired.top()
        elif desired.bottom() > self._drag_bounds.bottom():
            correction_y = self._drag_bounds.bottom() - desired.bottom()
        return proposed + QPointF(correction_x, correction_y)


class PdfGraphicsView(QGraphicsView):
    """Cena raster com zoom suave e sobreposições em coordenadas normalizadas."""

    proposta_selecionada = Signal(str)
    callout_selecionado = Signal(str)
    callout_movido = Signal(str, object)
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
        self._review_geometries: dict[str, PresentationGeometry] = {}
        self._review_transformer: TransformadorViewport | None = None
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
        plano: PlanoRasterRemoto,
        plano_previa: PlanoRasterRemoto,
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
        geometries: tuple[tuple[NormalizedPoint, ...], ...],
        transformer: TransformadorViewport,
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
        callouts: tuple[ComplianceCalloutDto, ...],
        transformer: TransformadorViewport,
    ) -> None:
        """Reconstrua a camada vetorial de callouts sem tocar no raster ou nos links."""
        self._remover_camada_callouts()
        if self._pixmap_item is None:
            return
        layer = QGraphicsRectItem(self._scene.sceneRect())
        layer.setPen(QPen(Qt.PenStyle.NoPen))
        layer.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        layer.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        layer.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        layer.setZValue(30)
        self._scene.addItem(layer)
        self._callout_layer = layer
        for callout in callouts:
            if callout.navigation.page_id.root != transformer.pagina.page_id.root:
                continue
            self._callout_items[str(callout.callout_id.root)] = _criar_graficos_callout(
                callout,
                transformer,
                layer,
                zoom=self._zoom,
                callout_movido=lambda callout_id, box: self.callout_movido.emit(
                    callout_id,
                    box,
                ),
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
        proposals: tuple[ReviewOverlayDto, ...],
        transformer: TransformadorViewport,
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
            key = str(proposal.proposal_id.root)
            geometry = _review_geometry_to_presentation(proposal.geometry)
            link_geometry = _review_geometry_to_presentation(proposal.link_geometry)
            item = ReviewLinkItem(
                _review_link_path(link_geometry, transformer),
            )
            item.setPen(_review_link_pen(proposal.review_state))
            self._scene.addItem(item)
            item.setZValue(20)
            item.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.setToolTip(
                f"Abrir {proposal.category.value} na revisão · "
                f"{proposal.situation_label} · "
                f"{proposal.review_state.value} · "
                f"confiança {proposal.confidence if proposal.confidence is not None else '-'}"
            )
            item.setData(0, key)
            item.setData(1, proposal.review_state.value)
            item.setData(2, "review_proposal")
            self._review_items[key] = item
            self._review_geometries[key] = geometry

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

    def geometria_proposta(self, proposal_id: str) -> PresentationGeometry | None:
        item = self._review_items.get(proposal_id)
        geometry = self._review_geometries.get(proposal_id)
        transformer = self._review_transformer
        if item is None or geometry is None or transformer is None:
            return None
        normalized_points: list[NormalizedPoint] = []
        for normalized in geometry.points:
            pixel = transformer.normalizado_para_pixel(normalized)
            moved = item.mapToScene(QPointF(pixel.x, pixel.y))
            normalized_points.append(
                transformer.pixel_para_normalizado(PontoPlano(moved.x(), moved.y()))
            )
        return PresentationGeometry(
            page_id=geometry.page_id,
            kind=geometry.kind,
            points=tuple(normalized_points),
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
                    ReviewState(str(item.data(1))),
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
            color, background = _cores_callout(graphics.resultado, selecionado=selected)
            pen = QPen(color, 3.2 if selected else 2.0)
            pen.setCosmetic(True)
            graphics.caixa.setPen(pen)
            graphics.caixa.setBrush(QBrush(background))
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
        gateway: PdfViewerGateway,
        dpi: int,
        limite_pixels_tile: int,
        cache_limite_bytes: int = DEFAULT_PDF_TILE_CACHE_MAX_BYTES,
        limpar_credenciais_efemeras: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pdfViewerWidget")
        self._gateway = gateway
        self._limpar_credenciais_efemeras = limpar_credenciais_efemeras or (lambda: None)
        self._dpi = dpi
        self._tile_max_pixels = limite_pixels_tile
        self._render_cache: CacheLruBytes[ChaveCacheRenderizacao, _RasterEmCache] = CacheLruBytes(
            cache_limite_bytes
        )
        self._render_queue = FilaRenderizacao()
        self._generation = 0
        self._render_cancellation = CancelamentoRenderizacao()
        self._scheduled_requests: set[ChaveCacheRenderizacao] = set()
        self._viewer_session_id: UUID | None = None
        self._retired_session_ids: list[UUID] = []
        self._current_preview: _RasterEmCache | None = None
        self._closed = False
        self._inspection: ViewerDocumentDto | None = None
        self._inspections: tuple[ViewerDocumentDto, ...] = ()
        self._project_pages: tuple[_PaginaProjetoRemota, ...] = ()
        self._rotation = 0
        self._overlays: tuple[tuple[NormalizedPoint, ...], ...] = ()
        self._review_proposals: tuple[ReviewOverlayDto, ...] = ()
        self._review_link_geometries: dict[str, PresentationGeometry] = {}
        self._compliance_callouts: tuple[ComplianceCalloutDto, ...] = ()
        self._callout_position_overrides: dict[str, NormalizedBoxDto] = {}
        self._selected_compliance_callout_id: str | None = None
        self._current_transformer: TransformadorViewport | None = None
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
    def inspecao(self) -> ViewerDocumentDto | None:
        return self._inspection

    @property
    def inspecoes(self) -> tuple[ViewerDocumentDto, ...]:
        """Documentos abertos, na ordem das folhas do projeto."""
        return self._inspections

    @property
    def folha_atual(self) -> int:
        return self._page.value()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        toolbar = QHBoxLayout()
        open_button = QPushButton("Abrir PDF(s)")
        open_button.setObjectName("openPdfButton")
        open_button.setProperty("role", "primary")
        open_button.setToolTip("Abrir um ou mais PDFs somente para visualização")
        open_button.clicked.connect(self.selecionar_pdf)
        toolbar.addWidget(open_button)

        previous_button = QPushButton("Anterior")
        previous_button.setObjectName("pdfPreviousPageButton")
        previous_button.setToolTip("Ir para a folha anterior")
        previous_button.clicked.connect(lambda: self._change_page(-1))
        toolbar.addWidget(previous_button)
        self._page = QSpinBox()
        self._page.setObjectName("pdfPageSpinBox")
        self._page.setRange(1, 1)
        self._page.setEnabled(False)
        self._page.valueChanged.connect(self._render_current_page)
        toolbar.addWidget(self._page)
        next_button = QPushButton("Próxima")
        next_button.setObjectName("pdfNextPageButton")
        next_button.setToolTip("Ir para a próxima folha")
        next_button.clicked.connect(lambda: self._change_page(1))
        toolbar.addWidget(next_button)

        zoom_out = QPushButton("-")
        zoom_out.setObjectName("pdfZoomOutButton")
        zoom_out.setToolTip("Reduzir zoom")
        zoom_out.clicked.connect(self._zoom_out)
        toolbar.addWidget(zoom_out)
        zoom_in = QPushButton("+")
        zoom_in.setObjectName("pdfZoomInButton")
        zoom_in.setToolTip("Ampliar zoom")
        zoom_in.clicked.connect(self._zoom_in)
        toolbar.addWidget(zoom_in)
        fit_button = QPushButton("Ajustar")
        fit_button.setObjectName("pdfFitPageButton")
        fit_button.setToolTip("Ajustar a folha à área disponível")
        fit_button.clicked.connect(self._fit_page)
        toolbar.addWidget(fit_button)
        rotate_button = QPushButton("Girar 90°")
        rotate_button.setObjectName("pdfRotateButton")
        rotate_button.setToolTip("Girar a visualização sem modificar o PDF")
        rotate_button.clicked.connect(self._rotate_page)
        toolbar.addWidget(rotate_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self._metadata = QLabel("Nenhum PDF aberto")
        self._metadata.setObjectName("pdfMetadataLabel")
        self._metadata.setProperty("role", "hint")
        self._metadata.setWordWrap(True)
        layout.addWidget(self._metadata)
        self.view = PdfGraphicsView()
        self.view.proposta_selecionada.connect(self.proposal_selected)
        self.view.callout_selecionado.connect(self._callout_selected)
        self.view.callout_movido.connect(self._callout_moved)
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
        return self.carregar_projeto((path,), senha_inicial=password)

    def limpar(self) -> None:
        self._cancel_current_rendering()
        self._render_cache.limpar()
        self._current_preview = None
        if self._viewer_session_id is not None:
            self._retire_session(self._viewer_session_id)
            self._viewer_session_id = None
        self._inspection = None
        self._inspections = ()
        self._project_pages = ()
        self._overlays = ()
        self._review_proposals = ()
        self._review_link_geometries = {}
        self._compliance_callouts = ()
        self._callout_position_overrides.clear()
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
        self._limpar_credenciais_efemeras()

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
            session_ids = tuple(self._retired_session_ids)
            if self._viewer_session_id is not None:
                session_ids = (self._viewer_session_id, *session_ids)
            self._viewer_session_id = None
            self._retired_session_ids.clear()
            _close_remote_sessions(self._gateway, session_ids)
            self._render_cache.limpar()
            self._limpar_credenciais_efemeras()

    def ir_para_folha(self, numero: int) -> None:
        if not self._project_pages:
            return
        self._page.setValue(min(max(1, numero), len(self._project_pages)))

    def carregar_projeto(
        self,
        paths: tuple[Path, ...],
        *,
        documentos: tuple[object, ...] | None = None,
        fontes: tuple[object, ...] | None = None,
        ordem_paginas: tuple[UUID, ...] | None = None,
        senha_inicial: str | None = None,
        senhas_iniciais: tuple[str | None, ...] | None = None,
    ) -> bool:
        """Envie PDFs ao servidor antes de substituir o projeto atualmente exibido."""
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
                    senha_inicial=senha_inicial,
                    senhas_iniciais=senhas_iniciais,
                    observation=observation,
                )
            except Exception as error:
                observation.failed(error, expected=False)
                raise

    def _load_project(
        self,
        paths: tuple[Path, ...],
        *,
        documentos: tuple[object, ...] | None,
        fontes: tuple[object, ...] | None,
        ordem_paginas: tuple[UUID, ...] | None,
        senha_inicial: str | None,
        senhas_iniciais: tuple[str | None, ...] | None,
        observation: OperationLogger,
    ) -> bool:
        canonical_paths = tuple(str(path.resolve()).casefold() for path in paths)
        if len(set(canonical_paths)) != len(canonical_paths):
            duplicate_error = ValueError("A seleção contém um PDF duplicado")
            observation.failed(duplicate_error, expected=True)
            self._open_warning(str(duplicate_error))
            return False
        missing = next((path for path in paths if not path.is_file()), None)
        if missing is not None:
            missing_error = FileNotFoundError(f"O PDF selecionado não existe: {missing.name}")
            observation.failed(missing_error, expected=True)
            self._open_warning(str(missing_error))
            return False
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
            created = self._gateway.create_session(
                paths,
                idempotency_key=f"viewer-{uuid4()}",
            )
            response = self._unlock_pending_uploads(
                created,
                senha_inicial=senha_inicial,
                senhas_iniciais=senhas_iniciais,
            )
        except ViewerGatewayError as error:
            observation.failed(error, expected=True)
            self.status_changed.emit(str(error))
            QMessageBox.warning(self, "Não foi possível abrir o PDF", str(error))
            return False
        except OSError as error:
            observation.failed(error, expected=True)
            self._open_warning("Não foi possível ler o PDF selecionado para envio ao servidor")
            return False
        if response is None:
            observation.cancelled()
            return False
        try:
            inspections, project_pages = _temporary_project_model(
                response.documents,
                persisted_documents=documentos,
                reading_order=ordem_paginas,
            )
        except ValueError as error:
            self._gateway.close_session(response.viewer_session_id.root)
            observation.failed(error, expected=True)
            self._open_warning(str(error))
            return False
        self._activate_project(
            inspections,
            project_pages=project_pages,
            viewer_session_id=response.viewer_session_id.root,
        )
        observation.succeeded(
            item_count=len(inspections),
            document_ids=tuple(item.document_id.root for item in inspections),
        )
        return True

    def carregar_projeto_remoto(self, project_id: UUID) -> bool:
        """Abra metadados e páginas gerenciadas sem receber qualquer caminho do cliente."""
        observation = operation_logger("pdf.viewer.open")
        with observation.context():
            observation.started(project_id=str(project_id))
            try:
                response = self._gateway.get_project(project_id)
            except ViewerGatewayError as error:
                observation.failed(error, expected=True)
                self._open_warning(str(error))
                return False
            pages = tuple(
                _PaginaProjetoRemota(
                    documento=next(
                        item for item in response.documents if item.document_id == page.document_id
                    ),
                    pagina=page,
                    pagina_remota_id=page.page_id.root,
                )
                for page in response.pages
            )
            self._activate_project(
                response.documents,
                project_pages=pages,
                viewer_session_id=None,
            )
            observation.succeeded(
                project_id=str(project_id),
                item_count=len(response.documents),
                document_ids=tuple(item.document_id.root for item in response.documents),
            )
            return True

    def _unlock_pending_uploads(
        self,
        response: CreateViewerSessionResponse,
        *,
        senha_inicial: str | None,
        senhas_iniciais: tuple[str | None, ...] | None,
    ) -> CreateViewerSessionResponse | None:
        current = response
        fallback_initial = senha_inicial
        initial_by_position = senhas_iniciais or ()
        attempted_positions: set[int] = set()
        while current.pending_uploads:
            pending = current.pending_uploads[0]
            password = None
            if pending.position not in attempted_positions:
                attempted_positions.add(pending.position)
                if pending.position < len(initial_by_position):
                    password = initial_by_position[pending.position]
            if password is None and fallback_initial is not None:
                password = fallback_initial
                fallback_initial = None
            if password is None:
                password, accepted = QInputDialog.getText(
                    self,
                    "Senha do PDF",
                    f"{pending.display_name}\nInforme a senha para continuar.",
                    QLineEdit.EchoMode.Password,
                )
                if not accepted:
                    self._gateway.close_session(current.viewer_session_id.root)
                    self.status_changed.emit("A abertura do PDF protegido foi cancelada")
                    return None
            try:
                unlocked = self._gateway.unlock_session_pdf(
                    current.viewer_session_id.root,
                    pending.upload_id.root,
                    password,
                )
            except ViewerGatewayError as error:
                if error.code is ErrorCode.PDF_PASSWORD_INVALID:
                    raw_remaining = (error.details or {}).get("password_attempts_remaining", 0)
                    remaining = int(raw_remaining) if isinstance(raw_remaining, (int, str)) else 0
                    if remaining > 0:
                        continue
                self._gateway.close_session(current.viewer_session_id.root)
                raise
            current = CreateViewerSessionResponse(
                viewer_session_id=unlocked.viewer_session_id,
                documents=unlocked.documents,
                pending_uploads=unlocked.pending_uploads,
                expires_at=unlocked.expires_at,
            )
        return current

    def _open_warning(self, message: str) -> None:
        self.status_changed.emit(message)
        QMessageBox.warning(self, "Não foi possível abrir os arquivos", message)

    def _activate_project(
        self,
        inspections: tuple[ViewerDocumentDto, ...],
        *,
        project_pages: tuple[_PaginaProjetoRemota, ...],
        viewer_session_id: UUID | None,
    ) -> None:
        previous_session_id = self._viewer_session_id
        self._cancel_current_rendering()
        self._render_cache.limpar()
        self._current_preview = None
        self.view.limpar()
        self._inspections = inspections
        self._viewer_session_id = viewer_session_id
        self._overlays = ()
        self._review_proposals = ()
        self._review_link_geometries = {}
        self._compliance_callouts = ()
        self._callout_position_overrides.clear()
        self._selected_compliance_callout_id = None
        self._last_page_id = None
        self._project_pages = project_pages
        self._inspection = inspections[0] if inspections else None
        self._rotation = 0
        self.view.limpar_selecao_callout()
        self._page.blockSignals(True)
        self._page.setRange(1, max(1, len(self._project_pages)))
        self._page.setValue(1)
        self._page.setEnabled(bool(self._project_pages))
        self._page.blockSignals(False)
        if previous_session_id is not None:
            self._retire_session(previous_session_id)
        if project_pages:
            self._render_current_page()

    def definir_sobreposicoes(self, geometries: tuple[tuple[NormalizedPoint, ...], ...]) -> None:
        self._overlays = geometries
        if self._current_transformer is not None:
            self.view.definir_sobreposicoes(geometries, self._current_transformer)

    def definir_sobreposicoes_revisao(
        self,
        geometries: tuple[ReviewGeometryDto, ...],
    ) -> None:
        """Converta DTOs normalizados somente para o desenho vetorial local."""
        self.definir_sobreposicoes(
            tuple(_review_geometry_to_presentation(item).points for item in geometries)
        )

    def definir_propostas_revisao(
        self,
        proposals: tuple[ReviewOverlayDto, ...],
    ) -> None:
        self._review_proposals = proposals
        if self._current_transformer is not None:
            self.view.definir_propostas_revisao(
                proposals,
                self._current_transformer,
            )

    def definir_callouts_conformidade(
        self,
        callouts: tuple[ComplianceCalloutDto, ...],
    ) -> None:
        positioned = tuple(
            item.model_copy(
                update={
                    "box": self._callout_position_overrides.get(
                        str(item.callout_id.root),
                        item.box,
                    )
                }
            )
            for item in callouts
        )
        self._compliance_callouts = positioned
        visible_ids = {str(item.callout_id.root) for item in callouts}
        if self._selected_compliance_callout_id not in visible_ids:
            self._selected_compliance_callout_id = None
            self.view.limpar_selecao_callout()
        if self._current_transformer is not None:
            self.view.definir_callouts_conformidade(positioned, self._current_transformer)
            if self._selected_compliance_callout_id is not None:
                self.view.selecionar_callout(self._selected_compliance_callout_id)

    def posicoes_callouts_conformidade(self) -> tuple[CalloutPositionOverrideDto, ...]:
        """Entregue ao exportador as posições ajustadas na sessão visual atual."""
        return tuple(
            CalloutPositionOverrideDto(callout_id=item.callout_id, box=item.box)
            for item in self._compliance_callouts
        )

    def selecionar_callout(self, callout_id: str) -> None:
        if all(str(item.callout_id.root) != callout_id for item in self._compliance_callouts):
            return
        self._selected_compliance_callout_id = callout_id
        self.view.selecionar_callout(callout_id)

    def _callout_selected(self, callout_id: str) -> None:
        self._selected_compliance_callout_id = callout_id
        self.compliance_callout_selected.emit(callout_id)

    def _callout_moved(self, callout_id: str, box: object) -> None:
        if not isinstance(box, NormalizedBoxDto):
            return
        if all(str(item.callout_id.root) != callout_id for item in self._compliance_callouts):
            return
        self._callout_position_overrides[callout_id] = box
        self._compliance_callouts = tuple(
            item.model_copy(update={"box": box})
            if str(item.callout_id.root) == callout_id
            else item
            for item in self._compliance_callouts
        )

    def definir_destaque_navegacao(self, navigation: EvidenceNavigationDto) -> None:
        geometry = navigation.geometry
        if geometry is None:
            self.definir_sobreposicoes(())
            return
        left = Decimal(geometry.x)
        top = Decimal(geometry.y)
        right = left + Decimal(geometry.width)
        bottom = top + Decimal(geometry.height)
        if right <= left or bottom <= top:
            self.definir_sobreposicoes(((NormalizedPoint(left, top),),))
            return
        self.definir_sobreposicoes(
            (
                (
                    NormalizedPoint(left, top),
                    NormalizedPoint(right, top),
                    NormalizedPoint(right, bottom),
                    NormalizedPoint(left, bottom),
                ),
            )
        )

    def selecionar_proposta(self, proposal_id: str) -> None:
        self.view.selecionar_proposta(proposal_id)

    def geometria_proposta(self, proposal_id: str) -> ReviewGeometryDto | None:
        geometry = self.view.geometria_proposta(proposal_id)
        return _review_geometry_from_presentation(geometry) if geometry is not None else None

    def _render_current_page(self) -> None:
        if not self._project_pages:
            return
        project_page_number = self._page.value()
        context = self._project_pages[project_page_number - 1]
        document = context.documento
        page = context.pagina
        self._inspection = document
        self._cancel_current_rendering()
        self._current_preview = None
        self._current_transformer = None
        self.view.limpar()
        self._update_metadata(document)
        page_id = str(page.page_id.root)
        if page_id != self._last_page_id:
            self._last_page_id = page_id
            self.page_changed.emit(page_id)
        request = self._new_request(
            document,
            page=page,
            region=(0.0, 0.0, 1.0, 1.0),
            dpi=self._dpi,
            preview=True,
        )
        self._request_raster(
            request,
            page_id=context.pagina_remota_id,
            priority=-2_000_000,
        )

    def _new_request(
        self,
        document: ViewerDocumentDto,
        *,
        page: ViewerPageDto,
        region: tuple[float, float, float, float],
        dpi: int,
        preview: bool,
    ) -> SolicitacaoRenderizacao:
        return SolicitacaoRenderizacao(
            geracao=self._generation,
            documento=_render_document_identity(document),
            pagina=page.source_page_number,
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
        page_id: UUID,
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
                pagina_id=page_id,
                gateway=self._gateway,
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
        rendered: RasterPngRenderizado,
    ) -> None:
        _require_ui_thread()
        if not self._request_is_current(request):
            if request.previa and self._request_needs_replacement(request):
                self._render_current_page()
            return
        self._scheduled_requests.discard(request.chave_cache)
        if (
            rendered.pagina_id != self._current_page_context().pagina_remota_id
            or rendered.rotacao_adicional_graus != request.rotacao
            or rendered.plano.dpi_solicitado != request.dpi
            or (
                (request.previa and not rendered.plano.pagina_inteira)
                or (
                    not request.previa
                    and not _same_region(rendered.plano.recorte_normalizado, request.regiao)
                )
            )
        ):
            self.status_changed.emit("O backend devolveu uma região PDF incompatível")
            return
        raster = _RasterEmCache(
            pixmap=_png_to_pixmap(rendered),
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
        context = self._current_page_context()
        document = context.documento
        page = context.pagina
        self._current_preview = raster
        signals_blocked = self.view.blockSignals(True)
        try:
            self.view.definir_previa(raster.pixmap)
        finally:
            self.view.blockSignals(signals_blocked)
        transformer = TransformadorViewport(page, raster.plano)
        self._current_transformer = transformer
        self.view.definir_sobreposicoes(self._overlays, transformer)
        self.view.definir_propostas_revisao(
            self._review_proposals,
            transformer,
        )
        self.view.definir_callouts_conformidade(self._compliance_callouts, transformer)
        if self._selected_compliance_callout_id is not None:
            self.view.selecionar_callout(self._selected_compliance_callout_id)
        project_page_number = self._page.value()
        self.status_changed.emit(
            f"Folha {project_page_number}/{len(self._project_pages)} - "
            f"página {page.source_page_number}/{document.page_count} de "
            f"{document.display_name} - "
            f"{raster.plano.largura_pixels}x{raster.plano.altura_pixels}px - "
            f"{raster.plano.dpi_efetivo}/{raster.plano.dpi_solicitado} DPI"
        )
        self._cancel_current_rendering()
        self._detail_timer.start()

    def _update_metadata(self, document: ViewerDocumentDto) -> None:
        if len(self._inspections) == 1:
            self._metadata.setText(
                f"{document.display_name}  |  "
                f"{document.page_count} página(s)  |  "
                f"SHA-256 {document.sha256[:12]}…"
            )
        else:
            document_position = self._inspections.index(document) + 1
            self._metadata.setText(
                f"Projeto: {len(self._inspections)} PDFs, "
                f"{len(self._project_pages)} folhas  |  "
                f"Arquivo {document_position}: {document.display_name}"
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
        context = self._current_page_context()
        document = context.documento
        page = context.pagina
        for priority, region in regioes_tiles_priorizadas(
            largura_pagina_pixels=preview.plano.largura_pagina_pixels,
            altura_pagina_pixels=preview.plano.altura_pagina_pixels,
            dpi_previa=preview.plano.dpi_efetivo,
            dpi_detalhe=target_dpi,
            viewport_normalizado=self.view.viewport_normalizado(),
            rotacao=self._rotation,
            limite_pixels_tile=self._tile_max_pixels,
        ):
            request = self._new_request(
                document,
                page=page,
                region=region,
                dpi=target_dpi,
                preview=False,
            )
            self._request_raster(
                request,
                page_id=context.pagina_remota_id,
                priority=priority,
            )

    def _receber_falha_renderizacao(
        self,
        request: SolicitacaoRenderizacao,
        error: Exception,
    ) -> None:
        _require_ui_thread()
        if not self._request_is_current(request):
            return
        self._scheduled_requests.discard(request.chave_cache)
        if (
            isinstance(error, ViewerGatewayError)
            and error.code is ErrorCode.PDF_PASSWORD_REQUIRED
            and self._viewer_session_id is None
        ):
            self._unlock_current_project_document()
            return
        if isinstance(error, ViewerGatewayError) and error.code in {
            ErrorCode.PDF_SOURCE_CHANGED,
            ErrorCode.VIEWER_SESSION_EXPIRED,
        }:
            self.limpar()
        self.status_changed.emit(str(error))

    def _unlock_current_project_document(self) -> None:
        context = self._current_page_context()
        for attempt in range(1, 4):
            password, accepted = QInputDialog.getText(
                self,
                "Senha do PDF",
                f"{context.documento.display_name}\nTentativa {attempt} de 3",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                self.status_changed.emit("O desbloqueio do PDF foi cancelado")
                return
            try:
                self._gateway.unlock_project_document(
                    context.documento.document_id.root,
                    password,
                )
            except ViewerGatewayError as error:
                if error.code is ErrorCode.PDF_PASSWORD_INVALID:
                    continue
                self.status_changed.emit(str(error))
                return
            self._render_current_page()
            return
        self.status_changed.emit("O limite de 3 tentativas de senha do PDF foi atingido")

    def _request_is_current(self, request: SolicitacaoRenderizacao) -> bool:
        if self._closed or request.geracao != self._generation or not self._project_pages:
            return False
        context = self._current_page_context()
        return (
            request.documento == _render_document_identity(context.documento)
            and request.pagina == context.pagina.source_page_number
            and request.rotacao == self._rotation
            and request.zoom == _stable_scale(self.view.zoom)
            and request.device_pixel_ratio == _stable_scale(self.view.devicePixelRatioF())
        )

    def _request_needs_replacement(self, request: SolicitacaoRenderizacao) -> bool:
        if self._closed or request.geracao != self._generation or not self._project_pages:
            return False
        context = self._current_page_context()
        return (
            request.documento == _render_document_identity(context.documento)
            and request.pagina == context.pagina.source_page_number
            and request.rotacao == self._rotation
        )

    def _current_page_context(
        self,
    ) -> _PaginaProjetoRemota:
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

    def _retire_session(self, session_id: UUID) -> None:
        if self._render_queue.esta_ociosa():
            _close_remote_sessions(self._gateway, (session_id,))
            return
        self._retired_session_ids.append(session_id)

    def _liberar_sessoes_apos_renderizacao(self) -> None:
        retired, self._retired_session_ids = self._retired_session_ids, []
        _close_remote_sessions(self._gateway, tuple(retired))

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


def _render_document_identity(document: ViewerDocumentDto) -> IdentidadeDocumentoRenderizacao:
    return IdentidadeDocumentoRenderizacao(
        documento_id=document.document_id.root,
        sha256=document.sha256,
        tamanho_bytes=document.size_bytes,
    )


def _stable_scale(value: float) -> float:
    return round(value, 6)


def _same_region(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return len(first) == len(second) and all(
        math.isclose(left, right, abs_tol=1e-10) for left, right in zip(first, second, strict=True)
    )


def _rotate_normalized(x: float, y: float, rotation: int) -> tuple[float, float]:
    if rotation == 90:
        return 1 - y, x
    if rotation == 180:
        return 1 - x, 1 - y
    if rotation == 270:
        return y, 1 - x
    return x, y


def _unrotate_normalized(x: float, y: float, rotation: int) -> tuple[float, float]:
    if rotation == 90:
        return y, 1 - x
    if rotation == 180:
        return 1 - x, 1 - y
    if rotation == 270:
        return 1 - y, x
    return x, y


def _require_ui_thread() -> None:
    application = QApplication.instance()
    if application is None or QThread.currentThread() != application.thread():
        raise RuntimeError("QPixmap e widgets do visualizador exigem a thread da interface")


def _png_to_pixmap(rendered: RasterPngRenderizado) -> QPixmap:
    _require_ui_thread()
    image = QImage.fromData(rendered.dados_png)
    if image.isNull():
        raise ValueError("O PNG remoto do PDF não pôde ser convertido em imagem")
    if image.width() != rendered.largura_pixels or image.height() != rendered.altura_pixels:
        raise ValueError("As dimensões do PNG remoto divergem dos metadados")
    return QPixmap.fromImage(image)


def _pixmap_size_bytes(pixmap: QPixmap) -> int:
    bytes_per_pixel = max(1, math.ceil(pixmap.depth() / 8))
    return pixmap.width() * pixmap.height() * bytes_per_pixel


class _PersistedPage(Protocol):
    id: UUID


class _PersistedDocument(Protocol):
    id: UUID
    nome_arquivo: str
    sha256: str
    tamanho_bytes: int | None
    paginas: tuple[_PersistedPage, ...]


def _temporary_project_model(
    remote_documents: tuple[ViewerDocumentDto, ...],
    *,
    persisted_documents: tuple[object, ...] | None,
    reading_order: tuple[UUID, ...] | None,
) -> tuple[tuple[ViewerDocumentDto, ...], tuple[_PaginaProjetoRemota, ...]]:
    if persisted_documents is None:
        contexts = tuple(
            sorted(
                (
                    _PaginaProjetoRemota(document, page, page.page_id.root)
                    for document in remote_documents
                    for page in document.pages
                ),
                key=lambda item: item.pagina.reading_order,
            )
        )
        return remote_documents, contexts
    persisted = cast(tuple[_PersistedDocument, ...], persisted_documents)
    if len(persisted) != len(remote_documents):
        raise ValueError("A quantidade de PDFs remotos diverge do projeto")
    displayed_documents: list[ViewerDocumentDto] = []
    by_page_id: dict[UUID, _PaginaProjetoRemota] = {}
    for remote, local in zip(remote_documents, persisted, strict=True):
        if remote.sha256 != local.sha256:
            raise ValueError(f"O conteúdo de {local.nome_arquivo} foi alterado desde a importação")
        if len(remote.pages) != len(local.paginas):
            raise ValueError(f"A paginação de {local.nome_arquivo} não corresponde ao projeto")
        displayed_pages = tuple(
            remote_page.model_copy(
                update={
                    "page_id": PageId(local_page.id),
                    "document_id": DocumentId(local.id),
                }
            )
            for remote_page, local_page in zip(remote.pages, local.paginas, strict=True)
        )
        displayed = remote.model_copy(
            update={
                "document_id": DocumentId(local.id),
                "display_name": local.nome_arquivo,
                "size_bytes": local.tamanho_bytes or remote.size_bytes,
                "pages": displayed_pages,
            }
        )
        displayed_documents.append(displayed)
        for remote_page, displayed_page in zip(remote.pages, displayed_pages, strict=True):
            by_page_id[displayed_page.page_id.root] = _PaginaProjetoRemota(
                displayed,
                displayed_page,
                remote_page.page_id.root,
            )
    expected_order = (
        reading_order
        if reading_order is not None
        else tuple(
            item.pagina.page_id.root
            for item in sorted(by_page_id.values(), key=lambda value: value.pagina.reading_order)
        )
    )
    if len(expected_order) != len(by_page_id) or set(expected_order) != set(by_page_id):
        raise ValueError("A ordem de leitura não corresponde às páginas dos PDFs abertos")
    return tuple(displayed_documents), tuple(by_page_id[page_id] for page_id in expected_order)


def _close_remote_sessions(gateway: PdfViewerGateway, session_ids: tuple[UUID, ...]) -> None:
    for session_id in session_ids:
        with suppress(ViewerGatewayError):
            gateway.close_session(session_id)


def _review_geometry_to_presentation(value: ReviewGeometryDto) -> PresentationGeometry:
    return PresentationGeometry(
        page_id=value.page_id.root,
        kind=value.kind,
        points=tuple(NormalizedPoint(Decimal(item.x), Decimal(item.y)) for item in value.points),
    )


def _review_geometry_from_presentation(value: PresentationGeometry) -> ReviewGeometryDto:
    return ReviewGeometryDto(
        page_id=PageId(value.page_id),
        kind=value.kind,
        points=tuple(
            NormalizedPointDto(x=decimal_string(item.x), y=decimal_string(item.y))
            for item in value.points
        ),
    )


def _review_color(state: ReviewState, *, alpha: int = 255) -> QColor:
    colors = {
        ReviewState.PENDING: (255, 193, 7),
        ReviewState.CONFLICTING: (255, 69, 58),
        ReviewState.ACCEPTED: (52, 199, 89),
        ReviewState.ADJUSTED: (52, 199, 89),
        ReviewState.REJECTED: (142, 142, 147),
    }
    red, green, blue = colors[state]
    return QColor(red, green, blue, alpha)


def _criar_graficos_callout(
    callout: ComplianceCalloutDto,
    transformer: TransformadorViewport,
    layer: QGraphicsRectItem,
    *,
    zoom: float,
    callout_movido: Callable[[str, NormalizedBoxDto], None],
) -> _GraficosCallout:
    result = callout.status
    color, background = _cores_callout(result, selecionado=False)
    box = callout.box
    left, top, right, bottom = _box_edges(box)
    top_left = transformer.normalizado_para_pixel(NormalizedPoint(left, top))
    top_right = transformer.normalizado_para_pixel(NormalizedPoint(right, top))
    bottom_left = transformer.normalizado_para_pixel(NormalizedPoint(left, bottom))
    box_width = math.hypot(top_right.x - top_left.x, top_right.y - top_left.y)
    box_height = math.hypot(bottom_left.x - top_left.x, bottom_left.y - top_left.y)
    angle = math.degrees(math.atan2(top_right.y - top_left.y, top_right.x - top_left.x))
    rectangle = CalloutBoxItem(QRectF(0, 0, box_width, box_height), layer)
    pen = QPen(color, 2)
    pen.setCosmetic(True)
    rectangle.setPen(pen)
    rectangle.setBrush(QBrush(background))
    rectangle.setData(0, str(callout.callout_id.root))
    rectangle.setData(2, "compliance_callout")
    rectangle.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    rectangle.setPos(top_left.x, top_left.y)
    rectangle.setRotation(angle)
    rectangle.setZValue(1)
    text_item = QGraphicsTextItem(rectangle)
    text_item.setDefaultTextColor(color)
    text_item.document().setDocumentMargin(0)
    points_width = float(Decimal(box.width)) * float(transformer.pagina.width_points)
    pixels_per_point = box_width / points_width
    padding = max(2.0, 6.0 * pixels_per_point)
    available_width = max(1.0, box_width - 2 * padding)
    minimum_scene_pixels = max(1, math.ceil(7.0 / zoom))
    font_points = float(callout.font_size_points)
    font = _fonte_callout(max(minimum_scene_pixels, round(font_points * pixels_per_point)))
    text_item.setFont(font)
    text_item.setPlainText(callout.text)
    text_item.setTextWidth(available_width)
    text_item.setPos(padding, padding)
    text_item.setData(0, str(callout.callout_id.root))
    text_item.setData(2, "compliance_callout")
    text_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    text_item.setZValue(1)
    tooltip = f"{callout.text.replace(chr(10), ' ')} · Arraste a caixa para reposicioná-la"
    rectangle.setToolTip(tooltip)
    text_item.setToolTip(tooltip)
    scene_bounds = layer.rect()
    arrow_pen = QPen(color, 2)
    arrow_pen.setCosmetic(True)
    lines: list[QGraphicsPathItem] = []
    for _anchor in _callout_anchors(callout):
        line = CalloutLinkItem(QPainterPath(), layer)
        line.setPen(arrow_pen)
        line.setData(0, str(callout.callout_id.root))
        line.setData(2, "compliance_callout")
        line.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        line.setCursor(Qt.CursorShape.PointingHandCursor)
        line.setToolTip(tooltip)
        lines.append(line)
    line_tuple = tuple(lines)

    def current_box() -> NormalizedBoxDto:
        return _caixa_callout_normalizada(rectangle, transformer)

    def update_arrows() -> None:
        _atualizar_setas_callout(
            line_tuple,
            current_box(),
            callout,
            transformer,
            pixels_per_point=pixels_per_point,
            scene_bounds=scene_bounds,
        )

    update_arrows()
    rectangle.habilitar_arraste(
        limites=scene_bounds,
        posicao_alterada=update_arrows,
        arraste_concluido=lambda: callout_movido(
            str(callout.callout_id.root),
            current_box(),
        ),
    )
    return _GraficosCallout(rectangle, text_item, line_tuple, result)


def _caixa_callout_normalizada(
    rectangle: CalloutBoxItem,
    transformer: TransformadorViewport,
) -> NormalizedBoxDto:
    corners = tuple(
        transformer.pixel_para_normalizado(PontoPlano(point.x(), point.y()))
        for point in (
            rectangle.mapToScene(rectangle.rect().topLeft()),
            rectangle.mapToScene(rectangle.rect().topRight()),
            rectangle.mapToScene(rectangle.rect().bottomLeft()),
            rectangle.mapToScene(rectangle.rect().bottomRight()),
        )
    )
    left = min(item.x for item in corners)
    top = min(item.y for item in corners)
    right = max(item.x for item in corners)
    bottom = max(item.y for item in corners)
    return NormalizedBoxDto(
        x=decimal_string(left),
        y=decimal_string(top),
        width=decimal_string(right - left),
        height=decimal_string(bottom - top),
    )


def _atualizar_setas_callout(
    lines: tuple[QGraphicsPathItem, ...],
    box: NormalizedBoxDto,
    callout: ComplianceCalloutDto,
    transformer: TransformadorViewport,
    *,
    pixels_per_point: float,
    scene_bounds: QRectF,
) -> None:
    for line, anchor in zip(lines, _callout_anchors(callout), strict=True):
        connection = _ponto_conexao_callout(box, anchor)
        start = transformer.normalizado_para_pixel(_point_to_presentation(connection))
        end = transformer.normalizado_para_pixel(_point_to_presentation(anchor))
        line.setPath(_caminho_seta_aberta(start, end, pixels_per_point, scene_bounds))


def _callout_anchors(callout: ComplianceCalloutDto) -> tuple[NormalizedPointDto, ...]:
    return callout.anchors or (callout.anchor,)


def _box_edges(box: NormalizedBoxDto) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left = Decimal(box.x)
    top = Decimal(box.y)
    return left, top, left + Decimal(box.width), top + Decimal(box.height)


def _point_to_presentation(point: NormalizedPointDto) -> NormalizedPoint:
    return NormalizedPoint(Decimal(point.x), Decimal(point.y))


def _ponto_conexao_callout(
    box: NormalizedBoxDto,
    anchor: NormalizedPointDto,
) -> NormalizedPointDto:
    left, top, right, bottom = _box_edges(box)
    anchor_x = Decimal(anchor.x)
    anchor_y = Decimal(anchor.y)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    dx = anchor_x - center_x
    dy = anchor_y - center_y
    if left <= anchor_x <= right and top <= anchor_y <= bottom:
        _distance, point = min(
            (
                (anchor_x - left, (left, anchor_y)),
                (right - anchor_x, (right, anchor_y)),
                (anchor_y - top, (anchor_x, top)),
                (bottom - anchor_y, (anchor_x, bottom)),
            ),
            key=lambda item: item[0],
        )
        return NormalizedPointDto(x=decimal_string(point[0]), y=decimal_string(point[1]))
    half_width = (right - left) / 2
    half_height = (bottom - top) / 2
    horizontal_ratio = abs(dx) / half_width if dx else Decimal(0)
    vertical_ratio = abs(dy) / half_height if dy else Decimal(0)
    if horizontal_ratio >= vertical_ratio:
        x = right if dx > 0 else left
        scale = (x - center_x) / dx
        return NormalizedPointDto(
            x=decimal_string(x),
            y=decimal_string(center_y + dy * scale),
        )
    y = bottom if dy > 0 else top
    scale = (y - center_y) / dy
    return NormalizedPointDto(
        x=decimal_string(center_x + dx * scale),
        y=decimal_string(y),
    )


def _cores_callout(
    resultado: ComplianceStatus,
    *,
    selecionado: bool,
) -> tuple[QColor, QColor]:
    foregrounds = {
        ComplianceStatus.DIVERGENCE: ("#c62828", "#8e0000"),
        ComplianceStatus.COMPLIANT: ("#2e7d32", "#1b5e20"),
        ComplianceStatus.NOT_EVALUABLE: ("#8d6e00", "#5f4b00"),
    }
    selected_backgrounds = {
        ComplianceStatus.DIVERGENCE: "#fff3e0",
        ComplianceStatus.COMPLIANT: "#e8f5e9",
        ComplianceStatus.NOT_EVALUABLE: "#fff8e1",
    }
    regular, highlighted = foregrounds[resultado]
    foreground = QColor(highlighted if selecionado else regular)
    background = QColor(selected_backgrounds[resultado] if selecionado else "white")
    background.setAlpha(205)
    return foreground, background


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


def _review_link_pen(state: ReviewState, *, selected: bool = False) -> QPen:
    pen = QPen(QColor("#0078d4") if selected else _review_color(state), 5 if selected else 3)
    pen.setCosmetic(True)
    if state is ReviewState.REJECTED:
        pen.setStyle(Qt.PenStyle.DashLine)
    return pen


def _review_link_path(
    geometry: PresentationGeometry,
    transformer: TransformadorViewport,
) -> QPainterPath:
    pixels = tuple(transformer.normalizado_para_pixel(point) for point in geometry.points)
    if geometry.kind is ReviewGeometryKind.POLYGON and len(pixels) == 4:
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
