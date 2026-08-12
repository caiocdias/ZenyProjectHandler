"""Validação estrutural do schema JSON público de regras de conformidade."""

from __future__ import annotations

import re
from math import isfinite
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

from zeny_project_handler.domain.errors import DomainValidationError

_FACT_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_SCOPES = frozenset({"PROJETO", "DOCUMENTO", "PAGINA", "REGIAO", "ELEMENTO"})
_SEVERITIES = frozenset({"INFORMATIVA", "ALERTA", "ERRO", "CRITICA"})
_OPERATORS = frozenset(
    {
        "EXISTE",
        "AUSENTE",
        "IGUAL",
        "DIFERENTE",
        "MENOR",
        "MENOR_OU_IGUAL",
        "MAIOR",
        "MAIOR_OU_IGUAL",
        "EM",
        "NAO_EM",
        "CONTEM",
    }
)
_QUANTIFIERS = frozenset({"TODOS", "QUALQUER"})


def validar_schema_registro(payload: object) -> dict[str, Any]:
    root = _object(payload, "raiz")
    _keys(root, "raiz", {"schema_version", "registry", "rules"}, required=True)
    if _integer(root.get("schema_version"), "schema_version") != 1:
        _fail("schema_version", "deve ser igual a 1")
    _validate_registry(root.get("registry"))
    rules = _array(root.get("rules"), "rules", minimum=1)
    seen: set[str] = set()
    for index, raw_rule in enumerate(rules):
        rule = _validate_rule(raw_rule, index)
        rule_id = cast(str, rule["id"])
        if rule_id in seen:
            _fail(f"regra '{rule_id}' · campo id", "ID duplicado")
        seen.add(rule_id)
    return root


def _validate_registry(value: object) -> None:
    registry = _object(value, "registry")
    _keys(registry, "registry", {"id", "version"}, required=True)
    registry_id = _text(registry.get("id"), "registry.id")
    try:
        UUID(registry_id)
    except ValueError as error:
        raise DomainValidationError("Campo registry.id: deve ser um UUID válido") from error
    _text(registry.get("version"), "registry.version")


def _validate_rule(value: object, index: int) -> dict[str, Any]:
    prefix = f"rules[{index}]"
    rule = _object(value, prefix)
    required = {
        "id",
        "title",
        "description",
        "scope",
        "severity",
        "source",
        "when",
        "must",
        "enabled",
    }
    allowed = required | {"unless"}
    _keys(rule, prefix, allowed, required=required)
    rule_id = _text(rule.get("id"), f"{prefix}.id")
    label = f"regra '{rule_id}'"
    _text(rule.get("title"), f"{label} · campo title")
    _text(rule.get("description"), f"{label} · campo description")
    _enum(rule.get("scope"), _SCOPES, f"{label} · campo scope")
    _enum(rule.get("severity"), _SEVERITIES, f"{label} · campo severity")
    _validate_source(rule.get("source"), label)
    _validate_conditions(rule.get("when"), label, "when")
    if "unless" in rule:
        _validate_conditions(rule.get("unless"), label, "unless")
    _validate_conditions(rule.get("must"), label, "must", minimum=1)
    if not isinstance(rule.get("enabled"), bool):
        _fail(f"{label} · campo enabled", "deve ser booleano")
    return rule


def _validate_source(value: object, label: str) -> None:
    field = f"{label} · campo source"
    source = _object(value, field)
    required = {"document", "revision", "item"}
    _keys(source, field, required | {"page", "url"}, required=required)
    for name in sorted(required):
        _text(source.get(name), f"{field}.{name}")
    page = source.get("page")
    if page is not None and _integer(page, f"{field}.page") < 1:
        _fail(f"{field}.page", "deve ser positivo")
    url = source.get("url")
    if url is not None:
        parsed = urlparse(_text(url, f"{field}.url"))
        if not parsed.scheme:
            _fail(f"{field}.url", "deve ser uma URI absoluta")


def _validate_conditions(
    value: object,
    label: str,
    group: str,
    *,
    minimum: int = 0,
) -> None:
    conditions = _array(value, f"{label} · campo {group}", minimum=minimum)
    for index, raw_condition in enumerate(conditions):
        prefix = f"{label} · campo {group}[{index}]"
        condition = _object(raw_condition, prefix)
        required = {"fact", "operator", "expected"}
        _keys(condition, prefix, required | {"quantifier"}, required=required)
        fact = _text(condition.get("fact"), f"{prefix}.fact")
        if not _FACT_PATTERN.fullmatch(fact):
            _fail(f"{prefix}.fact", "chave de fato possui formato inválido")
        _enum(condition.get("operator"), _OPERATORS, f"{prefix}.operator")
        expected = _array(condition.get("expected"), f"{prefix}.expected")
        for value_index, item in enumerate(expected):
            if not _json_primitive(item):
                _fail(
                    f"{prefix}.expected[{value_index}]",
                    "deve ser texto, número, booleano ou nulo",
                )
        if "quantifier" in condition:
            _enum(condition.get("quantifier"), _QUANTIFIERS, f"{prefix}.quantifier")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(field, "deve ser um objeto JSON")
    return cast(dict[str, Any], value)


def _array(value: object, field: str, *, minimum: int = 0) -> list[Any]:
    if not isinstance(value, list):
        _fail(field, "deve ser uma lista JSON")
    result = cast(list[Any], value)
    if len(result) < minimum:
        _fail(field, f"deve possuir ao menos {minimum} item(ns)")
    return result


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(field, "deve ser texto não vazio")
    return cast(str, value)


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _fail(field, "deve ser um número inteiro")
    return cast(int, value)


def _enum(value: object, allowed: frozenset[str], field: str) -> None:
    if not isinstance(value, str) or value not in allowed:
        _fail(field, "valor não permitido pelo schema")


def _keys(
    value: dict[str, Any],
    field: str,
    allowed: set[str],
    *,
    required: bool | set[str],
) -> None:
    if required is True:
        required_keys = allowed
    elif required is False:
        required_keys = set()
    else:
        required_keys = required
    missing = sorted(required_keys - value.keys())
    if missing:
        _fail(field, f"campo obrigatório ausente: {missing[0]}")
    extra = sorted(value.keys() - allowed)
    if extra:
        _fail(field, f"campo não permitido: {extra[0]}")


def _json_primitive(value: object) -> bool:
    if isinstance(value, float):
        return isfinite(value)
    return value is None or isinstance(value, (str, int, bool))


def _fail(field: str, reason: str) -> None:
    raise DomainValidationError(f"Campo {field}: {reason}")
