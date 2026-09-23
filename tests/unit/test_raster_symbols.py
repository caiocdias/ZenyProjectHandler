# mypy: disable-error-code="no-untyped-call"
"""Author-owned raster controls for the opt-in E08 detector.

The synthetic PDF contains an embedded page image, not drawing primitives. Its
reference coordinates come from this fixture and never enter the detector.
"""

from __future__ import annotations

import hashlib
import io
import random
from decimal import Decimal
from typing import Any

import pymupdf
import pytest
from PIL import Image, ImageDraw
from scripts.symbol_benchmark_runner import _raster_prediction

from zeny_project_handler.adapters.analysis.legacy_symbols import observar_simbolos_legados
from zeny_project_handler.adapters.analysis.raster_symbols import (
    ConfiguracaoDetectorRaster,
    TemplateRasterVerificado,
    carregar_templates_raster,
    observar_simbolos_raster,
)
from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import ObservacaoSimbolo, ResultadoMetodoSimbolos

_SOURCE_HASH = "a" * 64
_PAGE_SIZE = (512, 256)


def _png(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _ground_image(*, fourth_bar: bool = False) -> Image.Image:
    """Simple synthetic grounding motif, not a claim about an E01 variant."""
    image = Image.new("L", (64, 48), 255)
    draw = ImageDraw.Draw(image)
    draw.line((5, 24, 49, 24), fill=0, width=2)
    for x, half_height in ((23, 13), (31, 9), (39, 6)):
        draw.line((x, 24 - half_height, x, 24 + half_height), fill=0, width=2)
    if fourth_bar:
        draw.line((47, 19, 47, 29), fill=0, width=2)
    return image


def _template(*, fourth_bar: bool = False) -> TemplateRasterVerificado:
    png = _png(_ground_image(fourth_bar=fourth_bar))
    return TemplateRasterVerificado(
        id="synthetic-four-bars" if fourth_bar else "synthetic-three-bars",
        classe="PARA_RAIOS_MT" if fourth_bar else "ATERRAMENTO",
        fonte_referencia="fixture-autoral-e08",
        dados_png=png,
        sha256=hashlib.sha256(png).hexdigest(),
    )


def _page_image(
    placements: tuple[tuple[int, int, int, float], ...] = (),
    *,
    noise: int = 0,
) -> Image.Image:
    image = Image.new("L", _PAGE_SIZE, 255)
    for x, y, rotation, scale in placements:
        symbol = _ground_image()
        if scale != 1:
            symbol = symbol.resize(
                (round(symbol.width * scale), round(symbol.height * scale)),
                Image.Resampling.NEAREST,
            )
        if rotation:
            symbol = symbol.rotate(rotation, expand=True)
        image.paste(symbol, (x, y))
    if noise:
        rng = random.Random(8108)
        for _ in range(noise):
            image.putpixel((rng.randrange(image.width), rng.randrange(image.height)), 0)
    return image


def _raster_page(document: pymupdf.Document, image: Image.Image) -> pymupdf.Page:
    page = document.new_page(width=_PAGE_SIZE[0] / 2, height=_PAGE_SIZE[1] / 2)
    page.insert_image(page.rect, stream=_png(image))
    return page


def _e02_two_class_raster() -> Image.Image:
    """Draw two author-owned E02 motifs, then discard all vectors before detection."""
    with pymupdf.open() as source:
        page = source.new_page(width=_PAGE_SIZE[0] / 2, height=_PAGE_SIZE[1] / 2)
        for x, count in ((50, 3), (150, 4)):
            page.draw_line((x, 50), (x + 15, 50), color=(0, 0, 0), width=0.5)
            for index, length in enumerate((10.0, 7.0, 4.0, 7.0)[:count]):
                bar_x = x + 15 + index * 4
                page.draw_line(
                    (bar_x, 50 - length / 2),
                    (bar_x, 50 + length / 2),
                    color=(0, 0, 0),
                    width=0.5,
                )
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples).convert("L")


def _detect(page: pymupdf.Page, **configuration: Any) -> tuple[ResultadoMetodoSimbolos, ...]:
    return observar_simbolos_raster(
        page,
        documento_id="synthetic-e08",
        documento_sha256=_SOURCE_HASH,
        pagina_numero=1,
        templates=(_template(),),
        configuracao=ConfiguracaoDetectorRaster(**configuration),
    )


