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
from zeny_project_handler.domain.errors import DomainValidationError

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
    registry = _object(payload.get("registry"), field_name="registry")
    try:
        registry_id = UUID(str(registry.get("id")))
    except (ValueError, TypeError, AttributeError) as error:
        raise DomainValidationError("registry.id deve ser um UUID válido") from error
    rules = tuple(
        _rule(_object(item, field_name="rule"))
        for item in _list(payload.get("rules"), field_name="rules")
    )
    return RegistroRegrasConformidade(
        id=registry_id,
        versao=str(registry.get("version", "")),
        versao_schema=int(payload.get("schema_version", 0)),
        regras=rules,
    )


def carregar_registro_conformidade_json(path: Path) -> RegistroRegrasConformidade:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError(f"Não foi possível carregar regras: {path}") from error
    return registro_conformidade_de_dict(_object(payload, field_name="root"))


def carregar_registro_conformidade_inicial() -> RegistroRegrasConformidade:
    resource = files(SEED_PACKAGE).joinpath(SEED_FILE_NAME)
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError("Registro inicial de conformidade é inválido") from error
    return registro_conformidade_de_dict(_object(payload, field_name="root"))


def _rule(data: dict[str, Any]) -> RegraConformidade:
    source = _object(data.get("source"), field_name="source")
    return RegraConformidade(
        id=str(data.get("id", "")),
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
        aplicabilidade=tuple(
            _condition(_object(item, field_name="when condition"))
            for item in _list(data.get("when", []), field_name="when")
        ),
        excecoes=tuple(
            _condition(_object(item, field_name="unless condition"))
            for item in _list(data.get("unless", []), field_name="unless")
        ),
        requisitos=tuple(
            _condition(_object(item, field_name="must condition"))
            for item in _list(data.get("must"), field_name="must")
        ),
        ativa=bool(data.get("enabled", True)),
    )


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
