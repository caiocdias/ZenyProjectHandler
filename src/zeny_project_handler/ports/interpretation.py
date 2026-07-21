"""Contratos neutros do pipeline semântico versionado."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Protocol
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DiagnosticoAnalise,
    EvidenciaDocumento,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.catalog import CatalogoTecnico, ExtraAttributes
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.interpretation import (
    RegistroRegrasInterpretacao,
    RegraReconhecimento,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ConfiguracaoInterpretacao:
    categorias_habilitadas: tuple[CategoriaElemento, ...] = tuple(CategoriaElemento)
    confianca_minima: Decimal = Decimal("0.50")
    gerar_relacoes: bool = True
    maximo_propostas: int = 10000

    def __post_init__(self) -> None:
        categories = tuple(self.categorias_habilitadas)
        if not categories or len(set(categories)) != len(categories):
            raise ValueError("Categorias habilitadas devem ser únicas e não vazias")
        confidence = Decimal(self.confianca_minima)
        if not Decimal(0) <= confidence <= Decimal(1):
            raise ValueError("Confiança mínima deve estar entre 0 e 1")
        if self.maximo_propostas < 1:
            raise ValueError("Máximo de propostas deve ser positivo")
        object.__setattr__(self, "categorias_habilitadas", categories)
        object.__setattr__(self, "confianca_minima", confidence)

    def parametros(self) -> ExtraAttributes:
        return (
            (
                "categorias_habilitadas",
                ",".join(item.value for item in self.categorias_habilitadas),
            ),
            ("confianca_minima", self.confianca_minima),
            ("gerar_relacoes", self.gerar_relacoes),
            ("maximo_propostas", self.maximo_propostas),
        )

    def assinatura(self) -> str:
        payload = json.dumps(
            {
                key: str(value) if isinstance(value, Decimal) else value
                for key, value in self.parametros()
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class SolicitacaoInterpretacao:
    projeto_id: UUID
    execucao_id: UUID
    execucao_extracao_id: UUID
    catalogo: CatalogoTecnico
    evidencias: tuple[EvidenciaDocumento, ...]
    registro: RegistroRegrasInterpretacao
    configuracao: ConfiguracaoInterpretacao = ConfiguracaoInterpretacao()


@dataclass(frozen=True, slots=True, kw_only=True)
class ResultadoInterpretacao:
    elementos: tuple[PropostaElemento, ...]
    relacoes: tuple[PropostaRelacao, ...] = ()
    diagnosticos: tuple[DiagnosticoAnalise, ...] = ()


class InterpretacaoCanceladaError(RuntimeError):
    """O chamador solicitou cancelamento em um ponto seguro do pipeline."""


class AnalisadorCategoriaPort(Protocol):
    nome: str
    versao: str
    categoria: CategoriaElemento

    def analisar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        regra: RegraReconhecimento,
    ) -> tuple[PropostaElemento, ...]: ...


class InterpretadorEvidenciasPort(Protocol):
    nome: str
    versao: str

    def interpretar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        *,
        cancelado: Callable[[], bool] | None = None,
    ) -> ResultadoInterpretacao: ...


class RepositorioRegrasInterpretacaoPort(Protocol):
    def carregar(self) -> RegistroRegrasInterpretacao: ...
