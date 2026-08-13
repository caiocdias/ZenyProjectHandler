from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot
from tests.pdf_fixtures import TEST_RENDER_BUDGET, create_callout_formats_pdf

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.compliance_callouts import (
    AncoraCallout,
    CalloutConformidade,
    OrigemAncoraCallout,
    RetanguloCallout,
)
from zeny_project_handler.domain.analysis import PropostaElemento
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, SituacaoProjeto
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf
from zeny_project_handler.ui.pdf_viewer import PdfViewerWidget

TILED_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=200_000,
    limite_bytes=1_400_000,
)


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
    page = viewer.inspecao.documento.paginas[0]
    callout = _callout(page.id, float(page.largura_pontos), float(page.altura_pontos), "primeiro")
    proposal = _proposal(page.id)

    viewer.definir_callouts_conformidade((callout,))
    viewer.definir_propostas_revisao((proposal,))

    graphics = viewer.view._callout_items[str(callout.id)]
    assert graphics.caixa.brush().color() == QColor("white")
    assert graphics.caixa.pen().color() == QColor("#c62828")
    assert graphics.texto.defaultTextColor() == QColor("#c62828")
    assert graphics.texto.toPlainText() == callout.texto
    assert len(graphics.linhas) == 2
    assert all(item.path().elementCount() == 6 for item in graphics.linhas)
    assert str(proposal.id) in viewer.view._review_items
    assert viewer.view._callout_layer is not None
    assert viewer.view._callout_layer.zValue() == 30
    assert viewer.view._review_items[str(proposal.id)].zValue() == 20


@pytest.mark.integration
def test_callout_anchor_survives_zoom_resize_rotation_tiles_and_page_changes(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "transformacoes-callout.pdf")
    viewer = _viewer(qtbot, dpi=600, budget=TILED_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    pages = viewer.inspecao.documento.paginas
    callouts = tuple(
        _callout(page.id, float(page.largura_pontos), float(page.altura_pontos), str(index))
        for index, page in enumerate(pages, start=1)
    )
    viewer.definir_callouts_conformidade(callouts)
    _assert_anchor_aligned(viewer, callouts[0])

    viewer.view.definir_zoom(0.1)
    graphics = viewer.view._callout_items[str(callouts[0].id)]
    assert graphics.texto.font().pixelSize() * viewer.view.zoom >= 7.0
    _assert_anchor_aligned(viewer, callouts[0])
    viewer.view.definir_zoom(4.0)
    qtbot.waitUntil(lambda: bool(viewer.view._tile_items), timeout=10_000)
    _assert_anchor_aligned(viewer, callouts[0])
    viewer.resize(1024, 720)
    qtbot.wait(20)
    _assert_anchor_aligned(viewer, callouts[0])

    for rotation in (90, 180, 270, 0):
        viewer._rotate_page()
        _wait_preview(qtbot, viewer, rotation=rotation)
        _assert_anchor_aligned(viewer, callouts[0])

    viewer.ir_para_folha(2)
    _wait_preview(qtbot, viewer, page=2)
    assert set(viewer.view._callout_items) == {str(callouts[1].id)}
    _assert_anchor_aligned(viewer, callouts[1])
    viewer.ir_para_folha(1)
    _wait_preview(qtbot, viewer, page=1)
    assert set(viewer.view._callout_items) == {str(callouts[0].id)}


@pytest.mark.integration
def test_synthetic_a4_a3_portrait_landscape_callout_renders_are_saved(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    source = create_callout_formats_pdf(tmp_path / "inspecao-visual-callouts.pdf")
    viewer = _viewer(qtbot, dpi=144, budget=TEST_RENDER_BUDGET)
    assert viewer.carregar_pdf(source)
    _wait_preview(qtbot, viewer)
    assert viewer.inspecao is not None
    pages = viewer.inspecao.documento.paginas
    callouts = tuple(
        _callout(page.id, float(page.largura_pontos), float(page.altura_pontos), str(index))
        for index, page in enumerate(pages, start=1)
    )
    viewer.definir_callouts_conformidade(callouts)

    renders: list[Path] = []
    for page_number, callout in enumerate(callouts, start=1):
        viewer.ir_para_folha(page_number)
        _wait_preview(qtbot, viewer, page=page_number)
        _assert_anchor_aligned(viewer, callout)
        output = tmp_path / f"callout-formato-{page_number}.png"
        assert viewer.view.grab().save(str(output), "PNG")
        assert output.stat().st_size > 10_000
        renders.append(output)

    assert len(renders) == 4


def _viewer(qtbot: QtBot, *, dpi: int, budget: OrcamentoRenderizacaoPdf) -> PdfViewerWidget:
    viewer = PdfViewerWidget(
        leitor=PyMuPdfReader(),
        dpi=dpi,
        orcamento=budget,
    )
    qtbot.addWidget(viewer)
    viewer.resize(900, 700)
    viewer.show()
    return viewer


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
            and viewer._current_preview.plano.pagina_numero == page
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


def _proposal(page_id: UUID) -> PropostaElemento:
    point = PontoNormalizado(Decimal("0.46"), Decimal("0.56"))
    return PropostaElemento(
        id=uuid4(),
        execucao_id=uuid4(),
        categoria=CategoriaElemento.POSTE,
        situacao_projeto=SituacaoProjeto.INSTALAR,
        estado_revisao=EstadoRevisao.PROPOSTA,
        evidencia_ids=(uuid4(),),
        geometria=GeometriaDocumento.ponto(page_id, point),
        confianca=Decimal("0.9"),
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
