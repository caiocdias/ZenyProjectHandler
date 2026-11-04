"""Agrupamento de primitivas e caminhos próximos em candidatos a símbolo."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caixa,
    Caminho,
    Circulo,
    GrupoCandidato,
    Polilinha,
)

_CELULA = 10.0


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


def _caminhos_elegiveis(
    primitivas: Sequence[Polilinha | Circulo | Arco], caminhos: Sequence[Caminho]
) -> list[int]:
    origens_circulo: set[int] = set()
    origens_curva: set[int] = set()
    for primitiva in primitivas:
        if isinstance(primitiva, Circulo):
            origens_circulo.update(primitiva.origens)
            origens_curva.update(primitiva.origens)
        elif isinstance(primitiva, Arco):
            origens_curva.update(primitiva.origens)
    elegiveis: list[int] = []
    for indice, caminho in enumerate(caminhos):
        itens = [item for sub in caminho.subcaminhos for item in sub]
        if not itens:
            continue
        if indice in origens_circulo and all(item.tipo == "c" for item in itens):
            continue  # inteiramente convertido em círculo
        if caminho.tipo == "traco":
            if indice not in origens_curva and any(item.tipo == "c" for item in itens):
                elegiveis.append(indice)
        else:
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
    for i, (x0, y0, x1, y1) in enumerate(caixas):
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
