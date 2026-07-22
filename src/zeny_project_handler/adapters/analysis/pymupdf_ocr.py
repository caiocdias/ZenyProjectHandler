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
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    config = request.configuracao
    if not config.habilitar_ocr_condicional:
        return (), ()
    has_enough_native_text = native_characters >= config.minimo_caracteres_texto_nativo
    has_relevant_raster = image_coverage >= config.area_imagem_minima_para_ocr
    has_dense_vector_content = vector_count >= config.minimo_vetores_para_ocr
    if has_enough_native_text and not has_relevant_raster and not has_dense_vector_content:
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
        return _extract_ocr(page, page_number, ocr_engine, config.dpi_ocr), ()
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
    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
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
        geometry = GeometriaNormalizada(
            tipo=TipoGeometria.CAIXA,
            pontos=(_normalized_point(x0, y0), _normalized_point(x1, y1)),
        )
        confidence = Decimal(str(item.confianca)) if item.confianca is not None else None
        candidates.append(
            CandidatoEvidenciaDocumento(
                chave_estavel=f"p{page_number}:ocr:{engine.nome}:{engine.versao}:{index}",
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
                ),
            )
        )
    return tuple(candidates)
