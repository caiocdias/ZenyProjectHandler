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
    CondicaoConformidade,
    FatoConformidade,
    OperadorCondicao,
    QuantificadorCondicao,
    RegistroRegrasConformidade,
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
            applicability = _conditions(rule.aplicabilidade, scoped_facts)
            if applicability is _Truth.FALSE:
                continue
            if applicability is _Truth.UNKNOWN:
                result = ResultadoConformidade.NAO_AVALIAVEL
            else:
                exception = _conditions(rule.excecoes, scoped_facts)
                if rule.excecoes and exception is _Truth.TRUE:
                    continue
                requirement = _conditions(rule.requisitos, scoped_facts)
                result = {
                    _Truth.TRUE: ResultadoConformidade.CONFORME,
                    _Truth.FALSE: ResultadoConformidade.DIVERGENCIA,
                    _Truth.UNKNOWN: ResultadoConformidade.NAO_AVALIAVEL,
                }[requirement]
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for fact in scoped_facts
                    if fact.chave
                    in {
                        condition.chave_fato
                        for condition in (
                            *rule.aplicabilidade,
                            *rule.excecoes,
                            *rule.requisitos,
                        )
                    }
                    for evidence_id in fact.evidencia_ids
                )
            )
            findings.append(
                AchadoConformidade(
                    id=uuid5(target.id, f"{registro.assinatura()}:{rule.id}"),
                    regra_id=rule.id,
                    alvo_id=target.id,
                    resultado=result,
                    severidade=rule.severidade,
                    titulo=rule.titulo,
                    mensagem=_finding_message(result, rule.descricao, target.rotulo),
                    fonte=rule.fonte,
                    versao_regras=registro.versao,
                    evidencia_ids=evidence_ids,
                )
            )
    return tuple(findings)


def _conditions(
    conditions: tuple[CondicaoConformidade, ...],
    facts: tuple[FatoConformidade, ...],
) -> _Truth:
    if not conditions:
        return _Truth.TRUE
    results = tuple(_condition(condition, facts) for condition in conditions)
    if _Truth.FALSE in results:
        return _Truth.FALSE
    if _Truth.UNKNOWN in results:
        return _Truth.UNKNOWN
    return _Truth.TRUE


def _condition(
    condition: CondicaoConformidade,
    facts: tuple[FatoConformidade, ...],
) -> _Truth:
    values = tuple(fact.valor for fact in facts if fact.chave == condition.chave_fato)
    if condition.operador is OperadorCondicao.EXISTE:
        return _truth(bool(values))
    if condition.operador is OperadorCondicao.AUSENTE:
        return _truth(not values)
    if not values:
        return _Truth.UNKNOWN
    comparisons = tuple(
        _compare(value, condition.operador, condition.valores_esperados) for value in values
    )
    known = tuple(item for item in comparisons if item is not _Truth.UNKNOWN)
    if not known:
        return _Truth.UNKNOWN
    if condition.quantificador is QuantificadorCondicao.QUALQUER:
        return _Truth.TRUE if _Truth.TRUE in known else _Truth.FALSE
    return _Truth.FALSE if _Truth.FALSE in known else _Truth.TRUE


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
) -> str:
    prefix = {
        ResultadoConformidade.CONFORME: "Atende à condição verificável",
        ResultadoConformidade.DIVERGENCIA: "Possível divergência",
        ResultadoConformidade.NAO_AVALIAVEL: "Não avaliável com os fatos disponíveis",
    }[result]
    return f"{prefix} em {target_label}: {description}"
