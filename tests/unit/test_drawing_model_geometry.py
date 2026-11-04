"""Geometria pura do modelo de desenho: polilinhas, círculos e arcos."""

from __future__ import annotations

import math
import time
from itertools import pairwise
from typing import Literal

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.geometry import (
    reconstruir_polilinhas,
    recuperar_circulos_e_arcos,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caminho,
    Circulo,
    Estilo,
    ItemCaminho,
)

Ponto = tuple[float, float]
TipoCaminho = Literal["traco", "preenchimento", "traco_e_preenchimento"]
KAPPA = 0.5522847498307936


def traco(estilo: Estilo, *pontos: Ponto, ordem: int, tipo: TipoCaminho = "traco") -> Caminho:
    itens = tuple(ItemCaminho("l", (inicio, fim)) for inicio, fim in pairwise(pontos))
    return Caminho((itens,), estilo, tipo, ordem)


def quadrado(estilo: Estilo, tipo: TipoCaminho) -> Caminho:
    return traco(estilo, (0, 0), (10, 0), (10, 10), (0, 10), (0, 0), ordem=0, tipo=tipo)


def quarto(cx: float, cy: float, r: float, k: int) -> ItemCaminho:
    """Quarto de círculo número k (0..3), no sentido horário visual."""
    a0 = math.radians(90 * k)
    a1 = math.radians(90 * (k + 1))
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    c1 = (p0[0] - KAPPA * r * math.sin(a0), p0[1] + KAPPA * r * math.cos(a0))
    c2 = (p1[0] + KAPPA * r * math.sin(a1), p1[1] - KAPPA * r * math.cos(a1))
    return ItemCaminho("c", (p0, c1, c2, p1))


def circulo_em_beziers(centro: Ponto, raio: float, *, tipo: TipoCaminho) -> Caminho:
    estilo = Estilo("SIMB", (0, 0, 0), (0, 0, 0), 1.0, "")
    itens = tuple(quarto(centro[0], centro[1], raio, k) for k in range(4))
    return Caminho((itens,), estilo, tipo, 0)


def test_segmentos_colineares_fragmentados_viram_uma_polilinha() -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    caminhos = [
        traco(e, (0, 0), (10, 0), ordem=0),
        traco(e, (10, 0), (25, 0), ordem=1),
        traco(e, (25.2, 0), (40, 0), ordem=2),
    ]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.pontos == ((0, 0), (40, 0))
    assert not p.fechada
    assert p.origens == (0, 1, 2)


def test_segmentos_em_l_viram_polilinha_de_tres_pontos() -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    caminhos = [traco(e, (0, 0), (10, 0), ordem=0), traco(e, (10, 0), (10, 10), ordem=1)]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.pontos == ((0, 0), (10, 0), (10, 10))
    assert not p.fechada
    assert p.origens == (0, 1)


def test_quadrado_de_traco_vira_polilinha_fechada() -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    (p,) = reconstruir_polilinhas([quadrado(e, "traco")])
    assert p.fechada
    assert set(p.pontos) == {(0, 0), (10, 0), (10, 10), (0, 10)}
    assert len(p.pontos) == 4
    assert p.origens == (0,)


@pytest.mark.parametrize(
    "outro",
    [
        Estilo("OUTRA", (0, 0, 0), None, 1.0, ""),
        Estilo("REDE", (1, 0, 0), None, 1.0, ""),
        Estilo("REDE", (0, 0, 0), None, 2.0, ""),
        Estilo("REDE", (0, 0, 0), None, 1.0, "[3] 0"),
    ],
)
def test_nao_funde_segmentos_de_estilo_diferente(outro: Estilo) -> None:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    caminhos = [traco(e, (0, 0), (10, 0), ordem=0), traco(outro, (10, 0), (20, 0), ordem=1)]
    polilinhas = reconstruir_polilinhas(caminhos)
    assert len(polilinhas) == 2
    assert {p.pontos for p in polilinhas} == {((0, 0), (10, 0)), ((10, 0), (20, 0))}


