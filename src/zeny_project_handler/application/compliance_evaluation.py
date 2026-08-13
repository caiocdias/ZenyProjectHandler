"""Avaliação determinística de regras sobre fatos de conformidade."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from enum import Enum
from uuid import UUID, uuid5

from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.compliance import (
    AchadoConformidade,
    AlvoConformidade,
    AvaliacaoCondicaoConformidade,
    CondicaoConformidade,
    FatoConformidade,
    GrupoCondicaoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    RegistroRegrasConformidade,
    ResultadoCondicaoConformidade,
    ResultadoConformidade,
)


class _Truth(Enum):
    TRUE = 1
    FALSE = 0
    UNKNOWN = -1


def avaliar_regras_conformidade(
    registro: RegistroRegrasConformidade,
    alvos: tuple[AlvoConformidade, ...],
    fatos: tuple[FatoConformidade, ...],
) -> tuple[AchadoConformidade, ...]:
    """Produza um achado por regra aplicável e alvo conhecido."""
    facts_by_target: dict[UUID, list[FatoConformidade]] = defaultdict(list)
    for fact in fatos:
        facts_by_target[fact.alvo_id].append(fact)
    findings: list[AchadoConformidade] = []
    for rule in registro.regras:
        if not rule.ativa:
            continue
        for target in alvos:
            if target.tipo is not rule.escopo:
                continue
            scoped_facts = tuple(facts_by_target[target.id])
            applicability, applicability_audit = _conditions(
                rule.aplicabilidade,
                scoped_facts,
                GrupoCondicaoConformidade.APLICABILIDADE,
            )
            if applicability is _Truth.FALSE:
                continue
            exception, exception_audit = _conditions(
                rule.excecoes,
                scoped_facts,
                GrupoCondicaoConformidade.EXCECAO,
            )
            requirement, requirement_audit = _conditions(
                rule.requisitos,
                scoped_facts,
                GrupoCondicaoConformidade.REQUISITO,
            )
            evaluations = (*applicability_audit, *exception_audit, *requirement_audit)
            if applicability is _Truth.UNKNOWN:
                result = ResultadoConformidade.NAO_AVALIAVEL
            else:
                if rule.excecoes and exception is _Truth.TRUE:
                    continue
                result = {
                    _Truth.TRUE: ResultadoConformidade.CONFORME,
                    _Truth.FALSE: ResultadoConformidade.DIVERGENCIA,
                    _Truth.UNKNOWN: ResultadoConformidade.NAO_AVALIAVEL,
                }[requirement]
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for fact in scoped_facts
                    if fact.id in {item for audit in evaluations for item in audit.fato_ids}
                    for evidence_id in fact.evidencia_ids
                )
            )
            fact_ids = tuple(
                dict.fromkeys(item for audit in evaluations for item in audit.fato_ids)
            )
            findings.append(
                AchadoConformidade(
                    id=uuid5(target.id, f"{registro.assinatura()}:{rule.id}"),
                    regra_id=rule.id,
                    alvo_id=target.id,
                    resultado=result,
                    severidade=rule.severidade,
                    titulo=rule.titulo,
                    mensagem=_finding_message(
                        result,
                        rule.descricao,
                        target.rotulo,
                        evaluations,
                    ),
                    fonte=rule.fonte,
                    versao_regras=registro.versao,
                    evidencia_ids=evidence_ids,
                    fato_ids=fact_ids,
                    avaliacoes_condicoes=evaluations,
                )
            )
    return tuple(findings)


def _conditions(
    conditions: tuple[CondicaoConformidade, ...],
    facts: tuple[FatoConformidade, ...],
    group: GrupoCondicaoConformidade,
) -> tuple[_Truth, tuple[AvaliacaoCondicaoConformidade, ...]]:
    if not conditions:
        return _Truth.TRUE, ()
    evaluated = tuple(
        _condition(condition, facts, group=group, index=index)
        for index, condition in enumerate(conditions)
    )
    results = tuple(item[0] for item in evaluated)
    if _Truth.FALSE in results:
        truth = _Truth.FALSE
    elif _Truth.UNKNOWN in results:
        truth = _Truth.UNKNOWN
    else:
        truth = _Truth.TRUE
    return truth, tuple(item[1] for item in evaluated)


def _condition(
    condition: CondicaoConformidade,
    facts: tuple[FatoConformidade, ...],
    *,
    group: GrupoCondicaoConformidade,
    index: int,
) -> tuple[_Truth, AvaliacaoCondicaoConformidade]:
    relevant_facts = tuple(fact for fact in facts if fact.chave == condition.chave_fato)
    values = tuple(fact.valor for fact in relevant_facts)
    if condition.operador is OperadorCondicao.EXISTE:
        truth = _truth(bool(values))
    elif condition.operador is OperadorCondicao.AUSENTE:
        truth = _truth(not values)
    elif not values:
        truth = _Truth.UNKNOWN
    else:
        comparisons = tuple(
            _compare(value, condition.operador, condition.valores_esperados) for value in values
        )
        if condition.quantificador is QuantificadorCondicao.QUALQUER:
            if _Truth.TRUE in comparisons:
                truth = _Truth.TRUE
            elif _Truth.UNKNOWN in comparisons:
                truth = _Truth.UNKNOWN
            else:
                truth = _Truth.FALSE
        elif _Truth.FALSE in comparisons:
            truth = _Truth.FALSE
        elif _Truth.UNKNOWN in comparisons:
            truth = _Truth.UNKNOWN
        else:
            truth = _Truth.TRUE
    return truth, AvaliacaoCondicaoConformidade(
        grupo=group,
        indice=index,
        chave_fato=condition.chave_fato,
        operador=condition.operador,
        quantificador=condition.quantificador,
        valores_esperados=condition.valores_esperados,
        valores_observados=values,
        fato_ids=tuple(item.id for item in relevant_facts),
        resultado={
            _Truth.TRUE: ResultadoCondicaoConformidade.ATENDE,
            _Truth.FALSE: ResultadoCondicaoConformidade.NAO_ATENDE,
            _Truth.UNKNOWN: ResultadoCondicaoConformidade.DESCONHECIDO,
        }[truth],
    )


def _compare(
    actual: JsonPrimitive,
    operator: OperadorCondicao,
    expected: tuple[JsonPrimitive, ...],
) -> _Truth:
    if operator is OperadorCondicao.IGUAL:
        return _truth(actual == expected[0])
    if operator is OperadorCondicao.DIFERENTE:
        return _truth(actual != expected[0])
    if operator is OperadorCondicao.EM:
        return _truth(actual in expected)
    if operator is OperadorCondicao.NAO_EM:
        return _truth(actual not in expected)
    if operator is OperadorCondicao.CONTEM:
        return _truth(str(expected[0]).casefold() in str(actual).casefold())
    try:
        actual_number = Decimal(str(actual))
        expected_number = Decimal(str(expected[0]))
    except (InvalidOperation, ValueError):
        return _Truth.UNKNOWN
    if operator is OperadorCondicao.MENOR:
        return _truth(actual_number < expected_number)
    if operator is OperadorCondicao.MENOR_OU_IGUAL:
        return _truth(actual_number <= expected_number)
    if operator is OperadorCondicao.MAIOR:
        return _truth(actual_number > expected_number)
    if operator is OperadorCondicao.MAIOR_OU_IGUAL:
        return _truth(actual_number >= expected_number)
    return _Truth.UNKNOWN


def _truth(value: bool) -> _Truth:
    return _Truth.TRUE if value else _Truth.FALSE


def _finding_message(
    result: ResultadoConformidade,
    description: str,
    target_label: str,
    evaluations: tuple[AvaliacaoCondicaoConformidade, ...],
) -> str:
    prefix = {
        ResultadoConformidade.CONFORME: "Atende à condição verificável",
        ResultadoConformidade.DIVERGENCIA: "Possível divergência",
        ResultadoConformidade.NAO_AVALIAVEL: "Não avaliável com os fatos disponíveis",
    }[result]
    decisive = _decisive_evaluation(result, evaluations)
    detail = _evaluation_detail(decisive) if decisive is not None else ""
    return f"{prefix} em {target_label}: {description}{detail}"


def _decisive_evaluation(
    result: ResultadoConformidade,
    evaluations: tuple[AvaliacaoCondicaoConformidade, ...],
) -> AvaliacaoCondicaoConformidade | None:
    expected_result = {
        ResultadoConformidade.DIVERGENCIA: ResultadoCondicaoConformidade.NAO_ATENDE,
        ResultadoConformidade.NAO_AVALIAVEL: ResultadoCondicaoConformidade.DESCONHECIDO,
        ResultadoConformidade.CONFORME: ResultadoCondicaoConformidade.ATENDE,
    }[result]
    requirements = tuple(
        item for item in evaluations if item.grupo is GrupoCondicaoConformidade.REQUISITO
    )
    return next(
        (item for item in requirements if item.resultado is expected_result),
        next((item for item in evaluations if item.resultado is expected_result), None),
    )


def _evaluation_detail(evaluation: AvaliacaoCondicaoConformidade) -> str:
    observed = ", ".join(map(str, evaluation.valores_observados)) or "ausente"
    if evaluation.operador is OperadorCondicao.EXISTE:
        expected = "presente"
    elif evaluation.operador is OperadorCondicao.AUSENTE:
        expected = "ausente"
    else:
        expected_values = ", ".join(map(str, evaluation.valores_esperados))
        expected = f"{evaluation.operador.value.lower()} {expected_values}"
    return f" Valor observado: {observed}; esperado: {evaluation.chave_fato} {expected}."
