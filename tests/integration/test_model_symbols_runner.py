# mypy: disable-error-code="no-untyped-call"
"""E06.2.2.1: o método sobre o modelo de desenho como quinto método do runner opt-in."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pymupdf
import pytest

from zeny_project_handler.adapters.analysis import pymupdf_drawing_model
from zeny_project_handler.adapters.analysis.drawing_model.glyph_table import (
    TabelaGlifos,
    carregar_tabela_glifos,
)
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.domain.documents import DocumentoProjeto
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_server import symbol_execution
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import (
    SymbolCompositionError,
    SymbolCompositionRunner,
)

pytestmark = pytest.mark.integration

_METODO_NOVO = "declarative-drawing-model"
_MOLDURA_CT = (101.0, 115.0, 169.0, 149.0)
_PRETO = (0, 0, 0)


def _settings(data: Path, **opcoes: Any) -> ServerSettings:
    return ServerSettings(
        password="senha segura do metodo do modelo",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=data,
        symbol_composition=True,
        symbol_profile="vector-only",
        **opcoes,
    )


def _pdf(caminho: Path, *, paginas: int = 2, ocg: bool = False, imagem: bool = False) -> Path:
    with pymupdf.open() as documento:
        oc = documento.add_ocg("REDE") if ocg else 0
        for _ in range(paginas):
            pagina = documento.new_page(width=300, height=300)
            if imagem:
                pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), False)
                pixmap.clear_with(128)
                pagina.insert_image(pymupdf.Rect(10, 10, 30, 30), pixmap=pixmap)
            else:
                pagina.draw_rect(pymupdf.Rect(_MOLDURA_CT), color=_PRETO, width=1, oc=oc)
                pagina.insert_text((_MOLDURA_CT[0] + 6, _MOLDURA_CT[1] + 25), "CT", fontsize=11)
        documento.save(caminho)
    return caminho


def _fonte(pdf: Path) -> tuple[DocumentoProjeto, ReferenciaFontePdf]:
    documento = PyMuPdfReader().inspecionar(pdf).documento
    return documento, ReferenciaFontePdf(
        documento_id=documento.id,
        projeto_id=uuid4(),
        caminho_canonico=pdf.resolve(),
        sha256=documento.sha256,
        tamanho_bytes=pdf.stat().st_size,
        modificado_em_ns=pdf.stat().st_mtime_ns,
    )


def _journals(runner: SymbolCompositionRunner) -> list[dict[str, Any]]:
    arquivos = sorted(runner.partial_directory.glob("*.json"), key=lambda a: a.stat().st_mtime_ns)
    return [json.loads(arquivo.read_text(encoding="utf-8")) for arquivo in arquivos]


def _cobertura_do_novo(journal: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        cobertura
        for resultado in journal["results"]
        if resultado["method_id"] == _METODO_NOVO
        for cobertura in resultado["coverage"]
    ]


def test_quinto_metodo_roda_e_entra_na_assinatura(tmp_path: Path) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf"))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    runner.run(documento, fonte)

    (journal,) = _journals(runner)
    assert journal["status"] == "completed"
    assert [item["page"] for item in _cobertura_do_novo(journal)] == [1, 2]
    assert len(runner._profiles) == 5
    assert _METODO_NOVO in {profile.metodo_id for profile in runner._profiles}
    assert [item["status"] for item in _cobertura_do_novo(journal)] == ["CONCLUIDO"] * 2


@pytest.mark.parametrize("ocg", [False, True], ids=["sem-ocg", "com-ocg"])
def test_mesmo_desenho_nao_duplica_na_reconciliacao(tmp_path: Path, ocg: bool) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1, ocg=ocg))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))
    novo = next(p for p in runner._profiles if p.metodo_id == _METODO_NOVO).assinatura()

    composto = runner.run(documento, fonte)

    com_o_novo = [
        ocorrencia
        for ocorrencia in composto.occurrences
        if any(o.metodo_assinatura == novo for o in ocorrencia.observations)
    ]
    assert len(com_o_novo) == 1
    assert len({o.metodo_assinatura for o in com_o_novo[0].observations}) == 2


@pytest.mark.parametrize(
    "modulo",
    ["symbol_matcher", "glyph_signature", "pymupdf_annotations"],
)
def test_assinatura_muda_com_tabela_e_com_modulo_do_nucleo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modulo: str
) -> None:
    configuracao = _settings(tmp_path / "dados")
    original = SymbolCompositionRunner(configuracao).signature
    tabela: TabelaGlifos = carregar_tabela_glifos()
    outra = replace(tabela, sha256="b" * 64)
    assert SymbolCompositionRunner(configuracao, glyph_table=outra).signature != original

    digest_original = symbol_execution._module_digest

    def digest(alvo: Any) -> str:
        if alvo.__name__.rsplit(".", 1)[-1] == modulo:
            return "alterado"
        return digest_original(alvo)

    monkeypatch.setattr(symbol_execution, "_module_digest", digest)

    assert SymbolCompositionRunner(configuracao).signature != original


def test_teto_no_metodo_novo_e_cacheado_e_nao_derruba_os_outros(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1))
    monkeypatch.setattr(symbol_execution, "LIMITE_CONSULTAS_PAGINA", 1)
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    runner.run(documento, fonte)
    runner.run(documento, fonte)

    primeiro, segundo = _journals(runner)
    assert primeiro["status"] == "completed"
    assert segundo["status"] == "cache_hit"
    (cobertura,) = _cobertura_do_novo(primeiro)
    assert (cobertura["status"], cobertura["reason"]) == ("FORA_DOMINIO", "teto_consultas")
    outros = [r for r in primeiro["results"] if r["method_id"] != _METODO_NOVO]
    assert len(outros) == 4
    assert any(r["observations"] for r in outros)


def test_falha_de_fonte_aborta_e_nao_entra_no_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documento, fonte = _fonte(_pdf(tmp_path / "a.pdf", paginas=1))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    def falhar(_pagina: Any) -> Any:
        raise RuntimeError("falha de caminhos")

    monkeypatch.setattr(pymupdf_drawing_model, "_caminhos_e_glifos", falhar)

    with pytest.raises(SymbolCompositionError, match=r"modelo.caminhos_falhou"):
        runner.run(documento, fonte)

    assert not list(runner.cache_directory.glob("*.json"))
    assert _journals(runner)[-1]["status"] == "failed"


def test_residuo_raster_nao_gera_proposta(tmp_path: Path) -> None:
    com_imagem, fonte_com = _fonte(_pdf(tmp_path / "com.pdf", paginas=1, imagem=True))
    runner = SymbolCompositionRunner(_settings(tmp_path / "dados"))

    composto = runner.run(com_imagem, fonte_com)

    assert composto.occurrences == ()
    (cobertura,) = _cobertura_do_novo(_journals(runner)[-1])
    assert cobertura["status"] == "NAO_DETECCAO"
    assert cobertura["reason"] == "residuo_raster:1"
