"""Ataque ao encerramento por estado (E17, Task 1): token, corridas e ciclo de vida dos receptores.

Complementa ``test_project_panel_encerramento.py`` sem alterá-lo. Toda thread bloqueada num
``Event`` é liberada e juntada num ``try/finally`` (ou no teardown da fábrica de painéis) antes
de destruir o dono: destruir uma ``QThread`` viva aborta o processo (``node down``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event, Timer
from typing import cast

import pytest
from PySide6.QtCore import QCoreApplication, QDeadlineTimer, QEvent, QObject, QThread, Signal
from pytestqt.qtbot import QtBot

from zeny_project_handler_client.ui import project_search, remote_read
from zeny_project_handler_client.ui.project_gateway import ProjectGateway
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_client.ui.project_search import ProjectSearchThread
from zeny_project_handler_client.ui.remote_read import RemoteRequestThread
from zeny_project_handler_contracts.projects import ProjectSummaryListResponse

_PRAZO_BLOQUEIO_S = 30.0
_PRAZO_JUNTAR_MS = 10_000
_PEDIDO_CURTO_MS = 100
_PEDIDO_FOLGADO_MS = 5_000
# Maior que o intervalo de 300 ms da pesquisa agendada por restart_polling().
_FOLGA_SEM_EMISSAO_MS = 600


class _SemServidorError(RuntimeError):
    pass


class _GatewayFalso:
    """Gateway sem servidor; ``session()`` pode bloquear até o teste liberar e conta chamadas."""

    def __init__(self, *, sessao_lenta: bool = False) -> None:
        self.sessao_lenta = sessao_lenta
        self.entrou = Event()
        self.liberar = Event()
        self.chamadas = 0

    def session(self) -> object:
        self.chamadas += 1
        if self.sessao_lenta:
            self.entrou.set()
            self.liberar.wait(_PRAZO_BLOQUEIO_S)
        raise _SemServidorError("sem servidor no teste")

    def list_projects(self, *, limit: int = 200, offset: int = 0) -> object:
        raise _SemServidorError("sem servidor no teste")

    def search_projects(self, query: str, *, limit: int = 200, offset: int = 0) -> object:
        raise _SemServidorError("sem servidor no teste")


class _ViewerFalso(QObject):
    page_changed = Signal(str)
    folha_atual = 0


class _Bloqueio:
    """Leitura que bloqueia num ``Event`` até o teste liberar."""

    def __init__(self) -> None:
        self.entrou = Event()
        self.liberar = Event()

    def __call__(self) -> ProjectSummaryListResponse:
        self.entrou.set()
        self.liberar.wait(_PRAZO_BLOQUEIO_S)
        raise _SemServidorError("leitura liberada pelo teste")


def _resposta_imediata() -> ProjectSummaryListResponse:
    raise _SemServidorError("resposta imediata")


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


def _novo_painel(gateway: _GatewayFalso, caminho: Path) -> ProjectPanelWidget:
    return ProjectPanelWidget(
        gateway=cast(ProjectGateway, gateway),
        viewer=_ViewerFalso(),
        review_panel=object(),
        state_path=caminho,
    )


@pytest.fixture
def criar_painel(qtbot: QtBot, tmp_path: Path) -> Iterator[PainelFactory]:
    criados: list[tuple[ProjectPanelWidget, _GatewayFalso]] = []

    def criar(gateway: _GatewayFalso) -> ProjectPanelWidget:
        painel = _novo_painel(gateway, tmp_path / f"painel-{len(criados)}.ini")
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
            painel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _contar_emissoes(painel: ProjectPanelWidget) -> list[int]:
    emissoes: list[int] = []
    painel.rede_encerrada.connect(lambda: emissoes.append(1))
    return emissoes


def _esperar_n_emissoes(qtbot: QtBot, emissoes: list[int], total: int) -> None:
    qtbot.waitUntil(lambda: len(emissoes) == total)


def _observacao(painel: ProjectPanelWidget) -> QThread:
    thread = painel._global_poll_thread
    assert thread is not None
    return thread


def _sem_nada_rodando(painel: ProjectPanelWidget) -> None:
    assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
    _drenar_eventos()
    assert not painel.rede_ativa()


def _receptores() -> tuple[int, int]:
    """Receptores atuais do ``terminou`` dos dois registros (leituras, pesquisas)."""
    return (
        remote_read.notificador_leituras._criado().receivers("2terminou()"),
        project_search.notificador_pesquisas._criado().receivers("2terminou()"),
    )


# ---------------------------------------------------------------------------------------------
# Token próprio: perda de conexão (shutdown_polling) não cancela; só restart_polling cancela.
# ---------------------------------------------------------------------------------------------


def test_shutdown_repetido_nao_cancela_o_pedido_e_emite_uma_vez(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        for _ in range(3):
            assert painel.shutdown_polling(0) is False
            QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        gateway.liberar.set()
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_perda_e_volta_da_conexao_cancelam_o_pedido(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    velha = _observacao(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        painel.shutdown_polling(0)  # connection_lost
        painel.restart_polling()  # reconexão
    finally:
        gateway.liberar.set()
        assert velha.wait(_PRAZO_JUNTAR_MS)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == []


def test_pedido_novo_depois_do_restart_emite_uma_vez(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False  # pedido A
        painel.restart_polling()  # cancela A
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False  # pedido B
        assert emissoes == []
    finally:
        gateway.liberar.set()
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_restart_sem_pedido_pendente_nao_emite(qtbot: QtBot, criar_painel: PainelFactory) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    painel.restart_polling()
    painel.restart_polling()
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == []


def test_restart_depois_da_emissao_nao_emite_de_novo(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    painel.restart_polling()
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_restart_com_observacao_antiga_viva_retoma_a_observacao(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    """Reconexão com a observação antiga ainda em curso não pode deixar o painel sem observar.

    Perda de conexão com o servidor lento: ``shutdown_polling`` vence o prazo (``False``), a
    reconexão chama ``restart_polling`` com a thread antiga viva e ela sai sem iniciar outra; a
    antiga já recebeu o stop e morre. Resultado: ninguém consulta ``session()`` de novo.
    """
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.shutdown_polling(0) is False
        painel.restart_polling()
    finally:
        gateway.liberar.set()
        assert velha.wait(_PRAZO_JUNTAR_MS)
    _drenar_eventos()
    chamadas_na_morte = gateway.chamadas
    qtbot.waitUntil(lambda: gateway.chamadas > chamadas_na_morte, timeout=3_000)


# ---------------------------------------------------------------------------------------------
# Corrida entre _dispose (registros) e _conferir_encerramento (finished da observação).
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("repeticao", range(8))
def test_termino_simultaneo_da_observacao_e_da_leitura_emite_uma_vez(
    qtbot: QtBot, criar_painel: PainelFactory, repeticao: int
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    leitura = _Bloqueio()
    pesquisa_leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    pesquisa = ProjectSearchThread(0, "123", pesquisa_leitura)
    principal = QThread.currentThread()
    vistos: list[tuple[bool, bool]] = []

    def ao_encerrar() -> None:
        vistos.append((QThread.currentThread() is principal, painel.rede_ativa()))

    painel.rede_encerrada.connect(ao_encerrar)
    remota.launch()
    pesquisa.launch()
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        qtbot.waitUntil(leitura.entrou.is_set)
        qtbot.waitUntil(pesquisa_leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
    finally:
        gateway.liberar.set()
        leitura.liberar.set()
        pesquisa_leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
        assert pesquisa.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: len(vistos) >= 1)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    # Uma emissão, na thread da UI, com tudo parado no instante em que o sinal sai.
    assert vistos == [(True, False)]


def test_leitura_termina_antes_da_observacao_e_nada_sai_cedo(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
        # O _dispose da leitura já avisou o painel; a observação ainda bloqueia.
        qtbot.waitUntil(lambda: remota not in remote_read._RUNNING)
        qtbot.wait(50)
        assert emissoes == []
        assert painel.rede_ativa()
    finally:
        gateway.liberar.set()
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_membro_terminado_mas_nao_descartado_nao_segura_o_painel(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    _sem_nada_rodando(painel)
    emissoes = _contar_emissoes(painel)
    remota = RemoteRequestThread(0, _resposta_imediata)
    pesquisa = ProjectSearchThread(0, "123", _resposta_imediata)
    remota.launch()
    pesquisa.launch()
    assert remota.wait(_PRAZO_JUNTAR_MS)
    assert pesquisa.wait(_PRAZO_JUNTAR_MS)
    # Terminaram, mas o _dispose em fila ainda não rodou: continuam nos registros.
    assert remota in remote_read._RUNNING
    assert pesquisa in project_search._RUNNING_SEARCHES

    assert painel.rede_ativa() is False
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
    assert emissoes == []

    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    # Os _dispose chegaram depois do pedido e não geraram emissão extra.
    assert remota not in remote_read._RUNNING
    assert pesquisa not in project_search._RUNNING_SEARCHES
    assert emissoes == [1]


def test_cada_thread_dos_registros_notifica_exatamente_uma_vez(qtbot: QtBot) -> None:
    contagem = {"leituras": 0, "pesquisas": 0}

    def leitura_terminou() -> None:
        contagem["leituras"] += 1

    def pesquisa_terminou() -> None:
        contagem["pesquisas"] += 1

    remote_read.notificador_leituras.terminou.connect(leitura_terminou)
    project_search.notificador_pesquisas.terminou.connect(pesquisa_terminou)
    try:
        for indice in range(10):
            RemoteRequestThread(indice, _resposta_imediata).launch()
            ProjectSearchThread(indice, "123", _resposta_imediata).launch()
        qtbot.waitUntil(
            lambda: contagem == {"leituras": 10, "pesquisas": 10},
            timeout=_PRAZO_JUNTAR_MS,
        )
        _juntar_registros()
        qtbot.wait(100)
        assert contagem == {"leituras": 10, "pesquisas": 10}
    finally:
        _juntar_registros()
        remote_read.notificador_leituras.terminou.disconnect(leitura_terminou)
        project_search.notificador_pesquisas.terminou.disconnect(pesquisa_terminou)


# ---------------------------------------------------------------------------------------------
# Thread remota de outro painel como a última viva.
# ---------------------------------------------------------------------------------------------


def test_dois_paineis_pedem_e_esperam_a_mesma_leitura_remota(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel_a = criar_painel(_GatewayFalso())
    painel_b = criar_painel(_GatewayFalso())
    painel_c = criar_painel(_GatewayFalso())
    emissoes_a = _contar_emissoes(painel_a)
    emissoes_b = _contar_emissoes(painel_b)
    emissoes_c = _contar_emissoes(painel_c)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel_a.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert painel_b.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        QCoreApplication.processEvents()
        qtbot.wait(50)
        assert emissoes_a == emissoes_b == []
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes_a == [1] and emissoes_b == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    # Quem não pediu nada não é avisado.
    assert (emissoes_a, emissoes_b, emissoes_c) == ([1], [1], [])


def test_pedido_do_painel_a_nao_e_cancelado_pelo_restart_do_painel_b(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel_a = criar_painel(_GatewayFalso())
    painel_b = criar_painel(_GatewayFalso())
    emissoes_a = _contar_emissoes(painel_a)
    emissoes_b = _contar_emissoes(painel_b)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel_a.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert painel_b.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        painel_b.restart_polling()
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes_a == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert (emissoes_a, emissoes_b) == ([1], [])


def test_thread_lancada_depois_do_pedido_atrasa_a_emissao(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    primeira = _Bloqueio()
    segunda = _Bloqueio()
    remota_1 = RemoteRequestThread(0, primeira)
    remota_2 = RemoteRequestThread(1, segunda)
    remota_1.launch()
    try:
        qtbot.waitUntil(primeira.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        # Uma leitura nova, nascida depois do pedido (por exemplo, recarga do mercado).
        remota_2.launch()
        qtbot.waitUntil(segunda.entrou.is_set)
        primeira.liberar.set()
        assert remota_1.wait(_PRAZO_JUNTAR_MS)
        qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
        assert emissoes == []
        assert painel.rede_ativa()
    finally:
        primeira.liberar.set()
        segunda.liberar.set()
        # A primeira já saiu do registro e foi destruída; junta-se o que restar pelo registro.
        assert remote_read.aguardar_leituras(QDeadlineTimer(_PRAZO_JUNTAR_MS))
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


# ---------------------------------------------------------------------------------------------
# Painel destruído com pedido pendente: nenhum slot sobre objeto apagado.
# ---------------------------------------------------------------------------------------------


def test_painel_destruido_com_pedido_sem_threads_nao_dispara_o_agendamento(
    qtbot: QtBot, tmp_path: Path
) -> None:
    gateway = _GatewayFalso()
    painel = _novo_painel(gateway, tmp_path / "destruido-sem-threads.ini")
    emissoes = _contar_emissoes(painel)
    base = _receptores()
    assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
    _drenar_eventos()
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
    # O QTimer.singleShot(0, ...) do pedido ainda está na fila quando o painel morre.
    painel.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    _drenar_eventos()
    qtbot.wait(50)
    assert emissoes == []
    assert _receptores() == base


def test_painel_destruido_com_pedido_pendente_solta_o_receptor_dos_registros(
    qtbot: QtBot, tmp_path: Path
) -> None:
    gateway = _GatewayFalso()
    painel = _novo_painel(gateway, tmp_path / "destruido-com-leitura.ini")
    base = _receptores()
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    pesquisa_leitura = _Bloqueio()
    pesquisa = ProjectSearchThread(0, "123", pesquisa_leitura)
    remota.launch()
    pesquisa.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        qtbot.waitUntil(pesquisa_leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert _receptores() == (base[0] + 1, base[1] + 1)
        # A observação é do painel e para antes; as leituras sem pai continuam vivas.
        assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
        painel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        # Destruído o painel, o notificador de módulo não pode manter receptor dele.
        assert _receptores() == base
    finally:
        leitura.liberar.set()
        pesquisa_leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
        assert pesquisa.wait(_PRAZO_JUNTAR_MS)
    _drenar_eventos()
    qtbot.wait(50)
    assert not remote_read.leituras_ativas()
    assert not project_search.pesquisas_ativas()


# ---------------------------------------------------------------------------------------------
# Ciclo de vida dos receptores: ligado só com pedido pendente.
# ---------------------------------------------------------------------------------------------


def test_receptores_so_existem_enquanto_o_pedido_esta_pendente(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    base = _receptores()
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert _receptores() == base  # sem pedido, nada ligado
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert _receptores() == (base[0] + 1, base[1] + 1)
        # Pedido sobreposto não liga em dobro.
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert _receptores() == (base[0] + 1, base[1] + 1)
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: len(emissoes) >= 1)
    assert _receptores() == base


def test_restart_solta_os_receptores_dos_registros(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    base = _receptores()
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert _receptores() == (base[0] + 1, base[1] + 1)
        painel.restart_polling()
        assert _receptores() == base
        # Cancelar de novo, sem nada ligado, não pode estourar na desconexão.
        painel.restart_polling()
        assert _receptores() == base
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)


def test_pedido_sem_threads_solta_os_receptores_depois_de_emitir(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    base = _receptores()
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    assert _receptores() == base


# ---------------------------------------------------------------------------------------------
# Notificadores: criados só na thread principal, e só no primeiro uso.
# ---------------------------------------------------------------------------------------------


def test_notificadores_vivem_na_thread_principal(qtbot: QtBot) -> None:
    RemoteRequestThread(0, _resposta_imediata).launch()
    ProjectSearchThread(0, "123", _resposta_imediata).launch()
    _juntar_registros()
    principal = QCoreApplication.instance().thread()  # type: ignore[union-attr]
    assert remote_read.notificador_leituras._criado().thread() is principal
    assert project_search.notificador_pesquisas._criado().thread() is principal


_SCRIPT_PRIMEIRO_USO = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from PySide6.QtCore import QCoreApplication, QDeadlineTimer
    from PySide6.QtWidgets import QApplication

    from zeny_project_handler_client.ui import project_search, remote_read
    from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
    from zeny_project_handler_client.ui.remote_read import RemoteRequestThread
    from PySide6.QtCore import QObject, Signal

    # Importar nada cria QObject de módulo.
    assert remote_read.notificador_leituras._objeto is None
    assert project_search.notificador_pesquisas._objeto is None

    app = QApplication([])
    principal = app.thread()

    class Gateway:
        def session(self):
            raise RuntimeError("sem servidor")

    class Viewer(QObject):
        page_changed = Signal(str)
        folha_atual = 0

    painel = ProjectPanelWidget(
        gateway=Gateway(), viewer=Viewer(), review_panel=object(),
        state_path=Path(sys.argv[2]),
    )
    # Construir o painel também não cria.
    assert remote_read.notificador_leituras._objeto is None
    assert project_search.notificador_pesquisas._objeto is None

    if sys.argv[1] == "pedido":
        assert painel.pedir_encerramento(5000) is True
    else:
        thread = RemoteRequestThread(0, lambda: None)
        thread.launch()
        assert thread.wait(5000)
        assert painel.shutdown_polling(5000)

    assert remote_read.notificador_leituras._objeto is not None
    assert remote_read.notificador_leituras._objeto.thread() is principal
    for _ in range(5):
        QCoreApplication.processEvents()
    painel.shutdown_polling(5000)
    assert remote_read.aguardar_leituras(QDeadlineTimer(5000))
    assert project_search.aguardar_pesquisas(QDeadlineTimer(5000))
    for _ in range(5):
        QCoreApplication.processEvents()
    painel.deleteLater()
    QCoreApplication.sendPostedEvents(None, 52)
    print("OK")
    """
)


