# mypy: disable-error-code="no-untyped-call"
"""Cache JSON do modelo de desenho: ida e volta, invalidação e tolerância a falhas."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

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
        pagina.draw_circle((100, 100), 20, color=(0, 0, 1))
        pagina.draw_rect(pymupdf.Rect(20, 120, 80, 160), color=(0, 0, 0), fill=(0, 1, 0))
        pagina.insert_text((30, 180), "POSTE 12", fontsize=10)
        documento.save(caminho)
    return caminho


def _chave() -> str:
    return chave_modelo_desenho("a" * 64, "pymupdf-teste")


def _arquivo_do_cache(raiz: Path) -> Path:
    return next((raiz / "modelo-desenho").glob("*.json"))


def test_ida_e_volta_preserva_o_modelo(tmp_path: Path) -> None:
    modelo = extrair_modelo_desenho(_pdf(tmp_path / "a.pdf"))
    assert modelo.paginas[0].caminhos
    assert modelo.paginas[0].textos
    familia = replace(
        modelo.familia, sinais=(*modelo.familia.sinais, ("razao", Decimal("0.125")), ("n", None))
    )
    modelo = replace(modelo, familia=familia)
    cache = JsonDrawingModelCache(tmp_path / "cache")

    cache.salvar(_chave(), modelo)

    lido = cache.obter(_chave())
    assert lido == modelo
    assert lido is not None
    assert ("razao", Decimal("0.125")) in lido.familia.sinais


def test_chave_depende_de_documento_versao_e_leitor() -> None:
    base = chave_modelo_desenho("a" * 64, "l1")
    assert base == chave_modelo_desenho("a" * 64, "l1")
    assert base != chave_modelo_desenho("b" * 64, "l1")
    assert base != chave_modelo_desenho("a" * 64, "l2")
    assert base != chave_modelo_desenho("a" * 64, "l1", versao="outra")


def test_segunda_chamada_usa_o_cache_sem_reextrair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "cache")
    primeiro = obter_modelo_desenho(pdf, cache)

    def _proibido(_pdf: Path) -> ModeloDesenho:
        raise AssertionError("não deveria reextrair")

    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", _proibido)
    assert obter_modelo_desenho(pdf, cache) == primeiro


def test_versao_diferente_invalida_o_cache(tmp_path: Path) -> None:
    modelo = extrair_modelo_desenho(_pdf(tmp_path / "a.pdf"))
    cache = JsonDrawingModelCache(tmp_path / "cache")
    cache.salvar(_chave(), replace(modelo, versao="modelo-desenho-antigo"))
    assert cache.obter(_chave()) is None

    cache.salvar(_chave(), modelo)
    alvo = _arquivo_do_cache(tmp_path / "cache")
    bruto: dict[str, Any] = json.loads(alvo.read_text(encoding="utf-8"))
    bruto["schema_version"] = 999
    alvo.write_text(json.dumps(bruto), encoding="utf-8")
    assert cache.obter(_chave()) is None


def test_json_corrompido_e_ignorado(tmp_path: Path) -> None:
    modelo = extrair_modelo_desenho(_pdf(tmp_path / "a.pdf"))
    cache = JsonDrawingModelCache(tmp_path / "cache")
    cache.salvar(_chave(), modelo)
    alvo = _arquivo_do_cache(tmp_path / "cache")

    alvo.write_text("{nao e json", encoding="utf-8")
    assert cache.obter(_chave()) is None
    alvo.write_text('{"schema_version":1,"modelo":{"versao":"x"}}', encoding="utf-8")
    assert cache.obter(_chave()) is None
    assert cache.obter(chave_modelo_desenho("c" * 64, "x")) is None


def test_chave_invalida_e_rejeitada(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        JsonDrawingModelCache(tmp_path).obter("../fora")


def test_falha_de_gravacao_nao_derruba_a_extracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "cache")

    def _falha(self: JsonDrawingModelCache, chave: str, modelo: ModeloDesenho) -> None:
        raise OSError("disco cheio")

    monkeypatch.setattr(JsonDrawingModelCache, "salvar", _falha)
    assert obter_modelo_desenho(pdf, cache) == extrair_modelo_desenho(pdf)


def test_falha_de_leitura_do_cache_nao_derruba_a_extracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")

    def _falha(self: JsonDrawingModelCache, chave: str) -> ModeloDesenho | None:
        raise RuntimeError("quebrou")

    monkeypatch.setattr(JsonDrawingModelCache, "obter", _falha)
    cache = JsonDrawingModelCache(tmp_path / "cache")
    assert obter_modelo_desenho(pdf, cache) == extrair_modelo_desenho(pdf)


def test_modelo_com_diagnostico_de_falha_nao_e_gravado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    cache = JsonDrawingModelCache(tmp_path / "cache")
    real = extrair_modelo_desenho(pdf)
    pagina = replace(real.paginas[0], diagnosticos=("modelo.imagens_anotacao_falhou",))
    quebrado = replace(real, paginas=(pagina,))
    monkeypatch.setattr(pymupdf_drawing_model, "extrair_modelo_desenho", lambda _p: quebrado)

    assert obter_modelo_desenho(pdf, cache) == quebrado
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_sem_cache_apenas_extrai(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path / "a.pdf")
    assert obter_modelo_desenho(pdf, None) == extrair_modelo_desenho(pdf)
