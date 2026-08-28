"""Metadados técnicos e dados sensíveis separados do agregado elétrico."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from zeny_project_handler.domain.catalog import ExtraAttributes
from zeny_project_handler.domain.errors import DomainValidationError

NOTA_SERVICO_PATTERN = re.compile(r"^[0-9]{10}$")
CODIGO_SERVICO_PATTERN = re.compile(r"^[0-9]{4}$")
ESCALA_PATTERN = re.compile(r"^1:\d+$")


def _optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else None
    return normalized or None


def normalizar_numero_ns(value: str) -> str:
    """Normalize e valide a NS informada pelo usuário sem perder zeros à esquerda."""
    normalized = value.strip()
    if not NOTA_SERVICO_PATTERN.fullmatch(normalized):
        raise DomainValidationError("Número da NS deve conter exatamente 10 dígitos")
    return normalized


def normalizar_codigo_servico(value: str) -> str:
    """Normalize e valide um código de serviço sem perder zeros à esquerda."""
    if not isinstance(value, str):
        raise DomainValidationError("Código de serviço deve conter exatamente 4 dígitos ASCII")
    normalized = value.strip()
    if not CODIGO_SERVICO_PATTERN.fullmatch(normalized):
        raise DomainValidationError("Código de serviço deve conter exatamente 4 dígitos ASCII")
    return normalized


@dataclass(frozen=True, slots=True, kw_only=True)
class MetadadosProjeto:
    nota_servico: str | None = None
    circuito: str | None = None
    municipio: str | None = None
    bairro: str | None = None
    tipo_servico: str | None = None
    escala: str | None = None
    formato_folha: str | None = None
    numero_folha: str | None = None
    data_projeto: date | None = None
    impacto_ambiental: bool | None = None
    dispositivo_seccionamento: str | None = None
    atributos_extras: ExtraAttributes = ()

    def __post_init__(self) -> None:
        service_note = _optional_text(self.nota_servico)
        scale = _optional_text(self.escala)
        if service_note is not None:
            service_note = normalizar_numero_ns(service_note)
        if scale is not None and not ESCALA_PATTERN.fullmatch(scale):
            raise DomainValidationError("Escala deve usar o formato 1:n")
        extras = tuple(sorted(self.atributos_extras, key=lambda item: item[0]))
        if any(not key.strip() for key, _ in extras) or len({key for key, _ in extras}) != len(
            extras
        ):
            raise DomainValidationError("Metadados extras devem possuir chaves únicas e não vazias")
        object.__setattr__(self, "nota_servico", service_note)
        object.__setattr__(self, "circuito", _optional_text(self.circuito))
        object.__setattr__(self, "municipio", _optional_text(self.municipio))
        object.__setattr__(self, "bairro", _optional_text(self.bairro))
        object.__setattr__(self, "tipo_servico", _optional_text(self.tipo_servico))
        object.__setattr__(self, "escala", scale)
        object.__setattr__(self, "formato_folha", _optional_text(self.formato_folha))
        object.__setattr__(self, "numero_folha", _optional_text(self.numero_folha))
        object.__setattr__(
            self, "dispositivo_seccionamento", _optional_text(self.dispositivo_seccionamento)
        )
        object.__setattr__(self, "atributos_extras", extras)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContatoSolicitante:
    nome: str | None = None
    telefone: str | None = None

    def __post_init__(self) -> None:
        name = _optional_text(self.nome)
        phone = _optional_text(self.telefone)
        if name is None and phone is None:
            raise DomainValidationError("Contato deve possuir nome ou telefone")
        object.__setattr__(self, "nome", name)
        object.__setattr__(self, "telefone", phone)
