"""Ataque ao fechamento adiado da janela (E17 Task 2).

Cobre o que o teste do desenvolvedor não força: leitura remota ou pesquisa de outro painel como
a última thread viva, closes repetidos durante o adiamento, janela realmente desabilitada,
``_save_ui_state``/``release_resources`` uma vez só, corrida entre a liberação da thread e o
segundo ``close()`` e o ``exec()`` real com o ``bootstrap.run()`` e perda de conexão por HTTP.

Os cenários que entram no ``app.exec()`` rodam em subprocesso, sem o ``tests/conftest.py``: o
aborto da ``QThread`` vira ``returncode != 0`` com saída legível. Toda thread bloqueada num
``Event`` é liberada e juntada antes de destruir o dono.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Literal

import pytest
from PySide6.QtCore import QCoreApplication, QDeadlineTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDockWidget, QMessageBox, QWidget
from pytestqt.qtbot import QtBot
from tests.conftest import ApplicationFactory

from zeny_project_handler_client.config import ClientSettings
from zeny_project_handler_client.ui import project_search, remote_read
from zeny_project_handler_client.ui.main_window import MainWindow
from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget
from zeny_project_handler_client.ui.project_search import ProjectSearchThread
from zeny_project_handler_client.ui.remote_read import RemoteRequestThread
from zeny_project_handler_contracts.projects import ProjectSummaryListResponse

pytestmark = pytest.mark.integration

_RAIZ = Path(__file__).resolve().parents[2]
_PRAZO_SUBPROCESSO_S = 300
_DURACAO_MAXIMA_S = 30.0
_TRECHO_MAXIMO = 4_000
_PRAZO_JUNTAR_MS = 10_000
_PRAZO_FECHAR_MS = 10_000
_PRAZO_SEGURAR_S = 30.0
_STATUS_ENCERRANDO = "Encerrando: aguardando o servidor responder"

Registro = Literal["leitura", "pesquisa"]


# --------------------------------------------------------------------------------------------
# Em processo
# --------------------------------------------------------------------------------------------


@dataclass
class _Janela:
    window: MainWindow
    panel: ProjectPanelWidget
    liberacoes: list[int]
    salvamentos: list[int]
    portao: Event


def _segurar(
    registro: Registro, portao: Event, qtbot: QtBot
) -> RemoteRequestThread | ProjectSearchThread:
    """Registre uma thread de rede de outro painel que só termina quando o portão abre.

    Espera a requisição entrar: uma interrupção pedida antes de ``run()`` a faria sair sozinha.
    """
    entrou = Event()
    if registro == "leitura":

        def pedir() -> object:
            entrou.set()
            portao.wait(_PRAZO_SEGURAR_S)
            return None

        leitura = RemoteRequestThread(0, pedir)
        leitura.launch()
        qtbot.waitUntil(entrou.is_set, timeout=_PRAZO_FECHAR_MS)
        return leitura

    def pesquisar() -> ProjectSummaryListResponse:
        entrou.set()
        portao.wait(_PRAZO_SEGURAR_S)
        raise RuntimeError("pesquisa liberada pelo teste")

    pesquisa = ProjectSearchThread(0, "ns", pesquisar)
    pesquisa.launch()
    qtbot.waitUntil(entrou.is_set, timeout=_PRAZO_FECHAR_MS)
    return pesquisa


def _juntar(janela: _Janela) -> None:
    janela.portao.set()
    assert janela.panel.shutdown_polling(_PRAZO_JUNTAR_MS)
    prazo = QDeadlineTimer(_PRAZO_JUNTAR_MS)
    assert remote_read.aguardar_leituras(prazo)
    assert project_search.aguardar_pesquisas(prazo)
    QCoreApplication.processEvents()


JanelaFactory = Callable[[], _Janela]


@pytest.fixture
def criar_janela(
    application_factory: ApplicationFactory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[JanelaFactory]:
    criadas: list[_Janela] = []

    def criar() -> _Janela:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / f"janela-{len(criadas)}")
        )
        panel = window.project_panel
        assert isinstance(panel, ProjectPanelWidget)
        liberacoes: list[int] = []
        salvamentos: list[int] = []
        original_cleanup = window._resource_cleanup
        original_salvar = window._save_ui_state

        def liberar() -> None:
            liberacoes.append(1)
            original_cleanup()

        def salvar() -> None:
            salvamentos.append(1)
            original_salvar()

        window.set_resource_cleanup(liberar)
        monkeypatch.setattr(window, "_save_ui_state", salvar)
        janela = _Janela(window, panel, liberacoes, salvamentos, Event())
        criadas.append(janela)
        return janela

    try:
        yield criar
    finally:
        for janela in criadas:
            _juntar(janela)


class _Registros(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.mensagens: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensagens.append(record.getMessage())


def _fechar_com_rede_viva(qtbot: QtBot, janela: _Janela, registro: Registro) -> None:
    """Segure uma thread de outro painel e peça o fechamento: a janela adia."""
    janela.window.show()
    qtbot.waitUntil(janela.window.isVisible)
    _segurar(registro, janela.portao, qtbot)
    assert not janela.window.close()
    assert janela.window._fechamento_adiado


@pytest.mark.parametrize("via", ["sinal", "timer"])
@pytest.mark.parametrize("registro", ["leitura", "pesquisa"])
def test_leitura_ou_pesquisa_de_outro_painel_como_ultima_viva_segura_o_fechamento(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
    registro: Registro,
    via: str,
) -> None:
    janela = criar_janela()
    window, panel = janela.window, janela.panel
    logger = logging.getLogger(MainWindow.__module__)
    registros = _Registros()
    logger.addHandler(registros)
    try:
        _fechar_com_rede_viva(qtbot, janela, registro)
        if via == "timer":
            assert panel.rede_encerrada.disconnect(window._concluir_fechamento_adiado)

        # A observação global já terminou; só a thread de outro painel segura a janela.
        assert panel._global_poll_thread is None or not panel._global_poll_thread.isRunning()
        assert window.isVisible()
        assert not window.isEnabled()

        # Vários ticks de 250 ms com a rede ainda ativa não fecham nem repetem o adiamento.
        qtbot.wait(900)
        assert window.isVisible()
        assert window._timer_reconferencia.isActive()
        assert janela.liberacoes == []
        assert janela.salvamentos == []

        janela.portao.set()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)

        assert janela.liberacoes == [1]
        assert janela.salvamentos == [1]
        assert not panel.rede_ativa()
        assert not window._timer_reconferencia.isActive()
        inicios = [m for m in registros.mensagens if m.startswith("Fechamento adiado:")]
        assert len(inicios) == 1
        assert registros.mensagens[-1].startswith("Fechamento adiado concluído em ")
    finally:
        logger.removeHandler(registros)


def test_closes_repetidos_durante_o_adiamento_so_sao_ignorados(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    janela = criar_janela()
    window, panel = janela.window, janela.panel
    avisos: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: avisos.append(str(a[1])))
    pedidos: list[int] = []
    original = panel.pedir_encerramento

    def pedir(timeout_ms: int) -> bool:
        pedidos.append(timeout_ms)
        return original(timeout_ms)

    monkeypatch.setattr(panel, "pedir_encerramento", pedir)
    _fechar_com_rede_viva(qtbot, janela, "leitura")
    status = window.statusBar().currentMessage()
    assert status == _STATUS_ENCERRANDO

    for _ in range(5):
        assert not window.close()
    for _ in range(2):
        evento = QCloseEvent()
        QCoreApplication.sendEvent(window, evento)
        assert not evento.isAccepted()

    assert pedidos == [1000]
    assert panel.receivers("2rede_encerrada()") == 1
    assert avisos == []
    assert window.statusBar().currentMessage() == status
    assert window.isVisible()
    assert not window.isEnabled()
    assert janela.liberacoes == []
    assert janela.salvamentos == []

    janela.portao.set()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
    assert janela.liberacoes == [1]
    assert janela.salvamentos == [1]
    assert pedidos == [1000]


def test_fechamento_sem_rede_viva_salva_e_libera_uma_vez_mesmo_com_close_event_repetido(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
) -> None:
    janela = criar_janela()
    window = janela.window
    window.show()
    qtbot.waitUntil(window.isVisible)

    assert window.close()
    for _ in range(3):
        evento = QCloseEvent()
        QCoreApplication.sendEvent(window, evento)
        assert evento.isAccepted()

    assert not window._fechamento_adiado
    assert janela.salvamentos == [1]
    assert janela.liberacoes == [1]


def test_janela_adiada_esta_inteira_desabilitada_e_ignora_cliques(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
) -> None:
    janela = criar_janela()
    window, panel = janela.window, janela.panel
    flutuante = window.findChildren(QDockWidget)[0]
    flutuante.setFloating(True)
    flutuante.show()
    cliques: list[bool] = []
    panel._run.clicked.connect(lambda *_a: cliques.append(True))
    _fechar_com_rede_viva(qtbot, janela, "leitura")

    filhos = window.findChildren(QWidget)
    habilitados = [w.objectName() or type(w).__name__ for w in filhos if w.isEnabled()]
    assert habilitados == []
    assert not window.menuBar().isEnabled()
    assert not window.centralWidget().isEnabled()
    assert not flutuante.isEnabled()
    # Qualquer janela de topo visível do processo também está desabilitada.
    for topo in QApplication.topLevelWidgets():
        if topo.isVisible() and topo is not window:
            assert not topo.isEnabled(), topo

    # Mesmo com o botão marcado como habilitado por conta própria, o clique não chega.
    panel._run.setEnabled(True)
    QTest.mouseClick(panel._run, Qt.MouseButton.LeftButton)
    QTest.keyClick(panel._run, Qt.Key.Key_Space)
    assert cliques == []
    assert not window.close()
    assert window.isVisible()


def test_perda_de_conexao_antes_do_close_nao_adia_nem_prende(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
) -> None:
    janela = criar_janela()
    window, panel = janela.window, janela.panel
    window.show()
    qtbot.waitUntil(window.isVisible)
    window.set_connection_available(False, "Servidor indisponível")
    assert not panel.rede_ativa()

    assert window.close()

    assert not window._fechamento_adiado
    assert not window.isVisible()
    assert janela.liberacoes == [1]
    assert janela.salvamentos == [1]


@pytest.mark.parametrize("atraso_s", [0.0, 0.05, 0.4])
def test_liberar_a_thread_junto_do_segundo_close_libera_uma_vez(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
    atraso_s: float,
) -> None:
    janela = criar_janela()
    window = janela.window
    _fechar_com_rede_viva(qtbot, janela, "leitura")

    janela.portao.set()
    time.sleep(atraso_s)
    # O término ainda está na fila de eventos; o segundo close() passa por cima dele.
    window.close()
    QCoreApplication.processEvents()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
    qtbot.wait(600)

    assert janela.liberacoes == [1]
    assert janela.salvamentos == [1]
    assert not window._timer_reconferencia.isActive()
    assert not janela.panel.rede_ativa()


def test_nova_leitura_de_outro_painel_durante_o_adiamento_estende_a_espera(
    qtbot: QtBot,
    criar_janela: JanelaFactory,
) -> None:
    janela = criar_janela()
    window = janela.window
    _fechar_com_rede_viva(qtbot, janela, "leitura")
    segundo = Event()
    _segurar("pesquisa", segundo, qtbot)

    janela.portao.set()
    qtbot.wait(700)
    assert window.isVisible()
    assert janela.liberacoes == []

    segundo.set()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=_PRAZO_FECHAR_MS)
    assert janela.liberacoes == [1]
    assert janela.salvamentos == [1]


# --------------------------------------------------------------------------------------------
# Subprocessos com app.exec() real
# --------------------------------------------------------------------------------------------

_MONTAGEM = textwrap.dedent(
    """
    import sys
    import threading
    import time
    from pathlib import Path

    from PySide6.QtCore import QTimer

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
    from zeny_project_handler_client.ui import project_search, remote_read
    from zeny_project_handler_client.ui.project_search import ProjectSearchThread
    from zeny_project_handler_client.ui.remote_read import RemoteRequestThread
    from zeny_project_handler_server.composition import compose_server_runtime
    from zeny_project_handler_server.config import ServerSettings


    def montar(diretorio):
        runtime = compose_server_runtime(
            ServerSettings(
                password="senha isolada do cenario de ataque ao fechamento",
                market_sqlserver_connection_string="fixture-market-connection",
                data_directory=Path(diretorio) / "server",
            ),
            market_classifier=FakeClassificadorMercado(),
        )
        app, janela = create_application(
            [],
            settings=ClientSettings(data_directory=Path(diretorio) / "client"),
            pdf_viewer_gateway=DirectPdfViewerGateway(runtime),
            project_gateway=DirectProjectGateway(runtime),
            review_gateway=DirectReviewGateway(runtime),
            documentation_gateway=DirectDocumentationGateway(runtime),
            portability_gateway=DirectPortabilityGateway(runtime),
        )
        return app, janela, runtime


    def contar_liberacoes(janela):
        chamadas = []
        original = janela._resource_cleanup

        def liberar():
            chamadas.append(1)
            original()

        janela.set_resource_cleanup(liberar)
        return chamadas
    """
)

_SCRIPT_REMOTA = _MONTAGEM + textwrap.dedent(
    """

    def principal():
        diretorio, modo = sys.argv[1], sys.argv[2]
        app, janela, runtime = montar(diretorio)
        liberacoes = contar_liberacoes(janela)
        marcas = {}
        try:
            janela.show()

            entraram = []

            def leitura_lenta():
                entraram.append("leitura")
                time.sleep(1.6)

            def pesquisa_lenta():
                entraram.append("pesquisa")
                time.sleep(2.4)
                raise RuntimeError("pesquisa terminou")

            esperados = {"leitura": 1, "pesquisa": 1, "ambas": 2}[modo]
            vigia = QTimer()
            vigia.setInterval(20)

            def fechar_quando_entrarem():
                # Uma interrupção pedida antes do run() faria a thread sair sozinha.
                if len(entraram) < esperados:
                    return
                vigia.stop()
                marcas["fechou"] = time.monotonic()
                janela.close()
                estado = f"adiado={janela._fechamento_adiado} visivel={janela.isVisible()}"
                print(estado, flush=True)

            def lancar():
                if modo in ("leitura", "ambas"):
                    RemoteRequestThread(0, leitura_lenta).launch()
                if modo in ("pesquisa", "ambas"):
                    ProjectSearchThread(0, "ns", pesquisa_lenta).launch()
                vigia.timeout.connect(fechar_quando_entrarem)
                vigia.start()

            QTimer.singleShot(300, lancar)
            codigo = app.exec()
            print(f"exec={codigo}", flush=True)
            print(f"leituras_ativas={remote_read.leituras_ativas()}", flush=True)
            print(f"pesquisas_ativas={project_search.pesquisas_ativas()}", flush=True)
            print(f"rede_ativa={janela.project_panel.rede_ativa()}", flush=True)
            print(f"espera_s={time.monotonic() - marcas['fechou']:.2f}", flush=True)
            janela.close()  # como o finally de bootstrap.run()
            print(f"liberacoes={len(liberacoes)}", flush=True)
            return codigo
        finally:
            janela.project_panel.shutdown_polling(30_000)
            runtime.close()


    sys.exit(principal())
    """
)

_SCRIPT_RUN = textwrap.dedent(
    """
    import sys
    import threading
    import time
    from contextlib import closing
    from pathlib import Path
    from socket import create_server

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QDialog
    from uvicorn import Config, Server

    from zeny_project_handler_client.bootstrap import run
    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui import project_search, remote_read
    from zeny_project_handler_client.ui.main_window import MainWindow
    from zeny_project_handler_client.ui.remote_read import RemoteRequestThread
    from zeny_project_handler_server.app import create_app
    from zeny_project_handler_server.config import ServerSettings

    SENHA = "senha runtime exclusiva do ataque ao fechamento"


    class DialogoAutomatico(QDialog):
        def __init__(self, url, attempt, parent):
            super().__init__(parent)
            self._url = url
            self._attempt = attempt
            self.session = None
            self.connected_url = None

        def exec(self):
            self.session = self._attempt(self._url, SENHA)
            self.connected_url = self._url
            return int(QDialog.DialogCode.Accepted)


    def principal():
        diretorio = Path(sys.argv[1])
        servidor_settings = ServerSettings(
            password=SENHA,
            market_sqlserver_connection_string="fixture-market-connection",
            data_directory=diretorio / "server",
        )
        with closing(create_server(("127.0.0.1", 0))) as ouvinte:
            porta = int(ouvinte.getsockname()[1])
            config = Config(create_app(servidor_settings), log_level="critical", lifespan="on")
            servidor = Server(config)
            fio = threading.Thread(target=lambda: servidor.run(sockets=[ouvinte]), daemon=True)
            fio.start()
            for _ in range(500):
                if servidor.started:
                    break
                time.sleep(0.01)
            else:
                raise RuntimeError("servidor nao iniciou")

            app = QApplication([])
            marcas = {"liberacoes": [], "perdas": [], "disponibilidade": []}
            vigia = QTimer()
            vigia.setInterval(20)

            def matar_servidor():
                servidor.should_exit = True
                fio.join(10)
                marcas["servidor_morto"] = not fio.is_alive()

            def ao_aparecer():
                janelas = [
                    w
                    for w in QApplication.topLevelWidgets()
                    if isinstance(w, MainWindow) and w.isVisible()
                ]
                janela = janelas[0] if janelas else None
                if janela is None:
                    return
                vigia.stop()
                original = janela._resource_cleanup

                def liberar():
                    marcas["liberacoes"].append(1)
                    original()

                janela.set_resource_cleanup(liberar)
                disponibilidade = janela.set_connection_available

                def observar(disponivel, mensagem=""):
                    marcas["disponibilidade"].append((disponivel, janela._fechamento_adiado))
                    return disponibilidade(disponivel, mensagem)

                janela.set_connection_available = observar
                gateway = janela.project_panel._gateway

                entrou = threading.Event()

                def pedido():
                    entrou.set()
                    prazo = time.monotonic() + 20
                    while not marcas.get("servidor_morto") and time.monotonic() < prazo:
                        time.sleep(0.02)
                    gateway.session()  # servidor morto: perde a conexão com a janela adiada

                RemoteRequestThread(0, pedido).launch()
                espera = QTimer()
                espera.setInterval(20)

                def fechar_quando_entrar():
                    # Uma interrupção pedida antes do run() faria a thread sair sozinha.
                    if not entrou.is_set():
                        return
                    espera.stop()
                    marcas["fechou"] = time.monotonic()
                    QTimer.singleShot(1300, matar_servidor)
                    janela.close()
                    estado = f"adiado={janela._fechamento_adiado} visivel={janela.isVisible()}"
                    print(estado, flush=True)

                espera.timeout.connect(fechar_quando_entrar)
                espera.start()
                marcas["espera"] = espera

            vigia.timeout.connect(ao_aparecer)
            vigia.start()
            codigo = run(
                [],
                settings=ClientSettings(data_directory=diretorio / "client"),
                dialog_factory=lambda _url, attempt, parent: DialogoAutomatico(
                    f"http://127.0.0.1:{porta}", attempt, parent
                ),
            )
            print(f"run={codigo}", flush=True)
            print(f"leituras_ativas={remote_read.leituras_ativas()}", flush=True)
            print(f"pesquisas_ativas={project_search.pesquisas_ativas()}", flush=True)
            print(f"liberacoes={len(marcas['liberacoes'])}", flush=True)
            print(f"servidor_morto={marcas.get('servidor_morto')}", flush=True)
            print(f"disponibilidade={marcas['disponibilidade']}", flush=True)
            print(f"espera_s={time.monotonic() - marcas['fechou']:.2f}", flush=True)
            servidor.should_exit = True
            fio.join(10)
            return codigo


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


