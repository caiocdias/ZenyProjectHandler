"""Configuração compartilhada dos testes."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Protocol

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.logging_config import LOGGER_NAME

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from zeny_project_handler.config import AppSettings
    from zeny_project_handler.ui.main_window import MainWindow

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def catalogo_inicial() -> CatalogoTecnico:
    return carregar_catalogo_inicial()


@pytest.fixture
def app_log_capture(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    """Capture o logger não propagado da aplicação sem substituir seus handlers reais."""
    logger = logging.getLogger(LOGGER_NAME)
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        yield caplog
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


class ApplicationFactory(Protocol):
    def __call__(
        self,
        argv: Sequence[str] | None = None,
        *,
        settings: AppSettings | None = None,
    ) -> tuple[QApplication, MainWindow]: ...


@pytest.fixture
def application_factory() -> Iterator[ApplicationFactory]:
    """Componha janelas e descarte seus engines antes da coleta do pytest."""
    created: list[tuple[QApplication, MainWindow]] = []

    def create(
        argv: Sequence[str] | None = None,
        *,
        settings: AppSettings | None = None,
    ) -> tuple[QApplication, MainWindow]:
        from zeny_project_handler.bootstrap import create_application

        result = create_application(argv, settings=settings)
        created.append(result)
        return result

    try:
        yield create
    finally:
        for application, window in reversed(created):
            window.close()
            window.release_resources()
            application.processEvents()
