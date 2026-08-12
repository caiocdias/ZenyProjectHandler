"""Filtro dos elementos que possuem identificador operacional no desenho."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from itertools import pairwise

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.values import GeometriaDocumento

from .rule_support import center, normalized_text

_MAXIMUM_IDENTIFIER_DISTANCE = 0.14
_MAXIMUM_TARGETED_IDENTIFIER_DISTANCE = 0.06
_MAXIMUM_OCCURRENCE_COMPONENT_DISTANCE = 0.10
_TARGETED_IDENTIFIER_ENGINES = {
    "tesseract-identificador-localizado",
    "tesseract-identificador-vetorial-localizado",
}
_TARGETED_IDENTIFIER_ENGINE_PRIORITY = {
    "tesseract-identificador-localizado": 2,
    "tesseract-identificador-vetorial-localizado": 1,
}
_POLE_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:(?:POSTE|PONTO)\s+)?P\s*[-.:]?\s*0*(\d{1,4})(?![A-Z0-9])"
)
_SPAN_IDENTIFIER_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:VAO\s+)?V\s*0*(\d{1,4})\s*-\s*0*(\d{1,4})(?![A-Z0-9])"
)
_POLE_IDENTIFIED_CATEGORIES = {
    CategoriaElemento.POSTE,
    CategoriaElemento.ESTRUTURA_MT,
    CategoriaElemento.ESTRUTURA_BT,
    CategoriaElemento.EQUIPAMENTO,
}


@dataclass(frozen=True, slots=True)
class _OperationalLabel:
    value: str
    evidence: EvidenciaDocumento


def filtrar_propostas_identificadas(
    propostas: tuple[PropostaElemento, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
    *,
    distancia_maxima: float = _MAXIMUM_IDENTIFIER_DISTANCE,
) -> tuple[PropostaElemento, ...]:
    """Mantenha somente ativos vinculados a um identificador operacional numerado."""
    if distancia_maxima <= 0:
        raise ValueError("Distância máxima do identificador deve ser positiva")
    pole_labels, span_labels = _operational_labels(evidencias)
    identified: list[PropostaElemento] = []
    for proposal in propostas:
        labels = (
            pole_labels
            if proposal.categoria in _POLE_IDENTIFIED_CATEGORIES
            else span_labels
            if proposal.categoria is CategoriaElemento.CABO
            else ()
        )
        nearest = _nearest_label(proposal, labels, distancia_maxima)
        if nearest is not None:
            identified.append(_with_operational_label(proposal, nearest))
    return _select_unique_identifier_occurrences(
        tuple(identified),
        (*pole_labels, *span_labels),
    )


def _operational_labels(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[tuple[_OperationalLabel, ...], tuple[_OperationalLabel, ...]]:
    pole_labels: list[_OperationalLabel] = []
    span_labels: list[_OperationalLabel] = []
    for item in evidence:
        if item.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR} or not item.conteudo_bruto:
            continue
        text = normalized_text(item.conteudo_bruto)
        pole_match = _POLE_IDENTIFIER_PATTERN.search(text)
        if pole_match is not None and _is_operational_identifier_evidence(item, pole_match):
            point_number = int(pole_match.group(1))
            if point_number == 0:
                continue
            pole_labels.append(
                _OperationalLabel(
                    value=f"P{point_number}",
                    evidence=item,
                )
            )
            continue
        span_match = _SPAN_IDENTIFIER_PATTERN.search(text)
        if span_match is not None and _is_operational_identifier_evidence(item, span_match):
            origin_number = int(span_match.group(1))
            destination_number = int(span_match.group(2))
            if origin_number == 0 or destination_number == 0 or origin_number == destination_number:
                continue
            span_labels.append(
                _OperationalLabel(
                    value=f"V{origin_number}-{destination_number}",
                    evidence=item,
                )
            )

    def key(label: _OperationalLabel) -> tuple[str, str]:
        return label.value, str(label.evidence.id)

    return (
        tuple(sorted(_prefer_targeted_labels(pole_labels), key=key)),
        tuple(sorted(_prefer_targeted_labels(span_labels), key=key)),
    )


def _prefer_targeted_labels(labels: list[_OperationalLabel]) -> tuple[_OperationalLabel, ...]:
    """Prefira a Ã¢ncora localizada quando o mesmo identificador foi lido mais de uma vez."""
    grouped: dict[str, list[_OperationalLabel]] = {}
    for label in labels:
        grouped.setdefault(label.value, []).append(label)
    selected: list[_OperationalLabel] = []
    for value in sorted(grouped):
        candidates = grouped[value]
        targeted = tuple(
            label
            for label in candidates
            if _identifier_engine(label) in _TARGETED_IDENTIFIER_ENGINES
        )
        if not targeted:
            selected.extend(candidates)
            continue
        best_engine_priority = max(
            _TARGETED_IDENTIFIER_ENGINE_PRIORITY[_identifier_engine(label)] for label in targeted
        )
        selected.extend(
            label
            for label in targeted
            if _TARGETED_IDENTIFIER_ENGINE_PRIORITY[_identifier_engine(label)]
            == best_engine_priority
        )
    return tuple(selected)


def _identifier_engine(label: _OperationalLabel) -> str:
    return str(dict(label.evidence.atributos_extraidos).get("motor_ocr") or "")


def _select_unique_identifier_occurrences(
    proposals: tuple[PropostaElemento, ...],
    labels: tuple[_OperationalLabel, ...],
) -> tuple[PropostaElemento, ...]:
    """Mantenha uma ocorrÃªncia fÃ­sica por identificador de ponto ou vÃ£o do projeto."""
    grouped: dict[str, list[PropostaElemento]] = {}
    passthrough: list[PropostaElemento] = []
    for proposal in proposals:
        identifier = str(dict(proposal.atributos_sugeridos).get("identificador_operacional") or "")
        if not identifier:
            passthrough.append(proposal)
            continue
        grouped.setdefault(identifier, []).append(proposal)

    selected_ids = {proposal.id for proposal in passthrough}
    labels_by_value: dict[str, tuple[_OperationalLabel, ...]] = {
        value: tuple(label for label in labels if label.value == value) for value in grouped
    }
    for identifier, candidates in grouped.items():
        components = _occurrence_components(tuple(candidates))
        winning = max(
            components,
            key=lambda component: _occurrence_rank(
                component,
                labels_by_value.get(identifier, ()),
            ),
        )
        selected_ids.update(proposal.id for proposal in winning)
    return tuple(proposal for proposal in proposals if proposal.id in selected_ids)


def _occurrence_components(
    proposals: tuple[PropostaElemento, ...],
) -> tuple[tuple[PropostaElemento, ...], ...]:
    remaining = set(range(len(proposals)))
    components: list[tuple[PropostaElemento, ...]] = []
    while remaining:
        pending = [min(remaining)]
        remaining.remove(pending[0])
        indexes: list[int] = []
        while pending:
            current = pending.pop()
            indexes.append(current)
            connected = tuple(
                index
                for index in remaining
                if _proposal_distance(proposals[current], proposals[index])
                <= _MAXIMUM_OCCURRENCE_COMPONENT_DISTANCE
            )
            pending.extend(connected)
            remaining.difference_update(connected)
        components.append(tuple(proposals[index] for index in sorted(indexes)))
    return tuple(components)


def _occurrence_rank(
    proposals: tuple[PropostaElemento, ...],
    labels: tuple[_OperationalLabel, ...],
) -> tuple[int, int, int, int, float, float, tuple[str, ...]]:
    changed = tuple(
        proposal
        for proposal in proposals
        if proposal.situacao_projeto is not SituacaoProjeto.EXISTENTE
    )
    poles = tuple(
        proposal for proposal in proposals if proposal.categoria is CategoriaElemento.POSTE
    )
    changed_poles = tuple(
        proposal for proposal in poles if proposal.situacao_projeto is not SituacaoProjeto.EXISTENTE
    )
    label_distance = min(
        (
            _distance_to_geometry(center(label.evidence.geometria), proposal.geometria)
            for proposal in proposals
            for label in labels
            if label.evidence.pagina_id == proposal.geometria.pagina_id
        ),
        default=math.inf,
    )
    confidence = sum(float(proposal.confianca or 0) for proposal in proposals)
    return (
        len(changed),
        len(changed_poles),
        len(poles),
        len(proposals),
        -label_distance,
        confidence,
        tuple(sorted(str(proposal.id) for proposal in proposals)),
    )


def _proposal_distance(first: PropostaElemento, second: PropostaElemento) -> float:
    if first.geometria.pagina_id != second.geometria.pagina_id:
        return math.inf
    return math.dist(center(first.geometria), center(second.geometria))


def _is_operational_identifier_evidence(
    evidence: EvidenciaDocumento,
    match: re.Match[str],
) -> bool:
    engine = dict(evidence.atributos_extraidos).get("motor_ocr")
    return match.start() == 0 or engine in _TARGETED_IDENTIFIER_ENGINES


def _nearest_label(
    proposal: PropostaElemento,
    labels: tuple[_OperationalLabel, ...],
    maximum_distance: float,
) -> _OperationalLabel | None:
    eligible = tuple(
        label
        for label in labels
        if label.evidence.pagina_id == proposal.geometria.pagina_id
        and _distance_to_geometry(center(label.evidence.geometria), proposal.geometria)
        <= _maximum_distance_for_label(label, maximum_distance)
    )
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda label: (
            _distance_to_geometry(center(label.evidence.geometria), proposal.geometria),
            label.value,
            str(label.evidence.id),
        ),
    )


def _maximum_distance_for_label(
    label: _OperationalLabel,
    configured_maximum: float,
) -> float:
    engine = dict(label.evidence.atributos_extraidos).get("motor_ocr")
    if engine in _TARGETED_IDENTIFIER_ENGINES:
        return min(configured_maximum, _MAXIMUM_TARGETED_IDENTIFIER_DISTANCE)
    return configured_maximum


def _with_operational_label(
    proposal: PropostaElemento,
    label: _OperationalLabel,
) -> PropostaElemento:
    attributes = dict(proposal.atributos_sugeridos)
    attributes.update(
        {
            "identificador_operacional": label.value,
            "evidencia_identificador_id": str(label.evidence.id),
        }
    )
    category = "ponto" if proposal.categoria in _POLE_IDENTIFIED_CATEGORIES else "vão"
    return replace(
        proposal,
        evidencia_ids=tuple(sorted({*proposal.evidencia_ids, label.evidence.id}, key=str)),
        atributos_sugeridos=tuple(attributes.items()),
        justificativa=(
            f"{proposal.justificativa or ''} "
            f"O identificador operacional {label.value} confirmou o {category} de projeto."
        ).strip(),
    )


def _distance_to_geometry(
    point: tuple[float, float],
    geometry: GeometriaDocumento,
) -> float:
    points = tuple((float(item.x), float(item.y)) for item in geometry.pontos)
    if geometry.tipo is TipoGeometria.PONTO:
        return math.dist(point, points[0])
    if geometry.tipo is TipoGeometria.CAIXA:
        left = min(points[0][0], points[1][0])
        right = max(points[0][0], points[1][0])
        top = min(points[0][1], points[1][1])
        bottom = max(points[0][1], points[1][1])
        nearest = (
            min(right, max(left, point[0])),
            min(bottom, max(top, point[1])),
        )
        return math.dist(point, nearest)
    segments = tuple(pairwise(points))
    if geometry.tipo is TipoGeometria.POLIGONO:
        segments = (*segments, (points[-1], points[0]))
    return min(_distance_to_segment(point, start, end) for start, end in segments)


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    squared_length = delta_x * delta_x + delta_y * delta_y
    if squared_length == 0:
        return math.dist(point, start)
    projection = (
        (point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y
    ) / squared_length
    factor = min(1.0, max(0.0, projection))
    nearest = (start[0] + factor * delta_x, start[1] + factor * delta_y)
    return math.dist(point, nearest)


__all__ = ["filtrar_propostas_identificadas"]
