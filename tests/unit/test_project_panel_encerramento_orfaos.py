"""Reinício da observação global: nunca duas observações vivas, nunca uma ressuscitada (E17).

Cobre o ``finished`` enfileirado de uma observação antiga que chega depois de um novo
``restart_polling()`` e o reinício adiado por geração. Toda thread bloqueada num ``Event`` é
liberada e juntada antes de destruir o dono: destruir uma ``QThread`` viva aborta o processo.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event, Lock, get_ident
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QDeadlineTimer, QEvent, QObject, QThread, Signal
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui import project_search, remote_read
from zeny_project_handler_client.ui.project_gateway import ProjectGateway
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget

_PRAZO_BLOQUEIO_S = 30.0
_PRAZO_JUNTAR_MS = 10_000
# Maior que o intervalo de 300 ms da pesquisa agendada por restart_polling(), e menor que os
# 400 ms de espera do laço da observação entre duas consultas de sessão.
_FOLGA_ASSENTAR_MS = 250
_FOLGA_SEM_REINICIO_MS = 700


class _SemServidorError(RuntimeError):
    pass


class _GatewayFalso:
    """Gateway sem servidor: ``session()`` bloqueia até ``liberar`` e registra quem a chamou."""

    def __init__(self) -> None:
        self.entrou = Event()
        self.liberar = Event()
        self._trava = Lock()
        self._threads: set[int] = set()

    def session(self) -> object:
        with self._trava:
            self._threads.add(get_ident())
        self.entrou.set()
        self.liberar.wait(_PRAZO_BLOQUEIO_S)
        raise _SemServidorError("sem servidor no teste")

    def threads_que_consultaram(self) -> int:
        with self._trava:
            return len(self._threads)

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> object:
        raise _SemServidorError("sem servidor no teste")

    def search_projects(self, query: str, *, limit: int = 200, offset: int = 0) -> object:
        raise _SemServidorError("sem servidor no teste")


class _ViewerFalso(QObject):
    page_changed = Signal(str)
    folha_atual = 0


def _drenar_eventos() -> None:
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _juntar_registros() -> None:
    prazo = QDeadlineTimer(_PRAZO_JUNTAR_MS)
    assert remote_read.aguardar_leituras(prazo)
    assert project_search.aguardar_pesquisas(prazo)
    _drenar_eventos()


@pytest.fixture(autouse=True)
def _registros_limpos(qtbot: QtBot) -> Iterator[None]:
    _juntar_registros()
    yield
    _juntar_registros()


PainelFactory = Callable[[_GatewayFalso], ProjectPanelWidget]


@pytest.fixture
def criar_painel(qtbot: QtBot, tmp_path: Path) -> Iterator[PainelFactory]:
    criados: list[tuple[ProjectPanelWidget, _GatewayFalso]] = []

    def criar(gateway: _GatewayFalso) -> ProjectPanelWidget:
        painel = ProjectPanelWidget(
            gateway=cast(ProjectGateway, gateway),
            viewer=_ViewerFalso(),
            review_panel=object(),
            state_path=tmp_path / f"painel-{len(criados)}.ini",
        )
        criados.append((painel, gateway))
        return painel

    try:
        yield criar
    finally:
        for painel, gateway in criados:
            gateway.liberar.set()
            assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
        _juntar_registros()
        for painel, _gateway in criados:
            # Observação ressuscitada por um finished atrasado (bug) é juntada: destruir o painel
            # com ela viva abortaria o processo. O teste que a provocou já falhou pela asserção.
            painel._global_poll_stop.set()
            for thread in _observacoes_rodando(painel):
                assert thread.wait(_PRAZO_JUNTAR_MS)
        _juntar_registros()
        for painel, _gateway in criados:
            painel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _observacao(painel: ProjectPanelWidget) -> QThread:
    thread = painel._global_poll_thread
    assert thread is not None
    return thread


def _observacoes_rodando(painel: ProjectPanelWidget) -> list[QThread]:
    """Threads de observação global vivas: ``QThread`` pura filha do painel (pesquisa é subclasse)."""
    return [
        thread
        for thread in painel.findChildren(QThread)
        if type(thread) is QThread and thread.isRunning()
    ]


def _encerrar_e_conferir_que_nada_renasce(qtbot: QtBot, painel: ProjectPanelWidget) -> None:
    """Perda de conexão final: os ``finished`` pendentes não podem abrir observação nenhuma."""
    assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
    _drenar_eventos()
    qtbot.wait(_FOLGA_SEM_REINICIO_MS)
    assert _observacoes_rodando(painel) == []


def test_restart_com_observacao_antiga_encerrada_e_finished_enfileirado_nao_duplica(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    """A antiga já morreu, mas o ``finished`` dela ainda está na fila quando o restart chega.

    O restart vê a thread parada e inicia a nova na hora. Quando o ``finished`` atrasado é
    entregue, o ``_retomar_observacao_adiada`` não pode iniciar uma segunda observação.
    """
    gateway = _GatewayFalso()
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    qtbot.waitUntil(gateway.entrou.is_set)
    assert painel.shutdown_polling(0) is False  # stop enviado; a antiga segue referenciada
    gateway.liberar.set()
    # Sem processar eventos: a antiga termina e o finished dela fica enfileirado, sem entrega.
    assert velha.wait(_PRAZO_JUNTAR_MS)
    assert not velha.isRunning()
    assert painel._global_poll_thread is velha

    painel.restart_polling()

    nova = _observacao(painel)
    assert nova is not velha
    assert nova.isRunning()
    # Entrega o finished atrasado da antiga (e o descarte dela) e deixa a nova consultar a sessão.
    _drenar_eventos()
    qtbot.waitUntil(lambda: gateway.threads_que_consultaram() >= 2)
    qtbot.wait(_FOLGA_ASSENTAR_MS)
    assert _observacoes_rodando(painel) == [nova]
    assert painel._global_poll_thread is nova
    assert gateway.threads_que_consultaram() == 2  # a antiga e a nova; nenhuma terceira
    _encerrar_e_conferir_que_nada_renasce(qtbot, painel)


def test_dois_restarts_seguidos_com_antiga_viva_e_parada_iniciam_uma_so_observacao(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    """Dois ``restart_polling`` com a antiga viva e já parada: uma observação, no ``finished``."""
    gateway = _GatewayFalso()
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    qtbot.waitUntil(gateway.entrou.is_set)
    assert painel.shutdown_polling(0) is False

    painel.restart_polling()
    painel.restart_polling()

    # Nada nasce enquanto a antiga vive: só ela roda e só ela consultou a sessão.
    _drenar_eventos()
    qtbot.wait(_FOLGA_ASSENTAR_MS)
    assert painel._global_poll_thread is velha
    assert _observacoes_rodando(painel) == [velha]
    assert gateway.threads_que_consultaram() == 1

    gateway.liberar.set()
    assert velha.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: painel._global_poll_thread is not velha)
    nova = _observacao(painel)
    qtbot.waitUntil(lambda: gateway.threads_que_consultaram() >= 2)
    qtbot.wait(_FOLGA_ASSENTAR_MS)
    assert _observacoes_rodando(painel) == [nova]
    assert painel._global_poll_thread is nova
    assert gateway.threads_que_consultaram() == 2  # a antiga e uma só nova
    _encerrar_e_conferir_que_nada_renasce(qtbot, painel)


def test_finished_atrasado_da_antiga_nao_ressuscita_observacao_parada_depois_do_restart(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    """O restart já iniciou a nova, uma perda de conexão a parou e só então chega o ``finished``.

    A geração mudou com a perda de conexão: o reinício atrasado não pode abrir observação
    nenhuma, mesmo com nenhuma thread rodando para barrá-lo.
    """
    gateway = _GatewayFalso()
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    qtbot.waitUntil(gateway.entrou.is_set)
    assert painel.shutdown_polling(0) is False
    gateway.liberar.set()
    assert velha.wait(_PRAZO_JUNTAR_MS)  # finished da antiga enfileirado, sem entrega

    painel.restart_polling()  # nasce a nova na hora
    nova = _observacao(painel)
    assert nova is not velha
    assert painel.shutdown_polling(_PRAZO_JUNTAR_MS) is True  # perda de conexão: a nova para
    assert not nova.isRunning()

    _drenar_eventos()
    qtbot.wait(_FOLGA_SEM_REINICIO_MS)
    assert _observacoes_rodando(painel) == []
    assert not painel.rede_ativa()
