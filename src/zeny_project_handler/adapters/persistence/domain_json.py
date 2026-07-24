"""Codec JSON explícito para entidades de domínio, sem importação dinâmica."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar, cast
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    ArtefatoExtraido,
    DecisaoRevisao,
    DiagnosticoAnalise,
    EvidenciaDocumento,
    ExecucaoAnalise,
    OrigemObjetoPdf,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.documents import DocumentoProjeto, PaginaDocumento
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoConexao,
    EstadoExecucaoAnalise,
    EstadoRevisao,
    NivelRede,
    OrigemComprimentoVao,
    SituacaoProjeto,
    StatusCatalogo,
    TipoAcaoRevisaoManual,
    TipoDecisaoRevisao,
    TipoEvidencia,
    TipoGeometria,
    TipoOrigemPdf,
    TipoPontoRede,
    TipoVinculoObra,
)
from zeny_project_handler.domain.operations import VinculoObra
from zeny_project_handler.domain.project import (
    Cabo,
    ConexaoInternaEquipamento,
    Equipamento,
    EstruturaBt,
    EstruturaMt,
    FotoElemento,
    PontoRede,
    Poste,
    Projeto,
    RegistroRevisaoManual,
    RelacaoConfirmada,
    TerminalEquipamento,
)
from zeny_project_handler.domain.project_metadata import ContatoSolicitante, MetadadosProjeto
from zeny_project_handler.domain.values import (
    CaixaPagina,
    CoordenadaCampo,
    GeometriaDocumento,
    PontoNormalizado,
)

from .errors import DomainCodecError

T = TypeVar("T")

_DOMAIN_CLASSES: dict[str, type[Any]] = {
    domain_type.__name__: domain_type
    for domain_type in (
        ArtefatoExtraido,
        Cabo,
        CaixaPagina,
        ConexaoInternaEquipamento,
        ContatoSolicitante,
        CoordenadaCampo,
        DecisaoRevisao,
        DiagnosticoAnalise,
        DocumentoProjeto,
        Equipamento,
        EstruturaBt,
        EstruturaMt,
        EvidenciaDocumento,
        ExecucaoAnalise,
        FotoElemento,
        GeometriaDocumento,
        MetadadosProjeto,
        OrigemObjetoPdf,
        PaginaDocumento,
        PontoNormalizado,
        PontoRede,
        Poste,
        Projeto,
        PropostaElemento,
        PropostaRelacao,
        RegistroRevisaoManual,
        RelacaoConfirmada,
        TerminalEquipamento,
        VinculoObra,
    )
}

_ENUM_CLASSES: dict[str, type[Enum]] = {
    enum_type.__name__: enum_type
    for enum_type in (
        CategoriaElemento,
        EstadoConexao,
        EstadoExecucaoAnalise,
        EstadoRevisao,
        NivelRede,
        OrigemComprimentoVao,
        SituacaoProjeto,
        StatusCatalogo,
        TipoAcaoRevisaoManual,
        TipoDecisaoRevisao,
        TipoEvidencia,
        TipoGeometria,
        TipoOrigemPdf,
        TipoPontoRede,
        TipoVinculoObra,
    )
}

_UNSUPPORTED = object()


def _encode_scalar(value: object) -> object:
    if isinstance(value, Enum):
        return {"$enum": value.__class__.__name__, "value": value.value}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    return _UNSUPPORTED


def _encode_collection(value: object) -> object:
    if isinstance(value, tuple):
        return {"$tuple": [_encode(item) for item in value]}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise DomainCodecError("Somente dicionários com chaves textuais podem ser persistidos")
        return {str(key): _encode(item) for key, item in value.items()}
    return _UNSUPPORTED


def _encode_dataclass(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        class_name = value.__class__.__name__
        if class_name not in _DOMAIN_CLASSES:
            raise DomainCodecError(f"Tipo de domínio não registrado: {class_name}")
        return {
            "$type": class_name,
            "fields": {field.name: _encode(getattr(value, field.name)) for field in fields(value)},
        }
    return _UNSUPPORTED


def _encode(value: object) -> object:
    for encoder in (_encode_scalar, _encode_collection, _encode_dataclass):
        encoded = encoder(value)
        if encoded is not _UNSUPPORTED:
            return encoded
    raise DomainCodecError(f"Valor não serializável: {type(value).__name__}")


def _decode_scalar_tag(value: dict[str, Any]) -> object:
    if "$uuid" in value:
        return UUID(str(value["$uuid"]))
    if "$decimal" in value:
        return Decimal(str(value["$decimal"]))
    if "$datetime" in value:
        return datetime.fromisoformat(str(value["$datetime"]))
    if "$date" in value:
        return date.fromisoformat(str(value["$date"]))
    return _UNSUPPORTED


def _decode_complex_tag(value: dict[str, Any]) -> object:
    if "$tuple" in value:
        raw_items = value["$tuple"]
        if not isinstance(raw_items, list):
            raise DomainCodecError("Tupla persistida deve ser uma lista JSON")
        return tuple(_decode(item) for item in raw_items)
    if "$enum" in value:
        enum_name = str(value["$enum"])
        enum_type = _ENUM_CLASSES.get(enum_name)
        if enum_type is None:
            raise DomainCodecError(f"Enum de domínio não registrado: {enum_name}")
        return enum_type(str(value.get("value")))
    if "$type" in value:
        class_name = str(value["$type"])
        domain_type = _DOMAIN_CLASSES.get(class_name)
        raw_fields = value.get("fields")
        if domain_type is None or not isinstance(raw_fields, dict):
            raise DomainCodecError(f"Tipo de domínio inválido: {class_name}")
        kwargs: dict[str, Any] = {str(key): _decode(item) for key, item in raw_fields.items()}
        return domain_type(**kwargs)
    return _UNSUPPORTED


def _tagged_value(value: dict[str, Any]) -> object:
    for decoder in (_decode_scalar_tag, _decode_complex_tag):
        decoded = decoder(value)
        if decoded is not _UNSUPPORTED:
            return decoded
    return {str(key): _decode(item) for key, item in value.items()}


def _decode(value: object) -> object:
    if isinstance(value, dict):
        return _tagged_value(cast(dict[str, Any], value))
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def dumps_domain(value: object) -> str:
    """Produza JSON canônico, apropriado para hash e comparação."""
    return json.dumps(_encode(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads_domain(payload: str, expected_type: type[T] | tuple[type[T], ...]) -> T:
    """Reconstrua somente classes presentes no registro explícito."""
    try:
        decoded_json = json.loads(payload)
        decoded = _decode(decoded_json)
    except (ValueError, TypeError, KeyError) as error:
        raise DomainCodecError("Payload persistido é inválido") from error
    if not isinstance(decoded, expected_type):
        expected_name = (
            " | ".join(item.__name__ for item in expected_type)
            if isinstance(expected_type, tuple)
            else expected_type.__name__
        )
        raise DomainCodecError(f"Payload contém {type(decoded).__name__}; esperado {expected_name}")
    return decoded
