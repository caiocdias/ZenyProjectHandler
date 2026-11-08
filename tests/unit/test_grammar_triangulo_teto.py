"""Teto de orçamento da gramática `split_triangle`: página hostil e gasto linear com os símbolos."""

from __future__ import annotations

from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import estilo, pagina_gramatica, poligono
from tests.fixtures.symbol_grammars.triangulo import (
    CASOS_TRIANGULO,
    CIANO,
    GRUPO_DA_VARIANTE,
    GRUPOS,
    LADO,
    caminhos_trafo,
    vertices,
)

from zeny_project_handler.adapters.analysis.drawing_model.grammar_triangulo import (
    casa_triangulos,
    triangulos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    ItemCaminho,
    Ponto,
)
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    PaginaGramatica,
    TetoGramaticasExcedido,
    contexto_gramaticas,
)

_GRAMATICA_POR_GRUPO: Final = {GRUPO_DA_VARIANTE[id_]: g for id_, g in reversed(CASOS_TRIANGULO)}
_PASSO: Final = 40.0
_COLUNAS: Final = 50
_RAZAO_MAXIMA: Final = 12
_FOLGA_POR_TRIANGULO: Final = 4
_EMPILHADOS: Final = 1_500
_FATIAS: Final = 3_000


def _simbolos(grupo: tuple[str, str, bool], quantidade: int) -> PaginaGramatica:
    caminhos: list[Caminho] = []
    for i in range(quantidade):
        centro = (30.0 + (i % _COLUNAS) * _PASSO, 30.0 + (i // _COLUNAS) * _PASSO)
        caminhos.extend(caminhos_trafo(grupo, centro, LADO))
    return pagina_gramatica(
        caminhos, largura=_COLUNAS * _PASSO + 60.0, altura=(quantidade // _COLUNAS + 2) * _PASSO
    )


def _gasto_e_casamentos(grupo: tuple[str, str, bool], quantidade: int) -> tuple[int, int]:
    contexto = contexto_gramaticas(_simbolos(grupo, quantidade), limite=10**9)
    casamentos = casa_triangulos(contexto, _GRAMATICA_POR_GRUPO[grupo])
    return contexto.orcamento.gasto, len(casamentos)


def _hachura(fatias: int, centro: Ponto) -> Caminho:
    """Um preenchimento ciano de `fatias` triângulos finos com o vértice no ápice."""
    apice, base0, base1 = vertices(centro, 0.0, LADO)
    pontos = [
        (
            base0[0] + (base1[0] - base0[0]) * k / fatias,
            base0[1] + (base1[1] - base0[1]) * k / fatias,
        )
        for k in range(fatias + 1)
    ]
    subcaminhos = tuple(
        (
            ItemCaminho("l", (apice, pontos[k])),
            ItemCaminho("l", (pontos[k], pontos[k + 1])),
            ItemCaminho("l", (pontos[k + 1], apice)),
        )
        for k in range(fatias)
    )
    return Caminho(subcaminhos, estilo(None, CIANO), "preenchimento", 0)


def _pagina_hostil() -> PaginaGramatica:
    """Milhares de triângulos de contorno e de meios cianos nas mesmas células, mais um
    preenchimento de milhares de fatias de hachura.

    Os triângulos diferem em frações de milésimo: todos são o mesmo desenho dentro da tolerância e
    cada um consulta todos os que já estão no índice de centros (o gasto quadrático que o teto
    precisa cobrar).
    """
    caminhos: list[Caminho] = []
    for i in range(_EMPILHADOS):
        centro = (100.0 + (i % 40) * 0.001, 100.0 + (i // 40) * 0.001)
        caminhos.append(poligono(vertices(centro, 0.0, LADO)))
        meio_centro = (200.0 + (i % 40) * 0.001, 100.0 + (i // 40) * 0.001)
        a, b, c = vertices(meio_centro, 0.0, LADO)
        m = ((b[0] + c[0]) / 2, (b[1] + c[1]) / 2)
        caminhos.append(poligono([m, a, b], preenchimento=CIANO))
        caminhos.append(poligono([m, a, c], preenchimento=(1.0, 1.0, 1.0)))
    caminhos.append(_hachura(_FATIAS, (50.0, 200.0)))
    return pagina_gramatica(caminhos)


def test_pagina_hostil_estoura_o_orcamento() -> None:
    """Triângulos empilhados e hachura de milhares de fatias: o teto vem do gasto da gramática.

    O limite deixa passar os índices da página e 4 por triângulo (a leitura linear); o estouro só
    pode vir das comparações entre os contornos e os meios cianos empilhados, que pagam 1 por
    vizinho, nunca de um laço sem limite.
    """
    pagina = _pagina_hostil()
    contexto = contexto_gramaticas(pagina)
    limite = contexto.orcamento.gasto + _FOLGA_POR_TRIANGULO * 3 * _EMPILHADOS
    contexto = contexto_gramaticas(pagina, limite=limite)

    with pytest.raises(TetoGramaticasExcedido):
        triangulos_candidatos(contexto)

    assert contexto.orcamento.gasto >= limite


def test_hachura_de_milhares_de_fatias_nao_gasta_nem_casa() -> None:
    """Fatias mais finas que o fechamento não formam triângulo: o preenchimento é descartado
    sem passar pelos índices, e a página não casa nada."""
    contexto = contexto_gramaticas(pagina_gramatica([_hachura(_FATIAS, (150.0, 150.0))]))
    gasto_dos_indices = contexto.orcamento.gasto

    candidatos = triangulos_candidatos(contexto)

    assert candidatos == ()
    assert contexto.orcamento.gasto == gasto_dos_indices


@pytest.mark.parametrize("grupo", GRUPOS, ids=lambda g: "-".join(map(str, g)))
def test_gasto_cresce_linear_com_os_simbolos(grupo: tuple[str, str, bool]) -> None:
    """Contagem de trabalho (não tempo de parede): 10x mais símbolos isolados, no máximo 12x."""
    (pequeno, casadas_pequeno), (grande, casadas_grande) = (
        _gasto_e_casamentos(grupo, 10),
        _gasto_e_casamentos(grupo, 100),
    )

    assert (casadas_pequeno, casadas_grande) == (10, 100)
    assert pequeno > 0
    assert grande / pequeno <= _RAZAO_MAXIMA
