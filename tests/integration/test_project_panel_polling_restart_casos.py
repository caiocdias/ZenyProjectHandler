"""Casos de borda da destruição tardia da thread de observação global do painel.

Complementa ``test_project_panel_polling_restart.py``: dois reinícios seguidos, fechamento sem
reinício e painel destruído antes das threads antigas. Cada cenário roda num subprocesso porque o
defeito que ele guarda aborta o processo (qFatal); assim a falha vira ``returncode != 0`` legível.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_RAIZ = Path(__file__).resolve().parents[2]
_PRAZO_SUBPROCESSO_S = 300
_TRECHO_MAXIMO = 4_000
_TOTAL_CENARIOS = 3

_CENARIOS = textwrap.dedent(
    """
    import time
    from collections.abc import Iterator
    from pathlib import Path

    import pytest
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete, isValid
    from tests.conftest import ApplicationFactory
    from tests.remote_gateways import DirectProjectGateway

    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui.main_window import MainWindow
    from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget


    @pytest.fixture
    def destruir_janelas_depois_da_fabrica() -> Iterator[list[MainWindow]]:
        janelas: list[MainWindow] = []
        yield janelas
        for janela in janelas:
            if isValid(janela):
                delete(janela)
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


    def _painel(tmp_path, monkeypatch, fabrica, janelas, nome):
        original = DirectProjectGateway.session

        def sessao_lenta(self):
            time.sleep(1.2)
            return original(self)

        monkeypatch.setattr(DirectProjectGateway, "session", sessao_lenta)
        app, window = fabrica([], settings=ClientSettings(data_directory=tmp_path / nome))
        janelas.append(window)
        panel = window.project_panel
        assert isinstance(panel, ProjectPanelWidget)
        return app, window, panel


    def _entregar_destruicoes(app) -> None:
        app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


    def test_dois_reinicios_seguidos_so_a_ultima_thread_sobrevive(
        tmp_path, monkeypatch, destruir_janelas_depois_da_fabrica, application_factory
    ) -> None:
        app, _, panel = _painel(
            tmp_path, monkeypatch, application_factory, destruir_janelas_depois_da_fabrica, "dois"
        )
        assert panel.shutdown_polling()
        panel.restart_polling()
        segunda = panel._global_poll_thread
        assert segunda is not None
        assert panel.shutdown_polling()
        panel.restart_polling()
        terceira = panel._global_poll_thread
        assert terceira is not None and terceira is not segunda
        _entregar_destruicoes(app)
        assert panel._global_poll_thread is terceira
        assert panel._global_poll_worker is not None
        assert terceira.isRunning()
        assert panel.shutdown_polling()
        assert panel._global_poll_thread is None
        assert panel._global_poll_worker is None


    def test_fechar_sem_reinicio_junta_e_limpa_as_referencias(
        tmp_path, monkeypatch, destruir_janelas_depois_da_fabrica, application_factory
    ) -> None:
        app, _, panel = _painel(
            tmp_path, monkeypatch, application_factory, destruir_janelas_depois_da_fabrica, "sem"
        )
        assert panel._global_poll_thread is not None
        assert panel.shutdown_polling()
        assert panel._global_poll_thread is None
        _entregar_destruicoes(app)
        assert panel._global_poll_thread is None
        assert panel._global_poll_worker is None


    def test_painel_destruido_com_destruicoes_pendentes_nao_levanta(
        tmp_path, monkeypatch, destruir_janelas_depois_da_fabrica, application_factory
    ) -> None:
        _, _, panel = _painel(
            tmp_path, monkeypatch, application_factory, destruir_janelas_depois_da_fabrica, "pai"
        )
        assert panel.shutdown_polling()
        panel.restart_polling()
        assert panel.shutdown_polling()
        # Sem entregar os deleteLater: o fim do teste destrói o painel com as threads pendentes,
        # e o destroyed delas chega com o painel já em destruição.
    """
)


def _truncar(texto: str) -> str:
    if len(texto) <= _TRECHO_MAXIMO:
        return texto
    return f"[...]{texto[-_TRECHO_MAXIMO:]}"


def test_casos_de_borda_da_destruicao_tardia_da_thread_de_observacao(tmp_path: Path) -> None:
    cenario = tmp_path / "cenario" / "test_cenarios_reinicio.py"
    cenario.parent.mkdir()
    cenario.write_text(_CENARIOS, encoding="utf-8")
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    ambiente |= {"QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(_RAIZ)}
    comando = [
        *[sys.executable, "-m", "pytest", str(cenario), "-p", "tests.conftest", "-q", "-n", "0"],
        *["--rootdir", str(_RAIZ), "-c", str(_RAIZ / "pyproject.toml")],
        *["-p", "no:cacheprovider", "--basetemp", str(tmp_path / "base"), "--no-cov"],
    ]

    try:
        resultado = subprocess.run(
            comando,
            cwd=_RAIZ,
            env=ambiente,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PRAZO_SUBPROCESSO_S,
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        pytest.fail(f"cenários de reinício passaram de {_PRAZO_SUBPROCESSO_S} s: {erro}")

    assert resultado.returncode == 0, (
        f"cenários de reinício terminaram com código {resultado.returncode} "
        f"(aborto da QThread costuma dar 127/134/3221226505)\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )
    assert f"{_TOTAL_CENARIOS} passed" in resultado.stdout
