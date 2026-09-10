"""Regressões sintéticas do marca-texto operacional, separado da revisão humana."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler_client.presentation import NormalizedPoint
from zeny_project_handler_client.ui.pdf_rendering import PlanoRasterRemoto
from zeny_project_handler_client.ui.pdf_viewer import (
    PdfGraphicsView,
    PdfViewerWidget,
    TransformadorViewport,
)
from zeny_project_handler_contracts.base import DocumentId, PageId, ProposalId
from zeny_project_handler_contracts.common import NormalizedPointDto
from zeny_project_handler_contracts.enums import (
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewState,
)
from zeny_project_handler_contracts.review import ReviewGeometryDto, ReviewOverlayDto
from zeny_project_handler_contracts.viewer import ViewerPageDto

pytestmark = pytest.mark.integration


def _view(qtbot: QtBot, rotation: int = 0) -> tuple[PdfGraphicsView, TransformadorViewport]:
    page = ViewerPageDto(
        page_id=PageId(uuid4()),
        document_id=DocumentId(uuid4()),
        reading_order=0,
        source_page_number=1,
        width_points="400",
        height_points="300",
        intrinsic_rotation_degrees=0,
    )
    width, height = (300, 400) if rotation in (90, 270) else (400, 300)
    transformer = TransformadorViewport(
        page,
        PlanoRasterRemoto(
            dpi_solicitado=72,
            dpi_efetivo=72,
            rotacao_adicional_graus=rotation,
            recorte_normalizado=(0, 0, 1, 1),
            largura_pixels=width,
            altura_pixels=height,
            largura_pagina_pixels=width,
            altura_pagina_pixels=height,
            origem_x_pixels=0,
            origem_y_pixels=0,
            reduzido=False,
        ),
    )
    view = PdfGraphicsView()
    qtbot.addWidget(view)
    view.resize(700, 700)
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.white)
    view.definir_previa(pixmap)
    view.show()
    return view, transformer


def _geometry(
    transformer: TransformadorViewport,
    kind: ReviewGeometryKind = ReviewGeometryKind.BOX,
    points: tuple[tuple[float, float], ...] = ((0.2, 0.2), (0.6, 0.6)),
) -> ReviewGeometryDto:
    if kind is ReviewGeometryKind.BOX and len(points) == 2:
        (left, top), (right, bottom) = points
        points = ((left, top), (right, top), (right, bottom), (left, bottom))
    return ReviewGeometryDto(
        page_id=transformer.pagina.page_id,
        kind=kind,
        points=tuple(NormalizedPointDto(x=str(x), y=str(y)) for x, y in points),
    )


def _proposal(
    geometry: ReviewGeometryDto,
    *,
    situation: ElementSituation = ElementSituation.INSTALL,
    state: ReviewState = ReviewState.PENDING,
    link: ReviewGeometryDto | None = None,
) -> ReviewOverlayDto:
    return ReviewOverlayDto(
        proposal_id=ProposalId(uuid4()),
        geometry=geometry,
        link_geometry=link or geometry,
        label="Ocorrência sintética",
        category=ElementCategory.POLE,
        situation=situation,
        situation_label=situation.value,
        review_state=state,
        confidence="0.9",
    )


def _render(view: PdfGraphicsView) -> QImage:
    rect = view.sceneRect()
    image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    view.scene().render(painter, QRectF(image.rect()), rect)
    painter.end()
    return image


@pytest.mark.parametrize(
    ("situation", "hex_color"),
    (
        (ElementSituation.INSTALL, "#22c55e"),
        (ElementSituation.EXISTING, "#facc15"),
        (ElementSituation.REMOVE, "#ef4444"),
        (ElementSituation.CHANGE, "#3b82f6"),
    ),
)
@pytest.mark.parametrize(
    "state",
    (ReviewState.PENDING, ReviewState.CONFLICTING, ReviewState.ACCEPTED, ReviewState.ADJUSTED),
)
def test_situation_color_and_quarter_opacity_are_independent_of_review_state(
    qtbot: QtBot, situation: ElementSituation, hex_color: str, state: ReviewState
) -> None:
    view, transformer = _view(qtbot)
    proposal = _proposal(_geometry(transformer), situation=situation, state=state)
    view.definir_propostas_revisao((proposal,), transformer)

    fill = view._review_highlight_fills[situation]
    assert fill.brush().color().name() == hex_color
    assert fill.brush().color().alphaF() == pytest.approx(0.25, abs=0.005)
    expected = QColor(hex_color)
    pixel = _render(view).pixelColor(160, 120)
    for channel in ("red", "green", "blue"):
        assert getattr(pixel, channel)() == pytest.approx(
            round(255 * 0.75 + getattr(expected, channel)() * 0.25), abs=1
        )
    marker = view._review_items[str(proposal.proposal_id.root)]
    assert state.value in marker.toolTip()


def test_selection_and_click_keep_fill_and_editable_geometry(qtbot: QtBot) -> None:
    view, transformer = _view(qtbot)
    geometry = _geometry(transformer, points=((0.05, 0.05), (0.95, 0.95)))
    evidence = _geometry(transformer)
    proposal = _proposal(geometry, link=evidence)
    view.definir_propostas_revisao((proposal,), transformer)
    key = str(proposal.proposal_id.root)
    marker = view._review_items[key]
    fill = view._review_highlight_fills[proposal.situation]
    original_brush = fill.brush()
    original_geometry = view.geometria_proposta(key)
    assert marker.path().contains(QPointF(160, 120))
    assert not marker.path().contains(QPointF(350, 250))

    with qtbot.waitSignal(view.proposta_selecionada, timeout=1_000) as selected:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.mapFromScene(QPointF(160, 120)),
        )
    assert selected.args == [key]
    assert marker.isSelected()
    assert marker.pen().color().name() == "#172033"
    assert fill.brush() == original_brush
    assert view.geometria_proposta(key) == original_geometry
    assert original_geometry is not None
    assert len(original_geometry.points) == len(geometry.points)
    for point, expected in zip(original_geometry.points, geometry.points, strict=True):
        assert float(point.x) == pytest.approx(float(expected.x))
        assert float(point.y) == pytest.approx(float(expected.y))


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
@pytest.mark.parametrize("zoom", (0.5, 1.0, 2.0))
def test_inclined_polygon_stays_on_evidence_at_every_rotation_and_zoom(
    qtbot: QtBot, rotation: int, zoom: float
) -> None:
    view, transformer = _view(qtbot, rotation)
    polygon = _geometry(
        transformer,
        ReviewGeometryKind.POLYGON,
        ((0.2, 0.2), (0.7, 0.5), (0.65, 0.6), (0.15, 0.3)),
    )
    proposal = _proposal(polygon)
    view.definir_propostas_revisao((proposal,), transformer)
    view.definir_zoom(zoom)
    path = view._review_items[str(proposal.proposal_id.root)].path()
    for coordinates, inside in (((0.425, 0.4), True), ((0.65, 0.25), False)):
        normalized = NormalizedPoint(Decimal(str(coordinates[0])), Decimal(str(coordinates[1])))
        point = transformer.normalizado_para_pixel(normalized)
        assert path.contains(QPointF(point.x, point.y)) is inside
    assert view.zoom == zoom


@pytest.mark.parametrize(
    ("kind", "points", "inside", "outside"),
    (
        (
            ReviewGeometryKind.POLYLINE,
            ((0.2, 0.2), (0.8, 0.8)),
            QPointF(200, 150),
            QPointF(80, 240),
        ),
        (
            ReviewGeometryKind.POINT,
            ((0.5, 0.5),),
            QPointF(200, 150),
            QPointF(220, 170),
        ),
    ),
)
def test_line_and_point_have_compact_filled_area_instead_of_bounding_box(
    qtbot: QtBot,
    kind: ReviewGeometryKind,
    points: tuple[tuple[float, float], ...],
    inside: QPointF,
    outside: QPointF,
) -> None:
    view, transformer = _view(qtbot)
    proposal = _proposal(_geometry(transformer, kind, points))
    view.definir_propostas_revisao((proposal,), transformer)
    path = view._review_items[str(proposal.proposal_id.root)].path()
    assert path.contains(inside)
    assert not path.contains(outside)


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_box_with_two_corners_keeps_its_area_when_rotated(qtbot: QtBot, rotation: int) -> None:
    view, transformer = _view(qtbot, rotation)
    box = _geometry(transformer)
    box = box.model_copy(update={"points": (box.points[0], box.points[2])})
    proposal = _proposal(box)
    view.definir_propostas_revisao((proposal,), transformer)
    path = view._review_items[str(proposal.proposal_id.root)].path()
    point = transformer.normalizado_para_pixel(NormalizedPoint(Decimal("0.4"), Decimal("0.4")))
    assert path.contains(QPointF(point.x, point.y))


def test_same_situation_overlap_does_not_darken_and_clear_removes_all_fill(qtbot: QtBot) -> None:
    view, transformer = _view(qtbot)
    first = _proposal(_geometry(transformer))
    duplicate = first.model_copy(update={"proposal_id": ProposalId(uuid4())})
    overlap = _proposal(_geometry(transformer, points=((0.4, 0.3), (0.8, 0.7))))
    view.definir_propostas_revisao((first,), transformer)
    single_pixel = _render(view).pixelColor(200, 150)
    view.definir_propostas_revisao((first, duplicate, overlap), transformer)
    assert _render(view).pixelColor(200, 150) == single_pixel
    assert len(view._review_items) == 3
    view.definir_propostas_revisao((), transformer)
    assert not view._review_items
    assert not view._review_highlight_fills
    assert _render(view).pixelColor(200, 150) == QColor("white")


def test_mixed_situations_stay_bounded_to_four_fills_even_with_duplicate_evidence(
    qtbot: QtBot,
) -> None:
    view, transformer = _view(qtbot)
    proposals = tuple(
        _proposal(_geometry(transformer), situation=situation) for situation in ElementSituation
    )
    view.definir_propostas_revisao(proposals, transformer)
    original = _render(view).pixelColor(160, 120)
    duplicates = tuple(
        proposal.model_copy(update={"proposal_id": ProposalId(uuid4())})
        for proposal in proposals
        for _ in range(20)
    )
    view.definir_propostas_revisao(duplicates, transformer)
    assert len(view._review_highlight_fills) == 4
    assert len(view._review_items) == 80
    assert _render(view).pixelColor(160, 120) == original


@pytest.mark.parametrize("rotation", (0, 90, 180, 270))
def test_point_at_page_corner_is_clipped_to_page(qtbot: QtBot, rotation: int) -> None:
    view, transformer = _view(qtbot, rotation)
    proposal = _proposal(_geometry(transformer, ReviewGeometryKind.POINT, ((0, 0),)))
    view.definir_propostas_revisao((proposal,), transformer)
    bounds = view._review_highlight_fills[proposal.situation].path().boundingRect()
    assert not bounds.isEmpty()
    assert bounds.left() >= 0
    assert bounds.top() >= 0
    assert bounds.right() <= transformer.largura_pixels
    assert bounds.bottom() <= transformer.altura_pixels


def test_small_point_remains_clickable_near_its_edge_at_half_zoom(qtbot: QtBot) -> None:
    view, transformer = _view(qtbot)
    proposal = _proposal(_geometry(transformer, ReviewGeometryKind.POINT, ((0.5, 0.5),)))
    view.definir_propostas_revisao((proposal,), transformer)
    view.definir_zoom(0.5)
    marker = view._review_items[str(proposal.proposal_id.root)]
    target = QPointF(207, 150)
    assert marker.shape().contains(target)
    with qtbot.waitSignal(view.proposta_selecionada, timeout=1_000) as selected:
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            view.viewport(), Qt.MouseButton.LeftButton, pos=view.mapFromScene(target)
        )
    assert selected.args == [str(proposal.proposal_id.root)]


def test_rejected_proposal_retains_navigation_without_operational_fill(qtbot: QtBot) -> None:
    view, transformer = _view(qtbot)
    proposal = _proposal(_geometry(transformer))
    view.definir_propostas_revisao((proposal,), transformer)
    rejected = proposal.model_copy(update={"review_state": ReviewState.REJECTED})
    view.definir_propostas_revisao((rejected,), transformer)
    assert not view._review_highlight_fills
    assert _render(view).pixelColor(160, 120) == QColor("white")
    key = str(proposal.proposal_id.root)
    marker = view._review_items[key]
    assert marker.pen().style() == Qt.PenStyle.DashLine
    with qtbot.waitSignal(view.proposta_selecionada, timeout=1_000) as selected:
        view.selecionar_proposta(key)
    assert selected.args == [key]


@pytest.mark.parametrize("wrong_field", ("geometry", "link_geometry"))
def test_evidence_from_other_page_is_never_painted(qtbot: QtBot, wrong_field: str) -> None:
    view, transformer = _view(qtbot)
    proposal = _proposal(_geometry(transformer))
    other_page = proposal.geometry.model_copy(update={"page_id": PageId(uuid4())})
    proposal = proposal.model_copy(update={wrong_field: other_page})
    view.definir_propostas_revisao((proposal,), transformer)
    assert not view._review_items
    assert not view._review_highlight_fills


def test_highlight_legend_identifies_all_situations_and_review_distinction(qtbot: QtBot) -> None:
    viewer = PdfViewerWidget(
        gateway=LocalTestPdfViewerGateway(), dpi=72, limite_pixels_tile=100_000
    )
    qtbot.addWidget(viewer)
    legend = viewer.findChild(QLabel, "reviewHighlightLegend")
    assert legend is not None
    text = legend.text().lower()
    for label in ("instalar", "existente", "remover", "alterar"):
        assert label in text
    for color in ("#22c55e", "#facc15", "#ef4444", "#3b82f6"):
        assert color in text
    assert "aprovação" in text
    assert "seleção" in text
    assert "rejeitada" in text
