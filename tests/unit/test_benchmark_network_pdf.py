from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.benchmark_network_pdf import benchmark, json_value, verify_ocr
from tests.pdf_fixtures import create_analysis_pdf, create_network_benchmark_pdf

from zeny_project_handler.adapters.analysis.tesseract_runtime import RuntimeTesseract
from zeny_project_handler.ports.analysis import (
    PaginaRasterOcr,
    ResultadoConsultaCapacidadeOcr,
    TrechoTextoOcr,
)


class EmptyOcr:
    nome = "synthetic"

    def consultar_capacidade(self) -> ResultadoConsultaCapacidadeOcr:
        return ResultadoConsultaCapacidadeOcr(capacidade=None)

    def reconhecer(self, pagina: PaginaRasterOcr) -> tuple[TrechoTextoOcr, ...]:
        return ()


def test_native_benchmark_persists_promotes_and_preserves_source(tmp_path: Path) -> None:
    source = create_network_benchmark_pdf(tmp_path / "synthetic.pdf")
    original = source.read_bytes()
    output = tmp_path / "report.json"
    report = benchmark(source, output, tmp_path, native_only=True)
    counts = report["native"]["counts"]
    assert report["source_unchanged"]
    assert counts["raw_proposals"] >= counts["proposals"] > 0
    assert counts["confirmed"] > 0
    assert counts["regions"] > 0
    assert counts["spans"] > 0
    assert source.read_bytes() == original
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["native"]["extraction"]["evidencias"][0]["geometria"]
    assert stored["native"]["decisions"]
    assert not list(tmp_path.glob("benchmark-native-*"))
    repeated = benchmark(source, tmp_path / "repeat.json", tmp_path, native_only=True)
    first_ids = [p.id for p in report["native"]["semantic"].elementos]
    assert first_ids == [p.id for p in repeated["native"]["semantic"].elementos]


def test_benchmark_refuses_to_overwrite_source(tmp_path: Path) -> None:
    source = create_analysis_pdf(tmp_path / "synthetic.pdf")
    original = source.read_bytes()
    with pytest.raises(ValueError, match="origem"):
        benchmark(source, source, tmp_path, native_only=True)
    assert source.read_bytes() == original


def test_benchmark_requires_portuguese_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_analysis_pdf(tmp_path / "synthetic.pdf")
    monkeypatch.setattr(
        "scripts.benchmark_network_pdf.inspect_tesseract_runtime",
        lambda _: RuntimeTesseract(executavel=None, diretorio_tessdata=None),
    )
    with pytest.raises(RuntimeError, match="português"):
        benchmark(source, tmp_path / "report.json", tmp_path)
    assert not (tmp_path / "report.json").exists()


def test_ocr_control_rejects_silent_empty_output() -> None:
    with pytest.raises(RuntimeError, match="controle sintético"):
        verify_ocr(EmptyOcr())


def test_report_rejects_unknown_values() -> None:
    with pytest.raises(TypeError):
        json_value(object())
