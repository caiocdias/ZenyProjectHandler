"""Reiniciar a observação global não perde a thread nova quando a antiga é destruída.

A thread antiga é destruída depois (``deleteLater``), quando a nova já está em execução. Se a
destruição tardia apagar as referências da thread nova, o fechamento seguinte não a junta e destruir
o painel com a QThread viva aborta o processo inteiro. Por isso o cenário roda num subprocesso: o
aborto vira ``returncode != 0`` com saída legível, em vez de um "worker crashed" do xdist.
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

_CENARIO = textwrap.dedent(
    '''
    import time
    from collections.abc import Iterator
    from pathlib import Path

    import pytest
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from shiboken6 import delete
    from tests.conftest import ApplicationFactory
    from tests.remote_gateways import DirectProjectGateway

    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui.main_window import MainWindow
    from zeny_project_handler_client.ui.project_panel import ProjectPanelWidget

    # A sessão dorme mais que o prazo padrão de 1000 ms de shutdown_polling: o cenário dá à
    # junção um prazo explícito, sem alargar o prazo do produto.
    _PRAZO_JUNTAR_MS = 60_000


    @pytest.fixture
    def destruir_janelas_depois_da_fabrica() -> Iterator[list[MainWindow]]:
        """Destrói o objeto C++ depois do descarte da fábrica, como o coletor faz num teste real."""
        janelas: list[MainWindow] = []
        yield janelas
        for janela in janelas:
            delete(janela)
            QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


    def test_cenario(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        destruir_janelas_depois_da_fabrica: list[MainWindow],
        application_factory: ApplicationFactory,
    ) -> None:
        original = DirectProjectGateway.session

        def sessao_lenta(self):
            time.sleep(1.6)
            return original(self)

        monkeypatch.setattr(DirectProjectGateway, "session", sessao_lenta)
        app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "reinicio")
        )
        destruir_janelas_depois_da_fabrica.append(window)
        panel = window.project_panel
        assert isinstance(panel, ProjectPanelWidget)
        assert panel.shutdown_polling(_PRAZO_JUNTAR_MS)
        panel.restart_polling()
        nova = panel._global_poll_thread
        assert nova is not None
        # A thread antiga termina antes da nova; sua destruição tardia chega agora.
        app.processEvents()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert panel._global_poll_thread is nova
        assert nova.isRunning()
    '''
)


def _truncar(texto: str) -> str:
    if len(texto) <= _TRECHO_MAXIMO:
        return texto
    return f"[...]{texto[-_TRECHO_MAXIMO:]}"


def test_destruicao_tardia_da_thread_antiga_nao_solta_a_thread_reiniciada(
    tmp_path: Path,
) -> None:
    cenario = tmp_path / "cenario" / "test_cenario_reinicio.py"
    cenario.parent.mkdir()
    cenario.write_text(_CENARIO, encoding="utf-8")
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_XDIST")}
    ambiente |= {"QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": str(_RAIZ)}
    comando = [
        *[sys.executable, "-m", "pytest", str(cenario), "-p", "tests.conftest", "-q", "-n", "0"],
        *["--rootdir", str(_RAIZ), "-c", str(_RAIZ / "pyproject.toml")],
        # Sem confcutdir a coleta lista cada pasta acima do cenário, inclusive o %TEMP%
        # compartilhado, onde outros testes criam e apagam pastas durante a listagem.
        *["--confcutdir", str(cenario.parent)],
        *["-p", "no:cacheprovider", "--basetemp", str(tmp_path / "base")],
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
        pytest.fail(f"cenário de reinício passou de {_PRAZO_SUBPROCESSO_S} s: {erro}")

    assert resultado.returncode == 0, (
        f"cenário de reinício terminou com código {resultado.returncode} "
        f"(aborto da QThread costuma dar 127/134/3221226505)\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )
    assert "1 passed" in resultado.stdout
