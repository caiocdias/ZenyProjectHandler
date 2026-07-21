"""Configuração compartilhada dos testes."""

import os

import pytest

from zeny_project_handler.adapters.catalog import carregar_catalogo_inicial
from zeny_project_handler.domain.catalog import CatalogoTecnico

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def catalogo_inicial() -> CatalogoTecnico:
    return carregar_catalogo_inicial()
