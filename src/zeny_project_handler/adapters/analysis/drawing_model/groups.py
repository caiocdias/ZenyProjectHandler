"""Agrupamento de primitivas e caminhos próximos em candidatos a símbolo."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence

from zeny_project_handler.adapters.analysis.drawing_model.geometry import _ponto_bezier
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    GrupoCandidato,
    ItemCaminho,
    Polilinha,
)

_CELULA = 10.0
_TOLERANCIA_RELATIVA = 0.02


def _caixa_pontos(pontos: Iterable[tuple[float, float]]) -> Caixa:
    xs, ys = zip(*pontos, strict=True)
    return (min(xs), min(ys), max(xs), max(ys))


def _caixa_primitiva(primitiva: Polilinha | Circulo | Arco) -> Caixa:
    if isinstance(primitiva, Polilinha):
        return _caixa_pontos(primitiva.pontos)
    (cx, cy), r = primitiva.centro, primitiva.raio
    return (cx - r, cy - r, cx + r, cy + r)


def _caixa_caminho(caminho: Caminho) -> Caixa:
    return _caixa_pontos(
        ponto for sub in caminho.subcaminhos for item in sub for ponto in item.pontos
    )


def _no_circulo(figura: Circulo | Arco, ponto: tuple[float, float]) -> bool:
    distancia = math.dist(figura.centro, ponto)
    return abs(distancia - figura.raio) <= _TOLERANCIA_RELATIVA * figura.raio


def _item_coberto(item: ItemCaminho, figuras: Sequence[Circulo | Arco]) -> bool:
    pontos = (item.pontos[0], _ponto_bezier(item.pontos, 0.5), item.pontos[-1])
    return any(all(_no_circulo(figura, ponto) for ponto in pontos) for figura in figuras)


def _caminhos_elegiveis(
    primitivas: Sequence[Polilinha | Circulo | Arco], caminhos: Sequence[Caminho]
) -> list[int]:
    figuras_por_origem: dict[int, list[Circulo | Arco]] = defaultdict(list)
    for primitiva in primitivas:
        if isinstance(primitiva, Circulo | Arco):
            for origem in primitiva.origens:
                figuras_por_origem[origem].append(primitiva)
    elegiveis: list[int] = []
    for indice, caminho in enumerate(caminhos):
        itens = [item for sub in caminho.subcaminhos for item in sub]
        if not itens:
            continue
        figuras = figuras_por_origem.get(indice, [])
        if figuras and all(item.tipo == "c" for item in itens):
            circulos = [f for f in figuras if isinstance(f, Circulo)]
            if any(all(_item_coberto(item, [c]) for item in itens) for c in circulos):
                continue  # inteiramente convertido num mesmo círculo
        if caminho.tipo != "traco" or any(
            item.tipo == "c" and not _item_coberto(item, figuras) for item in itens
        ):
            elegiveis.append(indice)
    return elegiveis


def agrupar_candidatos(
    primitivas: Sequence[Polilinha | Circulo | Arco],
    caminhos: Sequence[Caminho],
    *,
    folga: float = 1.5,
    lado_maximo: float = 40.0,
) -> tuple[GrupoCandidato, ...]:
    indices_caminhos = _caminhos_elegiveis(primitivas, caminhos)
    caixas: list[Caixa] = [_caixa_primitiva(p) for p in primitivas]
    caixas.extend(_caixa_caminho(caminhos[i]) for i in indices_caminhos)
    total = len(caixas)
    pai = list(range(total))

    def raiz(i: int) -> int:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    celulas: dict[tuple[int, int], list[int]] = defaultdict(list)
    # Elemento maior que `lado_maximo` sozinho é traçado da rede, não parte de símbolo.
    grandes = {i for i, c in enumerate(caixas) if max(c[2] - c[0], c[3] - c[1]) > lado_maximo}
    for i, (x0, y0, x1, y1) in enumerate(caixas):
        if i in grandes:
            continue
        faixa_x = range(math.floor((x0 - folga) / _CELULA), math.floor((x1 + folga) / _CELULA) + 1)
        faixa_y = range(math.floor((y0 - folga) / _CELULA), math.floor((y1 + folga) / _CELULA) + 1)
        vizinhos: set[int] = set()
        for cx in faixa_x:
            for cy in faixa_y:
                celula = celulas[(cx, cy)]
                vizinhos.update(celula)
                celula.append(i)
        for j in vizinhos:
            ox0, oy0, ox1, oy1 = caixas[j]
            # Caixas dilatadas por `folga` cada uma: sobrepõem se a distância <= 2 * folga.
            if (
                ox0 <= x1 + 2 * folga
                and x0 <= ox1 + 2 * folga
                and oy0 <= y1 + 2 * folga
                and y0 <= oy1 + 2 * folga
            ):
                pai[raiz(i)] = raiz(j)

    membros: dict[int, list[int]] = defaultdict(list)
    for i in range(total):
        if i in grandes:
            continue
        membros[raiz(i)].append(i)

    n_prim = len(primitivas)
    grupos: list[GrupoCandidato] = []
    for lista in membros.values():
        caixa = (
            min(caixas[i][0] for i in lista),
            min(caixas[i][1] for i in lista),
            max(caixas[i][2] for i in lista),
            max(caixas[i][3] for i in lista),
        )
        if max(caixa[2] - caixa[0], caixa[3] - caixa[1]) > lado_maximo:
            continue
        if len(lista) == 1 and lista[0] < n_prim:
            unica = primitivas[lista[0]]
            if isinstance(unica, Polilinha) and not unica.fechada and len(unica.pontos) == 2:
                continue
        grupos.append(
            GrupoCandidato(
                caixa,
                tuple(i for i in lista if i < n_prim),
                tuple(indices_caminhos[i - n_prim] for i in lista if i >= n_prim),
            )
        )
    grupos.sort(key=lambda g: (g.indices_primitivas or (n_prim,), g.indices_caminhos))
    return tuple(grupos)
