"""Apoio para testes que fecham a janela principal e conferem o efeito logo depois."""

from __future__ import annotations

from time import monotonic, sleep

from PySide6.QtWidgets import QApplication, QWidget

# Prazo dos testes para o fechamento adiado concluir: a janela espera a rede encerrar.
PRAZO_FECHAMENTO_S = 60.0
_INTERVALO_S = 0.01


def esperar_fechamento(window: QWidget, prazo_s: float) -> None:
    """Processe eventos até a janela deixar de estar visível.

    O fechamento pode ser adiado enquanto alguma thread de rede ainda roda: a janela continua
    visível e desabilitada e fecha sozinha quando a rede encerra. Os eventos são processados ao
    menos uma vez, mesmo que a janela já tenha fechado.
    """
    limite = monotonic() + prazo_s
    while True:
        QApplication.processEvents()
        if not window.isVisible():
            return
        if monotonic() >= limite:
            raise AssertionError(f"a janela não fechou em {prazo_s} s")
        sleep(_INTERVALO_S)
