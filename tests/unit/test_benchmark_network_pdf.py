from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from scripts.benchmark_network_pdf import TimedTesseract, benchmark, json_value, verify_ocr
from tests.pdf_fixtures import create_analysis_pdf, create_network_benchmark_pdf

from zeny_project_handler.adapters.analysis import TesseractCliOcr
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
    assert stored["native"]["export"]["verified"]
    assert len(stored["native"]["results"]["proposals"]) == counts["proposals"]
    assert len(stored["native"]["export"]["sheets"][0]["rows"]) == counts["proposals"]
    assert len(stored["native"]["export"]["sheets"][1]["rows"]) == counts["spans"]
    assert not list(tmp_path.glob("benchmark-native-*"))
    assert "annotation_rendering" not in stored
    assert "documentation" not in stored["native"]
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


def test_telemetry_renders_both_layers_and_projects_documentation(tmp_path: Path) -> None:
    source = create_network_benchmark_pdf(tmp_path / "synthetic.pdf")
    with pymupdf.open(source) as document:  # type: ignore[no-untyped-call]
        rectangle = pymupdf.Rect(10, 10, 120, 40)  # type: ignore[no-untyped-call]
        document[0].add_freetext_annot(rectangle, "REVISAO TESTE")
        document.saveIncr()
    original = source.read_bytes()
    report = benchmark(source, tmp_path / "report.json", tmp_path, native_only=True, telemetry=True)
    layers = report["annotation_rendering"]
    assert [item["annotations"] for item in layers] == [False, True]
    assert all(item["annotation_count"] == 1 for item in layers)
    assert layers[0]["raster_sha256"] != layers[1]["raster_sha256"]
    assert report["native"]["documentation"]["dto"]["sections"]
    assert report["native"]["export"]["verified"]
    sheet_names = [sheet.name for sheet in report["native"]["export"]["sheets"]]
    assert sheet_names[:3] == ["Elementos", "Vãos", "Trechos físicos"]
    assert "Documentação" in sheet_names
    assert source.read_bytes() == original
    plain = benchmark(source, tmp_path / "plain.json", tmp_path, native_only=True)
    assert plain["native"]["counts"] == report["native"]["counts"]
    assert [item.id for item in plain["native"]["semantic"].elementos] == [
        item.id for item in report["native"]["semantic"].elementos
    ]


@pytest.mark.parametrize("fails", [False, True])
def test_timing_preserves_all_ocr_modes_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fails: bool
) -> None:
    executable = tmp_path / "synthetic.exe"
    executable.touch()
    received: list[tuple[int, str | None, bool]] = []

    def recognize(
        self: TesseractCliOcr,
        pagina: PaginaRasterOcr,
        *,
        page_segmentation_mode: int,
        character_whitelist: str | None = None,
        technical_glyphs: bool = False,
    ) -> tuple[TrechoTextoOcr, ...]:
        received.append((page_segmentation_mode, character_whitelist, technical_glyphs))
        if fails:
            raise RuntimeError("synthetic failure")
        return ()

    monkeypatch.setattr(TesseractCliOcr, "_recognize", recognize)
    timed = TimedTesseract(executable)
    plain = TesseractCliOcr(executable)
    page = PaginaRasterOcr(
        pagina_numero=1, largura_pixels=1, altura_pixels=1, stride=3, dados_rgb=b"abc", dpi=150
    )
    methods = (
        "reconhecer",
        "reconhecer_glifos",
        "reconhecer_identificador",
        "reconhecer_rotulo_operacional",
        "reconhecer_bloco_operacional",
    )
    for method in methods:
        for engine in (plain, timed):
            if fails:
                with pytest.raises(RuntimeError, match="synthetic failure"):
                    getattr(engine, method)(page)
            else:
                assert getattr(engine, method)(page) == ()
    assert received[::2] == received[1::2]
    assert len(timed.calls) == 5
    assert all(call["completed"] is (not fails) for call in timed.calls)
    assert all(call["seconds"] >= 0 for call in timed.calls)
