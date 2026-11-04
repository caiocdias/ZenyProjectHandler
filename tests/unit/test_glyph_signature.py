from __future__ import annotations

import math

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PONTOS_POR_SUBCAMINHO,
    achatar_subcaminho,
    assinatura_glifo,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import ItemCaminho, Ponto

L_FORMA: list[Ponto] = [(0, 0), (1, 0), (1, 4), (3, 4), (3, 5), (0, 5)]
T_FORMA: list[Ponto] = [(0, 0), (3, 0), (3, 1), (2, 1), (2, 5), (1, 5), (1, 1), (0, 1)]


def _transformar(pontos: list[Ponto], escala: float, dx: float, dy: float) -> list[Ponto]:
    return [(x * escala + dx, y * escala + dy) for x, y in pontos]


def _circulo(raio: float, deslocamento: float = 0.0) -> list[ItemCaminho]:
    k = 0.5522847498 * raio
    cantos = [(raio, 0.0), (0.0, raio), (-raio, 0.0), (0.0, -raio)]
    controles = [
        ((raio, k), (k, raio)),
        ((-k, raio), (-raio, k)),
        ((-raio, -k), (-k, -raio)),
        ((k, -raio), (raio, -k)),
    ]
    itens = []
    for i, (c1, c2) in enumerate(controles):
        c1 = (c1[0] + deslocamento, c1[1])
        c2 = (c2[0], c2[1] + deslocamento)
        itens.append(ItemCaminho("c", (cantos[i], c1, c2, cantos[(i + 1) % 4])))
    return itens


def test_assinatura_invariante_a_translacao_e_escala() -> None:
    a = assinatura_glifo([L_FORMA], altura_linha=5.0, base_linha=5.0)
    b = assinatura_glifo(
        [_transformar(L_FORMA, 3.0, 40.0, -7.0)], altura_linha=15.0, base_linha=3 * 5.0 - 7.0
    )
    assert a is not None and b is not None
    assert distancia_assinaturas(a, b) == pytest.approx(0, abs=1e-9)
    assert all(len(c) == PONTOS_POR_SUBCAMINHO for c in a.contornos)


def test_inicio_e_sentido_do_contorno_nao_mudam_a_assinatura() -> None:
    outro = L_FORMA[3:] + L_FORMA[:3]
    inverso = list(reversed(L_FORMA))
    a = assinatura_glifo([L_FORMA], altura_linha=5.0, base_linha=5.0)
    for variante in (outro, inverso):
        b = assinatura_glifo([variante], altura_linha=5.0, base_linha=5.0)
        assert a is not None and b is not None
        assert distancia_assinaturas(a, b) < 1e-6


def test_formas_diferentes_ficam_longe() -> None:
    letra_l = assinatura_glifo([L_FORMA], altura_linha=5.0, base_linha=5.0)
    letra_t = assinatura_glifo([T_FORMA], altura_linha=5.0, base_linha=5.0)
    dois = assinatura_glifo(
        [L_FORMA, _transformar([(0, 0), (1, 0), (1, 1), (0, 1)], 1.0, 5.0, 0.0)],
        altura_linha=5.0,
        base_linha=5.0,
    )
    assert letra_l is not None and letra_t is not None and dois is not None
    assert distancia_assinaturas(letra_l, letra_t) > 0.08
    assert distancia_assinaturas(letra_l, dois) == math.inf


def test_variacao_pequena_de_curva_fica_dentro_da_tolerancia() -> None:
    raio = 10.0
    a = assinatura_glifo(
        [list(achatar_subcaminho(_circulo(raio)))], altura_linha=20.0, base_linha=10.0
    )
    b = assinatura_glifo(
        [list(achatar_subcaminho(_circulo(raio, 0.01 * raio)))],
        altura_linha=20.0,
        base_linha=10.0,
    )
    assert a is not None and b is not None
    assert distancia_assinaturas(a, b) < 0.08


def test_achatar_subcaminho_segmentos_e_beziers() -> None:
    itens = [
        ItemCaminho("l", ((0.0, 0.0), (2.0, 0.0))),
        ItemCaminho("c", ((2.0, 0.0), (2.0, 1.0), (1.0, 2.0), (0.0, 2.0))),
    ]
    pontos = achatar_subcaminho(itens)
    assert pontos[0] == (0.0, 0.0)
    assert pontos[1] == (2.0, 0.0)
    assert pontos[-1] == (0.0, 2.0)
    assert len(pontos) == 2 + 8
    assert achatar_subcaminho([]) == ()


@pytest.mark.parametrize(
    ("poligonos", "altura"),
    [
        ([[(1.0, 1.0)] * 5], 5.0),
        ([[(0.0, 0.0), (math.nan, 1.0), (1.0, 1.0)]], 5.0),
        ([[(0.0, 0.0), (math.inf, 1.0), (1.0, 1.0)]], 5.0),
        ([L_FORMA], 0.0),
        ([L_FORMA], -1.0),
        ([], 5.0),
    ],
)
def test_degenerado_devolve_none(poligonos: list[list[Ponto]], altura: float) -> None:
    assert assinatura_glifo(poligonos, altura_linha=altura, base_linha=5.0) is None
