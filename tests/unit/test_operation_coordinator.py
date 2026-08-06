from __future__ import annotations

import ast
from pathlib import Path
from threading import Event, Thread

import pytest

from zeny_project_handler.application.errors import OperacaoEmAndamentoError
from zeny_project_handler.application.operation_coordinator import (
    CoordenadorOperacoes,
    TipoOperacao,
)

COORDINATOR_SOURCE = (
    Path(__file__).parents[2]
    / "src"
    / "zeny_project_handler"
    / "application"
    / "operation_coordinator.py"
)


def test_context_releases_operation_after_success_and_exception() -> None:
    coordinator = CoordenadorOperacoes()

    with coordinator.adquirir(TipoOperacao.ANALISE) as token:
        assert coordinator.operacao_em_andamento is TipoOperacao.ANALISE
        assert not token.liberado

    assert token.liberado
    assert coordinator.operacao_em_andamento is None

    with (
        pytest.raises(RuntimeError, match="falha simulada"),
        coordinator.adquirir(TipoOperacao.BACKUP),
    ):
        raise RuntimeError("falha simulada")

    assert coordinator.operacao_em_andamento is None


def test_conflict_and_reentry_are_refused_immediately_with_friendly_message() -> None:
    coordinator = CoordenadorOperacoes()
    attempt_finished = Event()
    received: list[OperacaoEmAndamentoError] = []

    def attempt_conflict() -> None:
        try:
            coordinator.adquirir(TipoOperacao.RESTAURACAO)
        except OperacaoEmAndamentoError as error:
            received.append(error)
        finally:
            attempt_finished.set()

    with coordinator.adquirir(TipoOperacao.ANALISE):
        with pytest.raises(OperacaoEmAndamentoError) as reentry:
            coordinator.adquirir(TipoOperacao.ANALISE)
        contender = Thread(target=attempt_conflict)
        contender.start()
        assert attempt_finished.wait(timeout=1)
        contender.join(timeout=1)
        assert not contender.is_alive()

    assert reentry.value.operacao_solicitada == "análise do projeto"
    assert reentry.value.operacao_em_andamento == "análise do projeto"
    assert len(received) == 1
    message = str(received[0])
    assert "restauração do backup" in message
    assert "análise do projeto está em andamento" in message
    assert "Aguarde" in message


def test_repeated_or_stale_release_never_releases_another_operation() -> None:
    coordinator = CoordenadorOperacoes()
    first = coordinator.adquirir(TipoOperacao.IMPORTACAO_PROJETO)

    assert first.liberar()
    assert not first.liberar()
    second = coordinator.adquirir(TipoOperacao.EXPORTACAO_PROJETO)

    assert not first.liberar()
    assert coordinator.operacao_em_andamento is TipoOperacao.EXPORTACAO_PROJETO
    assert second.liberar()
    assert coordinator.operacao_em_andamento is None


def test_observers_receive_transitions_and_cannot_break_token_lifecycle() -> None:
    coordinator = CoordenadorOperacoes()
    transitions: list[TipoOperacao | None] = []
    remove = coordinator.observar(transitions.append)

    def broken_observer(_operation: TipoOperacao | None) -> None:
        raise RuntimeError("observer")

    coordinator.observar(broken_observer)

    with coordinator.adquirir(TipoOperacao.BACKUP):
        assert coordinator.operacao_em_andamento is TipoOperacao.BACKUP

    assert transitions == [None, TipoOperacao.BACKUP, None]
    remove()
    with coordinator.adquirir(TipoOperacao.RESTAURACAO):
        pass
    assert transitions == [None, TipoOperacao.BACKUP, None]


def test_application_coordinator_has_no_qt_or_infrastructure_dependency() -> None:
    tree = ast.parse(COORDINATOR_SOURCE.read_text(encoding="utf-8"))
    modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else ())
    }
    modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    roots = {name.partition(".")[0] for name in modules}

    assert not roots.intersection({"PySide6", "sqlalchemy", "pymupdf"})
    assert not any(name.startswith("zeny_project_handler.adapters") for name in modules)
