"""Agrupamento espacial dos resultados da análise em regiões de ocorrência."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
    ReferenciaProposta,
)
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.domain.enums import CategoriaElemento, TipoEvidencia
from zeny_project_handler.domain.values import (
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)

from .coordinate_pairs import detectar_pares_coordenadas

_DEFAULT_REGION_DISTANCE = 0.10
_COORDINATE_REGION_DISTANCE = 0.18
_POINT_ANCHOR_DISTANCE = 0.14
_POINT_LABEL_PATTERN = re.compile(
    r"^\s*(?:PONTO\s+)?P\s*[-.:]?\s*0*(\d{1,4})\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RegiaoAnalise:
    """Uma ocorrência localizada na folha e os resultados que acontecem nela."""

    id: UUID
    pagina_id: UUID
    geometria: GeometriaDocumento
    elemento_ids: tuple[UUID, ...]
    vinculo_ids: tuple[UUID, ...] = ()
    coordenada: CoordenadaCampo | None = None
    rotulo_ponto: str | None = None

    def __post_init__(self) -> None:
        elements = tuple(self.elemento_ids)
        links = tuple(self.vinculo_ids)
        if self.geometria.pagina_id != self.pagina_id:
            raise ValueError("Geometria da região deve pertencer à página informada")
        if not elements or len(set(elements)) != len(elements):
            raise ValueError("Região deve possuir elementos únicos")
        if len(set(links)) != len(links):
            raise ValueError("Região deve possuir vínculos únicos")
        object.__setattr__(self, "elemento_ids", elements)
        object.__setattr__(self, "vinculo_ids", links)


@dataclass(frozen=True, slots=True)
class _CoordinateCandidate:
    coordinate: CoordenadaCampo
    geometry: GeometriaDocumento


@dataclass(frozen=True, slots=True)
class _PointAnchor:
    label: str
    geometry: GeometriaDocumento


def agrupar_regioes_da_analise(
    propostas: tuple[ReferenciaProposta, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
    documentos: tuple[DocumentoProjeto, ...],
    *,
    ordem_paginas: tuple[UUID, ...] | None = None,
    distancia_maxima: float = _DEFAULT_REGION_DISTANCE,
) -> tuple[RegiaoAnalise, ...]:
    """Derive regiões estáveis sem transformar os resultados em um grafo."""
    if distancia_maxima <= 0:
        raise ValueError("Distância máxima de uma região deve ser positiva")
    elements = tuple(item for item in propostas if isinstance(item, PropostaElemento))
    relations = tuple(item for item in propostas if isinstance(item, PropostaRelacao))
    if not elements:
        return ()

    point_labels = _assign_point_labels(elements, _point_anchors(evidencias))
    components = _spatial_components(elements, distancia_maxima, point_labels)
    preliminary = tuple(
        _build_region(component, relations, point_labels) for component in components
    )
    coordinate_candidates = _coordinate_candidates(evidencias)
    assigned_coordinates = _assign_coordinates(preliminary, coordinate_candidates)
    regions = tuple(
        RegiaoAnalise(
            id=region.id,
            pagina_id=region.pagina_id,
            geometria=region.geometria,
            elemento_ids=region.elemento_ids,
            vinculo_ids=region.vinculo_ids,
            coordenada=(
                _coordinate_from_elements(region, elements) or assigned_coordinates.get(region.id)
            ),
            rotulo_ponto=region.rotulo_ponto,
        )
        for region in preliminary
    )
    default_page_order = tuple(page.id for document in documentos for page in document.paginas)
    reading_order = ordem_paginas or default_page_order
    page_order = {page_id: index for index, page_id in enumerate(reading_order)}
    return tuple(
        sorted(
            regions,
            key=lambda item: (
                page_order.get(item.pagina_id, len(page_order)),
                _center(item.geometria)[1],
                _center(item.geometria)[0],
                str(item.id),
            ),
        )
    )


def _spatial_components(
    elements: tuple[PropostaElemento, ...],
    maximum_distance: float,
    point_labels: dict[UUID, str],
) -> tuple[tuple[PropostaElemento, ...], ...]:
    parents = list(range(len(elements)))
    component_labels = [
        ({point_labels[element.id]} if element.id in point_labels else set())
        for element in elements
    ]

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        left_labels = component_labels[left_root]
        right_labels = component_labels[right_root]
        if left_labels and right_labels and left_labels != right_labels:
            return
        parents[right_root] = left_root
        component_labels[left_root] = left_labels | right_labels

    edges: list[tuple[float, str, str, int, int]] = []
    for left_index, left in enumerate(elements):
        for right_index in range(left_index + 1, len(elements)):
            right = elements[right_index]
            if left.geometria.pagina_id != right.geometria.pagina_id:
                continue
            distance = _regional_distance(left, right)
            if distance <= maximum_distance:
                edges.append(
                    (
                        distance,
                        str(min(left.id, right.id)),
                        str(max(left.id, right.id)),
                        left_index,
                        right_index,
                    )
                )
    for _distance, _left_id, _right_id, left_index, right_index in sorted(edges):
        union(left_index, right_index)

    grouped: dict[int, list[PropostaElemento]] = {}
    for index, element in enumerate(elements):
        grouped.setdefault(find(index), []).append(element)
    return tuple(
        tuple(
            sorted(
                component,
                key=lambda item: (
                    _center(item.geometria)[1],
                    _center(item.geometria)[0],
                    item.categoria.value,
                    str(item.id),
                ),
            )
        )
        for component in grouped.values()
    )


def _regional_distance(left: PropostaElemento, right: PropostaElemento) -> float:
    if CategoriaElemento.CABO in {left.categoria, right.categoria}:
        return math.dist(_center(left.geometria), _center(right.geometria))
    return _box_gap(left.geometria, right.geometria)


def _box_gap(left: GeometriaDocumento, right: GeometriaDocumento) -> float:
    left_x_min, left_y_min, left_x_max, left_y_max = _bounds(left)
    right_x_min, right_y_min, right_x_max, right_y_max = _bounds(right)
    x_gap = max(0.0, left_x_min - right_x_max, right_x_min - left_x_max)
    y_gap = max(0.0, left_y_min - right_y_max, right_y_min - left_y_max)
    return math.hypot(x_gap, y_gap)


def _build_region(
    elements: tuple[PropostaElemento, ...],
    relations: tuple[PropostaRelacao, ...],
    point_labels: dict[UUID, str],
) -> RegiaoAnalise:
    element_ids = tuple(item.id for item in elements)
    element_id_set = set(element_ids)
    link_ids = tuple(
        relation.id
        for relation in relations
        if (
            relation.origem_referencia_id in element_id_set
            or relation.destino_referencia_id in element_id_set
        )
    )
    page_id = elements[0].geometria.pagina_id
    identity = ":".join(sorted(map(str, element_ids)))
    return RegiaoAnalise(
        id=uuid5(page_id, f"regiao-analise:{identity}"),
        pagina_id=page_id,
        geometria=_combined_geometry(tuple(item.geometria for item in elements)),
        elemento_ids=element_ids,
        vinculo_ids=link_ids,
        rotulo_ponto=next(
            (point_labels[element.id] for element in elements if element.id in point_labels),
            None,
        ),
    )


def _point_anchors(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[_PointAnchor, ...]:
    anchors: list[_PointAnchor] = []
    for item in evidence:
        if item.tipo not in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}:
            continue
        match = _POINT_LABEL_PATTERN.fullmatch(item.conteudo_bruto or "")
        if match is None:
            continue
        label = f"P{int(match.group(1))}"
        anchors.append(_PointAnchor(label=label, geometry=item.geometria))
    return tuple(anchors)


def _assign_point_labels(
    elements: tuple[PropostaElemento, ...],
    anchors: tuple[_PointAnchor, ...],
) -> dict[UUID, str]:
    assignments: dict[UUID, str] = {}
    for element in elements:
        same_page = tuple(
            anchor for anchor in anchors if anchor.geometry.pagina_id == element.geometria.pagina_id
        )
        nearest = min(
            same_page,
            key=lambda anchor: math.dist(
                _center(element.geometria),
                _center(anchor.geometry),
            ),
            default=None,
        )
        if nearest is None:
            continue
        distance = math.dist(
            _center(element.geometria),
            _center(nearest.geometry),
        )
        if distance <= _POINT_ANCHOR_DISTANCE:
            assignments[element.id] = nearest.label
    return assignments


def _combined_geometry(geometries: tuple[GeometriaDocumento, ...]) -> GeometriaDocumento:
    page_id = geometries[0].pagina_id
    x_values = [float(point.x) for geometry in geometries for point in geometry.pontos]
    y_values = [float(point.y) for geometry in geometries for point in geometry.pontos]
    left, right = min(x_values), max(x_values)
    top, bottom = min(y_values), max(y_values)
    minimum_size = 0.004
    if right - left < minimum_size:
        center_x = (left + right) / 2
        left = max(0.0, center_x - minimum_size / 2)
        right = min(1.0, center_x + minimum_size / 2)
    if bottom - top < minimum_size:
        center_y = (top + bottom) / 2
        top = max(0.0, center_y - minimum_size / 2)
        bottom = min(1.0, center_y + minimum_size / 2)
    return GeometriaDocumento.caixa(
        page_id,
        PontoNormalizado(Decimal(str(left)), Decimal(str(top))),
        PontoNormalizado(Decimal(str(right)), Decimal(str(bottom))),
    )


def _coordinate_from_elements(
    region: RegiaoAnalise,
    elements: tuple[PropostaElemento, ...],
) -> CoordenadaCampo | None:
    region_ids = set(region.elemento_ids)
    values = [
        (Decimal(str(attributes["coordenada_leste"])), Decimal(str(attributes["coordenada_norte"])))
        for element in elements
        if element.id in region_ids
        if (attributes := dict(element.atributos_sugeridos))
        and attributes.get("coordenada_leste") is not None
        and attributes.get("coordenada_norte") is not None
    ]
    if not values:
        return None
    east, north = Counter(values).most_common(1)[0][0]
    return CoordenadaCampo(leste=east, norte=north, sistema_referencia="UTM")


def _coordinate_candidates(
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[_CoordinateCandidate, ...]:
    pairs = detectar_pares_coordenadas(
        evidence,
        distancia_maxima=_COORDINATE_REGION_DISTANCE,
        distancia_geometrias=_box_gap,
    )
    candidates: dict[tuple[UUID, int, int], _CoordinateCandidate] = {}
    for pair in pairs:
        key = (pair.geometria_leste.pagina_id, pair.leste, pair.norte)
        candidates[key] = _CoordinateCandidate(
            coordinate=CoordenadaCampo(
                leste=Decimal(pair.leste),
                norte=Decimal(pair.norte),
                sistema_referencia="UTM",
            ),
            geometry=_combined_geometry((pair.geometria_leste, pair.geometria_norte)),
        )
    return tuple(candidates.values())


def _assign_coordinates(
    regions: tuple[RegiaoAnalise, ...],
    candidates: tuple[_CoordinateCandidate, ...],
) -> dict[UUID, CoordenadaCampo]:
    assignments: dict[UUID, tuple[float, CoordenadaCampo]] = {}
    for candidate in candidates:
        same_page = tuple(
            region for region in regions if region.pagina_id == candidate.geometry.pagina_id
        )
        nearest = min(
            same_page,
            key=lambda region: _box_gap(region.geometria, candidate.geometry),
            default=None,
        )
        if nearest is None:
            continue
        distance = _box_gap(nearest.geometria, candidate.geometry)
        if distance > _COORDINATE_REGION_DISTANCE:
            continue
        previous = assignments.get(nearest.id)
        if previous is None or distance < previous[0]:
            assignments[nearest.id] = (distance, candidate.coordinate)
    return {region_id: value[1] for region_id, value in assignments.items()}


def _bounds(geometry: GeometriaDocumento) -> tuple[float, float, float, float]:
    x_values = [float(point.x) for point in geometry.pontos]
    y_values = [float(point.y) for point in geometry.pontos]
    return min(x_values), min(y_values), max(x_values), max(y_values)


def _center(geometry: GeometriaDocumento) -> tuple[float, float]:
    left, top, right, bottom = _bounds(geometry)
    return (left + right) / 2, (top + bottom) / 2
