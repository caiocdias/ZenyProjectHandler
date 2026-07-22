"""Porta neutra para reconstrução das projeções de grafo."""

from __future__ import annotations

from typing import Protocol

from zeny_project_handler.domain.catalog import CatalogoTecnico
from zeny_project_handler.domain.graph import ResultadoReconstrucaoGrafo
from zeny_project_handler.domain.project import Projeto


class ReconstrutorGrafoPort(Protocol):
    nome: str
    versao: str

    def reconstruir(
        self, projeto: Projeto, catalogo: CatalogoTecnico
    ) -> ResultadoReconstrucaoGrafo: ...
