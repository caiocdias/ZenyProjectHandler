"""Fatos, regras e achados auditáveis de conformidade de projeto."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento, decimal_value, required_text

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_RULE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class TipoEscopoConformidade(StrEnum):
    PROJETO = "PROJETO"
    DOCUMENTO = "DOCUMENTO"
    PAGINA = "PAGINA"
    REGIAO = "REGIAO"
    ELEMENTO = "ELEMENTO"


class SeveridadeConformidade(StrEnum):
    INFORMATIVA = "INFORMATIVA"
    ALERTA = "ALERTA"
    ERRO = "ERRO"
    CRITICA = "CRITICA"


class OperadorCondicao(StrEnum):
    EXISTE = "EXISTE"
    AUSENTE = "AUSENTE"
    IGUAL = "IGUAL"
    DIFERENTE = "DIFERENTE"
    MENOR = "MENOR"
    MENOR_OU_IGUAL = "MENOR_OU_IGUAL"
    MAIOR = "MAIOR"
    MAIOR_OU_IGUAL = "MAIOR_OU_IGUAL"
    EM = "EM"
    NAO_EM = "NAO_EM"
    CONTEM = "CONTEM"


class QuantificadorCondicao(StrEnum):
    TODOS = "TODOS"
    QUALQUER = "QUALQUER"


class ResultadoConformidade(StrEnum):
    CONFORME = "CONFORME"
    DIVERGENCIA = "DIVERGENCIA"
    NAO_AVALIAVEL = "NAO_AVALIAVEL"


class TipoValorFato(StrEnum):
    TEXTO = "TEXTO"
    NUMERO = "NUMERO"
    INTEIRO = "INTEIRO"
    BOOLEANO = "BOOLEANO"


class DisponibilidadeProvedorFato(StrEnum):
    DISPONIVEL = "DISPONIVEL"
    PLANEJADO = "PLANEJADO"


@dataclass(frozen=True, slots=True, kw_only=True)
class DefinicaoFatoConformidade:
    chave: str
    escopos: frozenset[TipoEscopoConformidade]
    tipo_valor: TipoValorFato
    operadores: frozenset[OperadorCondicao]
    descricao: str
    disponibilidade: DisponibilidadeProvedorFato

    def __post_init__(self) -> None:
        if not self.escopos:
            raise DomainValidationError("Fato deve declarar ao menos um escopo")
        if not self.operadores:
            raise DomainValidationError("Fato deve declarar ao menos um operador")
        object.__setattr__(self, "chave", _fact_key(self.chave))
        object.__setattr__(
            self,
            "descricao",
            required_text(self.descricao, field_name="descrição do fato"),
        )


def _rule_identifier(value: str) -> str:
    normalized = required_text(value, field_name="id da regra").lower()
    if not _RULE_ID_PATTERN.fullmatch(normalized):
        raise DomainValidationError("ID da regra de conformidade é inválido")
    return normalized


def _fact_key(value: str) -> str:
    normalized = required_text(value, field_name="chave do fato").lower()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise DomainValidationError("Chave de fato deve usar segmentos separados por ponto")
    return normalized


@dataclass(frozen=True, slots=True, kw_only=True)
class FonteNormativa:
    documento: str
    revisao: str
    item: str
    pagina: int | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        if self.pagina is not None and self.pagina < 1:
            raise DomainValidationError("Página da fonte normativa deve ser positiva")
        object.__setattr__(
            self, "documento", required_text(self.documento, field_name="documento normativo")
        )
        object.__setattr__(self, "revisao", required_text(self.revisao, field_name="revisão"))
        object.__setattr__(self, "item", required_text(self.item, field_name="item normativo"))
        object.__setattr__(self, "url", self.url.strip() if self.url else None)


@dataclass(frozen=True, slots=True, kw_only=True)
class AlvoConformidade:
    id: UUID
    tipo: TipoEscopoConformidade
    rotulo: str
    referencia_id: UUID | None = None
    pagina_id: UUID | None = None
    geometria: GeometriaDocumento | None = None

    def __post_init__(self) -> None:
        if self.geometria is not None and self.geometria.pagina_id != self.pagina_id:
            raise DomainValidationError("Geometria do alvo deve pertencer à página informada")
        object.__setattr__(self, "rotulo", required_text(self.rotulo, field_name="rótulo do alvo"))


@dataclass(frozen=True, slots=True, kw_only=True)
class FatoConformidade:
    id: UUID
    alvo_id: UUID
    chave: str
    valor: JsonPrimitive
    origem: str
    evidencia_ids: tuple[UUID, ...] = ()
    confianca: Decimal | None = None
    geometria: GeometriaDocumento | None = None

    def __post_init__(self) -> None:
        evidence_ids = tuple(self.evidencia_ids)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise DomainValidationError("Fato não pode repetir evidências")
        confidence = self.confianca
        if confidence is not None:
            confidence = decimal_value(confidence, field_name="confiança do fato")
            if not Decimal(0) <= confidence <= Decimal(1):
                raise DomainValidationError("Confiança do fato deve ficar entre zero e um")
        object.__setattr__(self, "chave", _fact_key(self.chave))
        object.__setattr__(self, "origem", required_text(self.origem, field_name="origem do fato"))
        object.__setattr__(self, "evidencia_ids", evidence_ids)
        object.__setattr__(self, "confianca", confidence)


@dataclass(frozen=True, slots=True, kw_only=True)
class CondicaoConformidade:
    chave_fato: str
    operador: OperadorCondicao
    valores_esperados: tuple[JsonPrimitive, ...] = ()
    quantificador: QuantificadorCondicao = QuantificadorCondicao.TODOS

    def __post_init__(self) -> None:
        expected = tuple(self.valores_esperados)
        if self.operador in {OperadorCondicao.EXISTE, OperadorCondicao.AUSENTE}:
            if expected:
                raise DomainValidationError("Condição de presença não aceita valor esperado")
        elif not expected:
            raise DomainValidationError("Condição comparativa exige ao menos um valor esperado")
        elif (
            self.operador not in {OperadorCondicao.EM, OperadorCondicao.NAO_EM}
            and len(expected) != 1
        ):
            raise DomainValidationError("Este operador aceita exatamente um valor esperado")
        object.__setattr__(self, "chave_fato", _fact_key(self.chave_fato))
        object.__setattr__(self, "valores_esperados", expected)


@dataclass(frozen=True, slots=True, kw_only=True)
class RegraConformidade:
    id: str
    titulo: str
    descricao: str
    escopo: TipoEscopoConformidade
    severidade: SeveridadeConformidade
    fonte: FonteNormativa
    requisitos: tuple[CondicaoConformidade, ...]
    aplicabilidade: tuple[CondicaoConformidade, ...] = ()
    excecoes: tuple[CondicaoConformidade, ...] = ()
    ativa: bool = True

    def __post_init__(self) -> None:
        requirements = tuple(self.requisitos)
        if not requirements:
            raise DomainValidationError("Regra deve possuir ao menos um requisito")
        object.__setattr__(self, "id", _rule_identifier(self.id))
        object.__setattr__(self, "titulo", required_text(self.titulo, field_name="título da regra"))
        object.__setattr__(
            self, "descricao", required_text(self.descricao, field_name="descrição da regra")
        )
        object.__setattr__(self, "requisitos", requirements)
        object.__setattr__(self, "aplicabilidade", tuple(self.aplicabilidade))
        object.__setattr__(self, "excecoes", tuple(self.excecoes))


@dataclass(frozen=True, slots=True, kw_only=True)
class RegistroRegrasConformidade:
    id: UUID
    versao: str
    versao_schema: int
    regras: tuple[RegraConformidade, ...]

    def __post_init__(self) -> None:
        rules = tuple(self.regras)
        if self.versao_schema != 1:
            raise DomainValidationError("Versão do registro de conformidade não suportada")
        if not rules or len({rule.id for rule in rules}) != len(rules):
            raise DomainValidationError("Registro deve possuir regras com IDs únicos")
        object.__setattr__(self, "versao", required_text(self.versao, field_name="versão"))
        object.__setattr__(self, "regras", rules)

    def assinatura(self) -> str:
        return sha256(self.json_canonico().encode("utf-8")).hexdigest()

    def para_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.versao_schema,
            "registry": {"id": str(self.id), "version": self.versao},
            "rules": [
                {
                    "id": rule.id,
                    "title": rule.titulo,
                    "description": rule.descricao,
                    "scope": rule.escopo.value,
                    "severity": rule.severidade.value,
                    "enabled": rule.ativa,
                    "source": {
                        "document": rule.fonte.documento,
                        "revision": rule.fonte.revisao,
                        "item": rule.fonte.item,
                        "page": rule.fonte.pagina,
                        "url": rule.fonte.url,
                    },
                    "when": [_condition_payload(item) for item in rule.aplicabilidade],
                    "unless": [_condition_payload(item) for item in rule.excecoes],
                    "must": [_condition_payload(item) for item in rule.requisitos],
                }
                for rule in self.regras
            ],
        }

    def json_canonico(self) -> str:
        return json.dumps(
            self.para_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RevisaoRegistroConformidade:
    id: UUID
    registro: RegistroRegrasConformidade
    assinatura: str
    json_canonico: str
    criada_em: datetime
    ativa: bool

    def __post_init__(self) -> None:
        if self.assinatura != self.registro.assinatura():
            raise DomainValidationError("Assinatura da revisão de regras é inválida")
        if self.json_canonico != self.registro.json_canonico():
            raise DomainValidationError("JSON canônico da revisão de regras é inválido")
        if self.criada_em.tzinfo is None or self.criada_em.utcoffset() is None:
            raise DomainValidationError("Data da revisão de regras deve possuir fuso horário")


@dataclass(frozen=True, slots=True, kw_only=True)
class NumeroRegraConformidade:
    regra_id: str
    numero: int
    atribuido_em: datetime

    def __post_init__(self) -> None:
        if self.numero < 1:
            raise DomainValidationError("Número da regra deve ser positivo")
        if self.atribuido_em.tzinfo is None or self.atribuido_em.utcoffset() is None:
            raise DomainValidationError("Data de atribuição da regra deve possuir fuso horário")
        object.__setattr__(self, "regra_id", _rule_identifier(self.regra_id))


@dataclass(frozen=True, slots=True, kw_only=True)
class AchadoConformidade:
    id: UUID
    regra_id: str
    alvo_id: UUID
    resultado: ResultadoConformidade
    severidade: SeveridadeConformidade
    titulo: str
    mensagem: str
    fonte: FonteNormativa
    versao_regras: str
    evidencia_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        evidence_ids = tuple(self.evidencia_ids)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise DomainValidationError("Achado não pode repetir evidências")
        object.__setattr__(self, "regra_id", _rule_identifier(self.regra_id))
        object.__setattr__(self, "titulo", required_text(self.titulo, field_name="título"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))
        object.__setattr__(
            self, "versao_regras", required_text(self.versao_regras, field_name="versão das regras")
        )
        object.__setattr__(self, "evidencia_ids", evidence_ids)


def _condition_payload(condition: CondicaoConformidade) -> dict[str, object]:
    return {
        "fact": condition.chave_fato,
        "operator": condition.operador.value,
        "expected": [_json_primitive_payload(value) for value in condition.valores_esperados],
        "quantifier": condition.quantificador.value,
    }


def _json_primitive_payload(value: JsonPrimitive) -> JsonPrimitive | float:
    return float(value) if isinstance(value, Decimal) else value
