"""Geometria pura: reconstrução de polilinhas e recuperação de círculos e arcos."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Arco,
    Caminho,
    Circulo,
    Estilo,
    ItemCaminho,
    Polilinha,
    Ponto,
)


class _GradeDeNos:
    """Agrupa pontos a até `tolerancia` de um nó existente, com busca por grade."""

    def __init__(self, tolerancia: float) -> None:
        self._tolerancia = tolerancia
        self._celulas: dict[tuple[int, int], list[int]] = {}
        self.posicoes: list[Ponto] = []

    def no_para(self, ponto: Ponto) -> int:
        cx = math.floor(ponto[0] / self._tolerancia)
        cy = math.floor(ponto[1] / self._tolerancia)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for no in self._celulas.get((cx + dx, cy + dy), ()):
                    px, py = self.posicoes[no]
                    if math.hypot(px - ponto[0], py - ponto[1]) <= self._tolerancia:
                        return no
        no = len(self.posicoes)
        self.posicoes.append(ponto)
        self._celulas.setdefault((cx, cy), []).append(no)
        return no


@dataclass(slots=True)
class _Aresta:
    a: int
    b: int
    origem: int
    usada: bool = False


def reconstruir_polilinhas(
    caminhos: Sequence[Caminho],
    *,
    tolerancia_ponto: float = 0.5,
    tolerancia_angulo_graus: float = 1.0,
) -> tuple[Polilinha, ...]:
    """Funde segmentos "l" de caminhos de traço, de mesmo estilo, em polilinhas."""
    por_estilo: dict[Estilo, list[tuple[Ponto, Ponto, int]]] = {}
    for indice, caminho in enumerate(caminhos):
        if caminho.tipo != "traco":
            continue
        for subcaminho in caminho.subcaminhos:
            for item in subcaminho:
                if item.tipo == "l":
                    por_estilo.setdefault(caminho.estilo, []).append(
                        (item.pontos[0], item.pontos[1], indice)
                    )
    resultado: list[Polilinha] = []
    for estilo, segmentos in por_estilo.items():
        resultado.extend(
            _polilinhas_do_estilo(estilo, segmentos, tolerancia_ponto, tolerancia_angulo_graus)
        )
    return tuple(resultado)


def _polilinhas_do_estilo(
    estilo: Estilo,
    segmentos: Sequence[tuple[Ponto, Ponto, int]],
    tolerancia_ponto: float,
    tolerancia_angulo: float,
) -> list[Polilinha]:
    grade = _GradeDeNos(tolerancia_ponto)
    arestas: list[_Aresta] = []
    incidentes: dict[int, list[int]] = {}
    for inicio, fim, origem in segmentos:
        a = grade.no_para(inicio)
        b = grade.no_para(fim)
        if a == b:
            continue
        indice = len(arestas)
        arestas.append(_Aresta(a, b, origem))
        incidentes.setdefault(a, []).append(indice)
        incidentes.setdefault(b, []).append(indice)

    # Cursor por nó: aresta usada nunca volta a ser livre, então o ponteiro só avança e a
    # "primeira aresta livre" é a mesma de uma busca desde o início, em custo amortizado linear.
    cursor: dict[int, int] = dict.fromkeys(incidentes, 0)

    def primeira_livre(no: int) -> int | None:
        lista = incidentes[no]
        posicao = cursor[no]
        while posicao < len(lista) and arestas[lista[posicao]].usada:
            posicao += 1
        cursor[no] = posicao
        return lista[posicao] if posicao < len(lista) else None

    def percorrer(no_inicial: int) -> tuple[list[int], list[int]]:
        nos = [no_inicial]
        origens: list[int] = []
        atual = no_inicial
        while True:
            proxima = primeira_livre(atual)
            if proxima is None:
                return nos, origens
            aresta = arestas[proxima]
            aresta.usada = True
            origens.append(aresta.origem)
            atual = aresta.b if aresta.a == atual else aresta.a
            nos.append(atual)
            if len(incidentes[atual]) != 2 or atual == no_inicial:
                return nos, origens

    polilinhas: list[Polilinha] = []
    nos_ordenados = sorted(incidentes)
    # Primeiro as pontas e junções (grau != 2); depois o que sobrou são ciclos.
    ordem_de_partida = [n for n in nos_ordenados if len(incidentes[n]) != 2] + nos_ordenados
    for no in ordem_de_partida:
        while primeira_livre(no) is not None:
            nos, origens = percorrer(no)
            if len(nos) == 3 and nos[0] == nos[2]:
                nos = nos[:2]  # segmento pintado duas vezes: aberta, com as duas origens
            fechada = len(nos) > 3 and nos[0] == nos[-1]
            usados = nos[:-1] if fechada else nos
            pontos = _remover_colineares(
                [grade.posicoes[n] for n in usados], fechada, tolerancia_angulo
            )
            polilinhas.append(
                Polilinha(tuple(pontos), fechada, estilo, tuple(sorted(set(origens))))
            )
    return polilinhas


def _desvio_graus(anterior: Ponto, vertice: Ponto, seguinte: Ponto) -> float:
    ax, ay = vertice[0] - anterior[0], vertice[1] - anterior[1]
    bx, by = seguinte[0] - vertice[0], seguinte[1] - vertice[1]
    return abs(math.degrees(math.atan2(ax * by - ay * bx, ax * bx + ay * by)))


def _remover_colineares(pontos: list[Ponto], fechada: bool, tolerancia: float) -> list[Ponto]:
    """Remove vértices colineares em passada única com pilha (linear)."""
    pilha: list[Ponto] = []
    for ponto in pontos:
        while len(pilha) >= 2 and _desvio_graus(pilha[-2], pilha[-1], ponto) <= tolerancia:
            pilha.pop()
        pilha.append(ponto)
    if not fechada:
        return pilha
    inicio = 0
    mudou = True
    while mudou and len(pilha) - inicio > 3:
        mudou = False
        if _desvio_graus(pilha[-2], pilha[-1], pilha[inicio]) <= tolerancia:
            pilha.pop()
            mudou = True
        elif _desvio_graus(pilha[-1], pilha[inicio], pilha[inicio + 1]) <= tolerancia:
            inicio += 1
            mudou = True
    return pilha[inicio:]


def ponto_bezier(pontos: tuple[Ponto, ...], t: float) -> Ponto:
    u = 1.0 - t
    pesos = (u**3, 3 * u * u * t, 3 * u * t * t, t**3)
    return (
        sum(p[0] * w for p, w in zip(pontos, pesos, strict=True)),
        sum(p[1] * w for p, w in zip(pontos, pesos, strict=True)),
    )


def _circunferencia(a: Ponto, b: Ponto, c: Ponto) -> tuple[Ponto, float] | None:
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) < 1e-12:
        return None
    a2, b2, c2 = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    ux = (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d
    uy = (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d
    return (ux, uy), math.hypot(a[0] - ux, a[1] - uy)


@dataclass(frozen=True, slots=True)
class _TrechoCircular:
    centro: Ponto
    raio: float
    angulo_inicial: float
    varredura: float  # com sinal: positivo = sentido horário visual
    inicio: Ponto
    fim: Ponto


def _trecho_circular(item: ItemCaminho, tolerancia: float) -> _TrechoCircular | None:
    p0, _, _, p1 = item.pontos
    meio = ponto_bezier(item.pontos, 0.5)
    ajuste = _circunferencia(p0, meio, p1)
    if ajuste is None:
        return None
    centro, raio = ajuste
    if raio <= 0 or not math.isfinite(raio):
        return None
    for t in (0.25, 0.75):
        x, y = ponto_bezier(item.pontos, t)
        if abs(math.hypot(x - centro[0], y - centro[1]) - raio) > tolerancia * raio:
            return None

    def angulo(ponto: Ponto) -> float:
        return math.degrees(math.atan2(ponto[1] - centro[1], ponto[0] - centro[0])) % 360.0

    a0, am, a1 = angulo(p0), angulo(meio), angulo(p1)
    ate_o_meio = (am - a0) % 360.0
    ate_o_fim = (a1 - a0) % 360.0
    varredura = ate_o_fim if ate_o_meio <= ate_o_fim else ate_o_fim - 360.0
    return _TrechoCircular(centro, raio, a0, varredura, p0, p1)


def _continua(anterior: _TrechoCircular, seguinte: _TrechoCircular, tolerancia: float) -> bool:
    limite = tolerancia * anterior.raio
    return (
        math.dist(anterior.centro, seguinte.centro) <= limite
        and abs(anterior.raio - seguinte.raio) <= limite
        and (anterior.varredura > 0) == (seguinte.varredura > 0)
        and math.dist(anterior.fim, seguinte.inicio) <= max(limite, 1e-6)
    )


def recuperar_circulos_e_arcos(
    caminhos: Sequence[Caminho], *, tolerancia_relativa: float = 0.02
) -> tuple[Circulo | Arco, ...]:
    """Reconhece Béziers que são arcos de círculo e une arcos contíguos."""
    resultado: list[Circulo | Arco] = []
    for indice, caminho in enumerate(caminhos):
        for subcaminho in caminho.subcaminhos:
            grupo: list[_TrechoCircular] = []
            for item in subcaminho:
                trecho = _trecho_circular(item, tolerancia_relativa) if item.tipo == "c" else None
                if (
                    trecho is not None
                    and grupo
                    and _continua(grupo[-1], trecho, tolerancia_relativa)
                ):
                    grupo.append(trecho)
                    continue
                resultado.extend(_emitir(grupo, caminho.estilo, indice))
                grupo = [] if trecho is None else [trecho]
            resultado.extend(_emitir(grupo, caminho.estilo, indice))
    return tuple(resultado)


def _emitir(grupo: list[_TrechoCircular], estilo: Estilo, origem: int) -> list[Circulo | Arco]:
    if not grupo:
        return []
    primeiro = grupo[0]
    total = sum(t.varredura for t in grupo)
    if abs(total) >= 360.0 - 1.0:
        return [Circulo(primeiro.centro, primeiro.raio, estilo, (origem,))]
    inicial = primeiro.angulo_inicial if total > 0 else (primeiro.angulo_inicial + total) % 360.0
    return [Arco(primeiro.centro, primeiro.raio, inicial, inicial + abs(total), estilo, (origem,))]