@pytest.mark.parametrize("primeiro_uso", ["pedido", "launch"])
def test_notificador_nasce_so_no_primeiro_uso_e_na_thread_principal(
    tmp_path: Path, primeiro_uso: str
) -> None:
    ambiente = dict(os.environ)
    ambiente["QT_QPA_PLATFORM"] = "offscreen"
    # O mesmo código que este processo importou (worktree da tarefa), não outro instalado.
    ambiente["PYTHONPATH"] = str(Path(remote_read.__file__).resolve().parents[2])
    processo = subprocess.run(
        [sys.executable, "-c", _SCRIPT_PRIMEIRO_USO, primeiro_uso, str(tmp_path / "estado.ini")],
        capture_output=True,
        text=True,
        timeout=120,
        env=ambiente,
        cwd=tmp_path,
        check=False,
    )
    assert processo.returncode == 0, processo.stdout + processo.stderr
    assert "OK" in processo.stdout


# ---------------------------------------------------------------------------------------------
# Pedido sem nada rodando, reentrada, sequência, sobreposição.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("prazo_ms", [0, -1, 1, _PEDIDO_FOLGADO_MS], ids=lambda ms: f"prazo{ms}")
def test_pedido_sem_nada_rodando_emite_assincrono_com_qualquer_prazo(
    qtbot: QtBot, criar_painel: PainelFactory, prazo_ms: int
) -> None:
    painel = criar_painel(_GatewayFalso())
    _sem_nada_rodando(painel)
    emissoes = _contar_emissoes(painel)

    assert painel.pedir_encerramento(prazo_ms) is True
    assert emissoes == []
    assert painel.rede_ativa() is False
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_pedido_dentro_do_slot_da_emissao_emite_de_novo_sem_laco(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    _sem_nada_rodando(painel)
    emissoes: list[int] = []
    reentradas: list[bool] = []

    def ao_encerrar() -> None:
        emissoes.append(1)
        if len(emissoes) == 1:
            reentradas.append(painel.pedir_encerramento(_PEDIDO_FOLGADO_MS))
            # A segunda emissão não pode sair dentro desta chamada.
            assert len(emissoes) == 1

    painel.rede_encerrada.connect(ao_encerrar)
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
    qtbot.waitUntil(lambda: len(emissoes) == 2)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1, 1]
    assert reentradas == [True]


