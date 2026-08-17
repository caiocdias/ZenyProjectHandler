"""Projeção determinística de divergências localizáveis para callouts do visualizador."""

from __future__ import annotations

import math
import re
import textwrap
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    ExecucaoConformidade,
    FatoConformidade,
    GrupoCondicaoConformidade,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.documents import PaginaDocumento
from zeny_project_handler.domain.values import (
    GeometriaDocumento,
    PontoNormalizado,
    decimal_value,
    required_text,
)

from .visual_occupancy import MapaOcupacaoVisual

_MARGEM_PAGINA_PONTOS = 8.0
_DISTANCIA_ALVO_PONTOS = 10.0
_MARGEM_CONTEUDO_PONTOS = 5.0
_LARGURA_MINIMA_PONTOS = 138.0
_LARGURA_MINIMA_FAIXA_PONTOS = 108.0
_LARGURA_MAXIMA_PONTOS = 228.0
_ALTURA_MINIMA_PONTOS = 36.0
_PREENCHIMENTO_HORIZONTAL_PONTOS = 12.0
_PREENCHIMENTO_VERTICAL_PONTOS = 9.0
_ESPACO_ENTRE_CAIXAS_PONTOS = 6.0
_MARGEM_ESPACO_BRANCO_PONTOS = 8.0
_FONTE_MINIMA_PONTOS = 8.5
_FONTE_PADRAO_PONTOS = 9.5
_ROTULO_PONTO = re.compile(r"^P\s*\d+[A-Z]?$", re.IGNORECASE)


class LayoutCalloutsImpossivelError(ValueError):
    """Indica que nem a distribuição compacta cabe no espaço físico da página."""


@dataclass(frozen=True, slots=True)
class _VariacaoCaixa:
    tamanho_fonte_pontos: float
    proporcao_largura_pagina: float
    largura_maxima_pontos: float


_VARIACOES_CAIXA = (
    _VariacaoCaixa(_FONTE_PADRAO_PONTOS, 0.33, _LARGURA_MAXIMA_PONTOS),
    _VariacaoCaixa(9.0, 0.38, 264.0),
    _VariacaoCaixa(8.75, 0.30, 210.0),
    _VariacaoCaixa(_FONTE_MINIMA_PONTOS, 0.27, 192.0),
)


class OrigemAncoraCallout(StrEnum):
    """Origem rastreável usada para localizar um callout."""

    FATO = "FATO"
    EVIDENCIA = "EVIDENCIA"
    ALVO = "ALVO"


@dataclass(frozen=True, slots=True)
class RetanguloCallout:
    """Retângulo normalizado e contido na página."""

    esquerda: Decimal
    topo: Decimal
    direita: Decimal
    base: Decimal

    def __post_init__(self) -> None:
        left = decimal_value(self.esquerda, field_name="esquerda")
        top = decimal_value(self.topo, field_name="topo")
        right = decimal_value(self.direita, field_name="direita")
        bottom = decimal_value(self.base, field_name="base")
        if not Decimal(0) <= left < right <= Decimal(1):
            raise ValueError("A caixa do callout deve caber horizontalmente na página")
        if not Decimal(0) <= top < bottom <= Decimal(1):
            raise ValueError("A caixa do callout deve caber verticalmente na página")
        object.__setattr__(self, "esquerda", left)
        object.__setattr__(self, "topo", top)
        object.__setattr__(self, "direita", right)
        object.__setattr__(self, "base", bottom)

    @property
    def largura(self) -> Decimal:
        return self.direita - self.esquerda

    @property
    def altura(self) -> Decimal:
        return self.base - self.topo


@dataclass(frozen=True, slots=True, kw_only=True)
class AncoraCallout:
    """Ponto de chamada derivado de uma geometria e de sua proveniência."""

    origem: OrigemAncoraCallout
    referencia_id: UUID
    geometria: GeometriaDocumento
    ponto: PontoNormalizado


