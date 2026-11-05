"""Ataques adicionais aos dados sintéticos e às métricas do spike E11 (Task 1)."""

from __future__ import annotations

import itertools
import math

import numpy
import pytest
from scripts.treino_detector.dados_sinteticos import (
    CLASSES,
    Anotacao,
    gerar_amostra,
    gerar_conjunto,
)
from scripts.treino_detector.metricas import (
    Deteccao,
    avaliar,
    deteccoes_equivalentes,
    iou,
    ladrilhos_por_folha,
    perdas_equivalentes,
    resumir_tempos,
)

CAIXA = (10.0, 10.0, 60.0, 60.0)


# ---------------------------------------------------------------- dados sintéticos


@pytest.mark.parametrize("semente", range(300))
def test_geometria_vale_para_muitas_sementes(semente: int) -> None:
    amostra = gerar_amostra(semente)
    assert 1 <= len(amostra.anotacoes) <= 4
    for anot in amostra.anotacoes:
        x0, y0, x1, y1 = anot.caixa
        assert 0 <= x0 < x1 <= 320
        assert 0 <= y0 < y1 <= 320
        assert 32 <= x1 - x0 <= 96
        assert 32 <= y1 - y0 <= 96
        assert 1 <= anot.rotulo <= len(CLASSES)
    assert all(iou(p.caixa, q.caixa) == 0 for p, q in itertools.combinations(amostra.anotacoes, 2))


def test_numero_de_simbolos_varia_e_respeita_max_simbolos() -> None:
    contagens = [len(gerar_amostra(s).anotacoes) for s in range(300)]
    assert set(contagens) == {1, 2, 3, 4}
    assert all(len(gerar_amostra(s, max_simbolos=1).anotacoes) == 1 for s in range(40))
    assert all(len(gerar_amostra(s, max_simbolos=2).anotacoes) <= 2 for s in range(40))


def test_lado_pequeno_mantem_caixas_dentro_e_sem_sobreposicao() -> None:
    for semente in range(60):
        amostra = gerar_amostra(semente, lado=100)
        assert amostra.imagem.shape == (100, 100, 3)
        assert len(amostra.anotacoes) >= 1
        for anot in amostra.anotacoes:
            x0, y0, x1, y1 = anot.caixa
            assert 0 <= x0 < x1 <= 100
            assert 0 <= y0 < y1 <= 100
            assert 32 <= x1 - x0 <= 96
        assert all(
            iou(p.caixa, q.caixa) == 0 for p, q in itertools.combinations(amostra.anotacoes, 2)
        )


def test_lado_minimo_32_ainda_gera_um_simbolo_que_cabe() -> None:
    amostra = gerar_amostra(1, lado=32)
    assert len(amostra.anotacoes) == 1
    assert amostra.anotacoes[0].caixa == (0.0, 0.0, 32.0, 32.0)


def test_caixas_sao_anotacoes_com_floats() -> None:
    for anot in gerar_amostra(11).anotacoes:
        assert isinstance(anot, Anotacao)
        assert all(isinstance(v, float) for v in anot.caixa)


@pytest.mark.parametrize("semente", range(40))
def test_tinta_escura_em_cada_caixa_e_fora_das_caixas_so_fundo_claro(semente: int) -> None:
    amostra = gerar_amostra(semente)
    mascara = numpy.zeros(amostra.imagem.shape[:2], dtype=bool)
    for anot in amostra.anotacoes:
        x0, y0, x1, y1 = (int(v) for v in anot.caixa)
        assert int(amostra.imagem[y0:y1, x0:x1].min()) < 80
        mascara[y0:y1, x0:x1] = True
    # o ruído de fundo é claro (> 120): nenhuma tinta escura fora das caixas anotadas
    assert int(amostra.imagem[~mascara].min()) > 120


def test_semente_derivada_nao_colide_entre_conjuntos() -> None:
    a = gerar_conjunto(1, 2)
    b = gerar_conjunto(2, 2)
    assert not numpy.array_equal(a[0].imagem, b[0].imagem)
    assert not numpy.array_equal(a[0].imagem, a[1].imagem)


def test_gerar_conjunto_vazio_e_deterministico() -> None:
    assert gerar_conjunto(1, 0) == []
    x, y = gerar_conjunto(9, 5), gerar_conjunto(9, 5)
    assert all(
        numpy.array_equal(p.imagem, q.imagem) and p.anotacoes == q.anotacoes
        for p, q in zip(x, y, strict=True)
    )