def _executar_script(
    tmp_path: Path, nome: str, codigo: str, *argumentos: str
) -> tuple[subprocess.CompletedProcess[str], float]:
    script = tmp_path / "script" / nome
    script.parent.mkdir()
    script.write_text(codigo, encoding="utf-8")
    inicio = time.monotonic()
    try:
        resultado = subprocess.run(
            [sys.executable, str(script), str(tmp_path / "dados"), *argumentos],
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
        pytest.fail(f"cenário passou de {_PRAZO_SUBPROCESSO_S} s: {erro}")
    return resultado, time.monotonic() - inicio


def _saida(resultado: subprocess.CompletedProcess[str]) -> str:
    return (
        f"código {resultado.returncode} (aborto da QThread costuma dar 127/134/3221226505)\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )


def _valor(resultado: subprocess.CompletedProcess[str], chave: str) -> str:
    for linha in resultado.stdout.splitlines():
        if linha.startswith(f"{chave}="):
            return linha.split("=", 1)[1]
    raise AssertionError(f"o script não imprimiu {chave}=\n{_saida(resultado)}")


@pytest.mark.parametrize(
    ("modo", "espera_minima_s"),
    [("leitura", 1.4), ("pesquisa", 2.0), ("ambas", 2.0)],
)
def test_exec_real_espera_a_ultima_thread_de_outro_painel_e_sai_sem_thread_viva(
    tmp_path: Path, modo: str, espera_minima_s: float
) -> None:
    resultado, duracao = _executar_script(tmp_path, "remota.py", _SCRIPT_REMOTA, modo)

    assert resultado.returncode == 0, _saida(resultado)
    assert duracao < _DURACAO_MAXIMA_S, _saida(resultado)
    assert "adiado=True visivel=True" in resultado.stdout, _saida(resultado)
    assert _valor(resultado, "exec") == "0"
    assert _valor(resultado, "leituras_ativas") == "False", _saida(resultado)
    assert _valor(resultado, "pesquisas_ativas") == "False", _saida(resultado)
    assert _valor(resultado, "rede_ativa") == "False", _saida(resultado)
    assert float(_valor(resultado, "espera_s")) >= espera_minima_s, _saida(resultado)
    assert _valor(resultado, "liberacoes") == "1", _saida(resultado)
    assert "Destroyed while thread" not in resultado.stderr, _saida(resultado)


def test_bootstrap_run_com_perda_de_conexao_no_adiamento_sai_e_fecha_no_finally(
    tmp_path: Path,
) -> None:
    resultado, duracao = _executar_script(tmp_path, "run_real.py", _SCRIPT_RUN)

    assert resultado.returncode == 0, _saida(resultado)
    assert duracao < _DURACAO_MAXIMA_S, _saida(resultado)
    assert "adiado=True visivel=True" in resultado.stdout, _saida(resultado)
    assert _valor(resultado, "run") == "0"
    assert _valor(resultado, "servidor_morto") == "True", _saida(resultado)
    # A perda de conexão chegou com a janela adiada e não a prendeu nem reconectou.
    assert "(False, True)" in _valor(resultado, "disponibilidade"), _saida(resultado)
    assert _valor(resultado, "leituras_ativas") == "False", _saida(resultado)
    assert _valor(resultado, "pesquisas_ativas") == "False", _saida(resultado)
    # O close() do finally de run() não repete release_resources.
    assert _valor(resultado, "liberacoes") == "1", _saida(resultado)
    assert "Destroyed while thread" not in resultado.stderr, _saida(resultado)
