"""Elementos, relações e ciclos de revisão da anotação humana."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from zeny_project_handler.domain.documents import SHA256_PATTERN
from zeny_project_handler.domain.enums import (
    CategoriaElemento,
    EstadoAnotacao,
    PapelAnotacao,
    SituacaoProjeto,
    TipoGeometria,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.evaluation_common import (
    evaluation_identifier,
    optional_evaluation_text,
)
from zeny_project_handler.domain.evaluation_dataset import ManifestoAvaliacao
from zeny_project_handler.domain.values import (
    PontoNormalizado,
    required_text,
    validar_geometria_normalizada,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class GeometriaAvaliacao:
    pagina_numero: int
    tipo: TipoGeometria
    pontos: tuple[PontoNormalizado, ...]

    def __post_init__(self) -> None:
        if self.pagina_numero <= 0:
            raise DomainValidationError("Página da anotação deve ser positiva")
        object.__setattr__(
            self, "pontos", validar_geometria_normalizada(self.tipo, tuple(self.pontos))
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RotuloElementoAvaliacao:
    id: str
    categoria: CategoriaElemento
    situacao: SituacaoProjeto
    geometria: GeometriaAvaliacao
    codigo_catalogo: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", evaluation_identifier(self.id, field_name="id do elemento"))
        object.__setattr__(self, "codigo_catalogo", optional_evaluation_text(self.codigo_catalogo))


@dataclass(frozen=True, slots=True, kw_only=True)
class RotuloRelacaoAvaliacao:
    id: str
    origem_id: str
    destino_id: str
    tipo_relacao: str
    direcionada: bool = True

    def __post_init__(self) -> None:
        origin = evaluation_identifier(self.origem_id, field_name="origem_id")
        destination = evaluation_identifier(self.destino_id, field_name="destino_id")
        if origin == destination:
            raise DomainValidationError("Relação deve conectar elementos distintos")
        object.__setattr__(self, "id", evaluation_identifier(self.id, field_name="id da relação"))
        object.__setattr__(self, "origem_id", origin)
        object.__setattr__(self, "destino_id", destination)
        object.__setattr__(
            self,
            "tipo_relacao",
            required_text(self.tipo_relacao, field_name="tipo_relacao").upper(),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class AnotacaoAmostra:
    schema_version: int
    id: str
    conjunto_id: str
    conjunto_versao: str
    amostra_id: str
    documento_sha256: str
    papel: PapelAnotacao
    estado: EstadoAnotacao
    anotador_id: str
    criada_em: datetime
    elementos: tuple[RotuloElementoAvaliacao, ...]
    relacoes: tuple[RotuloRelacaoAvaliacao, ...] = ()
    revisada_em: datetime | None = None
    revisor_id: str | None = None

    def __post_init__(self) -> None:
        digest = _validated_annotation_header(self)
        reviewer = _validated_review(self)
        elements, relations = _validated_labels(self.elementos, self.relacoes)
        object.__setattr__(self, "id", evaluation_identifier(self.id, field_name="id da anotação"))
        object.__setattr__(
            self, "conjunto_id", evaluation_identifier(self.conjunto_id, field_name="conjunto_id")
        )
        object.__setattr__(
            self, "conjunto_versao", required_text(self.conjunto_versao, field_name="versao")
        )
        object.__setattr__(
            self, "amostra_id", evaluation_identifier(self.amostra_id, field_name="amostra_id")
        )
        object.__setattr__(self, "documento_sha256", digest)
        object.__setattr__(
            self, "anotador_id", evaluation_identifier(self.anotador_id, field_name="anotador_id")
        )
        object.__setattr__(self, "revisor_id", reviewer)
        object.__setattr__(self, "elementos", tuple(sorted(elements, key=lambda item: item.id)))
        object.__setattr__(self, "relacoes", tuple(sorted(relations, key=lambda item: item.id)))


def _validated_annotation_header(annotation: AnotacaoAmostra) -> str:
    if annotation.schema_version != 1:
        raise DomainValidationError("Versão de schema da anotação não suportada")
    digest = annotation.documento_sha256.strip().lower()
    if not SHA256_PATTERN.fullmatch(digest):
        raise DomainValidationError("SHA-256 da anotação é inválido")
    if annotation.criada_em.tzinfo is None:
        raise DomainValidationError("Criação da anotação deve possuir fuso horário")
    if annotation.revisada_em is not None and annotation.revisada_em.tzinfo is None:
        raise DomainValidationError("Revisão da anotação deve possuir fuso horário")
    return digest


def _validated_review(annotation: AnotacaoAmostra) -> str | None:
    reviewed = annotation.estado in {EstadoAnotacao.REVISADA, EstadoAnotacao.CONGELADA}
    reviewer = optional_evaluation_text(annotation.revisor_id)
    if reviewed and (annotation.revisada_em is None or reviewer is None):
        raise DomainValidationError("Anotação revisada deve registrar revisor e data")
    if not reviewed and (annotation.revisada_em is not None or reviewer is not None):
        raise DomainValidationError("Rascunho não pode registrar revisão")
    if (
        annotation.estado is EstadoAnotacao.CONGELADA
        and annotation.papel is not PapelAnotacao.CONSENSO
    ):
        raise DomainValidationError("Somente anotação de consenso pode ser congelada")
    return reviewer


def _validated_labels(
    elements_value: tuple[RotuloElementoAvaliacao, ...],
    relations_value: tuple[RotuloRelacaoAvaliacao, ...],
) -> tuple[tuple[RotuloElementoAvaliacao, ...], tuple[RotuloRelacaoAvaliacao, ...]]:
    elements = tuple(elements_value)
    relations = tuple(relations_value)
    element_ids = {item.id for item in elements}
    if len(element_ids) != len(elements):
        raise DomainValidationError("IDs de elementos anotados devem ser únicos")
    if len({item.id for item in relations}) != len(relations):
        raise DomainValidationError("IDs de relações anotadas devem ser únicos")
    if any(
        item.origem_id not in element_ids or item.destino_id not in element_ids
        for item in relations
    ):
        raise DomainValidationError("Relação anotada referencia elemento inexistente")
    return elements, relations


def validar_anotacao_no_manifesto(anotacao: AnotacaoAmostra, manifesto: ManifestoAvaliacao) -> None:
    sample = manifesto.obter_amostra(anotacao.amostra_id)
    if anotacao.conjunto_id != manifesto.conjunto_id:
        raise DomainValidationError("Anotação pertence a outro conjunto")
    if anotacao.conjunto_versao != manifesto.versao:
        raise DomainValidationError("Anotação pertence a outra versão do conjunto")
    if anotacao.documento_sha256 != sample.sha256:
        raise DomainValidationError("Hash da anotação diverge da amostra")
    if any(item.geometria.pagina_numero > sample.total_paginas for item in anotacao.elementos):
        raise DomainValidationError("Anotação referencia página inexistente")
