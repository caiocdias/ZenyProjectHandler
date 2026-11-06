"""Fechar a janela com o servidor lento adia o fechamento até a rede encerrar.

A janela fica visível e desabilitada enquanto alguma thread de rede ainda roda e só fecha depois,
sem destruir ``QThread`` viva. Os cenários que destroem a janela ou entram no ``app.exec()`` de
verdade rodam num subprocesso, sem o ``tests/conftest.py``: o aborto vira ``returncode != 0`` com
saída legível, em vez de um "worker crashed" do xdist.

Toda thread bloqueada num ``Event`` é liberada e juntada no ``finally`` antes de destruir o dono.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import cast

import pytest
from PySide6.QtCore import SIGNAL, QCoreApplication, QDeadlineTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory
from tests.market_fakes import FakeClassificadorMercado
from tests.remote_gateways import (
    DirectDocumentationGateway,
    DirectPdfViewerGateway,
    DirectPortabilityGateway,
    DirectProjectGateway,
    DirectReviewGateway,
)

from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.connection import ConnectionEvents, ReconnectableGateway
from zeny_project_handler_client.ui import project_search, remote_read
from zeny_project_handler_client.ui.main_window import MainWindow
from zeny_project_handler_client.ui.project_gateway import ProjectGateway, ProjectGatewayError
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_contracts.errors import ErrorCode
from zeny_project_handler_contracts.session import SessionCapabilitiesResponse
from zeny_project_handler_server.composition import ServerRuntime, compose_server_runtime
from zeny_project_handler_server.config import ServerSettings

pytestmark = pytest.mark.integration

_RAIZ = Path(__file__).resolve().parents[2]
_PRAZO_SUBPROCESSO_S = 300
_DURACAO_MAXIMA_EXEC_S = 30.0
_TRECHO_MAXIMO = 4_000
_PRAZO_BLOQUEIO_S = 30.0
_PRAZO_JUNTAR_MS = 10_000
_PRAZO_FECHAR_MS = 10_000
_STATUS_ENCERRANDO = "Encerrando: aguardando o servidor responder"

# Montagem comum aos subprocessos: runtime em memória, gateways diretos e create_application,
# sem o tests/conftest.py (e portanto sem o monkeypatch de 60 s em shutdown_polling).
_MONTAGEM = textwrap.dedent(
    '''
    import threading
    import time
    from pathlib import Path

    from tests.market_fakes import FakeClassificadorMercado
    from tests.remote_gateways import (
        DirectDocumentationGateway,
        DirectPdfViewerGateway,
        DirectPortabilityGateway,
        DirectProjectGateway,
        DirectReviewGateway,
    )
    from zeny_project_handler_client.bootstrap import create_application
    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_server.composition import compose_server_runtime
    from zeny_project_handler_server.config import ServerSettings


    class GatewayLento(DirectProjectGateway):
        """Depois de armada, session() dorme 1,6 s ('lento') ou bloqueia sem timeout ('evento')."""

        def __init__(self, runtime, modo):
            super().__init__(runtime)
            self.modo = modo
            self.armada = False
            self.entrou = threading.Event()
            self.liberar = threading.Event()

        def armar(self):
            self.entrou.clear()
            self.armada = True

        def session(self):
            if self.armada:
                self.entrou.set()
                if self.modo == "evento":
                    self.liberar.wait()
                else:
                    time.sleep(1.6)
            return super().session()


    def montar(diretorio, modo):
        runtime = compose_server_runtime(
            ServerSettings(
                password="senha isolada do cenario de fechamento",
                market_sqlserver_connection_string="fixture-market-connection",
                data_directory=Path(diretorio) / "server",
            ),
            market_classifier=FakeClassificadorMercado(),
        )
        projeto = GatewayLento(runtime, modo)
        app, janela = create_application(
            [],
            settings=ClientSettings(data_directory=Path(diretorio) / "client"),
            pdf_viewer_gateway=DirectPdfViewerGateway(runtime),
            project_gateway=projeto,
            review_gateway=DirectReviewGateway(runtime),
            documentation_gateway=DirectDocumentationGateway(runtime),
            portability_gateway=DirectPortabilityGateway(runtime),
        )
        return app, janela, projeto, runtime
    '''
)

_CENARIO_PYTEST = _MONTAGEM + textwrap.dedent(
    """

    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete


    def test_cenario(tmp_path, qtbot):
        app, janela, projeto, runtime = montar(tmp_path, "lento")
        try:
            janela.show()
            projeto.armar()
            qtbot.waitUntil(projeto.entrou.is_set, timeout=10_000)
            janela.close()
            qtbot.waitUntil(lambda: not janela.isVisible(), timeout=30_000)
            # Destrói o painel e a QThread filha, como o coletor faz com a janela fechada.
            delete(janela)
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        finally:
            projeto.armada = False
            runtime.close()
    """
)

_SCRIPT_EXEC = _MONTAGEM + textwrap.dedent(
    """

    import sys

    from PySide6.QtCore import QTimer


    def principal():
        diretorio, modo = sys.argv[1], sys.argv[2]
        app, janela, projeto, runtime = montar(diretorio, modo)
        marcas = {}
        try:
            janela.show()
            vigia = QTimer()
            vigia.setInterval(20)

            def fechar_quando_a_leitura_lenta_comecar():
                if not projeto.entrou.is_set():
                    return
                vigia.stop()
                marcas["fechou"] = time.monotonic()
                if modo == "evento":
                    QTimer.singleShot(2000, projeto.liberar.set)
                janela.close()
                adiado = getattr(janela, "_fechamento_adiado", None)
                print(f"adiado={adiado} visivel={janela.isVisible()}", flush=True)

            vigia.timeout.connect(fechar_quando_a_leitura_lenta_comecar)
            projeto.armar()
            vigia.start()
            codigo = app.exec()
            print(f"exec={codigo}", flush=True)
            print(f"rede_ativa={janela.project_panel.rede_ativa()}", flush=True)
            print(f"espera_s={time.monotonic() - marcas['fechou']:.2f}", flush=True)
            janela.close()  # como o finally de bootstrap.run()
            return codigo
        finally:
            projeto.armada = False
            projeto.liberar.set()
            janela.project_panel.shutdown_polling(30_000)
            runtime.close()


    sys.exit(principal())
    """
)


def _truncar(texto: str) -> str:
    if len(texto) <= _TRECHO_MAXIMO:
        return texto
    return f"[...]{texto[-_TRECHO_MAXIMO:]}"


def _ambiente() -> dict[str, str]:
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    herdados = [c for c in ambiente.get("PYTHONPATH", "").split(os.pathsep) if c]
    caminhos = os.pathsep.join([*herdados, str(_RAIZ), str(_RAIZ / "src")])
    return ambiente | {"QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": caminhos}


def _executar(comando: list[str]) -> tuple[subprocess.CompletedProcess[str], float]:
    inicio = time.monotonic()
    try:
        resultado = subprocess.run(
            comando,
            cwd=_RAIZ,
            env=_ambiente(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PRAZO_SUBPROCESSO_S,
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        pytest.fail(f"cenário de fechamento passou de {_PRAZO_SUBPROCESSO_S} s: {erro}")
    return resultado, time.monotonic() - inicio


def _saida(resultado: subprocess.CompletedProcess[str]) -> str:
    return (
        f"código {resultado.returncode} (aborto da QThread costuma dar 127/134/3221226505)\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )


def _executar_script_exec(
    tmp_path: Path, modo: str
) -> tuple[subprocess.CompletedProcess[str], float]:
    script = tmp_path / "script" / "fechar_no_exec.py"
    script.parent.mkdir()
    script.write_text(_SCRIPT_EXEC, encoding="utf-8")
    return _executar([sys.executable, str(script), str(tmp_path / "dados"), modo])


def _valor(saida: str, chave: str) -> str:
    for linha in saida.splitlines():
        if linha.startswith(f"{chave}="):
            return linha.split("=", 1)[1]
    raise AssertionError(f"o script não imprimiu {chave}=\n{saida}")


def test_fechar_com_leitura_de_sessao_de_1_6_s_nao_aborta(tmp_path: Path) -> None:
    cenario = tmp_path / "cenario" / "test_cenario_fechamento.py"
    cenario.parent.mkdir()
    cenario.write_text(_CENARIO_PYTEST, encoding="utf-8")
    comando = [
        *[sys.executable, "-m", "pytest", str(cenario), "-q", "-n", "0"],
        *["--rootdir", str(_RAIZ), "-c", str(_RAIZ / "pyproject.toml")],
        # Sem confcutdir a coleta lista cada pasta acima do cenário, inclusive o %TEMP%
        # compartilhado, onde outros testes criam e apagam pastas durante a listagem.
        *["--confcutdir", str(cenario.parent)],
        *["-p", "no:cacheprovider", "--basetemp", str(tmp_path / "base")],
    ]

    resultado, _duracao = _executar(comando)

    assert resultado.returncode == 0, _saida(resultado)
    assert "1 passed" in resultado.stdout


def test_exec_real_sai_depois_da_thread(tmp_path: Path) -> None:
    resultado, duracao = _executar_script_exec(tmp_path, "lento")

    assert resultado.returncode == 0, _saida(resultado)
    assert duracao < _DURACAO_MAXIMA_EXEC_S, _saida(resultado)
    assert "adiado=True visivel=True" in resultado.stdout, _saida(resultado)
    assert _valor(resultado.stdout, "exec") == "0"
    assert _valor(resultado.stdout, "rede_ativa") == "False", _saida(resultado)


def test_gateway_sem_timeout_espera_o_evento(tmp_path: Path) -> None:
    resultado, duracao = _executar_script_exec(tmp_path, "evento")

    assert resultado.returncode == 0, _saida(resultado)
    assert duracao < _DURACAO_MAXIMA_EXEC_S, _saida(resultado)
    assert "adiado=True visivel=True" in resultado.stdout, _saida(resultado)
    assert _valor(resultado.stdout, "rede_ativa") == "False", _saida(resultado)
    # O processo só sai depois que o timer de 2 s libera o evento e a thread termina.
    assert float(_valor(resultado.stdout, "espera_s")) >= 1.9, _saida(resultado)


@dataclass
class _Bloqueio:
    """Depois de armado, ``session()`` bloqueia num ``Event`` até o teste liberar."""

    armado: bool = False
    entrou: Event = field(default_factory=Event)
    liberar: Event = field(default_factory=Event)

    def armar(self) -> None:
        self.entrou.clear()
        self.armado = True

    def aguardar(self) -> None:
        if not self.armado:
            return
        self.entrou.set()
        self.liberar.wait(_PRAZO_BLOQUEIO_S)


@dataclass
class _Janela:
    window: MainWindow
    panel: ProjectPanelWidget
    bloqueio: _Bloqueio
    liberacoes: list[int]


def _contar_liberacoes(window: MainWindow) -> list[int]:
    liberacoes: list[int] = []
    original = window._resource_cleanup

    def contar() -> None:
        liberacoes.append(1)
        original()

    window.set_resource_cleanup(contar)
    return liberacoes


def _preparar(window: MainWindow, bloqueio: _Bloqueio) -> _Janela:
    panel = window.project_panel
    assert isinstance(panel, ProjectPanelWidget)
    return _Janela(window, panel, bloqueio, _contar_liberacoes(window))


def _juntar(janela: _Janela) -> None:
    janela.bloqueio.armado = False
    janela.bloqueio.liberar.set()
    # Sem fechamento concluído a observação continua em laço: interrompe e junta.
    assert janela.panel.shutdown_polling(_PRAZO_JUNTAR_MS)
    prazo = QDeadlineTimer(_PRAZO_JUNTAR_MS)
    assert remote_read.aguardar_leituras(prazo)
    assert project_search.aguardar_pesquisas(prazo)
    QCoreApplication.processEvents()


JanelaFactory = Callable[[], _Janela]


@pytest.fixture
def janela_com_sessao_bloqueavel(
    application_factory: ApplicationFactory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[JanelaFactory]:
    criadas: list[_Janela] = []
    bloqueio = _Bloqueio()
    original = DirectProjectGateway.session

    def sessao(self: DirectProjectGateway) -> SessionCapabilitiesResponse:
        bloqueio.aguardar()
        return original(self)

    monkeypatch.setattr(DirectProjectGateway, "session", sessao)

    def criar() -> _Janela:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / f"janela-{len(criadas)}")
        )
        janela = _preparar(window, bloqueio)
        criadas.append(janela)
        return janela

    try:
        yield criar
    finally:
        for janela in criadas:
            _juntar(janela)


def _adiar_fechamento(qtbot: QtBot, janela: _Janela) -> None:
    janela.window.show()
    janela.bloqueio.armar()
    qtbot.waitUntil(janela.bloqueio.entrou.is_set, timeout=_PRAZO_FECHAR_MS)
    assert not janela.window.close()


def _conexoes_rede_encerrada(panel: ProjectPanelWidget) -> int:
    return panel.receivers(SIGNAL("rede_encerrada()"))


def _contar_pedidos(monkeypatch: pytest.MonkeyPatch, panel: ProjectPanelWidget) -> list[int]:
    pedidos: list[int] = []
    original = panel.pedir_encerramento

    def pedir(timeout_ms: int) -> bool:
        pedidos.append(timeout_ms)
        return original(timeout_ms)

    monkeypatch.setattr(panel, "pedir_encerramento", pedir)
    return pedidos


class _Registros(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.mensagens: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensagens.append(record.getMessage())


def test_fechamento_adiado_fica_visivel_desabilitado_e_fecha_depois(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window = janela.window
    # create_application reconfigura os handlers do cliente: o registro entra depois dele.
    logger = logging.getLogger(MainWindow.__module__)
    registros = _Registros()
    logger.addHandler(registros)
    try:
        _adiar_fechamento(qtbot, janela)

        assert window.isVisible()
        assert not window.isEnabled()
        assert window._fechamento_adiado
        assert window.statusBar().currentMessage() == _STATUS_ENCERRANDO
        assert janela.liberacoes == []

        janela.bloqueio.liberar.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)

        assert janela.liberacoes == [1]
        assert not janela.panel.rede_ativa()
        assert registros.mensagens[0].startswith("Fechamento adiado: aguardando o servidor")
        assert registros.mensagens[-1].startswith("Fechamento adiado concluído em ")
    finally:
        logger.removeHandler(registros)
        _juntar(janela)


def test_dois_closes_rapidos_nao_duplicam_conexao(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window, panel = janela.window, janela.panel
    ocupado = {"analise": True}
    avisos: list[str] = []
    monkeypatch.setattr(ProjectPanelWidget, "processando", property(lambda _s: ocupado["analise"]))
    monkeypatch.setattr(
        ProjectPanelWidget, "cancelar_e_aguardar", lambda _s, _ms: not ocupado["analise"]
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *a: avisos.append(str(a[1])))
    pedidos = _contar_pedidos(monkeypatch, panel)
    try:
        window.show()
        janela.bloqueio.armar()
        qtbot.waitUntil(janela.bloqueio.entrou.is_set, timeout=_PRAZO_FECHAR_MS)

        # Análise em andamento com observação lenta: o aviso existente, sem adiar nem conectar.
        assert not window.close()
        assert avisos == ["Operação em andamento"]
        assert window.isEnabled()
        assert not window._fechamento_adiado
        assert pedidos == []
        assert _conexoes_rede_encerrada(panel) == 0

        ocupado["analise"] = False
        assert not window.close()
        assert not window.close()

        assert pedidos == [1000]
        assert _conexoes_rede_encerrada(panel) == 1
        assert window.isVisible()
        assert not window.isEnabled()

        janela.bloqueio.liberar.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
        assert janela.liberacoes == [1]
        assert _conexoes_rede_encerrada(panel) == 0
    finally:
        _juntar(janela)


def test_thread_termina_entre_pedido_e_conexao(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window, panel = janela.window, janela.panel
    original = panel.pedir_encerramento
    respostas: list[bool] = []

    def pedir_e_deixar_a_thread_terminar(timeout_ms: int) -> bool:
        thread = panel._global_poll_thread
        encerrou = original(timeout_ms)
        respostas.append(encerrou)
        # A thread termina depois do pedido e antes de a janela ligar o slot.
        janela.bloqueio.liberar.set()
        assert thread is not None
        assert thread.wait(_PRAZO_JUNTAR_MS)
        return encerrou

    monkeypatch.setattr(panel, "pedir_encerramento", pedir_e_deixar_a_thread_terminar)
    try:
        window.show()
        janela.bloqueio.armar()
        qtbot.waitUntil(janela.bloqueio.entrou.is_set, timeout=_PRAZO_FECHAR_MS)

        assert window.close()

        assert respostas == [False]
        assert not window.isVisible()
        assert not window._fechamento_adiado
        assert janela.liberacoes == [1]
        assert _conexoes_rede_encerrada(panel) == 0
    finally:
        _juntar(janela)


def test_perda_de_conexao_durante_o_adiamento_nao_prende_a_janela(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window, panel = janela.window, janela.panel
    try:
        _adiar_fechamento(qtbot, janela)
        thread = panel._global_poll_thread

        window.set_connection_available(False, "Servidor indisponível")
        window.set_connection_available(True, "Conexão restabelecida")

        assert panel._global_poll_thread is thread
        assert window.statusBar().currentMessage() == _STATUS_ENCERRANDO
        assert not window.isEnabled()

        janela.bloqueio.liberar.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
        assert janela.liberacoes == [1]
        assert not panel.rede_ativa()
    finally:
        _juntar(janela)


class _ProjetoQueCai(DirectProjectGateway):
    """Depois de armado, ``session()`` bloqueia e então levanta ``INTERNAL_ERROR``."""

    def __init__(self, runtime: ServerRuntime, bloqueio: _Bloqueio) -> None:
        super().__init__(runtime)
        self._bloqueio = bloqueio

    def session(self) -> SessionCapabilitiesResponse:
        if not self._bloqueio.armado:
            return super().session()
        self._bloqueio.aguardar()
        raise ProjectGatewayError(ErrorCode.INTERNAL_ERROR, "Servidor caiu no teste")


@pytest.fixture
def runtime_proprio(tmp_path: Path) -> Iterator[ServerRuntime]:
    runtime = compose_server_runtime(
        ServerSettings(
            password="senha isolada do teste de perda de conexão",
            market_sqlserver_connection_string="fixture-market-connection",
            data_directory=tmp_path / "server-proprio",
        ),
        market_classifier=FakeClassificadorMercado(),
    )
    try:
        yield runtime
    finally:
        runtime.close()


def test_perda_de_conexao_pelo_gateway_reconectavel_nao_prende_a_janela(
    qtbot: QtBot,
    tmp_path: Path,
    runtime_proprio: ServerRuntime,
    application_factory: ApplicationFactory,
) -> None:
    bloqueio = _Bloqueio()
    events = ConnectionEvents()
    proxy = ReconnectableGateway(events, _ProjetoQueCai(runtime_proprio, bloqueio))
    _app, window = application_factory(
        [],
        settings=ClientSettings(data_directory=tmp_path / "reconectavel"),
        pdf_viewer_gateway=DirectPdfViewerGateway(runtime_proprio),
        project_gateway=cast(ProjectGateway, proxy),
        review_gateway=DirectReviewGateway(runtime_proprio),
        documentation_gateway=DirectDocumentationGateway(runtime_proprio),
        portability_gateway=DirectPortabilityGateway(runtime_proprio),
    )
    perdas: list[str] = []

    def perder_conexao(mensagem: str) -> None:
        perdas.append(mensagem)
        window.set_connection_available(False, mensagem)

    events.lost.connect(perder_conexao)
    janela = _preparar(window, bloqueio)
    try:
        _adiar_fechamento(qtbot, janela)
        assert window._fechamento_adiado

        bloqueio.liberar.set()
        qtbot.waitUntil(lambda: bool(perdas) and not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
        assert janela.liberacoes == [1]
        assert not janela.panel.rede_ativa()
    finally:
        _juntar(janela)


def test_timer_de_reconferencia_fecha_sem_sinal(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window, panel = janela.window, janela.panel
    try:
        _adiar_fechamento(qtbot, janela)
        assert window._timer_reconferencia.interval() == 250
        assert window._timer_reconferencia.isActive()
        assert panel.rede_encerrada.disconnect(window._concluir_fechamento_adiado)
        assert _conexoes_rede_encerrada(panel) == 0

        janela.bloqueio.liberar.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
        assert janela.liberacoes == [1]
        assert not window._timer_reconferencia.isActive()
    finally:
        _juntar(janela)


def test_run_com_close_no_finally_nao_repete_release(
    qtbot: QtBot,
    janela_com_sessao_bloqueavel: JanelaFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    janela = janela_com_sessao_bloqueavel()
    window, panel = janela.window, janela.panel
    pedidos = _contar_pedidos(monkeypatch, panel)
    try:
        _adiar_fechamento(qtbot, janela)
        janela.bloqueio.liberar.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
        assert janela.liberacoes == [1]

        # O finally de bootstrap.run() fecha a janela já fechada depois do exec(). O Qt nem
        # sempre entrega esse closeEvent; o envio direto cobre a plataforma que entrega.
        assert window.close()
        evento = QCloseEvent()
        QCoreApplication.sendEvent(window, evento)

        assert evento.isAccepted()
        assert janela.liberacoes == [1]
        assert pedidos == [1000]
        assert not window._timer_reconferencia.isActive()
    finally:
        _juntar(janela)
