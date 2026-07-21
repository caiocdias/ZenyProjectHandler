"""Carga explícita do registro JSON de regras de interpretação."""

from __future__ import annotations

import json
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from zeny_project_handler.domain.enums import CategoriaElemento, TipoEvidencia
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.interpretation import (
    RegistroRegrasInterpretacao,
    RegraReconhecimento,
    RegraRelacaoInterpretacao,
)

SEED_PACKAGE = "zeny_project_handler.adapters.interpretation.data"
SEED_FILE_NAME = "regras_interpretacao_v1.json"


class JsonRuleRegistry:
    """Repositório que usa o seed embarcado ou um arquivo externo configurável."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def carregar(self) -> RegistroRegrasInterpretacao:
        if self._path is None:
            return carregar_registro_regras_inicial()
        return carregar_registro_regras_json(self._path)


def _object(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError(f"{field_name} deve ser um objeto JSON")
    return cast(dict[str, Any], value)


def _list(value: object, *, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise DomainValidationError(f"{field_name} deve ser uma lista JSON")
    return value


def registro_regras_de_dict(payload: dict[str, Any]) -> RegistroRegrasInterpretacao:
    registry = _object(payload.get("registry"), field_name="registry")
    recognition = tuple(
        RegraReconhecimento(
            id=str(data.get("id", "")),
            categoria=CategoriaElemento(str(data.get("category"))),
            tipos_evidencia=tuple(
                TipoEvidencia(str(kind))
                for kind in _list(data.get("evidence_types"), field_name="evidence_types")
            ),
            estrategia=str(data.get("strategy", "")),
            confianca_base=Decimal(str(data.get("base_confidence"))),
            distancia_contexto_maxima=Decimal(str(data.get("maximum_context_distance"))),
            ativa=bool(data.get("enabled", True)),
        )
        for raw in _list(payload.get("recognition_rules"), field_name="recognition_rules")
        for data in [_object(raw, field_name="recognition_rule")]
    )
    relations = tuple(
        RegraRelacaoInterpretacao(
            id=str(data.get("id", "")),
            categoria_origem=CategoriaElemento(str(data.get("origin_category"))),
            categoria_destino=CategoriaElemento(str(data.get("destination_category"))),
            tipo_relacao=str(data.get("relation_type", "")),
            estrategia=str(data.get("strategy", "")),
            distancia_maxima=Decimal(str(data.get("maximum_distance"))),
            confianca=Decimal(str(data.get("confidence"))),
            ativa=bool(data.get("enabled", True)),
        )
        for raw in _list(payload.get("relation_rules", []), field_name="relation_rules")
        for data in [_object(raw, field_name="relation_rule")]
    )
    try:
        registry_id = UUID(str(registry.get("id")))
    except (ValueError, TypeError, AttributeError) as error:
        raise DomainValidationError("registry.id deve ser um UUID válido") from error
    return RegistroRegrasInterpretacao(
        id=registry_id,
        versao=str(registry.get("version", "")),
        versao_schema=int(payload.get("schema_version", 0)),
        regras_reconhecimento=recognition,
        regras_relacao=relations,
    )


def carregar_registro_regras_json(path: Path) -> RegistroRegrasInterpretacao:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError(f"Não foi possível carregar regras: {path}") from error
    return registro_regras_de_dict(_object(payload, field_name="root"))


def carregar_registro_regras_inicial() -> RegistroRegrasInterpretacao:
    resource = files(SEED_PACKAGE).joinpath(SEED_FILE_NAME)
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError("Registro inicial de regras é inválido") from error
    return registro_regras_de_dict(_object(payload, field_name="root"))
