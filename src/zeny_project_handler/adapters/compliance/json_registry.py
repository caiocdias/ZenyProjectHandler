"""Carga do registro JSON de regras normativas e empresariais."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.compliance import (
    CondicaoConformidade,
    FonteNormativa,
    OperadorCondicao,
    QuantificadorCondicao,
    RegistroRegrasConformidade,
    RegraConformidade,
    SeveridadeConformidade,
    TipoEscopoConformidade,
)
from zeny_project_handler.domain.compliance_facts import validar_semantica_registro
from zeny_project_handler.domain.errors import DomainValidationError

from .schema_validation import validar_schema_registro

SEED_PACKAGE = "zeny_project_handler.adapters.compliance.data"
SEED_FILE_NAME = "regras_conformidade_v1.json"


class JsonComplianceRuleRegistry:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def carregar(self) -> RegistroRegrasConformidade:
        if self._path is None:
            return carregar_registro_conformidade_inicial()
        return carregar_registro_conformidade_json(self._path)


def registro_conformidade_de_dict(payload: dict[str, Any]) -> RegistroRegrasConformidade:
    result, _warnings = registro_conformidade_e_avisos_de_dict(payload)
    return result


def registro_conformidade_e_avisos_de_dict(
    payload: dict[str, Any],
) -> tuple[RegistroRegrasConformidade, tuple[str, ...]]:
    payload = validar_schema_registro(payload)
    registry = _object(payload.get("registry"), field_name="registry")
    try:
        registry_id = UUID(str(registry.get("id")))
    except (ValueError, TypeError, AttributeError) as error:
        raise DomainValidationError("registry.id deve ser um UUID válido") from error
    rules = tuple(
        _rule(_object(item, field_name="rule"))
        for item in _list(payload.get("rules"), field_name="rules")
    )
    result = RegistroRegrasConformidade(
        id=registry_id,
        versao=str(registry.get("version", "")),
        versao_schema=int(payload.get("schema_version", 0)),
        regras=rules,
    )
    return result, validar_semantica_registro(result)


def carregar_registro_conformidade_json(path: Path) -> RegistroRegrasConformidade:
    registry, _warnings = carregar_registro_conformidade_json_com_avisos(path)
    return registry


def carregar_registro_conformidade_json_com_avisos(
    path: Path,
) -> tuple[RegistroRegrasConformidade, tuple[str, ...]]:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DomainValidationError("Não foi possível ler o arquivo de regras") from error
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise DomainValidationError(
            f"JSON de regras inválido na linha {error.lineno}, coluna {error.colno}"
        ) from error
    return registro_conformidade_e_avisos_de_dict(_object(payload, field_name="root"))


def carregar_registro_conformidade_texto(content: str) -> RegistroRegrasConformidade:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise DomainValidationError(
            f"JSON de regras inválido na linha {error.lineno}, coluna {error.colno}"
        ) from error
    return registro_conformidade_de_dict(_object(payload, field_name="root"))


def carregar_registro_conformidade_inicial() -> RegistroRegrasConformidade:
    resource = files(SEED_PACKAGE).joinpath(SEED_FILE_NAME)
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError("Registro inicial de conformidade é inválido") from error
    return registro_conformidade_de_dict(_object(payload, field_name="root"))


def registro_conformidade_para_dict(
    registro: RegistroRegrasConformidade,
) -> dict[str, object]:
    return registro.para_dict()


def _rule(data: dict[str, Any]) -> RegraConformidade:
    source = _object(data.get("source"), field_name="source")
    rule_id = str(data.get("id", ""))
    try:
        return RegraConformidade(
            id=rule_id,
            titulo=str(data.get("title", "")),
            descricao=str(data.get("description", "")),
            escopo=TipoEscopoConformidade(str(data.get("scope"))),
            severidade=SeveridadeConformidade(str(data.get("severity"))),
            fonte=FonteNormativa(
                documento=str(source.get("document", "")),
                revisao=str(source.get("revision", "")),
                item=str(source.get("item", "")),
                pagina=(int(source["page"]) if source.get("page") is not None else None),
                url=(str(source["url"]) if source.get("url") else None),
            ),
            aplicabilidade=_conditions(data.get("when", []), "when"),
            excecoes=_conditions(data.get("unless", []), "unless"),
            avaliabilidade=_conditions(data.get("evaluate_when", []), "evaluate_when"),
            requisitos=_conditions(data.get("must"), "must"),
            ativa=bool(data.get("enabled", True)),
        )
    except (DomainValidationError, ValueError) as error:
        raise DomainValidationError(f"Regra '{rule_id}': {error}") from error


def _conditions(value: object, group: str) -> tuple[CondicaoConformidade, ...]:
    result: list[CondicaoConformidade] = []
    for index, item in enumerate(_list(value, field_name=group)):
        try:
            result.append(_condition(_object(item, field_name=f"{group}[{index}]")))
        except (DomainValidationError, ValueError) as error:
            raise DomainValidationError(f"campo {group}[{index}]: {error}") from error
    return tuple(result)


def _condition(data: dict[str, Any]) -> CondicaoConformidade:
    return CondicaoConformidade(
        chave_fato=str(data.get("fact", "")),
        operador=OperadorCondicao(str(data.get("operator"))),
        valores_esperados=tuple(
            _json_primitive(value)
            for value in _list(data.get("expected", []), field_name="expected")
        ),
        quantificador=QuantificadorCondicao(str(data.get("quantifier", "TODOS"))),
    )


def _json_primitive(value: object) -> JsonPrimitive:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    raise DomainValidationError("Valor esperado deve ser um primitivo JSON")


def _object(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError(f"{field_name} deve ser um objeto JSON")
    return cast(dict[str, Any], value)


def _list(value: object, *, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise DomainValidationError(f"{field_name} deve ser uma lista JSON")
    return value