@dataclass(frozen=True, slots=True, kw_only=True)
class CalloutConformidade:
    """Projeção sem Qt de uma divergência localizável."""

    id: UUID
    pagina_id: UUID
    texto: str
    caixa_sugerida: RetanguloCallout
    ancoras: tuple[AncoraCallout, ...]
    tamanho_fonte_pontos: Decimal = Decimal("10.5")

    def __post_init__(self) -> None:
        anchors = tuple(self.ancoras)
        if not anchors:
            raise ValueError("Callout deve possuir ao menos uma âncora")
        if any(item.geometria.pagina_id != self.pagina_id for item in anchors):
            raise ValueError("Âncoras do callout devem pertencer à página informada")
        font_size = decimal_value(
            self.tamanho_fonte_pontos,
            field_name="tamanho da fonte do callout",
        )
        if font_size < Decimal(str(_FONTE_MINIMA_PONTOS)):
            raise ValueError("A fonte do callout deve respeitar o tamanho mínimo legível")
        object.__setattr__(self, "texto", required_text(self.texto, field_name="texto do callout"))
        object.__setattr__(self, "ancoras", anchors)
        object.__setattr__(self, "tamanho_fonte_pontos", font_size)


@dataclass(frozen=True, slots=True)
class _RetanguloPontos:
    esquerda: float
    topo: float
    direita: float
    base: float

    @property
    def largura(self) -> float:
        return self.direita - self.esquerda

    @property
    def altura(self) -> float:
        return self.base - self.topo


@dataclass(frozen=True, slots=True)
class _GeometriaRastreavel:
    origem: OrigemAncoraCallout
    referencia_id: UUID
    geometria: GeometriaDocumento


@dataclass(frozen=True, slots=True)
class _PedidoCallout:
    finding: AchadoConformidade
    page: PaginaDocumento
    texto: str
    ancoras: tuple[AncoraCallout, ...]
    limites_ancora: _RetanguloPontos


@dataclass(frozen=True, slots=True)
class _CalloutPosicionado:
    pedido: _PedidoCallout
    caixa: RetanguloCallout
    texto: str
    tamanho_fonte_pontos: float


def projetar_callouts_conformidade(
    execucao: ExecucaoConformidade,
    *,
    evidencias: tuple[EvidenciaDocumento, ...],
    paginas: tuple[PaginaDocumento, ...],
    textos_apresentacao: Mapping[UUID, str] | None = None,
    mapas_ocupacao_visual: Mapping[UUID, MapaOcupacaoVisual] | None = None,
) -> tuple[CalloutConformidade, ...]:
    """Converta somente divergências com geometria rastreável em callouts estáveis."""
    pages_by_id = {item.id: item for item in paginas}
    facts_by_id = {item.id: item for item in execucao.fatos}
    evidence_by_id = {item.id: item for item in evidencias}
    targets_by_id = {item.id: item for item in execucao.alvos}
    important_content_by_page = _conteudo_importante_por_pagina(
        execucao,
        evidencias=evidencias,
        paginas=pages_by_id,
    )
    requests_by_page: dict[UUID, list[_PedidoCallout]] = defaultdict(list)
    divergent = tuple(
        item for item in execucao.achados if item.resultado is ResultadoConformidade.DIVERGENCIA
    )
    for finding in divergent:
        target = targets_by_id[finding.alvo_id]
        traceable = _geometrias_do_achado(
            finding,
            facts_by_id=facts_by_id,
            evidence_by_id=evidence_by_id,
            target=target,
            page_ids=frozenset(pages_by_id),
        )
        if not traceable:
            continue
        page_id = traceable[0].geometria.pagina_id
        page = pages_by_id[page_id]
        anchors = _ancoras_unicas(traceable)
        raw_text = (
            textos_apresentacao.get(finding.id, finding.titulo)
            if textos_apresentacao is not None
            else finding.titulo
        )
        requests_by_page[page_id].append(
            _PedidoCallout(
                finding=finding,
                page=page,
                texto=raw_text,
                ancoras=anchors,
                limites_ancora=_limites_geometrias_pontos(
                    tuple(item.geometria for item in traceable),
                    page,
                ),
            )
        )
    page_order = {item.id: (index, item.numero, str(item.id)) for index, item in enumerate(paginas)}
    positioned: list[_CalloutPosicionado] = []
    for page_id in sorted(requests_by_page, key=lambda item: page_order[item]):
        requests = tuple(
            sorted(
                requests_by_page[page_id],
                key=lambda item: (
                    (item.limites_ancora.topo + item.limites_ancora.base) / 2,
                    (item.limites_ancora.esquerda + item.limites_ancora.direita) / 2,
                    str(item.finding.id),
                ),
            )
        )
        positioned.extend(
            _posicionar_pagina(
                requests,
                important_content=important_content_by_page.get(page_id, ()),
                visual_occupancy=(mapas_ocupacao_visual or {}).get(page_id),
            )
        )
    return tuple(
        CalloutConformidade(
            id=item.pedido.finding.id,
            pagina_id=item.pedido.page.id,
            texto=item.texto,
            caixa_sugerida=item.caixa,
            ancoras=item.pedido.ancoras,
            tamanho_fonte_pontos=Decimal(str(item.tamanho_fonte_pontos)),
        )
        for item in positioned
    )


