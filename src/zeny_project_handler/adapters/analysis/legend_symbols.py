# mypy: disable-error-code="no-untyped-call"
"""Document-local legend exemplars and reviewable unknown symbol occurrences.

Legend text is a hypothesis about a visual exemplar, never a catalog identity.
The matcher receives no evaluator annotations or regions of interest. All state is
local to one invocation; no exemplar survives into another document or process.
"""

from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
from typing import Any

import pymupdf
from PIL import Image

from zeny_project_handler.domain.enums import EstadoMetodoSimbolos
from zeny_project_handler.domain.symbols import (
    AlternativaClasseSimbolo,
    CoberturaMetodoSimbolos,
    FonteObservacaoSimbolo,
    ObservacaoSimbolo,
    PerfilMetodoSimbolos,
    ResultadoMetodoSimbolos,
)
from zeny_project_handler.domain.values import PontoNormalizado

from .raster_symbols import _geometry, _iou, _positions, _search_template

Caixa = tuple[float, float, float, float]
_HEADING = re.compile(r"^(?:LEGENDA|SIMBOLOGIA|S[IÍ]MBOLOS?)\s*:?$", re.IGNORECASE)
_REVISION = re.compile(r"\bREV(?:ISAO|ISÃO|\.)?\b\s*[:.]?\s*([A-Z0-9_-]+)\b", re.IGNORECASE)
_VERSION = "e10-legend-documental-1"


@dataclass(frozen=True, slots=True, kw_only=True)
class LeituraLegenda:
    pagina_numero: int
    texto: str
    caixa: Caixa
    origem: str = "ocr"
    revisao: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracaoLegenda:
    dpi: int = 144
    tile_pixels: int = 768
    sobreposicao_pixels: int = 128
    largura_maxima_exemplar_pt: float = 88.0
    alcance_vertical_pt: float = 180.0
    limite_pares: int = 64
    limite_ocorrencias: int = 256
    limite_pixels_pagina: int = 8_000_000
    limite_tiles: int = 512

    def __post_init__(self) -> None:
        if not 72 <= self.dpi <= 300:
            raise ValueError("DPI de legenda fora do intervalo")
        if self.largura_maxima_exemplar_pt <= 8 or self.alcance_vertical_pt <= 8:
            raise ValueError("Janela de legenda inválida")
        if min(self.limite_pares, self.limite_ocorrencias, self.limite_pixels_pagina) < 1:
            raise ValueError("Limites de legenda devem ser positivos")
        if (
            not 128 <= self.tile_pixels <= 2048
            or not 0 <= self.sobreposicao_pixels < self.tile_pixels
        ):
            raise ValueError("Tile de legenda inválido")
        if self.limite_tiles < 1:
            raise ValueError("Limite de tiles deve ser positivo")


_DEFAULT_CONFIG = ConfiguracaoLegenda()


@dataclass(frozen=True, slots=True, kw_only=True)
class RegiaoLegenda:
    pagina_numero: int
    caixa: Caixa
    titulo: str
    origem: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ParLegenda:
    id: str
    pagina_numero: int
    caixa_exemplar: Caixa
    caixa_descricao: Caixa
    descricao: str
    origem: str
    revisao: str | None
    pareamento_incerto: bool
    template_sha256: str
    dados_png: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoLegendaDocumental:
    resultado: ResultadoMetodoSimbolos
    pares: tuple[ParLegenda, ...]
    regioes_legenda: tuple[RegiaoLegenda, ...]
    diagnosticos: tuple[str, ...]


def _overlap(first: Caixa, second: Caixa) -> bool:
    return (
        first[0] < second[2]
        and second[0] < first[2]
        and first[1] < second[3]
        and second[1] < first[3]
    )


def _native_readings(page: Any) -> tuple[LeituraLegenda, ...]:
    lines: dict[tuple[int, int], list[tuple[Any, ...]]] = {}
    for word in page.get_text("words"):
        lines.setdefault((int(word[5]), int(word[6])), []).append(word)
    readings = []
    for words in lines.values():
        words.sort(key=lambda word: word[0])
        readings.append(
            LeituraLegenda(
                pagina_numero=page.number + 1,
                texto=" ".join(str(word[4]) for word in words),
                caixa=(
                    min(word[0] for word in words),
                    min(word[1] for word in words),
                    max(word[2] for word in words),
                    max(word[3] for word in words),
                ),
                origem="texto-nativo",
            )
        )
    return tuple(readings)


