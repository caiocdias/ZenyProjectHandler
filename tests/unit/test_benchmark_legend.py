"""E10 runner boundary: local unknowns remain outside frozen E02 metrics."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.symbol_benchmark_runner as runner
from scripts.symbol_benchmark_runner import infer_pdf, run_synthetic
from tests.unit.test_legend_symbols import _document


def test_legend_opt_in_keeps_closed_baseline_and_source_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = run_synthetic(tmp_path / "baseline")
    monkeypatch.setattr(
        runner,
        "extrair_leituras_ocr_legenda",
        lambda _document: ((), ("OCR unavailable in control",)),
    )
    combined = run_synthetic(tmp_path / "legend", include_legend=True, include_legend_ocr=True)

    assert (
        combined["report"]["methods"]["legacy-vector-symbols"]["micro"]
        == baseline["report"]["methods"]["legacy-vector-symbols"]["micro"]
    )
    assert combined["manifest"]["legend_configuration_unchanged"]
    assert combined["manifest"]["counts"]["pages_failed"] == 0
    assert all(
        "OCR unavailable in control" in document["legend_reference"]["diagnostics"]
        for document in combined["manifest"]["documents"]
    )

    from json import loads

    payload = loads((tmp_path / "legend" / "predictions.json").read_text(encoding="utf-8"))
    assert "document-local-legend" in {method["id"] for method in payload["methods"]}
    documents = {item["id"]: item["sha256"] for item in payload["documents"]}
    for item in payload["local_candidates"]:
        assert item["provenance"]["document_sha256"] == documents[item["document_id"]]
        assert item["context"] == "operational"
        assert item["review_required"]
        assert item["class_id"] == "UNKNOWN_LOCAL"


def test_runner_exposes_document_local_candidate_without_legend_exemplar(tmp_path: Path) -> None:
    source = tmp_path / "local-convention.pdf"
    with _document(occurrences=(2,), pages=2) as document:
        document.save(source)

    manifest, closed_predictions, executions = infer_pdf(
        source, "project-a/local-convention", include_legend=True
    )

    assert manifest["status"] == "executed"
    assert not closed_predictions
    assert any(
        item["descricao"] == "ANCORA LOCAL" for item in manifest["legend_reference"]["pairs"]
    )
    candidates = manifest["local_candidates"]
    assert candidates
    assert {item["page"] for item in candidates} == {2}
    assert all(item["class_id"] == "UNKNOWN_LOCAL" for item in candidates)
    assert all(
        item["provenance"]["attributes"]["descricao_legenda"] == "ANCORA LOCAL"
        for item in candidates
    )
    assert any(
        item["method_id"] == "document-local-legend" and item["status"] == "executed"
        for item in executions
    )
