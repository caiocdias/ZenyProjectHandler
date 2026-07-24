"""Projeção dos vãos físicos reconhecidos entre postes do projeto."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid5

from zeny_project_handler.domain.enums import OrigemComprimentoVao, SituacaoProjeto
from zeny_project_handler.domain.project import Cabo, Poste, Projeto
from zeny_project_handler.domain.values import GeometriaDocumento


@dataclass(frozen=True, slots=True, kw_only=True)
class VaoDetectado:
    """Trecho de um cabo cujas duas extremidades pertencem a postes distintos."""

    id: UUID
    cabo_id: UUID
    poste_origem_id: UUID
    poste_destino_id: UUID
    situacao: SituacaoProjeto
    geometria: GeometriaDocumento | None
    comprimento_m: Decimal | None = None
    origem_comprimento: OrigemComprimentoVao | None = None

    def __post_init__(self) -> None:
        if self.poste_origem_id == self.poste_destino_id:
            raise ValueError("Vão deve ligar dois postes distintos")
        if self.comprimento_m is None and self.origem_comprimento is not None:
            raise ValueError("Origem do comprimento requer um comprimento identificado")
        if self.comprimento_m is not None and self.comprimento_m <= 0:
            raise ValueError("Comprimento do vão deve ser positivo")


def detectar_vaos(projeto: Projeto) -> tuple[VaoDetectado, ...]:
    """Derive vãos dos cabos confirmados e dos pontos de rede de suas extremidades."""
    postes = {
        elemento.id: elemento for elemento in projeto.elementos if isinstance(elemento, Poste)
    }
    pontos = {ponto.id: ponto for ponto in projeto.pontos_rede}
    vaos: list[VaoDetectado] = []
    for cabo in projeto.elementos:
        if not isinstance(cabo, Cabo):
            continue
        origem = pontos.get(cabo.ponto_origem_id)
        destino = pontos.get(cabo.ponto_destino_id)
        if (
            origem is None
            or destino is None
            or origem.poste_id not in postes
            or destino.poste_id not in postes
            or origem.poste_id == destino.poste_id
        ):
            continue
        comprimento, fonte = _comprimento(cabo, postes[origem.poste_id], postes[destino.poste_id])
        vaos.append(
            VaoDetectado(
                id=uuid5(cabo.id, "vao-detectado"),
                cabo_id=cabo.id,
                poste_origem_id=origem.poste_id,
                poste_destino_id=destino.poste_id,
                situacao=cabo.situacao,
                geometria=cabo.geometria,
                comprimento_m=comprimento,
                origem_comprimento=fonte,
            )
        )
    page_order = {page_id: index for index, page_id in enumerate(projeto.ordem_leitura_paginas)}
    return tuple(
        sorted(
            vaos,
            key=lambda vao: (
                (
                    page_order.get(vao.geometria.pagina_id, len(page_order))
                    if vao.geometria is not None
                    else len(page_order)
                ),
                str(vao.id),
            ),
        )
    )


def _comprimento(
    cabo: Cabo,
    poste_origem: Poste,
    poste_destino: Poste,
) -> tuple[Decimal | None, OrigemComprimentoVao | None]:
    if cabo.comprimento_m is not None:
        return (
            cabo.comprimento_m,
            cabo.origem_comprimento or OrigemComprimentoVao.INFORMADO,
        )
    origem = poste_origem.coordenada_campo
    destino = poste_destino.coordenada_campo
    if origem is None or destino is None:
        return None, None
    delta_leste = destino.leste - origem.leste
    delta_norte = destino.norte - origem.norte
    comprimento = (delta_leste * delta_leste + delta_norte * delta_norte).sqrt()
    if comprimento <= 0:
        return None, None
    return comprimento.quantize(Decimal("0.01")), OrigemComprimentoVao.COORDENADAS