def _bbox(observation: ObservacaoSimbolo) -> tuple[float, float, float, float]:
    points = observation.geometria.pontos_originais
    return (
        float(min(point[0] for point in points)),
        float(min(point[1] for point in points)),
        float(max(point[0] for point in points)),
        float(max(point[1] for point in points)),
    )


def test_raster_only_pdf_recovers_symbol_that_vector_legacy_misses() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((204, 92, 0, 1),)))
        assert not page.get_drawings()
        legacy = observar_simbolos_legados(
            page, documento_id="synthetic-e08", documento_sha256=_SOURCE_HASH, pagina_numero=1
        )
        raster = _detect(page, tile_pixels=160, sobreposicao_pixels=80)
        alternate_dpi = _detect(page, dpi=180, tile_pixels=160, sobreposicao_pixels=80)

    assert legacy.observacoes == ()
    matches = raster[0].observacoes
    assert len(matches) == 1
    assert matches[0].alternativas[0].classe == "ATERRAMENTO"
    assert matches[0].raster_sha256 is not None
    assert matches[0].template == "synthetic-three-bars"
    assert matches[0].score_bruto is not None
    assert isinstance(matches[0].score_bruto, Decimal)
    assert raster[0].perfil.familia != legacy.perfil.familia
    assert raster[0].perfil.assinatura() != alternate_dpi[0].perfil.assinatura()
    assert raster[0].perfil.possui_origem_correlacionada(alternate_dpi[0].perfil)
    assert not raster[0].coberturas[0].estado.comprova_ausencia
    for actual, expected in zip(_bbox(matches[0]), (102, 46, 134, 70), strict=True):
        assert abs(actual - expected) <= 2


def test_tile_boundary_preserves_page_box_and_one_candidate() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((110, 80, 0, 1),)))
        result = _detect(page, tile_pixels=128, sobreposicao_pixels=96)

    assert len(result[0].observacoes) == 1
    observation = result[0].observacoes[0]
    attributes = dict(observation.atributos)
    tiles = attributes["tiles_concordantes"]
    assert isinstance(tiles, str)
    assert len(set(tiles.split(";"))) >= 2
    assert attributes["score_tipo"] == "similaridade_binaria_bruta_nao_probabilidade"
    for actual, expected in zip(_bbox(observation), (55, 40, 87, 64), strict=True):
        assert abs(actual - expected) <= 2
    x0, y0, x1, y1 = _bbox(observation)
    for normalized, original in zip(
        observation.geometria.pontos_normalizados,
        observation.geometria.pontos_originais,
        strict=True,
    ):
        matrix = observation.geometria.transformacao.normalizada_para_original
        recovered = (
            matrix[0] * normalized.x + matrix[2] * normalized.y + matrix[4],
            matrix[1] * normalized.x + matrix[3] * normalized.y + matrix[5],
        )
        assert abs(recovered[0] - original[0]) < Decimal("0.01")
        assert abs(recovered[1] - original[1]) < Decimal("0.01")
    assert x0 < x1 and y0 < y1


def test_rotated_raster_pdf_page_restores_unrotated_box() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((204, 92, 0, 1),)))
        page.set_rotation(90)
        assert not page.get_drawings()
        assert tuple(page.rect) == (0, 0, 128, 256)
        result = _detect(page, tile_pixels=160, sobreposicao_pixels=80)

    assert len(result[0].observacoes) == 1
    geometry = result[0].observacoes[0].geometria
    # Input image is in the unrotated 256 x 128 pt PDF frame.
    for actual, expected in zip(_bbox(result[0].observacoes[0]), (102, 46, 134, 70), strict=True):
        assert abs(actual - expected) <= 2
    # A clockwise page rotation maps (x, y) to (128-y, x): visual box
    # (58, 102)-(82, 134) in the 128 x 256 pt rotated page frame.
    normalized = geometry.pontos_normalizados
    visual_x = [float(point.x) * 128 for point in normalized]
    visual_y = [float(point.y) * 256 for point in normalized]
    for actual, expected in zip(
        (min(visual_x), min(visual_y), max(visual_x), max(visual_y)),
        (58, 102, 82, 134),
        strict=True,
    ):
        assert abs(actual - expected) <= 2
    matrix = geometry.transformacao.normalizada_para_original
    for point, original in zip(
        geometry.pontos_normalizados, geometry.pontos_originais, strict=True
    ):
        restored = (
            matrix[0] * point.x + matrix[2] * point.y + matrix[4],
            matrix[1] * point.x + matrix[3] * point.y + matrix[5],
        )
        assert abs(restored[0] - original[0]) < Decimal("0.01")
        assert abs(restored[1] - original[1]) < Decimal("0.01")


