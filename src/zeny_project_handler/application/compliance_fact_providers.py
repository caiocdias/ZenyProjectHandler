"""Contrato mínimo para famílias determinísticas de fatos de conformidade."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.compliance import AlvoConformidade, FatoConformidade
from zeny_project_handler.domain.market import DescricaoAcao, Mercado
from zeny_project_handler.domain.values import GeometriaDocumento

from .human_review import SessaoRevisao


class EstadoVerificacaoAcao(StrEnum):
    """Estado auditável de uma ação sem carregar detalhes da infraestrutura."""

    NAO_APLICAVEL = "NAO_APLICAVEL"
    SEM_CODIGOS_SERVICO = "SEM_CODIGOS_SERVICO"
    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"


@dataclass(frozen=True, slots=True)
class GatilhosAcoesProjeto:
    """Evidências positivas, ordenadas, que tornam cada consulta aplicável."""

    impacto_ambiental_sim: tuple[EvidenciaDocumento, ...] = ()
    servidao_mencionada: tuple[EvidenciaDocumento, ...] = ()

    def evidencias_para(self, acao: DescricaoAcao) -> tuple[EvidenciaDocumento, ...]:
        return {
            DescricaoAcao.AVALIAR_IMPACTO_AMBIENTAL: self.impacto_ambiental_sim,
            DescricaoAcao.FALTA_SERVIDAO: self.servidao_mencionada,
        }[acao]


@dataclass(frozen=True, slots=True)
class ResultadoVerificacaoAcao:
    """Resultado fechado que distingue consulta, pendência e falta de serviços."""

    acao: DescricaoAcao
    estado: EstadoVerificacaoAcao

    @property
    def concluida(self) -> bool:
        return self.estado is EstadoVerificacaoAcao.CONCLUIDA

    @property
    def consultada(self) -> bool:
        return self.estado in {
            EstadoVerificacaoAcao.PENDENTE,
            EstadoVerificacaoAcao.CONCLUIDA,
        }


@dataclass(frozen=True, slots=True)
class ContextoAcoesProjeto:
    """Entrada operacional completa e imutável entregue ao analisador de fatos."""

    codigos_servico: tuple[str, ...]
    gatilhos: GatilhosAcoesProjeto
    resultados: tuple[ResultadoVerificacaoAcao, ...]

    def __post_init__(self) -> None:
        if tuple(item.acao for item in self.resultados) != tuple(DescricaoAcao):
            raise ValueError("Resultados de ações devem seguir a ordem canônica completa")

    def resultado_para(self, acao: DescricaoAcao) -> ResultadoVerificacaoAcao:
        return next(item for item in self.resultados if item.acao is acao)


@dataclass(frozen=True, slots=True)
class ContextoProvedorFatos:
    """Entrada imutável compartilhada por todos os provedores compostos."""

    sessao: SessaoRevisao
    alvos: tuple[AlvoConformidade, ...]
    mercado: Mercado
    acoes_projeto: ContextoAcoesProjeto | None = None


class ProvedorFatosConformidade(Protocol):
    """Uma família recebe a sessão e publica apenas fatos comprovados."""

    def __call__(self, contexto: ContextoProvedorFatos) -> tuple[FatoConformidade, ...]: ...


def criar_fato_conformidade(
    alvo_id: UUID,
    chave: str,
    valor: JsonPrimitive,
    origem: str,
    *,
    evidencias: tuple[EvidenciaDocumento, ...] = (),
    confianca: Decimal | None = None,
    geometria: GeometriaDocumento | None = None,
) -> FatoConformidade:
    """Centralize identidade e proveniência sem conhecer a família produtora."""
    evidence_ids = tuple(dict.fromkeys(item.id for item in evidencias))
    identity = f"{chave}:{valor}:{origem}:{','.join(map(str, evidence_ids))}"
    return FatoConformidade(
        id=uuid5(alvo_id, identity),
        alvo_id=alvo_id,
        chave=chave,
        valor=valor,
        origem=origem,
        evidencia_ids=evidence_ids,
        confianca=confianca,
        geometria=geometria or (evidencias[0].geometria if evidencias else None),
    )
