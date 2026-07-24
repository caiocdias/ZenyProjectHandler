"""Combinação contextual e geração determinística de relações propostas."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import (
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.enums import CategoriaElemento, EstadoRevisao, TipoEvidencia
from zeny_project_handler.domain.interpretation import (
    RegistroRegrasInterpretacao,
    RegraRelacaoInterpretacao,
)

from .rule_support import center, geometry_distance, point_distance


def mark_conflicts(
    proposals: tuple[PropostaElemento, ...],
    evidence: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    semantic_evidence = {
        item.id for item in evidence if item.tipo in {TipoEvidencia.TEXTO, TipoEvidencia.OCR}
    }
    categories_by_evidence: dict[UUID, set[CategoriaElemento]] = defaultdict(set)
    for proposal in proposals:
        for evidence_id in proposal.evidencia_ids:
            if evidence_id in semantic_evidence:
                categories_by_evidence[evidence_id].add(proposal.categoria)
    conflicting = {key for key, categories in categories_by_evidence.items() if len(categories) > 1}
    return tuple(
        replace(proposal, estado_revisao=EstadoRevisao.CONFLITANTE)
        if conflicting.intersection(proposal.evidencia_ids)
        else proposal
        for proposal in proposals
    )


def generate_relations(
    execution_id: UUID,
    elements: tuple[PropostaElemento, ...],
    registry: RegistroRegrasInterpretacao,
    catalog: CatalogoTecnico,
) -> tuple[PropostaRelacao, ...]:
    relations: list[PropostaRelacao] = []
    for rule in registry.regras_relacao:
        if not rule.ativa:
            continue
        origins = tuple(item for item in elements if item.categoria is rule.categoria_origem)
        destinations = tuple(item for item in elements if item.categoria is rule.categoria_destino)
        for origin in origins:
            targets = _relation_targets(origin, destinations, rule, catalog)
            relations.extend(_relation(execution_id, origin, target, rule) for target in targets)
    unique = {item.id: item for item in relations}
    return tuple(unique.values())


def _relation_targets(
    origin: PropostaElemento,
    destinations: tuple[PropostaElemento, ...],
    rule: RegraRelacaoInterpretacao,
    catalog: CatalogoTecnico,
) -> tuple[PropostaElemento, ...]:
    same_page = tuple(
        item for item in destinations if item.geometria.pagina_id == origin.geometria.pagina_id
    )
    if rule.estrategia == "CENTROS_PROXIMOS":
        same_situation = tuple(
            item for item in same_page if item.situacao_projeto is origin.situacao_projeto
        )
        candidates = same_situation or same_page
        nearest = min(
            candidates,
            key=lambda item: geometry_distance(origin.geometria, item.geometria),
            default=None,
        )
        if nearest is not None and geometry_distance(origin.geometria, nearest.geometria) <= float(
            rule.distancia_maxima
        ):
            return (nearest,)
        return ()
    if rule.estrategia in {"EXTREMIDADES_PROXIMAS", "COMPATIBILIDADE_E_PROXIMIDADE"}:
        compatible = tuple(item for item in same_page if _compatible(origin, item, rule, catalog))
        same_situation = tuple(
            item for item in compatible if item.situacao_projeto is origin.situacao_projeto
        )
        return _targets_near_endpoints(
            origin,
            same_situation or compatible,
            float(rule.distancia_maxima),
        )
    raise ValueError(f"Estratégia de relação não suportada: {rule.estrategia}")


def _compatible(
    origin: PropostaElemento,
    target: PropostaElemento,
    rule: RegraRelacaoInterpretacao,
    catalog: CatalogoTecnico,
) -> bool:
    if rule.estrategia != "COMPATIBILIDADE_E_PROXIMIDADE":
        return True
    if origin.tipo_catalogo_sugerido_id is None or target.tipo_catalogo_sugerido_id is None:
        return False
    pairs = {(item.tipo_cabo_id, item.tipo_estrutura_id) for item in catalog.compatibilidades}
    return (origin.tipo_catalogo_sugerido_id, target.tipo_catalogo_sugerido_id) in pairs


def _targets_near_endpoints(
    origin: PropostaElemento,
    destinations: tuple[PropostaElemento, ...],
    maximum_distance: float,
) -> tuple[PropostaElemento, ...]:
    points = origin.geometria.pontos
    endpoints = (points[0], points[-1])
    selected: dict[UUID, PropostaElemento] = {}
    for endpoint in endpoints:
        coordinate = (float(endpoint.x), float(endpoint.y))
        nearest = min(
            destinations,
            key=lambda item: point_distance(coordinate, center(item.geometria)),
            default=None,
        )
        if (
            nearest is not None
            and point_distance(coordinate, center(nearest.geometria)) <= maximum_distance
        ):
            selected[nearest.id] = nearest
    return tuple(selected.values())


def _relation(
    execution_id: UUID,
    origin: PropostaElemento,
    destination: PropostaElemento,
    rule: RegraRelacaoInterpretacao,
) -> PropostaRelacao:
    evidence_ids = tuple(sorted({*origin.evidencia_ids, *destination.evidencia_ids}, key=str))
    confidence_values = [rule.confianca]
    confidence_values.extend(
        value for value in (origin.confianca, destination.confianca) if value is not None
    )
    return PropostaRelacao(
        id=uuid5(execution_id, f"relacao:{rule.id}:{origin.id}:{destination.id}"),
        execucao_id=execution_id,
        origem_referencia_id=origin.id,
        destino_referencia_id=destination.id,
        tipo_relacao=rule.tipo_relacao,
        evidencia_ids=evidence_ids,
        confianca=min(confidence_values),
        justificativa=f"A regra {rule.id} associou propostas por {rule.estrategia.lower()}.",
    )