def test_imagem_retornada_e_gravavel_e_independente() -> None:
    a = gerar_amostra(3)
    copia = a.imagem.copy()
    a.imagem[0, 0] = 0
    assert numpy.array_equal(gerar_amostra(3).imagem, copia)


# ---------------------------------------------------------------------------- iou


def test_iou_e_simetrico_e_contido() -> None:
    a, b = (0.0, 0.0, 10.0, 10.0), (2.0, 2.0, 6.0, 6.0)
    assert iou(a, b) == iou(b, a) == pytest.approx(16 / 100)


def test_iou_tocando_so_no_canto_ou_na_borda_e_zero() -> None:
    assert iou((0, 0, 10, 10), (10, 10, 20, 20)) == 0.0
    assert iou((0, 0, 10, 10), (0, 10, 10, 20)) == 0.0


def test_iou_caixa_degenerada_nao_levanta() -> None:
    assert iou((5, 5, 5, 5), (5, 5, 5, 5)) == 0.0
    assert iou((0, 0, 0, 0), (0, 0, 10, 10)) == 0.0


# ------------------------------------------------------------------------ avaliar


def test_avaliar_casamento_guloso_por_score_e_nao_por_ordem_de_entrada() -> None:
    # duas detecções disputam a mesma verdade; a de maior score (listada por último) vence
    boa = Deteccao(CAIXA, 1, 0.95)
    razoavel = Deteccao((12.0, 10.0, 62.0, 60.0), 1, 0.60)
    r = avaliar([[razoavel, boa]], [[Anotacao(CAIXA, 1)]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 1, 0)


def test_avaliar_cada_verdade_casa_uma_vez_com_duas_verdades_e_duas_deteccoes() -> None:
    outra = (100.0, 100.0, 150.0, 150.0)
    r = avaliar(
        [[Deteccao(outra, 1, 0.8), Deteccao(CAIXA, 1, 0.9)]],
        [[Anotacao(CAIXA, 1), Anotacao(outra, 1)]],
    )
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (2, 0, 0)


def test_avaliar_deteccao_acima_do_score_e_sem_verdade_e_falso_positivo() -> None:
    r = avaliar([[Deteccao(CAIXA, 1, 0.9)]], [[]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 1, 0)
    assert r.precisao == 0.0
    assert r.recall == 0.0


def test_avaliar_score_igual_ao_minimo_conta() -> None:
    r = avaliar([[Deteccao(CAIXA, 1, 0.5)]], [[Anotacao(CAIXA, 1)]])
    assert r.verdadeiros == 1


def test_avaliar_iou_igual_ao_minimo_conta() -> None:
    # IoU exatamente 1/3 com iou_minimo=1/3
    r = avaliar(
        [[Deteccao((5.0, 0.0, 15.0, 10.0), 1, 0.9)]],
        [[Anotacao((0.0, 0.0, 10.0, 10.0), 1)]],
        iou_minimo=1 / 3,
    )
    assert r.verdadeiros == 1


def test_avaliar_iou_logo_abaixo_do_minimo_nao_conta() -> None:
    r = avaliar(
        [[Deteccao((6.0, 0.0, 16.0, 10.0), 1, 0.9)]],
        [[Anotacao((0.0, 0.0, 10.0, 10.0), 1)]],
    )
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 1, 1)


def test_avaliar_soma_imagens_sem_misturar_verdades_entre_imagens() -> None:
    r = avaliar(
        [[Deteccao(CAIXA, 1, 0.9)], []],
        [[], [Anotacao(CAIXA, 1)]],
    )
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 1, 1)


def test_avaliar_imagem_com_verdade_e_sem_predicao_so_gera_falso_negativo() -> None:
    r = avaliar([[], []], [[Anotacao(CAIXA, 1), Anotacao(CAIXA, 2)], [Anotacao(CAIXA, 3)]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 0, 3)


def test_avaliar_exige_mesmo_numero_de_imagens() -> None:
    with pytest.raises(ValueError):
        avaliar([[]], [[], []])


def test_avaliar_classe_errada_nao_consome_a_verdade_da_classe_certa() -> None:
    r = avaliar(
        [[Deteccao(CAIXA, 2, 0.99), Deteccao(CAIXA, 1, 0.6)]],
        [[Anotacao(CAIXA, 1)]],
    )
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 1, 0)


