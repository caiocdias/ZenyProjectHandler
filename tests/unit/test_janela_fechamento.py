"""Ataque ao helper ``esperar_fechamento`` (E17, Task 3).

O helper precisa esperar de verdade o fechamento adiado e estourar com mensagem clara; se ele
voltasse na hora, os testes que fecham a janela e conferem logo depois voltariam a depender da
sorte do agendamento.
"""

from __future__ import annotations

from time import monotonic

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from tests.janela_fechamento import esperar_fechamento

_ADIAMENTO_S = 0.4


class _JanelaAdiavel(QWidget):
    """Ignore o fechamento até ``liberada``, como a janela principal com a rede ainda ativa."""

    def __init__(self) -> None:
        super().__init__()
        self.liberada = False
        self.tentativas = 0

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        self.tentativas += 1
        if self.liberada:
            event.accept()
        else:
            event.ignore()


def _janela_exibida(qtbot: QtBot) -> _JanelaAdiavel:
    janela = _JanelaAdiavel()
    qtbot.addWidget(janela)
    janela.show()
    assert janela.isVisible()
    return janela


def test_espera_o_fechamento_adiado_ate_a_janela_fechar(qtbot: QtBot) -> None:
    janela = _janela_exibida(qtbot)
    assert not janela.close()
    assert janela.isVisible()

    def liberar() -> None:
        janela.liberada = True
        janela.close()

    QTimer.singleShot(int(_ADIAMENTO_S * 1000), liberar)
    inicio = monotonic()

    esperar_fechamento(janela, 30.0)

    assert not janela.isVisible()
    assert monotonic() - inicio >= _ADIAMENTO_S * 0.9


def test_estoura_com_mensagem_clara_quando_a_janela_nao_fecha_no_prazo(qtbot: QtBot) -> None:
    janela = _janela_exibida(qtbot)
    assert not janela.close()
    inicio = monotonic()
    try:
        with pytest.raises(AssertionError, match=r"a janela não fechou em 0\.3 s"):
            esperar_fechamento(janela, 0.3)
        decorrido = monotonic() - inicio
        assert 0.25 <= decorrido < 5.0
        assert janela.isVisible()
    finally:
        janela.liberada = True


def test_prazo_zero_ainda_processa_eventos_antes_de_estourar(qtbot: QtBot) -> None:
    janela = _janela_exibida(qtbot)
    assert not janela.close()
    chamados: list[str] = []
    QTimer.singleShot(0, lambda: chamados.append("evento"))
    try:
        with pytest.raises(AssertionError, match="a janela não fechou"):
            esperar_fechamento(janela, 0.0)
        assert chamados == ["evento"]
    finally:
        janela.liberada = True


def test_janela_ja_fechada_volta_sem_esperar_e_processa_os_eventos_pendentes(
    qtbot: QtBot,
) -> None:
    janela = _janela_exibida(qtbot)
    janela.liberada = True
    assert janela.close()
    chamados: list[str] = []
    QTimer.singleShot(0, lambda: chamados.append("evento"))
    inicio = monotonic()

    esperar_fechamento(janela, 30.0)

    assert chamados == ["evento"]
    assert monotonic() - inicio < 2.0
