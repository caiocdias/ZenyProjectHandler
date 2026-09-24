"""Projection of persisted symbol evidence; no detection or reconciliation."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento
from zeny_project_handler_contracts.common import EvidenceNavigationDto
from zeny_project_handler_contracts.enums import ElementSituation
from zeny_project_handler_contracts.review import (
    ReviewSymbolAlternativeDto,
    ReviewSymbolDto,
    ReviewSymbolMethodDto,
)


def _array(value: object) -> list[Any]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _decimal(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return format(number, "f") if number.is_finite() else None


def project_symbol(
    proposal: PropostaElemento,
    evidence_by_id: dict[UUID, EvidenciaDocumento],
    navigation: tuple[EvidenceNavigationDto, ...],
    effective_situation: ElementSituation,
    *,
    confirmed: bool,
) -> ReviewSymbolDto | None:
    values = dict(proposal.atributos_sugeridos)
    occurrence = values.get("origem_simbolo_ocorrencia_id")
    if not occurrence:
        return None
    alternatives = tuple(
        ReviewSymbolAlternativeDto(symbol_class=item.get("classe"), subtype=item.get("subtipo"))
        for item in _array(values.get("simbolo_alternativas"))
        if isinstance(item, dict)
    )
    methods: list[ReviewSymbolMethodDto] = []
    navigation_by_id = {
        str(item.evidence_id.root): item for item in navigation if item.evidence_id is not None
    }
    for row in _array(values.get("simbolo_observacoes")):
        if not isinstance(row, dict):
            continue
        target = navigation_by_id.get(str(row.get("evidence_id")))
        if target is not None:
            methods.append(
                ReviewSymbolMethodDto(
                    signature=str(row["method_signature"]),
                    observation_id=str(row["observation_id"]),
                    raw_score=_decimal(row.get("raw_score")),
                    evidence=target,
                )
            )
    for target in navigation:
        if target.evidence_id is None:
            continue
        evidence = evidence_by_id.get(target.evidence_id.root)
        if evidence is None:
            continue
        attributes = dict(evidence.atributos_extraidos)
        observation = attributes.get("simbolo_observacao_id")
        if observation is None or str(observation) in {m.observation_id for m in methods}:
            continue
        methods.append(
            ReviewSymbolMethodDto(
                signature=evidence.metodo.removeprefix("simbolo:"),
                observation_id=str(observation),
                raw_score=_decimal(attributes.get("simbolo_score_bruto")),
                evidence=target,
            )
        )
    exclusive = len({method.signature for method in methods}) == 1
    role = str(values.get("simbolo_papel") or "desconhecido")
    coverage = tuple(i for i in _array(values.get("simbolo_matriz_metodos")) if isinstance(i, dict))
    references = tuple(str(i) for i in _array(values.get("simbolo_reference_ids")))
    situation_hints = {
        row.get("situacao")
        for row in _array(values.get("simbolo_situacoes_observadas"))
        if isinstance(row, dict) and row.get("situacao") is not None
    }
    ambiguous = (
        len({(a.symbol_class, a.subtype) for a in alternatives}) > 1
        or len(references) > 1
        or len(situation_hints) > 1
        or any(row.get("state") == "conflict" for row in coverage)
    )
    status: Any = (
        "informative"
        if role == "informativo"
        else "conflicting"
        if ambiguous
        else "unknown"
        if role == "desconhecido" or not methods
        else "exclusive"
        if exclusive
        else "supported"
    )
    return ReviewSymbolDto(
        occurrence_id=str(occurrence),
        symbol_class=str(values["simbolo_classe"]) if values.get("simbolo_classe") else None,
        role=role,
        status=status,
        exclusive=exclusive,
        unsupported_family=values.get("simbolo_familia_nao_suportada") is True,
        alternatives=alternatives,
        reference_ids=references,
        observation_ids=tuple(str(i) for i in _array(values.get("simbolo_observacao_ids"))),
        methods=tuple(methods),
        coverage=coverage,
        pending_reasons=tuple(
            filter(None, str(values.get("simbolo_motivo_pendencia") or "").split(","))
        ),
        layer=str(values.get("simbolo_camada") or "base"),
        effective_situation=effective_situation
        if confirmed or values.get("simbolo_situacao_resolvida") is True
        else None,
        quantity=_decimal(values.get("quantidade_ativos"))
        if values.get("simbolo_quantidade_resolvida") is True
        else None,
        calibrated_probability=_decimal(values.get("simbolo_probabilidade_calibrada")),
    )
