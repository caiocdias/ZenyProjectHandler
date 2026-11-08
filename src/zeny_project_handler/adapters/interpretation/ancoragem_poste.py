"""Ancoragem do poste no disco do desenho (identidade até a ancoragem real)."""

from __future__ import annotations

from zeny_project_handler.domain.analysis import EvidenciaDocumento, PropostaElemento


def ancorar_postes_no_desenho(
    propostas: tuple[PropostaElemento, ...],
    evidencias: tuple[EvidenciaDocumento, ...],
) -> tuple[PropostaElemento, ...]:
    del evidencias
    return propostas


__all__ = ["ancorar_postes_no_desenho"]
