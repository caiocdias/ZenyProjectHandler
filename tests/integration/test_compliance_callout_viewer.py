from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import (
    TEST_RENDER_BUDGET,
    create_callout_formats_pdf,
    create_callout_header_pdf,
)
from tests.viewer_gateway import LocalTestPdfViewerGateway

from zeny_project_handler.application.compliance_callouts import (
    AncoraCallout,
    CalloutConformidade,
    OrigemAncoraCallout,
    RetanguloCallout,
    projetar_callouts_conformidade,
)
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    AvaliacaoCondicaoConformidade,
    ExecucaoConformidade,
    FatoConformidade,
    FonteNormativa,
    GrupoCondicaoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
    SeveridadeConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import PaginaDocumento
from zeny_project_handler.domain.values import CaixaPagina, GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler_client.ui.pdf_viewer import PdfViewerWidget
from zeny_project_handler_contracts.base import CalloutId, DocumentId, FindingId, PageId, ProposalId
from zeny_project_handler_contracts.common import (
    EvidenceNavigationDto,
    NormalizedBoxDto,
    NormalizedPointDto,
)
from zeny_project_handler_contracts.compliance import ComplianceCalloutDto
from zeny_project_handler_contracts.enums import (
    ComplianceStatus,
    ElementCategory,
    ElementSituation,
    ReviewGeometryKind,
    ReviewState,
)
from zeny_project_handler_contracts.review import ReviewGeometryDto, ReviewOverlayDto
from zeny_project_handler_contracts.viewer import ViewerPageDto

TILED_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=200_000,
    limite_bytes=1_400_000,
)


class _DtoCalloutViewer(PdfViewerWidget):
    def definir_callouts_conformidade(
        self,
        callouts: tuple[ComplianceCalloutDto | CalloutConformidade, ...],
    ) -> None:
        super().definir_callouts_conformidade(tuple(_callout_dto(item) for item in callouts))


