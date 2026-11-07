"""Agrupamento de primitivas e caminhos próximos em candidatos a símbolo."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Final

from zeny_project_handler.adapters.analysis.drawing_model.geometry import ponto_bezier
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
LIMITE_VISITAS_AGRUPAMENTO: Final = 50_000_000


class AgrupamentoExcedido(Exception):  # noqa: N818 - nome fixado pelo plano da E06.2.2.1
    """O agrupamento da página passou do teto de visitas às células."""


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
    pontos = (item.pontos[0], ponto_bezier(item.pontos, 0.5), item.pontos[-1])
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


def _lado(caixa: Caixa) -> float:
    return max(caixa[2] - caixa[0], caixa[3] - caixa[1])


def _caixas_se_encostam(a: Caixa, b: Caixa, margem: float) -> bool:
    return (
        a[0] <= b[2] + margem
        and b[0] <= a[2] + margem
        and a[1] <= b[3] + margem
        and b[1] <= a[3] + margem
    )


def _unir_proximos(
    caixas: Sequence[Caixa], ativos: Sequence[int], folga: float, limite_visitas: int
) -> list[int]:
    """Union-find com grade espacial sobre caixas dilatadas por `folga`; devolve o vetor de pais.

    Uma visita é cada entrada de célula lida; passar de `limite_visitas` levanta
    `AgrupamentoExcedido`. Comparações repetidas entre quem já tem a mesma raiz são puladas, mas a
    leitura de célula densa segue quadrática em visitas: o teto é quem limita o caso hostil.
    """
    pai = list(range(len(caixas)))

    def raiz(i: int) -> int:
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    celulas: dict[tuple[int, int], list[int]] = defaultdict(list)
    visitas = 0
    for i in ativos:
        x0, y0, x1, y1 = caixas[i]
        faixa_x = range(math.floor((x0 - folga) / _CELULA), math.floor((x1 + folga) / _CELULA) + 1)
        faixa_y = range(math.floor((y0 - folga) / _CELULA), math.floor((y1 + folga) / _CELULA) + 1)
        vizinhos: set[int] = set()
        for cx in faixa_x:
            for cy in faixa_y:
                celula = celulas[(cx, cy)]
                visitas += len(celula)
                if visitas > limite_visitas:
                    raise AgrupamentoExcedido(limite_visitas)
                vizinhos.update(celula)
                celula.append(i)
        for j in vizinhos:
            if raiz(j) == raiz(i):
                continue
            # Caixas dilatadas por `folga` cada uma: sobrepõem se a distância <= 2 * folga.
            if _caixas_se_encostam(caixas[i], caixas[j], 2 * folga):
                pai[raiz(i)] = raiz(j)
    return [raiz(i) for i in range(len(caixas))]


def _polilinha_aberta_de_dois_pontos(elemento: Polilinha | Circulo | Arco) -> bool:
    return isinstance(elemento, Polilinha) and not elemento.fechada and len(elemento.pontos) == 2


def _montar_grupo(
    membros: Sequence[int],
    caixas: Sequence[Caixa],
    primitivas: Sequence[Polilinha | Circulo | Arco],
    indices_caminhos: Sequence[int],
    lado_maximo: float,
) -> GrupoCandidato | None:
    n_prim = len(primitivas)
    caixa = (
        min(caixas[i][0] for i in membros),
        min(caixas[i][1] for i in membros),
        max(caixas[i][2] for i in membros),
        max(caixas[i][3] for i in membros),
    )
    if _lado(caixa) > lado_maximo:
        return None
    if (
        len(membros) == 1
        and membros[0] < n_prim
        and _polilinha_aberta_de_dois_pontos(primitivas[membros[0]])
    ):
        return None
    return GrupoCandidato(
        caixa,
        tuple(i for i in membros if i < n_prim),
        tuple(indices_caminhos[i - n_prim] for i in membros if i >= n_prim),
    )


def agrupar_candidatos(
    primitivas: Sequence[Polilinha | Circulo | Arco],
    caminhos: Sequence[Caminho],
    *,
    folga: float = 1.5,
    lado_maximo: float = 40.0,
    limite_visitas: int = LIMITE_VISITAS_AGRUPAMENTO,
) -> tuple[GrupoCandidato, ...]:
    indices_caminhos = _caminhos_elegiveis(primitivas, caminhos)
    caixas: list[Caixa] = [_caixa_primitiva(p) for p in primitivas]
    caixas.extend(_caixa_caminho(caminhos[i]) for i in indices_caminhos)
    # Elemento maior que `lado_maximo` sozinho é traçado da rede, não parte de símbolo.
    ativos = [i for i, caixa in enumerate(caixas) if _lado(caixa) <= lado_maximo]
    raizes = _unir_proximos(caixas, ativos, folga, limite_visitas)
    membros: dict[int, list[int]] = defaultdict(list)
    for i in ativos:
        membros[raizes[i]].append(i)
    montados = (
        _montar_grupo(lista, caixas, primitivas, indices_caminhos, lado_maximo)
        for lista in membros.values()
    )
    grupos = [grupo for grupo in montados if grupo is not None]
    n_prim = len(primitivas)
    grupos.sort(key=lambda g: (g.indices_primitivas or (n_prim,), g.indices_caminhos))
    return tuple(grupos)
