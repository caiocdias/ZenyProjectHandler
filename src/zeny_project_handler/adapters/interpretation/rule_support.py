"""Operações puras compartilhadas pelas regras explícitas."""

from __future__ import annotations

import math
import re
import unicodedata
from decimal import Decimal

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.catalog import AssinaturaSimbologia, CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, SituacaoProjeto, TipoEvidencia
from zeny_project_handler.domain.values import GeometriaDocumento


def normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).upper()
    return " ".join(normalized.split())


def contains_code(text: str, code: str) -> bool:
    normalized_code = normalized_text(code)
    if len(normalized_code) < 2:
        return False
    pattern = rf"(?<![A-Z0-9]){re.escape(normalized_code)}(?![A-Z0-9])"
    return re.search(pattern, normalized_text(text)) is not None


def center(geometry: GeometriaDocumento) -> tuple[float, float]:
    x_values = [float(point.x) for point in geometry.pontos]
    y_values = [float(point.y) for point in geometry.pontos]
    return (min(x_values) + max(x_values)) / 2, (min(y_values) + max(y_values)) / 2


def point_distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def geometry_distance(first: GeometriaDocumento, second: GeometriaDocumento) -> float:
    if first.pagina_id != second.pagina_id:
        return math.inf
    return point_distance(center(first), center(second))


def _color_values(evidence: EvidenciaDocumento) -> tuple[str, ...]:
    attributes = dict(evidence.atributos_extraidos)
    return tuple(
        str(attributes[key]).upper()
        for key in ("cor", "cor_contorno", "cor_preenchimento")
        if attributes.get(key) not in {None, "", "None"}
    )


def _rgb(value: str) -> tuple[int, int, int] | None:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return None
    return int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)


def _signature_matches(color: str, signature: AssinaturaSimbologia) -> bool:
    observed = _rgb(color)
    expected = _rgb(signature.cor)
    if observed is None or expected is None:
        return False
    return max(abs(left - right) for left, right in zip(observed, expected, strict=True)) <= (
        signature.tolerancia_cor
    )


def situation_from_evidence(
    evidence: EvidenciaDocumento,
    category: CategoriaElemento,
    catalog: CatalogoTecnico,
) -> SituacaoProjeto | None:
    signatures = sorted(
        catalog.assinaturas_simbologia,
        key=lambda item: item.prioridade,
        reverse=True,
    )
    for signature in signatures:
        if signature.categoria_elemento not in {None, category}:
            continue
        if any(_signature_matches(color, signature) for color in _color_values(evidence)):
            return signature.situacao_projeto
    return None


def nearest_context_evidence(
    source: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
    maximum_distance: Decimal,
) -> EvidenciaDocumento | None:
    candidates = (
        item
        for item in evidence
        if item.tipo in {TipoEvidencia.VETOR, TipoEvidencia.IMAGEM}
        and item.pagina_id == source.pagina_id
    )
    nearest = min(
        candidates,
        key=lambda item: geometry_distance(source.geometria, item.geometria),
        default=None,
    )
    if nearest is None:
        return None
    return (
        nearest
        if geometry_distance(source.geometria, nearest.geometria) <= float(maximum_distance)
        else None
    )
