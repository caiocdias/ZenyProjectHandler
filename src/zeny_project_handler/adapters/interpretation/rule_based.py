"""Orquestrador determinístico dos analisadores e relações explícitas."""

from __future__ import annotations

from collections.abc import Callable

from zeny_project_handler.domain.analysis import DiagnosticoAnalise, PropostaElemento
from zeny_project_handler.domain.interpretation import RegistroRegrasInterpretacao
from zeny_project_handler.ports.interpretation import (
    AnalisadorCategoriaPort,
    InterpretacaoCanceladaError,
    ResultadoInterpretacao,
    SolicitacaoInterpretacao,
)

from .category_analyzers import (
    AnalisadorCabo,
    AnalisadorEquipamento,
    AnalisadorEstruturaBt,
    AnalisadorEstruturaMt,
    AnalisadorPoste,
)
from .relation_rules import generate_relations, mark_conflicts


class InterpretadorRegrasExplicitas:
    nome = "regras-explicitas-cemig"
    versao = "2.0"

    def __init__(
        self,
        registro: RegistroRegrasInterpretacao,
        analisadores: tuple[AnalisadorCategoriaPort, ...] | None = None,
    ) -> None:
        self.registro = registro
        self._analyzers = analisadores or (
            AnalisadorPoste(),
            AnalisadorEstruturaMt(),
            AnalisadorEstruturaBt(),
            AnalisadorCabo(),
            AnalisadorEquipamento(),
        )

    def interpretar(
        self,
        solicitacao: SolicitacaoInterpretacao,
        *,
        cancelado: Callable[[], bool] | None = None,
    ) -> ResultadoInterpretacao:
        if solicitacao.registro.assinatura() != self.registro.assinatura():
            raise ValueError("Solicitação usa um registro diferente do interpretador")
        cancellation = cancelado or (lambda: False)
        proposals: list[PropostaElemento] = []
        diagnostics: list[DiagnosticoAnalise] = []
        for analyzer in self._analyzers:
            _raise_if_cancelled(cancellation)
            if analyzer.categoria not in solicitacao.configuracao.categorias_habilitadas:
                continue
            try:
                rule = self.registro.regra_da_categoria(analyzer.categoria)
                proposals.extend(analyzer.analisar(solicitacao, rule))
            except Exception as error:
                diagnostics.append(_analyzer_diagnostic(analyzer.nome, error))
            if len(proposals) > solicitacao.configuracao.maximo_propostas:
                raise ValueError("Quantidade de propostas excedeu o limite configurado")
        elements = mark_conflicts(tuple(proposals), solicitacao.evidencias)
        relations = (
            generate_relations(
                solicitacao.execucao_id,
                elements,
                self.registro,
                solicitacao.catalogo,
            )
            if solicitacao.configuracao.gerar_relacoes
            else ()
        )
        _raise_if_cancelled(cancellation)
        return ResultadoInterpretacao(
            elementos=tuple(sorted(elements, key=lambda item: str(item.id))),
            relacoes=tuple(sorted(relations, key=lambda item: str(item.id))),
            diagnosticos=tuple(diagnostics),
        )


def _raise_if_cancelled(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise InterpretacaoCanceladaError("Interpretação cancelada")


def _analyzer_diagnostic(name: str, error: Exception) -> DiagnosticoAnalise:
    return DiagnosticoAnalise(
        codigo="interpretacao.analisador_falhou",
        mensagem=str(error).strip() or error.__class__.__name__,
        extrator=name,
    )


__all__ = [
    "AnalisadorCabo",
    "AnalisadorEquipamento",
    "AnalisadorEstruturaBt",
    "AnalisadorEstruturaMt",
    "AnalisadorPoste",
    "InterpretadorRegrasExplicitas",
]
