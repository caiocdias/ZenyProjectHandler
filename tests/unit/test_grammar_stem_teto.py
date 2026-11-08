"""Teto de orçamento da gramática `stem_bars`: página hostil e gasto linear com as hastes."""

from __future__ import annotations

from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica
from tests.fixtures.symbol_grammars.stem_bars import CASOS_HASTE, DECRESCENTES

from zeny_project_handler.adapters.analysis.drawing_model.grammar_stem import casa_hastes
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

_GRAMATICA: Final = CASOS_HASTE[0][1]
_PASSO: Final = 40.0
_COLUNAS: Final = 50
_RAZAO_MAXIMA: Final = 15


def _haste_isolada(cx: float, cy: float) -> list[Caminho]:
    caminhos = [linha((cx, cy + 5.0), (cx, cy - 5.0))]
    for i, comprimento in enumerate(DECRESCENTES):
        y, meio = cy - 5.0 - i * 2.0, comprimento / 2
        caminhos.append(linha((cx - meio, y), (cx + meio, y)))
    return caminhos


def _pagina_com_hastes(quantidade: int) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        caminhos.extend(
            _haste_isolada(30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)
        )
    return pagina_gramatica(
        caminhos, largura=_COLUNAS * _PASSO + 60.0, altura=(quantidade // _COLUNAS + 2) * _PASSO
    )


def _gasto_e_casamentos(quantidade: int) -> tuple[int, int]:
    contexto = contexto_gramaticas(_pagina_com_hastes(quantidade), limite=10**9)
    casamentos = casa_hastes(contexto, _GRAMATICA)
    return contexto.orcamento.gasto, len(casamentos)


def test_pagina_hostil_estoura_o_orcamento() -> None:
    """20.000 traços curtos paralelos: o teto vem do orçamento, nunca de um laço sem limite."""
    caminhos = [
        linha((5.0 + (i % 200) * 2.9, 5.0 + (i // 200) * 0.7), (5.0 + (i % 200) * 2.9, 13.0))
        for i in range(20_000)
    ]
    pagina = pagina_gramatica(caminhos, largura=700.0, altura=200.0)

    with pytest.raises(TetoGramaticasExcedido):
        contexto = contexto_gramaticas(pagina, limite=5_000)
        casa_hastes(contexto, _GRAMATICA)


def test_gasto_cresce_linear_com_hastes() -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais hastes isoladas, no máximo 15x."""
    (pequeno, casadas_pequeno), (grande, casadas_grande) = (
        _gasto_e_casamentos(10),
        _gasto_e_casamentos(100),
    )

    assert (casadas_pequeno, casadas_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA
