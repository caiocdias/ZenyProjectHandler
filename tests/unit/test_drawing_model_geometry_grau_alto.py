"""Saída fixa de `reconstruir_polilinhas` em nó de grau alto e custo do agrupamento (R-9)."""

from __future__ import annotations

from typing import Any

import pytest
from tests.unit.test_drawing_model_geometry_adversarial import E, traco

from zeny_project_handler.adapters.analysis.drawing_model import groups
from zeny_project_handler.adapters.analysis.drawing_model.geometry import reconstruir_polilinhas
from zeny_project_handler.adapters.analysis.drawing_model.groups import agrupar_candidatos
from zeny_project_handler.adapters.analysis.drawing_model.model import Circulo

Ponto = tuple[float, float]


def test_saida_identica_em_no_de_grau_alto() -> None:
    # Estrela de 5 raios saindo de (0, 0) mais um sexto raio que repete o primeiro.
    pontas: list[Ponto] = [
        (10.0, 0.0),
        (3.0, 9.0),
        (-8.0, 6.0),
        (-8.0, -6.0),
        (3.0, -9.0),
        (10.0, 0.0),
    ]
    caminhos = [traco((0.0, 0.0), ponta, ordem=i) for i, ponta in enumerate(pontas)]
    obtido = [(p.pontos, p.fechada, p.origens) for p in reconstruir_polilinhas(caminhos)]
    assert obtido == [
        (((0.0, 0.0), (10.0, 0.0)), False, (0, 5)),
        (((0.0, 0.0), (3.0, 9.0)), False, (1,)),
        (((0.0, 0.0), (-8.0, 6.0)), False, (2,)),
        (((0.0, 0.0), (-8.0, -6.0)), False, (3,)),
        (((0.0, 0.0), (3.0, -9.0)), False, (4,)),
    ]


def test_ciclo_e_segmento_duplo_mantem_a_saida() -> None:
    caminhos = [
        traco((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0), ordem=0),
        traco((0.0, 0.0), (10.0, 10.0), ordem=1),
        traco((20.0, 0.0), (30.0, 0.0), ordem=2),
        traco((30.0, 0.0), (20.0, 0.0), ordem=3),
    ]
    obtido = [(p.pontos, p.fechada, p.origens) for p in reconstruir_polilinhas(caminhos)]
    assert obtido == [
        (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0)), False, (0,)),
        (((0.0, 0.0), (0.0, 10.0), (10.0, 10.0)), False, (0,)),
        (((0.0, 0.0), (10.0, 10.0)), False, (1,)),
        (((20.0, 0.0), (30.0, 0.0)), False, (2, 3)),
    ]


def _comparacoes_sobrepostas(n: int, monkeypatch: pytest.MonkeyPatch) -> int:
    """Conta os pares de caixas comparados no agrupamento de `n` círculos quase sobrepostos."""
    primitivas = [Circulo((0.0, 0.0), 2.0 + i * 1e-4, E, (i,)) for i in range(n)]
    comparacoes = 0
    original = groups._caixas_se_encostam

    def contando(*args: Any) -> bool:
        nonlocal comparacoes
        comparacoes += 1
        return bool(original(*args))

    with monkeypatch.context() as contexto:
        contexto.setattr(groups, "_caixas_se_encostam", contando)
        agrupar_candidatos(primitivas, [])
    return comparacoes


def test_agrupamento_escala_linearmente_com_caixas_sobrepostas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pequeno = _comparacoes_sobrepostas(500, monkeypatch)
    grande = _comparacoes_sobrepostas(1_000, monkeypatch)
    assert pequeno > 0
    assert grande <= 2.5 * pequeno, (pequeno, grande)
