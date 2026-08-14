"""Fatos de conformidade inferidos da topologia confirmada e da simbologia."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler.domain.catalog import (
    JsonPrimitive,
    TipoCabo,
    TipoEquipamento,
    TipoEstruturaMt,
    TipoPoste,
)
from zeny_project_handler.domain.compliance import FatoConformidade, TipoEscopoConformidade
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    NivelRede,
    SituacaoProjeto,
)
from zeny_project_handler.domain.project import (
    Cabo,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
)
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado

from .compliance_fact_providers import ContextoProvedorFatos, criar_fato_conformidade

_ORIGEM = "TOPOLOGIA_E_SIMBOLOGIA"
_INCIDENT_ENDPOINT_DISTANCE = 0.02
_SYMBOL_POLE_DISTANCE = 0.075
_ANCHOR_INTERVAL_M = Decimal(500)
_NEUTRAL_GROUNDING_INTERVAL_M = Decimal(200)
_COMPACT_TEMP_GROUNDING_INTERVAL_M = Decimal(160)


class _GeometryCarrier(Protocol):
    @property
    def geometria(self) -> GeometriaDocumento | None: ...


@dataclass(frozen=True, slots=True)
class _RouteGroup:
    key: tuple[str, ...]
    pole_path: tuple[UUID, ...]
    cables: tuple[Cabo, ...]
    length_m: Decimal | None


@dataclass(frozen=True, slots=True)
class _RouteEdge:
    index: int
    first_pole_id: UUID
    second_pole_id: UUID
    length_m: Decimal


@dataclass(frozen=True, slots=True)
class _PathAssessment:
    total_length_m: Decimal
    largest_component_m: Decimal
    maximum_uninterrupted_m: Decimal | None
    maximum_uninterrupted_geometry: GeometriaDocumento | None
    complete: bool


def medir_extensao_rede_instalar(
    projeto: Projeto,
) -> tuple[Decimal | None, bool, GeometriaDocumento | None]:
    """Meça rotas instaladas uma vez quando cabos paralelos usam o mesmo percurso de postes."""
    cables = tuple(
        item
        for item in projeto.elementos
        if isinstance(item, Cabo) and item.situacao is SituacaoProjeto.INSTALAR
    )
    if not cables:
        return None, False, None
    points = {item.id: item for item in projeto.pontos_rede}
    groups = _route_groups(cables, points)
    measured = tuple(group for group in groups if group.length_m is not None)
    length = sum((group.length_m or Decimal() for group in measured), Decimal())
    complete = len(measured) == len(groups) and all(len(group.pole_path) >= 2 for group in groups)
    geometry = next((item.geometria for item in cables if item.geometria is not None), None)
    return (length if measured else None), complete, geometry


def prover_fatos_topologicos(contexto: ContextoProvedorFatos) -> tuple[FatoConformidade, ...]:
    """Publique fatos objetivos sem depender de confirmação manual adicional."""
    sessao = contexto.sessao
    proposals = {
        p.id: p
        for p in sessao.propostas
        if isinstance(p, PropostaElemento) and p.estado_revisao is not EstadoRevisao.REJEITADA
    }
    confirmed = {e.id: e for e in sessao.projeto.elementos}
    by_proposal = {
        d.proposta_id: confirmed[d.elemento_confirmado_id]
        for d in sessao.decisoes
        if d.elemento_confirmado_id in confirmed
    }
    evidence = {e.id: e for e in sessao.evidencias}
    items = {i.id: i for i in sessao.catalogo.itens}
    option_codes = {o.id: o.codigo for g in sessao.catalogo.grupos_opcao for o in g.opcoes}
    points = {p.id: p for p in sessao.projeto.pontos_rede}
    pole_types = {i.id: i for i in sessao.catalogo.itens if isinstance(i, TipoPoste)}
    compatible = {(c.tipo_estrutura_id, c.tipo_cabo_id) for c in sessao.catalogo.compatibilidades}
    page_sizes = {
        page.id: (page.largura_pontos, page.altura_pontos)
        for document in sessao.projeto.documentos
        for page in document.paginas
    }
    geometric_cables = tuple(
        proposal
        for proposal in proposals.values()
        if proposal.categoria is CategoriaElemento.CABO
        and proposal.situacao_projeto is not SituacaoProjeto.REMOVER
        and not isinstance(by_proposal.get(proposal.id), Cabo)
    )
    region_targets = {
        a.referencia_id: a for a in contexto.alvos if a.tipo is TipoEscopoConformidade.REGIAO
    }
    project_target = next(
        (a for a in contexto.alvos if a.tipo is TipoEscopoConformidade.PROJETO),
        None,
    )
    result: list[FatoConformidade] = []

    def ev(*props: PropostaElemento) -> tuple[EvidenciaDocumento, ...]:
        ids = dict.fromkeys(i for p in props for i in p.evidencia_ids)
        return tuple(evidence[i] for i in ids if i in evidence)

    def equipment_class(prop: PropostaElemento) -> str:
        attributes = dict(prop.atributos_sugeridos)
        raw = (
            attributes.get("classe_equipamento")
            if attributes.get("reconhecido_por_simbologia") is True
            else None
        )
        catalog_item = (
            items.get(prop.tipo_catalogo_sugerido_id)
            if prop.tipo_catalogo_sugerido_id is not None
            else None
        )
        if isinstance(catalog_item, TipoEquipamento):
            raw = option_codes.get(catalog_item.classe_equipamento_opcao_id, raw)
        return _normalize_class(raw)

    def cable_technology(cable: Cabo | PropostaElemento) -> str:
        catalog_id = (
            cable.tipo_catalogo_id if isinstance(cable, Cabo) else cable.tipo_catalogo_sugerido_id
        )
        catalog_item = items.get(catalog_id) if catalog_id is not None else None
        if not isinstance(catalog_item, TipoCabo):
            return ""
        return option_codes.get(catalog_item.tecnologia_rede_opcao_id, "")

    def cable_level(cable: Cabo | PropostaElemento) -> str:
        catalog_id = (
            cable.tipo_catalogo_id if isinstance(cable, Cabo) else cable.tipo_catalogo_sugerido_id
        )
        catalog_item = items.get(catalog_id) if catalog_id is not None else None
        if not isinstance(catalog_item, TipoCabo):
            return ""
        return option_codes.get(catalog_item.nivel_tensao_opcao_id, "")

    def add(
        target_id: UUID,
        key: str,
        value: JsonPrimitive,
        props: tuple[PropostaElemento, ...] = (),
        geometry: GeometriaDocumento | None = None,
    ) -> None:
        result.append(
            criar_fato_conformidade(
                target_id, key, value, _ORIGEM, evidencias=ev(*props), geometria=geometry
            )
        )

    incident: dict[UUID, list[Cabo]] = defaultdict(list)
    for element in confirmed.values():
        if isinstance(element, Cabo) and element.situacao is not SituacaoProjeto.REMOVER:
            for point_id in (element.ponto_origem_id, element.ponto_destino_id):
                point = points.get(point_id)
                if point and point.poste_id:
                    incident[point.poste_id].append(element)

    proposal_poles = _associate_proposals_to_poles(
        tuple(proposals.values()),
        by_proposal,
        tuple(item for item in confirmed.values() if isinstance(item, Poste)),
        page_sizes,
    )
    classes_by_pole: dict[UUID, dict[str, list[PropostaElemento]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for proposal in proposals.values():
        pole_id = proposal_poles.get(proposal.id)
        equipment_class_code = equipment_class(proposal)
        if (
            pole_id is not None
            and equipment_class_code
            and proposal.situacao_projeto is not SituacaoProjeto.REMOVER
        ):
            classes_by_pole[pole_id][equipment_class_code].append(proposal)
    grounded_poles = {
        pole_id for pole_id, classes in classes_by_pole.items() if classes.get("ATERRAMENTO")
    }

    active_cables = tuple(
        element
        for element in confirmed.values()
        if isinstance(element, Cabo) and element.situacao is not SituacaoProjeto.REMOVER
    )
    compact_cables = tuple(
        element for element in active_cables if cable_technology(element) == "PROTEGIDA"
    )
    anchor_poles = {
        element.poste_id
        for element in confirmed.values()
        if isinstance(element, EstruturaMt)
        and element.situacao is not SituacaoProjeto.REMOVER
        and isinstance((catalog_item := items.get(element.tipo_catalogo_id)), TipoEstruturaMt)
        and catalog_item.ancoragem
    }
    compact_assessment = _assess_paths(compact_cables, points, anchor_poles)
    compact_grounding = _assess_paths(compact_cables, points, grounded_poles)
    neutral_cables = tuple(
        element
        for element in active_cables
        if isinstance((catalog_item := items.get(element.tipo_catalogo_id)), TipoCabo)
        and _is_neutral_cable(catalog_item)
    )
    neutral_grounding = _assess_paths(neutral_cables, points, grounded_poles)
    if project_target is not None and compact_assessment is not None:
        geometry = next(
            (item.geometria for item in compact_cables if item.geometria is not None),
            None,
        )
        add(
            project_target.id,
            "projeto.rede_compacta_extensao_m",
            compact_assessment.total_length_m,
            geometry=geometry,
        )
        add(
            project_target.id,
            "projeto.rede_compacta_maior_componente_m",
            compact_assessment.largest_component_m,
            geometry=geometry,
        )
        add(
            project_target.id,
            "projeto.rede_compacta_ancoragem_avaliada",
            compact_assessment.complete,
            geometry=geometry,
        )
        if compact_assessment.complete and compact_assessment.maximum_uninterrupted_m is not None:
            interval_geometry = compact_assessment.maximum_uninterrupted_geometry or geometry
            add(
                project_target.id,
                "projeto.rede_compacta_maior_trecho_sem_ancoragem_m",
                compact_assessment.maximum_uninterrupted_m,
                geometry=interval_geometry,
            )
            add(
                project_target.id,
                "projeto.rede_compacta_ancoragem_suficiente",
                compact_assessment.maximum_uninterrupted_m <= _ANCHOR_INTERVAL_M,
                geometry=interval_geometry,
            )
    if project_target is not None and compact_grounding is not None:
        geometry = next(
            (item.geometria for item in compact_cables if item.geometria is not None),
            None,
        )
        ground_evidence = tuple(
            proposal
            for pole_id in grounded_poles
            for proposal in classes_by_pole[pole_id]["ATERRAMENTO"]
        )
        add(
            project_target.id,
            "projeto.rede_compacta_aterramento_temporario_avaliado",
            compact_grounding.complete,
            ground_evidence,
            geometry,
        )
        if compact_grounding.complete and compact_grounding.maximum_uninterrupted_m is not None:
            interval_geometry = compact_grounding.maximum_uninterrupted_geometry or geometry
            add(
                project_target.id,
                "projeto.rede_compacta_maior_trecho_sem_aterramento_m",
                compact_grounding.maximum_uninterrupted_m,
                ground_evidence,
                interval_geometry,
            )
            add(
                project_target.id,
                "projeto.rede_compacta_aterramento_temporario_suficiente",
                compact_grounding.maximum_uninterrupted_m <= _COMPACT_TEMP_GROUNDING_INTERVAL_M,
                ground_evidence,
                interval_geometry,
            )
    if project_target is not None and neutral_grounding is not None:
        geometry = next(
            (item.geometria for item in neutral_cables if item.geometria is not None),
            None,
        )
        ground_evidence = tuple(
            proposal
            for pole_id in grounded_poles
            for proposal in classes_by_pole[pole_id]["ATERRAMENTO"]
        )
        add(
            project_target.id,
            "projeto.neutro_maior_componente_m",
            neutral_grounding.largest_component_m,
            ground_evidence,
            geometry,
        )
        add(
            project_target.id,
            "projeto.neutro_aterramento_periodico_avaliado",
            neutral_grounding.complete,
            ground_evidence,
            geometry,
        )
        if neutral_grounding.complete and neutral_grounding.maximum_uninterrupted_m is not None:
            interval_geometry = neutral_grounding.maximum_uninterrupted_geometry or geometry
            add(
                project_target.id,
                "projeto.neutro_maior_trecho_sem_aterramento_m",
                neutral_grounding.maximum_uninterrupted_m,
                ground_evidence,
                interval_geometry,
            )
            add(
                project_target.id,
                "projeto.neutro_aterramento_periodico_suficiente",
                neutral_grounding.maximum_uninterrupted_m <= _NEUTRAL_GROUNDING_INTERVAL_M,
                ground_evidence,
                interval_geometry,
            )

    for region in sessao.regioes:
        target = region_targets.get(region.id)
        if target is None:
            continue
        region_props = tuple(proposals[i] for i in region.elemento_ids if i in proposals)
        region_elements = tuple(by_proposal[p.id] for p in region_props if p.id in by_proposal)

        installed_poles = [
            (p, e)
            for p in region_props
            if p.situacao_projeto is SituacaoProjeto.INSTALAR
            and isinstance((e := by_proposal.get(p.id)), Poste)
        ]
        for prop, pole in installed_poles:
            pole_type = pole_types.get(pole.tipo_catalogo_id)
            if pole_type:
                add(target.id, "regiao.poste_instalar_altura_m", pole_type.altura_m, (prop,))
                add(
                    target.id,
                    "regiao.poste_instalar_resistencia_dan",
                    pole_type.resistencia_dan,
                    (prop,),
                )
                add(
                    target.id,
                    "regiao.poste_instalar_formato",
                    option_codes[pole_type.formato_opcao_id],
                    (prop,),
                )

        equipment_props = tuple(
            p for p in region_props if p.categoria is CategoriaElemento.EQUIPAMENTO
        )
        region_poles: list[tuple[PropostaElemento, Poste]] = []
        for proposal in region_props:
            confirmed_element = by_proposal.get(proposal.id)
            if isinstance(confirmed_element, Poste):
                region_poles.append((proposal, confirmed_element))
        required_mt_poles: set[UUID] = set()
        for pole_proposal, pole in region_poles:
            cable_candidates: list[Cabo | PropostaElemento] = list(incident.get(pole.id, ()))
            identities = {_cable_candidate_identity(candidate) for candidate in cable_candidates}
            for candidate in sorted(geometric_cables, key=lambda item: str(item.id)):
                identity = _cable_candidate_identity(candidate)
                if identity not in identities and _endpoint_is_near(
                    pole.geometria, candidate.geometria
                ):
                    identities.add(identity)
                    cable_candidates.append(candidate)
            geometric_evidence = tuple(
                candidate
                for candidate in cable_candidates
                if isinstance(candidate, PropostaElemento)
            )
            transition_pairs = tuple(
                (first, second)
                for first_index, first in enumerate(cable_candidates)
                for second in cable_candidates[first_index + 1 :]
                if cable_level(first) == cable_level(second) == "MT"
                and _is_transition_pair(
                    cable_technology(first),
                    cable_technology(second),
                )
            )
            transition = bool(transition_pairs)
            if transition:
                angles = {
                    angle
                    for first, second in transition_pairs
                    if (
                        angle := _deflection_angle(
                            pole.geometria,
                            (first, second),
                            page_sizes=page_sizes,
                        )
                    )
                    is not None
                }
            else:
                angles = {
                    angle
                    for level in {cable_level(item) for item in cable_candidates}
                    if level
                    for angle in _deflection_angles(
                        pole.geometria,
                        tuple(item for item in cable_candidates if cable_level(item) == level),
                        page_sizes=page_sizes,
                    )
                }
            for angle in sorted(angles):
                add(
                    target.id,
                    "conexao.angulo_graus",
                    angle,
                    (pole_proposal, *geometric_evidence),
                    pole.geometria,
                )
            if transition:
                add(
                    target.id,
                    "regiao.transicao_rede",
                    True,
                    (pole_proposal, *geometric_evidence),
                    pole.geometria,
                )
            incident_mt = tuple(cable for cable in cable_candidates if cable_level(cable) == "MT")
            line_end_mt = len(incident_mt) == 1
            if transition or line_end_mt:
                required_mt_poles.add(pole.id)
                add(
                    target.id,
                    "regiao.para_raios_mt_requerido",
                    True,
                    (pole_proposal, *geometric_evidence),
                    pole.geometria,
                )

        transformer_props = tuple(
            prop
            for prop in equipment_props
            if equipment_class(prop) == "TRANSFORMADOR"
            and prop.situacao_projeto is SituacaoProjeto.INSTALAR
        )
        transformer_poles = {
            pole_id
            for prop in transformer_props
            if (pole_id := proposal_poles.get(prop.id)) is not None
        }
        for prop in equipment_props:
            normalized_class = equipment_class(prop)
            if (
                normalized_class == "TRANSFORMADOR"
                and prop.situacao_projeto is SituacaoProjeto.INSTALAR
                and (associated_pole_id := proposal_poles.get(prop.id)) is not None
            ):
                associated_pole = confirmed.get(associated_pole_id)
                pole_type = (
                    pole_types.get(associated_pole.tipo_catalogo_id)
                    if isinstance(associated_pole, Poste)
                    else None
                )
                if (
                    pole_type
                    and isinstance(associated_pole, Poste)
                    and associated_pole.situacao is SituacaoProjeto.INSTALAR
                ):
                    add(
                        target.id,
                        "regiao.poste_equipamento_instalar_altura_m",
                        pole_type.altura_m,
                        (prop,),
                    )
                    add(
                        target.id,
                        "regiao.poste_equipamento_instalar_resistencia_dan",
                        pole_type.resistencia_dan,
                        (prop,),
                    )
                    add(
                        target.id,
                        "regiao.poste_equipamento_instalar_formato",
                        option_codes[pole_type.formato_opcao_id],
                        (prop,),
                    )

        add(
            target.id,
            "regiao.transformador_instalar",
            bool(transformer_props),
            transformer_props,
        )
        for key, accepted, applicable_poles in (
            (
                "chave_fusivel_presente",
                {"CHAVE_FUSIVEL", "CHAVE_FUSIVEL_REPETIDORA"},
                transformer_poles,
            ),
            (
                "para_raios_mt_presente",
                {"PARA_RAIOS_MT"},
                transformer_poles | required_mt_poles,
            ),
            (
                "transformador_para_raios_mt_presente",
                {"PARA_RAIOS_MT"},
                transformer_poles,
            ),
            (
                "para_raios_mt_requisito_presente",
                {"PARA_RAIOS_MT"},
                required_mt_poles,
            ),
            ("para_raios_bt_presente", {"PARA_RAIOS_BT"}, transformer_poles),
            ("aterramento_presente", {"ATERRAMENTO"}, transformer_poles),
        ):
            matching = tuple(
                proposal
                for pole_id in applicable_poles
                for class_code in accepted
                for proposal in classes_by_pole[pole_id].get(class_code, ())
            )
            add(
                target.id,
                f"regiao.{key}",
                bool(applicable_poles)
                and all(
                    any(classes_by_pole[pole_id].get(class_code) for class_code in accepted)
                    for pole_id in applicable_poles
                ),
                matching,
            )

        structures = [e for e in region_elements if isinstance(e, (EstruturaMt, EstruturaBt))]
        pairs = [
            (structure, cable)
            for structure in structures
            for cable in incident.get(structure.poste_id, ())
            if _structure_uses_cable(structure, cable, points)
            and (
                structure.situacao is SituacaoProjeto.INSTALAR
                or cable.situacao is SituacaoProjeto.INSTALAR
            )
        ]
        if pairs:
            add(target.id, "regiao.estrutura_cabo_avaliada", True)
            add(
                target.id,
                "regiao.estrutura_cabo_incompativel",
                any((s.tipo_catalogo_id, c.tipo_catalogo_id) not in compatible for s, c in pairs),
            )
    return tuple(result)


def _deflection_angle(
    pole_geometry: GeometriaDocumento | None,
    cables: Iterable[_GeometryCarrier],
    *,
    page_sizes: dict[UUID, tuple[Decimal, Decimal]] | None = None,
) -> Decimal | None:
    if pole_geometry is None:
        return None
    pole = _center(pole_geometry)
    vectors: list[tuple[float, float]] = []
    width, height = (page_sizes or {}).get(
        pole_geometry.pagina_id,
        (Decimal(1), Decimal(1)),
    )
    for cable in cables:
        geometry = cable.geometria
        if geometry is None or len(geometry.pontos) < 2:
            continue
        pts = geometry.pontos
        start = _distance(pts[0], pole, width, height)
        oriented = pts if start <= _distance(pts[-1], pole, width, height) else tuple(reversed(pts))
        for point in oriented[1:]:
            vector = (
                float((point.x - pole.x) * width),
                float((point.y - pole.y) * height),
            )
            if math.hypot(*vector) > 1e-9:
                vectors.append(vector)
                break
    if len(vectors) < 2:
        return None
    a, b = vectors[0], vectors[1]
    cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b))))
    value = 180.0 - math.degrees(math.acos(cosine))
    return Decimal(str(round(value, 3))).normalize()


def _deflection_angles(
    pole_geometry: GeometriaDocumento | None,
    cables: Iterable[_GeometryCarrier],
    *,
    page_sizes: dict[UUID, tuple[Decimal, Decimal]] | None = None,
) -> tuple[Decimal, ...]:
    candidates = tuple(cables)
    values = {
        angle
        for first_index, first in enumerate(candidates)
        for second in candidates[first_index + 1 :]
        if (
            angle := _deflection_angle(
                pole_geometry,
                (first, second),
                page_sizes=page_sizes,
            )
        )
        is not None
    }
    return tuple(sorted(values))


def _is_transition_pair(first: str, second: str) -> bool:
    return (first == "PROTEGIDA" and second.startswith("CONVENCIONAL")) or (
        second == "PROTEGIDA" and first.startswith("CONVENCIONAL")
    )


def _cable_candidate_identity(cable: Cabo | PropostaElemento) -> tuple[object, ...]:
    catalog_id = (
        cable.tipo_catalogo_id if isinstance(cable, Cabo) else cable.tipo_catalogo_sugerido_id
    )
    geometry = cable.geometria
    if geometry is None:
        return ("id", cable.id)
    return ("geometry", catalog_id, geometry.pagina_id, geometry.pontos)


def _structure_uses_cable(
    structure: EstruturaMt | EstruturaBt,
    cable: Cabo,
    points: dict[UUID, PontoRede],
) -> bool:
    fixed_points = set(structure.pontos_fixados_ids)
    if fixed_points:
        return bool(fixed_points.intersection(cable.percurso_pontos_ids))
    expected_level = NivelRede.MT if isinstance(structure, EstruturaMt) else NivelRede.BT
    return any(
        points.get(point_id) is not None and points[point_id].nivel_rede is expected_level
        for point_id in cable.percurso_pontos_ids
    )


def _route_groups(
    cables: Iterable[Cabo],
    points: dict[UUID, PontoRede],
) -> tuple[_RouteGroup, ...]:
    grouped: dict[tuple[str, ...], list[Cabo]] = defaultdict(list)
    paths: dict[tuple[str, ...], tuple[UUID, ...]] = {}
    for cable in cables:
        path = _pole_path(cable, points)
        if len(path) >= 2:
            forward = tuple(str(item) for item in path)
            backward = tuple(reversed(forward))
            key = ("route", *(forward if forward <= backward else backward))
        else:
            key = ("cable", str(cable.id))
        grouped[key].append(cable)
        paths[key] = path
    result: list[_RouteGroup] = []
    for key in sorted(grouped):
        members = tuple(grouped[key])
        lengths = tuple(item.comprimento_m for item in members if item.comprimento_m is not None)
        result.append(
            _RouteGroup(
                key=key,
                pole_path=paths[key],
                cables=members,
                length_m=max(lengths) if lengths else None,
            )
        )
    return tuple(result)


def _pole_path(cable: Cabo, points: dict[UUID, PontoRede]) -> tuple[UUID, ...]:
    result: list[UUID] = []
    for point_id in cable.percurso_pontos_ids:
        point = points.get(point_id)
        if point is None or point.poste_id is None:
            continue
        if not result or result[-1] != point.poste_id:
            result.append(point.poste_id)
    return tuple(result)


def _assess_paths(
    cables: Iterable[Cabo],
    points: dict[UUID, PontoRede],
    markers: set[UUID],
) -> _PathAssessment | None:
    groups = _route_groups(cables, points)
    if not groups:
        return None
    complete = all(group.length_m is not None and len(group.pole_path) == 2 for group in groups)
    edge_groups = tuple(
        group for group in groups if group.length_m is not None and len(group.pole_path) == 2
    )
    edges_list: list[_RouteEdge] = []
    for index, group in enumerate(edge_groups):
        assert group.length_m is not None
        edges_list.append(_RouteEdge(index, group.pole_path[0], group.pole_path[1], group.length_m))
    edges = tuple(edges_list)
    total = sum((edge.length_m for edge in edges), Decimal())
    if not edges:
        return _PathAssessment(total, Decimal(), None, None, False)
    components = _edge_components(edges)
    largest_component = max(
        sum((edges[index].length_m for index in component), Decimal()) for component in components
    )
    if any(
        len(component)
        != len(
            {
                pole_id
                for index in component
                for pole_id in (edges[index].first_pole_id, edges[index].second_pole_id)
            }
        )
        - 1
        for component in components
    ):
        complete = False
    maximum: Decimal | None = None
    maximum_geometry: GeometriaDocumento | None = None
    if complete:
        maximum, maximum_edges = _maximum_uninterrupted_distance(edges, components, markers)
        maximum_geometry = _representative_interval_geometry(
            maximum_edges,
            edges,
            edge_groups,
        )
    return _PathAssessment(total, largest_component, maximum, maximum_geometry, complete)


def _edge_components(edges: tuple[_RouteEdge, ...]) -> tuple[frozenset[int], ...]:
    by_pole: dict[UUID, set[int]] = defaultdict(set)
    for edge in edges:
        by_pole[edge.first_pole_id].add(edge.index)
        by_pole[edge.second_pole_id].add(edge.index)
    remaining = {edge.index for edge in edges}
    result: list[frozenset[int]] = []
    while remaining:
        pending = [min(remaining)]
        component: set[int] = set()
        while pending:
            index = pending.pop()
            if index in component:
                continue
            component.add(index)
            edge = edges[index]
            pending.extend(by_pole[edge.first_pole_id] - component)
            pending.extend(by_pole[edge.second_pole_id] - component)
        remaining.difference_update(component)
        result.append(frozenset(component))
    return tuple(result)


def _maximum_uninterrupted_distance(
    edges: tuple[_RouteEdge, ...],
    components: tuple[frozenset[int], ...],
    markers: set[UUID],
) -> tuple[Decimal, frozenset[int]]:
    maximum = Decimal()
    maximum_edges: frozenset[int] = frozenset()
    maximum_signature: tuple[int, ...] | None = None
    for component in components:
        adjacency: dict[
            tuple[str, str, int],
            list[tuple[tuple[str, str, int], Decimal, int]],
        ] = defaultdict(list)
        for index in sorted(component):
            edge = edges[index]
            first = _split_node(edge.first_pole_id, edge.index, markers)
            second = _split_node(edge.second_pole_id, edge.index, markers)
            adjacency[first].append((second, edge.length_m, edge.index))
            adjacency[second].append((first, edge.length_m, edge.index))
        unseen = set(adjacency)
        while unseen:
            start = min(unseen)
            subgraph = _reachable_nodes(start, adjacency)
            unseen.difference_update(subgraph)
            farthest, _distance_m, _first_path = _farthest_node(start, adjacency, subgraph)
            _other, diameter, diameter_edges = _farthest_node(
                farthest,
                adjacency,
                subgraph,
            )
            signature = tuple(sorted(diameter_edges))
            if diameter > maximum or (
                diameter == maximum and (maximum_signature is None or signature < maximum_signature)
            ):
                maximum = diameter
                maximum_edges = diameter_edges
                maximum_signature = signature
    return maximum, maximum_edges


def _representative_interval_geometry(
    interval_edges: frozenset[int],
    edges: tuple[_RouteEdge, ...],
    edge_groups: tuple[_RouteGroup, ...],
) -> GeometriaDocumento | None:
    ordered = sorted(
        interval_edges,
        key=lambda index: (-edges[index].length_m, index),
    )
    return next(
        (
            cable.geometria
            for index in ordered
            for cable in edge_groups[index].cables
            if cable.geometria is not None
        ),
        None,
    )


def _split_node(pole_id: UUID, edge_index: int, markers: set[UUID]) -> tuple[str, str, int]:
    if pole_id in markers:
        return ("marker", str(pole_id), edge_index)
    return ("pole", str(pole_id), 0)


def _reachable_nodes(
    start: tuple[str, str, int],
    adjacency: dict[
        tuple[str, str, int],
        list[tuple[tuple[str, str, int], Decimal, int]],
    ],
) -> set[tuple[str, str, int]]:
    pending = [start]
    result: set[tuple[str, str, int]] = set()
    while pending:
        node = pending.pop()
        if node in result:
            continue
        result.add(node)
        pending.extend(
            neighbor for neighbor, _length, _edge_index in adjacency[node] if neighbor not in result
        )
    return result


def _farthest_node(
    start: tuple[str, str, int],
    adjacency: dict[
        tuple[str, str, int],
        list[tuple[tuple[str, str, int], Decimal, int]],
    ],
    allowed: set[tuple[str, str, int]],
) -> tuple[tuple[str, str, int], Decimal, frozenset[int]]:
    pending: list[
        tuple[
            tuple[str, str, int],
            tuple[str, str, int] | None,
            Decimal,
            frozenset[int],
        ]
    ] = [(start, None, Decimal(), frozenset())]
    farthest = start
    maximum = Decimal()
    maximum_edges: frozenset[int] = frozenset()
    while pending:
        node, previous, distance, path_edges = pending.pop()
        if distance > maximum or (distance == maximum and node < farthest):
            farthest, maximum = node, distance
            maximum_edges = path_edges
        pending.extend(
            (neighbor, node, distance + length, path_edges | {edge_index})
            for neighbor, length, edge_index in adjacency[node]
            if neighbor != previous and neighbor in allowed
        )
    return farthest, maximum, maximum_edges


def _associate_proposals_to_poles(
    proposals: tuple[PropostaElemento, ...],
    confirmed_by_proposal: Mapping[UUID, object],
    poles: tuple[Poste, ...],
    page_sizes: Mapping[UUID, tuple[Decimal, Decimal]],
) -> dict[UUID, UUID]:
    labels: dict[str, set[UUID]] = defaultdict(set)
    for pole in poles:
        for value in (pole.identificador_operacional, pole.referencia_desenho):
            if value:
                labels[_normalize_identifier(value)].add(pole.id)
    for proposal in proposals:
        element = confirmed_by_proposal.get(proposal.id)
        if isinstance(element, Poste):
            identifier = dict(proposal.atributos_sugeridos).get("identificador_operacional")
            if identifier:
                labels[_normalize_identifier(identifier)].add(element.id)

    result: dict[UUID, UUID] = {}
    for proposal in proposals:
        element = confirmed_by_proposal.get(proposal.id)
        if isinstance(element, Equipamento):
            result[proposal.id] = element.poste_id
            continue
        attributes = dict(proposal.atributos_sugeridos)
        raw_pole_id = attributes.get("poste_id")
        if raw_pole_id:
            try:
                candidate_id = UUID(str(raw_pole_id))
            except ValueError:
                candidate_id = None
            if candidate_id is not None and any(pole.id == candidate_id for pole in poles):
                result[proposal.id] = candidate_id
                continue
        identifier = attributes.get("identificador_operacional")
        matched = labels.get(_normalize_identifier(identifier), set()) if identifier else set()
        if len(matched) == 1:
            result[proposal.id] = next(iter(matched))
            continue
        nearest = _nearest_pole(proposal.geometria, poles, page_sizes)
        if nearest is not None:
            result[proposal.id] = nearest.id
    return result


def _nearest_pole(
    geometry: GeometriaDocumento,
    poles: tuple[Poste, ...],
    page_sizes: Mapping[UUID, tuple[Decimal, Decimal]],
) -> Poste | None:
    center = _center(geometry)
    width, height = page_sizes.get(geometry.pagina_id, (Decimal(1), Decimal(1)))
    candidates = sorted(
        (
            (_distance(center, _center(pole.geometria), width, height), str(pole.id), pole)
            for pole in poles
            if pole.geometria is not None and pole.geometria.pagina_id == geometry.pagina_id
        ),
        key=lambda item: (item[0], item[1]),
    )
    if not candidates:
        return None
    normalized_distance = candidates[0][0] / math.hypot(float(width), float(height))
    return candidates[0][2] if normalized_distance <= _SYMBOL_POLE_DISTANCE else None


def _normalize_identifier(value: object) -> str:
    return re.sub(r"[^A-Z0-9]+", "", str(value).upper())


def _is_neutral_cable(cable_type: TipoCabo) -> bool:
    return re.match(r"^[ABC]*N\s*-", cable_type.codigo.strip().upper()) is not None


def _center(geometry: GeometriaDocumento) -> PontoNormalizado:
    return PontoNormalizado(
        sum((p.x for p in geometry.pontos), Decimal()) / len(geometry.pontos),
        sum((p.y for p in geometry.pontos), Decimal()) / len(geometry.pontos),
    )


def _endpoint_is_near(
    pole_geometry: GeometriaDocumento | None,
    cable_geometry: GeometriaDocumento | None,
) -> bool:
    if (
        pole_geometry is None
        or cable_geometry is None
        or pole_geometry.pagina_id != cable_geometry.pagina_id
        or len(cable_geometry.pontos) < 2
    ):
        return False
    pole = _center(pole_geometry)
    return (
        min(
            math.hypot(float(point.x - pole.x), float(point.y - pole.y))
            for point in (cable_geometry.pontos[0], cable_geometry.pontos[-1])
        )
        <= _INCIDENT_ENDPOINT_DISTANCE
    )


def _distance(
    first: PontoNormalizado,
    second: PontoNormalizado,
    width: Decimal,
    height: Decimal,
) -> float:
    return math.hypot(
        float((first.x - second.x) * width),
        float((first.y - second.y) * height),
    )


def _normalize_class(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
