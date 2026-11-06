"""Ataque à espera do fechamento adiado no descarte da fábrica de janelas (E17 Task 4).

Parte unitária: ``_esperar_fechamento_adiado`` com janela e aplicação falsas, para o prazo, a
mensagem de estouro e os atalhos (janela nunca adiada, ou já concluída). Parte em subprocesso: a
fábrica real com rede viva, onde uma thread destruída viva derruba o processo inteiro.
"""

from __future__ import annotations

import re
import subprocess
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Any, cast

import pytest
from tests import conftest as conftest_dos_testes
from tests.cenario_subprocesso import RAIZ, ambiente_subprocesso, comando_pytest_cenario

pytestmark = pytest.mark.integration

_PRAZO_SUBPROCESSO_S = 300
_TRECHO_MAXIMO = 4_000


@dataclass
class _JanelaFalsa:
    _fechamento_adiado: bool
    _fechamento_concluido: bool


class _AplicacaoFalsa:
    def __init__(self, *, a_cada_ciclo: Callable[[int], None] | None = None) -> None:
        self.ciclos = 0
        self._a_cada_ciclo = a_cada_ciclo

    def processEvents(self) -> None:  # noqa: N802 - API Qt
        self.ciclos += 1
        if self._a_cada_ciclo is not None:
            self._a_cada_ciclo(self.ciclos)


def _esperar(aplicacao: _AplicacaoFalsa, janela: _JanelaFalsa) -> None:
    esperar = cast(Any, conftest_dos_testes)._esperar_fechamento_adiado
    esperar(aplicacao, janela)


def test_estouro_do_prazo_levanta_assertion_error_com_o_prazo_na_mensagem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conftest_dos_testes, "_PRAZO_ENCERRAR_THREADS_MS", 150)
    aplicacao = _AplicacaoFalsa()
    janela = _JanelaFalsa(_fechamento_adiado=True, _fechamento_concluido=False)

    inicio = monotonic()
    with pytest.raises(AssertionError, match=r"fechamento adiado n.o concluiu em 150 ms"):
        _esperar(aplicacao, janela)
    decorrido = monotonic() - inicio

    assert decorrido >= 0.15, f"estourou antes do prazo: {decorrido:.3f} s"
    assert decorrido < 5.0, f"a espera passou muito do prazo de 150 ms: {decorrido:.3f} s"
    assert aplicacao.ciclos >= 1, "a espera deve processar eventos enquanto aguarda"


def test_a_espera_termina_assim_que_o_fechamento_conclui_sem_esperar_o_prazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conftest_dos_testes, "_PRAZO_ENCERRAR_THREADS_MS", 60_000)
    janela = _JanelaFalsa(_fechamento_adiado=True, _fechamento_concluido=False)

    def concluir_no_terceiro_ciclo(ciclo: int) -> None:
        if ciclo == 3:
            janela._fechamento_concluido = True

    aplicacao = _AplicacaoFalsa(a_cada_ciclo=concluir_no_terceiro_ciclo)

    inicio = monotonic()
    _esperar(aplicacao, janela)

    assert aplicacao.ciclos == 3
    assert monotonic() - inicio < 5.0


def test_janela_que_nunca_adiou_o_fechamento_volta_sem_processar_eventos() -> None:
    aplicacao = _AplicacaoFalsa()

    _esperar(aplicacao, _JanelaFalsa(_fechamento_adiado=False, _fechamento_concluido=False))

    assert aplicacao.ciclos == 0


def test_janela_que_ja_concluiu_o_fechamento_volta_sem_processar_eventos() -> None:
    aplicacao = _AplicacaoFalsa()

    _esperar(aplicacao, _JanelaFalsa(_fechamento_adiado=True, _fechamento_concluido=True))
    _esperar(aplicacao, _JanelaFalsa(_fechamento_adiado=False, _fechamento_concluido=True))

    assert aplicacao.ciclos == 0


