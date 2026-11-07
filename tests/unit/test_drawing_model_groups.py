# mypy: disable-error-code="no-untyped-call"
"""Grupos candidatos a símbolo."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model import groups
from zeny_project_handler.adapters.analysis.drawing_model.geometry import (
    recuperar_circulos_e_arcos,
)
from zeny_project_handler.adapters.analysis.drawing_model.groups import (
    AgrupamentoExcedido,
    agrupar_candidatos,
)
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


def _comparacoes(n: int, monkeypatch: pytest.MonkeyPatch) -> int:
    """Conta os pares de caixas comparados no agrupamento de `n` círculos."""
    primitivas = [circulo((i % 100) * 5.0, (i // 100) * 5.0, 2.0) for i in range(n)]
    comparacoes = 0
    original = groups._caixas_se_encostam

    def contando(*args: Any) -> bool:
        nonlocal comparacoes
        comparacoes += 1
        return bool(original(*args))

    with monkeypatch.context() as contexto:
        contexto.setattr(groups, "_caixas_se_encostam", contando)
        agrupar_candidatos(primitivas, [])
    return comparacoes


def test_agrupamento_escala_linearmente(monkeypatch: pytest.MonkeyPatch) -> None:
    # a grade espacial limita as comparações por elemento: dobrar a entrada não passa de 3x
    pequeno, grande = _comparacoes(10_000, monkeypatch), _comparacoes(20_000, monkeypatch)
    assert pequeno > 0
    assert grande / pequeno < 3


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


def _uniao_anterior(caixas: list[Any], folga: float) -> list[int]:
    """Cópia da união de antes do teto: compara cada item com tudo o que está nas suas células."""
    lado_celula = 10.0
    pai = list(range(len(caixas)))

    def raiz(i: int) -> int:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    celulas: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, (x0, y0, x1, y1) in enumerate(caixas):
        faixa_x = range(
            math.floor((x0 - folga) / lado_celula), math.floor((x1 + folga) / lado_celula) + 1
        )
        faixa_y = range(
            math.floor((y0 - folga) / lado_celula), math.floor((y1 + folga) / lado_celula) + 1
        )
        vizinhos: set[int] = set()
        for cx in faixa_x:
            for cy in faixa_y:
                celula = celulas[(cx, cy)]
                vizinhos.update(celula)
                celula.append(i)
        for j in vizinhos:
            if groups._caixas_se_encostam(caixas[i], caixas[j], 2 * folga):
                pai[raiz(i)] = raiz(j)
    return [raiz(i) for i in range(len(caixas))]


def _mantidos_e_descartados(
    primitivas: list[Circulo],
) -> tuple[set[tuple[int, ...]], set[tuple[int, ...]]]:
    """A saída pela união de antes do teto: os grupos que cabem no lado máximo e os que não."""
    caixas = [groups._caixa_primitiva(p) for p in primitivas]
    por_raiz: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(_uniao_anterior(caixas, 1.5)):
        por_raiz[r].append(i)
    mantidos: set[tuple[int, ...]] = set()
    descartados: set[tuple[int, ...]] = set()
    for membros in por_raiz.values():
        caixa = (
            min(caixas[i][0] for i in membros),
            min(caixas[i][1] for i in membros),
            max(caixas[i][2] for i in membros),
            max(caixas[i][3] for i in membros),
        )
        (mantidos if groups._lado(caixa) <= 40.0 else descartados).add(tuple(membros))
    return mantidos, descartados


def test_saida_igual_a_uniao_anterior() -> None:
    """200 sementes com 60 círculos em 60x60: densos o bastante para unir em toda semente e, em
    parte delas, formar cadeia que passa do lado máximo e é descartada."""
    sementes_com_descarte = 0
    for semente in range(200):
        sorteio = random.Random(semente)
        primitivas = [
            circulo(sorteio.uniform(0, 60), sorteio.uniform(0, 60), sorteio.uniform(0.5, 3.0), i)
            for i in range(60)
        ]
        esperado, descartados = _mantidos_e_descartados(primitivas)
        obtido = {g.indices_primitivas for g in agrupar_candidatos(primitivas, [])}
        assert obtido == esperado, f"semente {semente}"
        assert any(len(m) > 1 for m in esperado), f"semente {semente}"
        sementes_com_descarte += bool(descartados)
    assert sementes_com_descarte > 0


def test_saida_igual_a_uniao_anterior_com_200_circulos() -> None:
    sorteio = random.Random(20261106)
    primitivas = [
        circulo(sorteio.uniform(0, 100), sorteio.uniform(0, 100), sorteio.uniform(0.5, 3.0), i)
        for i in range(200)
    ]
    esperado, _ = _mantidos_e_descartados(primitivas)
    obtido = {g.indices_primitivas for g in agrupar_candidatos(primitivas, [])}
    assert obtido == esperado
    assert any(len(m) > 1 for m in esperado)


def _concentricos(n: int) -> list[Circulo]:
    return [circulo(0, 0, 2.0 + i * 1e-4, i) for i in range(n)]


def _visitas(primitivas: list[Circulo]) -> int:
    """Menor `limite_visitas` com que o agrupamento passa: o número de visitas feitas."""
    baixo, alto = 0, 1
    while True:
        try:
            agrupar_candidatos(primitivas, [], limite_visitas=alto)
            break
        except AgrupamentoExcedido:
            baixo, alto = alto, alto * 2
    while alto - baixo > 1:
        meio = (baixo + alto) // 2
        try:
            agrupar_candidatos(primitivas, [], limite_visitas=meio)
            alto = meio
        except AgrupamentoExcedido:
            baixo = meio
    return alto


def test_teto_de_visitas_levanta() -> None:
    densa = _concentricos(30)
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos(densa, [], limite_visitas=10)
    exato = _visitas(densa)
    assert exato > 10
    assert len(agrupar_candidatos(densa, [], limite_visitas=exato)) == 1
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos(densa, [], limite_visitas=exato - 1)


def test_visita_nao_multiplica_em_caixas_distantes() -> None:
    def espalhadas(n: int) -> list[Circulo]:
        return [circulo(i * 25.0, 0, 2.0, i) for i in range(n)]

    pequeno, grande = _visitas(espalhadas(500)), _visitas(espalhadas(1_000))
    assert pequeno > 0
    assert grande <= 2.5 * pequeno, (pequeno, grande)


def test_pagina_densa_vira_grupos_falhou(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "densa.pdf"
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        for i in range(12):
            pagina.draw_circle((100, 100), 5 + i * 0.01, color=(0, 0, 0))
        documento.save(pdf)
    normal = pymupdf_drawing_model.extrair_modelo_desenho(pdf).paginas[0]
    assert normal.grupos
    original = agrupar_candidatos
    monkeypatch.setattr(
        pymupdf_drawing_model,
        "agrupar_candidatos",
        lambda primitivas, caminhos: original(primitivas, caminhos, limite_visitas=5),
    )
    modelo = pymupdf_drawing_model.extrair_modelo_desenho(pdf).paginas[0]
    assert modelo.grupos == ()
    assert "modelo.grupos_falhou" in modelo.diagnosticos
    assert modelo.caminhos == normal.caminhos
    assert modelo.primitivas == normal.primitivas


def _particao(caixas: list[Any], raizes: list[int]) -> set[tuple[int, ...]]:
    por_raiz: dict[int, list[int]] = defaultdict(list)
    for i in range(len(caixas)):
        por_raiz[raizes[i]].append(i)
    return {tuple(m) for m in por_raiz.values()}


@pytest.mark.parametrize(
    ("semente", "folga", "lado_max_caixa"),
    [(1, 0.5, 6.0), (2, 1.5, 30.0), (3, 4.0, 12.0), (4, 1.5, 80.0)],
    ids=["folga-pequena", "folga-padrao", "folga-grande", "caixas-largas-varias-celulas"],
)
def test_uniao_igual_a_anterior_com_caixas_arbitrarias_e_coordenadas_negativas(
    semente: int, folga: float, lado_max_caixa: float
) -> None:
    sorteio = random.Random(semente)
    caixas: list[Any] = []
    for _ in range(300):
        x, y = sorteio.uniform(-150, 150), sorteio.uniform(-150, 150)
        caixas.append((x, y, x + sorteio.uniform(0, lado_max_caixa), y + sorteio.uniform(0, 3)))
    esperado = _particao(caixas, _uniao_anterior(caixas, folga))
    obtido = _particao(
        caixas, groups._unir_proximos(caixas, list(range(len(caixas))), folga, 10**9)
    )
    assert obtido == esperado
    assert any(len(m) > 1 for m in esperado)


def test_visitas_contam_uma_por_entrada_de_celula_lida() -> None:
    # 30 circulos concentricos em (0, 0), raio ~2 e folga 1,5: cada caixa cobre 4 celulas
    # e a i-esima le i entradas em cada uma: 4 * (0 + 1 + ... + 29) = 1740.
    densa = _concentricos(30)
    assert len(agrupar_candidatos(densa, [], limite_visitas=1740)) == 1
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos(densa, [], limite_visitas=1739)


def test_teto_zero_passa_sem_celula_compartilhada_e_levanta_com_ela() -> None:
    assert agrupar_candidatos([circulo(0, 0), circulo(100, 100, origem=1)], [], limite_visitas=0)
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos([circulo(0, 0), circulo(1, 0, origem=1)], [], limite_visitas=0)


def test_teto_vale_para_caminhos_e_so_conta_elementos_ativos() -> None:
    caminhos = [
        poligono((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)),
        poligono((1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)),
    ]
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos([], caminhos, limite_visitas=0)
    # Elemento maior que lado_maximo nao e ativo: nao le celula alguma.
    grande = linha((0.0, 0.0), (500.0, 0.0), (500.0, 1.0))
    assert agrupar_candidatos([grande, circulo(0, 0)], [], limite_visitas=0)


def test_excecao_e_reproduzivel_e_nao_deixa_estado_entre_chamadas() -> None:
    densa = _concentricos(30)
    primeiro = agrupar_candidatos(densa, [])
    for _ in range(2):
        with pytest.raises(AgrupamentoExcedido):
            agrupar_candidatos(densa, [], limite_visitas=10)
    assert agrupar_candidatos(densa, []) == primeiro


def _traco_de_arcos_disjuntos(n: int) -> Caminho:
    subcaminhos = tuple((quarto(100.0 * i, 0.0, 4.0, 0),) for i in range(n))
    return Caminho(subcaminhos, E, "traco", 0)


def test_caminho_de_traco_com_muitos_arcos_disjuntos_tem_varredura_limitada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caminho = _traco_de_arcos_disjuntos(300)
    figuras = recuperar_circulos_e_arcos([caminho])
    assert len(figuras) == 300
    chamadas = 0
    original = groups._no_circulo

    def contando(figura: Circulo | Arco, ponto: Ponto) -> bool:
        nonlocal chamadas
        chamadas += 1
        return bool(original(figura, ponto))

    monkeypatch.setattr(groups, "_no_circulo", contando)
    with pytest.raises(AgrupamentoExcedido):
        agrupar_candidatos(figuras, [caminho], limite_visitas=1_000)
    assert chamadas <= 3 * 1_000 + 3


def test_caminho_de_traco_com_poucos_arcos_disjuntos_segue_sem_grupo_de_caminho() -> None:
    caminho = _traco_de_arcos_disjuntos(5)
    figuras = recuperar_circulos_e_arcos([caminho])
    grupos = agrupar_candidatos(figuras, [caminho])
    assert all(g.indices_caminhos == () for g in grupos)
    assert agrupar_candidatos(figuras, [caminho], limite_visitas=1_000) == grupos
