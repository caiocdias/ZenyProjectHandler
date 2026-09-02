"""Regras geométricas para traçados e comprimentos de cabos anotados no desenho."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    TipoEvidencia,
    TipoGeometria,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .rule_support import center, normalized_text, point_distance, situation_from_evidence

_MAXIMUM_ANNOTATION_DISTANCE = 0.055
_MINIMUM_ENDPOINT_DISTANCE = 0.035
_MINIMUM_CABLE_PATH_LENGTH = 0.05
_MAXIMUM_PATH_ENDPOINT_DISTANCE = 0.10
_MAXIMUM_CABLE_LABEL_DISTANCE = 0.045
_MAXIMUM_SPAN_IDENTIFIER_DISTANCE = 0.060
_ASSOCIATION_AMBIGUITY_MARGIN = 0.004
_MEASUREMENT_AMBIGUITY_MARGIN = 0.003
_MAXIMUM_SUPERSESSION_MARK_DISTANCE = 0.012
_MAXIMUM_SUPERSESSION_MARK_LENGTH = 0.20
_ORIENTATION_SCORE_WEIGHT = 0.012
_LABELED_LENGTH_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:VAO|COMPRIMENTO|COMP|EXTENSAO|L)\.?"
    r"\s*[:=-]?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*M?(?![A-Z0-9])"
)
_LENGTH_WITH_UNIT_PATTERN = re.compile(
    r"(?<![A-Z0-9.,])(\d{1,4}(?:[.,]\d{1,2})?)"
    r"\s*M(?:ETRO|ETROS)?(?![A-Z0-9])"
)
_NON_SPAN_MEASUREMENT_PATTERN = re.compile(
    r"(?:^|[^A-Z0-9])(?:"
    r"H\.?\s*N\.?|ALTURA(?:\s+NOMINAL)?|ENGASTAMENTO|AREA|CAPACIDADE"
    r")\s*[:=.-]?\s*\d{1,4}(?:[.,]\d{1,2})?\s*M(?:ETRO|ETROS)?(?![A-Z0-9])"
)
_POINT_IDENTIFIER_PATTERN = re.compile(r"^P(\d{1,4})$")
_SPAN_IDENTIFIER_PATTERN = re.compile(r"^V(\d{1,4})-(\d{1,4})$")
_SPAN_IDENTIFIER_SEARCH_PATTERN = re.compile(
    r"(?<![A-Z0-9])(?:VAO\s+)?V\s*0*(\d{1,4})\s*-\s*0*(\d{1,4})(?![A-Z0-9])"
)
_TARGETED_IDENTIFIER_ENGINES = {
    "tesseract-identificador-localizado",
    "tesseract-identificador-vetorial-localizado",
}
_TARGETED_LINEAR_ENGINES = {
    "tesseract-rotulo-linear-retificado",
    "tesseract-comprimento-linear-retificado",
}


@dataclass(frozen=True, slots=True)
class _TracePath:
    evidence: EvidenciaDocumento
    geometry: GeometriaDocumento
    endpoint_poles: tuple[PropostaElemento | None, PropostaElemento | None]

    @property
    def endpoint_count(self) -> int:
        return sum(item is not None for item in self.endpoint_poles)


@dataclass(frozen=True, slots=True)
class _PathAssociation:
    path: _TracePath
    distance: float
    score: float


@dataclass(frozen=True, slots=True)
class _SpanLabel:
    value: str
    evidence: EvidenciaDocumento


@dataclass(frozen=True, slots=True)
class _MeasurementCandidate:
    value: Decimal
    evidence: EvidenciaDocumento
    distance: float
    projected_point: tuple[float, float]
    supersession_marker: EvidenciaDocumento | None


@dataclass(frozen=True, slots=True)
class _LengthResolution:
    current: _MeasurementCandidate | None
    superseded: _MeasurementCandidate | None


def associar_tracados_de_cabos(
    propostas: tuple[PropostaElemento, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
    catalogo: CatalogoTecnico,
) -> tuple[PropostaElemento, ...]:
    """Associe rótulo, traçado, identificador e comprimento sem propagar proximidade."""
    poles = tuple(
        proposal for proposal in propostas if proposal.categoria is CategoriaElemento.POSTE
    )
    paths = _trace_paths(evidencias, poles)
    evidence_by_id = {item.id: item for item in evidencias}
    identifiers_by_path = _span_identifiers_by_path(paths, evidencias)
    associated: list[PropostaElemento] = []
    for proposal in propostas:
        if proposal.categoria is not CategoriaElemento.CABO:
            associated.append(proposal)
            continue
        cable = _associate_cable(
            proposal,
            paths,
            identifiers_by_path,
            evidence_by_id,
            evidencias,
            catalogo,
        )
        if cable is not None:
            associated.append(cable)
    return tuple(associated)


def _trace_paths(
    evidence: tuple[EvidenciaDocumento, ...],
    poles: tuple[PropostaElemento, ...],
) -> tuple[_TracePath, ...]:
    return tuple(
        _canonical_trace_path(item, poles)
        for item in sorted(evidence, key=lambda current: str(current.id))
        if _is_trace_path(item)
    )


def _is_trace_path(evidence: EvidenciaDocumento) -> bool:
    geometry = evidence.geometria
    attributes = dict(evidence.atributos_extraidos)
    points = tuple((float(item.x), float(item.y)) for item in geometry.pontos)
    return bool(
        evidence.tipo is TipoEvidencia.VETOR
        and geometry.tipo is TipoGeometria.POLILINHA
        and len(points) >= 2
        and not bool(attributes.get("fechado", False))
        and math.dist(points[0], points[-1]) > 0.002
        and _solid_path(attributes.get("tracejado"))
        and _geometry_length(geometry) >= _MINIMUM_CABLE_PATH_LENGTH
        and not _is_burgundy_vector(evidence)
    )


def _canonical_trace_path(
    evidence: EvidenciaDocumento,
    poles: tuple[PropostaElemento, ...],
) -> _TracePath:
    geometry = evidence.geometria
    endpoints = (
        _nearest_endpoint_pole(geometry.pontos[0], evidence.pagina_id, poles),
        _nearest_endpoint_pole(geometry.pontos[-1], evidence.pagina_id, poles),
    )
    if endpoints[0] is not None and endpoints[1] is not None and endpoints[0].id == endpoints[1].id:
        first_distance = point_distance(
            (float(geometry.pontos[0].x), float(geometry.pontos[0].y)),
            center(endpoints[0].geometria),
        )
        last_distance = point_distance(
            (float(geometry.pontos[-1].x), float(geometry.pontos[-1].y)),
            center(endpoints[1].geometria),
        )
        endpoints = (
            (endpoints[0], None) if first_distance <= last_distance else (None, endpoints[1])
        )
    first_key = _endpoint_order_key(endpoints[0], geometry.pontos[0])
    last_key = _endpoint_order_key(endpoints[1], geometry.pontos[-1])
    if first_key > last_key:
        geometry = GeometriaDocumento.polilinha(
            geometry.pagina_id,
            tuple(reversed(geometry.pontos)),
        )
        endpoints = (endpoints[1], endpoints[0])
    return _TracePath(evidence=evidence, geometry=geometry, endpoint_poles=endpoints)


def _nearest_endpoint_pole(
    endpoint: PontoNormalizado,
    page_id: UUID,
    poles: tuple[PropostaElemento, ...],
) -> PropostaElemento | None:
    coordinate = (float(endpoint.x), float(endpoint.y))
    same_page = tuple(pole for pole in poles if pole.geometria.pagina_id == page_id)
    nearest = min(
        same_page,
        key=lambda pole: point_distance(coordinate, center(pole.geometria)),
        default=None,
    )
    if nearest is None:
        return None
    return (
        nearest
        if point_distance(coordinate, center(nearest.geometria)) <= _MAXIMUM_PATH_ENDPOINT_DISTANCE
        else None
    )


def _endpoint_order_key(
    proposal: PropostaElemento | None,
    endpoint: PontoNormalizado,
) -> tuple[object, ...]:
    if proposal is not None:
        identifier = str(dict(proposal.atributos_sugeridos).get("identificador_operacional") or "")
        match = _POINT_IDENTIFIER_PATTERN.fullmatch(identifier)
        if match is not None:
            return 0, int(match.group(1)), ""
        return 1, 0, str(proposal.id)
    return 2, float(endpoint.x), float(endpoint.y)


def _associate_cable(
    cable: PropostaElemento,
    paths: tuple[_TracePath, ...],
    identifiers_by_path: dict[UUID, _SpanLabel],
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    evidence: tuple[EvidenciaDocumento, ...],
    catalog: CatalogoTecnico,
) -> PropostaElemento | None:
    label = _cable_label_evidence(cable, evidence_by_id)
    association = (
        _unique_path_association(label, paths, _MAXIMUM_CABLE_LABEL_DISTANCE)
        if label is not None
        else None
    )
    if association is None:
        return cable if label is not None and _has_nearby_path(label, paths) else None
    path = association.path
    identifier_label = identifiers_by_path.get(path.evidence.id)
    geometry, endpoint_poles = _oriented_path(path, identifier_label)
    attributes = dict(cable.atributos_sugeridos)
    for key in (
        "comprimento_m",
        "comprimento_origem",
        "evidencia_comprimento_id",
        "comprimento_substituido_m",
        "evidencia_comprimento_substituido_id",
        "evidencia_supersessao_id",
        "alteracao_cabo",
        "identificador_operacional",
        "evidencia_identificador_id",
        "ponto_operacional_origem",
        "ponto_operacional_destino",
    ):
        attributes.pop(key, None)
    attributes.update(
        {
            "geometria_cabo_origem": "vetor_associado_geometricamente",
            "evidencia_geometria_id": str(path.evidence.id),
        }
    )
    evidence_ids = {*cable.evidencia_ids, path.evidence.id}
    justification_parts = [
        cable.justificativa or "",
        "O rótulo do cabo foi associado ao traçado por geometria e orientação sem empate.",
    ]
    if identifier_label is not None:
        identifier_endpoints = _identifier_endpoint_labels(identifier_label.value)
        origin_label = _pole_identifier(endpoint_poles[0])
        destination_label = _pole_identifier(endpoint_poles[1])
        if identifier_endpoints is not None:
            origin_label = origin_label or identifier_endpoints[0]
            destination_label = destination_label or identifier_endpoints[1]
        if origin_label is not None and destination_label is not None:
            attributes.update(
                {
                    "ponto_operacional_origem": origin_label,
                    "ponto_operacional_destino": destination_label,
                }
            )
        attributes.update(
            {
                "identificador_operacional": identifier_label.value,
                "evidencia_identificador_id": str(identifier_label.evidence.id),
            }
        )
        evidence_ids.add(identifier_label.evidence.id)
        match = _SPAN_IDENTIFIER_PATTERN.fullmatch(identifier_label.value)
        if match is not None:
            justification_parts.append(
                f"O identificador {identifier_label.value} fixou as extremidades em "
                f"P{int(match.group(1))} e P{int(match.group(2))}."
            )
    resolution = _resolve_length(path, paths, evidence)
    situation = situation_from_evidence(path.evidence, CategoriaElemento.CABO, catalog)
    situation = situation or cable.situacao_projeto
    if resolution.current is not None:
        current = resolution.current
        attributes.update(
            {
                "comprimento_m": current.value,
                "comprimento_origem": "anotacao_desenho",
                "evidencia_comprimento_id": str(current.evidence.id),
            }
        )
        evidence_ids.add(current.evidence.id)
        if resolution.superseded is not None:
            superseded = resolution.superseded
            assert superseded.supersession_marker is not None
            attributes.update(
                {
                    "comprimento_substituido_m": superseded.value,
                    "evidencia_comprimento_substituido_id": str(superseded.evidence.id),
                    "evidencia_supersessao_id": str(superseded.supersession_marker.id),
                    "alteracao_cabo": (
                        "REDUCAO_COMPRIMENTO"
                        if superseded.value > current.value
                        else "ALTERACAO_COMPRIMENTO"
                    ),
                }
            )
            evidence_ids.update((superseded.evidence.id, superseded.supersession_marker.id))
            situation = SituacaoProjeto.ALTERAR
            justification_parts.append(
                f"A medida {superseded.value} m foi riscada localmente e substituída por "
                f"{current.value} m; o cabo sobrevivente foi classificado como alteração."
            )
    return replace(
        cable,
        situacao_projeto=situation,
        geometria=geometry,
        evidencia_ids=tuple(sorted(evidence_ids, key=str)),
        atributos_sugeridos=tuple(sorted(attributes.items())),
        justificativa=" ".join(part.strip() for part in justification_parts if part.strip()),
    )


def _has_nearby_path(
    source: EvidenciaDocumento,
    paths: tuple[_TracePath, ...],
) -> bool:
    return any(
        path.geometry.pagina_id == source.pagina_id
        and _distance_to_geometry(center(source.geometria), path.geometry)[0]
        <= _MAXIMUM_CABLE_LABEL_DISTANCE
        for path in paths
    )


def _cable_label_evidence(
    cable: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
) -> EvidenciaDocumento | None:
    token = dict(cable.atributos_sugeridos).get("evidencia_rotulo_id")
    if token is None:
        return None
    return next(
        (item for identifier, item in evidence_by_id.items() if str(identifier) == str(token)),
        None,
    )


def _span_identifiers_by_path(
    paths: tuple[_TracePath, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> dict[UUID, _SpanLabel]:
    candidates: dict[UUID, list[tuple[float, _SpanLabel]]] = {}
    for label in _span_labels(evidence):
        association = _unique_path_association(
            label.evidence,
            paths,
            _MAXIMUM_SPAN_IDENTIFIER_DISTANCE,
        )
        if association is None or not _identifier_matches_endpoints(label.value, association.path):
            continue
        candidates.setdefault(association.path.evidence.id, []).append((association.score, label))
    selected: dict[UUID, _SpanLabel] = {}
    for path_id, options in candidates.items():
        best_by_value: dict[str, tuple[float, _SpanLabel]] = {}
        for score, label in sorted(
            options,
            key=lambda item: (item[0], item[1].value, str(item[1].evidence.id)),
        ):
            best_by_value.setdefault(label.value, (score, label))
        ranked = sorted(
            best_by_value.values(),
            key=lambda item: (item[0], item[1].value, str(item[1].evidence.id)),
        )
        if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= _ASSOCIATION_AMBIGUITY_MARGIN:
            continue
        selected[path_id] = ranked[0][1]
    return selected


def _span_labels(evidence: tuple[EvidenciaDocumento, ...]) -> tuple[_SpanLabel, ...]:
    labels: list[_SpanLabel] = []
    for item in sorted(evidence, key=lambda current: str(current.id)):
        if item.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR} or not item.conteudo_bruto:
            continue
        text = normalized_text(item.conteudo_bruto)
        match = _SPAN_IDENTIFIER_SEARCH_PATTERN.search(text)
        engine = str(dict(item.atributos_extraidos).get("motor_ocr") or "")
        if match is None or (match.start() != 0 and engine not in _TARGETED_IDENTIFIER_ENGINES):
            continue
        origin = int(match.group(1))
        destination = int(match.group(2))
        if origin == 0 or destination == 0 or origin == destination:
            continue
        labels.append(_SpanLabel(f"V{origin}-{destination}", item))
    return tuple(labels)


def _identifier_matches_endpoints(identifier: str, path: _TracePath) -> bool:
    match = _SPAN_IDENTIFIER_PATTERN.fullmatch(identifier)
    if match is None:
        return False
    expected = {f"P{int(match.group(1))}", f"P{int(match.group(2))}"}
    observed = {
        label for pole in path.endpoint_poles if (label := _pole_identifier(pole)) is not None
    }
    return not observed or observed.issubset(expected)


def _oriented_path(
    path: _TracePath,
    label: _SpanLabel | None,
) -> tuple[
    GeometriaDocumento,
    tuple[PropostaElemento | None, PropostaElemento | None],
]:
    geometry = path.geometry
    endpoints = path.endpoint_poles
    if label is None:
        return geometry, endpoints
    identifier_endpoints = _identifier_endpoint_labels(label.value)
    if identifier_endpoints is None:
        return geometry, endpoints
    origin_label, destination_label = identifier_endpoints
    first_label = _pole_identifier(endpoints[0])
    second_label = _pole_identifier(endpoints[1])
    if first_label == destination_label or second_label == origin_label:
        return (
            GeometriaDocumento.polilinha(
                geometry.pagina_id,
                tuple(reversed(geometry.pontos)),
            ),
            (endpoints[1], endpoints[0]),
        )
    return geometry, endpoints


def _identifier_endpoint_labels(identifier: str) -> tuple[str, str] | None:
    match = _SPAN_IDENTIFIER_PATTERN.fullmatch(identifier)
    if match is None:
        return None
    return f"P{int(match.group(1))}", f"P{int(match.group(2))}"


def _pole_identifier(proposal: PropostaElemento | None) -> str | None:
    if proposal is None:
        return None
    value = str(dict(proposal.atributos_sugeridos).get("identificador_operacional") or "")
    return value if _POINT_IDENTIFIER_PATTERN.fullmatch(value) is not None else None


def _unique_path_association(
    source: EvidenciaDocumento,
    paths: tuple[_TracePath, ...],
    maximum_distance: float,
) -> _PathAssociation | None:
    source_angle = _reliable_label_angle(source)
    candidates: list[_PathAssociation] = []
    for path in paths:
        if path.geometry.pagina_id != source.pagina_id:
            continue
        distance, _, segment_angle = _distance_to_geometry(center(source.geometria), path.geometry)
        if distance > maximum_distance:
            continue
        orientation_penalty = 0.0
        if source_angle is not None:
            orientation_penalty = (
                _undirected_angle_difference(source_angle, segment_angle) / 90.0
            ) * _ORIENTATION_SCORE_WEIGHT
        score = distance + orientation_penalty - min(path.endpoint_count, 2) * 0.0005
        candidates.append(_PathAssociation(path, distance, score))
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.score,
            item.distance,
            -item.path.endpoint_count,
            str(item.path.evidence.id),
        ),
    )
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[1].score - ranked[0].score <= _ASSOCIATION_AMBIGUITY_MARGIN:
        return None
    return ranked[0]


def _reliable_label_angle(evidence: EvidenciaDocumento) -> float | None:
    attributes = dict(evidence.atributos_extraidos)
    engine = str(attributes.get("motor_ocr") or "")
    if engine not in _TARGETED_LINEAR_ENGINES:
        return None
    raw_rotation = attributes.get("rotacao_graus", 0)
    if not isinstance(raw_rotation, str | int | Decimal):
        return None
    try:
        return float(raw_rotation) % 180
    except (TypeError, ValueError):
        return None


def _undirected_angle_difference(first: float, second: float) -> float:
    difference = abs((first - second) % 180)
    return min(difference, 180 - difference)


def _resolve_length(
    target: _TracePath,
    paths: tuple[_TracePath, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> _LengthResolution:
    candidates: list[_MeasurementCandidate] = []
    for item in sorted(evidence, key=lambda current: str(current.id)):
        value = _measurement_value(item)
        if value is None:
            continue
        association = _unique_path_association(item, paths, _MAXIMUM_ANNOTATION_DISTANCE)
        if association is None or association.path.evidence.id != target.evidence.id:
            continue
        distance, projected, _ = _distance_to_geometry(center(item.geometria), target.geometry)
        if _measurement_is_at_endpoint(item, target.geometry, projected):
            continue
        candidates.append(
            _MeasurementCandidate(
                value=value,
                evidence=item,
                distance=distance,
                projected_point=projected,
                supersession_marker=_supersession_marker(item, evidence),
            )
        )
    current = _select_measurement(
        tuple(item for item in candidates if item.supersession_marker is None)
    )
    superseded = _select_measurement(
        tuple(
            item
            for item in candidates
            if item.supersession_marker is not None
            and (current is None or item.value != current.value)
        )
    )
    return _LengthResolution(current=current, superseded=superseded)


def detectar_comprimento_anotado(
    geometria_cabo: GeometriaDocumento,
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[Decimal, EvidenciaDocumento] | None:
    """Localize medida vigente; uma medida riscada nunca é retornada como comprimento."""
    candidates: list[_MeasurementCandidate] = []
    for item in sorted(evidencias, key=lambda current: str(current.id)):
        value = _measurement_value(item)
        if value is None:
            continue
        distance, projected, _ = _distance_to_geometry(center(item.geometria), geometria_cabo)
        if distance > _MAXIMUM_ANNOTATION_DISTANCE or _measurement_is_at_endpoint(
            item, geometria_cabo, projected
        ):
            continue
        marker = _supersession_marker(item, evidencias)
        if marker is not None:
            continue
        candidates.append(_MeasurementCandidate(value, item, distance, projected, None))
    selected = _select_measurement(tuple(candidates))
    return (selected.value, selected.evidence) if selected is not None else None


def _measurement_value(evidence: EvidenciaDocumento) -> Decimal | None:
    if evidence.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR} or not evidence.conteudo_bruto:
        return None
    return _length_from_text(evidence.conteudo_bruto)


def _measurement_is_at_endpoint(
    evidence: EvidenciaDocumento,
    geometry: GeometriaDocumento,
    projected: tuple[float, float],
) -> bool:
    targeted = (
        dict(evidence.atributos_extraidos).get("motor_ocr")
        == "tesseract-comprimento-linear-retificado"
    )
    if targeted or len(geometry.pontos) < 2:
        return False
    evidence_center = center(evidence.geometria)
    endpoints = (
        (float(geometry.pontos[0].x), float(geometry.pontos[0].y)),
        (float(geometry.pontos[-1].x), float(geometry.pontos[-1].y)),
    )
    return (
        min(math.dist(evidence_center, endpoint) for endpoint in endpoints)
        < (_MINIMUM_ENDPOINT_DISTANCE)
        or min(math.dist(projected, endpoint) for endpoint in endpoints) < 0.005
    )


def _select_measurement(
    candidates: tuple[_MeasurementCandidate, ...],
) -> _MeasurementCandidate | None:
    if not candidates:
        return None
    best_by_value: dict[Decimal, _MeasurementCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (item.distance, str(item.evidence.id)),
    ):
        best_by_value.setdefault(candidate.value, candidate)
    ranked = sorted(
        best_by_value.values(),
        key=lambda item: (item.distance, item.value, str(item.evidence.id)),
    )
    if len(ranked) > 1 and ranked[1].distance - ranked[0].distance <= _MEASUREMENT_AMBIGUITY_MARGIN:
        return None
    return ranked[0]


def _supersession_marker(
    measurement: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
) -> EvidenciaDocumento | None:
    measurement_center = center(measurement.geometria)
    candidates: list[tuple[float, str, EvidenciaDocumento]] = []
    for item in evidence:
        if item.pagina_id != measurement.pagina_id or not _is_burgundy_vector(item):
            continue
        length = _geometry_length(item.geometria)
        if not 0.005 <= length <= _MAXIMUM_SUPERSESSION_MARK_LENGTH:
            continue
        distance, projected, _ = _distance_to_geometry(measurement_center, item.geometria)
        if distance > _MAXIMUM_SUPERSESSION_MARK_DISTANCE:
            continue
        if not _point_overlaps_measurement(projected, measurement.geometria):
            continue
        nearest_measurement = _nearest_measurement_for_marker(item, evidence)
        if nearest_measurement is None or nearest_measurement.id != measurement.id:
            continue
        candidates.append((distance, str(item.id), item))
    return min(candidates, default=(0.0, "", None))[2]


def _nearest_measurement_for_marker(
    marker: EvidenciaDocumento,
    evidence: tuple[EvidenciaDocumento, ...],
) -> EvidenciaDocumento | None:
    candidates: list[tuple[float, str, EvidenciaDocumento]] = []
    for item in evidence:
        if item.pagina_id != marker.pagina_id or _measurement_value(item) is None:
            continue
        distance, projected, _ = _distance_to_geometry(center(item.geometria), marker.geometria)
        if distance > _MAXIMUM_SUPERSESSION_MARK_DISTANCE:
            continue
        if not _point_overlaps_measurement(projected, item.geometria):
            continue
        candidates.append((distance, str(item.id), item))
    ranked = sorted(candidates)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= _MEASUREMENT_AMBIGUITY_MARGIN:
        return None
    return ranked[0][2]


def _point_overlaps_measurement(
    point: tuple[float, float],
    geometry: GeometriaDocumento,
) -> bool:
    if geometry.tipo is TipoGeometria.PONTO:
        return math.dist(point, center(geometry)) <= _MAXIMUM_SUPERSESSION_MARK_DISTANCE
    xs = tuple(float(item.x) for item in geometry.pontos)
    ys = tuple(float(item.y) for item in geometry.pontos)
    tolerance = 0.003
    return (
        min(xs) - tolerance <= point[0] <= max(xs) + tolerance
        and min(ys) - tolerance <= point[1] <= max(ys) + tolerance
    )


def _is_burgundy_vector(evidence: EvidenciaDocumento) -> bool:
    if evidence.tipo is not TipoEvidencia.VETOR:
        return False
    attributes = dict(evidence.atributos_extraidos)
    for key in ("cor", "cor_contorno", "cor_preenchimento"):
        value = str(attributes.get(key) or "")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            continue
        red, green, blue = (int(value[index : index + 2], 16) for index in (1, 3, 5))
        if 96 <= red <= 176 and green <= 48 and blue <= 80 and red - max(green, blue) >= 48:
            return True
    return False


def _solid_path(value: object) -> bool:
    dashed = re.sub(r"\s+", "", str(value or "")).casefold()
    return dashed in {"", "[]", "[]0"}


def _geometry_length(geometry: GeometriaDocumento) -> float:
    points = tuple((float(item.x), float(item.y)) for item in geometry.pontos)
    return sum(math.dist(start, end) for start, end in pairwise(points))


def _length_from_text(text: str) -> Decimal | None:
    normalized = normalized_text(text)
    match = _LABELED_LENGTH_PATTERN.search(normalized)
    if match is None:
        if _NON_SPAN_MEASUREMENT_PATTERN.search(normalized) is not None:
            return None
        match = _LENGTH_WITH_UNIT_PATTERN.search(normalized)
    if match is None:
        return None
    try:
        length = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return length if Decimal(0) < length <= Decimal(2000) else None


def _distance_to_geometry(
    point: tuple[float, float],
    geometry: GeometriaDocumento,
) -> tuple[float, tuple[float, float], float]:
    points = tuple((float(item.x), float(item.y)) for item in geometry.pontos)
    if len(points) == 1:
        return math.dist(point, points[0]), points[0], 0.0
    return min(
        (_distance_to_segment(point, start, end) for start, end in pairwise(points)),
        key=lambda item: item[0],
    )


def _distance_to_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, tuple[float, float], float]:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    squared_length = delta_x * delta_x + delta_y * delta_y
    if squared_length == 0:
        return math.dist(point, start), start, 0.0
    projection = (
        (point[0] - start[0]) * delta_x + (point[1] - start[1]) * delta_y
    ) / squared_length
    factor = min(1.0, max(0.0, projection))
    nearest = (start[0] + factor * delta_x, start[1] + factor * delta_y)
    angle = math.degrees(math.atan2(delta_y, delta_x)) % 180
    return math.dist(point, nearest), nearest, angle
