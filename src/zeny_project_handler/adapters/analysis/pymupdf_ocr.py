# mypy: disable-error-code="no-untyped-call"
"""Fronteira de rasterização usada exclusivamente pelo OCR condicional."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pymupdf

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    GeometriaNormalizada,
    MotorOcrPort,
    PaginaRasterOcr,
    SolicitacaoAnaliseDocumento,
)

from .pymupdf_support import _extras, _normalized_point


def _conditional_ocr(
    page: Any,
    page_number: int,
    request: SolicitacaoAnaliseDocumento,
    ocr_engine: MotorOcrPort | None,
    native_characters: int,
    image_coverage: Decimal,
    vector_count: int,
    image_candidates: tuple[CandidatoEvidenciaDocumento, ...],
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    config = request.configuracao
    if not config.habilitar_ocr_condicional:
        return (), ()
    has_enough_native_text = native_characters >= config.minimo_caracteres_texto_nativo
    has_relevant_raster = image_coverage >= config.area_imagem_minima_para_ocr
    has_dense_vector_content = vector_count >= config.minimo_vetores_para_ocr
    use_full_page = not has_enough_native_text or has_relevant_raster or has_dense_vector_content
    regional_images = tuple(
        item
        for item in image_candidates
        if _candidate_area(item) >= config.area_imagem_regional_minima_para_ocr
        and _has_regional_ocr_resolution(item)
    )
    if not use_full_page and not regional_images:
        return (), ()
    if ocr_engine is None:
        return (), (
            DiagnosticoAnalise(
                codigo="analise.ocr_indisponivel",
                mensagem=(
                    "A página pode conter texto rasterizado, mas nenhum motor OCR está configurado."
                ),
                extrator="ocr",
                pagina_numero=page_number,
            ),
        )
    try:
        if use_full_page:
            return _extract_ocr(page, page_number, ocr_engine, config.dpi_ocr), ()
        return (
            tuple(
                candidate
                for index, image in enumerate(regional_images)
                for candidate in _extract_ocr_region(
                    page,
                    page_number,
                    ocr_engine,
                    config.dpi_ocr,
                    bounds=_candidate_bounds(image),
                    stable_suffix=f"imagem:{index}",
                )
            ),
            (),
        )
    except Exception:
        return (), (
            DiagnosticoAnalise(
                codigo="analise.ocr_falhou",
                mensagem=(
                    "O extrator de ocr falhou nesta página; os demais resultados foram mantidos."
                ),
                extrator="ocr",
                pagina_numero=page_number,
            ),
        )


def _extract_ocr(
    page: Any, page_number: int, engine: MotorOcrPort, dpi: int
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    return _extract_ocr_region(
        page,
        page_number,
        engine,
        dpi,
        bounds=(Decimal(0), Decimal(0), Decimal(1), Decimal(1)),
        stable_suffix="pagina",
    )


def _extract_ocr_region(
    page: Any,
    page_number: int,
    engine: MotorOcrPort,
    dpi: int,
    *,
    bounds: tuple[Decimal, Decimal, Decimal, Decimal],
    stable_suffix: str,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    left, top, right, bottom = bounds
    page_rect = page.rect
    clip = pymupdf.Rect(
        page_rect.x0 + float(left) * page_rect.width,
        page_rect.y0 + float(top) * page_rect.height,
        page_rect.x0 + float(right) * page_rect.width,
        page_rect.y0 + float(bottom) * page_rect.height,
    )
    pixmap = page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csRGB,
        alpha=False,
        annots=True,
        clip=clip,
    )
    raster = PaginaRasterOcr(
        pagina_numero=page_number,
        largura_pixels=pixmap.width,
        altura_pixels=pixmap.height,
        stride=pixmap.stride,
        dados_rgb=bytes(pixmap.samples),
        dpi=dpi,
    )
    candidates = []
    for index, item in enumerate(engine.reconhecer(raster)):
        x0, y0, x1, y1 = item.caixa_normalizada
        width = right - left
        height = bottom - top
        geometry = GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(
                _normalized_point(
                    float(left + Decimal(str(x0)) * width),
                    float(top + Decimal(str(y0)) * height),
                ),
                _normalized_point(
                    float(left + Decimal(str(x1)) * width),
                    float(top + Decimal(str(y1)) * height),
                ),
            ),
        )
        confidence = Decimal(str(item.confianca)) if item.confianca is not None else None
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=(
                    f"p{page_number}:ocr:{engine.nome}:{engine.versao}:{stable_suffix}:{index}"
                ),
                pagina_numero=page_number,
                tipo=TipoEvidencia.OCR,
                geometria=geometry,
                origem_pdf=OrigemObjetoPdf(),
                conteudo_bruto=item.texto,
                atributos_extraidos=_extras(
                    motor_ocr=engine.nome,
                    versao_motor_ocr=engine.versao,
                    confianca=confidence,
                    dpi=dpi,
                    recorte_normalizado=",".join(map(str, bounds)),
                ),
            )
        )
    return tuple(candidates)


def _candidate_bounds(
    candidate: CandidatoEvidenciaDocumento,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x_values = tuple(point.x for point in candidate.geometria.pontos)
    y_values = tuple(point.y for point in candidate.geometria.pontos)
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _candidate_area(candidate: CandidatoEvidenciaDocumento) -> Decimal:
    left, top, right, bottom = _candidate_bounds(candidate)
    return (right - left) * (bottom - top)


def _has_regional_ocr_resolution(candidate: CandidatoEvidenciaDocumento) -> bool:
    attributes = dict(candidate.atributos_extraidos)
    width = int(attributes.get("largura_pixels") or 0)
    height = int(attributes.get("altura_pixels") or 0)
    return min(width, height) >= 16 and width * height >= 4096
