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


def quarto(cx: float, cy: float, r: float, k: int) -> ItemCaminho:
    kappa = 0.5522847498307936
    a0, a1 = math.radians(90 * k), math.radians(90 * (k + 1))
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    c1 = (p0[0] - kappa * r * math.sin(a0), p0[1] + kappa * r * math.cos(a0))
    c2 = (p1[0] + kappa * r * math.sin(a1), p1[1] - kappa * r * math.cos(a1))
    return ItemCaminho("c", (p0, c1, c2, p1))


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
    caminho = Caminho((tuple(quarto(2, 2, 2.0, k) for k in range(4)),), E, "preenchimento", 0)
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


def test_linha_longa_encostada_nao_apaga_o_simbolo() -> None:
    primitivas: list[Polilinha | Circulo | Arco] = [
        linha((0, 0), (200, 0)),
        circulo(10, 4, 2.0),
        linha((8, 2), (8, 0), (12, 0)),
    ]
    (grupo,) = agrupar_candidatos(primitivas, [])
    assert grupo.indices_primitivas == (1, 2)


def test_traco_com_um_arco_reconhecido_e_outra_curva_livre_entra_pelos_caminhos() -> None:
    arco = Arco((0, 0), 4.0, 0.0, 90.0, E, (0,))
    so_arco = Caminho(((quarto(0, 0, 4.0, 0),),), E, "traco", 0)
    assert agrupar_candidatos([arco], [so_arco]) == agrupar_candidatos([arco], [])
    com_curva = Caminho(((quarto(0, 0, 4.0, 0), bezier((30, 0), (36, 0))),), E, "traco", 0)
    grupos = agrupar_candidatos([arco], [com_curva])
    assert [g.indices_caminhos for g in grupos] == [(0,)]


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


def test_dois_circulos_a_exatamente_duas_folgas_agrupam() -> None:
    # caixas [0,4] e [7,11]: distancia 3 == 2 * folga
    grupos = agrupar_candidatos([circulo(2, 2), circulo(9, 2)], [], folga=1.5)
    assert [g.indices_primitivas for g in grupos] == [(0, 1)]


def test_dois_circulos_logo_alem_de_duas_folgas_nao_agrupam() -> None:
    grupos = agrupar_candidatos([circulo(2, 2), circulo(9.01, 2)], [], folga=1.5)
    assert [g.indices_primitivas for g in grupos] == [(0,), (1,)]


def test_agrupamento_atravessa_fronteira_de_celula_da_grade() -> None:
    grupos = agrupar_candidatos([circulo(8, 2), circulo(15, 2)], [], folga=1.5)
    assert [g.indices_primitivas for g in grupos] == [(0, 1)]


def test_grupo_com_lado_exatamente_lado_maximo_e_mantido() -> None:
    primitivas = [circulo(2, 2), circulo(38, 2)]  # caixas 0..4 e 36..40
    grupos = agrupar_candidatos(primitivas, [], folga=20.0, lado_maximo=40.0)
    assert len(grupos) == 1 and grupos[0].bbox == (0, 0, 40, 4)


def test_grupo_com_lado_logo_acima_de_lado_maximo_e_descartado() -> None:
    primitivas = [circulo(2, 2), circulo(38.5, 2)]
    assert agrupar_candidatos(primitivas, [], folga=20.0, lado_maximo=40.0) == ()


def test_elemento_com_lado_exatamente_lado_maximo_participa_do_grupo() -> None:
    grupos = agrupar_candidatos([linha((0, 0), (40, 0), (40, 3))], [], lado_maximo=40.0)
    assert [g.indices_primitivas for g in grupos] == [(0,)]


def test_cadeia_de_elementos_que_se_tocam_em_fila_vira_um_grupo_unico() -> None:
    cadeia = [circulo(i * 5.0, 0, 2.0) for i in range(6)]  # largura 29, vizinhos se tocam
    grupos = agrupar_candidatos(cadeia, [])
    assert [g.indices_primitivas for g in grupos] == [(0, 1, 2, 3, 4, 5)]


def test_cadeia_que_se_toca_mas_passa_de_lado_maximo_e_descartada_inteira() -> None:
    cadeia = [circulo(i * 5.0, 0, 2.0) for i in range(12)]  # largura 59
    assert agrupar_candidatos(cadeia, []) == ()


def test_elemento_grande_isolado_nao_gera_grupo() -> None:
    assert agrupar_candidatos([linha((0, 0), (50, 0), (50, 1))], []) == ()
    grande = Caminho(((ItemCaminho("l", ((0, 0), (0, 80))),),), E, "preenchimento", 0)
    assert agrupar_candidatos([], [grande]) == ()