def _exemplar(
    page: Any, text_box: Caixa, region: RegiaoLegenda, config: ConfiguracaoLegenda
) -> tuple[Caixa, bytes, str] | None:
    # Read the visual sample immediately to the left of the description. This
    # derives the region from the document layout, not benchmark reference ROIs.
    x1 = text_box[0] - 4
    x0 = max(region.caixa[0], x1 - config.largura_maxima_exemplar_pt)
    y0 = max(region.caixa[1], text_box[1] - 9)
    y1 = min(region.caixa[3], text_box[3] + 9)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    factor = config.dpi / 72
    clip = pymupdf.Rect(x0, y0, x1, y1)
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(factor, factor),
        clip=clip,
        colorspace=pymupdf.csRGB,
        alpha=False,
        annots=False,
    )
    with Image.frombytes("RGB", (pix.width, pix.height), pix.samples) as image:
        binary = image.convert("L").point(lambda value: 255 if value >= 220 else 0)
    # Ignore ruling touching the sample edges. It must not turn a table cell
    # itself into a template. Inset also avoids antialiased crop borders.
    data = binary.tobytes()
    ink = [
        (i % pix.width, i // pix.width)
        for i, value in enumerate(data)
        if value == 0
        and 2 <= i % pix.width < pix.width - 2
        and 2 <= i // pix.width < pix.height - 2
    ]
    if len(ink) < 8:
        return None
    left, top = min(x for x, _ in ink), min(y for _, y in ink)
    right, bottom = max(x for x, _ in ink) + 1, max(y for _, y in ink) + 1
    if right - left < 8 or bottom - top < 8:
        return None
    if (right - left) * (bottom - top) > 128 * 128:
        return None
    left, top = max(0, left - 10), max(0, top - 10)
    right, bottom = min(pix.width, right + 10), min(pix.height, bottom + 10)
    crop = binary.crop((left, top, right, bottom))
    density = crop.tobytes().count(0) / (crop.width * crop.height)
    if not 0.025 <= density <= 0.60:
        return None
    output = io.BytesIO()
    crop.save(output, format="PNG")
    box = (
        (pix.x + left) / factor,
        (pix.y + top) / factor,
        (pix.x + right) / factor,
        (pix.y + bottom) / factor,
    )
    content = output.getvalue()
    return box, content, sha256(content).hexdigest()


def _extract_pairs(
    document: Any, readings: tuple[LeituraLegenda, ...], config: ConfiguracaoLegenda
) -> tuple[tuple[ParLegenda, ...], tuple[RegiaoLegenda, ...], tuple[str, ...]]:
    pairs: list[ParLegenda] = []
    regions: list[RegiaoLegenda] = []
    diagnostics: list[str] = []
    for page in document:
        page_readings = tuple(item for item in readings if item.pagina_numero == page.number + 1)
        headings = tuple(item for item in page_readings if _HEADING.fullmatch(item.texto.strip()))
        for heading in headings:
            nearby_revisions = tuple(
                (item, match)
                for item in page_readings
                if item is not heading
                and abs(
                    (item.caixa[1] + item.caixa[3]) / 2 - (heading.caixa[1] + heading.caixa[3]) / 2
                )
                <= 18
                and (match := _REVISION.search(item.texto)) is not None
            )
            native_revision = (
                min(nearby_revisions, key=lambda pair: abs(pair[0].caixa[0] - heading.caixa[2]))[
                    1
                ].group(1)
                if nearby_revisions
                else None
            )
            region = RegiaoLegenda(
                pagina_numero=page.number + 1,
                caixa=(
                    max(0.0, heading.caixa[0] - 4),
                    max(0.0, heading.caixa[1] - 2),
                    min(float(page.rect.width), heading.caixa[0] + 260),
                    min(float(page.rect.height), heading.caixa[3] + config.alcance_vertical_pt),
                ),
                titulo=heading.texto,
                origem=heading.origem,
            )
            regions.append(region)
            lines = sorted(
                (
                    item
                    for item in page_readings
                    if item is not heading
                    and item.caixa[1] >= heading.caixa[3]
                    and item.caixa[1] < region.caixa[3]
                    and region.caixa[0] + 20 < item.caixa[0] < region.caixa[2]
                    and not _HEADING.fullmatch(item.texto.strip())
                    and not _REVISION.match(item.texto.strip())
                ),
                key=lambda item: (item.caixa[1], item.caixa[0]),
            )
            prior_bottom = heading.caixa[3]
            region_pairs: list[ParLegenda] = []
            for line in lines:
                if line.caixa[1] - prior_bottom > 40:
                    break
                prior_bottom = line.caixa[3]
                if len(pairs) >= config.limite_pares:
                    diagnostics.append("Limite de pares de legenda atingido")
                    return tuple(pairs), tuple(regions), tuple(diagnostics)
                sample = _exemplar(page, line.caixa, region, config)
                if sample is None:
                    continue
                box, image, digest = sample
                identity = sha256(
                    f"{page.number + 1}:{box}:{line.texto}:{line.origem}:{digest}".encode()
                ).hexdigest()
                pair = ParLegenda(
                    id=identity,
                    pagina_numero=page.number + 1,
                    caixa_exemplar=box,
                    caixa_descricao=line.caixa,
                    descricao=line.texto.strip(),
                    origem=line.origem,
                    revisao=line.revisao or heading.revisao or native_revision,
                    pareamento_incerto=(
                        line.origem != "texto-nativo" or heading.origem != "texto-nativo"
                    ),
                    template_sha256=digest,
                    dados_png=image,
                )
                pairs.append(pair)
                region_pairs.append(pair)
            if region_pairs:
                regions[-1] = replace(
                    region,
                    caixa=(
                        min(heading.caixa[0], *(pair.caixa_exemplar[0] for pair in region_pairs))
                        - 4,
                        heading.caixa[1] - 2,
                        max(heading.caixa[2], *(pair.caixa_descricao[2] for pair in region_pairs))
                        + 4,
                        max(pair.caixa_descricao[3] for pair in region_pairs) + 4,
                    ),
                )
    if len({pair.descricao for pair in pairs}) > 1:
        pairs = [replace(pair, pareamento_incerto=True) for pair in pairs]
    return tuple(pairs), tuple(regions), tuple(diagnostics)


def _embedded_repetitions(
    document: Any, regions: tuple[RegiaoLegenda, ...]
) -> dict[int, tuple[tuple[str, Caixa], ...]]:
    """Conservative exact-content unknown proposals from repeated small images."""
    by_digest: dict[str, set[tuple[int, Caixa]]] = {}
    for page in document:
        for image in page.get_images(full=True):
            xref = int(image[0])
            try:
                payload = document.extract_image(xref)["image"]
                if len(payload) > 500_000:
                    continue
                with Image.open(io.BytesIO(payload)) as source:
                    if not 8 <= source.width <= 128 or not 8 <= source.height <= 128:
                        continue
                    gray = source.convert("L")
                binary = gray.point(lambda value: 0 if value < 220 else 1).tobytes()
                density = binary.count(0) / len(binary)
                if not 0.025 <= density <= 0.60:
                    continue
                digest = sha256(payload).hexdigest()
                for rect in page.get_image_rects(xref):
                    box = (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
                    if not 8 <= box[2] - box[0] <= 80 or not 8 <= box[3] - box[1] <= 80:
                        continue
                    if any(
                        region.pagina_numero == page.number + 1 and _overlap(box, region.caixa)
                        for region in regions
                    ):
                        continue
                    by_digest.setdefault(digest, set()).add((page.number + 1, box))
            except (OSError, ValueError, KeyError):
                continue
    by_page: dict[int, list[tuple[str, Caixa]]] = {}
    for digest, occurrences in by_digest.items():
        if len(occurrences) < 2:
            continue
        for page_number, box in sorted(occurrences):
            by_page.setdefault(page_number, []).append((digest, box))
    return {page: tuple(items) for page, items in by_page.items()}


def observar_legenda_documental(
    document: Any,
    *,
    documento_id: str,
    documento_sha256: str,
    leituras_ocr: tuple[LeituraLegenda, ...] = (),
    configuracao: ConfiguracaoLegenda = _DEFAULT_CONFIG,
) -> ResultadoLegendaDocumental:
    """Find document-local legend pairs and their out-of-legend repetitions.

    The returned E03 result is additive. OCR absence or wrong descriptions cannot
    suppress candidates from other methods. Raw image score is not a probability.
    """
    all_readings = tuple(item for page in document for item in _native_readings(page)) + tuple(
        leituras_ocr
    )
    pairs, regions, raw_diagnostics = _extract_pairs(document, all_readings, configuracao)
    diagnostics = list(raw_diagnostics)
    repetitions = _embedded_repetitions(document, regions) if not pairs and not regions else {}
    ocr_signature = sha256(
        repr(
            tuple(
                (item.pagina_numero, item.texto, item.caixa, item.origem, item.revisao)
                for item in leituras_ocr
            )
        ).encode("utf-8")
    ).hexdigest()
    profile = PerfilMetodoSimbolos(
        metodo_id="document-local-legend",
        versao=_VERSION,
        familia="template-documental-local",
        dominio_aplicacao="Documento atual; ocorrências fora da legenda",
        classes_suportadas=(),
        camadas_suportadas=("base",),
        fontes_compartilhadas=("pymupdf:rgb-page:e10", "texto-nativo-ou-ocr:e10"),
        perfil_referencia=f"documento:{documento_id}:{documento_sha256}",
        parametros=(
            ("documento_id", documento_id),
            ("documento_sha256", documento_sha256),
            ("leituras_ocr_sha256", ocr_signature),
            ("dpi", configuracao.dpi),
            ("tile_pixels", configuracao.tile_pixels),
            ("sobreposicao_pixels", configuracao.sobreposicao_pixels),
            ("pares_sha256", ",".join(sorted(item.template_sha256 for item in pairs))),
            (
                "motivos_repetidos_sha256",
                ",".join(sorted({digest for items in repetitions.values() for digest, _ in items})),
            ),
            ("limite_pares", configuracao.limite_pares),
            ("limite_ocorrencias", configuracao.limite_ocorrencias),
            ("limite_tiles", configuracao.limite_tiles),
        ),
    )
    observations: list[ObservacaoSimbolo] = []
    coverages: list[CoberturaMetodoSimbolos] = []
    for page in document:
        page_number = page.number + 1
        source = FonteObservacaoSimbolo(
            documento_id=documento_id,
            documento_sha256=documento_sha256,
            pagina_numero=page_number,
            camada="base",
        )
        state = EstadoMetodoSimbolos.NAO_DETECCAO
        reason: str | None = None
        if pairs:
            factor = configuracao.dpi / 72
            variants = []
            for pair in pairs:
                with Image.open(io.BytesIO(pair.dados_png)) as image:
                    template = image.convert("L")
                variants.append(
                    (pair, template, bytes(0 if pixel == 0 else 1 for pixel in template.tobytes()))
                )
            overlap = max(
                configuracao.sobreposicao_pixels,
                max((max(image.size) for _, image, _ in variants), default=0),
            )
            if overlap >= configuracao.tile_pixels:
                state, reason = EstadoMetodoSimbolos.FALHA, "Template maior que o tile"
            else:
                width = math.ceil(float(page.rect.width) * factor)
                height = math.ceil(float(page.rect.height) * factor)
                tiles = tuple(
                    (x, y)
                    for y in _positions(height, configuracao.tile_pixels, overlap)
                    for x in _positions(width, configuracao.tile_pixels, overlap)
                )
                if len(tiles) > configuracao.limite_tiles:
                    state, reason = EstadoMetodoSimbolos.FALHA, "Limite de tiles atingido"
                else:
                    accepted: dict[str, list[Caixa]] = {}
                    try:
                        for tx, ty in tiles:
                            right = min(width, tx + configuracao.tile_pixels)
                            bottom = min(height, ty + configuracao.tile_pixels)
                            if (right - tx) * (bottom - ty) > configuracao.limite_pixels_pagina:
                                state, reason = (
                                    EstadoMetodoSimbolos.FALHA,
                                    "Limite de pixels do tile atingido",
                                )
                                break
                            pix = page.get_pixmap(
                                matrix=pymupdf.Matrix(factor, factor),
                                clip=pymupdf.Rect(
                                    tx / factor, ty / factor, right / factor, bottom / factor
                                ),
                                colorspace=pymupdf.csRGB,
                                alpha=False,
                                annots=False,
                            )
                            with Image.frombytes(
                                "RGB", (pix.width, pix.height), pix.samples
                            ) as rgb:
                                binary = rgb.convert("L").point(
                                    lambda value: 255 if value >= 220 else 0
                                )
                            page_data = bytes(0 if pixel == 0 else 1 for pixel in binary.tobytes())
                            tile_hash = sha256(pix.samples).hexdigest()
                            for pair, template, template_data in variants:
                                matches, overflow = _search_template(
                                    page_data,
                                    binary.width,
                                    binary.height,
                                    template_data,
                                    template.width,
                                    template.height,
                                    limit=configuracao.limite_ocorrencias,
                                )
                                if overflow:
                                    state, reason = (
                                        EstadoMetodoSimbolos.FALHA,
                                        "Busca de template saturada",
                                    )
                                for x, y, score in matches:
                                    box = (
                                        (pix.x + x) / factor,
                                        (pix.y + y) / factor,
                                        (pix.x + x + template.width) / factor,
                                        (pix.y + y + template.height) / factor,
                                    )
                                    if any(
                                        region.pagina_numero == page_number
                                        and _overlap(box, region.caixa)
                                        for region in regions
                                    ):
                                        continue
                                    if any(
                                        _iou(box, old) >= 0.62 for old in accepted.get(pair.id, ())
                                    ):
                                        continue
                                    if len(observations) >= configuracao.limite_ocorrencias:
                                        state, reason = (
                                            EstadoMetodoSimbolos.FALHA,
                                            "Limite de ocorrências atingido",
                                        )
                                        break
                                    accepted.setdefault(pair.id, []).append(box)
                                    observations.append(
                                        ObservacaoSimbolo(
                                            fonte=source,
                                            metodo_assinatura=profile.assinatura(),
                                            geometria=_geometry(page, box),
                                            alternativas=(AlternativaClasseSimbolo(classe=None),),
                                            score_bruto=Decimal(str(score)),
                                            raster_sha256=tile_hash,
                                            template=pair.id,
                                            atributos=(
                                                ("contexto", "operacional"),
                                                ("descricao_legenda", pair.descricao),
                                                ("origem_legenda", pair.origem),
                                                ("template_sha256", pair.template_sha256),
                                                ("par_legenda_id", pair.id),
                                                ("pareamento_incerto", pair.pareamento_incerto),
                                                ("revisao_legenda", pair.revisao or ""),
                                                (
                                                    "score_tipo",
                                                    "similaridade_binaria_bruta_nao_probabilidade",
                                                ),
                                            ),
                                        )
                                    )
                                if reason == "Limite de ocorrências atingido":
                                    break
                            if reason == "Limite de ocorrências atingido":
                                break
                    except Exception as error:
                        state, reason = EstadoMetodoSimbolos.FALHA, type(error).__name__
        else:
            for digest, box in repetitions.get(page_number, ()):
                if len(observations) >= configuracao.limite_ocorrencias:
                    state, reason = EstadoMetodoSimbolos.FALHA, "Limite de ocorrências atingido"
                    break
                observations.append(
                    ObservacaoSimbolo(
                        fonte=source,
                        metodo_assinatura=profile.assinatura(),
                        geometria=_geometry(page, box),
                        alternativas=(AlternativaClasseSimbolo(classe=None),),
                        raster_sha256=digest,
                        template=digest,
                        atributos=(
                            ("contexto", "operacional"),
                            ("descricao_legenda", ""),
                            ("origem_legenda", "repeticao-imagem-local"),
                            ("template_sha256", digest),
                            ("pareamento_incerto", True),
                            ("score_tipo", "repeticao-exata-nao-probabilidade"),
                        ),
                    )
                )
        if reason:
            diagnostics.append(f"p{page_number}: {reason}")
        if state is EstadoMetodoSimbolos.NAO_DETECCAO and any(
            item.fonte.pagina_numero == page_number for item in observations
        ):
            state = EstadoMetodoSimbolos.CONCLUIDO
        coverages.append(
            CoberturaMetodoSimbolos(
                fonte=source,
                regiao_normalizada=(
                    PontoNormalizado(Decimal(0), Decimal(0)),
                    PontoNormalizado(Decimal(1), Decimal(1)),
                ),
                classes_avaliadas=(),
                estado=state,
                motivo=reason,
            )
        )
    result = ResultadoMetodoSimbolos(
        perfil=profile, coberturas=tuple(coverages), observacoes=tuple(observations)
    )
    return ResultadoLegendaDocumental(
        resultado=result, pares=pairs, regioes_legenda=regions, diagnosticos=tuple(diagnostics)
    )
