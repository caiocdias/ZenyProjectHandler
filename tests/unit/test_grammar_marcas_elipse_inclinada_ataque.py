"""Fronteira da anisotropia mínima da envolvente inclinada.

Ovais de 72 retas e círculo de 32, desenho autoral relativo à escala: abaixo da anisotropia
mínima a direção principal é ruído e a elipse fica alinhada; acima, a inclinação é a do desenho.
"""

from __future__ import annotations

import math
from typing import Final

import pytest
from tests.fixtures.symbol_grammars.paginas import linha, pagina_gramatica, poligono

from zeny_project_handler.adapters.analysis.drawing_model.grammar_marcas import (
    Contorno,
    MarcasDaPagina,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Caminho, Ponto
from zeny_project_handler.adapters.analysis.drawing_model.symbol_grammars import (
    contexto_gramaticas,
)

_TOLERANCIA_RAD: Final = 1e-3
_CENTRO: Final[Ponto] = (150.0, 150.0)
_TODA_A_PAGINA: Final = (0.0, 0.0, 300.0, 300.0)


def _gira(ponto: Ponto, graus: float) -> Ponto:
    r = math.radians(graus)
    dx, dy = ponto[0] - _CENTRO[0], ponto[1] - _CENTRO[1]
    return (
        _CENTRO[0] + dx * math.cos(r) - dy * math.sin(r),
        _CENTRO[1] + dx * math.sin(r) + dy * math.cos(r),
    )


def _elipse_girada(a: float, b: float, graus: float, lados: int = 72) -> list[Ponto]:
    pontos = [
        (
            _CENTRO[0] + a * math.cos(2 * math.pi * k / lados),
            _CENTRO[1] + b * math.sin(2 * math.pi * k / lados),
        )
        for k in range(lados)
    ]
    return [_gira(p, graus) for p in pontos]


def _encostados(vertices: list[Ponto]) -> list[Caminho]:
    """Dois traços que saem de vértices opostos: partem a polilinha reconstruída."""
    caminhos = []
    for vertice in (vertices[len(vertices) // 8], vertices[len(vertices) // 8 * 5]):
        dx, dy = vertice[0] - _CENTRO[0], vertice[1] - _CENTRO[1]
        norma = math.hypot(dx, dy)
        caminhos.append(linha(vertice, (vertice[0] + 3 * dx / norma, vertice[1] + 3 * dy / norma)))
    return caminhos


def _contorno_unico(vertices: list[Ponto]) -> Contorno:
    pagina = pagina_gramatica([poligono(vertices), *_encostados(vertices)])
    contornos = list(
        MarcasDaPagina(contexto_gramaticas(pagina)).contornos.consultar(_TODA_A_PAGINA)
    )
    [contorno] = contornos
    return contorno


def test_razao_1_005_girada_30_graus_fica_alinhada() -> None:
    contorno = _contorno_unico(_elipse_girada(10.0, 10.0 / 1.005, 30.0))

    assert contorno.inclinacao == 0.0


def test_razao_1_05_girada_30_graus_tem_inclinacao_de_30_graus() -> None:
    contorno = _contorno_unico(_elipse_girada(10.0, 10.0 / 1.05, 30.0))

    assert contorno.inclinacao == pytest.approx(math.radians(30.0), abs=_TOLERANCIA_RAD)


@pytest.mark.parametrize("graus", [0.0, 7.0, 30.0, 45.0, 77.0, 123.0], ids=lambda g: f"{g:g}")
def test_circulo_regular_de_32_retas_girado_nao_tem_inclinacao(graus: float) -> None:
    raio = 10.0
    circulo = [
        _gira(
            (
                _CENTRO[0] + raio * math.cos(2 * math.pi * k / 32),
                _CENTRO[1] + raio * math.sin(2 * math.pi * k / 32),
            ),
            graus,
        )
        for k in range(32)
    ]

    assert _contorno_unico(circulo).inclinacao == 0.0
