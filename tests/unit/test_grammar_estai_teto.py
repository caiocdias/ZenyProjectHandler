"""Teto da gramática `forked_stem`: classificação única, gasto linear e página hostil."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import pytest
from tests.fixtures.symbol_grammars.estai import (
    GRAMATICAS_ESTAI,
    estai_com_circulo,
    garfo,
    x_sobre,
)
from tests.fixtures.symbol_grammars.paginas import pagina_gramatica

from zeny_project_handler.adapters.analysis.drawing_model.grammar_estai import estai_candidatos
from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import MarcasDaPagina
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_matcher import gasto_por_fase

_PASSO: Final = 60.0
_COLUNAS: Final = 5
_RAZAO_MAXIMA: Final = 12
_FOLGA_POR_GARFO: Final = 8
_EMPILHADOS: Final = 1_500


def _pagina(caminhos: list[Caminho], quantidade: int) -> PaginaGramatica:
    return pagina_gramatica(
        caminhos,
        primitivas=(),
        largura=_COLUNAS * _PASSO + 60.0,
        altura=(quantidade // _COLUNAS + 2) * _PASSO + 60.0,
    )


def _base(i: int) -> tuple[float, float]:
    return (30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)


def _pares(
    nomes: tuple[str, ...] = tuple(GRAMATICAS_ESTAI),
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    return [
        (
            {"family_id": "autoral"},
            {"id": nome, "recognition": {"status": "enabled", "grammar": GRAMATICAS_ESTAI[nome]}},
        )
        for nome in nomes
    ]


def _pagina_dos_tres_tipos(quantidade: int) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        base = _base(i)
        if i % 3 == 0:
            caminhos.extend(garfo(base=base))
        elif i % 3 == 1:
            caminhos.extend(estai_com_circulo(base=base))
        else:
            caminhos.extend(garfo(base=base))
            caminhos.extend(x_sobre(base))
    return _pagina(caminhos, quantidade)


def test_classificacao_uma_vez_por_candidato() -> None:
    """As 3 variantes custam o mesmo que uma só: `casa_estai` só filtra a classificação pronta."""
    pagina = _pagina_dos_tres_tipos(12)

    tres = gasto_por_fase(pagina, _pares())
    uma = gasto_por_fase(pagina, _pares(("existente",)))

    assert tres.gramaticas > 0
    assert tres == uma


def _gasto_dos_candidatos(quantidade: int) -> tuple[int, int]:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        caminhos.extend(garfo(base=_base(i)))
    contexto = contexto_gramaticas(_pagina(caminhos, quantidade), limite=10**9)
    antes = contexto.orcamento.gasto
    candidatos = estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))
    return contexto.orcamento.gasto - antes, len(candidatos)


def test_gasto_cresce_linear_com_os_desenhos() -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais desenhos isolados, no máximo 12x."""
    (pequeno, achados_pequeno), (grande, achados_grande) = (
        _gasto_dos_candidatos(10),
        _gasto_dos_candidatos(100),
    )

    assert (achados_pequeno, achados_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA


def test_pagina_hostil_estoura_o_orcamento() -> None:
    """Milhares de garfos quase coincidentes: o teto é o gasto dos índices mais uma folga linear.

    O limite deixa passar a leitura linear (`_FOLGA_POR_GARFO` por garfo); o estouro só vem de a
    gramática pagar os laços sobre as mesmas células, nunca de um laço sem orçamento.
    """
    caminhos: list[Caminho] = []
    for i in range(_EMPILHADOS):
        caminhos.extend(garfo(base=(100.0 + (i % 40) * 0.001, 100.0 + (i // 40) * 0.001)))
    pagina = pagina_gramatica(caminhos, primitivas=())
    limite = contexto_gramaticas(pagina).orcamento.gasto + _FOLGA_POR_GARFO * _EMPILHADOS
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        estai_candidatos(contexto, marcas=MarcasDaPagina(contexto))

    assert contexto.orcamento.gasto >= limite
