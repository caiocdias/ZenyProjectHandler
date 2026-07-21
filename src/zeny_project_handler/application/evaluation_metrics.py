"""Métricas por classe e divergência entre anotações independentes."""

from __future__ import annotations

from decimal import Decimal

from zeny_project_handler.application.evaluation_matching import (
    associar_elementos,
    relacoes_correspondentes,
)
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation import (
    AnotacaoAmostra,
    CriteriosRegressaoAvaliacao,
    RotuloElementoAvaliacao,
    RotuloRelacaoAvaliacao,
)
from zeny_project_handler.domain.evaluation_metrics import (
    ContagemDeteccao,
    DivergenciaAnotadores,
    MetricasCategoria,
)


def calcular_metricas_semanticas(
    referencias: tuple[RotuloElementoAvaliacao, ...],
    relacoes_referencia: tuple[RotuloRelacaoAvaliacao, ...],
    candidatos: tuple[RotuloElementoAvaliacao, ...],
    relacoes_candidatas: tuple[RotuloRelacaoAvaliacao, ...],
    criterios: CriteriosRegressaoAvaliacao,
) -> tuple[tuple[MetricasCategoria, ...], ContagemDeteccao]:
    matches = associar_elementos(referencias, candidatos, criterios, exigir_rotulos=True)
    matched_references = {item.referencia_id for item in matches}
    matched_candidates = {item.candidato_id for item in matches}
    metrics = []
    for category in CategoriaElemento:
        references_in_category = {item.id for item in referencias if item.categoria is category}
        candidates_in_category = {item.id for item in candidatos if item.categoria is category}
        true_positives = len(matched_references & references_in_category)
        metrics.append(
            MetricasCategoria(
                categoria=category,
                contagem=ContagemDeteccao(
                    verdadeiros_positivos=true_positives,
                    falsos_positivos=len(candidates_in_category - matched_candidates),
                    falsos_negativos=len(references_in_category - matched_references),
                ),
            )
        )
    mapping = {item.candidato_id: item.referencia_id for item in matches}
    relation_true_positives = relacoes_correspondentes(
        relacoes_referencia, relacoes_candidatas, mapping
    )
    relation_counts = ContagemDeteccao(
        verdadeiros_positivos=relation_true_positives,
        falsos_positivos=len(relacoes_candidatas) - relation_true_positives,
        falsos_negativos=len(relacoes_referencia) - relation_true_positives,
    )
    return tuple(metrics), relation_counts


def medir_divergencia_anotadores(
    primaria: AnotacaoAmostra,
    secundaria: AnotacaoAmostra,
    criterios: CriteriosRegressaoAvaliacao,
) -> DivergenciaAnotadores:
    if primaria.amostra_id != secundaria.amostra_id:
        raise DomainValidationError("Anotações devem pertencer à mesma amostra")
    if primaria.anotador_id == secundaria.anotador_id:
        raise DomainValidationError("Amostragem dupla exige anotadores distintos")
    matches = associar_elementos(
        primaria.elementos, secundaria.elementos, criterios, exigir_rotulos=False
    )
    primary_by_id = {item.id: item for item in primaria.elementos}
    secondary_by_id = {item.id: item for item in secundaria.elementos}
    category_disagreements = sum(
        primary_by_id[item.referencia_id].categoria
        is not secondary_by_id[item.candidato_id].categoria
        for item in matches
    )
    situation_disagreements = sum(
        primary_by_id[item.referencia_id].situacao
        is not secondary_by_id[item.candidato_id].situacao
        for item in matches
    )
    mapping = {item.candidato_id: item.referencia_id for item in matches}
    matching_relations = relacoes_correspondentes(primaria.relacoes, secundaria.relacoes, mapping)
    matching_labeled_elements = len(matches) - len(
        {
            item.referencia_id
            for item in matches
            if primary_by_id[item.referencia_id].categoria
            is not secondary_by_id[item.candidato_id].categoria
            or primary_by_id[item.referencia_id].situacao
            is not secondary_by_id[item.candidato_id].situacao
        }
    )
    element_agreement = Decimal(matching_labeled_elements) / Decimal(
        max(len(primaria.elementos), len(secundaria.elementos), 1)
    )
    relation_agreement = Decimal(matching_relations) / Decimal(
        max(len(primaria.relacoes), len(secundaria.relacoes), 1)
    )
    dimensions = [element_agreement]
    if primaria.relacoes or secundaria.relacoes:
        dimensions.append(relation_agreement)
    divergence = Decimal(1) - sum(dimensions, start=Decimal(0)) / Decimal(len(dimensions))
    return DivergenciaAnotadores(
        amostra_id=primaria.amostra_id,
        elementos_primarios=len(primaria.elementos),
        elementos_secundarios=len(secundaria.elementos),
        elementos_correspondentes=len(matches),
        divergencias_categoria=category_disagreements,
        divergencias_situacao=situation_disagreements,
        relacoes_primarias=len(primaria.relacoes),
        relacoes_secundarias=len(secundaria.relacoes),
        relacoes_correspondentes=matching_relations,
        taxa_divergencia=divergence,
    )
