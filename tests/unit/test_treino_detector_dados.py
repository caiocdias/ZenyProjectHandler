"""Dados sintéticos do ensaio de treino do detector (spike E11)."""

from __future__ import annotations

import itertools

import numpy
import pytest
from scripts.treino_detector.dados_sinteticos import CLASSES, gerar_amostra, gerar_conjunto
from scripts.treino_detector.metricas import iou


def test_amostra_e_deterministica_pela_semente() -> None:
    a, b = gerar_amostra(7), gerar_amostra(7)
    assert numpy.array_equal(a.imagem, b.imagem)
    assert a.anotacoes == b.anotacoes
    assert not numpy.array_equal(gerar_amostra(8).imagem, a.imagem)


def test_caixas_dentro_da_imagem_nao_degeneradas_e_sem_sobreposicao() -> None:
    for amostra in gerar_conjunto(3, 50):
        assert amostra.imagem.shape == (320, 320, 3)
        assert amostra.imagem.dtype == numpy.uint8
        assert 1 <= len(amostra.anotacoes) <= 4
        for anot in amostra.anotacoes:
            x0, y0, x1, y1 = anot.caixa
            assert 0 <= x0 < x1 <= 320
            assert 0 <= y0 < y1 <= 320
            assert 32 <= x1 - x0 <= 96
            assert 32 <= y1 - y0 <= 96
            assert 1 <= anot.rotulo <= len(CLASSES)
        assert all(
            iou(p.caixa, q.caixa) == 0 for p, q in itertools.combinations(amostra.anotacoes, 2)
        )


def test_simbolo_deixa_tinta_escura_dentro_da_caixa() -> None:
    for amostra in gerar_conjunto(5, 30):
        for anot in amostra.anotacoes:
            x0, y0, x1, y1 = (int(v) for v in anot.caixa)
            recorte = amostra.imagem[y0:y1, x0:x1]
            assert int(recorte.min()) < 80


def test_conjunto_usa_semente_derivada_por_indice() -> None:
    conjunto = gerar_conjunto(4, 3)
    assert len(conjunto) == 3
    esperado = gerar_amostra(4 * 1_000_003 + 2)
    assert numpy.array_equal(conjunto[2].imagem, esperado.imagem)


def test_todas_as_classes_aparecem_no_conjunto() -> None:
    rotulos = {a.rotulo for amostra in gerar_conjunto(1, 60) for a in amostra.anotacoes}
    assert rotulos == set(range(1, len(CLASSES) + 1))


def test_lado_menor_que_o_simbolo_minimo_nao_e_suportado() -> None:
    with pytest.raises(ValueError):
        gerar_amostra(1, lado=16)
