"""Assinatura numérica da forma de um glifo desenhado como contorno preenchido.

A assinatura é invariante a translação, escala (relativa à altura da linha), início e sentido do
contorno. Os polígonos chegam já no quadro do trecho (y para baixo, texto na horizontal).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.model import ItemCaminho, Ponto

PONTOS_POR_SUBCAMINHO: Final = 24
PASSOS_BEZIER: Final = 8
_DESLOCAMENTO_MAXIMO: Final = 3


@dataclass(frozen=True, slots=True)
class AssinaturaGlifo:
    subcaminhos: int
    caixa: tuple[float, float, float]
    contornos: tuple[tuple[Ponto, ...], ...]


def achatar_subcaminho(itens: Sequence[ItemCaminho]) -> tuple[Ponto, ...]:
    """Converte segmentos e Béziers cúbicas em uma polilinha (Bézier em `PASSOS_BEZIER` passos)."""
    if not itens:
        return ()
    pontos: list[Ponto] = [itens[0].pontos[0]]
    for item in itens:
        if item.tipo == "l":
            pontos.append(item.pontos[-1])
            continue
        p0, c1, c2, p1 = item.pontos
        for passo in range(1, PASSOS_BEZIER + 1):
            t = passo / PASSOS_BEZIER
            u = 1.0 - t
            pontos.append(
                (
                    u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p1[0],
                    u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p1[1],
                )
            )
    return tuple(pontos)


def _limpar(poligono: Sequence[Ponto]) -> list[Ponto]:
    limpo: list[Ponto] = []
    for ponto in poligono:
        if not limpo or ponto != limpo[-1]:
            limpo.append(ponto)
    if len(limpo) > 1 and limpo[0] == limpo[-1]:
        limpo.pop()
    return limpo


def _area_com_sinal(pontos: Sequence[Ponto]) -> float:
    total = 0.0
    for i, (x1, y1) in enumerate(pontos):
        x2, y2 = pontos[(i + 1) % len(pontos)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _perimetro(pontos: Sequence[Ponto]) -> float:
    return sum(math.dist(pontos[i], pontos[(i + 1) % len(pontos)]) for i in range(len(pontos)))


def _caixa(pontos: Sequence[Ponto]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pontos]
    ys = [p[1] for p in pontos]
    return min(xs), min(ys), max(xs), max(ys)


def _iniciar_no_canto(pontos: list[Ponto]) -> list[Ponto]:
    x0, y0, _, _ = _caixa(pontos)
    indice = min(
        range(len(pontos)),
        key=lambda i: (round(math.dist(pontos[i], (x0, y0)), 9), pontos[i][1], pontos[i][0]),
    )
    return pontos[indice:] + pontos[:indice]


def _reamostrar(pontos: Sequence[Ponto]) -> list[Ponto]:
    n = len(pontos)
    perimetro = _perimetro(pontos)
    passo = perimetro / PONTOS_POR_SUBCAMINHO
    amostras: list[Ponto] = []
    segmento = 0
    inicio_segmento = 0.0
    comprimento = math.dist(pontos[0], pontos[1 % n])
    for k in range(PONTOS_POR_SUBCAMINHO):
        alvo = k * passo
        while inicio_segmento + comprimento < alvo and segmento < n - 1:
            inicio_segmento += comprimento
            segmento += 1
            comprimento = math.dist(pontos[segmento], pontos[(segmento + 1) % n])
        fracao = (alvo - inicio_segmento) / comprimento if comprimento > 0 else 0.0
        (xa, ya), (xb, yb) = pontos[segmento], pontos[(segmento + 1) % n]
        amostras.append((xa + (xb - xa) * fracao, ya + (yb - ya) * fracao))
    return amostras


def assinatura_glifo(
    poligonos_no_quadro: Sequence[Sequence[Ponto]], *, altura_linha: float, base_linha: float
) -> AssinaturaGlifo | None:
    if not poligonos_no_quadro or not math.isfinite(altura_linha) or altura_linha <= 0:
        return None
    if not math.isfinite(base_linha):
        return None
    poligonos: list[list[Ponto]] = []
    for bruto in poligonos_no_quadro:
        if not all(math.isfinite(x) and math.isfinite(y) for x, y in bruto):
            return None
        poligono = _limpar(bruto)
        if len(poligono) < 2 or _perimetro(poligono) <= 0:
            return None
        if _area_com_sinal(poligono) < 0:
            poligono.reverse()
        poligonos.append(poligono)

    esquerda, topo, direita, fundo = _caixa([p for poligono in poligonos for p in poligono])
    centro_x, centro_y = (esquerda + direita) / 2.0, (topo + fundo) / 2.0
    h = altura_linha

    itens: list[tuple[tuple[float, float, float], tuple[Ponto, ...]]] = []
    for poligono in poligonos:
        caixa = _caixa(poligono)
        amostras = _reamostrar(_iniciar_no_canto(poligono))
        contorno = tuple(((x - centro_x) / h, (y - centro_y) / h) for x, y in amostras)
        area = abs(_area_com_sinal(poligono)) / (h * h)
        cx = ((caixa[0] + caixa[2]) / 2.0 - centro_x) / h
        cy = ((caixa[1] + caixa[3]) / 2.0 - centro_y) / h
        chave = (-round(area, 2) + 0.0, round(cy, 2) + 0.0, round(cx, 2) + 0.0)
        itens.append((chave, contorno))
    itens.sort(key=lambda item: item[0])

    return AssinaturaGlifo(
        subcaminhos=len(itens),
        caixa=((direita - esquerda) / h, (fundo - topo) / h, (fundo - base_linha) / h),
        contornos=tuple(contorno for _, contorno in itens),
    )


def diferenca_caixa(a: AssinaturaGlifo, b: AssinaturaGlifo) -> float:
    return max(abs(x - y) for x, y in zip(a.caixa, b.caixa, strict=True))


def _distancia_contorno(a: Sequence[Ponto], b: Sequence[Ponto]) -> float:
    n = len(a)
    melhor = math.inf
    for deslocamento in range(-_DESLOCAMENTO_MAXIMO, _DESLOCAMENTO_MAXIMO + 1):
        media = sum(math.dist(a[i], b[(i + deslocamento) % n]) for i in range(n)) / n
        melhor = min(melhor, media)
    return melhor


def distancia_assinaturas(a: AssinaturaGlifo, b: AssinaturaGlifo) -> float:
    if a.subcaminhos != b.subcaminhos:
        return math.inf
    contorno = sum(
        _distancia_contorno(ca, cb) for ca, cb in zip(a.contornos, b.contornos, strict=True)
    ) / max(a.subcaminhos, 1)
    return max(diferenca_caixa(a, b), contorno)
