"""Parcela de vizinhos da deduplicação do estai: `gastar(1 + len(vizinhos))` numa página densa."""

from __future__ import annotations

from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.estai import garfo, pagina_estai

from zeny_project_handler.adapters.analysis.drawing_model import grammar_estai
from zeny_project_handler.adapters.analysis.drawing_model.grammar_estai import estai_candidatos
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    contexto_gramaticas,
)

# Haste paralela deslocada 0,6: fora do "mesmo desenho" (0,5), mas dentro da vizinhança de células.
_DESLOCAMENTO: Final = 0.6
_POR_AGLOMERADO: Final = 2  # células vizinhas (0 e +1); com 3 o primeiro e o terceiro não se tocam
_ENTRE_AGLOMERADOS: Final = 40.0


def _aglomerados(quantidade: int) -> list[Caminho]:
    caminhos: list[Caminho] = []
    for k in range(quantidade):
        for i in range(_POR_AGLOMERADO):
            base = (100.0, 20.0 + k * _ENTRE_AGLOMERADOS + i * _DESLOCAMENTO)
            caminhos.extend(garfo(0.0, base=base))
    return caminhos


def _gasto_da_deduplicacao(
    quantidade: int, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, int, int]:
    pagina = pagina_estai(_aglomerados(quantidade), altura=quantidade * _ENTRE_AGLOMERADOS + 40.0)
    contexto = contexto_gramaticas(pagina, limite=10**9)
    medido = {"gasto": 0, "lidos": 0}
    original = grammar_estai._deduplicar

    def com_medida(lidos: Any, orcamento: Any) -> Any:
        antes = contexto.orcamento.gasto
        medido["lidos"] = len(lidos)
        try:
            return original(lidos, orcamento)
        finally:
            medido["gasto"] = contexto.orcamento.gasto - antes

    monkeypatch.setattr(grammar_estai, "_deduplicar", com_medida)
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    return medido["gasto"], medido["lidos"], len(candidatos)


def test_deduplicacao_paga_um_mais_cada_vizinho_ja_escolhido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gasto, lidos, candidatos = _gasto_da_deduplicacao(1, monkeypatch)

    assert (lidos, candidatos) == (2, 2)
    # O primeiro garfo paga 1 + 0; o segundo, 1 + 1 (o primeiro é vizinho de célula).
    assert gasto == 3


def test_deduplicacao_da_pagina_densa_soma_a_parcela_de_vizinhos_por_aglomerado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aglomerados = 10
    gasto, lidos, candidatos = _gasto_da_deduplicacao(aglomerados, monkeypatch)

    assert (lidos, candidatos) == (2 * aglomerados, 2 * aglomerados)
    # Cobrar só 1 por leitura daria 20; a parcela de vizinhos leva a 30.
    assert gasto == 3 * aglomerados