def _posicionar_pagina(
    requests: tuple[_PedidoCallout, ...],
    *,
    important_content: tuple[_RetanguloPontos, ...],
    visual_occupancy: MapaOcupacaoVisual | None,
) -> tuple[_CalloutPosicionado, ...]:
    page = requests[0].page
    for variation in _VARIACOES_CAIXA:
        occupied: list[RetanguloCallout] = []
        result: list[_CalloutPosicionado] = []
        for request in requests:
            dimensions = _dimensoes_texto(request.texto, page, variation=variation)
            if dimensions is None:
                break
            width, height, wrapped_text = dimensions
            suggested = _posicionar_caixa(
                page,
                anchor_bounds=request.limites_ancora,
                width=width,
                height=height,
                occupied=tuple(occupied),
                important_content=important_content,
                visual_occupancy=visual_occupancy,
            )
            if suggested is None:
                break
            occupied.append(suggested)
            result.append(
                _CalloutPosicionado(
                    pedido=request,
                    caixa=suggested,
                    texto=wrapped_text,
                    tamanho_fonte_pontos=variation.tamanho_fonte_pontos,
                )
            )
        if len(result) == len(requests):
            return tuple(result)
    compact = _distribuir_em_faixa_interna(
        requests,
        important_content=important_content,
        visual_occupancy=visual_occupancy,
    )
    if compact is None and visual_occupancy is not None:
        # O mapa raster é apenas uma melhoria de posicionamento. Uma folha sem
        # área totalmente branca suficiente não pode transformar achados que já
        # eram localizáveis em achados sem localização.
        return _posicionar_pagina(
            requests,
            important_content=important_content,
            visual_occupancy=None,
        )
    if compact is None:
        raise LayoutCalloutsImpossivelError(
            f"A página {page.numero} não comporta todos os callouts no tamanho mínimo legível"
        )
    return compact


def ponto_conexao_callout(
    caixa: RetanguloCallout,
    ancora: PontoNormalizado,
) -> PontoNormalizado:
    """Encontre na borda da caixa o início da linha voltada para a âncora."""
    center_x = (caixa.esquerda + caixa.direita) / 2
    center_y = (caixa.topo + caixa.base) / 2
    dx = ancora.x - center_x
    dy = ancora.y - center_y
    if caixa.esquerda <= ancora.x <= caixa.direita and caixa.topo <= ancora.y <= caixa.base:
        distances = (
            (ancora.x - caixa.esquerda, PontoNormalizado(caixa.esquerda, ancora.y)),
            (caixa.direita - ancora.x, PontoNormalizado(caixa.direita, ancora.y)),
            (ancora.y - caixa.topo, PontoNormalizado(ancora.x, caixa.topo)),
            (caixa.base - ancora.y, PontoNormalizado(ancora.x, caixa.base)),
        )
        return min(distances, key=lambda item: item[0])[1]
    half_width = caixa.largura / 2
    half_height = caixa.altura / 2
    horizontal_ratio = abs(dx) / half_width if dx else Decimal(0)
    vertical_ratio = abs(dy) / half_height if dy else Decimal(0)
    if horizontal_ratio >= vertical_ratio:
        x = caixa.direita if dx > 0 else caixa.esquerda
        scale = (x - center_x) / dx
        return PontoNormalizado(x, center_y + dy * scale)
    y = caixa.base if dy > 0 else caixa.topo
    scale = (y - center_y) / dy
    return PontoNormalizado(center_x + dx * scale, y)


