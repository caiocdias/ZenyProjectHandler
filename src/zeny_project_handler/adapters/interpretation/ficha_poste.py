"""Interpretador 26.0: o poste sai no disco do desenho (opção de símbolos ligada)."""

from __future__ import annotations

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, PropostaElemento
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao

from .ancoragem_poste import ancorar_postes_no_desenho
from .rule_based import InterpretadorRegrasExplicitas, _analyzer_diagnostic


class InterpretadorFichaPoste(InterpretadorRegrasExplicitas):
    versao = "26.0"

    def _refinar_propostas_identificadas(
        self,
        propostas: tuple[PropostaElemento, ...],
        solicitacao: SolicitacaoInterpretacao,
        diagnosticos: list[DiagnosticoAnalise],
    ) -> tuple[PropostaElemento, ...]:
        try:
            return ancorar_postes_no_desenho(propostas, solicitacao.evidencias)
        except Exception as error:
            diagnosticos.append(
                DiagnosticoAnalise(
                    codigo="interpretacao.ancoragem_poste_falhou",
                    mensagem=_analyzer_diagnostic("ancoragem-poste", error).mensagem,
                    extrator="ancoragem-poste",
                )
            )
            return propostas


__all__ = ["InterpretadorFichaPoste"]
