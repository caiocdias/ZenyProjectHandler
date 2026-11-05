"""Trabalho HTTP finito sem referências a widgets, com descarte por geração."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import QDeadlineTimer, QObject, QThread, Signal, SignalInstance

_RUNNING: set[RemoteRequestThread] = set()


class _Notificador(QObject):
    terminou = Signal()


class NotificadorDeTermino:
    """Avisa, na thread principal, que uma thread saiu do registro do módulo.

    O ``QObject`` só nasce no primeiro uso, sempre na thread principal (``launch()`` ou o painel
    que pede o encerramento), e nunca na importação do módulo.
    """

    def __init__(self) -> None:
        self._objeto: _Notificador | None = None

    def preparar(self) -> None:
        self._criado()

    @property
    def terminou(self) -> SignalInstance:
        return self._criado().terminou

    def _criado(self) -> _Notificador:
        if self._objeto is None:
            self._objeto = _Notificador()
        return self._objeto


notificador_leituras = NotificadorDeTermino()


def threads_ativas(registro: Iterable[QThread]) -> bool:
    """Conte só as threads rodando: a que terminou e aguarda o ``_dispose`` não conta."""
    return any(thread.isRunning() for thread in tuple(registro))


def interromper_threads(registro: Iterable[QThread]) -> None:
    for thread in tuple(registro):
        thread.requestInterruption()


def aguardar_threads(registro: Iterable[QThread], prazo: QDeadlineTimer) -> bool:
    return all(thread.wait(prazo) for thread in tuple(registro))


def leituras_ativas() -> bool:
    return threads_ativas(_RUNNING)


def interromper_leituras() -> None:
    interromper_threads(_RUNNING)


def aguardar_leituras(prazo: QDeadlineTimer) -> bool:
    return aguardar_threads(_RUNNING, prazo)


class RemoteRequestThread(QThread):
    received = Signal(int, object)

    def __init__(self, generation: int, request: Callable[[], object]) -> None:
        super().__init__()
        self._generation = generation
        self._request = request

    def launch(self) -> None:
        notificador_leituras.preparar()
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
        notificador_leituras.terminou.emit()
        self.deleteLater()