@pytest.mark.parametrize("rotation,scale", [(90, 1), (180, 1), (0, 1.5)])
def test_rotation_and_scale_remain_one_correlated_method(rotation: int, scale: float) -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((206, 82, rotation, scale),)))
        result = _detect(
            page,
            tile_pixels=192,
            sobreposicao_pixels=96,
            escalas=(1.0, 1.5),
            rotacoes=(0, 90, 180, 270),
        )
    assert len(result[0].observacoes) == 1
    assert {item.metodo_assinatura for item in result[0].observacoes} == {
        result[0].perfil.assinatura()
    }
    assert len(result) == 2
    assert result[0].perfil.possui_origem_correlacionada(result[1].perfil)


def test_vector_and_raster_exclusives_are_both_retained_on_mixed_page() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((204, 92, 0, 1),)))
        page.draw_line((25, 20), (40, 20), color=(0, 0, 0), width=0.5)
        for index, height in enumerate((5, 3.5, 2)):
            x = 40 + index * 4
            page.draw_line((x, 20 - height), (x, 20 + height), color=(0, 0, 0), width=0.5)
        legacy = observar_simbolos_legados(
            page, documento_id="synthetic-e08", documento_sha256=_SOURCE_HASH, pagina_numero=1
        )
        raster = _detect(page, tile_pixels=160, sobreposicao_pixels=80)
    assert legacy.observacoes
    assert any(abs(_bbox(item)[0] - 102) <= 2 for item in raster[0].observacoes)
    union = {item.id for item in (*legacy.observacoes, *raster[0].observacoes)}
    assert len(union) >= 2


@pytest.mark.parametrize("noise", [0, 700])
def test_blank_and_sparse_noise_do_not_create_symbols(noise: int) -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(noise=noise))
        result = _detect(page, tile_pixels=192, sobreposicao_pixels=96)
    assert result[0].observacoes == ()


def test_one_missing_foreground_anchor_keeps_high_similarity_symbol_detectable() -> None:
    # This pixel is on the long bar of the author-owned 64x48 template. Losing
    # one printed pixel must not erase a symbol whose raw similarity remains
    # above the detector threshold; noise on the symbol differs from background noise.
    symbol = _ground_image()
    assert symbol.getpixel((45, 24)) == 0
    dark_pixels = sum(value < 220 for value in symbol.tobytes())
    assert (1 - 1 / dark_pixels + 1) / 2 > 0.88
    image = _page_image(((204, 92, 0, 1),))
    image.putpixel((249, 116), 255)
    with pymupdf.open() as document:
        page = _raster_page(document, image)
        assert not page.get_drawings()
        result = _detect(page, tile_pixels=160, sobreposicao_pixels=80, rotacoes=(0,))
    assert len(result[0].observacoes) == 1
    for actual, expected in zip(_bbox(result[0].observacoes[0]), (102, 46, 134, 70), strict=True):
        assert abs(actual - expected) <= 2


def test_dense_black_raster_page_completes_without_spurious_candidates() -> None:
    # Every pixel is dark, so hundreds of thousands of anchor alignments are possible
    # but none can pass the template's light-background checks. The normal
    # candidate and memory budgets must suffice for this dense negative page.
    image = Image.new("L", (768, 768), 0)
    with pymupdf.open() as document:
        page = document.new_page(width=384, height=384)
        page.insert_image(page.rect, stream=_png(image))
        assert not page.get_drawings()
        result = observar_simbolos_raster(
            page,
            documento_id="synthetic-e08-dense-negative",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
            templates=(_template(),),
            configuracao=ConfiguracaoDetectorRaster(rotacoes=(0,)),
        )
    assert result[0].observacoes == ()
    assert result[0].coberturas[0].estado is EstadoMetodoSimbolos.NAO_DETECCAO
    assert result[0].completo


