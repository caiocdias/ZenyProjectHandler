"""Ataques à distância robusta (deslocamentos de meio passo, pareamento de subcaminhos)."""

from __future__ import annotations

import itertools
import math

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    AssinaturaGlifo,
    assinatura_glifo,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import Ponto

TOLERANCIA = 0.08
L_FORMA: list[Ponto] = [(0, 0), (1, 0), (1, 4), (3, 4), (3, 5), (0, 5)]
T_FORMA: list[Ponto] = [(0, 0), (3, 0), (3, 1), (2, 1), (2, 5), (1, 5), (1, 1), (0, 1)]
# Forma assimétrica parecida com 6/9: haste curva com laço (aproximada por polígono).
SEIS: list[Ponto] = [(2, 0), (3, 1), (1, 1), (1, 3), (3, 3), (3, 5), (0, 5), (0, 1)]


def _assinar(
    poligonos: list[list[Ponto]], altura: float = 5.0, base: float = 5.0
) -> AssinaturaGlifo:
    assinatura = assinatura_glifo(poligonos, altura_linha=altura, base_linha=base)
    assert assinatura is not None
    return assinatura


def _quadrado(x: float, y: float, lado: float) -> list[Ponto]:
    return [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)]


def _elipse(rx: float, ry: float, n: int = 40) -> list[Ponto]:
    return [
        (rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n)) for i in range(n)
    ]


def test_l_e_t_continuam_longe_com_inicio_livre() -> None:
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([T_FORMA])) > 3 * TOLERANCIA


def test_forma_girada_180_graus_nao_se_confunde_com_a_original() -> None:
    girada = [(3 - x, 5 - y) for x, y in L_FORMA]
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([girada])) > 3 * TOLERANCIA


def test_seis_e_nove_nao_se_confundem() -> None:
    nove = [(3 - x, 5 - y) for x, y in SEIS]
    assert distancia_assinaturas(_assinar([SEIS]), _assinar([nove])) > TOLERANCIA


def test_espelho_horizontal_segue_longe() -> None:
    espelho = [(3 - x, y) for x, y in L_FORMA]
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([espelho])) > 3 * TOLERANCIA


@pytest.mark.parametrize(("largura", "separa"), [(2.9, False), (2.7, True), (2.5, True)])
def test_o_estreito_vs_zero_separa_por_largura_no_limite_da_tolerancia(
    largura: float, separa: bool
) -> None:
    """Elipse de rx=3 contra rx menor: o meio passo não pode aproximar larguras 10% diferentes."""
    o = _assinar([_elipse(3.0, 4.0)])
    zero = _assinar([_elipse(largura, 4.0)])
    assert (distancia_assinaturas(o, zero) > TOLERANCIA) is separa


def test_quadrado_e_losango_de_mesma_caixa_nao_se_confundem() -> None:
    quadrado = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]
    losango = [(2.0, 0.0), (4.0, 2.0), (2.0, 4.0), (0.0, 2.0)]
    assert distancia_assinaturas(_assinar([quadrado]), _assinar([losango])) > TOLERANCIA


def test_distancia_e_simetrica_com_pareamento_de_subcaminhos() -> None:
    a = _assinar([_quadrado(0, 0, 1), _quadrado(0, 3, 1.2), _quadrado(0, 6, 0.8)], 8.0, 8.0)
    b = _assinar([_quadrado(0, 0, 1.1), _quadrado(0, 3, 1.0), _quadrado(0, 6, 0.9)], 8.0, 8.0)
    assert distancia_assinaturas(a, b) == pytest.approx(distancia_assinaturas(b, a), abs=1e-12)


def test_com_quatro_subcaminhos_qualquer_ordem_de_entrada_da_a_mesma_distancia() -> None:
    lados = [0.6, 0.8, 1.0, 1.2]
    quadrados = [_quadrado(0, 3 * i, lado) for i, lado in enumerate(lados)]
    referencia = _assinar(quadrados, 12.0, 12.0)
    for ordem in itertools.permutations(quadrados):
        assert distancia_assinaturas(referencia, _assinar(list(ordem), 12.0, 12.0)) < 1e-9


def test_pareamento_nao_aproxima_glifos_de_subcaminhos_distintos() -> None:
    """Dois pontos pequenos x dois retângulos: o melhor pareamento ainda fica longe."""
    pontos = _assinar([_quadrado(0, 0, 0.5), _quadrado(0, 2, 0.5)], 4.0, 4.0)
    barras = _assinar([_quadrado(0, 0, 1.5), _quadrado(0, 2, 1.5)], 4.0, 4.0)
    assert distancia_assinaturas(pontos, barras) > TOLERANCIA


def test_pareamento_de_quatro_nao_ignora_a_diferenca_da_caixa() -> None:
    a = _assinar([_quadrado(0, 3 * i, 1.0) for i in range(4)], 12.0, 12.0)
    b = _assinar([_quadrado(0, 3 * i, 1.0) for i in range(4)], 12.0, 6.0)
    assert distancia_assinaturas(a, b) >= 0.5 - 1e-9


def test_acima_de_quatro_subcaminhos_mantem_ordem_fixa_por_area_exata() -> None:
    """Com 5 subcaminhos a ordem de entrada ainda não importa (áreas distintas e exatas)."""
    quadrados = [_quadrado(0, 3 * i, 1.0 + 0.1 * i) for i in range(5)]
    referencia = _assinar(quadrados, 16.0, 16.0)
    invertida = _assinar(list(reversed(quadrados)), 16.0, 16.0)
    assert distancia_assinaturas(referencia, invertida) < 1e-9


def test_cinco_subcaminhos_identicos_distintos_so_pela_posicao_sao_deterministicos() -> None:
    quadrados = [_quadrado(0, 3 * i, 1.0) for i in range(5)]
    a = _assinar(quadrados, 16.0, 16.0)
    b = _assinar(list(reversed(quadrados)), 16.0, 16.0)
    assert a.contornos == b.contornos


def test_a_distancia_nunca_e_menor_que_a_diferenca_de_caixa() -> None:
    a = _assinar([_elipse(3.0, 4.0)], 5.0, 2.0)
    b = _assinar([_elipse(3.0, 4.0)], 5.0, 2.5)
    assert distancia_assinaturas(a, b) >= 0.1 - 1e-9


def test_distancia_com_inicio_arbitrario_continua_zero_para_o_mesmo_poligono_girado() -> None:
    """Todos os 24 deslocamentos possíveis do contorno reamostrado dão distância zero."""
    base = _assinar([T_FORMA])
    for passo in range(len(T_FORMA)):
        girado = T_FORMA[passo:] + T_FORMA[:passo]
        assert distancia_assinaturas(base, _assinar([girado])) < 1e-6