_CENARIO_TOLERANTE = textwrap.dedent(
    """
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
    def juntar_leituras_depois_da_fabrica() -> Iterator[None]:
        yield
        assert aguardar_leituras(QDeadlineTimer(10_000))


    def test_janela_nunca_exibida_e_sem_rede_descarta_sem_esperar(
        tmp_path: Path, application_factory: ApplicationFactory
    ) -> None:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "nunca-exibida")
        )
        assert not window.isVisible()
        assert not window._fechamento_adiado


    def test_janela_fechada_pelo_proprio_teste_antes_do_descarte(
        tmp_path: Path, application_factory: ApplicationFactory
    ) -> None:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "ja-fechada")
        )
        window.show()
        assert window.close()
        assert window._fechamento_concluido
        assert not window._fechamento_adiado


    def test_fechamento_adiado_que_o_proprio_teste_concluiu_antes_do_descarte(
        tmp_path: Path,
        juntar_leituras_depois_da_fabrica: None,
        application_factory: ApplicationFactory,
    ) -> None:
        app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "adiada-e-concluida")
        )
        window.show()
        em_execucao = threading.Event()

        def leitura_lenta() -> None:
            em_execucao.set()
            time.sleep(1.8)

        RemoteRequestThread(0, leitura_lenta).launch()
        # Sem esperar o início, o pedido de interrupção do closeEvent a cancelaria antes do run().
        assert em_execucao.wait(10)
        window.close()
        assert window._fechamento_adiado
        assert not window._fechamento_concluido
        limite = time.monotonic() + 30
        while not window._fechamento_concluido and time.monotonic() < limite:
            app.processEvents()
            time.sleep(0.01)
        assert window._fechamento_concluido
    """
)

_CENARIO_ESTOURO = textwrap.dedent(
    """
    import threading
    import time
    from collections.abc import Iterator
    from pathlib import Path

    import pytest
    from PySide6.QtCore import QDeadlineTimer
    from tests import conftest as conftest_dos_testes
    from tests.conftest import ApplicationFactory

    from zeny_project_handler_client.config import ClientSettings
    from zeny_project_handler_client.ui.remote_read import RemoteRequestThread, aguardar_leituras


    @pytest.fixture
    def juntar_leituras_depois_da_fabrica() -> Iterator[None]:
        yield
        assert aguardar_leituras(QDeadlineTimer(10_000))


    @pytest.fixture
    def prazo_curto_no_descarte(monkeypatch: pytest.MonkeyPatch) -> None:
        # Pedida antes da fábrica, é desfeita depois do descarte dela.
        monkeypatch.setattr(conftest_dos_testes, "_PRAZO_ENCERRAR_THREADS_MS", 400)


    def test_rede_que_nao_encerra_no_prazo_falha_o_descarte_com_mensagem_clara(
        tmp_path: Path,
        juntar_leituras_depois_da_fabrica: None,
        prazo_curto_no_descarte: None,
        application_factory: ApplicationFactory,
    ) -> None:
        _app, window = application_factory(
            [], settings=ClientSettings(data_directory=tmp_path / "estouro")
        )
        em_execucao = threading.Event()

        def leitura_lenta() -> None:
            em_execucao.set()
            time.sleep(1.9)

        # O closeEvent espera 1 s e adia; a leitura termina cerca de 0,9 s depois, acima dos 400 ms.
        RemoteRequestThread(0, leitura_lenta).launch()
        # Sem esperar o início, o pedido de interrupção do closeEvent a cancelaria antes do run().
        assert em_execucao.wait(10)
    """
)


def _truncar(texto: str) -> str:
    if len(texto) <= _TRECHO_MAXIMO:
        return texto
    return f"[...]{texto[-_TRECHO_MAXIMO:]}"


def _rodar(tmp_path: Path, nome: str, codigo: str) -> subprocess.CompletedProcess[str]:
    cenario = tmp_path / "cenario" / nome
    cenario.parent.mkdir()
    cenario.write_text(codigo, encoding="utf-8")
    comando = comando_pytest_cenario(cenario, tmp_path / "base", "-p", "tests.conftest")
    try:
        return subprocess.run(
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
        pytest.fail(f"cenário {nome} passou de {_PRAZO_SUBPROCESSO_S} s: {erro}")


def test_descarte_da_fabrica_tolera_janela_nunca_exibida_ja_fechada_e_adiada_concluida(
    tmp_path: Path,
) -> None:
    resultado = _rodar(tmp_path, "test_cenario_tolerante.py", _CENARIO_TOLERANTE)

    assert resultado.returncode == 0, (
        f"terminou com código {resultado.returncode}\n"
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )
    assert "3 passed" in resultado.stdout


def test_rede_que_nao_encerra_no_prazo_estoura_o_descarte_sem_abortar_o_processo(
    tmp_path: Path,
) -> None:
    resultado = _rodar(tmp_path, "test_cenario_estouro.py", _CENARIO_ESTOURO)

    saida = (
        f"--- stdout ---\n{_truncar(resultado.stdout)}\n"
        f"--- stderr ---\n{_truncar(resultado.stderr)}"
    )
    # Falha comum do pytest (código 1) e nunca aborto da QThread (127/134/3221226505).
    assert resultado.returncode == 1, f"código {resultado.returncode}\n{saida}"
    # O stdout do filho pode sair em cp1252: o acento vira um caractere qualquer.
    assert re.search(r"o fechamento adiado n.o concluiu em 400 ms", resultado.stdout), saida
    assert "1 error" in resultado.stdout, saida
    assert "1 passed" in resultado.stdout, saida
