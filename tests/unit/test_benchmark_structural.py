# mypy: disable-error-code="no-untyped-call"
"""E09 opt-in runner integration; the sealed reserve is never accessed."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from scripts.symbol_benchmark_runner import infer_pdf, structural_method_metadata

from zeny_project_handler.adapters.analysis.legacy_symbols import perfil_simbolos_legados
from zeny_project_handler.adapters.analysis.raster_symbols import (
    carregar_templates_raster,
    perfis_simbolos_raster,
)
from zeny_project_handler.adapters.analysis.structural_symbols import (
    ConfiguracaoDetectorEstrutural,
    perfil_simbolos_estruturais,
)


def test_structural_runner_adds_independent_records_without_changing_legacy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drawing.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=200, height=100)
        page.draw_line((20, 50), (60, 50), width=0.5)
        for x, height in ((45, 12), (53, 9), (61, 6)):
            page.draw_line((x, 50 - height), (x, 50 + height), width=0.5)
        document.save(source)

    baseline, base_predictions, base_executions = infer_pdf(source, "drawing")
    combined, predictions, executions = infer_pdf(source, "drawing", include_structural=True)

    assert baseline["source_before"] == combined["source_before"]
    assert combined["source_before"] == combined["source_after"]
    assert [item for item in predictions if item["method_id"] == "legacy-vector-symbols"] == (
        base_predictions
    )
    assert [
        {key: value for key, value in item.items() if key != "seconds"}
        for item in executions
        if item["method_id"] == "legacy-vector-symbols"
    ] == [
        {key: value for key, value in item.items() if key != "seconds"} for item in base_executions
    ]
    assert {item["method_id"] for item in executions} == {
        "legacy-vector-symbols",
        "structural-raster-graph",
        "structural-vector-graph",
    }
    for item in predictions:
        if item["method_id"].startswith("structural-"):
            assert item["review_required"] is True
            assert item["quantity"] is None
            assert item["association"] is None
            assert item["provenance"]["score_kind"].startswith("raw graph")


def test_structural_metadata_distinguishes_algorithm_from_shared_input() -> None:
    metadata = structural_method_metadata(
        (
            ConfiguracaoDetectorEstrutural(entrada="raster"),
            ConfiguracaoDetectorEstrutural(entrada="vetor"),
        )
    )
    assert {item["id"] for item in metadata} == {
        "structural-raster-graph",
        "structural-vector-graph",
    }
    assert len({item["algorithm_family"] for item in metadata}) == 1
    assert metadata[0]["signature"] != metadata[1]["signature"]
    assert metadata[0]["shared_sources"] != metadata[1]["shared_sources"]
    assert any("get_drawings" in source for source in metadata[1]["shared_sources"])

    raster = perfil_simbolos_estruturais(
        configuracao=ConfiguracaoDetectorEstrutural(entrada="raster")
    )
    vector = perfil_simbolos_estruturais(
        configuracao=ConfiguracaoDetectorEstrutural(entrada="vetor")
    )
    template = perfis_simbolos_raster(templates=carregar_templates_raster())[0]
    assert raster.possui_origem_correlacionada(template)
    assert vector.possui_origem_correlacionada(perfil_simbolos_legados())
    assert raster.possui_origem_correlacionada(vector)