@pytest.mark.integration
def test_callout_layer_draws_box_text_open_arrows_and_coexists_with_review_links(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "camadas-callout.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]
    callout = _callout(
        page.page_id.root,
        float(page.width_points),
        float(page.height_points),
        "primeiro",
    )
    proposal = _proposal(page.page_id.root)

    viewer.definir_callouts_conformidade((callout,))
    viewer.definir_propostas_revisao((proposal,))

    graphics = viewer.view._callout_items[str(callout.id)]
    background = graphics.caixa.brush().color()
    assert background.name() == QColor("white").name()
    assert background.alpha() == 205
    assert graphics.caixa.pen().color() == QColor("#c62828")
    assert graphics.texto.defaultTextColor() == QColor("#c62828")
    assert graphics.texto.toPlainText() == callout.texto
    assert len(graphics.linhas) == 2
    assert all(item.path().elementCount() == 6 for item in graphics.linhas)
    proposal_id = str(proposal.proposal_id.root)
    assert proposal_id in viewer.view._review_items
    assert viewer.view._callout_layer is not None
    assert viewer.view._callout_layer.zValue() == 30
    assert viewer.view._review_items[proposal_id].zValue() == 20

    viewer.definir_callouts_conformidade(())
    assert proposal_id in viewer.view._review_items
    viewer.definir_callouts_conformidade((callout,))
    viewer.definir_propostas_revisao(())
    assert str(callout.id) in viewer.view._callout_items


@pytest.mark.integration
def test_callout_box_and_arrow_emit_only_user_selection_and_are_highlighted(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "selecao-callout.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]
    callout = _callout(
        page.page_id.root,
        float(page.width_points),
        float(page.height_points),
        "selection",
    )
    viewer.definir_callouts_conformidade((callout,))
    graphics = viewer.view._callout_items[str(callout.id)]
    selected: list[str] = []
    proposals: list[str] = []
    viewer.compliance_callout_selected.connect(selected.append)
    viewer.proposal_selected.connect(proposals.append)

    viewer.selecionar_callout(str(callout.id))
    assert selected == []
    assert graphics.caixa.pen().color() == QColor("#8e0000")
    assert graphics.caixa.pen().widthF() == pytest.approx(3.2)
    assert graphics.caixa.brush().color().alpha() == 205

    box_center = viewer.view.mapFromScene(graphics.caixa.mapToScene(graphics.caixa.rect().center()))
    with qtbot.waitSignal(viewer.compliance_callout_selected, timeout=1_000):
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            viewer.view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=QPoint(box_center.x(), box_center.y()),
        )
    assert selected == [str(callout.id)]

    arrow = graphics.linhas[0]
    arrow_center = viewer.view.mapFromScene(arrow.mapToScene(arrow.path().pointAtPercent(0.5)))
    with qtbot.waitSignal(viewer.compliance_callout_selected, timeout=1_000):
        qtbot.mouseClick(  # type: ignore[no-untyped-call]
            viewer.view.viewport(),
            Qt.MouseButton.LeftButton,
            pos=QPoint(arrow_center.x(), arrow_center.y()),
        )
    assert selected == [str(callout.id), str(callout.id)]
    assert proposals == []


@pytest.mark.integration
def test_callout_box_drag_keeps_anchor_fixed_updates_arrow_and_preserves_position(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "arraste-callout.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]
    callout = _callout(
        page.page_id.root,
        float(page.width_points),
        float(page.height_points),
        "drag",
    )
    viewer.definir_callouts_conformidade((callout,))
    graphics = viewer.view._callout_items[str(callout.id)]
    original_position = graphics.caixa.pos()
    original_box = _callout_dto(callout).box
    original_path = graphics.linhas[0].path()
    original_start = original_path.elementAt(0)
    fixed_tip = original_path.elementAt(1)
    box_center = viewer.view.mapFromScene(graphics.caixa.mapToScene(graphics.caixa.rect().center()))
    target = box_center + QPoint(-110, 70)

    qtbot.mousePress(  # type: ignore[no-untyped-call]
        viewer.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=box_center,
    )
    qtbot.mouseMove(viewer.view.viewport(), pos=target, delay=20)  # type: ignore[no-untyped-call]
    qtbot.mouseRelease(  # type: ignore[no-untyped-call]
        viewer.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=target,
    )
    qtbot.wait(20)

    moved_path = graphics.linhas[0].path()
    moved_start = moved_path.elementAt(0)
    moved_tip = moved_path.elementAt(1)
    assert graphics.caixa.pos() != original_position
    assert (moved_start.x, moved_start.y) != pytest.approx((original_start.x, original_start.y))
    assert (moved_tip.x, moved_tip.y) == pytest.approx((fixed_tip.x, fixed_tip.y))
    moved_box = viewer._compliance_callouts[0].box
    assert moved_box != original_box
    moved_left = Decimal(moved_box.x)
    moved_top = Decimal(moved_box.y)
    assert Decimal(0) <= moved_left < moved_left + Decimal(moved_box.width) <= Decimal(1)
    assert Decimal(0) <= moved_top < moved_top + Decimal(moved_box.height) <= Decimal(1)

    viewer.definir_callouts_conformidade(())
    viewer.definir_callouts_conformidade((callout,))
    assert viewer._compliance_callouts[0].box == moved_box

    viewer.ir_para_folha(2)
    _wait_preview(qtbot, viewer, page=2)
    viewer.ir_para_folha(1)
    _wait_preview(qtbot, viewer, page=1)
    assert viewer._compliance_callouts[0].box == moved_box


@pytest.mark.integration
@pytest.mark.parametrize(
    ("result", "regular_color", "selected_color", "selected_background"),
    (
        (ResultadoConformidade.DIVERGENCIA, "#c62828", "#8e0000", "#fff3e0"),
        (ResultadoConformidade.CONFORME, "#2e7d32", "#1b5e20", "#e8f5e9"),
        (ResultadoConformidade.NAO_AVALIAVEL, "#8d6e00", "#5f4b00", "#fff8e1"),
    ),
)
def test_callout_color_identifies_compliance_result(
    qtbot: QtBot,
    tmp_path: Path,
    result: ResultadoConformidade,
    regular_color: str,
    selected_color: str,
    selected_background: str,
) -> None:
    source = create_callout_formats_pdf(tmp_path / f"cor-{result.value}.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]
    callout = replace(
        _callout(
            page.page_id.root,
            float(page.width_points),
            float(page.height_points),
            result.value,
        ),
        resultado=result,
    )

    viewer.definir_callouts_conformidade((callout,))

    graphics = viewer.view._callout_items[str(callout.id)]
    assert graphics.caixa.pen().color() == QColor(regular_color)
    assert graphics.texto.defaultTextColor() == QColor(regular_color)

    viewer.selecionar_callout(str(callout.id))
    assert graphics.caixa.pen().color() == QColor(selected_color)
    assert graphics.texto.defaultTextColor() == QColor(selected_color)
    assert graphics.caixa.brush().color().name() == QColor(selected_background).name()


@pytest.mark.integration
def test_callout_anchor_survives_zoom_resize_rotation_tiles_and_page_changes(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "transformacoes-callout.pdf")
    original_pdf = source.read_bytes()
    viewer = _viewer(qtbot, dpi=600, budget=TILED_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    pages = viewer.inspecao.pages
    callouts = tuple(
        _callout(
            page.page_id.root,
            float(page.width_points),
            float(page.height_points),
            str(index),
        )
        for index, page in enumerate(pages, start=1)
    )
    viewer.definir_callouts_conformidade(callouts)
    _assert_anchor_aligned(viewer, callouts[0])
    _assert_text_fits(viewer, callouts[0])

    viewer.view.definir_zoom(0.1)
    graphics = viewer.view._callout_items[str(callouts[0].id)]
    assert graphics.texto.font().pixelSize() * viewer.view.zoom >= 7.0
    _assert_anchor_aligned(viewer, callouts[0])
    viewer.view.definir_zoom(4.0)
    qtbot.waitUntil(lambda: bool(viewer.view._tile_items), timeout=10_000)
    _assert_anchor_aligned(viewer, callouts[0])
    _assert_text_fits(viewer, callouts[0])
    viewer.resize(1024, 720)
    qtbot.wait(20)
    _assert_anchor_aligned(viewer, callouts[0])
    _assert_text_fits(viewer, callouts[0])

    for rotation in (90, 180, 270, 0):
        viewer._rotate_page()
        _wait_preview(qtbot, viewer, rotation=rotation)
        _assert_anchor_aligned(viewer, callouts[0])
        _assert_text_fits(viewer, callouts[0])

    viewer.ir_para_folha(2)
    _wait_preview(qtbot, viewer, page=2)
    assert set(viewer.view._callout_items) == {str(callouts[1].id)}
    _assert_anchor_aligned(viewer, callouts[1])
    _assert_text_fits(viewer, callouts[1])
    viewer.ir_para_folha(1)
    _wait_preview(qtbot, viewer, page=1)
    assert set(viewer.view._callout_items) == {str(callouts[0].id)}
    assert source.read_bytes() == original_pdf


@pytest.mark.integration
def test_synthetic_a4_a3_portrait_landscape_callout_renders_are_saved(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    output_directory = _qa_output_directory(tmp_path)
    source = create_callout_formats_pdf(output_directory / "inspecao-visual-callouts.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    pages = viewer.inspecao.pages
    callouts = tuple(
        _callout(
            page.page_id.root,
            float(page.width_points),
            float(page.height_points),
            str(index),
        )
        for index, page in enumerate(pages, start=1)
    )
    viewer.definir_callouts_conformidade(callouts)

    renders: list[Path] = []
    for page_number, callout in enumerate(callouts, start=1):
        viewer.ir_para_folha(page_number)
        _wait_preview(qtbot, viewer, page=page_number)
        _assert_anchor_aligned(viewer, callout)
        output = output_directory / f"callout-formato-{page_number}.png"
        assert viewer.view.grab().save(str(output), "PNG")
        assert output.stat().st_size > 10_000
        renders.append(output)

    assert len(renders) == 4


@pytest.mark.integration
def test_client_draws_prepositioned_callout_without_local_layout_analysis(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    output_directory = _qa_output_directory(tmp_path)
    source = create_callout_header_pdf(output_directory / "callout-cabecalho-fixture.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]

    callout = _projected_dense_callouts(page, count=1)[0]
    box = callout.caixa_sugerida
    assert Decimal(0) <= box.esquerda < box.direita <= Decimal(1)

    viewer.definir_callouts_conformidade((callout,))
    viewer.resize(1400, 1000)
    viewer.view.ajustar_pagina()
    qtbot.wait(20)
    _save_viewport(viewer, output_directory / "callout-cabecalho-espaco-branco.png")


@pytest.mark.integration
def test_dense_projected_callouts_fit_at_minimum_font_and_save_visual_qa(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    output_directory = _qa_output_directory(tmp_path)
    source = create_callout_formats_pdf(output_directory / "callout-denso-fixture.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    page = viewer.inspecao.pages[0]
    callouts = _projected_dense_callouts(page, count=10)
    assert len(callouts) == 10
    assert all(
        _normalized_intersection_area(left.caixa_sugerida, right.caixa_sugerida) == 0
        for index, left in enumerate(callouts)
        for right in callouts[index + 1 :]
    )

    minimum_font_callouts = _projected_dense_callouts(
        page,
        count=11,
        long_text=True,
    )
    assert len(minimum_font_callouts) == 11
    assert all(
        Decimal("8.5") <= item.tamanho_fonte_pontos <= Decimal("9")
        for item in minimum_font_callouts
    )
    assert all(
        _normalized_intersection_area(left.caixa_sugerida, right.caixa_sugerida) == 0
        for index, left in enumerate(minimum_font_callouts)
        for right in minimum_font_callouts[index + 1 :]
    )
    viewer.view.definir_zoom(1.0)
    viewer.definir_callouts_conformidade(minimum_font_callouts)
    for callout in minimum_font_callouts:
        _assert_text_fits(viewer, callout)
        graphics = viewer.view._callout_items[str(callout.id)]
        assert graphics.texto.font().pixelSize() * viewer.view.zoom >= 7.0
    viewer.definir_callouts_conformidade(callouts)
    viewer.resize(1400, 1000)
    viewer.view.ajustar_pagina()
    qtbot.wait(20)
    output = output_directory / "callout-denso-10-p2.png"
    _save_viewport(viewer, output)


@pytest.mark.integration
def test_multipage_callout_visual_qa_captures_show_hide_and_correct_page(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    output_directory = _qa_output_directory(tmp_path)
    source = create_callout_formats_pdf(output_directory / "callout-multipagina-fixture.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    pages = viewer.inspecao.pages
    callouts = tuple(
        _callout(
            page.page_id.root,
            float(page.width_points),
            float(page.height_points),
            str(index),
        )
        for index, page in enumerate(pages, start=1)
    )

    viewer.definir_callouts_conformidade(callouts)
    assert set(viewer.view._callout_items) == {str(callouts[0].id)}
    first_graphics = viewer.view._callout_items[str(callouts[0].id)]
    assert first_graphics.caixa.brush().color().alpha() == 205
    assert first_graphics.texto.defaultTextColor() == QColor("#c62828")
    assert first_graphics.caixa.pen().color() == QColor("#c62828")
    assert first_graphics.linhas
    _save_viewport(viewer, output_directory / "callout-pagina-1-visivel.png")

    viewer.definir_callouts_conformidade(callouts[1:])
    assert viewer.view._callout_items == {}
    _save_viewport(viewer, output_directory / "callout-pagina-1-oculto.png")

    viewer.definir_callouts_conformidade(callouts)
    assert set(viewer.view._callout_items) == {str(callouts[0].id)}
    viewer.ir_para_folha(2)
    _wait_preview(qtbot, viewer, page=2)
    assert set(viewer.view._callout_items) == {str(callouts[1].id)}
    _assert_anchor_aligned(viewer, callouts[1])
    _save_viewport(viewer, output_directory / "callout-pagina-2-visivel.png")


def _qa_output_directory(tmp_path: Path) -> Path:
    configured = os.environ.get("ZENY_CALLOUT_QA_DIR")
    output_directory = Path(configured) if configured else tmp_path
    output_directory.mkdir(parents=True, exist_ok=True)
    return output_directory


def _save_viewport(viewer: PdfViewerWidget, output: Path) -> None:
    assert viewer.view.grab().save(str(output), "PNG")
    assert output.stat().st_size > 1_000


def _viewer(qtbot: QtBot, *, dpi: int, budget: OrcamentoRenderizacaoPdf) -> _DtoCalloutViewer:
    viewer = _DtoCalloutViewer(
        gateway=LocalTestPdfViewerGateway(budget=budget),
        dpi=dpi,
        limite_pixels_tile=min(budget.limite_pixels, budget.limite_bytes // 7),
    )
    qtbot.addWidget(viewer)
    viewer.resize(900, 700)
    viewer.show()
    return viewer


def _callout_dto(
    callout: ComplianceCalloutDto | CalloutConformidade,
) -> ComplianceCalloutDto:
    if isinstance(callout, ComplianceCalloutDto):
        return callout
    box = callout.caixa_sugerida
    box_dto = NormalizedBoxDto(
        x=str(box.esquerda),
        y=str(box.topo),
        width=str(box.largura),
        height=str(box.altura),
    )
    anchors = tuple(
        NormalizedPointDto(x=str(item.ponto.x), y=str(item.ponto.y)) for item in callout.ancoras
    )
    navigation = EvidenceNavigationDto(
        document_id=DocumentId(uuid5(NAMESPACE_URL, f"document:{callout.pagina_id}")),
        page_id=PageId(callout.pagina_id),
        geometry=box_dto,
        label=callout.texto,
    )
    return ComplianceCalloutDto(
        callout_id=CalloutId(callout.id),
        finding_id=FindingId(callout.id),
        text=callout.texto,
        anchor=anchors[0],
        anchors=anchors,
        box=box_dto,
        font_size_points=str(callout.tamanho_fonte_pontos),
        status={
            ResultadoConformidade.CONFORME: ComplianceStatus.COMPLIANT,
            ResultadoConformidade.DIVERGENCIA: ComplianceStatus.DIVERGENCE,
            ResultadoConformidade.NAO_AVALIAVEL: ComplianceStatus.NOT_EVALUABLE,
        }[callout.resultado],
        navigation=navigation,
    )


def _wait_preview(
    qtbot: QtBot,
    viewer: PdfViewerWidget,
    *,
    page: int = 1,
    rotation: int = 0,
) -> None:
    qtbot.waitUntil(
        lambda: (
            viewer._current_preview is not None
            and viewer.folha_atual == page
            and viewer._current_preview.plano.rotacao_adicional_graus == rotation
        ),
        timeout=10_000,
    )


def _callout(
    page_id: UUID,
    page_width: float,
    page_height: float,
    key: str,
) -> CalloutConformidade:
    anchor_points = (
        PontoNormalizado(Decimal("0.46"), Decimal("0.56")),
        PontoNormalizado(Decimal("0.50"), Decimal("0.60")),
    )
    width = min(252.0, page_width * 0.36) / page_width
    height = min(94.0, page_height * 0.22) / page_height
    left = 0.96 - width
    top = 0.08
    box = RetanguloCallout(
        Decimal(str(left)),
        Decimal(str(top)),
        Decimal("0.96"),
        Decimal(str(top + height)),
    )
    anchors = tuple(
        AncoraCallout(
            origem=OrigemAncoraCallout.FATO,
            referencia_id=uuid4(),
            geometria=GeometriaDocumento.ponto(page_id, point),
            ponto=point,
        )
        for point in anchor_points
    )
    return CalloutConformidade(
        id=uuid4(),
        pagina_id=page_id,
        texto=(
            f"Divergência {key}: valor observado incompatível\ncom o requisito sintético esperado."
        ),
        caixa_sugerida=box,
        ancoras=anchors,
    )


def _projected_dense_callouts(
    remote_page: ViewerPageDto,
    *,
    count: int,
    long_text: bool = False,
) -> tuple[CalloutConformidade, ...]:
    width = Decimal(remote_page.width_points)
    height = Decimal(remote_page.height_points)
    box = CaixaPagina(Decimal(0), Decimal(0), width, height)
    page = PaginaDocumento(
        id=remote_page.page_id.root,
        numero=remote_page.source_page_number,
        largura_pontos=width,
        altura_pontos=height,
        rotacao_graus=remote_page.intrinsic_rotation_degrees,
        media_box=box,
        crop_box=box,
    )
    target_id = _dense_id("target-p2")
    target = AlvoConformidade(
        id=target_id,
        tipo=TipoEscopoConformidade.REGIAO,
        rotulo="P2",
        pagina_id=page.id,
        geometria=GeometriaDocumento.ponto(
            page.id,
            PontoNormalizado(Decimal("0.46"), Decimal("0.56")),
        ),
    )
    facts: list[FatoConformidade] = []
    findings: list[AchadoConformidade] = []
    presentation: dict[UUID, str] = {}
    for index in range(count):
        point = PontoNormalizado(
            Decimal("0.18") + Decimal(index % 5) * Decimal("0.16"),
            Decimal("0.30") + Decimal(index // 5) * Decimal("0.34"),
        )
        geometry = GeometriaDocumento.ponto(page.id, point)
        fact_id = _dense_id(f"fact-{index}")
        finding_id = _dense_id(f"finding-{index}")
        facts.append(
            FatoConformidade(
                id=fact_id,
                alvo_id=target_id,
                chave="fixture.valor",
                valor=False,
                origem="fixture densa P2",
                geometria=geometry,
            )
        )
        evaluation = AvaliacaoCondicaoConformidade(
            grupo=GrupoCondicaoConformidade.REQUISITO,
            indice=0,
            chave_fato="fixture.valor",
            operador=OperadorCondicao.IGUAL,
            quantificador=QuantificadorCondicao.TODOS,
            valores_esperados=(True,),
            valores_observados=(False,),
            fato_ids=(fact_id,),
            resultado=ResultadoCondicaoConformidade.NAO_ATENDE,
        )
        findings.append(
            AchadoConformidade(
                id=finding_id,
                regra_id=f"fixture.densa-{index}",
                alvo_id=target_id,
                resultado=ResultadoConformidade.DIVERGENCIA,
                severidade=SeveridadeConformidade.ERRO,
                titulo=f"Divergência densa {index}",
                mensagem="Valor observado não atende ao requisito sintético.",
                fonte=FonteNormativa(
                    documento="Norma sintética",
                    revisao="1",
                    item="P2",
                ),
                versao_regras="fixture-1",
                fato_ids=(fact_id,),
                avaliacoes_condicoes=(evaluation,),
            )
        )
        presentation[finding_id] = (
            "Poste P2. " + "texto longo " * 22
            if long_text
            else (
                f"Poste P2 - divergência {index}. "
                "Requisito não atendido: presença de chave fusível."
            )
        )
    execution = ExecucaoConformidade(
        id=_dense_id("execution"),
        projeto_id=_dense_id("project"),
        execucoes_semanticas_ids=(_dense_id("semantic"),),
        revisao_regras_id=_dense_id("revision"),
        registro_regras_id=_dense_id("registry"),
        versao_regras="fixture-1",
        assinatura_regras="a" * 64,
        assinatura_sessao="b" * 64,
        versao_metodo="1",
        executada_em=datetime(2026, 8, 16, 12, tzinfo=UTC),
        alvos=(target,),
        fatos=tuple(facts),
        achados=tuple(findings),
        itens_documentais=(),
    )
    return projetar_callouts_conformidade(
        execution,
        evidencias=(),
        paginas=(page,),
        textos_apresentacao=presentation,
    )


def _assert_text_fits(viewer: PdfViewerWidget, callout: CalloutConformidade) -> None:
    graphics = viewer.view._callout_items[str(callout.id)]
    transformer = viewer._current_transformer
    assert transformer is not None
    box_width = graphics.caixa.rect().width()
    box_height = graphics.caixa.rect().height()
    width_points = float(callout.caixa_sugerida.largura) * float(transformer.pagina.width_points)
    pixels_per_point = box_width / width_points
    padding = max(2.0, 6.0 * pixels_per_point)
    assert graphics.texto.boundingRect().width() <= box_width - 2 * padding + 0.5
    assert graphics.texto.boundingRect().height() <= box_height - 2 * padding + 0.5


def _normalized_intersection_area(
    left: RetanguloCallout,
    right: RetanguloCallout,
) -> Decimal:
    width = max(
        Decimal(0),
        min(left.direita, right.direita) - max(left.esquerda, right.esquerda),
    )
    height = max(
        Decimal(0),
        min(left.base, right.base) - max(left.topo, right.topo),
    )
    return width * height


def _dense_id(value: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"callout-dense-render:{value}")


def _proposal(page_id: UUID) -> ReviewOverlayDto:
    proposal_id = ProposalId(uuid4())
    geometry = ReviewGeometryDto(
        page_id=PageId(page_id),
        kind=ReviewGeometryKind.POINT,
        points=(NormalizedPointDto(x="0.46", y="0.56"),),
    )
    return ReviewOverlayDto(
        proposal_id=proposal_id,
        geometry=geometry,
        link_geometry=geometry,
        label="Poste",
        category=ElementCategory.POLE,
        situation=ElementSituation.INSTALL,
        review_state=ReviewState.PENDING,
        confidence="0.9",
    )


def _assert_anchor_aligned(viewer: PdfViewerWidget, callout: CalloutConformidade) -> None:
    transformer = viewer._current_transformer
    assert transformer is not None
    graphics = viewer.view._callout_items[str(callout.id)]
    assert len(graphics.linhas) == len(callout.ancoras)
    for line, anchor in zip(graphics.linhas, callout.ancoras, strict=True):
        end = line.path().elementAt(1)
        expected = transformer.normalizado_para_pixel(anchor.ponto)
        assert end.x == pytest.approx(expected.x)
        assert end.y == pytest.approx(expected.y)
        normalized = transformer.pixel_para_normalizado(expected)
        assert float(normalized.x) == pytest.approx(float(anchor.ponto.x))
        assert float(normalized.y) == pytest.approx(float(anchor.ponto.y))
