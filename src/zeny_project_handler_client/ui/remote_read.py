"""Trabalho HTTP finito sem referências a widgets, com descarte por geração."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

_RUNNING: set[RemoteRequestThread] = set()


class RemoteRequestThread(QThread):
    received = Signal(int, object)

    def __init__(self, generation: int, request: Callable[[], object]) -> None:
        super().__init__()
        self._generation = generation
        self._request = request

    def launch(self) -> None:
        _RUNNING.add(self)
        self.finished.connect(self._dispose)
        self.start()

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            result = self._request()
        except Exception as error:
            result = error
        if not self.isInterruptionRequested():
            self.received.emit(self._generation, result)

    def _dispose(self) -> None:
        _RUNNING.discard(self)
        self.deleteLater()
