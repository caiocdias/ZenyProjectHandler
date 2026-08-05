"""Construtores de caminhos para regressões de compatibilidade com o Windows."""

from __future__ import annotations

from pathlib import Path

_NEAR_WINDOWS_PATH_LIMIT = 245
_WINDOWS_PATH_LIMIT = 260


def near_windows_path_limit(root: Path, filename: str) -> Path:
    """Crie um destino válido, mas próximo do limite clássico do Windows."""
    parent = root.resolve() / "near-limit"
    initial = parent / filename
    if len(str(initial)) >= _WINDOWS_PATH_LIMIT:
        raise AssertionError("O basetemp já é longo demais para montar a regressão Windows")

    while len(str(parent / filename)) < _NEAR_WINDOWS_PATH_LIMIT:
        missing = _NEAR_WINDOWS_PATH_LIMIT - len(str(parent / filename))
        parent /= "d" * min(24, max(1, missing - 1))

    parent.mkdir(parents=True)
    destination = parent / filename
    assert _NEAR_WINDOWS_PATH_LIMIT <= len(str(destination)) < _WINDOWS_PATH_LIMIT
    return destination
