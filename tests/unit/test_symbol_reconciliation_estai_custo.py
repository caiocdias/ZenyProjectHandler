"""E07.2.2.1, Task 4: o emparelhamento do ESTAI não volta ao custo cúbico em página densa.

Conta operações, sem medir tempo: cada contador falha assim que passa do limite, para que uma
regressão não custe minutos na suíte.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest
from tests.unit.test_symbol_reconciliation import _observation, _profile, _result

from zeny_project_handler.application import symbol_reconciliation
from zeny_project_handler.application.symbol_reconciliation import (
    CalibrationPolicy,
    SymbolReconciliation,
    reconcile_symbols,
)
from zeny_project_handler.domain.symbols import ObservacaoSimbolo

_MODELO = _profile("declarative-drawing-model")
_LEGADO = _profile("pymupdf-guys")
_POR_LADO = 100
_PASSO = Decimal("0.00001")


def _pagina_densa() -> tuple[tuple[ObservacaoSimbolo, ...], tuple[ObservacaoSimbolo, ...]]:
    """Todo legado cabe em todo modelo, e a passada de melhor mútuo só acharia um par por vez.

    Os centros dos legados recuam a partir de 0,110 e os dos modelos avançam: todos os legados
    preferem o primeiro modelo livre, e todos os modelos, o primeiro legado livre. As primitivas
    próprias impedem o agrupamento antigo (`_same_occurrence`) de juntar as caixas sobrepostas.
    """
    legados = tuple(
        _observation(
            _LEGADO,
            "ESTAI",
            x=str(Decimal("0.105") - indice * _PASSO),
            y="0.105",
            width="0.010",
            height="0.010",
            primitive=f"legado:{indice}",
        )
        for indice in range(1, _POR_LADO + 1)
    )
    modelos = tuple(
        _observation(
            _MODELO,
            "ESTAI",
            x=str(Decimal("0.100") + indice * _PASSO),
            y="0.100",
            width="0.020",
            height="0.020",
            primitive=f"modelo:{indice}",
        )
        for indice in range(1, _POR_LADO + 1)
    )
    return legados, modelos


def _reconciliar(
    legados: tuple[ObservacaoSimbolo, ...], modelos: tuple[ObservacaoSimbolo, ...]
) -> SymbolReconciliation:
    return reconcile_symbols(
        (_result(_LEGADO, *legados), _result(_MODELO, *modelos)), CalibrationPolicy()
    )


def _contador(limite: int, nome: str) -> Callable[[], int]:
    """Devolve a função que soma uma operação e falha ao passar do limite."""
    total = 0

    def contar() -> int:
        nonlocal total
        total += 1
        if total > limite:
            pytest.fail(f"{nome} passou de {limite} operações: o custo voltou a ser cúbico")
        return total

    return contar


def test_pagina_densa_pareia_cada_legado_com_o_modelo_de_mesma_posicao() -> None:
    legados, modelos = _pagina_densa()

    reconciliacao = _reconciliar(legados, modelos)

    assert {frozenset(o.id for o in item.observations) for item in reconciliacao.occurrences} == {
        frozenset({legado.id, modelo.id}) for legado, modelo in zip(legados, modelos, strict=True)
    }


def test_pagina_densa_nao_recalcula_a_guarda_por_aresta(monkeypatch: pytest.MonkeyPatch) -> None:
    # Recalcular por aresta soma cerca de 2 * n^3 leituras; uma vez por índice, cerca de 2 * n^2.
    legados, modelos = _pagina_densa()
    contar = _contador(20 * _POR_LADO**2, "leitura de atributos")
    original = symbol_reconciliation._attributes

    def contada(observacao: ObservacaoSimbolo) -> dict[str, object]:
        contar()
        return original(observacao)

    monkeypatch.setattr(symbol_reconciliation, "_attributes", contada)

    reconciliacao = _reconciliar(legados, modelos)

    assert len(reconciliacao.occurrences) == _POR_LADO


def test_pagina_densa_nao_repete_passadas_sobre_as_arestas(monkeypatch: pytest.MonkeyPatch) -> None:
    # Passadas repetidas pedem o id a cada aresta de cada passada: cerca de 2/3 * n^3 leituras.
    legados, modelos = _pagina_densa()
    contar = _contador(4 * _POR_LADO**2, "leitura de id")
    original = ObservacaoSimbolo.id

    def contada(observacao: ObservacaoSimbolo) -> str:
        contar()
        return original.fget(observacao)  # type: ignore[attr-defined,no-any-return]

    monkeypatch.setattr(ObservacaoSimbolo, "id", property(contada))

    reconciliacao = _reconciliar(legados, modelos)

    assert len(reconciliacao.occurrences) == _POR_LADO
