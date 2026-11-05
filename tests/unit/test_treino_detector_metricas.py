"""Métricas puras do ensaio de treino do detector (spike E11)."""

from __future__ import annotations

import pytest
from scripts.treino_detector.dados_sinteticos import Anotacao
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


def test_iou_casos_basicos() -> None:
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_avaliar_acerto_simples() -> None:
    r = avaliar([[Deteccao(CAIXA, 1, 0.9)]], [[Anotacao(CAIXA, 1)]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 0, 0)
    assert r.precisao == 1.0
    assert r.recall == 1.0


def test_avaliar_conta_classe_errada_e_duplicata_como_falso_positivo() -> None:
    errada = avaliar([[Deteccao(CAIXA, 2, 0.9)]], [[Anotacao(CAIXA, 1)]])
    assert (errada.verdadeiros, errada.falsos_positivos, errada.falsos_negativos) == (0, 1, 1)
    duplicada = avaliar(
        [[Deteccao(CAIXA, 1, 0.9), Deteccao(CAIXA, 1, 0.8)]], [[Anotacao(CAIXA, 1)]]
    )
    assert (duplicada.verdadeiros, duplicada.falsos_positivos, duplicada.falsos_negativos) == (
        1,
        1,
        0,
    )
    assert duplicada.precisao == 0.5


def test_avaliar_ignora_predicao_abaixo_do_score() -> None:
    r = avaliar([[Deteccao(CAIXA, 1, 0.4)]], [[Anotacao(CAIXA, 1)]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 0, 1)


def test_avaliar_sem_predicoes_tem_precisao_zero_e_recall_zero() -> None:
    r = avaliar([[]], [[Anotacao(CAIXA, 1)]])
    assert r.precisao == 0.0
    assert r.recall == 0.0
    vazio = avaliar([[]], [[]])
    assert vazio.precisao == 0.0
    assert vazio.recall == 0.0


def test_avaliar_casa_por_score_decrescente_com_iou_minimo() -> None:
    deslocada = (40.0, 10.0, 90.0, 60.0)  # IoU 20/80 = 0.25 com CAIXA
    r = avaliar([[Deteccao(deslocada, 1, 0.99), Deteccao(CAIXA, 1, 0.6)]], [[Anotacao(CAIXA, 1)]])
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 1, 0)


def test_deteccoes_equivalentes_aceita_ruido_minimo_e_rejeita_caixa_deslocada() -> None:
    ref = [Deteccao(CAIXA, 1, 0.90)]
    assert deteccoes_equivalentes(ref, [Deteccao((10.1, 10.0, 60.1, 60.0), 1, 0.88)])
    assert not deteccoes_equivalentes(ref, [Deteccao((14.0, 10.0, 64.0, 60.0), 1, 0.90)])
    assert not deteccoes_equivalentes(ref, [Deteccao(CAIXA, 2, 0.90)])


def test_deteccoes_equivalentes_rejeita_deteccao_sem_par_acima_da_margem() -> None:
    assert not deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.50)], [])
    assert not deteccoes_equivalentes([], [Deteccao(CAIXA, 1, 0.50)])


def test_deteccoes_equivalentes_tolera_deteccao_perto_do_limiar() -> None:
    assert deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.31)], [Deteccao(CAIXA, 1, 0.29)])
    assert deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.31)], [])
    assert deteccoes_equivalentes([Deteccao(CAIXA, 1, 0.20)], [])


def test_deteccoes_equivalentes_e_simetrica() -> None:
    a = [Deteccao(CAIXA, 1, 0.31)]
    b = [Deteccao(CAIXA, 1, 0.29)]
    assert deteccoes_equivalentes(a, b) == deteccoes_equivalentes(b, a)
    c = [Deteccao(CAIXA, 1, 0.50)]
    assert deteccoes_equivalentes(c, []) == deteccoes_equivalentes([], c)
    d = [Deteccao(CAIXA, 1, 0.9), Deteccao(CAIXA, 1, 0.9)]
    assert deteccoes_equivalentes(a, d) == deteccoes_equivalentes(d, a)


def test_deteccoes_equivalentes_casa_uma_a_uma() -> None:
    dupla = [Deteccao(CAIXA, 1, 0.9), Deteccao(CAIXA, 1, 0.9)]
    assert not deteccoes_equivalentes(dupla, [Deteccao(CAIXA, 1, 0.9)])
    assert deteccoes_equivalentes(dupla, list(dupla))


def test_perdas_equivalentes() -> None:
    assert perdas_equivalentes([2.0, 1.5], [2.05, 1.46])
    assert not perdas_equivalentes([2.0, 1.5], [2.0, 1.7])
    assert not perdas_equivalentes([2.0], [float("nan")])
    assert not perdas_equivalentes([2.0, 1.5], [2.0])
    assert not perdas_equivalentes([], [])
    assert not perdas_equivalentes([2.0], [float("inf")])


def test_resumir_tempos_mediana_p95_e_vazio() -> None:
    r = resumir_tempos([float(i) for i in range(1, 21)])
    assert (r.amostras, r.mediana_s, r.p95_s, r.total_s) == (20, 10.5, 19.0, 210.0)
    with pytest.raises(ValueError):
        resumir_tempos([])


def test_ladrilhos_por_folha() -> None:
    assert ladrilhos_por_folha(320, 320) == 1
    assert ladrilhos_por_folha(100, 100) == 1
    assert ladrilhos_por_folha(9933, 7016) == 35 * 25