def test_pedidos_em_sequencia_com_thread_viva_emitem_uma_vez_cada(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    for numero in (1, 2):
        leitura = _Bloqueio()
        remota = RemoteRequestThread(numero, leitura)
        remota.launch()
        try:
            qtbot.waitUntil(leitura.entrou.is_set)
            assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
            assert len(emissoes) == numero - 1
        finally:
            leitura.liberar.set()
            assert remota.wait(_PRAZO_JUNTAR_MS)
        _esperar_n_emissoes(qtbot, emissoes, numero)
        qtbot.wait(100)
        assert len(emissoes) == numero


def test_pedidos_sobrepostos_nunca_ficam_sem_emissao_nem_antes_da_hora(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        gateway.liberar.set()
    qtbot.waitUntil(lambda: len(emissoes) >= 1)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    # Fusão (1) ou uma por pedido (3) são ambas defensáveis; zero ou emissão tardia, não.
    assert len(emissoes) in (1, 3)
    assert not painel.rede_ativa()


# ---------------------------------------------------------------------------------------------
# Espera: prazo único, espera de verdade e interrupção entregue.
# ---------------------------------------------------------------------------------------------


def test_prazo_e_unico_para_observacao_leituras_e_pesquisas(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    prazo_ms = 1_000
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    leitura = _Bloqueio()
    pesquisa_leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    pesquisa = ProjectSearchThread(0, "123", pesquisa_leitura)
    remota.launch()
    pesquisa.launch()
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        qtbot.waitUntil(leitura.entrou.is_set)
        qtbot.waitUntil(pesquisa_leitura.entrou.is_set)
        inicio = time.monotonic()
        assert painel.pedir_encerramento(prazo_ms) is False
        gasto = time.monotonic() - inicio
        # Três esperas de 1 s em série dariam ~3 s; o prazo é um só, no total.
        assert gasto < 2.2
    finally:
        gateway.liberar.set()
        leitura.liberar.set()
        pesquisa_leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
        assert pesquisa.wait(_PRAZO_JUNTAR_MS)


def test_pedido_espera_de_verdade_e_volta_assim_que_tudo_para(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    qtbot.waitUntil(gateway.entrou.is_set)
    qtbot.waitUntil(leitura.entrou.is_set)

    def liberar_tudo() -> None:
        gateway.liberar.set()
        leitura.liberar.set()

    liberador = Timer(0.3, liberar_tudo)
    liberador.start()
    try:
        inicio = time.monotonic()
        assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
        gasto = time.monotonic() - inicio
        assert gasto < _PEDIDO_FOLGADO_MS / 1_000 - 0.5
    finally:
        liberador.join()
        gateway.liberar.set()
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    assert emissoes == []
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_pedido_logo_depois_do_launch_junta_a_thread_e_emite_uma_vez(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    remota = RemoteRequestThread(0, _resposta_imediata)
    pesquisa = ProjectSearchThread(0, "123", _resposta_imediata)
    # Sem esperar a thread chegar ao run(): start() já a marca em execução.
    remota.launch()
    pesquisa.launch()
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
    assert painel.rede_ativa() is False
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]
    assert not remote_read._RUNNING
    assert not project_search._RUNNING_SEARCHES


def test_pesquisa_agendada_pelo_digitar_nao_lanca_thread_depois_do_pedido(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    painel._project_search.setText("123")
    assert painel._search_timer.isActive()

    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
    assert not painel._search_timer.isActive()
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert painel._search_thread is None
    assert not project_search.pesquisas_ativas()
    assert emissoes == [1]


def test_interromper_e_aguardar_com_membro_terminado_nao_falham(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    remota = RemoteRequestThread(0, _resposta_imediata)
    remota.launch()
    assert remota.wait(_PRAZO_JUNTAR_MS)
    # Membro terminado e ainda no registro: interromper e esperar não podem falhar.
    remote_read.interromper_leituras()
    assert remote_read.aguardar_leituras(QDeadlineTimer(0)) is True
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True