def test_avaliar_precisao_e_recall_fracionarios() -> None:
    r = avaliar(
        [[Deteccao(CAIXA, 1, 0.9), Deteccao((200.0, 200.0, 250.0, 250.0), 1, 0.9)]],
        [[Anotacao(CAIXA, 1), Anotacao((100.0, 100.0, 150.0, 150.0), 1)]],
    )
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 1, 1)
    assert r.precisao == 0.5
    assert r.recall == 0.5


def test_avaliar_nao_consome_as_listas_de_entrada() -> None:
    verdade = [[Anotacao(CAIXA, 1)]]
    pred = [[Deteccao(CAIXA, 1, 0.9)]]
    avaliar(pred, verdade)
    assert verdade == [[Anotacao(CAIXA, 1)]]
    assert pred == [[Deteccao(CAIXA, 1, 0.9)]]


# ------------------------------------------------------- deteccoes_equivalentes


def test_equivalentes_ambos_vazios() -> None:
    assert deteccoes_equivalentes([], [])


def test_equivalentes_limite_exato_do_limiar_alto_exige_par() -> None:
    # 0.30 + 0.05 = 0.35 exige par (>=); sem par -> False
    assert not deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.35)], [])
    assert deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.349)], [])


def test_equivalentes_par_no_limite_inferior_aceita_e_abaixo_rejeita() -> None:
    ref = [Deteccao(CAIXA, 1, 0.90)]
    assert deteccoes_equivalentes(ref, [Deteccao(CAIXA, 1, 0.26)])  # >= 0.25
    # o par existe apenas abaixo de 0.25 -> não conta como par da obrigatória
    assert not deteccoes_equivalentes(ref, [Deteccao(CAIXA, 1, 0.20)])


def test_equivalentes_par_acima_do_alto_de_um_lado_e_entre_limiares_do_outro() -> None:
    # 0.36 (obrigatória) casa com 0.26 (reserva); 0.26 não exige par: simétrico
    a = [Deteccao(CAIXA, 1, 0.36)]
    b = [Deteccao(CAIXA, 1, 0.26)]
    assert deteccoes_equivalentes(a, b)
    assert deteccoes_equivalentes(b, a)


def test_equivalentes_iou_099_exato_aceita_e_logo_abaixo_rejeita() -> None:
    ref = [Deteccao((0.0, 0.0, 100.0, 100.0), 1, 0.9)]
    # IoU = 99*100/(100*100) = 0.99
    assert deteccoes_equivalentes(ref, [Deteccao((0.0, 0.0, 99.0, 100.0), 1, 0.9)])
    # IoU = 0.98
    assert not deteccoes_equivalentes(ref, [Deteccao((0.0, 0.0, 98.0, 100.0), 1, 0.9)])


def test_equivalentes_classes_diferentes_nao_casam_mesmo_com_caixa_igual() -> None:
    assert not deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.9)], [Deteccao(CAIXA, 2, 0.9)])
    assert not deteccoes_equivalentes([Deteccao(CAIXA, 2, 0.9)], [Deteccao(CAIXA, 1, 0.9)])


def test_equivalentes_um_a_um_nos_dois_sentidos() -> None:
    um = [Deteccao(CAIXA, 1, 0.9)]
    dois = [Deteccao(CAIXA, 1, 0.9), Deteccao(CAIXA, 1, 0.9)]
    assert not deteccoes_equivalentes(um, dois)
    assert not deteccoes_equivalentes(dois, um)


def test_equivalentes_emparelhamento_exige_caminho_aumentante() -> None:
    # x casa com y1 e y2; w casa só com y1. Guloso (x->y1) deixaria w sem par;
    # o emparelhamento ótimo (x->y2, w->y1) existe.
    x = Deteccao((0.0, 0.0, 100.0, 100.0), 1, 0.9)
    w = Deteccao((0.0, 0.0, 100.0, 98.8), 1, 0.9)
    y1 = Deteccao((0.0, 0.0, 100.0, 99.5), 1, 0.9)
    y2 = Deteccao((0.0, 0.0, 100.0, 100.0), 1, 0.9)
    assert iou(x.caixa, y1.caixa) >= 0.99 and iou(w.caixa, y1.caixa) >= 0.99
    assert iou(x.caixa, y2.caixa) >= 0.99 and iou(w.caixa, y2.caixa) < 0.99
    assert deteccoes_equivalentes([x, w], [y1, y2])
    assert deteccoes_equivalentes([y1, y2], [x, w])


