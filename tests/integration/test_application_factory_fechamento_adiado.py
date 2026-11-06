"""A fábrica de janelas só libera os recursos depois que o fechamento adiado conclui.

Uma leitura remota que passa do 1 s de espera do ``closeEvent`` adia o fechamento. Se o descarte
da fábrica liberar a janela logo depois do ``close()``, a liberação corre com a rede viva e o
fechamento adiado termina mais tarde, nos eventos de outro teste. O cenário roda num subprocesso
para que uma thread viva no fim do processo apareça como código de saída legível.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest
from tests.cenario_subprocesso import RAIZ, ambiente_subprocesso, comando_pytest_cenario

pytestmark = pytest.mark.integration

_PRAZO_SUBPROCESSO_S = 300
_TRECHO_MAXIMO = 4_000

_CENARIO = textwrap.dedent(
    '''
    import threading
    import time
    from collections.abc import Iterator
    from pathlib import Path

    import pytest
    from PySide6.QtCore import QDeadlineTimer
    from tests.conftest import ApplicationFactory

    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui.remote_read import RemoteRequestThread, aguardar_leituras


    @pytest.fixture
    def rede_ativa_em_cada_liberacao() -> Iterator[list[bool]]:
        """Confere, depois do descarte da fábrica, se alguma liberação correu com rede viva."""
        registro: list[bool] = []
        yield registro
        assert aguardar_leituras(QDeadlineTimer(10_000))
        assert registro, "a janela não liberou os recursos"
        assert not any(registro), f"liberação com rede viva: {registro}"


    def test_cenario(
        tmp_path: Path,
        rede_ativa_em_cada_liberacao: list[bool],
        application_factory: ApplicationFactory,
    ) -> None:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "janela")
        )
        panel = window.project_panel
        assert panel is not None
        liberar_original = window._resource_cleanup

        def liberar() -> None:
            rede_ativa_em_cada_liberacao.append(panel.rede_ativa())
            liberar_original()

        window.set_resource_cleanup(liberar)
        em_execucao = threading.Event()

        def leitura_lenta() -> None:
            em_execucao.set()
            # Passa com folga do 1 s que o closeEvent espera antes de adiar o fechamento.
            time.sleep(3.0)

        RemoteRequestThread(0, leitura_lenta).launch()
        # Sem esperar o início, o pedido de interrupção do close() no descarte a cancelaria antes
        # do run() e o cenário passaria sem exercitar o fechamento adiado.
        assert em_execucao.wait(10)
    '''
)


def _truncar(texto: str) -> str:
    if len(texto) <= _TRECHO_MAXIMO:
        return texto
    return f"[...]{texto[-_TRECHO_MAXIMO:]}"


def test_descarte_da_fabrica_espera_o_fechamento_adiado_antes_de_liberar(
    tmp_path: Path,
) -> None:
    cenario = tmp_path / "cenario" / "test_cenario_fechamento_adiado.py"
    cenario.parent.mkdir()
    cenario.write_text(_CENARIO, encoding="utf-8")
    comando = comando_pytest_cenario(cenario, tmp_path / "base", "-p", "tests.conftest")

    try:
        resultado = subprocess.run(
            comando,
            cwd=RAIZ,
            env=ambiente_subprocesso(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PRAZO_SUBPROCESSO_S,
            check=False,
        )
    except subprocess.TimeoutExpired as erro:
        pytest.fail(f"cenário de fechamento adiado passou de {_PRAZO_SUBPROCESSO_S} s: {erro}")

    assert resultado.returncode == 0, (
        f"cenário de fechamento adiado terminou com código {resultado.returncode} "
        f"(aborto da QThread costuma dar 127/134/3221226505)\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )
    assert "1 passed" in resultado.stdout
