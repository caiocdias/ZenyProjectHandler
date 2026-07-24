"""Promoção determinística dos resultados automáticos ao agregado do projeto."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import (
    DecisaoRevisao,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, TipoCabo
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoRevisao,
    NivelRede,
    OrigemComprimentoVao,
    TipoDecisaoRevisao,
    TipoGeometria,
    TipoPontoRede,
)
from zeny_project_handler.domain.project import (
    Cabo,
    ElementoProjetoType,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    PontoRede,
    Poste,
    Projeto,
    RelacaoConfirmada,
)
from zeny_project_handler.domain.values import (
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)


@dataclass(frozen=True, slots=True)
class ResultadoPromocaoAutomatica:
    projeto: Projeto
    elementos: tuple[PropostaElemento, ...]
    relacoes: tuple[PropostaRelacao, ...]
    decisoes: tuple[DecisaoRevisao, ...]


def promover_resultado_automatico(
    projeto: Projeto,
    catalogo: CatalogoTecnico,
    elementos: tuple[PropostaElemento, ...],
    relacoes: tuple[PropostaRelacao, ...],
    *,
    promovido_em: datetime,
) -> ResultadoPromocaoAutomatica:
    """Materialize tudo que possui tipo catalogado e vínculos de domínio resolvíveis."""
    cataloged = {
        proposal.id: proposal
        for proposal in elementos
        if proposal.tipo_catalogo_sugerido_id is not None
        and (item := catalogo.item_por_id(proposal.tipo_catalogo_sugerido_id)) is not None
        and item.ativo
        and item.categoria is proposal.categoria
    }
    poles = tuple(
        proposal for proposal in cataloged.values() if proposal.categoria is CategoriaElemento.POSTE
    )
    relation_index = _relations_by_origin(relacoes)
    existing_elements = {element.id: element for element in projeto.elementos}
    existing_points = {point.id: point for point in projeto.pontos_rede}
    existing_relations = {relation.id: relation for relation in projeto.relacoes_confirmadas}
    element_ids: dict[UUID, UUID] = {}
    added_elements: list[ElementoProjetoType] = []
    added_points: list[PontoRede] = []

    for proposal in poles:
        element_id = uuid5(proposal.id, "elemento-confirmado")
        element_ids[proposal.id] = element_id
        if element_id not in existing_elements:
            added_elements.append(
                Poste(
                    id=element_id,
                    tipo_catalogo_id=_catalog_id(proposal),
                    situacao=proposal.situacao_projeto,
                    codigo_observado=proposal.codigo_observado,
                    identificador_operacional=_operational_identifier(proposal),
                    geometria=proposal.geometria,
                    coordenada_campo=_coordinate(proposal),
                )
            )

    for proposal in cataloged.values():
        if proposal.categoria is CategoriaElemento.POSTE:
            continue
        element_id = uuid5(proposal.id, "elemento-confirmado")
        element = _dependent_element(
            proposal,
            element_id,
            catalogo,
            poles,
            relation_index,
            element_ids,
        )
        if element is None:
            continue
        built, points = element
        element_ids[proposal.id] = element_id
        if element_id not in existing_elements:
            added_elements.append(built)
        for point in points:
            if point.id not in existing_points:
                added_points.append(point)

    confirmed_relations: list[RelacaoConfirmada] = []
    promoted_relations: list[PropostaRelacao] = []
    relation_decisions: list[DecisaoRevisao] = []
    for relation_proposal in relacoes:
        origin_id = element_ids.get(relation_proposal.origem_referencia_id)
        destination_id = element_ids.get(relation_proposal.destino_referencia_id)
        if origin_id is None or destination_id is None:
            promoted_relations.append(relation_proposal)
            continue
        relation_id = uuid5(relation_proposal.id, "relacao-confirmada")
        if relation_id not in existing_relations:
            confirmed_relations.append(
                RelacaoConfirmada(
                    id=relation_id,
                    tipo_relacao=relation_proposal.tipo_relacao,
                    origem_id=origin_id,
                    destino_id=destination_id,
                )
            )
        promoted_relations.append(
            replace(relation_proposal, estado_revisao=EstadoRevisao.CONFIRMADA)
        )
        relation_decisions.append(
            _automatic_decision(
                relation_proposal.id,
                promovido_em,
                relation_id=relation_id,
            )
        )

    promoted_elements = tuple(
        replace(proposal, estado_revisao=EstadoRevisao.CONFIRMADA)
        if proposal.id in element_ids
        else proposal
        for proposal in elementos
    )
    element_decisions = tuple(
        _automatic_decision(
            proposal.id,
            promovido_em,
            element_id=element_ids[proposal.id],
        )
        for proposal in elementos
        if proposal.id in element_ids
    )
    updated = replace(
        projeto,
        elementos=(*projeto.elementos, *added_elements),
        pontos_rede=(*projeto.pontos_rede, *added_points),
        relacoes_confirmadas=(*projeto.relacoes_confirmadas, *confirmed_relations),
    )
    return ResultadoPromocaoAutomatica(
        projeto=updated,
        elementos=promoted_elements,
        relacoes=tuple(promoted_relations),
        decisoes=(*element_decisions, *relation_decisions),
    )


def _dependent_element(
    proposal: PropostaElemento,
    element_id: UUID,
    catalog: CatalogoTecnico,
    poles: tuple[PropostaElemento, ...],
    relation_index: dict[UUID, tuple[PropostaRelacao, ...]],
    element_ids: dict[UUID, UUID],
) -> tuple[ElementoProjetoType, tuple[PontoRede, ...]] | None:
    catalog_id = _catalog_id(proposal)
    pole_proposals = _related_poles(proposal, poles, relation_index)
    pole_ids = tuple(element_ids[item.id] for item in pole_proposals if item.id in element_ids)
    if proposal.categoria is CategoriaElemento.ESTRUTURA_MT:
        if not pole_ids:
            return None
        return (
            EstruturaMt(
                id=element_id,
                tipo_catalogo_id=catalog_id,
                situacao=proposal.situacao_projeto,
                codigo_observado=proposal.codigo_observado,
                identificador_operacional=_operational_identifier(proposal),
                geometria=proposal.geometria,
                poste_id=pole_ids[0],
            ),
            (),
        )
    if proposal.categoria is CategoriaElemento.ESTRUTURA_BT:
        if not pole_ids:
            return None
        return (
            EstruturaBt(
                id=element_id,
                tipo_catalogo_id=catalog_id,
                situacao=proposal.situacao_projeto,
                codigo_observado=proposal.codigo_observado,
                identificador_operacional=_operational_identifier(proposal),
                geometria=proposal.geometria,
                poste_id=pole_ids[0],
            ),
            (),
        )
    if proposal.categoria is CategoriaElemento.EQUIPAMENTO:
        if not pole_ids:
            return None
        return (
            Equipamento(
                id=element_id,
                tipo_catalogo_id=catalog_id,
                situacao=proposal.situacao_projeto,
                codigo_observado=proposal.codigo_observado,
                identificador_operacional=_operational_identifier(proposal),
                geometria=proposal.geometria,
                poste_id=pole_ids[0],
            ),
            (),
        )
    cable_type = catalog.item_por_id(catalog_id)
    if not isinstance(cable_type, TipoCabo):
        return None
    geometry = _cable_geometry(proposal.geometria)
    level = _network_level(catalog, cable_type.nivel_tensao_opcao_id)
    endpoint_poles = _endpoint_poles(geometry, pole_proposals, element_ids)
    points = tuple(
        _network_point(
            element_id,
            index,
            geometry,
            level,
            cable_type,
            endpoint_poles[index],
        )
        for index in range(2)
    )
    span_length, length_origin = _cable_length(proposal, pole_proposals)
    return (
        Cabo(
            id=element_id,
            tipo_catalogo_id=catalog_id,
            situacao=proposal.situacao_projeto,
            codigo_observado=proposal.codigo_observado,
            identificador_operacional=_operational_identifier(proposal),
            geometria=geometry,
            ponto_origem_id=points[0].id,
            ponto_destino_id=points[1].id,
            comprimento_m=span_length,
            origem_comprimento=length_origin,
            postes_apoio_ids=pole_ids,
        ),
        points,
    )


def _relations_by_origin(
    relations: tuple[PropostaRelacao, ...],
) -> dict[UUID, tuple[PropostaRelacao, ...]]:
    origins: dict[UUID, list[PropostaRelacao]] = {}
    for relation in relations:
        origins.setdefault(relation.origem_referencia_id, []).append(relation)
    return {key: tuple(value) for key, value in origins.items()}


def _operational_identifier(proposal: PropostaElemento) -> str | None:
    value = dict(proposal.atributos_sugeridos).get("identificador_operacional")
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _related_poles(
    proposal: PropostaElemento,
    poles: tuple[PropostaElemento, ...],
    relation_index: dict[UUID, tuple[PropostaRelacao, ...]],
) -> tuple[PropostaElemento, ...]:
    by_id = {pole.id: pole for pole in poles}
    related = tuple(
        by_id[relation.destino_referencia_id]
        for relation in relation_index.get(proposal.id, ())
        if relation.destino_referencia_id in by_id
    )
    if related:
        return related
    same_page = tuple(
        pole for pole in poles if pole.geometria.pagina_id == proposal.geometria.pagina_id
    )
    same_situation = tuple(
        pole for pole in same_page if pole.situacao_projeto is proposal.situacao_projeto
    )
    candidates = same_situation or same_page
    nearest = min(candidates, key=lambda pole: _distance(proposal, pole), default=None)
    return (nearest,) if nearest is not None else ()


def _endpoint_poles(
    geometry: GeometriaDocumento,
    poles: tuple[PropostaElemento, ...],
    element_ids: dict[UUID, UUID],
) -> tuple[UUID | None, UUID | None]:
    remaining = list(poles)
    selected: list[UUID | None] = []
    for point in (geometry.pontos[0], geometry.pontos[-1]):
        nearest = min(
            remaining,
            key=lambda pole: _point_distance(point, pole.geometria),
            default=None,
        )
        selected.append(element_ids.get(nearest.id) if nearest is not None else None)
        if nearest is not None:
            remaining.remove(nearest)
    return selected[0], selected[1]


def _network_point(
    cable_id: UUID,
    index: int,
    geometry: GeometriaDocumento,
    level: NivelRede,
    cable_type: TipoCabo,
    pole_id: UUID | None,
) -> PontoRede:
    suffix = "origem" if index == 0 else "destino"
    point = geometry.pontos[0] if index == 0 else geometry.pontos[-1]
    return PontoRede(
        id=uuid5(cable_id, f"ponto-{suffix}"),
        poste_id=pole_id,
        nome=f"{cable_id}-{suffix}",
        nivel_rede=level,
        nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
        tipo=TipoPontoRede.POSTE if pole_id is not None else TipoPontoRede.CONEXAO,
        geometria=GeometriaDocumento.ponto(geometry.pagina_id, point),
    )


def _coordinate(proposal: PropostaElemento) -> CoordenadaCampo | None:
    attributes = dict(proposal.atributos_sugeridos)
    east = attributes.get("coordenada_leste")
    north = attributes.get("coordenada_norte")
    if east is None or north is None:
        return None
    return CoordenadaCampo(
        leste=Decimal(str(east)),
        norte=Decimal(str(north)),
        sistema_referencia="UTM",
    )


def _cable_length(
    proposal: PropostaElemento,
    poles: tuple[PropostaElemento, ...],
) -> tuple[Decimal | None, OrigemComprimentoVao | None]:
    attributes = dict(proposal.atributos_sugeridos)
    annotated = attributes.get("comprimento_m")
    if annotated is not None:
        length = Decimal(str(annotated))
        if length > 0:
            return length, OrigemComprimentoVao.ANOTACAO_DESENHO
    coordinates = tuple(
        coordinate for pole in poles if (coordinate := _coordinate(pole)) is not None
    )
    if len(coordinates) != 2:
        return None, None
    delta_east = coordinates[1].leste - coordinates[0].leste
    delta_north = coordinates[1].norte - coordinates[0].norte
    length = (delta_east * delta_east + delta_north * delta_north).sqrt()
    if length <= 0:
        return None, None
    return length.quantize(Decimal("0.01")), OrigemComprimentoVao.COORDENADAS


def _catalog_id(proposal: PropostaElemento) -> UUID:
    if proposal.tipo_catalogo_sugerido_id is None:
        raise ValueError("Proposta automática não possui item de catálogo")
    return proposal.tipo_catalogo_sugerido_id


def _automatic_decision(
    proposal_id: UUID,
    decided_at: datetime,
    *,
    element_id: UUID | None = None,
    relation_id: UUID | None = None,
) -> DecisaoRevisao:
    return DecisaoRevisao(
        id=uuid5(proposal_id, "decisao-revisao"),
        proposta_id=proposal_id,
        decisao=TipoDecisaoRevisao.ACEITAR,
        revisor="Análise automática",
        decidida_em=decided_at,
        elemento_confirmado_id=element_id,
        relacao_confirmada_id=relation_id,
        motivo="Resultado promovido automaticamente para as próximas etapas.",
    )


def _cable_geometry(geometry: GeometriaDocumento) -> GeometriaDocumento:
    if geometry.tipo is TipoGeometria.POLILINHA:
        return geometry
    if geometry.tipo is TipoGeometria.CAIXA:
        return GeometriaDocumento.polilinha(geometry.pagina_id, geometry.pontos)
    point = geometry.pontos[0]
    start_x = max(Decimal(0), point.x - Decimal("0.005"))
    end_x = min(Decimal(1), point.x + Decimal("0.005"))
    return GeometriaDocumento.polilinha(
        geometry.pagina_id,
        (
            PontoNormalizado(start_x, point.y),
            PontoNormalizado(max(end_x, start_x + Decimal("0.001")), point.y),
        ),
    )


def _network_level(catalog: CatalogoTecnico, voltage_option_id: UUID) -> NivelRede:
    option = next(
        (
            item
            for group in catalog.grupos_opcao
            if group.chave == "nivel_tensao"
            for item in group.opcoes
            if item.id == voltage_option_id
        ),
        None,
    )
    if option is None:
        raise ValueError("Nível de tensão do cabo não está disponível no catálogo")
    label = f"{option.codigo} {option.rotulo}".upper()
    return NivelRede.MT if "MT" in label else NivelRede.BT


def _distance(first: PropostaElemento, second: PropostaElemento) -> float:
    return math.dist(_center(first.geometria), _center(second.geometria))


def _point_distance(point: PontoNormalizado, geometry: GeometriaDocumento) -> float:
    return math.dist((float(point.x), float(point.y)), _center(geometry))


def _center(geometry: GeometriaDocumento) -> tuple[float, float]:
    xs = [float(point.x) for point in geometry.pontos]
    ys = [float(point.y) for point in geometry.pontos]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
