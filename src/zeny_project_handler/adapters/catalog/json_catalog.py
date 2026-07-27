"""Serialização JSON na fronteira do catálogo técnico."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from zeny_project_handler.domain.catalog import (
    AssinaturaSimbologia,
    AvisoImportacao,
    CatalogoTecnico,
    CompatibilidadeEstruturaCabo,
    ContagensOrigem,
    FonteCatalogo,
    GrupoOpcao,
    ItemCatalogoType,
    JsonPrimitive,
    OpcaoCatalogo,
    RegraSimbologia,
    TipoCabo,
    TipoEquipamento,
    TipoEstruturaBt,
    TipoEstruturaMt,
    TipoPoste,
)
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    SituacaoProjeto,
    StatusCatalogo,
)
from zeny_project_handler.domain.errors import DomainValidationError

SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2})
SEED_PACKAGE = "zeny_project_handler.adapters.catalog.data"
SEED_FILE_NAME = "catalogo_cemig_v2.json"


def _object(value: object, *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DomainValidationError(f"{field_name} deve ser um objeto JSON")
    return cast(dict[str, Any], value)


def _list(value: object, *, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise DomainValidationError(f"{field_name} deve ser uma lista JSON")
    return value


def _uuid(value: object, *, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise DomainValidationError(f"{field_name} deve ser um UUID válido") from error


def _datetime(value: object, *, field_name: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as error:
        raise DomainValidationError(f"{field_name} deve ser uma data ISO-8601") from error


def _extras(value: object) -> tuple[tuple[str, JsonPrimitive], ...]:
    values = _object(value, field_name="extra_attributes")
    extras: list[tuple[str, JsonPrimitive]] = []
    for key, item in values.items():
        if not isinstance(item, (str, int, bool, Decimal)) and item is not None:
            raise DomainValidationError("Atributos extras do seed devem ser valores primitivos")
        extras.append((key, item))
    return tuple(extras)


def _common_item_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _uuid(data.get("id"), field_name="item.id"),
        "codigo": str(data.get("code", "")),
        "descricao": str(data.get("description", "")),
        "ativo": bool(data.get("active")),
        "linha_origem": int(data.get("source_row", 0)),
        "atributos_extras": _extras(data.get("extra_attributes", {})),
    }


def _item_from_dict(data: dict[str, Any]) -> ItemCatalogoType:
    kind = data.get("kind")
    common = _common_item_fields(data)
    if kind == "poste":
        return TipoPoste(
            **common,
            altura_m=Decimal(str(data.get("height_m"))),
            resistencia_dan=int(data.get("resistance_dan", 0)),
            formato_opcao_id=_uuid(data.get("format_option_id"), field_name="format_option_id"),
        )
    if kind == "estrutura_mt":
        return TipoEstruturaMt(
            **common,
            configuracao_fases_opcao_id=_uuid(
                data.get("phase_configuration_option_id"),
                field_name="phase_configuration_option_id",
            ),
            tecnologia_rede_opcao_id=_uuid(
                data.get("network_technology_option_id"),
                field_name="network_technology_option_id",
            ),
            ancoragem=bool(data.get("anchorage")),
            expressao_cabos_original=str(data.get("original_cable_expression", "")),
        )
    if kind == "estrutura_bt":
        return TipoEstruturaBt(
            **common,
            tecnologia_rede_opcao_id=_uuid(
                data.get("network_technology_option_id"),
                field_name="network_technology_option_id",
            ),
            ancoragem=bool(data.get("anchorage")),
            expressao_cabos_original=str(data.get("original_cable_expression", "")),
        )
    if kind == "cabo":
        factor = data.get("condemnation_factor")
        return TipoCabo(
            **common,
            configuracao_fases_opcao_id=_uuid(
                data.get("phase_configuration_option_id"),
                field_name="phase_configuration_option_id",
            ),
            tecnologia_rede_opcao_id=_uuid(
                data.get("network_technology_option_id"),
                field_name="network_technology_option_id",
            ),
            nivel_tensao_opcao_id=_uuid(
                data.get("voltage_level_option_id"), field_name="voltage_level_option_id"
            ),
            fator_condenacao=Decimal(str(factor)) if factor is not None else None,
            referencia_condutor=str(data.get("reference_size", "")),
        )
    if kind == "equipamento":
        return TipoEquipamento(
            **common,
            configuracao_fases_opcao_id=_uuid(
                data.get("phase_configuration_option_id"),
                field_name="phase_configuration_option_id",
            ),
            classe_equipamento_opcao_id=_uuid(
                data.get("equipment_class_option_id"),
                field_name="equipment_class_option_id",
            ),
        )
    raise DomainValidationError(f"Tipo de item desconhecido: {kind}")


def _option_groups_from_payload(payload: dict[str, Any]) -> tuple[GrupoOpcao, ...]:
    groups: list[GrupoOpcao] = []
    for raw_group in _list(payload.get("option_groups"), field_name="option_groups"):
        group_data = _object(raw_group, field_name="option_group")
        options = tuple(
            OpcaoCatalogo(
                id=_uuid(option_data.get("id"), field_name="option.id"),
                codigo=str(option_data.get("code", "")),
                rotulo=str(option_data.get("label", "")),
                ativo=bool(option_data.get("active")),
                ordem=int(option_data.get("order", 0)),
            )
            for raw_option in _list(group_data.get("options"), field_name="options")
            for option_data in [_object(raw_option, field_name="option")]
        )
        groups.append(
            GrupoOpcao(
                id=_uuid(group_data.get("id"), field_name="option_group.id"),
                chave=str(group_data.get("key", "")),
                nome=str(group_data.get("name", "")),
                ordem=int(group_data.get("order", 0)),
                opcoes=options,
            )
        )
    return tuple(groups)


def _compatibilities_from_payload(
    payload: dict[str, Any],
) -> tuple[CompatibilidadeEstruturaCabo, ...]:
    return tuple(
        CompatibilidadeEstruturaCabo(
            id=_uuid(data.get("id"), field_name="compatibility.id"),
            tipo_estrutura_id=_uuid(data.get("structure_type_id"), field_name="structure_type_id"),
            tipo_cabo_id=_uuid(data.get("cable_type_id"), field_name="cable_type_id"),
            expressao_origem=str(data.get("source_expression", "")),
        )
        for raw in _list(payload.get("compatibilities"), field_name="compatibilities")
        for data in [_object(raw, field_name="compatibility")]
    )


def _symbol_rules_from_payload(payload: dict[str, Any]) -> tuple[RegraSimbologia, ...]:
    return tuple(
        RegraSimbologia(
            id=_uuid(data.get("id"), field_name="symbol_rule.id"),
            categoria_elemento=CategoriaElemento(str(data.get("element_category"))),
            situacao_projeto=SituacaoProjeto(str(data.get("project_situation"))),
            icone=str(data.get("icon", "")),
            cor=str(data.get("color", "")),
            padrao_traco=str(data.get("stroke_pattern", "")),
            rotulo=str(data.get("label", "")),
        )
        for raw in _list(payload.get("symbol_rules"), field_name="symbol_rules")
        for data in [_object(raw, field_name="symbol_rule")]
    )


def _symbol_signatures_from_payload(
    payload: dict[str, Any],
) -> tuple[AssinaturaSimbologia, ...]:
    return tuple(
        AssinaturaSimbologia(
            id=_uuid(data.get("id"), field_name="recognition_signature.id"),
            categoria_elemento=(
                CategoriaElemento(str(data.get("element_category")))
                if data.get("element_category") is not None
                else None
            ),
            situacao_projeto=SituacaoProjeto(str(data.get("project_situation"))),
            cor=str(data.get("color", "")),
            tolerancia_cor=int(data.get("color_tolerance", 0)),
            padrao_traco=(
                str(data.get("stroke_pattern")) if data.get("stroke_pattern") is not None else None
            ),
            prioridade=int(data.get("priority", 0)),
            origem=str(data.get("source", "")),
        )
        for raw in _list(
            payload.get("recognition_signatures", []), field_name="recognition_signatures"
        )
        for data in [_object(raw, field_name="recognition_signature")]
    )


def _warnings_from_payload(payload: dict[str, Any]) -> tuple[AvisoImportacao, ...]:
    return tuple(
        AvisoImportacao(
            codigo=str(data.get("code", "")),
            mensagem=str(data.get("message", "")),
            categoria=CategoriaElemento(str(data.get("category"))),
            valor=str(data.get("value", "")),
            linhas_origem=tuple(
                int(row) for row in _list(data.get("source_rows"), field_name="source_rows")
            ),
            resolucao=str(data.get("resolution", "")),
        )
        for raw in _list(payload.get("warnings", []), field_name="warnings")
        for data in [_object(raw, field_name="warning")]
    )


def catalogo_de_dict(payload: dict[str, Any]) -> CatalogoTecnico:
    schema_version = int(payload.get("schema_version", 0))
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise DomainValidationError(
            f"Schema de catálogo não suportado: {schema_version}; "
            f"esperados: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    catalog_data = _object(payload.get("catalog"), field_name="catalog")
    source_data = _object(payload.get("source"), field_name="source")
    counts_data = _object(source_data.get("source_counts"), field_name="source_counts")

    groups = _option_groups_from_payload(payload)
    items = tuple(
        _item_from_dict(_object(raw_item, field_name="item"))
        for raw_item in _list(payload.get("items"), field_name="items")
    )
    compatibilities = _compatibilities_from_payload(payload)
    symbol_rules = _symbol_rules_from_payload(payload)
    symbol_signatures = _symbol_signatures_from_payload(payload)
    warnings = _warnings_from_payload(payload)

    published_at = catalog_data.get("published_at")
    return CatalogoTecnico(
        id=_uuid(catalog_data.get("id"), field_name="catalog.id"),
        versao=int(catalog_data.get("version", 0)),
        versao_schema=schema_version,
        status=StatusCatalogo(str(catalog_data.get("status"))),
        criado_em=_datetime(catalog_data.get("created_at"), field_name="created_at"),
        publicado_em=(
            _datetime(published_at, field_name="published_at") if published_at is not None else None
        ),
        fonte=FonteCatalogo(
            nome_arquivo=str(source_data.get("file_name", "")),
            sha256=str(source_data.get("sha256", "")),
            planilha=str(source_data.get("sheet", "")),
            contagens=ContagensOrigem(
                postes=int(counts_data.get("postes", 0)),
                estruturas_mt=int(counts_data.get("estruturas_mt", 0)),
                estruturas_bt=int(counts_data.get("estruturas_bt", 0)),
                cabos=int(counts_data.get("cabos", 0)),
                equipamentos=int(counts_data.get("equipamentos", 0)),
            ),
            importado_em=_datetime(source_data.get("imported_at"), field_name="imported_at"),
        ),
        grupos_opcao=groups,
        itens=items,
        compatibilidades=compatibilities,
        regras_simbologia=symbol_rules,
        avisos_importacao=warnings,
        assinaturas_simbologia=symbol_signatures,
    )


def carregar_catalogo_json(path: Path) -> CatalogoTecnico:
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError(f"Não foi possível carregar o catálogo: {path}") from error
    return catalogo_de_dict(_object(raw_payload, field_name="root"))


def carregar_catalogo_inicial() -> CatalogoTecnico:
    resource = files(SEED_PACKAGE).joinpath(SEED_FILE_NAME)
    try:
        raw_payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DomainValidationError("Seed inicial do catálogo é inválido") from error
    return catalogo_de_dict(_object(raw_payload, field_name="root"))


def _common_item_dict(item: ItemCatalogoType) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "code": item.codigo,
        "description": item.descricao,
        "active": item.ativo,
        "source_row": item.linha_origem,
        "extra_attributes": dict(item.atributos_extras),
    }


def _item_to_dict(item: ItemCatalogoType) -> dict[str, Any]:
    data = _common_item_dict(item)
    if isinstance(item, TipoPoste):
        data.update(
            kind="poste",
            height_m=str(item.altura_m),
            resistance_dan=item.resistencia_dan,
            format_option_id=str(item.formato_opcao_id),
        )
    elif isinstance(item, TipoEstruturaMt):
        data.update(
            kind="estrutura_mt",
            phase_configuration_option_id=str(item.configuracao_fases_opcao_id),
            network_technology_option_id=str(item.tecnologia_rede_opcao_id),
            anchorage=item.ancoragem,
            original_cable_expression=item.expressao_cabos_original,
        )
    elif isinstance(item, TipoEstruturaBt):
        data.update(
            kind="estrutura_bt",
            network_technology_option_id=str(item.tecnologia_rede_opcao_id),
            anchorage=item.ancoragem,
            original_cable_expression=item.expressao_cabos_original,
        )
    elif isinstance(item, TipoCabo):
        data.update(
            kind="cabo",
            phase_configuration_option_id=str(item.configuracao_fases_opcao_id),
            network_technology_option_id=str(item.tecnologia_rede_opcao_id),
            voltage_level_option_id=str(item.nivel_tensao_opcao_id),
            condemnation_factor=(
                str(item.fator_condenacao) if item.fator_condenacao is not None else None
            ),
            reference_size=item.referencia_condutor,
        )
    elif isinstance(item, TipoEquipamento):
        data.update(
            kind="equipamento",
            phase_configuration_option_id=str(item.configuracao_fases_opcao_id),
            equipment_class_option_id=str(item.classe_equipamento_opcao_id),
        )
    return data


def catalogo_para_dict(catalogo: CatalogoTecnico) -> dict[str, Any]:
    counts = catalogo.fonte.contagens
    return {
        "schema_version": catalogo.versao_schema,
        "catalog": {
            "id": str(catalogo.id),
            "version": catalogo.versao,
            "status": catalogo.status.value,
            "created_at": catalogo.criado_em.isoformat(),
            "published_at": (
                catalogo.publicado_em.isoformat() if catalogo.publicado_em is not None else None
            ),
        },
        "source": {
            "file_name": catalogo.fonte.nome_arquivo,
            "sha256": catalogo.fonte.sha256,
            "sheet": catalogo.fonte.planilha,
            "source_counts": {
                "postes": counts.postes,
                "estruturas_mt": counts.estruturas_mt,
                "estruturas_bt": counts.estruturas_bt,
                "cabos": counts.cabos,
                "equipamentos": counts.equipamentos,
            },
            "imported_at": catalogo.fonte.importado_em.isoformat(),
        },
        "option_groups": [
            {
                "id": str(group.id),
                "key": group.chave,
                "name": group.nome,
                "order": group.ordem,
                "options": [
                    {
                        "id": str(option.id),
                        "code": option.codigo,
                        "label": option.rotulo,
                        "active": option.ativo,
                        "order": option.ordem,
                    }
                    for option in group.opcoes
                ],
            }
            for group in catalogo.grupos_opcao
        ],
        "items": [_item_to_dict(item) for item in catalogo.itens],
        "compatibilities": [
            {
                "id": str(compatibility.id),
                "structure_type_id": str(compatibility.tipo_estrutura_id),
                "cable_type_id": str(compatibility.tipo_cabo_id),
                "source_expression": compatibility.expressao_origem,
            }
            for compatibility in catalogo.compatibilidades
        ],
        "symbol_rules": [
            {
                "id": str(rule.id),
                "element_category": rule.categoria_elemento.value,
                "project_situation": rule.situacao_projeto.value,
                "icon": rule.icone,
                "color": rule.cor,
                "stroke_pattern": rule.padrao_traco,
                "label": rule.rotulo,
            }
            for rule in catalogo.regras_simbologia
        ],
        "recognition_signatures": [
            {
                "id": str(signature.id),
                "element_category": (
                    signature.categoria_elemento.value
                    if signature.categoria_elemento is not None
                    else None
                ),
                "project_situation": signature.situacao_projeto.value,
                "color": signature.cor,
                "color_tolerance": signature.tolerancia_cor,
                "stroke_pattern": signature.padrao_traco,
                "priority": signature.prioridade,
                "source": signature.origem,
            }
            for signature in catalogo.assinaturas_simbologia
        ],
        "warnings": [
            {
                "code": warning.codigo,
                "message": warning.mensagem,
                "category": warning.categoria.value,
                "value": warning.valor,
                "source_rows": list(warning.linhas_origem),
                "resolution": warning.resolucao,
            }
            for warning in catalogo.avisos_importacao
        ],
    }
