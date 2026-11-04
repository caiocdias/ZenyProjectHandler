# mypy: disable-error-code="no-untyped-call"
"""Cache: hit com o mesmo sha256 é servido sem reextrair."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.test_drawing_model_cache_sha import _chave, _pdf

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.cache import JsonDrawingModelCache
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    obter_modelo_desenho,
)


def test_hit_com_mesmo_sha_nao_reextrai(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    real = extrair_modelo_desenho(pdf)
    cache = JsonDrawingModelCache(tmp_path / "c")
    cache.salvar(_chave(pdf), real)

    def _proibido(_pdf: Path) -> object:
        raise AssertionError("hit válido não pode reextrair")

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _proibido)

    assert obter_modelo_desenho(pdf, cache) == real
