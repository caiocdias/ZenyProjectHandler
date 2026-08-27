"""Contrato mínimo para famílias determinísticas de fatos de conformidade."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid5

from zeny_project_handler.domain.analysis import EvidenciaDocumento
from zeny_project_handler.domain.catalog import JsonPrimitive
from zeny_project_handler.domain.compliance import AlvoConformidade, FatoConformidade
from zeny_project_handler.domain.market import Mercado
from zeny_project_handler.domain.values import GeometriaDocumento

from .human_review import SessaoRevisao


@dataclass(frozen=True, slots=True)
class ContextoProvedorFatos:
    """Entrada imutável compartilhada por todos os provedores compostos."""

    sessao: SessaoRevisao
    alvos: tuple[AlvoConformidade, ...]
    mercado: Mercado


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
