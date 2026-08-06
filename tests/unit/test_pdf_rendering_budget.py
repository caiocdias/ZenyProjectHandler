from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from tests.pdf_fixtures import (
    TEST_RENDER_BUDGET,
    create_clip_rotation_golden_pdf,
    create_feature_pdf,
    create_large_format_pdf,
)

from zeny_project_handler.adapters.pdf import (
    PdfPaginaInvalidaError,
    PyMuPdfReader,
    TransformadorCoordenadasPagina,
)
from zeny_project_handler.domain.values import PontoNormalizado
from zeny_project_handler.ports.pdf import OrcamentoRenderizacaoPdf, PaginaPdfRenderizada

LARGE_PREVIEW_BUDGET = OrcamentoRenderizacaoPdf(
    limite_pixels=120_000,
    limite_bytes=840_000,
)


@pytest.mark.parametrize(
    ("rotation", "expected_dimensions", "expected_colors"),
    [
        (0, (80, 60), ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))),
        (90, (60, 80), ((0, 0, 255), (255, 0, 0), (255, 255, 0), (0, 255, 0))),
        (180, (80, 60), ((255, 255, 0), (0, 0, 255), (0, 255, 0), (255, 0, 0))),
        (270, (60, 80), ((0, 255, 0), (255, 255, 0), (255, 0, 0), (0, 0, 255))),
    ],
)
def test_rotation_golden_preserves_pixels(
    tmp_path: Path,
    rotation: int,
    expected_dimensions: tuple[int, int],
    expected_colors: tuple[tuple[int, int, int], ...],
) -> None:
    source = create_clip_rotation_golden_pdf(tmp_path / f"rotation-{rotation}.pdf")

    rendered = PyMuPdfReader().renderizar_pagina(
        source,
        1,
        dpi=72,
        orcamento=TEST_RENDER_BUDGET,
        rotacao_adicional_graus=rotation,
    )

    assert (rendered.largura_pixels, rendered.altura_pixels) == expected_dimensions
    _assert_colors(_quadrant_colors(rendered), expected_colors)
    assert isinstance(rendered.dados_rgb, memoryview)
    assert len(rendered.dados_rgb) == rendered.stride * rendered.altura_pixels