def test_equivalentes_sem_pares_distintos_suficientes_com_grafo_nao_trivial() -> None:
    # duas obrigatórias disputam o único par possível
    alvo = Deteccao((0.0, 0.0, 100.0, 100.0), 1, 0.9)
    longe = Deteccao((200.0, 200.0, 300.0, 300.0), 1, 0.9)
    assert not deteccoes_equivalentes([alvo, alvo], [alvo, longe])


def test_equivalentes_parametros_personalizados() -> None:
    assert deteccoes_equivalentes(
        [Deteccao(CAIXA, 1, 0.6)], [], score_minimo=0.7, margem=0.05, iou_minimo=0.99
    )
    assert not deteccoes_equivalentes(
        [Deteccao(CAIXA, 1, 0.9)],
        [Deteccao((14.0, 10.0, 64.0, 60.0), 1, 0.9)],
        iou_minimo=0.95,
    )
    assert deteccoes_equivalentes(
        [Deteccao(CAIXA, 1, 0.9)],
        [Deteccao((14.0, 10.0, 64.0, 60.0), 1, 0.9)],
        iou_minimo=0.8,
    )


@pytest.mark.parametrize("deslocamento", [0.0, 0.05, 0.4, 2.0, 10.0])
@pytest.mark.parametrize("score_a", [0.0, 0.25, 0.30, 0.35, 0.9])
@pytest.mark.parametrize("score_b", [0.0, 0.25, 0.30, 0.35, 0.9])
def test_equivalentes_e_simetrica_em_grade(
    deslocamento: float, score_a: float, score_b: float
) -> None:
    a = [Deteccao(CAIXA, 1, score_a)]
    b = [Deteccao((10.0 + deslocamento, 10.0, 60.0 + deslocamento, 60.0), 1, score_b)]
    assert deteccoes_equivalentes(a, b) == deteccoes_equivalentes(b, a)


def test_equivalentes_e_simetrica_com_multiplas_deteccoes() -> None:
    a = [
        Deteccao(CAIXA, 1, 0.9),
        Deteccao((100.0, 100.0, 150.0, 150.0), 2, 0.4),
        Deteccao((200.0, 0.0, 250.0, 50.0), 3, 0.2),
    ]
    b = [
        Deteccao(CAIXA, 1, 0.88),
        Deteccao((100.0, 100.0, 150.0, 150.0), 2, 0.28),
        Deteccao((0.0, 200.0, 50.0, 250.0), 4, 0.31),
    ]
    assert deteccoes_equivalentes(a, b) == deteccoes_equivalentes(b, a)


# ------------------------------------------------------------ perdas_equivalentes


def test_perdas_infinito_na_referencia_e_nan_na_referencia_rejeitam() -> None:
    assert not perdas_equivalentes([float("inf")], [float("inf")])
    assert not perdas_equivalentes([float("nan")], [float("nan")])
    assert not perdas_equivalentes([float("-inf")], [1.0])


def test_perdas_nan_em_qualquer_iteracao_rejeita_mesmo_com_o_resto_igual() -> None:
    assert not perdas_equivalentes([1.0, 2.0, 3.0], [1.0, float("nan"), 3.0])
    assert not perdas_equivalentes([1.0, 2.0, 3.0], [1.0, 2.0, float("-inf")])


def test_perdas_candidata_mais_longa_rejeita() -> None:
    assert not perdas_equivalentes([2.0], [2.0, 2.0])


def test_perdas_limite_exato_da_tolerancia_aceita_e_acima_rejeita() -> None:
    assert perdas_equivalentes([100.0], [105.0])
    assert perdas_equivalentes([100.0], [95.0])
    assert not perdas_equivalentes([100.0], [105.1])
    assert not perdas_equivalentes([100.0], [94.9])


def test_perdas_referencia_zero_usa_piso_e_nao_divide_por_zero() -> None:
    assert perdas_equivalentes([0.0], [0.0])
    assert perdas_equivalentes([0.0], [4e-8])
    assert not perdas_equivalentes([0.0], [1e-3])
    assert not perdas_equivalentes([1e-9], [1.0])