def test_caminho_preenchido_nao_entra_na_fusao() -> None:
    e = Estilo("REDE", None, (0, 0, 0), 1.0, "")
    assert reconstruir_polilinhas([quadrado(e, "preenchimento")]) == ()


def test_circulo_em_quatro_beziers_vira_circulo() -> None:
    (c,) = recuperar_circulos_e_arcos([circulo_em_beziers((50, 50), 5, tipo="traco")])
    assert isinstance(c, Circulo)
    assert c.centro == pytest.approx((50, 50), abs=1e-3)
    assert c.raio == pytest.approx(5, rel=1e-3)
    assert c.origens == (0,)


def test_disco_preenchido_tambem_vira_circulo() -> None:
    (c,) = recuperar_circulos_e_arcos([circulo_em_beziers((20, 30), 3, tipo="preenchimento")])
    assert isinstance(c, Circulo)
    assert c.centro == pytest.approx((20, 30), abs=1e-3)
    assert c.raio == pytest.approx(3, rel=1e-3)


def test_quarto_de_circulo_vira_arco() -> None:
    estilo = Estilo("SIMB", (0, 0, 0), None, 1.0, "")
    caminho = Caminho(((quarto(50, 50, 5, 1),),), estilo, "traco", 0)
    (a,) = recuperar_circulos_e_arcos([caminho])
    assert isinstance(a, Arco)
    assert a.centro == pytest.approx((50, 50), abs=1e-3)
    assert a.raio == pytest.approx(5, rel=1e-3)
    assert a.angulo_inicial == pytest.approx(90, abs=0.1)
    assert a.angulo_final == pytest.approx(180, abs=0.1)


def test_elipse_nao_vira_circulo() -> None:
    estilo = Estilo("SIMB", (0, 0, 0), None, 1.0, "")
    rx, ry = 5.0, 8.0
    itens = []
    for k in range(4):
        a0, a1 = math.radians(90 * k), math.radians(90 * (k + 1))
        p0 = (rx * math.cos(a0), ry * math.sin(a0))
        p1 = (rx * math.cos(a1), ry * math.sin(a1))
        c1 = (p0[0] - KAPPA * rx * math.sin(a0), p0[1] + KAPPA * ry * math.cos(a0))
        c2 = (p1[0] + KAPPA * rx * math.sin(a1), p1[1] - KAPPA * ry * math.cos(a1))
        itens.append(ItemCaminho("c", (p0, c1, c2, p1)))
    assert recuperar_circulos_e_arcos([Caminho((tuple(itens),), estilo, "traco", 0)]) == ()


def test_curva_s_nao_vira_arco() -> None:
    estilo = Estilo("SIMB", (0, 0, 0), None, 1.0, "")
    s = ItemCaminho("c", ((0, 0), (10, 10), (0, 10), (10, 0)))
    assert recuperar_circulos_e_arcos([Caminho(((s,),), estilo, "traco", 0)]) == ()


def _segmentos(quantidade: int) -> list[Caminho]:
    e = Estilo("REDE", (0, 0, 0), None, 1.0, "")
    por_linha = 100
    return [
        traco(
            e,
            (float(i % por_linha), float(i // por_linha * 5)),
            (float(i % por_linha + 1), float(i // por_linha * 5)),
            ordem=i,
        )
        for i in range(quantidade)
    ]


def _melhor_tempo(caminhos: list[Caminho]) -> float:
    melhor = math.inf
    for _ in range(3):
        inicio = time.perf_counter()
        reconstruir_polilinhas(caminhos)
        melhor = min(melhor, time.perf_counter() - inicio)
    return melhor


def test_fusao_escala_linearmente() -> None:
    pequeno, grande = _segmentos(10_000), _segmentos(20_000)
    assert len(reconstruir_polilinhas(grande)) == 200
    assert _melhor_tempo(grande) / _melhor_tempo(pequeno) < 3
