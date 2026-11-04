# mypy: disable-error-code="no-untyped-call"
"""O cache só vale para o sha256 da chave: gravação e leitura conferem a identidade do PDF."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.cache import (
    JsonDrawingModelCache,
    chave_modelo_desenho,
)
from zeny_project_handler.adapters.analysis.drawing_model.model import ModeloDesenho
from zeny_project_handler.adapters.analysis.pymupdf_drawing_model import (
    extrair_modelo_desenho,
    obter_modelo_desenho,
)


def _pdf(caminho: Path) -> Path:
    with pymupdf.open() as documento:
        pagina = documento.new_page(width=200, height=200)
        pagina.draw_line((10, 10), (100, 10), color=(1, 0, 0), width=2)
        pagina.insert_text((30, 180), "POSTE 12", fontsize=10)
        documento.save(caminho)
    return caminho


def _chave(pdf: Path) -> str:
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    return chave_modelo_desenho(sha, f"pymupdf-{pymupdf.VersionBind}")


def test_modelo_de_outro_sha_nao_e_gravado_na_chave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    real = extrair_modelo_desenho(pdf)
    trocado = replace(real, documento_sha256="b" * 64)  # o arquivo mudou entre hash e leitura
    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", lambda _pdf: trocado)
    cache = JsonDrawingModelCache(tmp_path / "c")

    assert obter_modelo_desenho(pdf, cache) == trocado

    assert cache.obter(_chave(pdf)) is None
    assert not list((tmp_path / "c").rglob("*.json"))


def test_entrada_em_cache_de_outro_sha_e_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    real = extrair_modelo_desenho(pdf)
    cache = JsonDrawingModelCache(tmp_path / "c")
    cache.salvar(_chave(pdf), replace(real, documento_sha256="b" * 64))
    chamadas: list[Path] = []

    def _espiao(caminho: Path) -> ModeloDesenho:
        chamadas.append(caminho)
        return real

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _espiao)

    assert obter_modelo_desenho(pdf, cache) == real
    assert chamadas == [pdf]
    regravado = cache.obter(_chave(pdf))
    assert regravado is not None and regravado.documento_sha256 == real.documento_sha256
