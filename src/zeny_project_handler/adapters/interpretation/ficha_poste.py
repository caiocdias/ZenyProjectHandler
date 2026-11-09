"""Interpretador 27.0: o poste sai no disco do desenho (opção de símbolos ligada)."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Final
from uuid import UUID

from zeny_project_handler.domain.analysis import (
    DiagnosticoAnalise,
    PropostaElemento,
    PropostaRelacao,
)
from zeny_project_handler.domain.enums import CategoriaElemento
from zeny_project_handler.domain.values import GeometriaDocumento, PontoNormalizado
from zeny_project_handler.ports.interpretation import SolicitacaoInterpretacao

from .ancoragem_poste import ancorar_postes_no_desenho
from .relation_rules import generate_relations
from .rule_based import InterpretadorRegrasExplicitas, _analyzer_diagnostic

# O raio destas regras foi calibrado em texto contra texto: o poste entra na posição do texto.
_REGIME_DE_TEXTO: Final = "CENTROS_PROXIMOS"


class InterpretadorFichaPoste(InterpretadorRegrasExplicitas):
    versao = "27.0"

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

    def _gerar_relacoes(
        self,
        execucao_id: UUID,
        elementos: tuple[PropostaElemento, ...],
        solicitacao: SolicitacaoInterpretacao,
    ) -> tuple[PropostaRelacao, ...]:
        """Estruturas e equipamentos se ligam ao poste no texto; os demais, ao poste no disco."""
        com_poste_no_texto = tuple(_com_poste_no_texto(item) for item in elementos)
        relacoes: dict[UUID, PropostaRelacao] = {}
        for regra in self.registro.regras_relacao:
            for relacao in generate_relations(
                execucao_id,
                com_poste_no_texto if regra.estrategia == _REGIME_DE_TEXTO else elementos,
                replace(self.registro, regras_relacao=(regra,)),
                solicitacao.catalogo,
            ):
                relacoes[relacao.id] = relacao
        return tuple(relacoes.values())


def _com_poste_no_texto(elemento: PropostaElemento) -> PropostaElemento:
    if elemento.categoria is not CategoriaElemento.POSTE:
        return elemento
    atributos = dict(elemento.atributos_sugeridos)
    # A disputa do disco não importa no texto; o pendente já está na posição do texto.
    # Isto vem antes do teste do centro: o pendente não tem `poste_texto_centro`.
    if atributos.get("associacao_pendente") == "poste_disco":
        del atributos["associacao_pendente"]
        elemento = replace(elemento, atributos_sugeridos=tuple(atributos.items()))
    centro = atributos.get("poste_texto_centro")
    if not isinstance(centro, str):
        return elemento
    x, y = (Decimal(parte) for parte in centro.split(","))
    return replace(
        elemento,
        geometria=GeometriaDocumento.ponto(elemento.geometria.pagina_id, PontoNormalizado(x, y)),
    )


__all__ = ["InterpretadorFichaPoste"]