def test_elemento_grande_nao_une_dois_simbolos_vizinhos() -> None:
    primitivas: list[Polilinha | Circulo | Arco] = [
        circulo(5, 5),
        circulo(60, 5),
        linha((0, 0), (100, 0)),
    ]
    grupos = agrupar_candidatos(primitivas, [])
    assert [g.indices_primitivas for g in grupos] == [(0,), (1,)]


def test_circulo_inteiro_traco_e_preenchimento_nao_duplica() -> None:
    itens = tuple(quarto(2, 2, 2.0, k) for k in range(4))
    caminho = Caminho((itens,), E, "traco_e_preenchimento", 0)
    (grupo,) = agrupar_candidatos([circulo(2, 2)], [caminho])
    assert grupo.indices_caminhos == ()


def test_circulo_cuja_origem_nao_inclui_o_caminho_nao_cobre_o_caminho() -> None:
    caminho = Caminho((tuple(quarto(2, 2, 2.0, k) for k in range(4)),), E, "preenchimento", 0)
    (grupo,) = agrupar_candidatos([circulo(2, 2, origem=7)], [caminho])
    assert grupo.indices_caminhos == (0,)


def test_circulo_de_mesma_origem_mas_geometria_diferente_nao_cobre_o_caminho() -> None:
    caminho = Caminho((tuple(quarto(2, 2, 2.0, k) for k in range(4)),), E, "preenchimento", 0)
    grupos = agrupar_candidatos([circulo(50, 50, 9.0)], [caminho])
    assert [(g.indices_primitivas, g.indices_caminhos) for g in grupos] == [((0,), ()), ((), (0,))]


def test_preenchido_com_arco_parcial_de_curvas_nao_e_tratado_como_circulo() -> None:
    caminho = Caminho(((quarto(0, 0, 4.0, 0), quarto(0, 0, 4.0, 1)),), E, "preenchimento", 0)
    arco = Arco((0, 0), 4.0, 0.0, 180.0, E, (0,))
    grupos = agrupar_candidatos([arco], [caminho])
    assert [g.indices_caminhos for g in grupos] == [(0,)]


def test_traco_com_curva_coberta_por_arco_de_outra_origem_entra() -> None:
    arco = Arco((0, 0), 4.0, 0.0, 90.0, E, (5,))
    caminho = Caminho(((quarto(0, 0, 4.0, 0),),), E, "traco", 0)
    grupos = agrupar_candidatos([arco], [caminho])
    assert [g.indices_caminhos for g in grupos] == [(0,)]


def test_polilinha_fechada_ou_com_tres_pontos_isolada_gera_grupo() -> None:
    fechada = Polilinha(((0, 0), (5, 0)), True, E, (0,))
    tres = linha((0, 0), (5, 0), (5, 5))
    assert len(agrupar_candidatos([fechada], [])) == 1
    assert len(agrupar_candidatos([tres], [])) == 1


def test_polilinha_de_dois_pontos_junto_de_circulo_nao_e_descartada() -> None:
    grupos = agrupar_candidatos([linha((4, 2), (8, 2)), circulo(2, 2)], [])
    assert [g.indices_primitivas for g in grupos] == [(0, 1)]


def test_entradas_vazias_nao_geram_grupos() -> None:
    assert agrupar_candidatos([], []) == ()
    assert agrupar_candidatos([], [Caminho((), E, "preenchimento", 0)]) == ()


def test_ordem_dos_grupos_e_deterministica_por_primeiro_indice() -> None:
    primitivas = [circulo(100, 0), circulo(0, 0), circulo(3, 0), circulo(50, 50)]
    caminhos = [poligono((200, 0), (206, 0), (203, 5)), poligono((52, 50), (58, 50), (55, 55))]
    grupos = agrupar_candidatos(primitivas, caminhos)
    assert [(g.indices_primitivas, g.indices_caminhos) for g in grupos] == [
        ((0,), ()),
        ((1, 2), ()),
        ((3,), (1,)),
        ((), (0,)),
    ]
    assert agrupar_candidatos(primitivas, caminhos) == grupos


def test_caminho_e_primitiva_agrupam_juntos_com_indices_em_cada_campo() -> None:
    grupos = agrupar_candidatos([circulo(8, 3)], [poligono((0, 0), (6, 0), (3, 5))])
    assert [(g.indices_primitivas, g.indices_caminhos) for g in grupos] == [((0,), (0,))]
    assert grupos[0].bbox == (0, 0, 10, 5)


def test_caminho_grande_encostado_fica_fora_e_grupos_de_so_caminhos_ordenam_por_indice() -> None:
    grande = Caminho(((ItemCaminho("l", ((0, 0), (100, 0))),),), E, "preenchimento", 0)
    caminhos = [poligono((60, 0), (66, 0), (63, 5)), grande, poligono((0, 1), (6, 1), (3, 6))]
    grupos = agrupar_candidatos([], caminhos)
    assert [(g.indices_primitivas, g.indices_caminhos) for g in grupos] == [((), (0,)), ((), (2,))]
