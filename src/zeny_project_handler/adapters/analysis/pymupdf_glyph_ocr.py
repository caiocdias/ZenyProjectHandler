# mypy: disable-error-code="no-untyped-call"
"""OCR limitado de contornos com proveniência e transformação inversa por ocorrência."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from math import atan2, degrees
from typing import Any

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, OrigemObjetoPdf
from zeny_project_handler.domain.enums import TipoEvidencia, TipoGeometria
from zeny_project_handler.ports.analysis import (
    CandidatoEvidenciaDocumento,
    GeometriaNormalizada,
    MotorOcrGlifosPort,
    MotorOcrPort,
    PaginaRasterOcr,
    TrechoTextoOcr,
)

from .pymupdf_glyph_consensus import GlyphConsensus
from .pymupdf_glyphs import (
    MAXIMUM_GLYPH_GROUPS,
    MAXIMUM_GLYPH_PIXELS,
    GlyphRegion,
    glyph_groups,
    glyph_region,
)
from .pymupdf_ocr_batch import MAXIMUM_BATCH_REGIONS, pack_ocr_rows
from .pymupdf_support import _extras, _normalized_point

MAXIMUM_GLYPH_RETRIES = 24


@dataclass(frozen=True)
class _Reading:
    raster: PaginaRasterOcr
    items: tuple[TrechoTextoOcr, ...]
    raw_items: tuple[TrechoTextoOcr, ...] = ()

    @property
    def confidence(self) -> float:
        return min((item.confianca or 0 for item in self.items), default=0)


def _recognize(engine: MotorOcrPort, raster: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
    if isinstance(engine, MotorOcrGlifosPort):
        return engine.reconhecer_glifos(raster)
    return engine.reconhecer(raster)


def _geometry(page: Any, region: GlyphRegion, reading: _Reading, item: TrechoTextoOcr) -> Any:
    raster = reading.raster
    x0, y0, _, _ = region.bounds
    left, top, right, bottom = item.caixa_normalizada
    scale = raster.dpi / 72
    points = []
    for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
        point = (
            region.point(
                x0 + (x * raster.largura_pixels - 15) / scale,
                y0 + (y * raster.altura_pixels - 15) / scale,
            )
            * page.rotation_matrix
        )
        points.append(_normalized_point(point.x / page.rect.width, point.y / page.rect.height))
    return GeometriaNormalizada(tipo=TipoGeometria.POLIGONO, pontos=tuple(points))


def _candidates(
    page: Any,
    number: int,
    index: int,
    region: GlyphRegion,
    reading: _Reading,
) -> tuple[CandidatoEvidenciaDocumento, ...]:
    return tuple(
        CandidatoEvidenciaDocumento(
            chave_estavel=f"p{number}:ocr-glifos:{index}:{item.caixa_normalizada}:{item.texto}",
            pagina_numero=number,
            tipo=TipoEvidencia.OCR,
            geometria=_geometry(page, region, reading, item),
            origem_pdf=OrigemObjetoPdf(),
            conteudo_bruto=item.texto,
            atributos_extraidos=_extras(
                motor_ocr="tesseract-contornos-vetoriais",
                confianca=Decimal(str(item.confianca)) if item.confianca is not None else None,
                dpi=reading.raster.dpi,
                rotacao_original_graus=Decimal(str(round(degrees(atan2(*region.axis[::-1])), 3))),
                pre_processamento="contornos_originais_sem_tracos_sobrepostos",
                indice_recorte=index,
                quantidade_glifos=len(region.paths),
                texto_ocr_original=reading.raw_items[0].texto if reading.raw_items else None,
                concordancia_contornos=bool(reading.raw_items),
            ),
        )
        for item in reading.items
        if item.texto.strip()
    )


def _regions(page: Any, dpi: int) -> tuple[list[GlyphRegion], int]:
    regions: list[GlyphRegion] = []
    pixels = skipped = 0
    for group in glyph_groups(page):
        if len(group) > 16:
            continue
        region = glyph_region(group)
        if region is None:
            continue
        width, height = region.dimensions(dpi)
        if len(regions) >= MAXIMUM_GLYPH_GROUPS or pixels + width * height > MAXIMUM_GLYPH_PIXELS:
            skipped += 1
            continue
        pixels += width * height
        regions.append(region)
    return regions, skipped


def _read_batches(
    regions: list[GlyphRegion],
    number: int,
    engine: MotorOcrPort,
    dpi: int,
    readings: dict[int, _Reading],
) -> None:
    # Aproximar larguras reduz pixels brancos sem reamostrar os caracteres.
    # Os índices originais continuam sendo a identidade e a geometria dos recortes.
    ordered = sorted(range(len(regions)), key=lambda i: regions[i].dimensions(dpi)[0])
    start = 0
    while start < len(ordered):
        indices = ordered[start : start + MAXIMUM_BATCH_REGIONS]
        rasters = tuple(regions[index].render(number, dpi) for index in indices)
        # Glifos já têm 15 px de margem própria; não multiplicar faixas vazias pelo DPI.
        batch = pack_ocr_rows(rasters, gap_pixels=20)
        if batch is None:
            raise ValueError("Recorte vetorial excedeu orçamento do lote")
        items: dict[int, list[TrechoTextoOcr]] = {}
        for item in _recognize(engine, batch.raster):
            located = batch.locate(item)
            if located is not None:
                index, local = located
                items.setdefault(index, []).append(local)
        for index in range(len(batch.boxes)):
            readings[indices[index]] = _Reading(rasters[index], tuple(items.get(index, ())))
        # O limite de pixels pode consumir menos que o limite de linhas.
        start += len(batch.boxes)


def _retry_weak(
    regions: list[GlyphRegion],
    number: int,
    engine: MotorOcrPort,
    dpi: int,
    readings: dict[int, _Reading],
) -> None:
    weak = sorted(
        (
            i
            for i, r in readings.items()
            if len(regions[i].paths) <= 16 and r.confidence < 0.75 and not r.raw_items
        ),
        key=lambda i: (readings[i].confidence, i),
    )
    for index in weak[:MAXIMUM_GLYPH_RETRIES]:
        for resolution in dict.fromkeys((dpi, min(dpi, 1200))):
            raster = regions[index].render(number, resolution)
            reading = _Reading(raster, _recognize(engine, raster))
            if reading.confidence > readings[index].confidence:
                readings[index] = reading
            if readings[index].confidence >= 0.90:
                break


def _apply_consensus(regions: list[GlyphRegion], readings: dict[int, _Reading]) -> None:
    atlas = GlyphConsensus()
    for index, reading in readings.items():
        if len(reading.items) == 1 and reading.confidence >= 0.85:
            atlas.add(index, regions[index], reading.items[0].texto)
    for index, reading in tuple(readings.items()):
        if len(reading.items) != 1:
            continue
        item = reading.items[0]
        if len(item.texto.replace(" ", "")) != len(regions[index].paths):
            continue
        chars = list(item.texto)
        offset = 0
        for position, char in enumerate(chars):
            if char == " ":
                continue
            if (
                char.isalnum()
                and (agreed := atlas.recognize(index, regions[index], offset))
                and (char.isdigit() or agreed.isdigit())
            ):
                chars[position] = agreed
            offset += 1
        text = "".join(chars)
        if text != item.texto:
            readings[index] = replace(
                reading,
                items=(replace(item, texto=text),),
                raw_items=reading.items,
            )


def extract_vector_glyphs(
    page: Any,
    number: int,
    engine: MotorOcrPort,
    dpi: int,
) -> tuple[tuple[CandidatoEvidenciaDocumento, ...], tuple[DiagnosticoAnalise, ...]]:
    readings: dict[int, _Reading] = {}
    regions: list[GlyphRegion] = []
    skipped = 0
    diagnostics: list[DiagnosticoAnalise] = []
    try:
        regions, skipped = _regions(page, dpi)
        _read_batches(regions, number, engine, dpi, readings)
        _apply_consensus(regions, readings)
        _retry_weak(regions, number, engine, dpi, readings)
    except Exception:
        diagnostics.append(
            DiagnosticoAnalise(
                codigo="analise.ocr_glifos_falhou",
                mensagem="OCR de contornos interrompido; recortes já concluídos foram preservados.",
                extrator="ocr-glifos",
                pagina_numero=number,
            )
        )
    if skipped:
        diagnostics.append(
            DiagnosticoAnalise(
                codigo="analise.ocr_cobertura_parcial",
                mensagem=f"{skipped} grupos de contornos excederam o orçamento de OCR localizado.",
                extrator="ocr-glifos",
                pagina_numero=number,
            )
        )
    candidates = tuple(
        candidate
        for index, reading in sorted(readings.items())
        for candidate in _candidates(page, number, index, regions[index], reading)
    )
    return candidates, tuple(diagnostics)
