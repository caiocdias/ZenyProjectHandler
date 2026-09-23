"""E08 runner integration on the public development corpus; reserve stays sealed."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from scripts.symbol_benchmark_runner import run_synthetic


def test_raster_opt_in_preserves_legacy_and_recovers_raster_exclusive(tmp_path: Path) -> None:
    baseline = run_synthetic(tmp_path / "vector")
    combined = run_synthetic(tmp_path / "combined", include_raster=True)

    baseline_report = baseline["report"]
    report = combined["report"]
    legacy = "legacy-vector-symbols"
    template = "raster-template"
    hough = "raster-hough-generalizado"

    assert report["methods"][legacy]["micro"] == baseline_report["methods"][legacy]["micro"]
    assert report["methods"][template]["micro"]["tp"] > 0
    assert {"dev-raster-p1-o00", "dev-raster-p1-o01"} <= set(
        report["complementarity"]["by_method"][template]["exclusive_tp_reference_ids"]
    )
    assert (
        report["compositions"]["raw_union"]["micro"]["tp"]
        > report["methods"][legacy]["micro"]["tp"]
    )
    assert combined["manifest"]["raster_configuration_unchanged"]
    assert combined["manifest"]["counts"]["pages_failed"] == 0
    if importlib.util.find_spec("cv2") is None:
        assert all(
            item["status"] == "not_applicable" for item in report["methods"][hough]["executions"]
        )
