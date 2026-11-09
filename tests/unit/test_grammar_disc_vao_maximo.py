"""Teto do vão do disco parametrizado (R-E06.3.5-3): o default não muda `terminal_disc`."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import circulo_bezier, pagina_gramatica, poligono

from zeny_project_handler.adapters.analysis.drawing_model.grammar_disc import (
    _caixas_de_faixa,
    discos_candidatos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caixa, Caminho, Cor
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    contexto_gramaticas,
)

VERMELHO: Final[Cor] = (0.9, 0.1, 0.1)
CENTRO: Final = (150.0, 150.0)
RAIO_DE_14_PT: Final = 7.2  # diâmetro 14,4 pt
TETO_DO_SCHEMA: Final = 72.0


def _cantos(caixa: Caixa) -> tuple[tuple[float, float], ...]:
    x0, y0, x1, y1 = caixa
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _disco_de_curva(raio: float) -> Caminho:
    return circulo_bezier(CENTRO, raio, 0, cor=VERMELHO, preenchimento=VERMELHO)


def _cordas(raio: float, quantidade: int) -> list[Caminho]:
    from math import sqrt

    altura = 2 * raio / quantidade
    caminhos: list[Caminho] = []
    for indice in range(quantidade):
        y0 = CENTRO[1] - raio + indice * altura
        meio = y0 + altura / 2 - CENTRO[1]
        corda = raio * sqrt(max(0.0, 1 - (meio / raio) ** 2))
        caixa = (CENTRO[0] - corda, y0, CENTRO[0] + corda, y0 + altura)
        caminhos.append(poligono(_cantos(caixa), indice, VERMELHO, cor=None))
    return caminhos


def _candidatos(caminhos: Sequence[Caminho], **kwargs: float) -> tuple[object, ...]:
    return discos_candidatos(contexto_gramaticas(pagina_gramatica(caminhos)), **kwargs)


def test_default_recusa_disco_de_14_pt() -> None:
    assert _candidatos([_disco_de_curva(RAIO_DE_14_PT)]) == ()


def test_vao_maximo_72_aceita_disco_de_14_pt() -> None:
    discos = _candidatos([_disco_de_curva(RAIO_DE_14_PT)], vao_maximo=TETO_DO_SCHEMA)
    assert len(discos) == 1


def test_vao_maximo_72_aceita_disco_em_faixas_de_14_pt() -> None:
    caminhos = _cordas(RAIO_DE_14_PT, 30)
    assert _candidatos(caminhos) == ()
    assert len(_candidatos(caminhos, vao_maximo=TETO_DO_SCHEMA)) == 1


def test_default_mantem_o_disco_de_8_pt() -> None:
    assert len(_candidatos([_disco_de_curva(4.0)])) == 1
    assert _candidatos([_disco_de_curva(4.01)]) == ()


def test_vao_maximo_explicito_igual_ao_default_da_o_mesmo_resultado() -> None:
    caminhos = [_disco_de_curva(1.4), *_cordas(3.0, 12)]
    assert _candidatos(caminhos, vao_maximo=8.0) == _candidatos(caminhos)


def test_default_gasta_o_mesmo_que_antes() -> None:
    contexto = contexto_gramaticas(pagina_gramatica(_cordas(3.0, 12)))
    antes = contexto.orcamento.gasto
    discos_candidatos(contexto)
    assert contexto.orcamento.gasto - antes == 11


@pytest.mark.parametrize(("vao_maximo", "faixas"), [(8.0, 0), (72.0, 1)])
def test_caixas_de_faixa_respeita_o_parametro(vao_maximo: float, faixas: int) -> None:
    caminho = poligono(_cantos((100.0, 100.0, 114.4, 100.5)), 0, VERMELHO, cor=None)
    assert len(_caixas_de_faixa(caminho, None, vao_maximo)) == faixas
