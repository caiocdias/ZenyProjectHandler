"""Correspondência determinística de geometrias e relações anotadas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from itertools import pairwise
from math import hypot

from zeny_project_handler.domain.enums import TipoGeometria
from zeny_project_handler.domain.evaluation import (
    CriteriosRegressaoAvaliacao,
    GeometriaAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.values import PontoNormalizado


@dataclass(frozen=True, slots=True)
class CorrespondenciaElemento:
    referencia_id: str
    candidato_id: str
    similaridade: Decimal


def associar_elementos(
    referencias: tuple[RotuloElementoAvaliacao, ...],
    candidatos: tuple[RotuloElementoAvaliacao, ...],
    criterios: CriteriosRegressaoAvaliacao,
    *,
    exigir_rotulos: bool,
) -> tuple[CorrespondenciaElemento, ...]:
    possibilities: list[CorrespondenciaElemento] = []
    for reference in referencias:
        for candidate in candidatos:
            if reference.geometria.pagina_numero != candidate.geometria.pagina_numero:
                continue
            if exigir_rotulos and (
                reference.categoria is not candidate.categoria
                or reference.situacao is not candidate.situacao
            ):
                continue
            similarity = similaridade_geometria(reference.geometria, candidate.geometria, criterios)
            if similarity is not None:
                possibilities.append(
                    CorrespondenciaElemento(reference.id, candidate.id, similarity)
                )
    possibilities.sort(key=lambda item: (-item.similaridade, item.referencia_id, item.candidato_id))
    used_references: set[str] = set()
    used_candidates: set[str] = set()
    matches: list[CorrespondenciaElemento] = []
    for match in possibilities:
        if match.referencia_id in used_references or match.candidato_id in used_candidates:
            continue
        used_references.add(match.referencia_id)
        used_candidates.add(match.candidato_id)
        matches.append(match)
    return tuple(sorted(matches, key=lambda item: item.referencia_id))


def similaridade_geometria(
    reference: GeometriaAvaliacao,
    candidate: GeometriaAvaliacao,
    criteria: CriteriosRegressaoAvaliacao,
) -> Decimal | None:
    if reference.tipo is not candidate.tipo:
        return None
    if reference.tipo is TipoGeometria.PONTO:
        return _distance_score(reference.pontos[0], candidate.pontos[0], criteria.tolerancia_ponto)
    if reference.tipo in {TipoGeometria.CAIXA, TipoGeometria.POLIGONO}:
        score = _bounding_box_iou(reference.pontos, candidate.pontos)
        return score if score >= criteria.iou_area_minimo else None
    distance = max(
        _directed_polyline_distance(reference.pontos, candidate.pontos),
        _directed_polyline_distance(candidate.pontos, reference.pontos),
    )
    return _linear_score(distance, criteria.tolerancia_polilinha)


def relacoes_correspondentes(
    referencias: tuple[RotuloRelacaoAvaliacao, ...],
    candidatos: tuple[RotuloRelacaoAvaliacao, ...],
    candidato_para_referencia: dict[str, str],
) -> int:
    reference_keys = {_relation_key(item, None) for item in referencias}
    candidate_keys = {
        key
        for item in candidatos
        if (key := _relation_key(item, candidato_para_referencia)) is not None
    }
    return len(reference_keys & candidate_keys)


def _relation_key(
    relation: RotuloRelacaoAvaliacao, id_mapping: dict[str, str] | None
) -> tuple[str, str, str, bool] | None:
    origin = relation.origem_id if id_mapping is None else id_mapping.get(relation.origem_id)
    destination = relation.destino_id if id_mapping is None else id_mapping.get(relation.destino_id)
    if origin is None or destination is None:
        return None
    if not relation.direcionada:
        origin, destination = sorted((origin, destination))
    return origin, destination, relation.tipo_relacao, relation.direcionada


def _distance_score(
    reference: PontoNormalizado, candidate: PontoNormalizado, tolerance: Decimal
) -> Decimal | None:
    delta_x = float(reference.x - candidate.x)
    delta_y = float(reference.y - candidate.y)
    distance = Decimal(str(hypot(delta_x, delta_y)))
    return _linear_score(distance, tolerance)


def _linear_score(distance: Decimal, tolerance: Decimal) -> Decimal | None:
    if distance > tolerance:
        return None
    return Decimal(1) - distance / tolerance


def _bounding_box_iou(
    reference: tuple[PontoNormalizado, ...], candidate: tuple[PontoNormalizado, ...]
) -> Decimal:
    left = _bounds(reference)
    right = _bounds(candidate)
    intersection_width = max(Decimal(0), min(left[2], right[2]) - max(left[0], right[0]))
    intersection_height = max(Decimal(0), min(left[3], right[3]) - max(left[1], right[1]))
    intersection = intersection_width * intersection_height
    left_area = (left[2] - left[0]) * (left[3] - left[1])
    right_area = (right[2] - right[0]) * (right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else Decimal(0)


def _bounds(
    points: tuple[PontoNormalizado, ...],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    return (
        min(point.x for point in points),
        min(point.y for point in points),
        max(point.x for point in points),
        max(point.y for point in points),
    )


def _directed_polyline_distance(
    source: tuple[PontoNormalizado, ...], target: tuple[PontoNormalizado, ...]
) -> Decimal:
    distances = [
        min(_point_segment_distance(point, left, right) for left, right in pairwise(target))
        for point in source
    ]
    return max(distances, default=Decimal(0))


def _point_segment_distance(
    point: PontoNormalizado, start: PontoNormalizado, end: PontoNormalizado
) -> Decimal:
    px, py = float(point.x), float(point.y)
    sx, sy = float(start.x), float(start.y)
    ex, ey = float(end.x), float(end.y)
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return Decimal(str(hypot(px - sx, py - sy)))
    projection = max(
        0.0,
        min(1.0, ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)),
    )
    projected_x = sx + projection * dx
    projected_y = sy + projection * dy
    return Decimal(str(hypot(px - projected_x, py - projected_y)))
