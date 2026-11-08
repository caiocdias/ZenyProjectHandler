"""Teto de orçamento da gramática `rect_diagonal`: página hostil e gasto linear com os símbolos."""

from __future__ import annotations

from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, retangulo_traco
from tests.fixtures.symbol_grammars.rect_diagonal import CASOS_RECT_DIAGONAL

from zeny_project_handler.adapters.analysis.drawing_model.grammar_rect_diagonal import (
    Perfil,
    _quadrilateros,
    casa_retangulos_diagonal,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

_GRAMATICA: Final = CASOS_RECT_DIAGONAL[0][1]
_PASSO: Final = 40.0
_COLUNAS: Final = 50
_RAZAO_MAXIMA: Final = 12
_FOLGA: Final = 100
_QUANTIDADE_HOSTIL: Final = 2_000


def _simbolo_isolado(cx: float, cy: float) -> list[Caminho]:
    """Retângulo de 8 x 3 pt com uma diagonal que o cruza pelos lados longos e passa além."""
    return [
        retangulo_traco((cx - 4.0, cy - 1.5, cx + 4.0, cy + 1.5)),
        linha((cx - 2.0, cy - 3.0), (cx + 2.0, cy + 3.0)),
    ]


def _pagina_com_simbolos(quantidade: int) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        caminhos.extend(
            _simbolo_isolado(30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)
        )
    return pagina_gramatica(
        caminhos, largura=_COLUNAS * _PASSO + 60.0, altura=(quantidade // _COLUNAS + 2) * _PASSO
    )


def _gasto_e_casamentos(quantidade: int) -> tuple[int, int]:
    contexto = contexto_gramaticas(_pagina_com_simbolos(quantidade), limite=10**9)
    casamentos = casa_retangulos_diagonal(contexto, _GRAMATICA)
    return contexto.orcamento.gasto, len(casamentos)


def _pagina_hostil() -> PaginaGramatica:
    """Milhares de quadriláteros e diagonais nas mesmas células da grade (16 pt).

    Os quadriláteros têm tamanhos todos distintos (nenhum é descartado como duplicata) e as
    sementes caem sobre as células deles: cada semente consulta todos os quadriláteros.
    """
    caminhos: list[Caminho] = []
    for i in range(_QUANTIDADE_HOSTIL):
        cx, cy = 100.0 + (i % 40) * 0.05, 100.0 + (i // 40) * 0.05
        meio_maior = 4.0 + (i % 50) * 0.04
        meio_menor = 1.5 + (i // 50) * 0.002
        caminhos.append(
            retangulo_traco((cx - meio_maior, cy - meio_menor, cx + meio_maior, cy + meio_menor))
        )
        dx = 1.0 + (i % 7) * 0.3
        caminhos.append(linha((cx - dx, cy - 3.0 - (i % 5) * 0.1), (cx + dx, cy + 3.0)))
    return pagina_gramatica(caminhos, largura=300.0, altura=300.0)


def test_pagina_hostil_estoura_o_orcamento() -> None:
    """Quadriláteros e diagonais empilhados: o teto vem das consultas das sementes.

    O limite deixa passar os índices e a grade dos quadriláteros (1 por item indexado); o
    estouro só pode vir das consultas das sementes à grade, nunca do laço sem limite.
    """
    pagina = _pagina_hostil()
    so_indices = contexto_gramaticas(pagina).orcamento.gasto
    custo_da_grade = so_indices + len(_quadrilateros(pagina.modelo, Perfil()))
    contexto = contexto_gramaticas(pagina, limite=custo_da_grade + _FOLGA)

    with pytest.raises(TetoGramaticasExcedido):
        casa_retangulos_diagonal(contexto, _GRAMATICA)

    assert contexto.orcamento.gasto > custo_da_grade
    assert len(_quadrilateros(pagina.modelo, Perfil())) == _QUANTIDADE_HOSTIL


def test_gasto_cresce_linear_com_os_simbolos() -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais símbolos isolados, no máximo 12x."""
    (pequeno, casadas_pequeno), (grande, casadas_grande) = (
        _gasto_e_casamentos(10),
        _gasto_e_casamentos(100),
    )

    assert (casadas_pequeno, casadas_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA
