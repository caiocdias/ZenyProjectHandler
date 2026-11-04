"""Testes adversariais da geometria pura do modelo de desenho (limites, degenerados, escala)."""

from __future__ import annotations

import math
import time
from itertools import pairwise
from pathlib import Path
from typing import Literal

import pytest
from tests.unit.test_architecture import imported_root_names

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
E = Estilo("REDE", (0, 0, 0), None, 1.0, "")


def traco(
    *pontos: Ponto, ordem: int = 0, tipo: TipoCaminho = "traco", estilo: Estilo = E
) -> Caminho:
    itens = tuple(ItemCaminho("l", (a, b)) for a, b in pairwise(pontos))
    return Caminho((itens,), estilo, tipo, ordem)


def bezier_de_arco(cx: float, cy: float, r: float, inicio: float, varredura: float) -> ItemCaminho:
    """Bézier cúbica para um arco de `varredura` graus (com sinal) a partir de `inicio` graus."""
    a0 = math.radians(inicio)
    a1 = math.radians(inicio + varredura)
    k = 4.0 / 3.0 * math.tan(math.radians(varredura) / 4.0)
    p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
    p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
    c1 = (p0[0] - k * r * math.sin(a0), p0[1] + k * r * math.cos(a0))
    c2 = (p1[0] + k * r * math.sin(a1), p1[1] - k * r * math.cos(a1))
    return ItemCaminho("c", (p0, c1, c2, p1))


def arcos(
    centro: Ponto, r: float, inicio: float, pedacos: list[float], tipo: TipoCaminho = "traco"
) -> Caminho:
    itens: list[ItemCaminho] = []
    atual = inicio
    for p in pedacos:
        itens.append(bezier_de_arco(centro[0], centro[1], r, atual, p))
        atual += p
    return Caminho((tuple(itens),), E, tipo, 0)


# ---------- polilinhas: tolerância de ponto ----------


def test_lacuna_exatamente_na_tolerancia_de_ponto_funde() -> None:
    (p,) = reconstruir_polilinhas([traco((0, 0), (10, 0)), traco((10.5, 0), (20, 0), ordem=1)])
    assert p.pontos == ((0, 0), (20, 0))


def test_lacuna_logo_acima_da_tolerancia_de_ponto_nao_funde() -> None:
    polilinhas = reconstruir_polilinhas(
        [traco((0, 0), (10, 0)), traco((10.51, 0), (20, 0), ordem=1)]
    )
    assert len(polilinhas) == 2


def test_lacuna_diagonal_dentro_da_tolerancia_funde() -> None:
    # distância euclidiana ~0,42 (0,3; 0,3), em célula diferente da grade
    (p,) = reconstruir_polilinhas([traco((0, 0), (10, 0)), traco((10.3, 0.3), (20, 0), ordem=1)])
    assert len(p.pontos) >= 2
    assert p.origens == (0, 1)


def test_tolerancia_de_ponto_customizada_e_respeitada() -> None:
    caminhos = [traco((0, 0), (10, 0)), traco((12, 0), (20, 0), ordem=1)]
    assert len(reconstruir_polilinhas(caminhos)) == 2
    assert len(reconstruir_polilinhas(caminhos, tolerancia_ponto=2.0)) == 1


def test_pontos_com_coordenadas_negativas_fundem() -> None:
    caminhos = [traco((-10, -5), (-0.2, -5)), traco((0.1, -5), (10, -5), ordem=1)]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.pontos == ((-10, -5), (10, -5))


# ---------- polilinhas: tolerância de ângulo ----------


def _dobra(graus: float) -> list[Caminho]:
    rad = math.radians(graus)
    meio = (10.0, 0.0)
    fim = (10 + 10 * math.cos(rad), 10 * math.sin(rad))
    return [traco((0, 0), meio), traco(meio, fim, ordem=1)]


def test_desvio_angular_abaixo_do_limite_funde_em_reta() -> None:
    (p,) = reconstruir_polilinhas(_dobra(0.9))
    assert len(p.pontos) == 2


def test_desvio_angular_logo_acima_do_limite_mantem_vertice() -> None:
    (p,) = reconstruir_polilinhas(_dobra(1.1))
    assert len(p.pontos) == 3


def test_desvio_angular_exatamente_no_limite_funde() -> None:
    (p,) = reconstruir_polilinhas(_dobra(45.0), tolerancia_angulo_graus=45.0)
    assert len(p.pontos) == 2


def test_inversao_de_sentido_nao_e_colinear() -> None:
    (p,) = reconstruir_polilinhas([traco((0, 0), (10, 0)), traco((10, 0), (5, 0), ordem=1)])
    assert len(p.pontos) == 3


def test_curva_suave_nao_colapsa_em_corda_unica() -> None:
    # Quarto de circunferência r=100 em 30 segmentos (3 graus cada): o desvio por vértice
    # (3 graus) passa de 1 grau, então todos os vértices precisam ser preservados.
    pts = [
        (100 * math.cos(math.radians(3 * i)), 100 * math.sin(math.radians(3 * i)))
        for i in range(31)
    ]
    (p,) = reconstruir_polilinhas([traco(*pts)])
    assert len(p.pontos) == 31


# ---------- polilinhas: direção, degenerados, fechada ----------


def test_segmentos_em_sentidos_opostos_encadeiam() -> None:
    caminhos = [traco((0, 0), (10, 0)), traco((20, 0), (10, 0), ordem=1)]
    (p,) = reconstruir_polilinhas(caminhos)
    assert {p.pontos[0], p.pontos[-1]} == {(0, 0), (20, 0)}
    assert p.origens == (0, 1)


def test_encadeamento_na_ordem_inversa_de_pintura() -> None:
    caminhos = [
        traco((20, 0), (30, 0), ordem=0),
        traco((10, 0), (20, 0), ordem=1),
        traco((0, 0), (10, 0), ordem=2),
    ]
    (p,) = reconstruir_polilinhas(caminhos)
    assert {p.pontos[0], p.pontos[-1]} == {(0, 0), (30, 0)}
    assert len(p.pontos) == 2
    assert p.origens == (0, 1, 2)


def test_segmento_de_comprimento_zero_e_ignorado_sem_erro() -> None:
    assert reconstruir_polilinhas([traco((5, 5), (5, 5))]) == ()


def test_segmento_degenerado_no_meio_nao_quebra_a_cadeia() -> None:
    caminhos = [
        traco((0, 0), (10, 0)),
        traco((10, 0), (10, 0), ordem=1),
        traco((10, 0), (20, 0), ordem=2),
    ]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.pontos == ((0, 0), (20, 0))


def test_segmento_mais_curto_que_a_tolerancia_nao_quebra_a_cadeia() -> None:
    caminhos = [
        traco((0, 0), (10, 0)),
        traco((10, 0), (10.2, 0), ordem=1),
        traco((10.2, 0), (20, 0), ordem=2),
    ]
    (p,) = reconstruir_polilinhas(caminhos)
    assert len(p.pontos) == 2


def test_sem_caminhos_devolve_vazio() -> None:
    assert reconstruir_polilinhas([]) == ()


def test_polilinha_fechada_em_um_unico_caminho_multissegmento_tem_origem_unica() -> None:
    (p,) = reconstruir_polilinhas([traco((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))])
    assert p.fechada
    assert p.origens == (0,)
    assert len(p.pontos) == 4


def test_polilinha_fechada_sem_repetir_o_ponto_inicial() -> None:
    (p,) = reconstruir_polilinhas([traco((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))])
    assert p.pontos.count(p.pontos[0]) == 1


def test_triangulo_fechado_por_tres_caminhos() -> None:
    caminhos = [
        traco((0, 0), (10, 0)),
        traco((10, 0), (5, 8), ordem=1),
        traco((5, 8), (0.1, 0.1), ordem=2),
    ]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.fechada
    assert len(p.pontos) == 3
    assert p.origens == (0, 1, 2)


def test_quadrado_com_vertice_colinear_extra_perde_o_vertice() -> None:
    (p,) = reconstruir_polilinhas([traco((0, 0), (5, 0), (10, 0), (10, 10), (0, 10), (0, 0))])
    assert p.fechada
    assert len(p.pontos) == 4


def test_segmento_duplicado_nao_vira_polilinha_fechada_de_dois_pontos() -> None:
    # BUG DOCUMENTADO (vermelho): o mesmo segmento pintado duas vezes forma um "ciclo" de 2 nos
    # e sai como Polilinha(fechada=True) com 2 pontos, forma degenerada sem area.
    polilinhas = reconstruir_polilinhas([traco((0, 0), (10, 0)), traco((0, 0), (10, 0), ordem=1)])
    assert not any(p.fechada and len(p.pontos) < 3 for p in polilinhas)


def test_juncao_em_t_gera_tres_polilinhas_sem_perder_origens() -> None:
    caminhos = [
        traco((0, 0), (10, 0)),
        traco((10, 0), (20, 0), ordem=1),
        traco((10, 0), (10, 10), ordem=2),
    ]
    polilinhas = reconstruir_polilinhas(caminhos)
    assert len(polilinhas) == 3
    assert sorted(o for p in polilinhas for o in p.origens) == [0, 1, 2]


def test_origens_sao_indices_na_sequencia_e_nao_a_ordem_de_pintura() -> None:
    caminhos = [traco((0, 0), (10, 0), ordem=7), traco((10, 0), (20, 0), ordem=3)]
    (p,) = reconstruir_polilinhas(caminhos)
    assert p.origens == (0, 1)


def test_origens_ignoram_caminhos_de_outro_estilo_e_de_preenchimento() -> None:
    outro = Estilo("OUTRA", (0, 0, 0), None, 1.0, "")
    caminhos = [
        traco((0, 0), (10, 0), tipo="preenchimento"),
        traco((0, 0), (10, 0), ordem=1, estilo=outro),
        traco((0, 0), (10, 0), ordem=2),
    ]
    polilinhas = reconstruir_polilinhas(caminhos)
    assert {p.estilo: p.origens for p in polilinhas} == {E: (2,), outro: (1,)}


def test_traco_e_preenchimento_nao_entra_na_fusao() -> None:
    assert reconstruir_polilinhas([traco((0, 0), (10, 0), tipo="traco_e_preenchimento")]) == ()


def test_beziers_nao_entram_na_fusao_de_polilinhas() -> None:
    caminho = Caminho(((bezier_de_arco(0, 0, 5, 0, 90),),), E, "traco", 0)
    assert reconstruir_polilinhas([caminho]) == ()


def test_caminho_com_varios_subcaminhos_nao_os_liga_sem_toque() -> None:
    caminho = Caminho(
        (
            (ItemCaminho("l", ((0, 0), (10, 0))),),
            (ItemCaminho("l", ((50, 50), (60, 50))),),
        ),
        E,
        "traco",
        0,
    )
    polilinhas = reconstruir_polilinhas([caminho])
    assert len(polilinhas) == 2
    assert all(p.origens == (0,) for p in polilinhas)


def test_fusao_de_cadeia_unica_com_ziguezague_seguido_de_reta_escala_linearmente() -> None:
    # BUG DOCUMENTADO (vermelho): _remover_colineares reinicia a varredura do inicio a cada
    # vertice removido; com muitos vertices colineares apos um trecho nao colinear, o custo e
    # quadratico (4k -> 8k vertices: razao ~4), contra o requisito "nada quadratico".
    def cadeia(n: int) -> list[Caminho]:
        pontos: list[Ponto] = [(float(i), float(i % 2) * 5) for i in range(n // 2)]
        ultimo_x = pontos[-1][0]
        pontos += [(ultimo_x + 1 + i, pontos[-1][1]) for i in range(n // 2)]
        return [traco(*pontos)]

    def melhor(caminhos: list[Caminho]) -> float:
        tempos = []
        for _ in range(2):
            inicio = time.perf_counter()
            reconstruir_polilinhas(caminhos)
            tempos.append(time.perf_counter() - inicio)
        return min(tempos)

    pequeno, grande = cadeia(4_000), cadeia(8_000)
    assert melhor(grande) / max(melhor(pequeno), 1e-6) < 3


# ---------- círculos e arcos ----------


def test_arcos_desiguais_que_somam_360_viram_circulo() -> None:
    caminho = arcos((50, 50), 5, 10, [30, 60, 90, 90, 90])
    (c,) = recuperar_circulos_e_arcos([caminho])
    assert isinstance(c, Circulo)
    assert c.raio == pytest.approx(5, rel=1e-3)
    assert c.centro == pytest.approx((50, 50), abs=1e-3)


def test_arcos_que_somam_menos_de_360_viram_um_arco_unico() -> None:
    (a,) = recuperar_circulos_e_arcos([arcos((0, 0), 10, 20, [30, 60, 90])])
    assert isinstance(a, Arco)
    assert a.angulo_inicial == pytest.approx(20, abs=0.1)
    assert a.angulo_final == pytest.approx(200, abs=0.1)


def test_arco_que_cruza_zero_grau_mantem_final_maior_que_inicial() -> None:
    (a,) = recuperar_circulos_e_arcos([arcos((0, 0), 10, 330, [45, 45])])
    assert isinstance(a, Arco)
    assert a.angulo_final > a.angulo_inicial
    assert a.angulo_final - a.angulo_inicial == pytest.approx(90, abs=0.1)
    assert a.angulo_inicial % 360 == pytest.approx(330, abs=0.1)


def test_arco_anti_horario_normaliza_para_final_maior_que_inicial() -> None:
    (a,) = recuperar_circulos_e_arcos([arcos((0, 0), 10, 90, [-45, -45])])
    assert isinstance(a, Arco)
    assert a.angulo_final - a.angulo_inicial == pytest.approx(90, abs=0.1)
    assert a.angulo_inicial % 360 == pytest.approx(0, abs=0.1) or a.angulo_inicial % 360 == (
        pytest.approx(360, abs=0.1)
    )


def test_arco_de_350_graus_nao_vira_circulo() -> None:
    (a,) = recuperar_circulos_e_arcos([arcos((0, 0), 10, 0, [90, 90, 90, 80])])
    assert isinstance(a, Arco)
    assert a.angulo_final - a.angulo_inicial == pytest.approx(350, abs=0.1)


def test_circulo_comecando_em_angulo_arbitrario() -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((7, -3), 2, 123, [90, 90, 90, 90])])
    assert isinstance(c, Circulo)
    assert c.centro == pytest.approx((7, -3), abs=1e-3)


def test_circulo_anti_horario_tambem_e_reconhecido() -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((0, 0), 4, 0, [-90, -90, -90, -90])])
    assert isinstance(c, Circulo)


@pytest.mark.parametrize("raio", [0.01, 0.001])
def test_circulo_de_raio_minusculo_longe_da_origem(raio: float) -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((500, 700), raio, 0, [90, 90, 90, 90])])
    assert isinstance(c, Circulo)
    assert c.raio == pytest.approx(raio, rel=1e-2)
    assert c.centro == pytest.approx((500, 700), abs=raio * 0.05)


def test_circulo_de_raio_minusculo_perto_da_origem() -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((0, 0), 1e-4, 0, [90, 90, 90, 90])])
    assert isinstance(c, Circulo)


def test_circulo_grande() -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((0, 0), 1e5, 0, [90, 90, 90, 90])])
    assert isinstance(c, Circulo)
    assert c.raio == pytest.approx(1e5, rel=1e-3)


def test_bezier_com_todos_os_pontos_iguais_nao_gera_nada_nem_erro() -> None:
    p = (3.0, 3.0)
    caminho = Caminho(((ItemCaminho("c", (p, p, p, p)),),), E, "traco", 0)
    assert recuperar_circulos_e_arcos([caminho]) == ()


def test_bezier_colinear_nao_vira_arco() -> None:
    item = ItemCaminho("c", ((0, 0), (1, 0), (2, 0), (3, 0)))
    assert recuperar_circulos_e_arcos([Caminho(((item,),), E, "traco", 0)]) == ()


def test_bezier_de_laco_com_extremos_coincidentes_nao_vira_circulo_nem_levanta() -> None:
    item = ItemCaminho("c", ((0, 0), (10, 10), (-10, 10), (0, 0)))
    resultado = recuperar_circulos_e_arcos([Caminho(((item,),), E, "traco", 0)])
    assert all(not isinstance(r, Circulo) for r in resultado)


def test_bezier_com_coordenadas_nao_finitas_nao_levanta() -> None:
    item = ItemCaminho("c", ((0, 0), (math.inf, 0), (1, 1), (2, 0)))
    assert recuperar_circulos_e_arcos([Caminho(((item,),), E, "traco", 0)]) == ()


def test_sem_caminhos_nao_ha_circulos() -> None:
    assert recuperar_circulos_e_arcos([]) == ()


def test_segmentos_l_sozinhos_nao_geram_arcos() -> None:
    assert recuperar_circulos_e_arcos([traco((0, 0), (10, 0), (10, 10))]) == ()


def test_arcos_de_raios_diferentes_nao_se_unem() -> None:
    a = bezier_de_arco(0, 0, 10, 0, 90)
    b = bezier_de_arco(0, 0, 14, 90, 90)
    resultado = recuperar_circulos_e_arcos([Caminho(((a, b),), E, "traco", 0)])
    assert len(resultado) == 2
    assert all(isinstance(r, Arco) for r in resultado)


def test_arcos_de_centros_diferentes_nao_se_unem() -> None:
    a = bezier_de_arco(0, 0, 10, 0, 90)
    b = bezier_de_arco(5, 5, 10, 90, 90)
    resultado = recuperar_circulos_e_arcos([Caminho(((a, b),), E, "traco", 0)])
    assert len(resultado) == 2


def test_arcos_nao_contiguos_do_mesmo_circulo_nao_se_unem() -> None:
    a = bezier_de_arco(0, 0, 10, 0, 90)
    b = bezier_de_arco(0, 0, 10, 180, 90)
    resultado = recuperar_circulos_e_arcos([Caminho(((a, b),), E, "traco", 0)])
    assert len(resultado) == 2


def test_arcos_em_subcaminhos_distintos_nao_se_unem() -> None:
    a = bezier_de_arco(0, 0, 10, 0, 90)
    b = bezier_de_arco(0, 0, 10, 90, 90)
    resultado = recuperar_circulos_e_arcos([Caminho(((a,), (b,)), E, "traco", 0)])
    assert len(resultado) == 2


def test_segmento_reto_entre_arcos_separa_os_grupos() -> None:
    a = bezier_de_arco(0, 0, 10, 0, 90)
    reta = ItemCaminho("l", (a.pontos[3], (0, 10)))
    b = bezier_de_arco(0, 0, 10, 90, 90)
    resultado = recuperar_circulos_e_arcos([Caminho(((a, reta, b),), E, "traco", 0)])
    assert len(resultado) == 2


def test_origens_de_circulos_apontam_para_o_indice_correto() -> None:
    lixo = traco((0, 0), (1, 1))
    c1 = arcos((10, 10), 3, 0, [90] * 4)
    c2 = arcos((30, 30), 3, 0, [90] * 4, tipo="preenchimento")
    resultado = recuperar_circulos_e_arcos([lixo, c1, c2])
    assert [r.origens for r in resultado] == [(1,), (2,)]
    assert resultado[0].centro == pytest.approx((10, 10), abs=1e-3)
    assert resultado[1].centro == pytest.approx((30, 30), abs=1e-3)


def test_traco_e_preenchimento_tambem_recupera_circulo() -> None:
    caminho = arcos((1, 1), 2, 0, [90] * 4, tipo="traco_e_preenchimento")
    (c,) = recuperar_circulos_e_arcos([caminho])
    assert isinstance(c, Circulo)


def test_estilo_do_caminho_e_propagado_ao_circulo() -> None:
    (c,) = recuperar_circulos_e_arcos([arcos((1, 1), 2, 0, [90] * 4)])
    assert c.estilo == E


def test_tolerancia_relativa_zero_rejeita_bezier_aproximada() -> None:
    # A Bézier de 90 graus com kappa padrão desvia ~0,03% do raio: passa a 2%, falha a 0.
    caminho = arcos((0, 0), 10, 0, [90])
    assert len(recuperar_circulos_e_arcos([caminho])) == 1
    assert recuperar_circulos_e_arcos([caminho], tolerancia_relativa=0.0) == ()


def test_deformacao_acima_da_tolerancia_nao_e_arco() -> None:
    item = bezier_de_arco(0, 0, 10, 0, 90)
    p0, c1, c2, p1 = item.pontos
    c1b = (c1[0] * 1.5, c1[1] * 1.5)
    c2b = (c2[0] * 1.5, c2[1] * 1.5)
    deformado = ItemCaminho("c", (p0, c1b, c2b, p1))
    assert recuperar_circulos_e_arcos([Caminho(((deformado,),), E, "traco", 0)]) == ()


# ---------- guardas de import ----------


def test_imported_root_names_detecta_import_proibido_sintetico(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.py"
    arquivo.write_text(
        "import ezdxf.entities\nfrom pymupdf import Document\n"
        "def f():\n    import onnxruntime as ort\n    return ort\n",
        encoding="utf-8",
    )
    assert imported_root_names(arquivo) >= {"ezdxf", "pymupdf", "onnxruntime"}


def test_imported_root_names_nao_acusa_nome_apenas_citado(tmp_path: Path) -> None:
    arquivo = tmp_path / "y.py"
    arquivo.write_text(
        '"""usa ezdxf no texto"""\nx = "import ezdxf"\n# import fitz\n', encoding="utf-8"
    )
    assert imported_root_names(arquivo) == set()


# ---------- remoção de colineares: fidelidade à curva original ----------


def _distancia_ao_segmento(p: Ponto, a: Ponto, b: Ponto) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    comprimento2 = dx * dx + dy * dy
    t = 0.0
    if comprimento2:
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / comprimento2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _afastamento_maximo(
    originais: list[Ponto], polilinha: tuple[Ponto, ...], fechada: bool
) -> float:
    vertices = list(polilinha) + ([polilinha[0]] if fechada else [])
    return max(
        min(_distancia_ao_segmento(p, a, b) for a, b in pairwise(vertices)) for p in originais
    )


@pytest.mark.parametrize(
    ("raio", "passo", "varredura"),
    [(100, 0.5, 90), (1000, 0.3, 90), (1000, 0.9, 180)],
)
def test_arco_suave_com_desvio_menor_que_um_grau_por_passo_fica_fiel_a_curva(
    raio: float, passo: float, varredura: float
) -> None:
    # Criterio: todo vertice original fica a no maximo 0,25 pt da polilinha resultante, metade
    # da tolerancia de ponto padrao (0,5 pt), que e a escala em que o modulo trata pontos como
    # iguais. Raios de ate 1000 pt cobrem uma folha de projeto inteira.
    n = int(varredura / passo)
    pts = [
        (raio * math.cos(math.radians(passo * i)), raio * math.sin(math.radians(passo * i)))
        for i in range(n + 1)
    ]
    (p,) = reconstruir_polilinhas([traco(*pts)])
    assert p.pontos[0] == pts[0]
    assert p.pontos[-1] == pts[-1]
    assert len(p.pontos) < len(pts)
    assert _afastamento_maximo(pts, p.pontos, p.fechada) <= 0.25


def test_circulo_poligonal_fechado_de_passo_suave_fica_fiel_e_fechado() -> None:
    n = 400
    pts = [
        (100 * math.cos(2 * math.pi * i / n), 100 * math.sin(2 * math.pi * i / n))
        for i in range(n + 1)
    ]
    (p,) = reconstruir_polilinhas([traco(*pts)])
    assert p.fechada
    assert len(p.pontos) >= 8
    assert _afastamento_maximo(pts, p.pontos, True) <= 0.25


def test_remocao_de_colineares_preserva_ordem_dos_vertices_mantidos() -> None:
    pts = [(float(i), 0.0) for i in range(50)] + [(49.0, float(i)) for i in range(1, 50)]
    (p,) = reconstruir_polilinhas([traco(*pts)])
    assert p.pontos == ((0, 0), (49, 0), (49, 49))
