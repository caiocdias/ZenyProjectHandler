"""Grupos candidatos a símbolo."""

from __future__ import annotations

import math
import time
from itertools import pairwise
from typing import Literal

from zeny_project_handler.adapters.analysis.drawing_model.groups import agrupar_candidatos
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caminho,
    Circulo,
    Estilo,
    ItemCaminho,
    Polilinha,
)

Ponto = tuple[float, float]
TipoCaminho = Literal["traco", "preenchimento", "traco_e_preenchimento"]
E = Estilo("SIMB", (0, 0, 0), (0, 0, 0), 1.0, "")


def circulo(cx: float, cy: float, r: float = 2.0, origem: int = 0) -> Circulo:
    return Circulo((cx, cy), r, E, (origem,))


def linha(*pontos: Ponto) -> Polilinha:
    return Polilinha(pontos, False, E, (0,))


def poligono(*pontos: Ponto, tipo: TipoCaminho = "preenchimento") -> Caminho:
    fechado = (*pontos, pontos[0])
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(fechado))
    return Caminho((itens,), E, tipo, 0)


def bezier(p0: Ponto, p1: Ponto) -> ItemCaminho:
    return ItemCaminho("c", (p0, (p0[0], p0[1] + 3), (p1[0], p1[1] + 3), p1))


def test_agrupa_circulo_e_tracos_proximos_num_grupo() -> None:
    grupos = agrupar_candidatos([circulo(10, 10), linha((12, 10), (20, 10), (20, 15))], [])
    assert len(grupos) == 1
    assert grupos[0].indices_primitivas == (0, 1)
    assert grupos[0].indices_caminhos == ()
    assert grupos[0].bbox == (8, 8, 20, 15)


def test_triangulo_preenchido_entra_no_grupo_pelos_caminhos() -> None:
    grupos = agrupar_candidatos([], [poligono((0, 0), (6, 0), (3, 5))])
    assert len(grupos) == 1 and grupos[0].indices_caminhos == (0,)


def test_caminho_que_virou_circulo_nao_entra_duas_vezes() -> None:
    itens = tuple(bezier((0, 0), (4, 0)) for _ in range(4))
    caminho = Caminho((itens,), E, "preenchimento", 0)
    grupos = agrupar_candidatos([circulo(2, 2)], [caminho])
    assert len(grupos) == 1
    assert grupos[0].indices_primitivas == (0,) and grupos[0].indices_caminhos == ()


def test_preenchido_com_arco_parcial_entra_pelos_caminhos() -> None:
    itens = (ItemCaminho("l", ((0, 0), (0, 6))), bezier((0, 6), (0, 0)))
    caminho = Caminho((itens,), E, "preenchimento", 0)
    arco = Arco((0, 3), 3.0, 270.0, 90.0, E, (0,))
    grupos = agrupar_candidatos([arco], [caminho])
    assert len(grupos) == 1 and grupos[0].indices_caminhos == (0,)


def test_elipse_tracada_entra_pelos_caminhos() -> None:
    caminho = Caminho(((bezier((0, 0), (8, 0)),),), E, "traco", 0)
    grupos = agrupar_candidatos([], [caminho])
    assert len(grupos) == 1 and grupos[0].indices_caminhos == (0,)


def test_traco_so_com_linhas_nao_entra_pelos_caminhos() -> None:
    assert agrupar_candidatos([], [poligono((0, 0), (6, 0), (3, 5), tipo="traco")]) == ()


def test_nao_agrupa_formas_distantes() -> None:
    grupos = agrupar_candidatos([circulo(0, 0), circulo(30, 0)], [])
    assert [g.indices_primitivas for g in grupos] == [(0,), (1,)]


def test_descarta_grupo_maior_que_lado_maximo() -> None:
    cadeia = [circulo(i * 3.0, 0, 2.0) for i in range(30)]  # largura ~ 90
    assert agrupar_candidatos(cadeia, []) == ()


def test_descarta_polilinha_aberta_isolada_de_dois_pontos() -> None:
    assert agrupar_candidatos([linha((0, 0), (10, 0))], []) == ()


def _melhor_tempo(n: int) -> float:
    primitivas = [circulo((i % 100) * 20.0, (i // 100) * 20.0, 2.0) for i in range(n)]
    melhor = math.inf
    for _ in range(3):
        inicio = time.perf_counter()
        agrupar_candidatos(primitivas, [])
        melhor = min(melhor, time.perf_counter() - inicio)
    return melhor


def test_agrupamento_escala_linearmente() -> None:
    assert _melhor_tempo(20_000) / _melhor_tempo(10_000) < 3