def _geometrias_do_achado(
    finding: AchadoConformidade,
    *,
    facts_by_id: dict[UUID, FatoConformidade],
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    target: AlvoConformidade,
    page_ids: frozenset[UUID],
) -> tuple[_GeometriaRastreavel, ...]:
    fact_ids = _ids_fatos_decisivos(finding)
    facts = tuple(facts_by_id.get(item) for item in fact_ids)
    fact_geometries = tuple(
        _GeometriaRastreavel(OrigemAncoraCallout.FATO, fact.id, fact.geometria)
        for fact in facts
        if fact is not None and fact.geometria is not None and fact.geometria.pagina_id in page_ids
    )
    fact_evidence_ids = tuple(
        evidence_id for fact in facts if fact is not None for evidence_id in fact.evidencia_ids
    )
    evidence_ids = tuple(dict.fromkeys((*fact_evidence_ids, *finding.evidencia_ids)))
    evidence_geometries = tuple(
        _GeometriaRastreavel(OrigemAncoraCallout.EVIDENCIA, evidence.id, evidence.geometria)
        for evidence_id in evidence_ids
        if (evidence := evidence_by_id.get(evidence_id)) is not None
        and evidence.geometria.pagina_id in page_ids
    )
    target_geometries = (
        (
            _GeometriaRastreavel(
                OrigemAncoraCallout.ALVO,
                target.id,
                target.geometria,
            ),
        )
        if target.geometria is not None and target.geometria.pagina_id in page_ids
        else ()
    )
    # P1, P2, P3 etc. representam regiões consolidadas do desenho. Nesses
    # alvos, uma geometria pontual de fato pode pertencer apenas a um símbolo
    # auxiliar; a seta deve terminar na região nomeada que o projetista vê.
    if (
        target.tipo is TipoEscopoConformidade.REGIAO
        and _ROTULO_PONTO.fullmatch(target.rotulo.strip())
        and target_geometries
    ):
        return target_geometries
    for tier in (fact_geometries, evidence_geometries, target_geometries):
        if tier:
            selected_page = tier[0].geometria.pagina_id
            selected = tuple(item for item in tier if item.geometria.pagina_id == selected_page)
            point_geometries = tuple(item for item in selected if len(item.geometria.pontos) == 1)
            if point_geometries:
                return point_geometries
            return selected
    return ()


def _ids_fatos_decisivos(finding: AchadoConformidade) -> tuple[UUID, ...]:
    decisive = tuple(
        fact_id
        for evaluation in finding.avaliacoes_condicoes
        if evaluation.grupo is GrupoCondicaoConformidade.REQUISITO
        and evaluation.resultado is ResultadoCondicaoConformidade.NAO_ATENDE
        for fact_id in evaluation.fato_ids
    )
    return tuple(dict.fromkeys(decisive or finding.fato_ids))


