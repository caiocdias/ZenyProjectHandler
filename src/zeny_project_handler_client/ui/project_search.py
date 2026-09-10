"""Consulta de sugestões Qt, sem referências a widgets no trabalho remoto."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from zeny_project_handler_contracts.projects import ProjectSummaryListResponse

# Uma leitura HTTP já iniciada termina pelo timeout do gateway. Manter sua thread viva
# até então permite destruir o painel sem destruir uma QThread ainda em execução.
_RUNNING_SEARCHES: set[ProjectSearchThread] = set()


class ProjectSearchThread(QThread):
    received = Signal(int, str, object)

    def __init__(
        self,
        generation: int,
        query: str,
        read: Callable[[], ProjectSummaryListResponse],
    ) -> None:
        super().__init__()
        self.generation = generation
        self.query = query
        self._read = read

    def launch(self) -> None:
        _RUNNING_SEARCHES.add(self)
        self.finished.connect(self._dispose)
        self.start()

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        try:
            result: object = self._read()
        except Exception as error:
            result = error
        if not self.isInterruptionRequested():
            self.received.emit(self.generation, self.query, result)

    def _dispose(self) -> None:
        _RUNNING_SEARCHES.discard(self)
        self.deleteLater()
