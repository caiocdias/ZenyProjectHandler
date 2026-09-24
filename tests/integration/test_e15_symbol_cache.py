"""E15: cache integral usa fonte e identidade operacional completas."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from tests.pdf_fixtures import create_golden_pdf

from zeny_project_handler.adapters.analysis.raster_symbols import carregar_templates_raster
from zeny_project_handler.adapters.pdf import PyMuPdfReader
from zeny_project_handler.application.symbol_reconciliation import CalibrationPolicy
from zeny_project_handler.ports.pdf import ReferenciaFontePdf
from zeny_project_handler_server.config import ServerSettings
from zeny_project_handler_server.symbol_execution import SymbolCompositionRunner

pytestmark = pytest.mark.integration


class CacheMissError(RuntimeError):
    pass


def test_integral_cache_reuses_exact_snapshot_and_invalidates_changed_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf = create_golden_pdf(tmp_path / "cache-source.pdf")
    inspection = PyMuPdfReader().inspecionar(pdf)
    document = inspection.documento
    source = ReferenciaFontePdf(
        documento_id=document.id,
        projeto_id=uuid4(),
        caminho_canonico=pdf.resolve(),
        sha256=document.sha256,
        tamanho_bytes=pdf.stat().st_size,
        modificado_em_ns=pdf.stat().st_mtime_ns,
    )
    settings = ServerSettings(
        password="senha segura para cache E15",
        market_sqlserver_connection_string="fixture-market-connection",
        data_directory=tmp_path / "server-data",
        symbol_composition=True,
    )
    runner = SymbolCompositionRunner(settings)
    expected = runner.run(document, source)
    assert len(list(runner.cache_directory.glob("*.json"))) == 1

    def cache_miss(*_args: object, **_kwargs: object) -> object:
        raise CacheMissError("observação executada após invalidação")

    monkeypatch.setattr(SymbolCompositionRunner, "_observe_page", cache_miss)
    assert runner.run(document, source) == expected

    templates = carregar_templates_raster()
    changed_template = replace(templates[0], id=f"{templates[0].id}-changed")
    variants = (
        SymbolCompositionRunner(replace(settings, symbol_profile="vector-only")),
        SymbolCompositionRunner(
            replace(settings, symbol_calibration_version="e15-cache-calibration-2")
        ),
        SymbolCompositionRunner(settings, templates=(changed_template, *templates[1:])),
        SymbolCompositionRunner(settings, calibration=CalibrationPolicy(minimum_samples=31)),
    )
    for changed in variants:
        assert changed.signature != runner.signature
        with pytest.raises(CacheMissError):
            changed.run(document, source)
    assert len(list(runner.cache_directory.glob("*.json"))) == 1
