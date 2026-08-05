"""Configuração compartilhada dos testes."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.logging_config import LOGGER_NAME

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
