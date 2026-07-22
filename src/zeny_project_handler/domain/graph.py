"""Projeções imutáveis das visões física e elétrica de um projeto confirmado."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from zeny_project_handler.domain.enums import (
    SeveridadeDiagnosticoGrafo,
    TipoNoGrafo,
    VisaoGrafo,
)
from zeny_project_handler.domain.errors import DomainValidationError
from zeny_project_handler.domain.values import GeometriaDocumento, decimal_value, required_text

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, kw_only=True)
class NoGrafo:
    id: UUID
    referencia_id: UUID
    tipo: TipoNoGrafo
    rotulo: str
    geometria: GeometriaDocumento | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "rotulo", required_text(self.rotulo, field_name="rotulo"))


@dataclass(frozen=True, slots=True, kw_only=True)
class ArestaGrafo:
    id: UUID
    origem_id: UUID
    destino_id: UUID
    tipo: str
    referencia_id: UUID
    direcionada: bool = False
    proposta: bool = False

    def __post_init__(self) -> None:
        if self.origem_id == self.destino_id:
            raise DomainValidationError("Aresta do grafo deve ligar nós distintos")
        object.__setattr__(self, "tipo", required_text(self.tipo, field_name="tipo"))


@dataclass(frozen=True, slots=True, kw_only=True)
class GrafoDerivado:
    visao: VisaoGrafo
    nos: tuple[NoGrafo, ...]
    arestas: tuple[ArestaGrafo, ...]

    def __post_init__(self) -> None:
        nodes = tuple(self.nos)
        edges = tuple(self.arestas)
        node_ids = {node.id for node in nodes}
        if len(node_ids) != len(nodes) or len({edge.id for edge in edges}) != len(edges):
            raise DomainValidationError("Nós e arestas do grafo devem possuir IDs únicos")
        if any(edge.origem_id not in node_ids or edge.destino_id not in node_ids for edge in edges):
            raise DomainValidationError("Aresta do grafo deve referenciar nós existentes")
        object.__setattr__(self, "nos", nodes)
        object.__setattr__(self, "arestas", edges)


@dataclass(frozen=True, slots=True, kw_only=True)
class SugestaoConexaoGrafo:
    id: UUID
    origem_id: UUID
    destino_id: UUID
    confianca: Decimal
    justificativa: str

    def __post_init__(self) -> None:
        if self.origem_id == self.destino_id:
            raise DomainValidationError("Sugestão de conexão deve ligar referências distintas")
        confidence = decimal_value(self.confianca, field_name="confianca")
        if not Decimal(0) <= confidence <= Decimal(1):
            raise DomainValidationError("Confiança da conexão deve estar entre 0 e 1")
        object.__setattr__(self, "confianca", confidence)
        object.__setattr__(
            self,
            "justificativa",
            required_text(self.justificativa, field_name="justificativa"),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DiagnosticoGrafo:
    id: UUID
    codigo: str
    severidade: SeveridadeDiagnosticoGrafo
    mensagem: str
    visao: VisaoGrafo
    referencias_ids: tuple[UUID, ...] = ()
    sugestao_id: UUID | None = None

    def __post_init__(self) -> None:
        references = tuple(self.referencias_ids)
        if len(set(references)) != len(references):
            raise DomainValidationError("Diagnóstico não pode repetir referências")
        object.__setattr__(self, "codigo", required_text(self.codigo, field_name="codigo"))
        object.__setattr__(self, "mensagem", required_text(self.mensagem, field_name="mensagem"))
        object.__setattr__(self, "referencias_ids", references)


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoReconstrucaoGrafo:
    projeto_id: UUID
    versao_metodo: str
    assinatura: str
    fisico: GrafoDerivado
    eletrico: GrafoDerivado
    diagnosticos: tuple[DiagnosticoGrafo, ...] = ()
    sugestoes: tuple[SugestaoConexaoGrafo, ...] = ()

    def __post_init__(self) -> None:
        signature = self.assinatura.strip().lower()
        if not _SHA256_PATTERN.fullmatch(signature):
            raise DomainValidationError("Assinatura do grafo deve ser um SHA-256 hexadecimal")
        if self.fisico.visao is not VisaoGrafo.FISICA:
            raise DomainValidationError("Projeção física usa a visão incorreta")
        if self.eletrico.visao is not VisaoGrafo.ELETRICA:
            raise DomainValidationError("Projeção elétrica usa a visão incorreta")
        diagnostics = tuple(self.diagnosticos)
        suggestions = tuple(self.sugestoes)
        if len({item.id for item in diagnostics}) != len(diagnostics):
            raise DomainValidationError("Diagnósticos do grafo devem possuir IDs únicos")
        if len({item.id for item in suggestions}) != len(suggestions):
            raise DomainValidationError("Sugestões do grafo devem possuir IDs únicos")
        object.__setattr__(
            self,
            "versao_metodo",
            required_text(self.versao_metodo, field_name="versao_metodo"),
        )
        object.__setattr__(self, "assinatura", signature)
        object.__setattr__(self, "diagnosticos", diagnostics)
        object.__setattr__(self, "sugestoes", suggestions)
