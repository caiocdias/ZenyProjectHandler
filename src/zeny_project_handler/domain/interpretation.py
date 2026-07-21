"""Registro versionado das regras explícitas de interpretação semântica."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from zeny_project_handler.domain.enums import CategoriaElemento, TipoEvidencia
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import decimal_value, required_text


def _identifier(value: str, *, field_name: str) -> str:
    normalized = required_text(value, field_name=field_name).strip().lower()
    if not all(part and part.replace("_", "").isalnum() for part in normalized.split("-")):
        raise DomainValidationError(
            f"{field_name} deve usar letras, números, hífens ou sublinhados"
        )
    return normalized


def _confidence(value: Decimal | int | str, *, field_name: str) -> Decimal:
    result = decimal_value(value, field_name=field_name)
    if not Decimal(0) <= result <= Decimal(1):
        raise DomainValidationError(f"{field_name} deve estar entre 0 e 1")
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class RegraReconhecimento:
    id: str
    categoria: CategoriaElemento
    tipos_evidencia: tuple[TipoEvidencia, ...]
    estrategia: str
    confianca_base: Decimal
    distancia_contexto_maxima: Decimal
    ativa: bool = True

    def __post_init__(self) -> None:
        evidence_types = tuple(self.tipos_evidencia)
        if not evidence_types or len(set(evidence_types)) != len(evidence_types):
            raise DomainValidationError("Regra deve possuir tipos de evidência únicos")
        distance = decimal_value(
            self.distancia_contexto_maxima,
            field_name="distancia_contexto_maxima",
        )
        if not Decimal(0) <= distance <= Decimal(1):
            raise DomainValidationError("Distância de contexto deve estar entre 0 e 1")
        object.__setattr__(self, "id", _identifier(self.id, field_name="id da regra"))
        object.__setattr__(self, "tipos_evidencia", evidence_types)
        object.__setattr__(
            self,
            "estrategia",
            required_text(self.estrategia, field_name="estrategia").upper(),
        )
        object.__setattr__(
            self,
            "confianca_base",
            _confidence(self.confianca_base, field_name="confianca_base"),
        )
        object.__setattr__(self, "distancia_contexto_maxima", distance)


@dataclass(frozen=True, slots=True, kw_only=True)
class RegraRelacaoInterpretacao:
    id: str
    categoria_origem: CategoriaElemento
    categoria_destino: CategoriaElemento
    tipo_relacao: str
    estrategia: str
    distancia_maxima: Decimal
    confianca: Decimal
    ativa: bool = True

    def __post_init__(self) -> None:
        distance = decimal_value(self.distancia_maxima, field_name="distancia_maxima")
        if not Decimal(0) < distance <= Decimal(1):
            raise DomainValidationError("Distância de relação deve estar entre 0 (exclusivo) e 1")
        object.__setattr__(self, "id", _identifier(self.id, field_name="id da regra de relação"))
        object.__setattr__(
            self,
            "tipo_relacao",
            required_text(self.tipo_relacao, field_name="tipo_relacao").upper(),
        )
        object.__setattr__(
            self,
            "estrategia",
            required_text(self.estrategia, field_name="estrategia").upper(),
        )
        object.__setattr__(self, "distancia_maxima", distance)
        object.__setattr__(
            self,
            "confianca",
            _confidence(self.confianca, field_name="confianca"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroRegrasInterpretacao:
    id: UUID
    versao: str
    versao_schema: int
    regras_reconhecimento: tuple[RegraReconhecimento, ...]
    regras_relacao: tuple[RegraRelacaoInterpretacao, ...]

    def __post_init__(self) -> None:
        recognition = tuple(self.regras_reconhecimento)
        relations = tuple(self.regras_relacao)
        if self.versao_schema != 1:
            raise DomainValidationError("Versão de schema do registro de regras não suportada")
        if not recognition:
            raise DomainValidationError("Registro deve possuir regras de reconhecimento")
        identifiers = [item.id for item in recognition] + [item.id for item in relations]
        if len(set(identifiers)) != len(identifiers):
            raise DomainValidationError("IDs das regras devem ser únicos no registro")
        active_categories = {item.categoria for item in recognition if item.ativa}
        if active_categories != set(CategoriaElemento):
            raise DomainValidationError("Registro deve cobrir todas as categorias de elemento")
        object.__setattr__(self, "versao", required_text(self.versao, field_name="versao"))
        object.__setattr__(self, "regras_reconhecimento", recognition)
        object.__setattr__(self, "regras_relacao", relations)

    def assinatura(self) -> str:
        payload = {
            "id": str(self.id),
            "version": self.versao,
            "schema": self.versao_schema,
            "recognition": [
                {
                    "id": item.id,
                    "category": item.categoria.value,
                    "evidence": [kind.value for kind in item.tipos_evidencia],
                    "strategy": item.estrategia,
                    "confidence": str(item.confianca_base),
                    "context": str(item.distancia_contexto_maxima),
                    "enabled": item.ativa,
                }
                for item in self.regras_reconhecimento
            ],
            "relations": [
                {
                    "id": item.id,
                    "origin": item.categoria_origem.value,
                    "destination": item.categoria_destino.value,
                    "type": item.tipo_relacao,
                    "strategy": item.estrategia,
                    "distance": str(item.distancia_maxima),
                    "confidence": str(item.confianca),
                    "enabled": item.ativa,
                }
                for item in self.regras_relacao
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    def regra_da_categoria(self, categoria: CategoriaElemento) -> RegraReconhecimento:
        return next(
            item
            for item in self.regras_reconhecimento
            if item.ativa and item.categoria is categoria
        )
