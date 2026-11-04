"""Ataques adversariais à assinatura de glifo (invariâncias, empates, início canônico)."""

from __future__ import annotations

import itertools
import math

import pytest

from zeny_project_handler.adapters.analysis.drawing_model.glyph_signature import (
    PONTOS_POR_SUBCAMINHO,
    AssinaturaGlifo,
    achatar_subcaminho,
    assinatura_glifo,
    distancia_assinaturas,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import ItemCaminho, Ponto

TOLERANCIA = 0.08
L_FORMA: list[Ponto] = [(0, 0), (1, 0), (1, 4), (3, 4), (3, 5), (0, 5)]


def _assinar(
    poligonos: list[list[Ponto]], altura: float = 5.0, base: float = 5.0
) -> AssinaturaGlifo:
    assinatura = assinatura_glifo(poligonos, altura_linha=altura, base_linha=base)
    assert assinatura is not None
    return assinatura


def _quadrado(x: float, y: float, lado: float) -> list[Ponto]:
    return [(x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado)]


def _retangulo(x: float, y: float, largura: float, altura: float) -> list[Ponto]:
    return [(x, y), (x + largura, y), (x + largura, y + altura), (x, y + altura)]


def _elipse(rx: float, ry: float, n: int = 40, fase: float = 0.0) -> list[Ponto]:
    return [
        (rx * math.cos(fase + 2 * math.pi * i / n), ry * math.sin(fase + 2 * math.pi * i / n))
        for i in range(n)
    ]


def _losango(meia: float, ruido: float = 0.0) -> list[Ponto]:
    """Losango regular: o canto da caixa fica equidistante dos vértices de cima e da esquerda."""
    return [(0.0, -meia), (meia, 0.0), (0.0, meia), (-meia - ruido, 0.0)]


# --- invariâncias -----------------------------------------------------------------------------


@pytest.mark.parametrize("deslocamento", range(len(L_FORMA)))
@pytest.mark.parametrize("sentido", ["direto", "inverso"])
def test_todo_vertice_inicial_e_sentido_geram_a_mesma_assinatura(
    deslocamento: int, sentido: str
) -> None:
    variante = L_FORMA[deslocamento:] + L_FORMA[:deslocamento]
    if sentido == "inverso":
        variante.reverse()
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([variante])) < 1e-6


def test_ponto_de_fechamento_repetido_e_pontos_duplicados_sao_ignorados() -> None:
    limpa = _assinar([L_FORMA])
    suja = _assinar([[*L_FORMA[:2], L_FORMA[1], *L_FORMA[2:], L_FORMA[0]]])
    assert distancia_assinaturas(limpa, suja) < 1e-6


def test_vertice_colinear_extra_nao_desloca_a_assinatura() -> None:
    com_extra: list[Ponto] = [(0, 0), (0.5, 0), (1, 0), (1, 4), (3, 4), (3, 5), (0, 5)]
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([com_extra])) < 1e-6


def test_assinatura_e_simetrica_e_zero_consigo_mesma() -> None:
    a = _assinar([L_FORMA])
    b = _assinar([_elipse(2.0, 4.0)])
    assert distancia_assinaturas(a, a) == 0.0
    assert distancia_assinaturas(a, b) == distancia_assinaturas(b, a)


def test_espelho_horizontal_nao_confunde_com_a_forma_original() -> None:
    espelho = [(3 - x, y) for x, y in L_FORMA]
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([espelho])) > TOLERANCIA


def test_inverter_verticalmente_nao_confunde_com_a_forma_original() -> None:
    de_cabeca_para_baixo = [(x, 5 - y) for x, y in L_FORMA]
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([de_cabeca_para_baixo])) > TOLERANCIA


def test_linha_de_base_diferente_separa_formas_iguais() -> None:
    """Mesma forma, uma com descendente (cauda abaixo da base): a caixa precisa distinguir."""
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([L_FORMA], base=3.5)) > TOLERANCIA


def test_altura_de_linha_diferente_muda_a_escala_normalizada() -> None:
    assert distancia_assinaturas(_assinar([L_FORMA]), _assinar([L_FORMA], altura=10.0)) > TOLERANCIA


@pytest.mark.parametrize("fase", [0.0, 0.1, 0.5, 1.0, math.pi / 4])
def test_elipse_amostrada_com_fases_diferentes_fica_dentro_da_tolerancia(fase: float) -> None:
    """Início canônico: o mesmo desenho de O com vértices em fases distintas é o mesmo glifo."""
    base = _assinar([_elipse(3.0, 4.0, fase=0.0)], altura=5.0, base=2.0)
    outra = _assinar([_elipse(3.0, 4.0, fase=fase)], altura=5.0, base=2.0)
    assert distancia_assinaturas(base, outra) < TOLERANCIA


def test_circulo_em_beziers_com_inicio_em_outro_quadrante_e_o_mesmo_glifo() -> None:
    raio = 10.0
    k = 0.5522847498 * raio
    cantos = [(raio, 0.0), (0.0, raio), (-raio, 0.0), (0.0, -raio)]
    controles = [
        ((raio, k), (k, raio)),
        ((-k, raio), (-raio, k)),
        ((-raio, -k), (-k, -raio)),
        ((k, -raio), (raio, -k)),
    ]
    itens = [
        ItemCaminho("c", (cantos[i], controles[i][0], controles[i][1], cantos[(i + 1) % 4]))
        for i in range(4)
    ]
    a = _assinar([list(achatar_subcaminho(itens))], altura=20.0, base=10.0)
    for giro in (1, 2, 3):
        girado = itens[giro:] + itens[:giro]
        b = _assinar([list(achatar_subcaminho(girado))], altura=20.0, base=10.0)
        assert distancia_assinaturas(a, b) < 1e-6


@pytest.mark.parametrize("ruido", [1e-6, 1e-4, 1e-3])
def test_losango_com_ruido_minusculo_continua_o_mesmo_glifo(ruido: float) -> None:
    """O canto da caixa é equidistante de dois vértices de um losango: o desempate pode saltar
    um quarto do perímetro (6 amostras, acima do limite de ±3) por causa de ruído irrisório."""
    exato = _assinar([_losango(3.0)], altura=6.0, base=3.0)
    ruidoso = _assinar([_losango(3.0, ruido)], altura=6.0, base=3.0)
    assert distancia_assinaturas(exato, ruidoso) < TOLERANCIA


# --- subcaminhos --------------------------------------------------------------------------------


def test_ordem_dos_subcaminhos_na_entrada_nao_importa() -> None:
    grande = _retangulo(0, 0, 4, 6)
    medio = _retangulo(6, 0, 2, 3)
    pequeno = _retangulo(6, 4, 1, 1)
    referencia = _assinar([grande, medio, pequeno])
    for permutacao in itertools.permutations([grande, medio, pequeno]):
        assert distancia_assinaturas(referencia, _assinar(list(permutacao))) < 1e-6


def test_subcaminhos_de_areas_identicas_ordenam_pela_posicao_nao_pela_entrada() -> None:
    """Dois pontos de dois-pontos com a mesma área: a ordem de entrada não altera a assinatura."""
    cima = _quadrado(0, 0, 1)
    baixo = _quadrado(0, 3, 1)
    a = _assinar([cima, baixo], altura=4.0, base=4.0)
    b = _assinar([baixo, cima], altura=4.0, base=4.0)
    assert a.contornos == b.contornos


def test_subcaminhos_empatados_geram_assinatura_deterministica() -> None:
    cima = _quadrado(0, 0, 1)
    baixo = _quadrado(0, 3, 1)
    primeira = _assinar([cima, baixo], altura=4.0, base=4.0)
    segunda = _assinar([cima, baixo], altura=4.0, base=4.0)
    assert primeira == segunda
    assert primeira.contornos[0] != primeira.contornos[1]


def test_areas_quase_iguais_nao_trocam_a_ordem_dos_subcaminhos() -> None:
    """Dois pontos de dois-pontos diferem 0,2% em área, em lados opostos de uma fronteira de
    arredondamento da chave de ordenação. Visualmente é o mesmo glifo: a distância deve ficar
    dentro da tolerância, não saltar para um valor enorme por troca de ordem."""
    lado_a, lado_b = math.sqrt(0.1249) * 4.0, math.sqrt(0.1251) * 4.0
    a = _assinar([_quadrado(0, 0, lado_a), _quadrado(0, 6, lado_b)], altura=4.0, base=4.0)
    b = _assinar([_quadrado(0, 0, lado_b), _quadrado(0, 6, lado_a)], altura=4.0, base=4.0)
    assert distancia_assinaturas(a, b) < TOLERANCIA


def test_numero_de_subcaminhos_e_contornos_acompanham_a_entrada() -> None:
    assinatura = _assinar([L_FORMA, _quadrado(5, 0, 1)])
    assert assinatura.subcaminhos == 2
    assert len(assinatura.contornos) == 2
    assert all(len(c) == PONTOS_POR_SUBCAMINHO for c in assinatura.contornos)


# --- degenerados -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("altura", "base"),
    [(math.inf, 5.0), (math.nan, 5.0), (5.0, math.nan), (5.0, math.inf), (-math.inf, 5.0)],
)
def test_altura_ou_base_nao_finita_devolve_none(altura: float, base: float) -> None:
    assert assinatura_glifo([L_FORMA], altura_linha=altura, base_linha=base) is None


def test_um_subcaminho_degenerado_invalida_o_glifo_inteiro() -> None:
    assert assinatura_glifo([L_FORMA, [(2.0, 2.0)] * 4], altura_linha=5.0, base_linha=5.0) is None


def test_subcaminho_vazio_ou_de_um_ponto_devolve_none() -> None:
    assert assinatura_glifo([[]], altura_linha=5.0, base_linha=5.0) is None
    assert assinatura_glifo([[(1.0, 1.0)]], altura_linha=5.0, base_linha=5.0) is None


def test_coordenada_infinita_em_qualquer_subcaminho_devolve_none() -> None:
    ruim = [(0.0, 0.0), (1.0, 0.0), (-math.inf, 1.0)]
    assert assinatura_glifo([L_FORMA, ruim], altura_linha=5.0, base_linha=5.0) is None


def test_assinatura_nunca_contem_valores_nao_finitos() -> None:
    for poligonos in ([L_FORMA], [_elipse(1.0, 2.0)], [_retangulo(0, 0, 1e-6, 1e-6)]):
        assinatura = _assinar(poligonos, altura=1e-3, base=0.0)
        valores = [*assinatura.caixa, *(v for c in assinatura.contornos for p in c for v in p)]
        assert all(math.isfinite(v) for v in valores)


def test_poligono_nao_e_mutado_pela_assinatura() -> None:
    entrada = [list(L_FORMA)]
    copia = [list(L_FORMA)]
    _assinar(entrada)
    assert entrada == copia
