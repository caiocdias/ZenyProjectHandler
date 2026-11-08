"""Lacunas da guarda de fonte por AST: comentários, bytes e inteiros grandes.

A guarda por AST não vê comentários (a textual via), `bytes` nem inteiros. Aqui os dois fontes
cobertos são varridos por `tokenize`/AST para esses três canais, e a varredura é provada capaz
de reprovar (casos sintéticos). Nada da guarda existente é alterado.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest
from tests.unit.test_symbol_packages_sem_memorizacao import (
    _GRAMATICAS_NOVAS,
    _violacoes_de_texto,
)

_INTEIRO_GRANDE = 100_000


def _violacoes_de_comentarios(fonte: str, nome: str) -> list[str]:
    violacoes: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(fonte).readline):
        if token.type == tokenize.COMMENT:
            violacoes.extend(_violacoes_de_texto(token.string, f"{nome}:{token.start[0]}"))
    return violacoes


def _violacoes_de_bytes_e_inteiros(fonte: str, nome: str) -> list[str]:
    violacoes: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.Constant):
            continue
        local = f"{nome}:{no.lineno}"
        if isinstance(no.value, bytes):
            violacoes.extend(_violacoes_de_texto(no.value.decode("latin-1"), local))
        elif isinstance(no.value, bool):
            continue
        elif isinstance(no.value, int) and abs(no.value) >= _INTEIRO_GRANDE:
            violacoes.append(f"{local}: inteiro grande ({no.value})")
    return violacoes


@pytest.mark.parametrize("arquivo", _GRAMATICAS_NOVAS, ids=lambda a: a.name)
def test_comentarios_dos_fontes_novos_passam_na_guarda(arquivo: Path) -> None:
    assert _violacoes_de_comentarios(arquivo.read_text(encoding="utf-8"), arquivo.name) == []


@pytest.mark.parametrize("arquivo", _GRAMATICAS_NOVAS, ids=lambda a: a.name)
def test_bytes_e_inteiros_dos_fontes_novos_passam_na_guarda(arquivo: Path) -> None:
    fonte = arquivo.read_text(encoding="utf-8")
    assert _violacoes_de_bytes_e_inteiros(fonte, arquivo.name) == []


@pytest.mark.parametrize(
    "fonte",
    [
        pytest.param("x = 1  # veja folha.pdf\n", id="comentario-pdf"),
        pytest.param("# 612345.678,7654321.123\nx = 1\n", id="comentario-coordenada"),
        pytest.param("# " + "ab" * 32 + "\nx = 1\n", id="comentario-sha256"),
    ],
)
def test_varredura_de_comentarios_reprova(fonte: str) -> None:
    assert _violacoes_de_comentarios(fonte, "s.py") != []


@pytest.mark.parametrize(
    "fonte",
    [
        pytest.param('x = b"folha.pdf"\n', id="bytes-pdf"),
        pytest.param("x = 7654321\n", id="inteiro-de-utm"),
    ],
)
def test_varredura_de_bytes_e_inteiros_reprova(fonte: str) -> None:
    assert _violacoes_de_bytes_e_inteiros(fonte, "s.py") != []


def test_varredura_aceita_comentario_e_inteiro_comuns() -> None:
    fonte = "# haste de 3 barras, 1.25 pt\nx = 20000\ny = b'ok'\n"
    assert _violacoes_de_comentarios(fonte, "s.py") == []
    assert _violacoes_de_bytes_e_inteiros(fonte, "s.py") == []