def test_perdas_referencia_negativa_usa_modulo() -> None:
    assert perdas_equivalentes([-2.0], [-2.05])
    assert not perdas_equivalentes([-2.0], [-2.5])


def test_perdas_tolerancia_personalizada() -> None:
    assert perdas_equivalentes([2.0], [2.19], tolerancia_relativa=0.1)
    assert not perdas_equivalentes([2.0], [2.3], tolerancia_relativa=0.1)
    assert not perdas_equivalentes([2.0], [2.05], tolerancia_relativa=0.0)
    assert perdas_equivalentes([2.0], [2.0], tolerancia_relativa=0.0)


def test_perdas_aceita_tuplas_e_uma_unica_iteracao() -> None:
    assert perdas_equivalentes((1.0,), (1.0,))


# --------------------------------------------------------------- resumir_tempos


def test_resumir_tempos_um_elemento() -> None:
    r = resumir_tempos([3.5])
    assert (r.amostras, r.mediana_s, r.p95_s, r.total_s) == (1, 3.5, 3.5, 3.5)


def test_resumir_tempos_nao_depende_da_ordem_de_entrada() -> None:
    cresc = [float(i) for i in range(1, 21)]
    assert resumir_tempos(list(reversed(cresc))) == resumir_tempos(cresc)
    embaralhado = cresc[10:] + cresc[:10]
    embaralhado[::2], embaralhado[1::2] = embaralhado[1::2], embaralhado[::2]
    assert resumir_tempos(embaralhado) == resumir_tempos(cresc)


def test_resumir_tempos_nao_altera_a_entrada() -> None:
    tempos = [3.0, 1.0, 2.0]
    resumir_tempos(tempos)
    assert tempos == [3.0, 1.0, 2.0]


@pytest.mark.parametrize("n", range(1, 201))
def test_resumir_tempos_p95_nearest_rank_exato(n: int) -> None:
    tempos = [float(i) for i in range(1, n + 1)]
    esperado_posto = -(-95 * n // 100)  # ceil(0.95 * n) em inteiros
    assert resumir_tempos(tempos).p95_s == float(esperado_posto)


def test_resumir_tempos_mediana_de_quantidade_impar() -> None:
    assert resumir_tempos([5.0, 1.0, 3.0]).mediana_s == 3.0


def test_resumir_tempos_p95_e_valor_da_amostra_nao_interpolado() -> None:
    r = resumir_tempos([1.0, 2.0, 100.0])
    assert r.p95_s == 100.0
    assert r.p95_s in (1.0, 2.0, 100.0)


def test_resumir_tempos_total_preciso_com_floats_pequenos() -> None:
    r = resumir_tempos([0.1] * 10)
    assert math.isclose(r.total_s, 1.0, rel_tol=0, abs_tol=1e-15)


# -------------------------------------------------------------- ladrilhos_por_folha


def test_ladrilhos_dimensao_igual_ao_lado_e_um_pixel_a_mais() -> None:
    assert ladrilhos_por_folha(320, 1) == 1
    assert ladrilhos_por_folha(321, 320) == 2
    assert ladrilhos_por_folha(320 + 288, 320) == 2
    assert ladrilhos_por_folha(320 + 289, 320) == 3


def test_ladrilhos_e_simetrico_nos_eixos() -> None:
    assert ladrilhos_por_folha(5000, 1234) == ladrilhos_por_folha(1234, 5000)


def test_ladrilhos_sem_sobreposicao_e_com_lado_diferente() -> None:
    assert ladrilhos_por_folha(640, 640, lado=320, sobreposicao=0.0) == 4
    assert ladrilhos_por_folha(641, 320, lado=320, sobreposicao=0.0) == 3
    assert ladrilhos_por_folha(1000, 500, lado=100, sobreposicao=0.5) == 19 * 9


def test_ladrilhos_cobrem_a_dimensao() -> None:
    passo = round(320 * 0.9)
    for dim in (1, 319, 320, 321, 607, 608, 609, 1000, 9933):
        por_eixo = ladrilhos_por_folha(dim, 320)
        assert (por_eixo - 1) * passo + 320 >= dim
        assert por_eixo == 1 or (por_eixo - 2) * passo + 320 < dim
