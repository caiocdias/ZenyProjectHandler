"""A fábrica de janelas só libera a janela depois de juntar a thread de observação do painel."""

from __future__ import annotations

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

pytestmark = pytest.mark.integration


@pytest.fixture
def destruir_janelas_depois_da_fabrica() -> Iterator[list[MainWindow]]:
    """Destrói o objeto C++ depois do descarte da fábrica, como o coletor faz num teste real."""
    janelas: list[MainWindow] = []
    yield janelas
    for janela in janelas:
        delete(janela)
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_leitura_de_sessao_mais_lenta_que_o_fechamento_nao_destroi_thread_em_execucao(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    destruir_janelas_depois_da_fabrica: list[MainWindow],
    application_factory: ApplicationFactory,
) -> None:
    # Sem a junção do descarte, destruir o painel com a QThread viva aborta o processo inteiro
    # (QThread: Destroyed while thread is still running), como ocorria sob carga paralela.
    original = DirectProjectGateway.session

    def sessao_lenta(self: DirectProjectGateway):  # type: ignore[no-untyped-def]
        time.sleep(1.6)
        return original(self)

    monkeypatch.setattr(DirectProjectGateway, "session", sessao_lenta)
    _app, window = application_factory(
        [], settings=ClientSettings(data_directory=tmp_path / "lento")
    )
    destruir_janelas_depois_da_fabrica.append(window)
