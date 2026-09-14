"""Promoção determinística dos resultados automáticos ao agregado do projeto."""

from __future__ import annotations

import math
from collections.abc import Mapping
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
    ModalidadeTrecho,
    NivelRede,
    OrigemComprimentoVao,
    TipoDecisaoRevisao,
    TipoGeometria,
    TipoPontoRede,
    TipoTrechoRede,
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
    cataloged = _promotable_proposals(elementos, catalogo)
    poles = tuple(
        proposal
        for proposal in cataloged.values()
        if proposal.categoria is CategoriaElemento.POSTE
        and dict(proposal.atributos_sugeridos).get("tipo_ponto_rede") != TipoPontoRede.ENTREGA.value
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
        if relation_proposal.estado_revisao is EstadoRevisao.REJEITADA:
            promoted_relations.append(relation_proposal)
            continue
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


def _promotable_proposals(
    proposals: tuple[PropostaElemento, ...],
    catalog: CatalogoTecnico,
) -> dict[UUID, PropostaElemento]:
    pending_keys = (
        "revisao_tecnica_pendente",
        "revisao_tecnica_decidida",
        "reconciliacao_reanalise_pendente",
        "associacao_pendente",
        "comprimento_pendente",
    )
    return {
        proposal.id: proposal
        for proposal in proposals
        if proposal.tipo_catalogo_sugerido_id is not None
        and proposal.estado_revisao is not EstadoRevisao.REJEITADA
        and not any(dict(proposal.atributos_sugeridos).get(key) for key in pending_keys)
        and (item := catalog.item_por_id(proposal.tipo_catalogo_sugerido_id)) is not None
        and item.ativo
        and item.categoria is proposal.categoria
    }


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
        if len(pole_ids) != 1:
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
        if len(pole_ids) != 1:
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
        if len(pole_ids) != 1:
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
    if proposal.geometria.tipo is not TipoGeometria.POLILINHA:
        return None
    geometry = proposal.geometria
    level = _network_level(catalog, cable_type.nivel_tensao_opcao_id)
    attributes = dict(proposal.atributos_sugeridos)
    explicit_endpoint_types: tuple[TipoPontoRede | None, TipoPontoRede | None] = (
        (
            TipoPontoRede.ENTREGA
            if attributes.get("tipo_ponto_operacional_origem") == TipoPontoRede.ENTREGA.value
            else None
        ),
        (
            TipoPontoRede.ENTREGA
            if attributes.get("tipo_ponto_operacional_destino") == TipoPontoRede.ENTREGA.value
            else None
        ),
    )
    endpoint_poles = _endpoint_poles(
        geometry,
        pole_proposals,
        element_ids,
        explicit_endpoint_types,
        attributes,
    )
    endpoint_types: tuple[TipoPontoRede, TipoPontoRede] = (
        explicit_endpoint_types[0]
        or (TipoPontoRede.POSTE if endpoint_poles[0] is not None else TipoPontoRede.CONEXAO),
        explicit_endpoint_types[1]
        or (TipoPontoRede.POSTE if endpoint_poles[1] is not None else TipoPontoRede.CONEXAO),
    )
    endpoint_labels = tuple(
        _normalized_attribute(attributes.get(f"ponto_operacional_{suffix}"))
        for suffix in ("origem", "destino")
    )
    points = tuple(
        _network_point(
            element_id,
            index,
            geometry,
            level,
            cable_type,
            endpoint_poles[index],
            endpoint_types[index],
            endpoint_labels[index],
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
            tipo_trecho=_network_segment_type(endpoint_types),
            modalidade=ModalidadeTrecho.DESCONHECIDO,
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
    return related


def _endpoint_poles(
    geometry: GeometriaDocumento,
    poles: tuple[PropostaElemento, ...],
    element_ids: dict[UUID, UUID],
    explicit_types: tuple[TipoPontoRede | None, TipoPontoRede | None],
    attributes: Mapping[str, object],
) -> tuple[UUID | None, UUID | None]:
    remaining = list(poles)
    selected: list[UUID | None] = []
    for index, point in enumerate((geometry.pontos[0], geometry.pontos[-1])):
        if explicit_types[index] is TipoPontoRede.ENTREGA:
            selected.append(None)
            continue
        label = attributes.get(f"ponto_operacional_{'origem' if index == 0 else 'destino'}")
        candidates = sorted(
            (
                pole
                for pole in remaining
                if (not label or _operational_identifier(pole) == label)
                and _point_distance(point, pole.geometria) <= 0.10
            ),
            key=lambda pole: (_point_distance(point, pole.geometria), str(pole.id)),
        )
        nearest = candidates[0] if candidates else None
        if len(candidates) > 1 and (
            _point_distance(point, candidates[1].geometria)
            - _point_distance(point, candidates[0].geometria)
            <= 0.004
        ):
            nearest = None
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
    point_type: TipoPontoRede,
    operational_label: str | None,
) -> PontoRede:
    suffix = "origem" if index == 0 else "destino"
    point = geometry.pontos[0] if index == 0 else geometry.pontos[-1]
    return PontoRede(
        id=uuid5(cable_id, f"ponto-{suffix}"),
        poste_id=pole_id,
        nome=(
            f"{operational_label} - Padrão do cliente"
            if point_type is TipoPontoRede.ENTREGA and operational_label
            else operational_label or f"{cable_id}-{suffix}"
        ),
        nivel_rede=level,
        nivel_tensao_opcao_id=cable_type.nivel_tensao_opcao_id,
        configuracao_fases_opcao_id=cable_type.configuracao_fases_opcao_id,
        tipo=point_type,
        geometria=GeometriaDocumento.ponto(geometry.pagina_id, point),
    )


def _network_segment_type(
    endpoint_types: tuple[TipoPontoRede, TipoPontoRede],
) -> TipoTrechoRede:
    delivery_count = endpoint_types.count(TipoPontoRede.ENTREGA)
    pole_count = endpoint_types.count(TipoPontoRede.POSTE)
    if delivery_count == 1 and pole_count == 1:
        return TipoTrechoRede.RAMAL_CONEXAO
    if pole_count == 2:
        return TipoTrechoRede.REDE_DISTRIBUICAO
    return TipoTrechoRede.DESCONHECIDO


def _normalized_attribute(value: object) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


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


def _point_distance(point: PontoNormalizado, geometry: GeometriaDocumento) -> float:
    return math.dist((float(point.x), float(point.y)), _center(geometry))


def _center(geometry: GeometriaDocumento) -> tuple[float, float]:
    xs = [float(point.x) for point in geometry.pontos]
    ys = [float(point.y) for point in geometry.pontos]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
