"""Encerramento por estado: o painel avisa quando nenhuma thread de rede ainda roda.

Toda thread bloqueada num ``Event`` é liberada e juntada no ``finally`` (ou no teardown do
painel) antes de destruir o dono: destruir uma ``QThread`` viva aborta o processo.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from threading import Event
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
    """Gateway sem servidor; ``session()`` pode bloquear até o teste liberar."""

    def __init__(self, *, sessao_lenta: bool = False) -> None:
        self.sessao_lenta = sessao_lenta
        self.entrou = Event()
        self.liberar = Event()

    def session(self) -> object:
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


def _juntar_registros() -> None:
    prazo = QDeadlineTimer(_PRAZO_JUNTAR_MS)
    assert remote_read.aguardar_leituras(prazo)
    assert project_search.aguardar_pesquisas(prazo)
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


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
            painel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _contar_emissoes(painel: ProjectPanelWidget) -> list[int]:
    emissoes: list[int] = []
    painel.rede_encerrada.connect(lambda: emissoes.append(1))
    return emissoes


def _observacao(painel: ProjectPanelWidget) -> QThread:
    thread = painel._global_poll_thread
    assert thread is not None
    return thread


def test_pedido_com_observacao_lenta_devolve_false_e_emite_uma_vez(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert painel.rede_ativa()
        QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        gateway.liberar.set()
    qtbot.waitUntil(lambda: emissoes == [1])
    assert not painel.rede_ativa()
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_pedido_sem_threads_emite_assincrono(qtbot: QtBot, criar_painel: PainelFactory) -> None:
    painel = criar_painel(_GatewayFalso())
    assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not painel.rede_ativa()
    emissoes = _contar_emissoes(painel)

    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS) is True

    assert emissoes == []
    qtbot.waitUntil(lambda: emissoes == [1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1]


def test_pesquisa_em_curso_entra_no_encerramento(qtbot: QtBot, criar_painel: PainelFactory) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    pesquisa = ProjectSearchThread(0, "123", leitura)
    recebidos: list[object] = []
    pesquisa.received.connect(lambda *args: recebidos.append(args))
    pesquisa.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert project_search.pesquisas_ativas()
        assert painel.rede_ativa()
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert pesquisa.isInterruptionRequested()
        QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        leitura.liberar.set()
        assert pesquisa.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    assert not project_search.pesquisas_ativas()
    assert recebidos == []


def test_leitura_remota_em_curso_entra_no_encerramento(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    recebidos: list[object] = []
    remota.received.connect(lambda *args: recebidos.append(args))
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert remote_read.leituras_ativas()
        assert painel.rede_ativa()
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert remota.isInterruptionRequested()
        QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    assert not remote_read.leituras_ativas()
    assert recebidos == []


def test_restart_cancela_o_pedido_e_a_thread_velha_nao_emite(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    velha = _observacao(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        painel.restart_polling()
    finally:
        gateway.liberar.set()
        assert velha.wait(_PRAZO_JUNTAR_MS)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == []


def test_dois_pedidos_seguidos_emitem_uma_vez_cada(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)

    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    assert painel.pedir_encerramento(_PEDIDO_FOLGADO_MS)
    assert emissoes == [1]
    qtbot.waitUntil(lambda: emissoes == [1, 1])
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == [1, 1]


def test_shutdown_por_perda_de_conexao_nao_cancela_o_pedido(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    emissoes = _contar_emissoes(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        # Perda de conexão: connection_lost -> set_connection_available(False) -> shutdown_polling.
        assert painel.shutdown_polling(0) is False
        QCoreApplication.processEvents()
        assert emissoes == []
    finally:
        gateway.liberar.set()
    qtbot.waitUntil(lambda: emissoes == [1])


def test_leitura_remota_de_outro_painel_e_a_ultima_viva(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    observacao = _observacao(painel)
    leitura = _Bloqueio()
    # Sem pai: como a do mercado, da documentação ou do GMAX, não pertence ao painel.
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        assert observacao.wait(_PRAZO_JUNTAR_MS)
        # O finished em fila da observação chega e confere: a leitura ainda roda.
        qtbot.wait(50)
        assert emissoes == []
        assert painel.rede_ativa()
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: emissoes == [1])
    assert not painel.rede_ativa()


def test_ativas_conta_so_threads_rodando(qtbot: QtBot) -> None:
    def resposta() -> ProjectSummaryListResponse:
        raise _SemServidorError("resposta imediata")

    remota = RemoteRequestThread(0, resposta)
    pesquisa = ProjectSearchThread(0, "123", resposta)
    remota.launch()
    pesquisa.launch()
    assert remota.wait(_PRAZO_JUNTAR_MS)
    assert pesquisa.wait(_PRAZO_JUNTAR_MS)

    # Terminaram, mas o _dispose em fila ainda não rodou.
    assert remota in remote_read._RUNNING
    assert pesquisa in project_search._RUNNING_SEARCHES
    assert remote_read.leituras_ativas() is False
    assert project_search.pesquisas_ativas() is False

    QCoreApplication.processEvents()
    assert remota not in remote_read._RUNNING
    assert pesquisa not in project_search._RUNNING_SEARCHES


def test_notificadores_avisam_depois_de_retirar_do_registro(qtbot: QtBot) -> None:
    def resposta() -> ProjectSummaryListResponse:
        raise _SemServidorError("resposta imediata")

    vistos: list[tuple[str, bool]] = []
    remota = RemoteRequestThread(0, resposta)
    pesquisa = ProjectSearchThread(0, "123", resposta)

    def leitura_terminou() -> None:
        vistos.append(("leitura", remota in remote_read._RUNNING))

    def pesquisa_terminou() -> None:
        vistos.append(("pesquisa", pesquisa in project_search._RUNNING_SEARCHES))

    remote_read.notificador_leituras.terminou.connect(leitura_terminou)
    project_search.notificador_pesquisas.terminou.connect(pesquisa_terminou)
    try:
        remota.launch()
        pesquisa.launch()
        qtbot.waitUntil(lambda: len(vistos) == 2)
    finally:
        # O _dispose já agendou a destruição; quem ainda rodar é juntado pelo registro.
        _juntar_registros()
        remote_read.notificador_leituras.terminou.disconnect(leitura_terminou)
        project_search.notificador_pesquisas.terminou.disconnect(pesquisa_terminou)
    assert sorted(vistos) == [("leitura", False), ("pesquisa", False)]


def test_restart_desliga_o_painel_dos_registros(qtbot: QtBot, criar_painel: PainelFactory) -> None:
    painel = criar_painel(_GatewayFalso())
    emissoes = _contar_emissoes(painel)
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        painel.restart_polling()
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert emissoes == []


def test_painel_destruido_com_pedido_pendente_nao_recebe_o_termino(
    qtbot: QtBot, tmp_path: Path
) -> None:
    gateway = _GatewayFalso()
    painel = ProjectPanelWidget(
        gateway=cast(ProjectGateway, gateway),
        viewer=_ViewerFalso(),
        review_panel=object(),
        state_path=tmp_path / "destruido.ini",
    )
    leitura = _Bloqueio()
    remota = RemoteRequestThread(0, leitura)
    remota.launch()
    try:
        qtbot.waitUntil(leitura.entrou.is_set)
        assert painel.pedir_encerramento(_PEDIDO_CURTO_MS) is False
        # A observação é do painel e para; a leitura sem pai continua viva.
        assert painel.shutdown_polling(_PRAZO_JUNTAR_MS)
        painel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    finally:
        leitura.liberar.set()
        assert remota.wait(_PRAZO_JUNTAR_MS)
    # O _dispose avisa o notificador do módulo, já sem o painel destruído ligado a ele.
    QCoreApplication.processEvents()
    assert not remote_read.leituras_ativas()


def test_restart_com_observacao_antiga_viva_so_inicia_a_nova_quando_ela_termina(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.shutdown_polling(0) is False
        painel.restart_polling()
        # Nunca duas observações ao mesmo tempo: a nova espera o finished da antiga.
        assert painel._global_poll_thread is velha
    finally:
        gateway.liberar.set()
        assert velha.wait(_PRAZO_JUNTAR_MS)
    qtbot.waitUntil(lambda: painel._global_poll_thread is not velha)
    nova = _observacao(painel)
    assert nova.isRunning()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert painel._global_poll_thread is nova


def test_interrupcao_depois_do_restart_adiado_anula_o_reinicio(
    qtbot: QtBot, criar_painel: PainelFactory
) -> None:
    gateway = _GatewayFalso(sessao_lenta=True)
    painel = criar_painel(gateway)
    velha = _observacao(painel)
    try:
        qtbot.waitUntil(gateway.entrou.is_set)
        assert painel.shutdown_polling(0) is False
        painel.restart_polling()
        # Nova perda de conexão antes de a antiga terminar.
        assert painel.shutdown_polling(0) is False
    finally:
        gateway.liberar.set()
        assert velha.wait(_PRAZO_JUNTAR_MS)
    qtbot.wait(_FOLGA_SEM_EMISSAO_MS)
    assert not painel.rede_ativa()