def _ancoras_unicas(
    geometries: tuple[_GeometriaRastreavel, ...],
) -> tuple[AncoraCallout, ...]:
    result: list[AncoraCallout] = []
    seen: set[tuple[UUID, tuple[PontoNormalizado, ...]]] = set()
    for item in geometries:
        identity = (item.geometria.pagina_id, item.geometria.pontos)
        if identity in seen:
            continue
        seen.add(identity)
        xs = tuple(point.x for point in item.geometria.pontos)
        ys = tuple(point.y for point in item.geometria.pontos)
        result.append(
            AncoraCallout(
                origem=item.origem,
                referencia_id=item.referencia_id,
                geometria=item.geometria,
                ponto=PontoNormalizado((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2),
            )
        )
    return tuple(result)


def _dimensoes_texto(
    text: str,
    page: PaginaDocumento,
    *,
    variation: _VariacaoCaixa,
    fixed_width: float | None = None,
) -> tuple[float, float, str] | None:
    page_width = float(page.largura_pontos)
    page_height = float(page.altura_pontos)
    available_width = max(1.0, page_width - 2 * _MARGEM_PAGINA_PONTOS)
    available_height = max(1.0, page_height - 2 * _MARGEM_PAGINA_PONTOS)
    width = fixed_width or min(
        available_width,
        max(
            _LARGURA_MINIMA_PONTOS,
            min(
                variation.largura_maxima_pontos,
                page_width * variation.proporcao_largura_pagina,
            ),
        ),
    )
    if width > available_width:
        return None
    wrapped, line_count = _quebrar_texto(
        text,
        width,
        font_size=variation.tamanho_fonte_pontos,
    )
    line_height = variation.tamanho_fonte_pontos * 1.28
    height = max(
        _ALTURA_MINIMA_PONTOS,
        2 * _PREENCHIMENTO_VERTICAL_PONTOS + line_count * line_height,
    )
    return (width, height, wrapped) if height <= available_height else None


def _quebrar_texto(
    text: str,
    width_points: float,
    *,
    font_size: float,
) -> tuple[str, int]:
    normalized = " ".join(text.split())
    usable = max(1.0, width_points - 2 * _PREENCHIMENTO_HORIZONTAL_PONTOS)
    conservative_character_width = font_size * 0.62
    limit = max(12, int(usable / conservative_character_width))
    lines = textwrap.wrap(
        normalized,
        width=limit,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [normalized]
    return "\n".join(lines), len(lines)


def _limites_geometrias_pontos(
    geometries: tuple[GeometriaDocumento, ...],
    page: PaginaDocumento,
) -> _RetanguloPontos:
    xs = tuple(float(point.x) for item in geometries for point in item.pontos)
    ys = tuple(float(point.y) for item in geometries for point in item.pontos)
    width = float(page.largura_pontos)
    height = float(page.altura_pontos)
    return _RetanguloPontos(min(xs) * width, min(ys) * height, max(xs) * width, max(ys) * height)


def _conteudo_importante_por_pagina(
    execution: ExecucaoConformidade,
    *,
    evidencias: tuple[EvidenciaDocumento, ...],
    paginas: dict[UUID, PaginaDocumento],
) -> dict[UUID, tuple[_RetanguloPontos, ...]]:
    """Mapeie conteúdo conhecido para que caixas prefiram espaços livres da folha."""
    geometries = (
        *(item.geometria for item in evidencias),
        *(item.geometria for item in execution.fatos if item.geometria is not None),
        *(item.geometria for item in execution.alvos if item.geometria is not None),
    )
    unique: dict[UUID, dict[tuple[PontoNormalizado, ...], GeometriaDocumento]] = {}
    for geometry in geometries:
        if geometry.pagina_id not in paginas:
            continue
        unique.setdefault(geometry.pagina_id, {}).setdefault(geometry.pontos, geometry)
    return {
        page_id: tuple(
            _expandir_retangulo(
                _limites_geometrias_pontos((geometry,), paginas[page_id]),
                _MARGEM_CONTEUDO_PONTOS,
                page_width=float(paginas[page_id].largura_pontos),
                page_height=float(paginas[page_id].altura_pontos),
            )
            for geometry in page_geometries.values()
        )
        for page_id, page_geometries in unique.items()
    }


def _distribuir_em_faixa_interna(
    requests: tuple[_PedidoCallout, ...],
    *,
    important_content: tuple[_RetanguloPontos, ...],
    visual_occupancy: MapaOcupacaoVisual | None,
) -> tuple[_CalloutPosicionado, ...] | None:
    page = requests[0].page
    page_width = float(page.largura_pontos)
    page_height = float(page.altura_pontos)
    available_width = page_width - 2 * _MARGEM_PAGINA_PONTOS
    available_height = page_height - 2 * _MARGEM_PAGINA_PONTOS
    variation = _VARIACOES_CAIXA[-1]
    maximum_columns = max(
        1,
        int(
            (available_width + _ESPACO_ENTRE_CAIXAS_PONTOS)
            / (_LARGURA_MINIMA_FAIXA_PONTOS + _ESPACO_ENTRE_CAIXAS_PONTOS)
        ),
    )
    candidates: list[tuple[tuple[float, float, int], tuple[_CalloutPosicionado, ...]]] = []
    for column_count in range(1, maximum_columns + 1):
        shared_width = (
            available_width - _ESPACO_ENTRE_CAIXAS_PONTOS * (column_count - 1)
        ) / column_count
        width_presets = tuple(
            width
            for width in dict.fromkeys(
                (
                    shared_width,
                    min(294.0, shared_width),
                    min(_LARGURA_MAXIMA_PONTOS, shared_width),
                    min(210.0, shared_width),
                )
            )
            if width >= _LARGURA_MINIMA_FAIXA_PONTOS
        )
        for column_width in width_presets:
            measured = tuple(
                _dimensoes_texto(
                    request.texto,
                    page,
                    variation=variation,
                    fixed_width=column_width,
                )
                for request in requests
            )
            if any(item is None for item in measured):
                continue
            column_heights = [0.0] * column_count
            placements: list[tuple[_PedidoCallout, int, float, float, str]] = []
            for request, dimensions in zip(requests, measured, strict=True):
                assert dimensions is not None
                _width, height, wrapped_text = dimensions
                column = min(range(column_count), key=lambda item: (column_heights[item], item))
                top = column_heights[column]
                placements.append((request, column, top, height, wrapped_text))
                column_heights[column] += height + _ESPACO_ENTRE_CAIXAS_PONTOS
            used_height = max(column_heights) - _ESPACO_ENTRE_CAIXAS_PONTOS
            if used_height > available_height:
                continue
            strip_width = (
                column_count * column_width + (column_count - 1) * _ESPACO_ENTRE_CAIXAS_PONTOS
            )
            horizontal_starts = (
                _conter_inicio_faixa(
                    sum(
                        (item.limites_ancora.esquerda + item.limites_ancora.direita) / 2
                        for item in requests
                    )
                    / len(requests)
                    - strip_width / 2,
                    strip_width,
                    page_width,
                ),
                (page_width - strip_width) / 2,
                _MARGEM_PAGINA_PONTOS,
                page_width - _MARGEM_PAGINA_PONTOS - strip_width,
            )
            vertical_starts = (
                _conter_inicio_faixa(
                    sum(
                        (item.limites_ancora.topo + item.limites_ancora.base) / 2
                        for item in requests
                    )
                    / len(requests)
                    - used_height / 2,
                    used_height,
                    page_height,
                ),
                _MARGEM_PAGINA_PONTOS,
                _MARGEM_PAGINA_PONTOS + (available_height - used_height) / 2,
                page_height - _MARGEM_PAGINA_PONTOS - used_height,
            )
            for left in dict.fromkeys(horizontal_starts):
                for top_offset in dict.fromkeys(vertical_starts):
                    candidate = _materializar_faixa(
                        placements,
                        page=page,
                        left=left,
                        top_offset=top_offset,
                        column_width=column_width,
                        font_size=variation.tamanho_fonte_pontos,
                    )
                    rectangles = tuple(
                        _retangulo_normalizado_em_pontos(item.caixa, page) for item in candidate
                    )
                    if visual_occupancy is not None and not all(
                        _retangulo_em_espaco_branco(rectangle, page, visual_occupancy)
                        for rectangle in rectangles
                    ):
                        continue
                    content_area = sum(
                        _intersection_area(rectangle, content)
                        for rectangle in rectangles
                        for content in important_content
                    )
                    distance = sum(
                        _rectangle_gap(rectangle, item.pedido.limites_ancora)
                        for rectangle, item in zip(rectangles, candidate, strict=True)
                    )
                    candidates.append(((content_area, distance, column_count), candidate))
    if candidates:
        return min(candidates, key=lambda item: item[0])[1]
    return None


def _conter_inicio_faixa(start: float, size: float, page_size: float) -> float:
    maximum = page_size - _MARGEM_PAGINA_PONTOS - size
    return min(maximum, max(_MARGEM_PAGINA_PONTOS, start))


def _materializar_faixa(
    placements: list[tuple[_PedidoCallout, int, float, float, str]],
    *,
    page: PaginaDocumento,
    left: float,
    top_offset: float,
    column_width: float,
    font_size: float,
) -> tuple[_CalloutPosicionado, ...]:
    page_width = float(page.largura_pontos)
    page_height = float(page.altura_pontos)
    result: list[_CalloutPosicionado] = []
    for request, column, top, height, wrapped_text in placements:
        x = left + column * (column_width + _ESPACO_ENTRE_CAIXAS_PONTOS)
        rectangle = _RetanguloPontos(
            x, top_offset + top, x + column_width, top_offset + top + height
        )
        result.append(
            _CalloutPosicionado(
                pedido=request,
                caixa=_retangulo_pontos_normalizado(rectangle, page_width, page_height),
                texto=wrapped_text,
                tamanho_fonte_pontos=font_size,
            )
        )
    return tuple(result)


def _posicionar_caixa(
    page: PaginaDocumento,
    *,
    anchor_bounds: _RetanguloPontos,
    width: float,
    height: float,
    occupied: tuple[RetanguloCallout, ...],
    important_content: tuple[_RetanguloPontos, ...],
    visual_occupancy: MapaOcupacaoVisual | None,
) -> RetanguloCallout | None:
    page_width = float(page.largura_pontos)
    page_height = float(page.altura_pontos)
    center_x = (anchor_bounds.esquerda + anchor_bounds.direita) / 2
    center_y = (anchor_bounds.topo + anchor_bounds.base) / 2
    gap = _DISTANCIA_ALVO_PONTOS
    raw_candidates = (
        (anchor_bounds.direita + gap, center_y - height / 2),
        (anchor_bounds.esquerda - gap - width, center_y - height / 2),
        (center_x - width / 2, anchor_bounds.topo - gap - height),
        (center_x - width / 2, anchor_bounds.base + gap),
        (anchor_bounds.direita + gap, anchor_bounds.topo - gap - height),
        (anchor_bounds.direita + gap, anchor_bounds.base + gap),
        (anchor_bounds.esquerda - gap - width, anchor_bounds.topo - gap - height),
        (anchor_bounds.esquerda - gap - width, anchor_bounds.base + gap),
        (anchor_bounds.direita + gap, _MARGEM_PAGINA_PONTOS),
        (anchor_bounds.esquerda - gap - width, _MARGEM_PAGINA_PONTOS),
        (anchor_bounds.direita + gap, page_height - _MARGEM_PAGINA_PONTOS - height),
        (anchor_bounds.esquerda - gap - width, page_height - _MARGEM_PAGINA_PONTOS - height),
    )
    horizontal_grid = tuple(
        dict.fromkeys(
            (
                *_distributed_positions(
                    _MARGEM_PAGINA_PONTOS,
                    page_width - _MARGEM_PAGINA_PONTOS - width,
                    divisions=8,
                ),
                *_packing_positions(
                    _MARGEM_PAGINA_PONTOS,
                    page_width - _MARGEM_PAGINA_PONTOS - width,
                    size=width,
                ),
            )
        )
    )
    vertical_grid = tuple(
        dict.fromkeys(
            (
                *_distributed_positions(
                    _MARGEM_PAGINA_PONTOS,
                    page_height - _MARGEM_PAGINA_PONTOS - height,
                    divisions=12,
                ),
                *_packing_positions(
                    _MARGEM_PAGINA_PONTOS,
                    page_height - _MARGEM_PAGINA_PONTOS - height,
                    size=height,
                ),
            )
        )
    )
    grid_candidates = tuple((x, y) for x in horizontal_grid for y in vertical_grid)
    candidates = tuple(
        dict.fromkeys(
            _contained_rect(x, y, width, height, page_width=page_width, page_height=page_height)
            for x, y in (*raw_candidates, *grid_candidates)
        )
    )
    occupied_points = tuple(
        _RetanguloPontos(
            float(item.esquerda) * page_width,
            float(item.topo) * page_height,
            float(item.direita) * page_width,
            float(item.base) * page_height,
        )
        for item in occupied
    )
    protected_anchor = _expandir_retangulo(
        anchor_bounds,
        _MARGEM_CONTEUDO_PONTOS,
        page_width=page_width,
        page_height=page_height,
    )
    collision_free = tuple(
        (index, candidate)
        for index, candidate in enumerate(candidates)
        if not _positive_intersections(candidate, occupied_points)
        and (
            visual_occupancy is None
            or _retangulo_em_espaco_branco(candidate, page, visual_occupancy)
        )
    )
    if not collision_free:
        return None
    _index, selected = min(
        collision_free,
        key=lambda pair: (
            _collision_score(
                pair[1],
                protected_anchor,
                (),
                important_content,
            ),
            _rectangle_gap(pair[1], anchor_bounds),
            pair[0],
        ),
    )
    return _retangulo_pontos_normalizado(selected, page_width, page_height)


def _retangulo_em_espaco_branco(
    rectangle: _RetanguloPontos,
    page: PaginaDocumento,
    visual_occupancy: MapaOcupacaoVisual,
) -> bool:
    expanded = _expandir_retangulo(
        rectangle,
        _MARGEM_ESPACO_BRANCO_PONTOS,
        page_width=float(page.largura_pontos),
        page_height=float(page.altura_pontos),
    )
    return visual_occupancy.regiao_totalmente_branca(
        expanded.esquerda / float(page.largura_pontos),
        expanded.topo / float(page.altura_pontos),
        expanded.direita / float(page.largura_pontos),
        expanded.base / float(page.altura_pontos),
    )


def _distributed_positions(start: float, end: float, *, divisions: int = 6) -> tuple[float, ...]:
    if end <= start:
        return (start,)
    interval = (end - start) / divisions
    return tuple(start + interval * index for index in range(divisions + 1))


def _packing_positions(start: float, end: float, *, size: float) -> tuple[float, ...]:
    if end <= start:
        return (start,)
    step = size + _ESPACO_ENTRE_CAIXAS_PONTOS
    result = [start]
    while result[-1] + step <= end:
        result.append(result[-1] + step)
    if result[-1] != end:
        result.append(end)
    return tuple(result)


def _contained_rect(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    page_width: float,
    page_height: float,
) -> _RetanguloPontos:
    max_x = max(_MARGEM_PAGINA_PONTOS, page_width - _MARGEM_PAGINA_PONTOS - width)
    max_y = max(_MARGEM_PAGINA_PONTOS, page_height - _MARGEM_PAGINA_PONTOS - height)
    left = min(max_x, max(_MARGEM_PAGINA_PONTOS, x))
    top = min(max_y, max(_MARGEM_PAGINA_PONTOS, y))
    return _RetanguloPontos(left, top, left + width, top + height)


def _collision_score(
    candidate: _RetanguloPontos,
    anchor: _RetanguloPontos,
    occupied: tuple[_RetanguloPontos, ...],
    important_content: tuple[_RetanguloPontos, ...],
) -> tuple[int, float, float, int, int]:
    anchor_overlaps = _positive_intersections(candidate, (anchor,))
    callout_overlaps = _positive_intersections(candidate, occupied)
    content_overlaps = _positive_intersections(candidate, important_content)
    return (
        int(bool(callout_overlaps)),
        sum(callout_overlaps),
        sum(anchor_overlaps) + sum(content_overlaps),
        len(anchor_overlaps) + len(content_overlaps),
        len(callout_overlaps),
    )


def _positive_intersections(
    candidate: _RetanguloPontos,
    obstacles: tuple[_RetanguloPontos, ...],
) -> tuple[float, ...]:
    return tuple(
        area for obstacle in obstacles if (area := _intersection_area(candidate, obstacle)) > 0
    )


def _retangulo_pontos_normalizado(
    rectangle: _RetanguloPontos,
    page_width: float,
    page_height: float,
) -> RetanguloCallout:
    return RetanguloCallout(
        Decimal(str(rectangle.esquerda / page_width)),
        Decimal(str(rectangle.topo / page_height)),
        Decimal(str(rectangle.direita / page_width)),
        Decimal(str(rectangle.base / page_height)),
    )


def _retangulo_normalizado_em_pontos(
    rectangle: RetanguloCallout,
    page: PaginaDocumento,
) -> _RetanguloPontos:
    page_width = float(page.largura_pontos)
    page_height = float(page.altura_pontos)
    return _RetanguloPontos(
        float(rectangle.esquerda) * page_width,
        float(rectangle.topo) * page_height,
        float(rectangle.direita) * page_width,
        float(rectangle.base) * page_height,
    )


def _rectangle_gap(left: _RetanguloPontos, right: _RetanguloPontos) -> float:
    horizontal = max(left.esquerda - right.direita, right.esquerda - left.direita, 0.0)
    vertical = max(left.topo - right.base, right.topo - left.base, 0.0)
    return math.hypot(horizontal, vertical)


def _expandir_retangulo(
    rectangle: _RetanguloPontos,
    margin: float,
    *,
    page_width: float,
    page_height: float,
) -> _RetanguloPontos:
    return _RetanguloPontos(
        max(0.0, rectangle.esquerda - margin),
        max(0.0, rectangle.topo - margin),
        min(page_width, rectangle.direita + margin),
        min(page_height, rectangle.base + margin),
    )


def _intersection_area(left: _RetanguloPontos, right: _RetanguloPontos) -> float:
    width = max(0.0, min(left.direita, right.direita) - max(left.esquerda, right.esquerda))
    height = max(0.0, min(left.base, right.base) - max(left.topo, right.topo))
    return width * height
