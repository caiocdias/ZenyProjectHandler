"""Equivalência de `reconstruir_polilinhas` com a travessia anterior (aresta livre por busca)."""

from __future__ import annotations

import random
from collections.abc import Sequence

import pytest
from tests.unit.test_drawing_model_geometry_adversarial import E, TipoCaminho, traco

from zeny_project_handler.adapters.analysis.drawing_model import geometry
from zeny_project_handler.adapters.analysis.drawing_model.geometry import reconstruir_polilinhas
from zeny_project_handler.adapters.analysis.drawing_model.model import (
    Caminho,
    Estilo,
    Polilinha,
    Ponto,
)

OUTRO = Estilo("OUTRO", (255, 0, 0), None, 2.0, "")


def _polilinhas_antigo(
    estilo: Estilo,
    segmentos: Sequence[tuple[Ponto, Ponto, int]],
    tolerancia_ponto: float,
    tolerancia_angulo: float,
) -> list[Polilinha]:
    """Cópia da implementação anterior ao cursor por nó (referência do teste)."""
    grade = geometry._GradeDeNos(tolerancia_ponto)
    arestas: list[geometry._Aresta] = []
    incidentes: dict[int, list[int]] = {}
    for inicio, fim, origem in segmentos:
        a = grade.no_para(inicio)
        b = grade.no_para(fim)
        if a == b:
            continue
        indice = len(arestas)
        arestas.append(geometry._Aresta(a, b, origem))
        incidentes.setdefault(a, []).append(indice)
        incidentes.setdefault(b, []).append(indice)

    def percorrer(no_inicial: int) -> tuple[list[int], list[int]]:
        nos = [no_inicial]
        origens: list[int] = []
        atual = no_inicial
        while True:
            proxima = next((i for i in incidentes[atual] if not arestas[i].usada), None)
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
    ordem_de_partida = [n for n in nos_ordenados if len(incidentes[n]) != 2] + nos_ordenados
    for no in ordem_de_partida:
        while any(not arestas[i].usada for i in incidentes[no]):
            nos, origens = percorrer(no)
            if len(nos) == 3 and nos[0] == nos[2]:
                nos = nos[:2]
            fechada = len(nos) > 3 and nos[0] == nos[-1]
            usados = nos[:-1] if fechada else nos
            pontos = geometry._remover_colineares(
                [grade.posicoes[n] for n in usados], fechada, tolerancia_angulo
            )
            polilinhas.append(
                Polilinha(tuple(pontos), fechada, estilo, tuple(sorted(set(origens))))
            )
    return polilinhas


def _referencia(caminhos: Sequence[Caminho]) -> tuple[Polilinha, ...]:
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
        resultado.extend(_polilinhas_antigo(estilo, segmentos, 0.5, 1.0))
    return tuple(resultado)


def _grafo_aleatorio(semente: int) -> list[Caminho]:
    rng = random.Random(semente)
    lado = rng.choice([2, 3, 4, 6])  # grade pequena força grau alto, ciclos e repetições
    ruido = rng.choice([0.0, 0.0, 0.2])  # ruído abaixo da tolerância funde nós
    escala = 10.0

    def ponto() -> Ponto:
        return (
            rng.randrange(lado) * escala + rng.uniform(-ruido, ruido),
            rng.randrange(lado) * escala + rng.uniform(-ruido, ruido),
        )

    caminhos: list[Caminho] = []
    for ordem in range(rng.randrange(1, 40)):
        pontos = [ponto() for _ in range(rng.randrange(2, 6))]
        if rng.random() < 0.15:
            pontos.append(pontos[0])  # percurso fechado
        estilo = rng.choice([E, E, OUTRO])
        tipo: TipoCaminho = "traco" if rng.random() < 0.9 else "preenchimento"
        caminhos.append(traco(*pontos, ordem=ordem, estilo=estilo, tipo=tipo))
    return caminhos


@pytest.mark.parametrize("semente", range(300))
def test_saida_igual_a_travessia_anterior_em_grafos_aleatorios(semente: int) -> None:
    caminhos = _grafo_aleatorio(semente)
    assert reconstruir_polilinhas(caminhos) == _referencia(caminhos)


def test_saida_igual_em_grafo_denso_com_hub_ciclos_e_laco() -> None:
    hub: Ponto = (0.0, 0.0)
    pontas: list[Ponto] = [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (-10.0, 5.0)]
    caminhos: list[Caminho] = []
    ordem = 0
    for ponta in pontas * 3:  # cada raio pintado 3 vezes, em ambos os sentidos
        caminhos.append(traco(hub, ponta, ordem=ordem))
        caminhos.append(traco(ponta, hub, ordem=ordem + 1))
        ordem += 2
    caminhos.append(traco(hub, (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), hub, ordem=ordem))
    caminhos.append(traco(hub, hub, (0.1, 0.1), ordem=ordem + 1))  # laço degenerado
    caminhos.append(traco((50.0, 0.0), (60.0, 0.0), (60.0, 10.0), (50.0, 0.0), ordem=ordem + 2))
    esperado = _referencia(caminhos)
    assert len(esperado) > 4
    assert reconstruir_polilinhas(caminhos) == esperado


def test_no_de_grau_dois_no_fechamento_do_ciclo_mantem_a_saida() -> None:
    # Triângulo com um raio saindo de um vértice: o fechamento passa por nó de grau 2.
    caminhos = [
        traco((0.0, 0.0), (10.0, 0.0), (5.0, 8.0), (0.0, 0.0), ordem=0),
        traco((0.0, 0.0), (-9.0, -9.0), ordem=1),
        traco((10.0, 0.0), (20.0, -5.0), ordem=2),
    ]
    assert reconstruir_polilinhas(caminhos) == _referencia(caminhos)