def test_similar_templates_preserve_competing_evidence_without_extra_votes() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((204, 92, 0, 1),)))
        result = observar_simbolos_raster(
            page,
            documento_id="synthetic-e08",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
            templates=(_template(), _template(fourth_bar=True)),
            configuracao=ConfiguracaoDetectorRaster(tile_pixels=160, sobreposicao_pixels=80),
        )
    assert len(result[0].observacoes) == 1
    alternatives = result[0].observacoes[0].alternativas
    assert tuple(item.classe for item in alternatives) == ("ATERRAMENTO", "PARA_RAIOS_MT")
    assert alternatives[0].score_bruto is not None
    assert alternatives[1].score_bruto is not None
    assert alternatives[0].score_bruto > alternatives[1].score_bruto
    assert result[0].perfil.possui_origem_correlacionada(result[1].perfil)
    projected = _raster_prediction(result[0].observacoes[0], "synthetic-e08", "raster-template")
    assert projected["class_id"] == "ATERRAMENTO"
    assert [item["class_id"] for item in projected["provenance"]["alternatives"]] == [
        "ATERRAMENTO",
        "PARA_RAIOS_MT",
    ]
    assert all(
        item.score_bruto is None or item.score_bruto.is_finite() for item in result[0].observacoes
    )


def test_two_similar_symbols_in_raster_pdf_keep_distinct_correct_occurrences() -> None:
    image = _page_image(((100, 90, 0, 1),))
    image.paste(_ground_image(fourth_bar=True), (300, 90))
    with pymupdf.open() as document:
        page = _raster_page(document, image)
        assert not page.get_drawings()
        legacy = observar_simbolos_legados(
            page, documento_id="synthetic-e08", documento_sha256=_SOURCE_HASH, pagina_numero=1
        )
        result = observar_simbolos_raster(
            page,
            documento_id="synthetic-e08",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
            templates=(_template(), _template(fourth_bar=True)),
            configuracao=ConfiguracaoDetectorRaster(tile_pixels=160, sobreposicao_pixels=80),
        )
    assert legacy.observacoes == ()
    matches = sorted(result[0].observacoes, key=lambda item: _bbox(item)[0])
    assert len(matches) == 2
    assert tuple(item.alternativas[0].classe for item in matches) == (
        "ATERRAMENTO",
        "PARA_RAIOS_MT",
    )
    assert all(
        {alternative.classe for alternative in item.alternativas}
        == {"ATERRAMENTO", "PARA_RAIOS_MT"}
        for item in matches
    )
    for item, expected_x in zip(matches, (50, 150), strict=True):
        x0, y0, x1, y1 = _bbox(item)
        assert abs(x0 - expected_x) <= 2
        assert abs(y0 - 45) <= 2
        assert abs(x1 - (expected_x + 32)) <= 2
        assert abs(y1 - 69) <= 2


def test_default_e02_templates_distinguish_grounding_from_mt_on_raster_page() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _e02_two_class_raster())
        assert not page.get_drawings()
        result = observar_simbolos_raster(
            page,
            documento_id="synthetic-e08-e02",
            documento_sha256=_SOURCE_HASH,
            pagina_numero=1,
            templates=carregar_templates_raster(),
            configuracao=ConfiguracaoDetectorRaster(tile_pixels=160, sobreposicao_pixels=80),
        )
    matches = sorted(result[0].observacoes, key=lambda item: _bbox(item)[0])
    assert len(matches) == 2
    assert tuple(item.alternativas[0].classe for item in matches) == (
        "ATERRAMENTO",
        "PARA_RAIOS_MT",
    )
    assert all(
        {alternative.classe for alternative in item.alternativas}
        == {"ATERRAMENTO", "PARA_RAIOS_MT"}
        for item in matches
    )
    for item, expected_x in zip(matches, (48, 148), strict=True):
        assert abs(_bbox(item)[0] - expected_x) <= 2


def test_candidate_saturation_reports_incomplete_coverage() -> None:
    placements = tuple((x, y, 0, 1) for y in (20, 100, 180) for x in (20, 120, 220, 320, 420))
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(placements))
        result = _detect(page, tile_pixels=160, sobreposicao_pixels=80, limite_candidatos=2)
    assert len(result[0].observacoes) <= 2
    assert any(
        coverage.estado not in {EstadoMetodoSimbolos.CONCLUIDO, EstadoMetodoSimbolos.NAO_DETECCAO}
        and coverage.motivo
        for coverage in result[0].coberturas
    )


def test_tight_memory_budget_reports_failure_without_false_completion() -> None:
    with pymupdf.open() as document:
        page = _raster_page(document, _page_image(((204, 92, 0, 1),)))
        result = _detect(page, tile_pixels=160, sobreposicao_pixels=80, limite_bytes=1024)
    assert not result[0].completo
    assert all(item.estado is not EstadoMetodoSimbolos.CONCLUIDO for item in result[0].coberturas)
    assert any(item.motivo for item in result[0].coberturas)
