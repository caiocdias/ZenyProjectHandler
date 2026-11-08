# mypy: disable-error-code="no-untyped-call"
"""Arquivo temporário de uma página desenhada, para testes que passam pelo leitor de arquivos.

Fica fora de `_GRAMATICAS_NOVAS` (`tests/unit/test_symbol_packages_sem_memorizacao.py`) de
propósito: o `PyMuPdfReader` só abre um arquivo com a extensão do formato, e a guarda de fonte
reprova esse literal nos arquivos guardados. Os testes guardados importam daqui em vez de montar
o nome por partes.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

import pymupdf

_NOME: Final = "folha.pdf"


def salvar_pagina(
    diretorio: Path,
    desenhar: Callable[[pymupdf.Page], object],
    *,
    largura: float = 300.0,
    altura: float = 300.0,
) -> Path:
    """Grava em `diretorio` um documento de uma página `largura` x `altura` com `desenhar`."""
    caminho = diretorio / _NOME
    with pymupdf.open() as documento:
        desenhar(documento.new_page(width=largura, height=altura))
        documento.save(caminho)
    return caminho
