# mypy: disable-error-code="no-untyped-call"
"""Balanced E16 run keeps legend context consistent in composition, cache, and journal."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pymupdf
import pytest

from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.symbol_reconciliation import SymbolReconciliation
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration


def _draw_ground(page: pymupdf.Page, *, x: float, y: float) -> None:
    page.draw_line((x - 15, y), (x, y), color=(0, 0, 0), width=0.5)
    for index, height in enumerate((5.0, 3.5, 2.0)):
        point = x + index * 4
        page.draw_line((point, y - height), (point, y + height), color=(0, 0, 0), width=0.5)


def _author_pdf(path: Path) -> Path:
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=400, height=240)
        page.insert_text((40, 34), "LEGENDA", fontsize=12)
        _draw_ground(page, x=70, y=63)
        _draw_ground(page, x=70, y=170)
        pdf.save(path)
    return path


def _observation_ids(composition: SymbolReconciliation) -> set[str]:
    return {item.id for occurrence in composition.occurrences for item in occurrence.observations}


def test_balanced_context_ids_survive_composition_cache_and_reopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf = _author_pdf(tmp_path / "author-legend.pdf")
    document = PyMuPdfReader().inspecionar(pdf).documento
    source = ReferenciaFontePdf(
        documento_id=document.id,
        projeto_id=uuid4(),
        caminho_canonico=pdf.resolve(),
        sha256=document.sha256,
        tamanho_bytes=pdf.stat().st_size,
        modificado_em_ns=pdf.stat().st_mtime_ns,
    )
    settings = ServerSettings(
        password="senha segura para contexto E16",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
        symbol_composition=True,
        symbol_profile="balanced",
    )
    runner = SymbolCompositionRunner(settings)
    first = runner.run(document, source)
    cached = runner._read_cache(document)
    assert cached is not None
    legacy = next(item for item in cached if item.perfil.metodo_id == "pymupdf-symbols-legacy")
    assert len(legacy.observacoes) >= 2
    legend = [
        item for item in legacy.observacoes if dict(item.atributos).get("contexto") == "legenda"
    ]
    operational = [
        item for item in legacy.observacoes if dict(item.atributos).get("contexto") != "legenda"
    ]
    assert len(legend) == 1
    assert operational
    assert dict(legend[0].atributos)["papel"] == "informative"
    assert {item.id for item in legacy.observacoes} <= _observation_ids(first)
    legend_occurrence = next(
        occurrence
        for occurrence in first.occurrences
        if legend[0].id in {item.id for item in occurrence.observations}
    )
    assert legend_occurrence.decision == "review"
    assert "legend_reference" in legend_occurrence.reasons

    journals = sorted((settings.data_directory / "symbol_partial_runs").glob("*.json"))
    assert len(journals) == 1
    journal = json.loads(journals[0].read_text(encoding="utf-8"))
    assert journal["status"] == "completed"
    assert journal["cache_status"] == "stored"
    assert journal["legend_contextualized"] >= 1
    legacy_journal = next(
        row for row in journal["results"] if row["method_id"] == "pymupdf-symbols-legacy"
    )
    assert {row["id"] for row in legacy_journal["observations"]} == {
        item.id for item in legacy.observacoes
    }

    def unexpected_inference(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("cache hit reprocessed a detector")

    monkeypatch.setattr(SymbolCompositionRunner, "_observe_page", unexpected_inference)
    reopened = SymbolCompositionRunner(settings).run(document, source)
    assert _observation_ids(reopened) == _observation_ids(first)
    assert any(
        occurrence.decision == "review"
        and "legend_reference" in occurrence.reasons
        and legend[0].id in {item.id for item in occurrence.observations}
        for occurrence in reopened.occurrences
    )
    journals = sorted((settings.data_directory / "symbol_partial_runs").glob("*.json"))
    assert len(journals) == 2
    assert any(
        json.loads(path.read_text(encoding="utf-8"))["status"] == "cache_hit" for path in journals
    )