@pytest.mark.parametrize(
    ("rotation", "expected_dimensions", "expected_origin", "first_color", "second_color"),
    [
        (0, (40, 60), (0, 0), (255, 0, 0), (0, 0, 255)),
        (90, (60, 40), (0, 0), (0, 0, 255), (255, 0, 0)),
        (180, (40, 60), (40, 0), (0, 0, 255), (255, 0, 0)),
        (270, (60, 40), (0, 40), (255, 0, 0), (0, 0, 255)),
    ],
)
def test_clip_golden_preserves_rotation_origin_and_normalized_alignment(
    tmp_path: Path,
    rotation: int,
    expected_dimensions: tuple[int, int],
    expected_origin: tuple[int, int],
    first_color: tuple[int, int, int],
    second_color: tuple[int, int, int],
) -> None:
    source = create_clip_rotation_golden_pdf(tmp_path / f"clip-{rotation}.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)

    rendered = reader.renderizar_pagina(
        source,
        1,
        dpi=72,
        orcamento=TEST_RENDER_BUDGET,
        rotacao_adicional_graus=rotation,
        recorte_normalizado=(0.0, 0.0, 0.5, 1.0),
    )

    assert (rendered.largura_pixels, rendered.altura_pixels) == expected_dimensions
    assert (rendered.plano.origem_x_pixels, rendered.plano.origem_y_pixels) == expected_origin
    _assert_colors(_axis_colors(rendered), (first_color, second_color))
    transformer = TransformadorCoordenadasPagina(
        inspection.paginas[0].pagina,
        dpi=rendered.dpi,
        largura_pixels=rendered.largura_pixels,
        altura_pixels=rendered.altura_pixels,
        largura_pagina_pixels=rendered.largura_pagina_pixels,
        altura_pagina_pixels=rendered.altura_pagina_pixels,
        origem_x_pixels=rendered.plano.origem_x_pixels,
        origem_y_pixels=rendered.plano.origem_y_pixels,
        rotacao_adicional_graus=rotation,
    )
    point = PontoNormalizado(Decimal("0.25"), Decimal("0.25"))

    assert transformer.pixel_para_normalizado(transformer.normalizado_para_pixel(point)) == point


@pytest.mark.parametrize(
    ("name", "width_points", "height_points", "minimum_requested_pixels"),
    [
        ("a0", 2384.0, 3370.0, 550_000_000),
        ("a1", 1684.0, 2384.0, 270_000_000),
    ],
)
def test_large_format_plan_and_preview_never_allocate_full_600_dpi_raster(
    tmp_path: Path,
    name: str,
    width_points: float,
    height_points: float,
    minimum_requested_pixels: int,
) -> None:
    source = create_large_format_pdf(
        tmp_path / f"{name}.pdf",
        width_points=width_points,
        height_points=height_points,
    )
    session = PyMuPdfReader().abrir_sessao(source)
    try:
        plan = session.planejar_renderizacao(
            1,
            dpi=600,
            orcamento=LARGE_PREVIEW_BUDGET,
        )
        preview = session.renderizar_pagina(
            1,
            dpi=600,
            orcamento=LARGE_PREVIEW_BUDGET,
        )
        detail = session.renderizar_pagina(
            1,
            dpi=600,
            orcamento=LARGE_PREVIEW_BUDGET,
            recorte_normalizado=(0.45, 0.45, 0.46, 0.46),
        )
    finally:
        session.fechar()

    requested_pixels = plan.largura_solicitada_pixels * plan.altura_solicitada_pixels
    assert requested_pixels >= minimum_requested_pixels
    assert plan.foi_reduzido
    assert plan.quantidade_pixels <= LARGE_PREVIEW_BUDGET.limite_pixels
    assert plan.bytes_pico_estimados <= LARGE_PREVIEW_BUDGET.limite_bytes
    assert preview.plano == plan
    assert len(preview.dados_rgb) == plan.bytes_rgb_estimados
    assert detail.dpi == 600
    assert detail.plano.quantidade_pixels <= LARGE_PREVIEW_BUDGET.limite_pixels
    assert detail.plano.bytes_pico_estimados <= LARGE_PREVIEW_BUDGET.limite_bytes


def test_intrinsic_rotation_and_cropbox_keep_budgeted_dimensions(tmp_path: Path) -> None:
    source = create_feature_pdf(tmp_path / "cropbox-rotation.pdf")
    reader = PyMuPdfReader()
    inspection = reader.inspecionar(source)
    page = inspection.paginas[1].pagina

    rendered = reader.renderizar_pagina(
        source,
        2,
        dpi=72,
        orcamento=TEST_RENDER_BUDGET,
        rotacao_adicional_graus=270,
    )

    assert page.media_box != page.crop_box
    assert page.rotacao_graus == 90
    assert (rendered.largura_pixels, rendered.altura_pixels) == (160, 80)


def test_budget_validates_limits_and_rejects_unrenderable_preview(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pixels"):
        OrcamentoRenderizacaoPdf(limite_pixels=0, limite_bytes=1)
    with pytest.raises(ValueError, match="bytes"):
        OrcamentoRenderizacaoPdf(limite_pixels=1, limite_bytes=0)

    source = create_large_format_pdf(
        tmp_path / "sem-orcamento.pdf",
        width_points=2384,
        height_points=3370,
    )
    with pytest.raises(PdfPaginaInvalidaError, match="orçamento"):
        PyMuPdfReader().planejar_renderizacao(
            source,
            1,
            dpi=600,
            orcamento=OrcamentoRenderizacaoPdf(limite_pixels=1, limite_bytes=7),
        )


@pytest.mark.parametrize(
    "budget",
    [
        OrcamentoRenderizacaoPdf(limite_pixels=100_000, limite_bytes=10_000_000),
        OrcamentoRenderizacaoPdf(limite_pixels=1_000_000, limite_bytes=350_000),
    ],
)
def test_pixel_and_byte_limits_are_enforced_independently(
    tmp_path: Path,
    budget: OrcamentoRenderizacaoPdf,
) -> None:
    source = create_clip_rotation_golden_pdf(tmp_path / "limites-independentes.pdf")

    rendered = PyMuPdfReader().renderizar_pagina(
        source,
        1,
        dpi=600,
        orcamento=budget,
    )

    assert rendered.plano.quantidade_pixels <= budget.limite_pixels
    assert rendered.plano.bytes_pico_estimados <= budget.limite_bytes


def test_visual_rendering_rejects_detail_above_600_dpi(tmp_path: Path) -> None:
    source = create_clip_rotation_golden_pdf(tmp_path / "teto-detalhe.pdf")

    with pytest.raises(PdfPaginaInvalidaError, match="600"):
        PyMuPdfReader().planejar_renderizacao(
            source,
            1,
            dpi=601,
            orcamento=TEST_RENDER_BUDGET,
        )


def _quadrant_colors(rendered: PaginaPdfRenderizada) -> tuple[tuple[int, int, int], ...]:
    width = rendered.largura_pixels
    height = rendered.altura_pixels
    return (
        _rgb_at(rendered, width // 4, height // 4),
        _rgb_at(rendered, width * 3 // 4, height // 4),
        _rgb_at(rendered, width // 4, height * 3 // 4),
        _rgb_at(rendered, width * 3 // 4, height * 3 // 4),
    )


def _axis_colors(
    rendered: PaginaPdfRenderizada,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    width = rendered.largura_pixels
    height = rendered.altura_pixels
    if width < height:
        return (
            _rgb_at(rendered, width // 2, height // 4),
            _rgb_at(rendered, width // 2, height * 3 // 4),
        )
    return (
        _rgb_at(rendered, width // 4, height // 2),
        _rgb_at(rendered, width * 3 // 4, height // 2),
    )


def _rgb_at(rendered: PaginaPdfRenderizada, x: int, y: int) -> tuple[int, int, int]:
    offset = y * rendered.stride + x * 3
    red, green, blue = rendered.dados_rgb[offset : offset + 3]
    return red, green, blue


def _assert_colors(
    actual: tuple[tuple[int, int, int], ...],
    expected: tuple[tuple[int, int, int], ...],
) -> None:
    for actual_color, expected_color in zip(actual, expected, strict=True):
        assert actual_color == pytest.approx(expected_color, abs=8)
