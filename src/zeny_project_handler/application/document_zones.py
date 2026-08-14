"""Classificação conservadora de zonas documentais que não representam a rede."""

from __future__ import annotations

import re
from collections import defaultdict
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.enums import TipoEvidencia, TipoOrigemPdf
from zeny_project_handler.domain.values import GeometriaDocumento

_SEMANTIC_TEXT_TYPES = {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
_REVIEW_ANNOTATION_ORIGINS = {
    TipoOrigemPdf.ANOTACAO,
    TipoOrigemPdf.APARENCIA_ANOTACAO,
}
_HEADER_LABEL_PATTERN = re.compile(
    r"(?:^|\s)(?:"
    r"APROVACAO|APROVADO\s+POR|CIRCUITO|CLIENTE|CONTRATADA|DATA|DESENHISTA|"
    r"DISPOSITIVO|ESCALA|FOLHA|LEVANTAMENTO|NOTA\s+DE\s+SERVICO|"
    r"NUMERO\s+DO\s+PROJETO|PROJETO|RESPONSAVEL(?:\s+TECNICO)?|REVISAO|TITULO"
    r")\s*:",
    re.IGNORECASE,
)
_ROW_VERTICAL_TOLERANCE = 0.008
_ROW_LEFT_TOLERANCE = 0.012
_ROW_RIGHT_REACH = 0.36
_HEADER_ZONE_MIN_CENTER_Y = 0.76


def evidencias_sem_anotacoes_de_revisao(
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    """Separe o conteúdo do projeto das anotações sobrepostas ao PDF.

    Comentários e suas aparências continuam persistidos para auditoria e para a
    documentação, mas não podem originar elementos técnicos do desenho.
    """
    return tuple(item for item in evidencias if not evidencia_eh_anotacao_de_revisao(item))


def evidencia_eh_anotacao_de_revisao(evidencia: EvidenciaDocumento) -> bool:
    """Identifique comentários PDF sem apagar portadores técnicos AutoCAD SHX."""
    if evidencia.origem_pdf.tipo not in _REVIEW_ANNOTATION_ORIGINS:
        return False
    attributes = dict(evidencia.atributos_extraidos)
    if attributes.get("anotacao_tecnica") is True:
        return False
    metadata = " ".join(
        str(attributes.get(key, "")) for key in ("titulo", "assunto", "nome")
    ).casefold()
    return not (
        (evidencia.origem_pdf.subtipo_anotacao or "").casefold() == "square"
        and "autocad" in metadata
        and "shx" in metadata
    )


def evidencia_esta_na_zona_de_cabecalho(evidencia: EvidenciaDocumento) -> bool:
    """Identifique a faixa física reservada ao cabeçalho/carimbo da prancha.

    As geometrias do documento usam ``y`` normalizado de cima para baixo. O
    cabeçalho dos modelos de prancha fica na faixa inferior; usar o centro da
    evidência nos últimos 24% da folha impede que referências ``NS:`` no corpo
    do desenho sejam confundidas com o número oficial do projeto. A largura não
    é restringida porque o carimbo pode se expandir para a esquerda em formatos
    e orientações diferentes.
    """
    _left, top, _right, bottom = _bounds(evidencia.geometria)
    return (top + bottom) / 2 >= _HEADER_ZONE_MIN_CENTER_Y


def evidencias_sem_cabecalho(
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[EvidenciaDocumento, ...]:
    """Retire apenas texto/OCR pertencente a linhas reconhecíveis do cabeçalho.

    Vetores e imagens são preservados. Isso evita apagar desenho útil apenas porque
    ele se encontra à direita ou na parte inferior da folha.
    """
    header_rows = _header_rows(evidencias)
    return tuple(
        item
        for item in evidencias
        if item.tipo not in _SEMANTIC_TEXT_TYPES
        or not _belongs_to_header_row(item, header_rows.get(item.pagina_id, ()))
    )


def _header_rows(
    evidencias: tuple[EvidenciaDocumento, ...],
) -> dict[UUID, tuple[tuple[float, float, float, float], ...]]:
    rows: dict[UUID, list[tuple[float, float, float, float]]] = defaultdict(list)
    for item in evidencias:
        if item.tipo not in _SEMANTIC_TEXT_TYPES or not item.conteudo_bruto:
            continue
        if _HEADER_LABEL_PATTERN.search(_normalized_label_text(item.conteudo_bruto)) is None:
            continue
        rows[item.pagina_id].append(_bounds(item.geometria))
    return {page_id: tuple(bounds) for page_id, bounds in rows.items()}


def _belongs_to_header_row(
    evidence: EvidenciaDocumento,
    header_rows: tuple[tuple[float, float, float, float], ...],
) -> bool:
    if evidence.conteudo_bruto and _HEADER_LABEL_PATTERN.search(
        _normalized_label_text(evidence.conteudo_bruto)
    ):
        return True
    left, top, right, bottom = _bounds(evidence.geometria)
    center_y = (top + bottom) / 2
    for row_left, row_top, row_right, row_bottom in header_rows:
        row_center_y = (row_top + row_bottom) / 2
        vertical_tolerance = max(
            _ROW_VERTICAL_TOLERANCE,
            (bottom - top + row_bottom - row_top) / 2,
        )
        if abs(center_y - row_center_y) > vertical_tolerance:
            continue
        if right < row_left - _ROW_LEFT_TOLERANCE:
            continue
        if left > row_right + _ROW_RIGHT_REACH:
            continue
        return True
    return False


def _normalized_label_text(value: str) -> str:
    return (
        value.upper()
        .replace("Ç", "C")
        .replace("Ã", "A")
        .replace("Á", "A")
        .replace("Â", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Õ", "O")
        .replace("Ú", "U")
    )


def _bounds(geometry: GeometriaDocumento) -> tuple[float, float, float, float]:
    x_values = tuple(float(point.x) for point in geometry.pontos)
    y_values = tuple(float(point.y) for point in geometry.pontos)
    return min(x_values), min(y_values), max(x_values), max(y_values)
